## Copyright (C) 2026  Solaar Contributors https://pwr-solaar.github.io/Solaar/
##
## This program is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation; either version 2 of the License, or
## (at your option) any later version.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License along
## with this program; if not, write to the Free Software Foundation, Inc.,
## 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

"""A receiver that comes back (e.g. through a USB switch) reports its devices'
links before they answer requests. The listener must not set up such a device
until it answers, instead of leaving it half set up and offline."""

import logging

from types import SimpleNamespace

import pytest

from logitech_receiver import exceptions
from logitech_receiver.base import HIDPPNotification
from logitech_receiver.common import Notification
from solaar import listener

# connection notifications for a Bolt mouse (B034) in slot 2, as sent by a real receiver
LINK_UP = HIDPPNotification(0x10, 2, Notification.DJ_PAIRING, 0x10, b"\x02\x34\xb0")
LINK_DOWN = HIDPPNotification(0x10, 2, Notification.DJ_PAIRING, 0x10, b"\x42\x34\xb0")


class FakeDevice:
    number = 2
    wpid = "B034"
    kind = "mouse"
    _serial = None

    def __init__(self, answers=()):
        self.answers = list(answers)  # results of successive pings; True, False, or an exception
        self.pings = 0
        self.activated = False
        self.online = None
        self.link_encrypted = None
        self.status_callback = None
        self.changes = []

    def ping(self):
        self.pings += 1
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        self.online = answer
        return answer

    def changed(self, active=None, alert=None, reason=None, push=False):
        self.changes.append(active)
        if active is not None:
            self.online = self.activated = active


class FakeReceiver:
    path = "/dev/hidraw15"
    isDevice = False
    kind = None
    receiver_kind = "bolt"

    def __init__(self, *devices):
        self.devices = {d.number: d for d in devices}
        self.status_callback = None
        self.pairing = SimpleNamespace(lock_open=False)

    def __contains__(self, number):
        return number in self.devices

    def __getitem__(self, number):
        return self.devices[number]


@pytest.fixture
def clock(mocker):
    clock = mocker.patch.object(listener, "time")
    clock.time.return_value = 1000.0
    return clock


@pytest.fixture
def process(mocker):
    return mocker.patch.object(listener.notifications, "process")


def _listener(device):
    return listener.SolaarListener(FakeReceiver(device), lambda *args, **kwargs: None)


def test_answering_device_is_set_up_at_once(clock, process):
    dev = FakeDevice(answers=[True])
    events = _listener(dev)

    events._process_connection(dev, LINK_UP)

    process.assert_called_once_with(dev, LINK_UP)
    assert dev.changes == []
    assert not events._pending_activations


def test_27mhz_device_is_not_pinged(clock, process):
    dev = FakeDevice()
    events = _listener(dev)
    notification = HIDPPNotification(0x10, 2, Notification.DJ_PAIRING, 0x02, b"\x00\x00\x10")

    events._process_connection(dev, notification)

    process.assert_called_once_with(dev, notification)
    assert dev.pings == 0


def test_set_up_device_is_not_pinged_again(clock, process):
    dev = FakeDevice()
    dev.activated = True
    events = _listener(dev)

    events._process_connection(dev, LINK_UP)

    process.assert_called_once_with(dev, LINK_UP)
    assert dev.pings == 0


@pytest.mark.parametrize("no_answer", [False, exceptions.NoSuchDevice(number=2, request=0x0010)])
def test_silent_device_is_set_up_once_it_answers(clock, process, no_answer):
    dev = FakeDevice(answers=[no_answer, False, True])
    events = _listener(dev)

    events._process_connection(dev, LINK_UP)

    process.assert_not_called()
    assert dev.changes == [False]  # shown offline while it does not answer
    assert dev.link_encrypted is True

    clock.time.return_value = 1000.4  # first retry is due after 0.5s
    events.tick()
    assert dev.pings == 1

    clock.time.return_value = 1000.5
    events.tick()
    assert dev.pings == 2
    assert dev.changes == [False]

    clock.time.return_value = 1001.5  # second retry is due 1s after the first one
    events.tick()
    assert dev.pings == 3
    assert dev.changes == [False, True]
    assert not events._pending_activations


def test_lost_link_cancels_the_retries(clock, process):
    dev = FakeDevice(answers=[False])
    events = _listener(dev)
    events._process_connection(dev, LINK_UP)

    events._process_connection(dev, LINK_DOWN)
    clock.time.return_value = 2000.0
    events.tick()

    process.assert_called_once_with(dev, LINK_DOWN)
    assert dev.pings == 1


def test_retries_stop_when_a_notification_set_the_device_up(clock, process):
    dev = FakeDevice(answers=[False])
    events = _listener(dev)
    events._process_connection(dev, LINK_UP)

    dev.activated = True  # e.g. a battery notification from the device
    clock.time.return_value = 2000.0
    events.tick()

    assert dev.pings == 1
    assert not events._pending_activations


def test_retries_stop_when_the_device_is_unpaired(clock, process):
    dev = FakeDevice(answers=[False])
    events = _listener(dev)
    events._process_connection(dev, LINK_UP)

    del events.receiver.devices[dev.number]
    clock.time.return_value = 2000.0
    events.tick()

    assert dev.pings == 1
    assert not events._pending_activations


def test_retries_give_up_until_the_device_reconnects(clock, process, caplog):
    retries = len(listener._ACTIVATION_RETRY_DELAYS)
    dev = FakeDevice(answers=[False] * (1 + retries))
    events = _listener(dev)
    events._process_connection(dev, LINK_UP)

    with caplog.at_level(logging.WARNING, logger=listener.__name__):
        for _ in range(retries):
            clock.time.return_value += 10
            events.tick()

    assert dev.pings == 1 + retries
    assert not events._pending_activations
    assert "does not answer" in caplog.text
    assert dev.changes == [False]


def test_link_notification_for_silent_device_is_held_back(clock, process):
    status_changes = []
    dev = FakeDevice(answers=[False, True])
    events = listener.SolaarListener(FakeReceiver(dev), lambda device, *args: status_changes.append(device))

    events._notifications_handler(LINK_UP)

    process.assert_not_called()
    assert dev.status_callback == events._status_changed
    assert dev.changes == [False]
    assert events.receiver in status_changes

    clock.time.return_value += 1
    events.tick()

    assert dev.changes == [False, True]
