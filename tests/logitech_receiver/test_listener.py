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

import pytest

from logitech_receiver import listener


class FakeReceiver:
    path = "/dev/hidraw0"
    handle = 11
    isDevice = False
    name = "receiver"


class TickingListener(listener.EventsListener):
    """Stops after `stop_after` ticks; the first `fail_first` ticks raise."""

    def __init__(self, stop_after=1, fail_first=0):
        super().__init__(FakeReceiver(), lambda n: None)
        self.ticks = 0
        self.stop_after = stop_after
        self.fail_first = fail_first

    def tick(self):
        self.ticks += 1
        if self.ticks <= self.fail_first:
            raise RuntimeError("tick failed")
        if self.ticks >= self.stop_after:
            self.stop()


@pytest.fixture
def quiet_hidraw(mocker):
    """No packets arrive, and closing the fake handle touches no real file descriptor."""
    mocker.patch.object(listener.base, "read", return_value=None)
    mocker.patch.object(listener.base, "close")


def _run(events):
    events.run()
    events.receiver.handle.close()  # while base.close is still patched


def test_tick_runs_after_a_read_without_packets(quiet_hidraw):
    events = TickingListener(stop_after=1)

    _run(events)

    assert events.ticks == 1


def test_failing_tick_does_not_stop_the_listener(quiet_hidraw):
    events = TickingListener(stop_after=2, fail_first=1)

    _run(events)

    assert events.ticks == 2
