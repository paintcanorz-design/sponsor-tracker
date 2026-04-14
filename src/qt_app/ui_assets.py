# -*- coding: utf-8 -*-
"""Inline SVG assets for navigation and accents (no external files)."""
from __future__ import annotations

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_SVG_OVERVIEW = b"""<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="11" width="7" height="10" rx="1.5"/><rect x="3" y="15" width="7" height="6" rx="1.5"/></svg>"""

_SVG_SETTINGS = b"""<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>"""

_SVG_ACCOUNT = b"""<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>"""

_SVG_MINI_DASH = b"""<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none"><path d="M4 18V6l4 8 4-10 4 8 4-6v14H4z" stroke="url(#g)" stroke-width="1.75" stroke-linejoin="round" fill="none"/><defs><linearGradient id="g" x1="4" y1="4" x2="20" y2="20" gradientUnits="userSpaceOnUse"><stop stop-color="#5AC8FA"/><stop offset="1" stop-color="#0A84FF"/></linearGradient></defs></svg>"""

_SVG_ARROW_UP_RIGHT = b"""<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 17L17 7"/><path d="M7 7h10v10"/></svg>"""

# Map-pin style (always-on-top toggle).
_SVG_PIN_TOP = b"""<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1 1 16 0Z"/><circle cx="12" cy="10" r="3"/></svg>"""


def svg_icon(svg_bytes: bytes, size: int = 20, color: str | None = None) -> QIcon:
    data = svg_bytes
    if color:
        data = svg_bytes.replace(b"currentColor", color.encode("utf-8"))
    renderer = QSvgRenderer(QByteArray(data))
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    renderer.render(p)
    p.end()
    return QIcon(pix)


def nav_overview_icon() -> QIcon:
    return svg_icon(_SVG_OVERVIEW)


def nav_settings_icon() -> QIcon:
    return svg_icon(_SVG_SETTINGS)


def nav_account_icon() -> QIcon:
    return svg_icon(_SVG_ACCOUNT)


def compact_open_main_icon(*, size: int = 14, color: str = "#8e8e93") -> QIcon:
    return svg_icon(_SVG_ARROW_UP_RIGHT, size=size, color=color)


def compact_pin_icon(*, size: int = 15, color: str = "#8e8e93") -> QIcon:
    return svg_icon(_SVG_PIN_TOP, size=size, color=color)


def mini_dashboard_icon() -> QIcon:
    renderer = QSvgRenderer(QByteArray(_SVG_MINI_DASH))
    pix = QPixmap(22, 22)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    renderer.render(p)
    p.end()
    return QIcon(pix)
