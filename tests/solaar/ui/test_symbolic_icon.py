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

"""KDE Plasma shows solaar-symbolic in the tray whenever the tray asks for
"solaar", and recolours it for the panel only through the current-color-scheme
stylesheet. GTK recolours the fill of -symbolic icons itself. Either way the
icon has to be one theme colour with no hardcoded paint."""

import xml.etree.ElementTree as ET

from pathlib import Path

SVG_NS = "{http://www.w3.org/2000/svg}"
ICON = Path(__file__).resolve().parents[3] / "share" / "solaar" / "icons" / "solaar-symbolic.svg"


def _style(element):
    declarations = (d.split(":", 1) for d in element.get("style", "").split(";") if ":" in d)
    return {name.strip(): value.strip() for name, value in declarations}


def test_symbolic_icon_has_kde_color_scheme_stylesheet():
    root = ET.parse(ICON).getroot()

    stylesheets = [s for s in root.iter(f"{SVG_NS}style") if s.get("id") == "current-color-scheme"]

    assert len(stylesheets) == 1
    assert ".ColorScheme-Text" in stylesheets[0].text


def test_symbolic_icon_paints_only_the_theme_color():
    root = ET.parse(ICON).getroot()
    paths = list(root.iter(f"{SVG_NS}path"))

    assert paths
    for path in paths:
        style = _style(path)
        assert path.get("class") == "ColorScheme-Text"
        assert style.get("fill") == "currentColor"
        assert style.get("stroke", "none") == "none"
        assert path.get("fill") is None and path.get("stroke") is None


def test_symbolic_icon_has_no_gradients():
    root = ET.parse(ICON).getroot()

    assert not list(root.iter(f"{SVG_NS}linearGradient"))
    assert not list(root.iter(f"{SVG_NS}radialGradient"))
