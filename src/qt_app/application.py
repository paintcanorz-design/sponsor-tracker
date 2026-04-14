# -*- coding: utf-8 -*-
"""PySide6 main window: mirrors app_gui layout, settings, and behavior."""
from __future__ import annotations

import html
import math
import subprocess
import sys
import threading
import time
from functools import partial
from datetime import timedelta
from pathlib import Path
from PySide6.QtCharts import QChart, QChartView, QDateTimeAxis, QLineSeries, QValueAxis
from PySide6.QtCore import (
    QEvent,
    QObject,
    QPoint,
    QRect,
    QDateTime,
    QMargins,
    QSize,
    Qt,
    QSignalBlocker,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QBrush,
    QCloseEvent,
    QDesktopServices,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QIcon,
    QMouseEvent,
    QPainter,
    QColor,
    QPalette,
    QPen,
    QPixmap,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QSystemTrayIcon,
    QMenu,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QLayout,
    QGraphicsDropShadowEffect,
)

from src.paths import project_root
from src.jst import date_days_ago_jst, now_jst, today_jst_str
from src.currency_ui import (
    display_currency_code,
    format_money_jpy_as_display,
    fx_dict_from_config,
    jpy_to_display_amount,
    platform_native_to_jpy,
)
from src.database import (
    clear_sponsorship_data,
    export_daily_summary_csv,
    get_chart_combined_daily_between,
    get_chart_combined_monthly_peaks_last12,
    get_total_vs_days_ago,
    init_db,
    save_record,
    update_daily_summary,
    get_dashboard_stats,
)
from src.exchange import ensure_fx_daily, sync_fx_cache_from_config
from src.fetchers.patreon_fetcher import PatreonFetcher
from src.fetchers.fanbox_fetcher import FanboxFetcher
from src.fetchers.fantia_fetcher import FantiaFetcher
from src.auth.browser_login import fanbox_login, fantia_login, patreon_login, PLAYWRIGHT_AVAILABLE
from src.discord_webhook import (
    format_daily_dashboard_report,
    format_scheduled_increase_message,
    is_discord_webhook_url,
    post_discord_webhook,
    post_discord_webhook_long,
)

from src.app_update import (
    configured_github_repo,
    current_app_version,
    download_zip_and_extract,
    fetch_latest_release_tag,
    fetch_lazy_update_plan,
    git_pull_project,
    lazy_update_supported,
    project_has_git,
    releases_latest_url,
    spawn_lazy_windows_updater,
    version_newer_than,
)

from src.i18n import (
    INCREASE_SOUND_KEYS,
    LANG_EN,
    LANG_JA,
    LANG_ZH_TW,
    SCHEDULE_INTERVAL_MINUTES,
    effective_ui_language,
    get_language,
    increase_sound_label,
    migrate_config_schedule_interval,
    normalize_schedule_interval_id,
    normalize_ui_language_raw,
    schedule_interval_label,
    set_language,
    system_language_guess,
    tr,
)
from src.qt_app.ui_assets import (
    compact_open_main_icon,
    compact_pin_icon,
    mini_dashboard_icon_on_accent,
    nav_account_icon,
    nav_overview_icon,
    nav_settings_icon,
)
from src.qt_app.shared import (
    FONT_FALLBACKS,
    PALETTE,
    palette_apply,
    detach_windows_console_if_present,
    load_config,
    parse_jst_hhmm,
    play_increase_sound,
    save_config,
    normalize_increase_sound_key,
)

_PLATFORM_ORDER: tuple[str, ...] = ("patreon", "fanbox", "fantia")

# Vertical gap after each settings / account section card (headline sits above the card).
_SETTINGS_SECTION_VGAP = 24


def _app_icon_path() -> Path | None:
    roots: list[Path] = [project_root() / "app_icon.ico"]
    if getattr(sys, "frozen", False):
        meip = getattr(sys, "_MEIPASS", None)
        if meip:
            roots.append(Path(meip) / "app_icon.ico")
        try:
            roots.append(Path(sys.executable).resolve().parent / "app_icon.ico")
        except OSError:
            pass
    for p in roots:
        try:
            if p.is_file():
                return p
        except OSError:
            continue
    return None


def _qf(size: int, bold: bool = False, weight: QFont.Weight | None = None) -> QFont:
    f = QFont()
    f.setFamilies(list(FONT_FALLBACKS))
    f.setPointSize(size)
    if weight is not None:
        f.setWeight(weight)
    else:
        f.setBold(bold)
    return f


def _qcolor_hex(hex_rgb: str) -> QColor:
    h = (hex_rgb or "").strip().lstrip("#")
    if len(h) != 6:
        return QColor(0, 122, 255)
    return QColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _sync_qapplication_palette() -> None:
    """After theme switch, align QPalette with PALETTE so light/dark text roles stay correct under Fusion."""
    app = QApplication.instance()
    if app is None:
        return
    c = PALETTE
    p = QPalette()
    mapping: list[tuple[QPalette.ColorRole, str]] = [
        (QPalette.ColorRole.Window, "bg"),
        (QPalette.ColorRole.WindowText, "text"),
        (QPalette.ColorRole.Base, "bg_card"),
        (QPalette.ColorRole.AlternateBase, "bg_elevated"),
        (QPalette.ColorRole.Text, "text"),
        (QPalette.ColorRole.Button, "bg_elevated"),
        (QPalette.ColorRole.ButtonText, "text"),
        (QPalette.ColorRole.ToolTipBase, "bg_card"),
        (QPalette.ColorRole.ToolTipText, "text"),
        (QPalette.ColorRole.PlaceholderText, "text_tertiary"),
    ]
    for group in (
        QPalette.ColorGroup.Active,
        QPalette.ColorGroup.Inactive,
        QPalette.ColorGroup.Disabled,
    ):
        for role, key in mapping:
            p.setColor(group, role, _qcolor_hex(c[key]))
    app.setPalette(p)


def _app_stylesheet() -> str:
    c = PALETTE
    return f"""
    /* ── Global ────────────────────────────────────────────── */
    QMainWindow {{ background-color: {c["bg"]}; color: {c["text"]} !important; }}
    QWidget#centralRoot {{ background-color: {c["bg"]}; }}
    QWidget#pageDash {{ background-color: {c["bg"]}; }}
    QWidget#pageSettings {{ background-color: {c["bg_grouped"]}; }}
    QWidget#pagePrefs {{ background-color: {c["bg_grouped"]}; }}
    QWidget#pageAccount {{ background-color: {c["bg_grouped"]}; }}
    QWidget#scrollContent {{ background-color: transparent; }}
    QLabel {{ color: {c["text"]} !important; }}
    QToolTip {{
        background-color: {c["bg_elevated"]};
        border: 1px solid {c["border_light"]};
        border-radius: 6px;
        color: {c["text"]};
        padding: 5px 8px;
        font-size: 12px;
    }}

    /* ── Dashboard Labels ──────────────────────────────────── */
    QLabel#pageEyebrow {{
        color: {c["text_tertiary"]} !important;
        font-size: 11px; font-weight: 600; letter-spacing: 1.2px;
    }}
    QLabel#pageHeadline {{
        color: {c["text"]} !important;
        font-size: 28px; font-weight: 800; letter-spacing: -0.3px;
    }}
    QLabel#platSectionLabel {{
        color: {c["text"]} !important;
        font-size: 20px; font-weight: 700;
    }}

    /* ── Settings Labels ───────────────────────────────────── */
    QLabel#settingsHeadline {{
        color: {c["text"]} !important;
        font-size: 16px; font-weight: 700;
        margin-top: 0px; margin-bottom: 2px;
    }}
    QLabel#settingsBlurb {{
        color: {c["text_secondary"]} !important;
        font-size: 12px;
        margin-top: 0px; margin-bottom: 6px;
    }}
    QLabel#settingsFormLabel {{
        color: {c["text_secondary"]} !important;
        font-size: 12px; font-weight: 500;
    }}
    QLabel#settingsStatus {{
        color: {c["text_secondary"]} !important;
        font-size: 13px;
    }}

    /* ── Header Bar ────────────────────────────────────────── */
    QFrame#appHeader {{
        background-color: {c["bg_sidebar"]};
        border: none;
        border-bottom: 1px solid {c["hairline"]};
    }}
    QLabel#appTitle {{
        color: {c["text"]} !important;
        font-size: 17px; font-weight: 700; letter-spacing: -0.2px;
    }}
    QLabel#appSubtitle {{
        color: {c["text_tertiary"]} !important;
        font-size: 12px; letter-spacing: 0.1px;
    }}
    QLabel#headerFxRate {{
        color: {c["text_tertiary"]} !important;
        font-size: 10px;
        font-weight: 500;
        letter-spacing: 0.05px;
    }}
    QFrame#headerFxBlock {{
        background-color: {c["bg_elevated"]};
        border-radius: 12px;
        border: 1px solid {c["border_light"]};
    }}
    QPushButton#headerPill {{
        background-color: transparent;
        border: none; border-radius: 8px;
        color: {c["accent"]}; font-size: 13px; font-weight: 600;
        padding: 8px 14px; min-height: 28px;
    }}
    QPushButton#headerPill:hover {{
        background-color: {c["segment_hover"]};
    }}
    QPushButton#headerPill:pressed {{
        background-color: {c["border_light"]};
    }}

    QFrame#navTabBar {{
        background-color: {c["segment_bg"]};
        border-radius: 10px;
        border: none;
    }}
    QPushButton#navTab {{
        background-color: transparent;
        border: none;
        border-radius: 8px;
        color: {c["text_secondary"]};
        font-size: 13px;
        font-weight: 600;
        padding: 8px 14px;
        text-align: left;
    }}
    QPushButton#navTab:hover {{
        background-color: {c["segment_hover"]};
        color: {c["text"]};
    }}
    QPushButton#navTab:checked {{
        background-color: {c["accent"]};
        color: #ffffff;
    }}
    QPushButton#navTab:checked:hover {{
        background-color: {c["accent_hover"]};
        color: #ffffff;
    }}

    QPushButton#headerMiniPill {{
        background-color: {c["accent"]};
        color: #ffffff;
        border: none;
        border-radius: 11px;
        padding: 2px 16px 2px 12px;
        min-height: 38px;
        font-size: 14px;
        font-weight: 700;
        letter-spacing: 0.02em;
    }}
    QPushButton#headerMiniPill:hover {{
        background-color: {c["accent_hover"]};
    }}
    QPushButton#headerMiniPill:pressed {{
        background-color: {c["accent"]};
    }}

    /* ── Card System ───────────────────────────────────────── */
    QFrame#card {{
        background-color: {c["bg_card"]};
        border: 1px solid {c["border_light"]};
        border-radius: 14px;
    }}
    QFrame#dashHeroPrimary {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {c["dash_hero_top"]}, stop:1 {c["dash_hero_bottom"]});
        border: 1px solid {c["border_light"]};
        border-radius: 14px;
    }}
    QFrame#statTile {{
        background-color: {c["bg_card"]};
        border: 1px solid {c["border_light"]};
        border-radius: 14px;
    }}
    QFrame#platTile {{
        background-color: {c["bg_card"]};
        border: 1px solid {c["border_light"]};
        border-radius: 14px;
    }}
    QFrame#card QLabel,
    QFrame#statTile QLabel,
    QFrame#platTile QLabel,
    QFrame#dashHeroPrimary QLabel {{
        background-color: transparent;
        color: {c["text"]} !important;
    }}

    /* ── Buttons ───────────────────────────────────────────── */
    QPushButton {{
        border-radius: 10px;
        padding: 9px 18px; min-height: 22px;
        background-color: {c["bg_elevated"]};
        border: 1px solid {c["border_light"]};
        color: {c["text"]} !important;
        font-size: 13px; font-weight: 500;
    }}
    QPushButton:hover {{
        background-color: {c["bg_card_hover"]};
        border-color: {c["border"]};
    }}
    QPushButton:pressed {{
        background-color: {c["border_light"]};
    }}
    QPushButton#primary {{
        background-color: {c["accent"]}; color: #ffffff;
        border: none; font-weight: 600;
    }}
    QPushButton#primary:hover {{ background-color: {c["accent_hover"]}; }}
    QPushButton#primary:pressed {{ background-color: #0070d6; }}
    QPushButton#success {{
        background-color: {c["success"]}; color: #ffffff;
        border: none; font-weight: 600;
    }}
    QPushButton#success:hover {{ background-color: #2bb848; }}
    QPushButton#success:pressed {{ background-color: #26a040; }}
    QPushButton#danger {{
        background-color: {c["error"]}; color: #ffffff;
        border: none; font-weight: 600;
    }}
    QPushButton#danger:hover {{ background-color: #e03e32; }}
    QPushButton#danger:pressed {{ background-color: #c7362c; }}

    /* ── Form Inputs ───────────────────────────────────────── */
    QLineEdit, QComboBox {{
        background-color: {c["bg_elevated"]};
        border: 1px solid {c["border_light"]};
        border-radius: 10px;
        padding: 9px 14px; min-height: 22px;
        color: {c["text"]} !important;
        font-size: 13px;
        selection-background-color: {c["accent"]};
        selection-color: #ffffff;
    }}
    QLineEdit:focus, QComboBox:focus {{
        border: 1.5px solid {c["accent"]};
    }}
    QComboBox::drop-down {{ border: none; width: 28px; }}
    QComboBox QAbstractItemView {{
        background-color: {c["bg_card"]};
        border: 1px solid {c["border_light"]};
        border-radius: 10px; padding: 4px;
        outline: none;
        color: {c["text"]} !important;
        selection-background-color: {c["accent"]};
        selection-color: #ffffff;
    }}

    /* ── Checkbox (iOS-inspired) ───────────────────────────── */
    QCheckBox {{
        spacing: 10px; color: {c["text"]} !important; font-size: 13px;
    }}
    QCheckBox::indicator {{
        width: 20px; height: 20px;
        border-radius: 6px;
        border: 1.5px solid {c["border"]};
        background-color: transparent;
    }}
    QCheckBox::indicator:hover {{
        border-color: {c["accent"]};
    }}
    QCheckBox::indicator:checked {{
        background-color: {c["accent"]};
        border-color: {c["accent"]};
    }}

    /* ── Slider ────────────────────────────────────────────── */
    QSlider::groove:horizontal {{
        height: 4px; background: {c["border_light"]};
        border-radius: 2px;
    }}
    QSlider::sub-page:horizontal {{
        background: {c["accent"]}; border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        background: #ffffff;
        width: 18px; height: 18px; margin: -7px 0;
        border-radius: 9px; border: none;
    }}
    QSlider::handle:horizontal:hover {{
        background: #e8e8ed;
    }}

    /* ── Scrollbars (thin, macOS-like) ─────────────────────── */
    QScrollArea {{ border: none; background: transparent; }}
    QScrollBar:vertical {{
        width: 8px; background: transparent; margin: 4px 0;
    }}
    QScrollBar::handle:vertical {{
        background: {c["border_light"]};
        border-radius: 4px; min-height: 32px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {c["border"]};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar:horizontal {{
        height: 8px; background: transparent; margin: 0 4px;
    }}
    QScrollBar::handle:horizontal {{
        background: {c["border_light"]};
        border-radius: 4px; min-width: 32px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {c["border"]};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

    /* ── Menu ──────────────────────────────────────────────── */
    QMenu {{
        background-color: {c["bg_elevated"]};
        border: 1px solid {c["border_light"]};
        border-radius: 12px; padding: 6px;
    }}
    QMenu::item {{
        padding: 8px 20px; border-radius: 8px;
        color: {c["text"]} !important;
    }}
    QMenu::item:selected {{
        background-color: {c["accent"]}; color: #ffffff;
    }}
    QMenu::separator {{
        height: 1px; margin: 4px 10px;
        background: {c["hairline"]};
    }}

    /* ── MessageBox ────────────────────────────────────────── */
    QMessageBox {{ background-color: {c["bg_elevated"]}; }}
    QMessageBox QLabel {{
        color: {c["text"]} !important;
        min-width: 280px; font-size: 13px;
    }}
    QMessageBox QPushButton {{ min-width: 72px; }}

    /* ── Settings Cards ────────────────────────────────────── */
    QFrame#settingsGroupCard {{
        background-color: {c["bg_card"]};
        border: 1px solid {c["border_light"]};
        border-radius: 12px;
    }}
    QFrame#settingsDivider {{
        background-color: {c["hairline"]};
        border: none; max-height: 1px; min-height: 1px;
    }}
    """


def _compact_window_stylesheet() -> str:
    c = PALETTE
    return f"""
    QWidget#compactRoot {{
        background-color: {c["bg_grouped"]};
        border: none;
        border-radius: 18px;
    }}
    QFrame#compactOuter {{
        background-color: {c["bg_grouped"]};
        border: 1px solid {c["hairline"]};
        border-radius: 15px;
    }}
    QFrame#compactInner {{
        background-color: {c["bg_card"]};
        border: none;
        border-radius: 12px;
    }}
    QWidget#compactPanel {{
        background-color: transparent;
        border: none;
    }}
    QLabel {{
        color: {c["text"]} !important;
        background: transparent;
    }}
    QToolButton#compactPinBtn {{
        background: transparent;
        border: none;
        border-radius: 6px;
        padding: 1px;
        min-width: 22px;
        min-height: 22px;
    }}
    QToolButton#compactPinBtn:hover {{
        background-color: {c["segment_hover"]};
    }}
    QToolButton#compactPinBtn:checked {{
        background-color: {c["accent_soft"]};
    }}
    QToolButton#compactTool {{
        background-color: transparent;
        border: 1px solid {c["border_light"]};
        border-radius: 6px;
        color: {c["accent"]};
        padding: 2px 6px;
        font-size: 10px; min-height: 20px;
    }}
    QToolButton#compactTool:hover {{
        background-color: {c["bg_card_hover"]};
        color: {c["text"]} !important;
    }}
    QToolButton#compactTool:checked {{
        background-color: {c["accent"]};
        color: #ffffff; border-color: {c["accent"]};
    }}
    QToolButton#compactToolAccent {{
        background-color: {c["bg_elevated"]};
        border: 1px solid {c["border"]};
        border-radius: 6px;
        color: {c["accent"]}; font-weight: 600;
        padding: 2px 6px; font-size: 10px; min-height: 20px;
    }}
    QToolButton#compactToolAccent:hover {{
        background-color: {c["bg_card_hover"]};
    }}
    QToolButton#compactChromeBtn {{
        background: transparent;
        border: none;
        border-radius: 6px;
        padding: 1px;
        min-width: 22px;
        min-height: 22px;
    }}
    QToolButton#compactChromeBtn:hover {{
        background-color: {c["segment_hover"]};
    }}
    """


def _make_card(parent: QWidget, object_name: str = "card") -> QFrame:
    f = QFrame(parent)
    f.setObjectName(object_name)
    f.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
    return f


def _make_settings_group_card(parent: QWidget) -> QFrame:
    f = QFrame(parent)
    f.setObjectName("settingsGroupCard")
    f.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
    return f


def _settings_form_label(text: str) -> QLabel:
    w = QLabel(text)
    w.setObjectName("settingsFormLabel")
    w.setWordWrap(True)
    return w


def _tray_icon_pixmap() -> QPixmap:
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(_qcolor_hex(PALETTE["accent"]))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(8, 8, 48, 48, 12, 12)
    p.setPen(QColor(255, 255, 255))
    p.setFont(_qf(28, True))
    p.drawText(QRect(0, 0, 64, 64), Qt.AlignmentFlag.AlignCenter, "\u00a5")
    p.end()
    return pix


class CompactFloatWindow(QWidget):
    """Mini dashboard: native surface + frameless chrome; drag client area; arrow opens main."""

    _PLAT_NAMES = {"patreon": "Patreon", "fanbox": "Fanbox", "fantia": "Fantia"}

    def __init__(self, app: SponsorMainWindow):
        super().__init__(
            None,
            # Tool: no taskbar button. Frameless: no system caption bar. Stays on top optional.
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self._app = app
        self._compact_drag_start: QPoint | None = None
        self._compact_win_start = QPoint()
        self._compact_dpi_signals_hooked = False
        self._compact_move_shrink_timer = QTimer(self)
        self._compact_move_shrink_timer.setSingleShot(True)
        self._compact_move_shrink_timer.setInterval(80)
        self._compact_move_shrink_timer.timeout.connect(self._shrink_compact_window)
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self.setWindowTitle(tr("app.title_compact"))
        self.setMinimumWidth(320)
        self.setMaximumWidth(16777215)
        self.setMaximumHeight(16777215)
        self.setStyleSheet(_compact_window_stylesheet())
        self.setToolTip(tr("compact.tooltip"))

        scr = QGuiApplication.primaryScreen()
        if scr is not None:
            g = scr.availableGeometry()
            self.move(g.right() - self.frameSize().width() - 20, g.top() + 20)

        self.setObjectName("compactRoot")
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(0)
        root.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)

        outer = QFrame()
        outer.setObjectName("compactOuter")
        outer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        _sh = QGraphicsDropShadowEffect(outer)
        _sh.setBlurRadius(18)
        _sh.setColor(QColor(0, 0, 0, 38))
        _sh.setOffset(0, 3)
        outer.setGraphicsEffect(_sh)
        ol = QVBoxLayout(outer)
        ol.setContentsMargins(2, 2, 2, 2)
        ol.setSpacing(0)

        inner = QFrame()
        inner.setObjectName("compactInner")
        inner.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        il = QVBoxLayout(inner)
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(0)

        panel = QWidget()
        self._compact_panel = panel
        panel.setObjectName("compactPanel")
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        panel.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        panel.customContextMenuRequested.connect(lambda p: self._show_compact_menu(panel, p))
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(14, 10, 14, 12)
        pl.setSpacing(6)

        row_total = QHBoxLayout()
        row_total.setSpacing(6)
        self._total_lbl = QLabel("\u00a50")
        self._total_lbl.setFont(_qf(16, True))
        self._total_lbl.setStyleSheet(f"color: {PALETTE['text']} !important;")
        row_total.addWidget(self._total_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        row_total.addStretch(1)
        self._patrons_lbl = QLabel("")
        self._patrons_lbl.setFont(_qf(13, False))
        self._patrons_lbl.setStyleSheet(f"color: {PALETTE['text_secondary']} !important;")
        self._patrons_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        row_total.addWidget(self._patrons_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        self._inc_arrow_lbl = QLabel("")
        self._inc_arrow_lbl.setFont(_qf(11, True))
        self._inc_arrow_lbl.setStyleSheet(f"color: {PALETTE['success']} !important;")
        row_total.addWidget(self._inc_arrow_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        self._btn_compact_pin = QToolButton()
        self._btn_compact_pin.setObjectName("compactPinBtn")
        self._btn_compact_pin.setCheckable(True)
        self._btn_compact_pin.setChecked(
            bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        )
        self._btn_compact_pin.setToolTip(tr("header.pin"))
        self._btn_compact_pin.setAutoRaise(True)
        self._btn_compact_pin.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_compact_pin.toggled.connect(self._on_topmost_toggled)
        self._sync_compact_pin_icon()
        row_total.addWidget(self._btn_compact_pin, 0, Qt.AlignmentFlag.AlignVCenter)
        self._btn_compact_open_main = QToolButton()
        self._btn_compact_open_main.setObjectName("compactChromeBtn")
        _arrow_col = PALETTE["text_tertiary"]
        self._btn_compact_open_main.setIcon(
            compact_open_main_icon(size=12, color=_arrow_col)
        )
        self._btn_compact_open_main.setIconSize(QSize(12, 12))
        self._btn_compact_open_main.setToolTip(tr("compact.open_main"))
        self._btn_compact_open_main.setAutoRaise(True)
        self._btn_compact_open_main.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_compact_open_main.clicked.connect(self._expand)
        row_total.addWidget(self._btn_compact_open_main, 0, Qt.AlignmentFlag.AlignVCenter)
        pl.addLayout(row_total)

        self._increase_lbl = QLabel("")
        self._increase_lbl.setFont(_qf(10, True))
        self._increase_lbl.setStyleSheet(f"color: {PALETTE['success']} !important;")
        self._increase_lbl.setMinimumHeight(0)
        self._increase_lbl.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self._increase_lbl.hide()
        pl.addWidget(self._increase_lbl)

        self._plat_host = QWidget()
        self._plat_grid = QGridLayout(self._plat_host)
        self._plat_grid.setContentsMargins(0, 4, 0, 0)
        self._plat_grid.setHorizontalSpacing(14)
        pl.addWidget(self._plat_host)

        self._plat_amount_min_w = QFontMetrics(_qf(15, True)).horizontalAdvance("\u00a5999,999") + 10

        il.addWidget(panel, 0, Qt.AlignmentFlag.AlignTop)
        ol.addWidget(inner, 0, Qt.AlignmentFlag.AlignTop)
        root.addWidget(outer, 0, Qt.AlignmentFlag.AlignTop)

        for _cw in [outer, inner, panel] + outer.findChildren(QWidget):
            _cw.installEventFilter(self)

        self._indicator_timer = QTimer(self)
        self._indicator_timer.timeout.connect(self._update_indicator)
        self._indicator_timer.start(30_000)

        self.refresh()
        self._shrink_compact_window()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self._hook_compact_dpi_signals)
        QTimer.singleShot(0, self._shrink_compact_window)

    def _hook_compact_dpi_signals(self) -> None:
        wh = self.windowHandle()
        if wh is None or self._compact_dpi_signals_hooked:
            return
        self._compact_dpi_signals_hooked = True
        wh.screenChanged.connect(self._on_compact_dpi_environment_changed)

    def moveEvent(self, event):
        super().moveEvent(event)
        self._compact_move_shrink_timer.start()

    def _on_compact_dpi_environment_changed(self, *args: object) -> None:
        QTimer.singleShot(0, self._shrink_compact_window)

    def _shrink_compact_window(self) -> None:
        """Fit window to content in logical pixels (re-run after screen / DPI changes)."""
        self.setMaximumWidth(16777215)
        self.setMaximumHeight(16777215)
        lay = self.layout()
        if lay is not None:
            lay.invalidate()
            lay.activate()
        self.updateGeometry()
        sh = self.sizeHint()
        if sh.isValid() and sh.width() > 0 and sh.height() > 0:
            self.resize(sh)

    def closeEvent(self, event: QCloseEvent):
        app = self._app
        if app._compact_win is self:
            app._compact_win = None
        event.accept()
        app.showNormal()
        app.raise_()
        app.activateWindow()

    def _expand(self):
        self._app._hide_compact()

    def _compact_drag_allowed(self, watched: QObject) -> bool:
        return watched not in (self._btn_compact_open_main, self._btn_compact_pin)

    def _sync_compact_pin_icon(self) -> None:
        on = self._btn_compact_pin.isChecked()
        col = PALETTE["accent"] if on else PALETTE["text_tertiary"]
        self._btn_compact_pin.setIcon(compact_pin_icon(size=12, color=col))
        self._btn_compact_pin.setIconSize(QSize(12, 12))

    def eventFilter(self, watched, event):
        if isinstance(event, QMouseEvent) and self._compact_drag_allowed(watched):
            if event.type() == QEvent.Type.MouseButtonDblClick and event.button() == Qt.MouseButton.LeftButton:
                self._expand()
                return True
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._compact_drag_start = event.globalPosition().toPoint()
                self._compact_win_start = self.pos()
                return False
            if event.type() == QEvent.Type.MouseMove:
                if (
                    self._compact_drag_start is not None
                    and event.buttons() & Qt.MouseButton.LeftButton
                ):
                    delta = event.globalPosition().toPoint() - self._compact_drag_start
                    self.move(self._compact_win_start + delta)
                return False
            if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                self._compact_drag_start = None
                return False
        return super().eventFilter(watched, event)

    def _show_compact_menu(self, host: QWidget, pos: QPoint):
        menu = QMenu(self)
        act_top = QAction(tr("header.pin"), self)
        act_top.setCheckable(True)
        act_top.setChecked(bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint))
        act_top.toggled.connect(self._on_topmost_toggled)
        menu.addAction(act_top)
        act_up = QAction(tr("tray.update"), self)
        act_up.triggered.connect(self._app._run_update)
        menu.addAction(act_up)
        act_main = QAction(tr("tray.show"), self)
        act_main.triggered.connect(self._expand)
        menu.addAction(act_main)
        menu.exec(host.mapToGlobal(pos))

    def _on_topmost_toggled(self, on: bool):
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, bool(on))
        self._btn_compact_pin.blockSignals(True)
        self._btn_compact_pin.setChecked(bool(on))
        self._btn_compact_pin.blockSignals(False)
        self._sync_compact_pin_icon()
        self.show()

    def _clear_plat_grid(self) -> None:
        while self._plat_grid.count():
            item = self._plat_grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def refresh(self, stats: dict | None = None):
        self._total_lbl.setStyleSheet(f"color: {PALETTE['text']} !important;")
        self._patrons_lbl.setStyleSheet(f"color: {PALETTE['text_secondary']} !important;")
        self._inc_arrow_lbl.setStyleSheet(f"color: {PALETTE['success']} !important;")
        self._increase_lbl.setStyleSheet(f"color: {PALETTE['success']} !important;")
        if stats is None:
            try:
                s = get_dashboard_stats()
            except Exception:
                return
        else:
            s = stats
        s = self._app._filter_stats_for_dashboard(s)
        total = float(s.get("total_amount") or 0)
        cfg = self._app.config
        self._total_lbl.setText(format_money_jpy_as_display(total, cfg))
        patrons = int(s.get("total_patron_count") or 0)
        pp = tr("common.people")
        self._patrons_lbl.setText(
            f"{patrons:,} {pp}".strip() if pp else f"{patrons:,}"
        )
        fx = fx_dict_from_config(cfg)
        uj = float(fx.get("usd_jpy") or 150)
        platforms = s.get("by_platform") or []
        tc = PALETTE["text"]
        self._clear_plat_grid()
        for col, p in enumerate(platforms):
            plat = str(p.get("platform") or "")
            amt = float(p.get("amount") or 0)
            cur = (p.get("currency") or "JPY").upper()
            amt_jpy = platform_native_to_jpy(amt, plat, cur, uj)
            color = {
                "patreon": PALETTE["patreon"],
                "fanbox": PALETTE["fanbox"],
                "fantia": PALETTE["fantia"],
            }.get(plat, PALETTE["accent"])
            name = self._PLAT_NAMES.get(plat, plat)
            name_esc = html.escape(name)
            line1 = (
                f"<span style='color:{color}; font-weight:600; font-size:11px; "
                f"letter-spacing:0.2px'>\u25cf {name_esc}</span>"
            )
            line2 = (
                f"<span style='color:{tc}; font-weight:700; font-size:15px; "
                f"letter-spacing:-0.35px'>{html.escape(format_money_jpy_as_display(amt_jpy, cfg))}</span>"
            )
            lbl = QLabel()
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setWordWrap(True)
            lbl.setMinimumHeight(30)
            lbl.setMinimumWidth(self._plat_amount_min_w)
            lbl.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.MinimumExpanding)
            lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            lbl.setText(line1 + "<br>" + line2)
            self._plat_grid.addWidget(lbl, 0, col, Qt.AlignmentFlag.AlignTop)
            self._plat_grid.setColumnStretch(col, 1)
        inc_this = getattr(self._app, "_last_update_increase", None) or 0
        if inc_this > 0:
            self._increase_lbl.setText(
                f"\u25b2 "
                + tr(
                    "dash.sub.this_update",
                    amt=format_money_jpy_as_display(float(inc_this), cfg, signed=True),
                )
            )
            self._increase_lbl.show()
        else:
            self._increase_lbl.setText("")
            self._increase_lbl.hide()
        self._update_indicator()
        self._shrink_compact_window()

    def _update_indicator(self):
        until = getattr(self._app, "_increase_indicator_until", None)
        active = bool(until is not None and now_jst() <= until)
        self._inc_arrow_lbl.setText("\u25b2" if active else "")


class SponsorMainWindow(QMainWindow):
    """\u8de8\u57f7\u7dd2\u7528\uff1a\u7248\u672c\u6aa2\u67e5\u5de5\u4f5c\u7d50\u679c\u5fc5\u9808\u56de\u5230\u4e3b\u57f7\u7dd2\u986f\u793a\u5c0d\u8a71\u6846\uff08\u4e0d\u53ef\u5728\u5de5\u4f5c\u57f7\u7dd2\u7528 QTimer.singleShot\u3002\uff09"""
    _update_check_worker_done = Signal(object)
    # Playwright \u5728\u80cc\u666f\u57f7\u7dd2\u56de\u547c cookie \u6642\uff0c\u5fc5\u9808\u7528 Signal \u6392\u968a\u56de\u4e3b\u57f7\u7dd2\uff08\u4e0d\u53ef\u5728\u8a72\u57f7\u7dd2 QTimer.singleShot\uff09\u3002
    _browser_login_payload = Signal(str, int, str)
    # \u80cc\u666f\u57f7\u7dd2\u5b8c\u6210\u8cc7\u6599\u64f7\u53d6\u5f8c\u6392\u968a\u56de\u4e3b\u57f7\u7dd2\uff08\u4e0d\u7528 QTimer.singleShot\uff09
    _manual_update_done = Signal(object, bool)
    _manual_update_failed = Signal(str)
    _dashboard_data_ready = Signal(int, object, object, bool, object)
    _oneclick_check_done = Signal(object)
    _oneclick_dl_done = Signal(object)
    _oneclick_dl_progress = Signal(int, int)

    def __init__(self):
        super().__init__()
        self.config = load_config()
        if migrate_config_schedule_interval(self.config):
            save_config(self.config)
        set_language(effective_ui_language(self.config))
        self.setWindowTitle(tr("app.title"))
        _ico = _app_icon_path()
        if _ico is not None:
            self.setWindowIcon(QIcon(str(_ico)))
        self.resize(1240, 820)
        self.setMinimumSize(980, 700)
        _gui0 = self.config.get("gui") or {}
        self._sounds_muted = bool(_gui0.get("sounds_muted", False))
        self._close_to_tray = bool(_gui0.get("close_to_tray", True))
        self._minimize_to_tray = bool(_gui0.get("minimize_to_tray", True))
        self._start_minimized_to_tray = bool(_gui0.get("start_minimized_to_tray", False))
        self._start_with_windows = bool(_gui0.get("start_with_windows", True))
        self._tray: QSystemTrayIcon | None = None
        self._dash_debounce: QTimer | None = None
        self._dashboard_fetch_seq = 0
        self._pending_dashboard_stats: dict | None = None
        self.browser_done_events: dict = {}
        self.browser_cancel_events: dict[str, threading.Event] = {}
        self._login_flow_active = {"patreon": False, "fanbox": False, "fantia": False}
        self._browser_login_generation = {"patreon": 0, "fanbox": 0, "fantia": 0}
        self._stack: QStackedWidget | None = None
        self._nav_group: QButtonGroup | None = None
        self._nav_btns: list[QPushButton] = []
        self._compact_win: CompactFloatWindow | None = None
        self._is_topmost = False
        self._schedule_running = False
        self._sched_thread: threading.Thread | None = None
        self._last_daily_report_sent_jst_date: str | None = None
        self._daily_report_thread_started = False
        self._last_update_increase: float | None = None
        self._increase_indicator_until = None
        self._sound_vol_timer: QTimer | None = None
        self._app_update_busy = False
        self._oneclick_busy = False
        self._oneclick_prog: QProgressDialog | None = None
        self._settings_i18n_headings: list[tuple[QLabel, str]] = []
        self._settings_i18n_blurbs: list[tuple[QLabel, str]] = []
        self._last_update_time_jst: str = ""
        self._update_check_worker_done.connect(self._on_update_check_worker_done)
        self._browser_login_payload.connect(
            self._on_browser_login_payload, Qt.ConnectionType.QueuedConnection
        )
        self._manual_update_done.connect(self._update_done, Qt.ConnectionType.QueuedConnection)
        self._manual_update_failed.connect(self._update_fail, Qt.ConnectionType.QueuedConnection)
        self._dashboard_data_ready.connect(
            self._on_dashboard_data_ready, Qt.ConnectionType.QueuedConnection
        )
        self._oneclick_check_done.connect(
            self._on_oneclick_check_done, Qt.ConnectionType.QueuedConnection
        )
        self._oneclick_dl_done.connect(
            self._on_oneclick_dl_done, Qt.ConnectionType.QueuedConnection
        )
        self._oneclick_dl_progress.connect(
            self._on_oneclick_dl_progress, Qt.ConnectionType.QueuedConnection
        )

        sync_fx_cache_from_config(self.config)
        init_db()
        self._build_ui()
        QTimer.singleShot(0, self._refresh_header_fx_labels)
        self._init_tray()
        QTimer.singleShot(120, self._ensure_daily_report_thread)
        QTimer.singleShot(80, self._apply_schedule_preferences)
        QTimer.singleShot(400, self._sync_windows_autostart)
        if self._start_minimized_to_tray and self._tray:
            QTimer.singleShot(280, self._apply_start_minimized_to_tray)

    def _ui_runner(self, fn):
        QTimer.singleShot(0, fn)

    # --- tray / lifecycle ---
    def _init_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self._tray = None
            return
        self._tray = QSystemTrayIcon(self)
        _ico = _app_icon_path()
        self._tray.setIcon(QIcon(str(_ico)) if _ico is not None else QIcon(_tray_icon_pixmap()))
        self._tray.setToolTip(tr("tray.tip"))
        menu = QMenu()
        self._tray_menu = menu
        self._tray_act_show = QAction(tr("tray.show"), self)
        self._tray_act_show.triggered.connect(self._tray_show_main)
        menu.addAction(self._tray_act_show)
        menu.addSeparator()
        self._act_compact = QAction(tr("tray.compact"), self)
        self._act_compact.setCheckable(True)
        self._act_compact.triggered.connect(self._tray_toggle_compact)
        menu.addAction(self._act_compact)
        self._act_top = QAction(tr("tray.main_top"), self)
        self._act_top.setCheckable(True)
        self._act_top.triggered.connect(self._toggle_topmost)
        menu.addAction(self._act_top)
        menu.addSeparator()
        self._act_mute = QAction(tr("tray.mute"), self)
        self._act_mute.setCheckable(True)
        self._act_mute.triggered.connect(self._tray_toggle_mute)
        menu.addAction(self._act_mute)
        self._tray_act_up = QAction(tr("tray.update"), self)
        self._tray_act_up.triggered.connect(self._run_update)
        menu.addAction(self._tray_act_up)
        self._tray_act_copy = QAction(tr("tray.copy"), self)
        self._tray_act_copy.triggered.connect(self._copy_dashboard_total_to_clipboard)
        menu.addAction(self._tray_act_copy)
        menu.addSeparator()
        self._tray_act_restart = QAction(tr("tray.restart"), self)
        self._tray_act_restart.triggered.connect(self._restart_application)
        menu.addAction(self._tray_act_restart)
        self._tray_act_quit = QAction(tr("tray.quit"), self)
        self._tray_act_quit.triggered.connect(self._quit_fully)
        menu.addAction(self._tray_act_quit)
        self._tray.setContextMenu(menu)
        menu.aboutToShow.connect(self._sync_tray_menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _sync_tray_menu(self):
        c = self._compact_win is not None and self._compact_win.isVisible()
        self._act_compact.setChecked(c)
        self._act_top.setChecked(self._is_topmost)
        self._act_mute.setChecked(self._sounds_muted)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._tray_show_main()

    def _tray_show_main(self):
        if self._compact_win and self._compact_win.isVisible():
            self._hide_compact()
            return
        if self._stack is not None and self._stack.currentIndex() != 0:
            self._stack.setCurrentIndex(0)
            if self._nav_btns and self._nav_group is not None:
                self._nav_group.blockSignals(True)
                self._nav_btns[0].setChecked(True)
                self._nav_group.blockSignals(False)
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _tray_toggle_compact(self):
        if self._compact_win and self._compact_win.isVisible():
            self._hide_compact()
        else:
            self._show_compact()

    def _tray_toggle_mute(self):
        self._sounds_muted = not self._sounds_muted
        self._persist_sounds_muted()

    def _apply_start_minimized_to_tray(self):
        if self._tray:
            self.hide()

    def _persist_sounds_muted(self):
        self.config = load_config()
        self.config.setdefault("gui", {})["sounds_muted"] = bool(self._sounds_muted)
        save_config(self.config)

    def _save_tray_gui_prefs(self):
        self.config = load_config()
        g = self.config.setdefault("gui", {})
        g["close_to_tray"] = bool(self._close_to_tray)
        g["minimize_to_tray"] = bool(self._minimize_to_tray)
        g["start_minimized_to_tray"] = bool(self._start_minimized_to_tray)
        g["start_with_windows"] = bool(self._start_with_windows)
        save_config(self.config)

    def _copy_dashboard_total_to_clipboard(self):
        try:
            s = self._filter_stats_for_dashboard(get_dashboard_stats())
            total = float(s.get("total_amount") or 0)
            text = format_money_jpy_as_display(float(total), self.config)
        except Exception:
            text = ""
        QGuiApplication.clipboard().setText(text)

    def _quit_fully(self):
        if self._tray:
            self._tray.hide()
            self._tray = None
        if self._compact_win:
            self._compact_win.close()
            self._compact_win = None
        QApplication.quit()

    def _restart_application(self):
        cwd = str(project_root())
        script = project_root() / "run_gui.py"
        if getattr(sys, "frozen", False):
            args = [sys.executable]
        else:
            args = [sys.executable, str(script), *sys.argv[1:]]
        popen_kw: dict = {"cwd": cwd, "close_fds": False}
        if sys.platform == "win32" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            popen_kw["creationflags"] = subprocess.CREATE_NO_WINDOW
        subprocess.Popen(args, **popen_kw)
        self._quit_fully()
        import os

        os._exit(0)

    def closeEvent(self, event: QCloseEvent):
        if self._close_to_tray and self._tray:
            event.ignore()
            self.hide()
            return
        event.accept()
        self._quit_fully()

    def changeEvent(self, event: QEvent):
        if event.type() == QEvent.Type.WindowStateChange and self._minimize_to_tray and self._tray:
            if self.isMinimized():
                QTimer.singleShot(0, self.hide)
        super().changeEvent(event)

    # --- header / pages ---
    def _build_ui(self):
        central = QWidget()
        central.setObjectName("centralRoot")
        central.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        central.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("appHeader")
        header.setFixedHeight(58)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(24, 0, 20, 0)
        title_block = QVBoxLayout()
        title_block.setSpacing(2)
        title_block.setContentsMargins(0, 8, 0, 8)
        self._w_app_title = QLabel(tr("app.title"))
        self._w_app_title.setObjectName("appTitle")
        self._w_app_subtitle = QLabel(tr("app.subtitle"))
        self._w_app_subtitle.setObjectName("appSubtitle")
        t1, t2 = self._w_app_title, self._w_app_subtitle
        title_block.addWidget(t1)
        title_block.addWidget(t2)
        hl.addLayout(title_block)
        hl.addStretch(1)
        fx_wrap = QFrame()
        fx_wrap.setObjectName("headerFxBlock")
        fx_wrap.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        fxl = QHBoxLayout(fx_wrap)
        fxl.setContentsMargins(10, 5, 10, 5)
        fxl.setSpacing(12)
        self._lbl_fx_twd_jpy = QLabel("")
        self._lbl_fx_usd_jpy = QLabel("")
        self._lbl_fx_usd_twd = QLabel("")
        for _fxlb in (self._lbl_fx_twd_jpy, self._lbl_fx_usd_jpy, self._lbl_fx_usd_twd):
            _fxlb.setObjectName("headerFxRate")
        fxl.addWidget(self._lbl_fx_twd_jpy, 0, Qt.AlignmentFlag.AlignVCenter)
        fxl.addWidget(self._lbl_fx_usd_jpy, 0, Qt.AlignmentFlag.AlignVCenter)
        fxl.addWidget(self._lbl_fx_usd_twd, 0, Qt.AlignmentFlag.AlignVCenter)
        hl.addWidget(fx_wrap, 0, Qt.AlignmentFlag.AlignVCenter)
        hl.addSpacing(10)
        nav_bar = QFrame()
        nav_bar.setObjectName("navTabBar")
        nav_bar.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        nav_l = QHBoxLayout(nav_bar)
        nav_l.setContentsMargins(4, 4, 4, 4)
        nav_l.setSpacing(2)
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        self._nav_btns = []
        for nid, tkey, ico in (
            (0, "nav.tab.overview", nav_overview_icon()),
            (1, "nav.tab.settings", nav_settings_icon()),
            (2, "nav.tab.account", nav_account_icon()),
        ):
            b = QPushButton(tr(tkey))
            b.setIcon(ico)
            b.setIconSize(QSize(18, 18))
            b.setObjectName("navTab")
            b.setCheckable(True)
            self._nav_group.addButton(b, nid)
            nav_l.addWidget(b)
            self._nav_btns.append(b)
        self._nav_group.idClicked.connect(self._on_main_nav)
        hl.addWidget(nav_bar, 0, Qt.AlignmentFlag.AlignVCenter)
        hl.addSpacing(12)
        self._btn_header_mini = QPushButton(tr("header.mini"))
        self._btn_header_mini.setObjectName("headerMiniPill")
        self._btn_header_mini.setIcon(mini_dashboard_icon_on_accent(size=24))
        self._btn_header_mini.setIconSize(QSize(24, 24))
        self._btn_header_mini.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self._btn_header_mini.setToolTip(tr("header.mini"))
        self._btn_header_mini.clicked.connect(self._show_compact)
        hl.addWidget(self._btn_header_mini, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addWidget(header)
        self._nav_btns[0].setChecked(True)

        self._stack = QStackedWidget()
        self._stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        page_dash = QWidget()
        page_dash.setObjectName("pageDash")
        page_dash.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        page_dash.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        bl = QVBoxLayout(page_dash)
        bl.setContentsMargins(20, 14, 20, 16)
        bl.setSpacing(12)
        hdr = QHBoxLayout()
        hdr.setSpacing(16)
        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        self._w_dash_headline = QLabel(tr("dash.overview"))
        self._w_dash_headline.setObjectName("pageHeadline")
        dash_title = self._w_dash_headline
        title_col.addWidget(dash_title)
        hdr.addLayout(title_col, 1)
        self._last_update_lbl = QLabel("")
        self._last_update_lbl.setFont(_qf(13))
        self._last_update_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        self._last_update_lbl.setStyleSheet(
            f"color: {PALETTE['text_secondary']}; padding-bottom: 4px;"
        )
        hdr.addWidget(self._last_update_lbl, 0, Qt.AlignmentFlag.AlignBottom)
        bl.addLayout(hdr)

        self._dash_hero = QWidget()
        self._dash_hero.setMinimumHeight(92)
        self._dash_hero_grid = QGridLayout(self._dash_hero)
        self._dash_hero_grid.setSpacing(10)
        for _ci in range(4):
            self._dash_hero_grid.setColumnStretch(_ci, 1)
        bl.addWidget(self._dash_hero)

        plat_hdr = QVBoxLayout()
        plat_hdr.setSpacing(0)
        self._w_plat_section = QLabel(tr("dash.platforms"))
        self._w_plat_section.setObjectName("platSectionLabel")
        plat_title = self._w_plat_section
        plat_hdr.addWidget(plat_title)
        bl.addLayout(plat_hdr)
        self._dash_platforms = QWidget()
        self._dash_platforms.setMinimumHeight(102)
        self._dash_plat_grid = QGridLayout(self._dash_platforms)
        self._dash_plat_grid.setSpacing(10)
        bl.addWidget(self._dash_platforms)

        self._build_trend_section(bl, page_dash)

        bl.addStretch(1)

        page_prefs, inner_p, lp, rp = self._make_settings_scroll_page("pagePrefs")
        self._build_prefs_scroll_content(lp, rp, inner_p)
        page_account, inner_a, la, ra = self._make_settings_scroll_page("pageAccount")
        self._build_account_scroll_content(la, ra, inner_a)

        self._stack.addWidget(page_dash)
        self._stack.addWidget(page_prefs)
        self._stack.addWidget(page_account)
        root.addWidget(self._stack, 1)

        self._init_dashboard_layout()
        self._bootstrap_dashboard_sync()
        self._refresh_dashboard()
        self._stack.setCurrentIndex(0)

    def _make_settings_scroll_page(
        self, object_name: str
    ) -> tuple[QWidget, QWidget, QVBoxLayout, QVBoxLayout]:
        page = QWidget()
        page.setObjectName(object_name)
        page.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        page.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        psl = QVBoxLayout(page)
        psl.setContentsMargins(16, 10, 16, 10)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        scroll.setMinimumSize(320, 200)
        content = QWidget()
        content.setObjectName("scrollContent")
        content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        content.setMinimumSize(0, 0)
        content.setMinimumWidth(640)
        sl = QVBoxLayout(content)
        sl.setSpacing(6)
        sl.setContentsMargins(0, 0, 0, 8)
        settings_row = QHBoxLayout()
        settings_row.setSpacing(14)
        left_col = QVBoxLayout()
        right_col = QVBoxLayout()
        left_col.setSpacing(6)
        right_col.setSpacing(6)
        settings_row.addLayout(left_col, 1)
        settings_row.addLayout(right_col, 1)
        sl.addLayout(settings_row, 1)
        scroll.setWidget(content)
        psl.addWidget(scroll, 1)
        return page, content, left_col, right_col

    def _on_main_nav(self, page_id: int) -> None:
        if self._stack is None:
            return
        self._stack.setCurrentIndex(int(page_id))

    def _on_pin_switch_toggled(self, on: bool) -> None:
        self._is_topmost = bool(on)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self._is_topmost)
        self.show()
        if hasattr(self, "_act_top") and self._act_top is not None:
            with QSignalBlocker(self._act_top):
                self._act_top.setChecked(self._is_topmost)

    def _refresh_header_fx_labels(self) -> None:
        if not hasattr(self, "_lbl_fx_twd_jpy"):
            return
        self.config = load_config()
        fx = fx_dict_from_config(self.config)
        self._lbl_fx_twd_jpy.setText(f"{tr('header.fx.twd_jpy')} {fx['twd_jpy']:.4f}")
        self._lbl_fx_usd_jpy.setText(f"{tr('header.fx.usd_jpy')} {fx['usd_jpy']:.2f}")
        self._lbl_fx_usd_twd.setText(f"{tr('header.fx.usd_twd')} {fx['usd_twd']:.2f}")

    def _refresh_sched_summary_line(self) -> None:
        if not hasattr(self, "_sched_summary_lbl"):
            return
        try:
            s = self._filter_stats_for_dashboard(get_dashboard_stats())
            total = float(s.get("total_amount") or 0)
            patrons = int(s.get("total_patron_count") or 0)
            t = (self._last_update_time_jst or "").strip()
            if not t:
                self._sched_summary_lbl.setText(tr("settings.sched.summary_none"))
                return
            total_s = format_money_jpy_as_display(float(total), self.config)
            self._sched_summary_lbl.setText(
                tr("settings.sched.summary", t=t, total=total_s, patrons=patrons)
            )
        except Exception:
            self._sched_summary_lbl.setText(tr("settings.sched.summary_none"))

    def _toggle_topmost(self):
        self._on_pin_switch_toggled(not self._is_topmost)

    def _show_compact(self):
        if self._compact_win and self._compact_win.isVisible():
            self._compact_win.raise_()
            return
        self.hide()
        self._compact_win = CompactFloatWindow(self)
        self._compact_win.show()

    def _hide_compact(self):
        w = self._compact_win
        self._compact_win = None
        if w is not None:
            w.hide()
            w.deleteLater()
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _refresh_platform_login_labels(self) -> None:
        for key in ("patreon", "fanbox", "fantia"):
            if not hasattr(self, f"{key}_status"):
                continue
            st = getattr(self, f"{key}_status")
            cfg = self.config.get(key, {})
            if key in ("patreon", "fanbox"):
                logged = bool(
                    (cfg.get("cookies") or "").strip() and "xxx" not in (cfg.get("cookies") or "")
                )
            else:
                _sid = (cfg.get("session_id") or "").strip()
                logged = bool(_sid) and "\u4f60\u7684" not in _sid and not _sid.lower().startswith(
                    "your "
                )
            st.setText(tr("settings.account.in") if logged else tr("settings.account.out"))
            st.setStyleSheet(
                f"color: {PALETTE['success'] if logged else PALETTE['text_tertiary']};"
            )

    def _on_ui_language_changed(self, _idx: int = 0) -> None:
        combo = getattr(self, "_ui_lang_combo", None)
        if combo is None:
            return
        raw = combo.currentData()
        if raw is None:
            return
        self.config = load_config()
        self.config.setdefault("gui", {})["ui_language"] = str(raw)
        save_config(self.config)
        set_language(effective_ui_language(self.config))
        self._apply_full_retranslate()

    def _on_display_currency_changed(self, _idx: int = 0) -> None:
        combo = getattr(self, "_display_currency_combo", None)
        if combo is None:
            return
        raw = combo.currentData()
        if raw is None:
            return
        code = str(raw).strip().lower()
        if code not in ("jpy", "twd", "usd"):
            return
        self.config = load_config()
        self.config.setdefault("gui", {})["display_currency"] = code
        save_config(self.config)
        try:
            s = self._filter_stats_for_dashboard(get_dashboard_stats())
            p = get_total_vs_days_ago(7)
        except Exception:
            s, p = None, None
        if s is not None:
            self._paint_dashboard_view(s, p)
        try:
            self._refresh_trend_chart()
        except Exception:
            pass
        self._refresh_sched_summary_line()
        self._refresh_header_fx_labels()
        cw = self._compact_win
        if cw is not None and cw.isVisible():
            cw.refresh()

    def _rebuild_sched_interval_combo(self, select_sid: str | None = None) -> None:
        if not hasattr(self, "_sched_interval"):
            return
        sid0 = normalize_schedule_interval_id(select_sid) if select_sid else self._sched_interval_sid()
        with QSignalBlocker(self._sched_interval):
            self._sched_interval.clear()
            for sid in ("15m", "30m", "1h", "2h", "4h"):
                self._sched_interval.addItem(schedule_interval_label(sid), sid)
            for i in range(self._sched_interval.count()):
                if self._sched_interval.itemData(i) == sid0:
                    self._sched_interval.setCurrentIndex(i)
                    break

    def _sched_interval_sid(self) -> str:
        sid = self._sched_interval.currentData() if hasattr(self, "_sched_interval") else None
        if isinstance(sid, str) and sid in SCHEDULE_INTERVAL_MINUTES:
            return sid
        return normalize_schedule_interval_id(str(sid) if sid else "1h")

    def _rebuild_sound_preset_combo(self, select_key: str | None = None) -> None:
        if not hasattr(self, "_increase_sound_preset"):
            return
        if select_key is not None:
            key0 = normalize_increase_sound_key(select_key)
        else:
            cur = self._increase_sound_preset.currentData()
            if isinstance(cur, str) and cur in INCREASE_SOUND_KEYS:
                key0 = cur
            else:
                key0 = normalize_increase_sound_key((load_config().get("gui") or {}).get("increase_sound"))
        with QSignalBlocker(self._increase_sound_preset):
            self._increase_sound_preset.clear()
            for k in INCREASE_SOUND_KEYS:
                self._increase_sound_preset.addItem(increase_sound_label(k), k)
            for i in range(self._increase_sound_preset.count()):
                if self._increase_sound_preset.itemData(i) == key0:
                    self._increase_sound_preset.setCurrentIndex(i)
                    break

    def _refresh_schedule_button_and_status(self) -> None:
        if not hasattr(self, "_sched_btn"):
            return
        if self._schedule_running:
            self._sched_btn.setText(tr("settings.sched.stop"))
            self._sched_btn.setObjectName("danger")
            self._sched_btn.setStyleSheet(
                f"background-color: {PALETTE['error']}; color: #ffffff; border: none; "
                f"border-radius: 8px; font-weight: 600;"
            )
            sid = self._sched_interval_sid()
            self.update_status.setText(
                tr("settings.sched.running", interval=schedule_interval_label(sid))
            )
            self.update_status.setStyleSheet(f"color: {PALETTE['success']};")
        else:
            self._sched_btn.setText(tr("settings.sched.start"))
            self._sched_btn.setObjectName("success")
            self._sched_btn.setStyleSheet(
                f"background-color: {PALETTE['success']}; color: #ffffff; border: none; "
                f"border-radius: 8px; font-weight: 600;"
            )
            self.update_status.setText(tr("settings.sched.stopped"))
            self.update_status.setStyleSheet(f"color: {PALETTE['text_tertiary']};")
        self._refresh_sched_summary_line()

    def _apply_full_retranslate(self) -> None:
        self.setWindowTitle(tr("app.title"))
        if self._w_app_title:
            self._w_app_title.setText(tr("app.title"))
        if self._w_app_subtitle:
            self._w_app_subtitle.setText(tr("app.subtitle"))
        if hasattr(self, "_btn_header_mini"):
            self._btn_header_mini.setText(tr("header.mini"))
            self._btn_header_mini.setToolTip(tr("header.mini"))
            self._btn_header_mini.setIcon(mini_dashboard_icon_on_accent(size=24))
        if self._nav_btns:
            _nav_keys = ("nav.tab.overview", "nav.tab.settings", "nav.tab.account")
            _icons = (nav_overview_icon(), nav_settings_icon(), nav_account_icon())
            for b, nk, ico in zip(self._nav_btns, _nav_keys, _icons):
                b.setText(tr(nk))
                b.setIcon(ico)
        if hasattr(self, "_fetch_hint_lbl"):
            self._fetch_hint_lbl.setText(tr("settings.fetch.hint"))
        if self._w_dash_headline:
            self._w_dash_headline.setText(tr("dash.overview"))
        if self._w_plat_section:
            self._w_plat_section.setText(tr("dash.platforms"))
        if hasattr(self, "_w_trend_title") and self._w_trend_title:
            self._w_trend_title.setText(tr("dash.trend"))
        if hasattr(self, "_trend_range_combo"):
            sel = self._trend_range_combo.currentData()
            with QSignalBlocker(self._trend_range_combo):
                self._trend_range_combo.clear()
                self._trend_range_combo.addItem(tr("dash.month"), "30d")
                self._trend_range_combo.addItem(tr("dash.year"), "12m")
                for i in range(self._trend_range_combo.count()):
                    if self._trend_range_combo.itemData(i) == sel:
                        self._trend_range_combo.setCurrentIndex(i)
                        break
        if hasattr(self, "_plat_empty_lbl"):
            self._plat_empty_lbl.setText(tr("dash.empty"))
        if self._tray:
            self._tray.setToolTip(tr("tray.tip"))
            self._tray_act_show.setText(tr("tray.show"))
            self._act_compact.setText(tr("tray.compact"))
            self._act_top.setText(tr("tray.main_top"))
            self._act_mute.setText(tr("tray.mute"))
            self._tray_act_up.setText(tr("tray.update"))
            self._tray_act_copy.setText(tr("tray.copy"))
            self._tray_act_restart.setText(tr("tray.restart"))
            self._tray_act_quit.setText(tr("tray.quit"))
        cw = self._compact_win
        if cw is not None:
            cw.setWindowTitle(tr("app.title_compact"))
            cw.setToolTip(tr("compact.tooltip"))
            if hasattr(cw, "_btn_compact_open_main"):
                cw._btn_compact_open_main.setToolTip(tr("compact.open_main"))
            if hasattr(cw, "_btn_compact_pin"):
                cw._btn_compact_pin.setToolTip(tr("header.pin"))
            cw.refresh()
        for lbl, key in self._settings_i18n_headings:
            lbl.setText(tr(key))
        for lbl, key in self._settings_i18n_blurbs:
            lbl.setText(tr(key))
        if hasattr(self, "_plat_hint_label"):
            self._plat_hint_label.setText(tr("settings.platform.hint"))
        if hasattr(self, "_lbl_sched_interval"):
            self._lbl_sched_interval.setText(tr("settings.sched.interval"))
        if hasattr(self, "_lbl_sound_system"):
            self._lbl_sound_system.setText(tr("settings.sound.system"))
        if hasattr(self, "_lbl_sound_volume"):
            self._lbl_sound_volume.setText(tr("settings.sound.volume"))
        if hasattr(self, "_lbl_sound_wav"):
            self._lbl_sound_wav.setText(tr("settings.sound.wav"))
        if hasattr(self, "_lbl_discord_time"):
            self._lbl_discord_time.setText(tr("settings.discord.time"))
        if hasattr(self, "_lbl_playwright_miss"):
            self._lbl_playwright_miss.setText(tr("settings.playwright.missing"))
        self._rebuild_sched_interval_combo()
        self._rebuild_sound_preset_combo()
        if hasattr(self, "_ui_lang_combo"):
            pairs = (
                ("auto", "lang.auto"),
                (LANG_ZH_TW, "lang.zh_TW"),
                (LANG_EN, "lang.en"),
                (LANG_JA, "lang.ja"),
            )
            with QSignalBlocker(self._ui_lang_combo):
                for i, (_val, lk) in enumerate(pairs):
                    if i < self._ui_lang_combo.count():
                        self._ui_lang_combo.setItemText(i, tr(lk))
        if hasattr(self, "_display_currency_combo"):
            _cur_sel = self._display_currency_combo.currentData()
            pairs_dc = (
                ("jpy", "settings.currency.jpy"),
                ("twd", "settings.currency.twd"),
                ("usd", "settings.currency.usd"),
            )
            with QSignalBlocker(self._display_currency_combo):
                for i, (_code, lk) in enumerate(pairs_dc):
                    if i < self._display_currency_combo.count():
                        self._display_currency_combo.setItemText(i, tr(lk))
                for i in range(self._display_currency_combo.count()):
                    if self._display_currency_combo.itemData(i) == _cur_sel:
                        self._display_currency_combo.setCurrentIndex(i)
                        break
        if hasattr(self, "update_btn"):
            self.update_btn.setText(tr("settings.fetch"))
        self._refresh_schedule_button_and_status()
        if hasattr(self, "_app_version_label"):
            self._app_version_label.setText(tr("settings.version.current", v=current_app_version()))
        if hasattr(self, "_app_update_btn"):
            self._app_update_btn.setText(tr("settings.update.check"))
        if hasattr(self, "_app_oneclick_btn"):
            self._app_oneclick_btn.setText(tr("settings.update.oneclick"))
            if not lazy_update_supported():
                self._app_oneclick_btn.setToolTip(tr("settings.update.oneclick_tip"))
        if hasattr(self, "_btn_github_repo"):
            self._btn_github_repo.setText(tr("settings.version.github"))
            _repo = (configured_github_repo() or "").strip()
            _ok_repo = bool(_repo) and _repo.count("/") == 1
            self._btn_github_repo.setEnabled(_ok_repo)
            self._btn_github_repo.setToolTip(
                "" if _ok_repo else tr("settings.version.github_tip")
            )
        if hasattr(self, "_btn_export_csv"):
            self._btn_export_csv.setText(tr("settings.export.btn"))
        for key in ("patreon", "fanbox", "fantia"):
            if hasattr(self, f"{key}_btn"):
                getattr(self, f"{key}_btn").setText(tr("settings.login"))
            if hasattr(self, f"{key}_done_btn"):
                getattr(self, f"{key}_done_btn").setText(tr("settings.done"))
            if hasattr(self, f"{key}_logout_btn"):
                getattr(self, f"{key}_logout_btn").setText(tr("settings.logout"))
        if hasattr(self, "_btn_sound_test"):
            self._btn_sound_test.setText(tr("settings.sound.test"))
        if hasattr(self, "_btn_discord_test"):
            self._btn_discord_test.setText(tr("settings.discord.test"))
        if hasattr(self, "_btn_discord_report_test"):
            self._btn_discord_report_test.setText(tr("settings.discord.test_report"))
        if hasattr(self, "_sw_daily_report"):
            self._sw_daily_report.setText(tr("settings.discord.daily"))
        if hasattr(self, "_sw_close_tray"):
            self._sw_close_tray.setText(tr("settings.tray.close"))
        if hasattr(self, "_sw_min_tray"):
            self._sw_min_tray.setText(tr("settings.tray.min"))
        if hasattr(self, "_sw_start_tray"):
            self._sw_start_tray.setText(tr("settings.tray.start"))
        if hasattr(self, "_sw_autostart"):
            self._sw_autostart.setText(tr("settings.tray.autostart"))
            if sys.platform != "win32":
                self._sw_autostart.setToolTip(tr("settings.tray.autostart_tip"))
        if hasattr(self, "_purge_btn"):
            self._purge_btn.setText(tr("settings.purge.btn"))
        if self._last_update_time_jst:
            self._last_update_lbl.setText(tr("dash.updated", t=self._last_update_time_jst))
        self._refresh_platform_login_labels()
        self._refresh_dashboard()
        for _pk in _PLATFORM_ORDER:
            _attr = f"_sw_plat_vis_{_pk}"
            if hasattr(self, _attr):
                getattr(self, _attr).setText(tr("settings.platform.show_overview"))

    def _platform_visibility(self) -> dict[str, bool]:
        gui = (self.config or {}).get("gui") or {}
        raw = gui.get("show_platforms") or {}
        return {k: True if raw.get(k) is None else bool(raw.get(k)) for k in _PLATFORM_ORDER}

    def _filter_stats_for_dashboard(self, s: dict) -> dict:
        vis = self._platform_visibility()
        by_in = {str(p.get("platform")): p for p in (s.get("by_platform") or [])}
        rate = float(s.get("fx_usd_jpy") or 150)
        filtered: list[dict] = []
        total_amt = 0.0
        total_pat = 0
        for key in _PLATFORM_ORDER:
            if not vis.get(key, True):
                continue
            p = by_in.get(key)
            if p is None:
                filtered.append(
                    {
                        "platform": key,
                        "amount": 0.0,
                        "patron_count": 0,
                        "change_amount": None,
                        "change_percent": None,
                        "currency": "JPY",
                        "last_updated": None,
                    }
                )
            else:
                filtered.append(dict(p))
                amt = float(p.get("amount") or 0)
                cur = (p.get("currency") or "JPY").upper()
                if key == "patreon" and cur == "USD":
                    amt *= rate
                total_amt += amt
                total_pat += int(p.get("patron_count") or 0)
        out = dict(s)
        out["by_platform"] = filtered
        out["total_amount"] = total_amt
        out["total_patron_count"] = total_pat
        return out

    def _on_platform_visibility_toggled(self, key: str, on: bool) -> None:
        self.config = load_config()
        self.config.setdefault("gui", {}).setdefault("show_platforms", {})
        self.config["gui"]["show_platforms"][key] = bool(on)
        save_config(self.config)
        self._refresh_dashboard()
        self._refresh_sched_summary_line()
        if self._compact_win is not None and self._compact_win.isVisible():
            self._compact_win.refresh()

    # --- dashboard ---
    def _init_dashboard_layout(self):
        self._hero_cells: list[dict] = []
        for col in range(4):
            oname = "dashHeroPrimary" if col == 0 else "card"
            card = _make_card(self._dash_hero, oname)
            lay = QVBoxLayout(card)
            lay.setContentsMargins(14, 12, 14, 12)
            lay.setSpacing(4)
            t_lbl = QLabel("")
            t_lbl.setFont(_qf(12, weight=QFont.Weight.DemiBold))
            t_lbl.setStyleSheet(f"color: {PALETTE['text_secondary']} !important; letter-spacing: 0.5px;")
            v_lbl = QLabel("--")
            if col == 0:
                v_sz = 26
            elif col == 1:
                v_sz = 20
            else:
                v_sz = 17
            v_lbl.setFont(_qf(v_sz, True))
            v_lbl.setStyleSheet(f"color: {PALETTE['text']} !important;")
            v_lbl.setWordWrap(False)
            s_lbl = QLabel("")
            s_lbl.setFont(_qf(12))
            s_lbl.setStyleSheet(f"color: {PALETTE['text_secondary']} !important;")
            s_lbl.setWordWrap(True)
            lay.addWidget(t_lbl)
            lay.addWidget(v_lbl)
            lay.addWidget(s_lbl)
            self._dash_hero_grid.addWidget(card, 0, col)
            self._hero_cells.append({"title": t_lbl, "value": v_lbl, "sub": s_lbl})

        self._plat_empty = _make_card(self._dash_platforms, "platTile")
        pel = QVBoxLayout(self._plat_empty)
        self._plat_empty_lbl = QLabel(tr("dash.empty"))
        self._plat_empty_lbl.setFont(_qf(16))
        self._plat_empty_lbl.setStyleSheet(f"color: {PALETTE['text_tertiary']} !important;")
        self._plat_empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pel.addWidget(self._plat_empty_lbl)

        pnames = {"patreon": "Patreon", "fanbox": "Fanbox", "fantia": "Fantia"}
        pcolors = {"patreon": PALETTE["patreon"], "fanbox": PALETTE["fanbox"], "fantia": PALETTE["fantia"]}
        self._plat_meta = (pnames, pcolors)
        self._plat_cells_main: list[dict] = []
        for _i in range(3):
            card = _make_card(self._dash_platforms, "platTile")
            outer = QVBoxLayout(card)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.setSpacing(0)
            accent_bar = QFrame()
            accent_bar.setFixedHeight(3)
            accent_bar.setStyleSheet("background-color: transparent; border: none;")
            body = QWidget()
            lay = QVBoxLayout(body)
            lay.setContentsMargins(14, 8, 14, 10)
            lay.setSpacing(5)
            row_top = QHBoxLayout()
            dot = QLabel("")
            dot.setFont(_qf(14))
            name = QLabel("")
            name.setFont(_qf(15, True))
            name.setStyleSheet(f"color: {PALETTE['text']} !important;")
            row_top.addWidget(dot)
            row_top.addWidget(name)
            row_top.addStretch()
            lay.addLayout(row_top)
            amt = QLabel("--")
            amt.setFont(_qf(16, True))
            amt.setStyleSheet(f"color: {PALETTE['text']} !important;")
            lay.addWidget(amt)
            detail = QHBoxLayout()
            detail.setSpacing(10)
            patron = QLabel("")
            patron.setFont(_qf(13))
            patron.setStyleSheet(f"color: {PALETTE['text']} !important;")
            patron.setWordWrap(False)
            chg = QLabel("")
            chg.setFont(_qf(12, weight=QFont.Weight.DemiBold))
            chg.setWordWrap(False)
            chg.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            detail.addWidget(patron, 0)
            detail.addWidget(chg, 0)
            detail.addStretch(1)
            lay.addLayout(detail)
            time_lbl = QLabel("")
            time_lbl.setFont(_qf(12))
            time_lbl.setStyleSheet(f"color: {PALETTE['text_tertiary']} !important;")
            lay.addWidget(time_lbl)
            outer.addWidget(accent_bar)
            outer.addWidget(body)
            self._plat_cells_main.append(
                {
                    "card": card,
                    "accent_bar": accent_bar,
                    "dot": dot,
                    "name": name,
                    "amount": amt,
                    "patron": patron,
                    "chg": chg,
                    "time": time_lbl,
                }
            )

        self._dash_plat_grid.addWidget(self._plat_empty, 0, 0)

    def _build_trend_section(self, parent_layout: QVBoxLayout, page: QWidget) -> None:
        self._w_trend_title = QLabel(tr("dash.trend"))
        self._w_trend_title.setObjectName("platSectionLabel")
        trend_title = self._w_trend_title
        hdr = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        title_col.addWidget(trend_title)
        hdr.addLayout(title_col, 1)
        self._trend_range_combo = QComboBox()
        self._trend_range_combo.addItem(tr("dash.month"), "30d")
        self._trend_range_combo.addItem(tr("dash.year"), "12m")
        self._trend_range_combo.currentIndexChanged.connect(lambda _i: self._refresh_trend_chart())
        hdr.addWidget(self._trend_range_combo, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        parent_layout.addLayout(hdr)

        card = _make_card(page, "card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(6, 4, 6, 6)
        cl.setSpacing(0)
        self._trend_chart = QChart()
        self._trend_chart.legend().hide()
        self._trend_chart.setBackgroundRoundness(12)
        cv = QChartView(self._trend_chart)
        self._trend_chart_view = cv
        cv.setFrameShape(QFrame.Shape.NoFrame)
        cv.setLineWidth(0)
        cv.setMidLineWidth(0)
        cv.setRenderHint(QPainter.RenderHint.Antialiasing)
        cv.setMinimumHeight(232)
        cv.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        cl.addWidget(cv)
        parent_layout.addWidget(card)

    def _refresh_trend_chart(self) -> None:
        chart = getattr(self, "_trend_chart", None)
        if chart is None:
            return
        chart.setTheme(QChart.ChartTheme.ChartThemeDark)
        combo = getattr(self, "_trend_range_combo", None)
        mode = combo.currentData() if combo is not None else "30d"
        if mode not in ("30d", "12m", "month", "year"):
            mode = "30d"
        if mode in ("month",):
            mode = "30d"
        if mode in ("year",):
            mode = "12m"
        end = today_jst_str()
        try:
            if mode == "30d":
                start = date_days_ago_jst(29)
                data = get_chart_combined_daily_between(start, end)
            else:
                data = get_chart_combined_monthly_peaks_last12()
        except Exception:
            data = []
        for s in list(chart.series()):
            chart.removeSeries(s)
        for ax in list(chart.axes()):
            chart.removeAxis(ax)
        self.config = load_config()
        _dcc = display_currency_code(self.config)
        _fx = fx_dict_from_config(self.config)
        series = QLineSeries()
        if mode == "30d":
            for date_str, amt, _ in data:
                dt = QDateTime.fromString(f"{date_str} 12:00:00", "yyyy-MM-dd HH:mm:ss")
                if not dt.isValid():
                    continue
                yv = jpy_to_display_amount(float(amt), _dcc, _fx)
                series.append(float(dt.toMSecsSinceEpoch()), float(yv))
        else:
            for date_str, amt in data:
                dt = QDateTime.fromString(f"{date_str} 12:00:00", "yyyy-MM-dd HH:mm:ss")
                if not dt.isValid():
                    continue
                yv = jpy_to_display_amount(float(amt), _dcc, _fx)
                series.append(float(dt.toMSecsSinceEpoch()), float(yv))
        pen = QPen(QColor(PALETTE["accent"]))
        pen.setWidthF(2.5)
        series.setPen(pen)
        chart.addSeries(series)
        axis_x = QDateTimeAxis()
        axis_x.setFormat("M/d" if mode == "30d" else "MMM")
        axis_x.setLabelsColor(QColor(PALETTE["text_secondary"]))
        axis_x.setGridLineColor(QColor(PALETTE["hairline"]))
        if data:
            if mode == "30d":
                d0 = QDateTime.fromString(f"{data[0][0]} 12:00:00", "yyyy-MM-dd HH:mm:ss")
                d1 = QDateTime.fromString(f"{data[-1][0]} 12:00:00", "yyyy-MM-dd HH:mm:ss")
            else:
                d0 = QDateTime.fromString(f"{data[0][0]} 12:00:00", "yyyy-MM-dd HH:mm:ss")
                d1 = QDateTime.fromString(f"{data[-1][0]} 12:00:00", "yyyy-MM-dd HH:mm:ss")
            if d0.isValid() and d1.isValid():
                axis_x.setRange(d0, d1)
        axis_y = QValueAxis()
        axis_y.setLabelsColor(QColor(PALETTE["text_secondary"]))
        axis_y.setGridLineColor(QColor(PALETTE["hairline"]))
        if _dcc == "usd":
            axis_y.setLabelFormat("%.2f")
        else:
            axis_y.setLabelFormat("%.0f")
        if data:
            ys = [jpy_to_display_amount(float(row[1]), _dcc, _fx) for row in data]
            lo, hi = min(ys), max(ys)
            span = max(hi - lo, abs(hi) * 0.02 if hi else 0.0, 1e-9)
            pad = max(span * 0.12, 1e-9)
            mag = max(abs(lo), abs(hi), abs(hi - lo))
            if _dcc != "usd" and mag >= 1000:
                y_lo = math.floor((lo - pad) / 1000) * 1000
                y_hi = math.ceil((hi + pad) / 1000) * 1000
                if y_hi <= y_lo:
                    y_hi = y_lo + 1000
                axis_y.setRange(y_lo, y_hi)
                step = max(1000, int((y_hi - y_lo) / 4 // 1000) * 1000) or 1000
                axis_y.setTickType(QValueAxis.TickType.TicksDynamic)
                axis_y.setTickInterval(float(step))
                axis_y.setTickAnchor(float(y_lo))
            else:
                y_lo = lo - pad
                y_hi = hi + pad
                if y_lo == y_hi:
                    y_hi = y_lo + max(abs(y_lo) * 0.01, 0.01)
                axis_y.setRange(y_lo, y_hi)
        else:
            axis_y.setRange(0, 1)
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_x)
        series.attachAxis(axis_y)
        chart.setBackgroundBrush(QBrush(QColor(PALETTE["bg_card"])))
        chart.setPlotAreaBackgroundVisible(True)
        chart.setPlotAreaBackgroundBrush(QBrush(QColor(PALETTE["bg_card"])))
        chart.setMargins(QMargins(8, 8, 8, 8))
        cv = getattr(self, "_trend_chart_view", None)
        if cv is not None:
            bgc = PALETTE["bg_card"]
            cv.setBackgroundBrush(QBrush(QColor(bgc)))
            cv.setStyleSheet(f"QChartView {{ background-color: {bgc}; border: none; }}")
        if hasattr(axis_x, "setTickCount"):
            if mode == "30d":
                n = len(data)
                axis_x.setTickCount(min(12, max(4, min(n, 12) or 4)))
            else:
                axis_x.setTickCount(12)

    def _bootstrap_dashboard_sync(self) -> None:
        try:
            s = get_dashboard_stats()
            p = get_total_vs_days_ago(7)
        except Exception:
            s = {
                "total_amount": 0.0,
                "total_patron_count": 0,
                "change_vs_yesterday": None,
                "change_pct_vs_yesterday": None,
                "increase_amount": 0.0,
                "decrease_amount": 0.0,
                "patron_change": None,
                "by_platform": [],
                "fx_usd_jpy": 150.0,
            }
            p = None
        try:
            self._paint_dashboard_view(s, p)
        except Exception:
            pass
        try:
            self._refresh_trend_chart()
        except Exception:
            pass

    def _refresh_dashboard(self):
        if self._dash_debounce is None:
            self._dash_debounce = QTimer(self)
            self._dash_debounce.setSingleShot(True)
            self._dash_debounce.timeout.connect(self._apply_dashboard_refresh)
        self._dash_debounce.stop()
        self._dash_debounce.start(50)

    def _apply_dashboard_refresh(self):
        self._dashboard_fetch_seq += 1
        seq = self._dashboard_fetch_seq
        pending_snap = self._pending_dashboard_stats

        def bg():
            try:
                if pending_snap is not None:
                    s = pending_snap
                else:
                    s = get_dashboard_stats()
                period = get_total_vs_days_ago(7)
                used = pending_snap is not None
                self._dashboard_data_ready.emit(seq, s, period, used, pending_snap)
            except Exception:
                self._dashboard_data_ready.emit(seq, None, None, False, None)

        threading.Thread(target=bg, daemon=True).start()

    def _apply_dashboard_ui_immediate(self, s: dict) -> None:
        """\u66f4\u65b0\u5b8c\u6210\u5f8c\u65bc\u4e3b\u57f7\u7dd2\u7acb\u5373\u91cd\u7e6e\u7e3d\u89bd\uff08\u907f\u514d\u80cc\u666f QTimer \u5931\u6548\u8207 seq \u7af6\u722d\uff09\u3002"""
        self._dashboard_fetch_seq += 1
        self._pending_dashboard_stats = None
        try:
            period = get_total_vs_days_ago(7)
        except Exception:
            period = None
        self._paint_dashboard_view(s, period)
        if self._compact_win and self._compact_win.isVisible():
            self._compact_win.refresh(s)
        try:
            self._refresh_trend_chart()
        except Exception:
            pass

    def _on_dashboard_data_ready(
        self,
        seq: int,
        s: dict | None,
        period: dict | None,
        used_pending: bool,
        pending_snap: object,
    ) -> None:
        """\u7531 Signal \u5f9e\u80cc\u666f\u57f7\u7dd2\u56de\u5230\u4e3b\u57f7\u7dd2\u61c9\u7528\u7e3d\u89bd\u3002"""
        if seq != self._dashboard_fetch_seq or s is None:
            return
        if used_pending and pending_snap is not None and self._pending_dashboard_stats is pending_snap:
            self._pending_dashboard_stats = None
        self._paint_dashboard_view(s, period)
        if self._compact_win and self._compact_win.isVisible():
            self._compact_win.refresh(s)
        try:
            self._refresh_trend_chart()
        except Exception:
            pass

    def _paint_dashboard_view(self, s: dict, period: dict | None):
        s = self._filter_stats_for_dashboard(s)
        pnames, pcolors = self._plat_meta
        h0 = self._hero_cells[0]
        h1 = self._hero_cells[1]
        h2 = self._hero_cells[2]
        h3 = self._hero_cells[3]
        total = s.get("total_amount") or 0
        ch = s.get("change_vs_yesterday")
        pct = s.get("change_pct_vs_yesterday")
        inc_this = getattr(self, "_last_update_increase", None) or 0
        sub_parts: list[str] = []
        if not total:
            sub_parts.append(tr("dash.sub.run_first"))
        if inc_this > 0:
            sub_parts.append(
                tr(
                    "dash.sub.this_update",
                    amt=format_money_jpy_as_display(float(inc_this), self.config, signed=True),
                )
            )
        sub_total = "\n".join(sub_parts)
        h0["title"].setText(tr("dash.hero.total"))
        h0["title"].setStyleSheet(
            f"color: {PALETTE['text_secondary']} !important; letter-spacing: 0.5px; font-weight: 600; font-size: 12px;"
        )
        h0["value"].setText(format_money_jpy_as_display(float(total), self.config))
        h0["value"].setStyleSheet(f"color: {PALETTE['text']} !important; letter-spacing: -0.5px;")
        h0["sub"].setText(sub_total)
        h0["sub"].setStyleSheet(f"color: {PALETTE['text_secondary']} !important;")

        patrons = s.get("total_patron_count") or 0
        pch = s.get("patron_change")
        h1["title"].setText(tr("dash.hero.patrons"))
        h1["title"].setStyleSheet(
            f"color: {PALETTE['text_secondary']} !important; letter-spacing: 0.5px; font-weight: 600; font-size: 12px;"
        )
        pp = tr("common.people")
        h1["value"].setText(f"{patrons} {pp}".strip() if pp else str(patrons))
        h1["value"].setStyleSheet(f"color: {PALETTE['text']} !important;")
        h1["sub"].setText(tr("dash.sub.vs_yday_p", n=pch) if pch is not None else "")
        h1["sub"].setStyleSheet(
            f"color: {PALETTE['success'] if (pch or 0) >= 0 else PALETTE['error']} !important;"
        )

        h2["title"].setText(tr("dash.hero.week"))
        h2["title"].setStyleSheet(
            f"color: {PALETTE['text_secondary']} !important; letter-spacing: 0.5px; font-weight: 600; font-size: 12px;"
        )
        if period:
            c2, pct2 = period["change_amount"], period["change_percent"]
            v2 = format_money_jpy_as_display(float(c2), self.config, signed=True) + (
                f" ({pct2:+.1f}%)" if pct2 is not None else ""
            )
            h2["value"].setText(v2)
            if (c2 or 0) > 0:
                c2_col = PALETTE["success"]
            elif (c2 or 0) < 0:
                c2_col = PALETTE["error"]
            else:
                c2_col = PALETTE["text_tertiary"]
            h2["value"].setStyleSheet(f"color: {c2_col} !important;")
            h2["sub"].setText(tr("dash.sub.vs_week_snapshot"))
        else:
            h2["value"].setText("\u2014")
            h2["value"].setStyleSheet(f"color: {PALETTE['text_tertiary']} !important;")
            h2["sub"].setText("")
        h2["sub"].setStyleSheet(f"color: {PALETTE['text_secondary']} !important;")

        h3["title"].setText(tr("dash.hero.yday_amt"))
        h3["title"].setStyleSheet(
            f"color: {PALETTE['text_secondary']} !important; letter-spacing: 0.5px; font-weight: 600; font-size: 12px;"
        )
        if ch is not None:
            pct_s = f" ({pct:+.1f}%)" if pct is not None else ""
            h3["value"].setText(
                format_money_jpy_as_display(float(ch), self.config, signed=True) + pct_s
            )
            if (ch or 0) > 0:
                ch_col = PALETTE["success"]
            elif (ch or 0) < 0:
                ch_col = PALETTE["error"]
            else:
                ch_col = PALETTE["text_tertiary"]
            h3["value"].setStyleSheet(f"color: {ch_col} !important;")
            h3["sub"].setText(tr("dash.sub.vs_yday_total"))
        else:
            h3["value"].setText("\u2014")
            h3["value"].setStyleSheet(f"color: {PALETTE['text_tertiary']} !important;")
            h3["sub"].setText("")
        h3["sub"].setStyleSheet(f"color: {PALETTE['text_secondary']} !important;")

        platforms = s.get("by_platform") or []
        nplat = len(platforms)
        for i in range(max(nplat, 1)):
            self._dash_plat_grid.setColumnStretch(i, 1)

        if not platforms:
            for cell in self._plat_cells_main:
                self._dash_plat_grid.removeWidget(cell["card"])
                cell["card"].hide()
            self._plat_empty_lbl.setStyleSheet(f"color: {PALETTE['text_tertiary']} !important;")
            self._plat_empty.show()
            if self._dash_plat_grid.indexOf(self._plat_empty) < 0:
                self._dash_plat_grid.addWidget(self._plat_empty, 0, 0)
        else:
            self._plat_empty.hide()
            self._dash_plat_grid.removeWidget(self._plat_empty)
            for i, cell in enumerate(self._plat_cells_main):
                if i < nplat:
                    p = platforms[i]
                    plat = p.get("platform") or ""
                    self._dash_plat_grid.addWidget(cell["card"], 0, i)
                    cell["card"].show()
                    color = pcolors.get(plat, PALETTE["accent"])
                    name = pnames.get(plat, plat)
                    cell["accent_bar"].setStyleSheet(
                        f"background-color: {color}; border: none; "
                        f"border-top-left-radius: 13px; border-top-right-radius: 13px;"
                    )
                    cell["dot"].setText("\u25cf")
                    cell["dot"].setStyleSheet(f"color: {color} !important;")
                    cell["name"].setText(name)
                    cell["name"].setStyleSheet(f"color: {PALETTE['text']} !important;")
                    amt = float(p.get("amount") or 0)
                    cur = (p.get("currency") or "JPY").strip()
                    uj = float(s.get("fx_usd_jpy") or 150)
                    jpy_amt = platform_native_to_jpy(amt, plat, cur, uj)
                    cell["amount"].setText(
                        format_money_jpy_as_display(jpy_amt, self.config)
                    )
                    cell["amount"].setStyleSheet(f"color: {PALETTE['text']} !important;")
                    pc = int(p.get("patron_count") or 0)
                    pp2 = tr("common.people")
                    cell["patron"].setText(f"{pc} {pp2}".strip() if pp2 else str(pc))
                    cell["patron"].setStyleSheet(f"color: {PALETTE['text']} !important;")
                    if p.get("change_amount") is not None:
                        c3 = p["change_amount"]
                        pct3 = p.get("change_percent")
                        tchg = f"{c3:+,.0f}" + (f" ({pct3:+.1f}%)" if pct3 is not None else "")
                        cell["chg"].setText(tchg)
                        cell["chg"].setStyleSheet(
                            f"color: {PALETTE['success'] if c3 >= 0 else PALETTE['error']} !important;"
                        )
                    else:
                        cell["chg"].setText("")
                        cell["chg"].setStyleSheet(f"color: {PALETTE['text_tertiary']} !important;")
                    lu = p.get("last_updated")
                    if lu:
                        cell["time"].setText(f"{str(lu)[:16]} JST")
                    else:
                        cell["time"].setText("")
                else:
                    self._dash_plat_grid.removeWidget(cell["card"])
                    cell["card"].hide()

    # --- schedule / update (continued in next part due to length) ---
    def _apply_schedule_preferences(self):
        self.config = load_config()
        gui = self.config.get("gui") or {}
        interval_id = normalize_schedule_interval_id(str(gui.get("schedule_interval") or "1h"))
        if hasattr(self, "_sched_interval"):
            self._rebuild_sched_interval_combo(interval_id)
        if gui.get("schedule_auto_start") and not self._schedule_running:
            self._start_schedule()

    def _save_schedule_preferences(self, running: bool):
        self.config = load_config()
        self.config.setdefault("gui", {})["schedule_interval"] = self._sched_interval_sid()
        self.config.setdefault("gui", {})["schedule_auto_start"] = running
        save_config(self.config)

    def _on_schedule_interval_changed(self, _idx: int = 0) -> None:
        if not hasattr(self, "_sched_interval"):
            return
        sid = self._sched_interval.currentData()
        if not isinstance(sid, str):
            return
        self.config = load_config()
        self.config.setdefault("gui", {})["schedule_interval"] = sid
        save_config(self.config)

    def _toggle_schedule(self):
        if self._schedule_running:
            self._stop_schedule()
        else:
            self._start_schedule()

    def _start_schedule(self):
        import schedule as sched_mod

        minutes = SCHEDULE_INTERVAL_MINUTES.get(self._sched_interval_sid(), 60)
        sched_mod.clear()
        sched_mod.every(minutes).minutes.do(lambda: self._run_update(True))
        self._schedule_running = True
        self._sched_interval.setEnabled(False)
        self._refresh_schedule_button_and_status()
        self._save_schedule_preferences(True)
        if self._sched_thread is None or not self._sched_thread.is_alive():

            def loop():
                while True:
                    sched_mod.run_pending()
                    idle = sched_mod.idle_seconds()
                    if idle is not None:
                        delay = min(max(float(idle), 0.5), 120.0)
                    else:
                        delay = 60.0
                    time.sleep(delay)

            self._sched_thread = threading.Thread(target=loop, daemon=True)
            self._sched_thread.start()

    def _stop_schedule(self):
        import schedule as sched_mod

        sched_mod.clear()
        self._schedule_running = False
        self._sched_interval.setEnabled(True)
        self._refresh_schedule_button_and_status()
        self._save_schedule_preferences(False)

    def _run_update(self, from_schedule: bool = False):
        self._pending_update_from_schedule = from_schedule
        try:
            s_before = get_dashboard_stats()
            self._total_before_update = s_before.get("total_amount") or 0
            self._platform_before_amounts = {
                (p.get("platform") or ""): float(p.get("amount") or 0)
                for p in (s_before.get("by_platform") or [])
                if p.get("platform")
            }
        except Exception:
            self._total_before_update = 0
            self._platform_before_amounts = {}
        self.update_btn.setEnabled(False)
        self.update_btn.setText(tr("settings.fetch.running"))
        if hasattr(self, "_fetch_hint_lbl"):
            self._fetch_hint_lbl.setVisible(True)

        def do():
            try:
                self.config = load_config()
                results = {}
                cfg = self.config
                try:
                    ensure_fx_daily(cfg)
                    save_config(cfg)
                except Exception:
                    pass

                def fetch_patreon():
                    pc = cfg.get("patreon", {})
                    if not pc.get("cookies"):
                        return ("patreon", None, None)
                    try:
                        url = pc.get("creator_page") or "https://www.patreon.com/c/user"
                        d = PatreonFetcher(pc["cookies"], url).fetch_sponsorship()
                        return ("patreon", d, tr("fetch.err.no_data") if not d else None)
                    except Exception as ex:
                        return ("patreon", None, str(ex))

                def fetch_fanbox():
                    fc = cfg.get("fanbox", {})
                    if not fc.get("cookies"):
                        return ("fanbox", None, None)
                    try:
                        d = FanboxFetcher(fc["cookies"]).fetch_sponsorship()
                        if d and (d.get("amount") or 0) >= 1000:
                            return ("fanbox", d, None)
                        return (
                            "fanbox",
                            None,
                            tr("fetch.err.fanbox_bad") if d else tr("fetch.err.no_data"),
                        )
                    except Exception as ex:
                        return ("fanbox", None, str(ex))

                def fetch_fantia():
                    fic = cfg.get("fantia", {})
                    if not fic.get("session_id"):
                        return ("fantia", None, None)
                    try:
                        d = FantiaFetcher(fic["session_id"]).fetch_sponsorship()
                        return ("fantia", d, tr("fetch.err.no_data") if not d else None)
                    except Exception as ex:
                        return ("fantia", None, str(ex))

                _stagger_s = 0.4
                for i, fn in enumerate((fetch_patreon, fetch_fanbox, fetch_fantia)):
                    if i:
                        time.sleep(_stagger_s)
                    try:
                        plat, data, err = fn()
                        if plat and (data or err):
                            if err:
                                results[plat] = {"error": err}
                            elif data:
                                results[plat] = data
                                save_record(
                                    plat,
                                    data["amount"],
                                    data.get("currency", "USD" if plat == "patreon" else "JPY"),
                                    data.get("patron_count"),
                                )
                    except Exception:
                        pass

                today = today_jst_str()
                for plat, data in results.items():
                    if "error" not in data:
                        update_daily_summary(plat, today, data["amount"], data.get("patron_count"))

                fs = getattr(self, "_pending_update_from_schedule", False)
                r = results
                self._manual_update_done.emit(r, fs)
            except Exception as e:
                self._manual_update_failed.emit(str(e))

        threading.Thread(target=do, daemon=True).start()

    def _update_done(self, results, from_schedule: bool = False):
        self.update_btn.setEnabled(True)
        self.update_btn.setText(tr("settings.fetch"))
        if hasattr(self, "_fetch_hint_lbl"):
            self._fetch_hint_lbl.setVisible(False)
        self._last_update_time_jst = f"{now_jst():%H:%M}"
        self._last_update_lbl.setText(tr("dash.updated", t=self._last_update_time_jst))
        s = None
        try:
            s = get_dashboard_stats()
            new_total = s.get("total_amount") or 0
            prev = getattr(self, "_total_before_update", 0) or 0
            increase_this_update = new_total - prev
            platform_before = getattr(self, "_platform_before_amounts", {}) or {}
            platform_increase = False
            for p in s.get("by_platform") or []:
                plat = p.get("platform")
                if not plat:
                    continue
                after_amt = float(p.get("amount") or 0)
                before_amt = float(platform_before.get(plat) or 0)
                if after_amt > before_amt:
                    platform_increase = True
                    break
            any_increase = (increase_this_update > 0) or platform_increase
            if any_increase:
                self._increase_indicator_until = now_jst() + timedelta(hours=3)
            if increase_this_update > 0:
                if not self._sounds_muted:
                    play_increase_sound(load_config())
                self._last_update_increase = increase_this_update
            else:
                self._last_update_increase = None
            if from_schedule and s is not None and any_increase:
                try:
                    cfg = load_config()
                    url = ((cfg.get("gui") or {}).get("discord_webhook_url") or "").strip()
                    if url and is_discord_webhook_url(url):
                        _lg = get_language()
                        msg = format_scheduled_increase_message(
                            time_jst=f"{now_jst():%Y-%m-%d %H:%M} JST",
                            new_total_jpy=float(new_total),
                            prev_total_jpy=float(prev),
                            increase_jpy=float(increase_this_update),
                            platform_before=dict(platform_before),
                            by_platform=s.get("by_platform") or [],
                            fx_usd_jpy=s.get("fx_usd_jpy"),
                            lang=_lg,
                        )

                        def _send_hook():
                            post_discord_webhook(url, msg, lang=_lg)

                        threading.Thread(target=_send_hook, daemon=True).start()
                except Exception:
                    pass
        except Exception:
            self._last_update_increase = None
        self.config = load_config()
        self._refresh_header_fx_labels()
        if s is not None:
            self._apply_dashboard_ui_immediate(s)
        else:
            self._refresh_dashboard()
        self._refresh_sched_summary_line()

    def _update_fail(self, msg):
        self.update_btn.setEnabled(True)
        self.update_btn.setText(tr("settings.fetch"))
        if hasattr(self, "_fetch_hint_lbl"):
            self._fetch_hint_lbl.setVisible(False)
        QMessageBox.critical(self, tr("update.fail.title"), msg or tr("update.fail.unknown"))

    def _msgbox_version_check_new_release(self, latest: str, ver_local: str) -> bool:
        """\u767c\u73fe\u8f03\u65b0\u7248\u672c\u6642\u8a62\u554f\u662f\u5426\u524d\u5f80\u4e0b\u8f09\u3002\u56de\u50b3 True \u8868\u793a\u958b\u555f\u700f\u89bd\u5668\u3002"""
        mb = QMessageBox(self)
        mb.setWindowTitle(tr("ver.title"))
        mb.setIcon(QMessageBox.Icon.Question)
        mb.setText(tr("ver.new.body", latest=f"<b>{html.escape(latest)}</b>"))
        mb.setTextFormat(Qt.TextFormat.RichText)
        mb.setInformativeText(tr("ver.new.info", local=html.escape(ver_local)))
        btn_dl = mb.addButton(tr("ver.download"), QMessageBox.ButtonRole.AcceptRole)
        mb.addButton(tr("ver.later"), QMessageBox.ButtonRole.RejectRole)
        mb.setDefaultButton(btn_dl)
        mb.exec()
        return mb.clickedButton() == btn_dl

    def _msgbox_version_check_uptodate(self, latest: str, ver_local: str) -> None:
        mb = QMessageBox(self)
        mb.setWindowTitle(tr("ver.title"))
        mb.setIcon(QMessageBox.Icon.Information)
        mb.setText(tr("ver.uptodate"))
        mb.setInformativeText(tr("ver.uptodate.info", local=ver_local, latest=latest))
        mb.setStandardButtons(QMessageBox.StandardButton.Ok)
        mb.exec()

    def _on_update_check_worker_done(self, payload: object) -> None:
        """\u5728\u4e3b\u57f7\u7dd2\u57f7\u884c\uff08\u7531 Signal \u6392\u968a\u9001\u905e\uff09\u3002"""
        self._app_update_busy = False
        self._app_update_btn.setEnabled(True)
        if not isinstance(payload, dict):
            QMessageBox.critical(
                self,
                tr("ver.title"),
                tr("ver.err.internal", detail=f"{payload!r}"),
            )
            return
        if payload.get("exc"):
            detail = (payload.get("trace") or payload.get("exc") or "").strip()
            QMessageBox.critical(
                self,
                tr("ver.title"),
                tr("ver.err.check", detail=detail),
            )
            return

        has_git = bool(payload.get("has_git"))
        repo = str(payload.get("repo") or "")
        git_ok = payload.get("git_ok")
        git_msg = str(payload.get("git_msg") or "")
        latest = payload.get("latest")
        api_err = payload.get("api_err")

        self._app_version_label.setText(tr("settings.version.current", v=current_app_version()))
        ver_local = current_app_version()

        if has_git:
            if git_ok:
                box = QMessageBox(self)
                box.setWindowTitle(tr("ver.git.title"))
                box.setIcon(QMessageBox.Icon.Information)
                box.setText(tr("ver.git.ok"))
                box.exec()
            else:
                QMessageBox.critical(self, tr("ver.git.title"), git_msg)

        if not repo:
            if not has_git:
                mb = QMessageBox(self)
                mb.setWindowTitle(tr("ver.title"))
                mb.setIcon(QMessageBox.Icon.Warning)
                mb.setText(tr("ver.no_repo"))
                mb.setInformativeText(tr("ver.no_repo.info"))
                mb.setStandardButtons(QMessageBox.StandardButton.Ok)
                mb.exec()
            return

        if latest is None:
            mb = QMessageBox(self)
            mb.setWindowTitle(tr("ver.title"))
            mb.setIcon(QMessageBox.Icon.Warning)
            mb.setText(tr("ver.cmp_fail"))
            detail = (api_err or "").strip() or tr("ver.cmp_fail.nodetail")
            mb.setInformativeText(tr("ver.cmp_fail.info", detail=detail))
            mb.setStandardButtons(QMessageBox.StandardButton.Ok)
            mb.exec()
            return

        if version_newer_than(str(latest), ver_local):
            if self._msgbox_version_check_new_release(str(latest), ver_local):
                QDesktopServices.openUrl(QUrl(releases_latest_url(repo)))
        else:
            self._msgbox_version_check_uptodate(str(latest), ver_local)

    def _on_open_github_repo_clicked(self) -> None:
        repo = (configured_github_repo() or "").strip()
        if not repo or repo.count("/") != 1:
            return
        QDesktopServices.openUrl(QUrl(f"https://github.com/{repo}"))

    def _on_export_daily_csv_clicked(self) -> None:
        default_n = f"sponsor_daily_{today_jst_str().replace('-', '')}.csv"
        path, _ = QFileDialog.getSaveFileName(
            self,
            tr("settings.export.dialog_title"),
            str(Path.home() / default_n),
            "CSV (*.csv)",
        )
        if not path:
            return
        p = Path(path)
        if p.suffix.lower() != ".csv":
            p = p.with_suffix(".csv")
        ok, msg = export_daily_summary_csv(p)
        if ok:
            QMessageBox.information(
                self,
                tr("settings.export.title"),
                tr("settings.export.ok", path=msg),
            )
        else:
            QMessageBox.critical(
                self,
                tr("settings.export.title"),
                tr("settings.export.fail", err=msg),
            )

    def _on_app_update_clicked(self):
        if self._app_update_busy:
            return
        self._app_update_busy = True
        self._app_update_btn.setEnabled(False)
        has_git = project_has_git()
        repo = configured_github_repo()

        def work():
            import traceback

            try:
                git_ok: bool | None = None
                git_msg = ""
                if has_git:
                    git_ok, git_msg = git_pull_project()
                latest: str | None = None
                api_err: str | None = None
                if repo:
                    latest, api_err = fetch_latest_release_tag(repo)
                self._update_check_worker_done.emit(
                    {
                        "has_git": has_git,
                        "repo": repo,
                        "git_ok": git_ok,
                        "git_msg": git_msg,
                        "latest": latest,
                        "api_err": api_err,
                    }
                )
            except Exception as e:
                self._update_check_worker_done.emit(
                    {"exc": repr(e), "trace": traceback.format_exc()}
                )

        threading.Thread(target=work, daemon=True).start()

    def _on_oneclick_update_clicked(self):
        if self._oneclick_busy:
            return
        if not lazy_update_supported():
            QMessageBox.information(
                self,
                tr("oneclick.title"),
                tr("oneclick.win_only"),
            )
            return
        repo = configured_github_repo()
        if not repo:
            QMessageBox.warning(
                self,
                tr("oneclick.title"),
                tr("oneclick.no_repo"),
            )
            return
        self._oneclick_busy = True
        self._app_oneclick_btn.setEnabled(False)

        def check_work():
            import traceback

            try:
                plan, err = fetch_lazy_update_plan(repo)
                if err:
                    self._oneclick_check_done.emit({"ok": False, "error": err})
                    return
                if plan and plan.get("kind") == "uptodate":
                    self._oneclick_check_done.emit(
                        {
                            "ok": True,
                            "uptodate": True,
                            "latest": str(plan.get("latest") or ""),
                        }
                    )
                    return
                if plan and plan.get("kind") == "update":
                    self._oneclick_check_done.emit({"ok": True, "uptodate": False, "plan": plan})
                    return
                self._oneclick_check_done.emit({"ok": False, "error": tr("oneclick.err.bad")})
            except Exception:
                self._oneclick_check_done.emit(
                    {"ok": False, "error": traceback.format_exc()}
                )

        threading.Thread(target=check_work, daemon=True).start()

    def _on_oneclick_check_done(self, payload: object) -> None:
        if not isinstance(payload, dict):
            self._oneclick_busy = False
            self._app_oneclick_btn.setEnabled(True)
            return
        if not payload.get("ok"):
            self._oneclick_busy = False
            self._app_oneclick_btn.setEnabled(True)
            QMessageBox.critical(
                self,
                tr("oneclick.title"),
                str(payload.get("error") or tr("oneclick.err.unknown")),
            )
            return
        if payload.get("uptodate"):
            self._oneclick_busy = False
            self._app_oneclick_btn.setEnabled(True)
            QMessageBox.information(
                self,
                tr("oneclick.title"),
                tr("oneclick.err.info", tag=str(payload.get("latest") or "")),
            )
            return
        plan = payload.get("plan")
        if not isinstance(plan, dict):
            self._oneclick_busy = False
            self._app_oneclick_btn.setEnabled(True)
            return
        latest = str(plan.get("latest") or "")
        size = int(plan.get("size") or 0)
        size_txt = (
            tr("oneclick.size_mb", mb=size / (1024 * 1024)) if size > 0 else tr("oneclick.size_unknown")
        )
        q = QMessageBox.question(
            self,
            tr("oneclick.title"),
            tr("oneclick.ask", latest=latest, size=size_txt),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if q != QMessageBox.StandardButton.Yes:
            self._oneclick_busy = False
            self._app_oneclick_btn.setEnabled(True)
            return
        self._start_oneclick_download(plan)

    def _start_oneclick_download(self, plan: dict) -> None:
        url = str(plan.get("url") or "").strip()
        if not url:
            self._oneclick_busy = False
            self._app_oneclick_btn.setEnabled(True)
            QMessageBox.warning(self, tr("oneclick.title"), tr("oneclick.no_url"))
            return
        self._oneclick_prog = QProgressDialog(
            tr("oneclick.downloading"),
            None,
            0,
            100,
            self,
        )
        self._oneclick_prog.setWindowTitle(tr("oneclick.title"))
        self._oneclick_prog.setWindowModality(Qt.WindowModality.WindowModal)
        self._oneclick_prog.setMinimumDuration(0)
        self._oneclick_prog.setCancelButton(None)
        self._oneclick_prog.setValue(0)
        self._oneclick_prog.show()

        exe_name = Path(sys.executable).name

        def dl_work():
            import traceback

            try:

                def prog(n: int, t: int) -> None:
                    self._oneclick_dl_progress.emit(n, t)

                staging, work_root, err = download_zip_and_extract(url, exe_name, prog)
                if err:
                    self._oneclick_dl_done.emit({"ok": False, "error": err})
                    return
                self._oneclick_dl_done.emit(
                    {
                        "ok": True,
                        "staging": str(staging),
                        "work_root": str(work_root),
                    }
                )
            except Exception:
                self._oneclick_dl_done.emit(
                    {"ok": False, "error": traceback.format_exc()}
                )

        threading.Thread(target=dl_work, daemon=True).start()

    def _on_oneclick_dl_progress(self, n: int, total: int) -> None:
        if not self._oneclick_prog:
            return
        if total > 0:
            self._oneclick_prog.setRange(0, total)
            self._oneclick_prog.setValue(min(n, total))
        else:
            self._oneclick_prog.setRange(0, 0)

    def _on_oneclick_dl_done(self, payload: object) -> None:
        if self._oneclick_prog is not None:
            self._oneclick_prog.close()
            self._oneclick_prog = None
        self._oneclick_busy = False
        self._app_oneclick_btn.setEnabled(True)
        if not isinstance(payload, dict) or not payload.get("ok"):
            QMessageBox.critical(
                self,
                tr("oneclick.title"),
                str((payload or {}).get("error") or tr("oneclick.dl_fail")),
            )
            return
        staging_s = str(payload.get("staging") or "").strip()
        work_s = str(payload.get("work_root") or "").strip()
        if not staging_s or not work_s:
            QMessageBox.critical(self, tr("oneclick.title"), tr("oneclick.path_invalid"))
            return
        QMessageBox.information(
            self,
            tr("oneclick.title"),
            tr("oneclick.done"),
        )
        ok, msg = spawn_lazy_windows_updater(Path(staging_s), Path(work_s))
        if not ok:
            QMessageBox.critical(self, tr("oneclick.title"), msg or tr("oneclick.spawn_fail"))
            return
        self._quit_fully()

    @staticmethod
    def _switch_is_on(checked: bool) -> bool:
        return bool(checked)

    def _add_settings_group(
        self, column: QVBoxLayout, title_key: str, blurb_key: str | None = None
    ) -> None:
        t = QLabel(tr(title_key))
        t.setObjectName("settingsHeadline")
        column.addWidget(t)
        self._settings_i18n_headings.append((t, title_key))
        if blurb_key:
            b = QLabel(tr(blurb_key))
            b.setObjectName("settingsBlurb")
            b.setWordWrap(True)
            column.addWidget(b)
            self._settings_i18n_blurbs.append((b, blurb_key))



    def _build_prefs_scroll_content(
        self, left: QVBoxLayout, right: QVBoxLayout, card_parent: QWidget
    ) -> None:
        gui_sound = self.config.get("gui") or {}
        self._settings_i18n_headings.clear()
        self._settings_i18n_blurbs.clear()

        self._add_settings_group(left, "settings.lang", "settings.lang_hint")
        lang_card = _make_settings_group_card(card_parent)
        lang_l = QVBoxLayout(lang_card)
        lang_l.setContentsMargins(14, 12, 14, 12)
        lang_l.setSpacing(8)
        self._ui_lang_combo = QComboBox()
        _lang_pairs = (
            ("auto", "lang.auto"),
            (LANG_ZH_TW, "lang.zh_TW"),
            (LANG_EN, "lang.en"),
            (LANG_JA, "lang.ja"),
        )
        for _val, lk in _lang_pairs:
            self._ui_lang_combo.addItem(tr(lk), _val)
        raw_ui = str(gui_sound.get("ui_language", "auto")).strip().lower()
        _sel_lang = "auto" if raw_ui in ("auto", "", "system") else normalize_ui_language_raw(raw_ui)
        with QSignalBlocker(self._ui_lang_combo):
            for _i in range(self._ui_lang_combo.count()):
                if self._ui_lang_combo.itemData(_i) == _sel_lang:
                    self._ui_lang_combo.setCurrentIndex(_i)
                    break
        self._ui_lang_combo.currentIndexChanged.connect(self._on_ui_language_changed)
        lang_l.addWidget(self._ui_lang_combo)
        left.addWidget(lang_card)
        left.addSpacing(_SETTINGS_SECTION_VGAP)

        self._add_settings_group(left, "settings.currency.title", "settings.currency.blurb")
        cur_card = _make_settings_group_card(card_parent)
        cur_l = QVBoxLayout(cur_card)
        cur_l.setContentsMargins(14, 12, 14, 12)
        cur_l.setSpacing(8)
        self._display_currency_combo = QComboBox()
        for _code, lk in (
            ("jpy", "settings.currency.jpy"),
            ("twd", "settings.currency.twd"),
            ("usd", "settings.currency.usd"),
        ):
            self._display_currency_combo.addItem(tr(lk), _code)
        _dcc0 = display_currency_code(self.config)
        with QSignalBlocker(self._display_currency_combo):
            for _i in range(self._display_currency_combo.count()):
                if self._display_currency_combo.itemData(_i) == _dcc0:
                    self._display_currency_combo.setCurrentIndex(_i)
                    break
        self._display_currency_combo.currentIndexChanged.connect(self._on_display_currency_changed)
        cur_l.addWidget(self._display_currency_combo)
        left.addWidget(cur_card)
        left.addSpacing(_SETTINGS_SECTION_VGAP)

        self._add_settings_group(left, "settings.group.tray")
        tray_card = _make_settings_group_card(card_parent)
        tl = QVBoxLayout(tray_card)
        tl.setContentsMargins(14, 12, 14, 12)
        tl.setSpacing(8)
        self._sw_close_tray = QCheckBox(tr("settings.tray.close"))
        self._sw_close_tray.setChecked(self._close_to_tray)
        self._sw_close_tray.toggled.connect(self._on_switch_close_to_tray)
        self._sw_min_tray = QCheckBox(tr("settings.tray.min"))
        self._sw_min_tray.setChecked(self._minimize_to_tray)
        self._sw_min_tray.toggled.connect(self._on_switch_minimize_to_tray)
        self._sw_start_tray = QCheckBox(tr("settings.tray.start"))
        self._sw_start_tray.setChecked(self._start_minimized_to_tray)
        self._sw_start_tray.toggled.connect(self._on_switch_start_tray)
        self._sw_autostart = QCheckBox(tr("settings.tray.autostart"))
        with QSignalBlocker(self._sw_autostart):
            self._sw_autostart.setChecked(self._start_with_windows)
        if sys.platform != "win32":
            self._sw_autostart.setEnabled(False)
            self._sw_autostart.setToolTip(tr("settings.tray.autostart_tip"))
        self._sw_autostart.toggled.connect(self._on_switch_autostart)
        for w in (self._sw_close_tray, self._sw_min_tray, self._sw_start_tray, self._sw_autostart):
            tl.addWidget(w)
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self._sw_close_tray.setEnabled(False)
            self._sw_min_tray.setEnabled(False)
            self._sw_start_tray.setEnabled(False)
        left.addWidget(tray_card)
        left.addSpacing(_SETTINGS_SECTION_VGAP)

        self._add_settings_group(left, "settings.group.version", "settings.version.blurb")
        ver_card = _make_settings_group_card(card_parent)
        vl = QVBoxLayout(ver_card)
        vl.setContentsMargins(14, 12, 14, 12)
        vl.setSpacing(10)
        self._app_version_label = QLabel(tr("settings.version.current", v=current_app_version()))
        self._app_version_label.setObjectName("settingsFormLabel")
        vl.addWidget(self._app_version_label)
        ver_btn_row = QHBoxLayout()
        ver_btn_row.setSpacing(8)
        self._app_update_btn = QPushButton(tr("settings.update.check"))
        self._app_update_btn.setMinimumHeight(36)
        self._app_update_btn.clicked.connect(self._on_app_update_clicked)
        ver_btn_row.addWidget(self._app_update_btn, 1)
        self._app_oneclick_btn = QPushButton(tr("settings.update.oneclick"))
        self._app_oneclick_btn.setMinimumHeight(36)
        self._app_oneclick_btn.clicked.connect(self._on_oneclick_update_clicked)
        if not lazy_update_supported():
            self._app_oneclick_btn.setEnabled(False)
            self._app_oneclick_btn.setToolTip(tr("settings.update.oneclick_tip"))
        ver_btn_row.addWidget(self._app_oneclick_btn, 1)
        vl.addLayout(ver_btn_row)
        self._btn_github_repo = QPushButton(tr("settings.version.github"))
        self._btn_github_repo.setMinimumHeight(36)
        self._btn_github_repo.clicked.connect(self._on_open_github_repo_clicked)
        _repo0 = (configured_github_repo() or "").strip()
        if not _repo0 or _repo0.count("/") != 1:
            self._btn_github_repo.setEnabled(False)
            self._btn_github_repo.setToolTip(tr("settings.version.github_tip"))
        vl.addWidget(self._btn_github_repo)
        left.addWidget(ver_card)
        left.addSpacing(_SETTINGS_SECTION_VGAP)

        self._add_settings_group(right, "settings.group.sound")
        sound_card = _make_settings_group_card(card_parent)
        sil = QVBoxLayout(sound_card)
        sil.setContentsMargins(14, 12, 14, 12)
        sil.setSpacing(10)
        r1 = QHBoxLayout()
        self._lbl_sound_system = _settings_form_label(tr("settings.sound.system"))
        r1.addWidget(self._lbl_sound_system, 0)
        self._increase_sound_preset = QComboBox()
        self._increase_sound_preset.currentIndexChanged.connect(self._on_increase_sound_preset_changed)
        self._rebuild_sound_preset_combo(gui_sound.get("increase_sound"))
        r1.addWidget(self._increase_sound_preset, 1)
        self._btn_sound_test = QPushButton(tr("settings.sound.test"))
        self._btn_sound_test.clicked.connect(self._test_increase_sound)
        r1.addWidget(self._btn_sound_test)
        sil.addLayout(r1)
        vr = QHBoxLayout()
        self._lbl_sound_volume = _settings_form_label(tr("settings.sound.volume"))
        vr.addWidget(self._lbl_sound_volume, 0)
        self._sound_volume_slider = QSlider(Qt.Orientation.Horizontal)
        self._sound_volume_slider.setRange(0, 100)
        _v0 = int(float(gui_sound.get("increase_sound_volume", 100)))
        self._sound_volume_slider.setValue(_v0)
        self._sound_volume_slider.valueChanged.connect(self._on_sound_volume_slider)
        vr.addWidget(self._sound_volume_slider, 1)
        self._sound_volume_lbl = QLabel(f"{_v0}%")
        vr.addWidget(self._sound_volume_lbl)
        sil.addLayout(vr)
        self._lbl_sound_wav = _settings_form_label(tr("settings.sound.wav"))
        sil.addWidget(self._lbl_sound_wav)
        self._increase_sound_wav_entry = QLineEdit()
        self._increase_sound_wav_entry.setText(gui_sound.get("increase_sound_wav") or "")
        self._increase_sound_wav_entry.editingFinished.connect(self._on_increase_sound_wav_done)
        sil.addWidget(self._increase_sound_wav_entry)
        right.addWidget(sound_card)
        right.addSpacing(_SETTINGS_SECTION_VGAP)

        self._add_settings_group(right, "settings.group.discord")
        dc = _make_settings_group_card(card_parent)
        dcl = QVBoxLayout(dc)
        dcl.setContentsMargins(14, 12, 14, 12)
        dcl.setSpacing(10)
        dcl.addWidget(_settings_form_label(tr("settings.discord.url")))
        self._discord_webhook_entry = QLineEdit()
        self._discord_webhook_entry.setPlaceholderText("https://discord.com/api/webhooks/...")
        self._discord_webhook_entry.setText(gui_sound.get("discord_webhook_url") or "")
        self._discord_webhook_entry.editingFinished.connect(self._on_discord_webhook_done)
        dcl.addWidget(self._discord_webhook_entry)
        dbtn = QHBoxLayout()
        self._btn_discord_test = QPushButton(tr("settings.discord.test"))
        self._btn_discord_test.clicked.connect(self._test_discord_webhook)
        dbtn.addWidget(self._btn_discord_test)
        dbtn.addStretch()
        dcl.addLayout(dbtn)
        self._sw_daily_report = QCheckBox(tr("settings.discord.daily"))
        self._sw_daily_report.setChecked(bool(gui_sound.get("daily_report_enabled")))
        self._sw_daily_report.toggled.connect(self._on_daily_report_switch)
        dcl.addWidget(self._sw_daily_report)
        dtr = QHBoxLayout()
        self._lbl_discord_time = _settings_form_label(tr("settings.discord.time"))
        dtr.addWidget(self._lbl_discord_time, 0)
        self._daily_report_time_entry = QLineEdit()
        _drt = gui_sound.get("daily_report_time_jst") or "09:00"
        _parsed_drt = parse_jst_hhmm(str(_drt))
        if _parsed_drt:
            _drt = f"{_parsed_drt[0]:02d}:{_parsed_drt[1]:02d}"
        self._daily_report_time_entry.setText(_drt)
        self._daily_report_time_entry.editingFinished.connect(self._on_daily_report_time_done)
        dtr.addWidget(self._daily_report_time_entry, 1)
        self._btn_discord_report_test = QPushButton(tr("settings.discord.test_report"))
        self._btn_discord_report_test.clicked.connect(self._test_discord_daily_report)
        dtr.addWidget(self._btn_discord_report_test)
        dcl.addLayout(dtr)
        right.addWidget(dc)
        right.addSpacing(_SETTINGS_SECTION_VGAP)

        left.addStretch(1)
        right.addStretch(1)


    def _build_account_scroll_content(
        self, left: QVBoxLayout, right: QVBoxLayout, card_parent: QWidget
    ) -> None:
        gui_sound = self.config.get("gui") or {}

        self._add_settings_group(left, "settings.group.sync")
        sync_card = _make_settings_group_card(card_parent)
        sl = QVBoxLayout(sync_card)
        sl.setContentsMargins(14, 12, 14, 12)
        sl.setSpacing(10)
        self.update_btn = QPushButton(tr("settings.fetch"))
        self.update_btn.setObjectName("primary")
        self.update_btn.clicked.connect(self._run_update)
        self.update_btn.setMinimumHeight(38)
        self._sched_btn = QPushButton(tr("settings.sched.start"))
        self._sched_btn.setObjectName("success")
        self._sched_btn.setMinimumHeight(38)
        self._sched_btn.clicked.connect(self._toggle_schedule)
        row_sync = QHBoxLayout()
        row_sync.setSpacing(8)
        row_sync.addWidget(self.update_btn, 1)
        row_sync.addWidget(self._sched_btn, 1)
        sl.addLayout(row_sync)
        self._fetch_hint_lbl = QLabel(tr("settings.fetch.hint"))
        self._fetch_hint_lbl.setVisible(False)
        self._fetch_hint_lbl.setObjectName("settingsStatus")
        self._fetch_hint_lbl.setStyleSheet(
            f"color: {PALETTE['accent']}; font-weight: 600; font-size: 13px;"
        )
        sl.addWidget(self._fetch_hint_lbl)
        row_iv = QHBoxLayout()
        self._lbl_sched_interval = _settings_form_label(tr("settings.sched.interval"))
        row_iv.addWidget(self._lbl_sched_interval, 0)
        self._sched_interval = QComboBox()
        self._sched_interval.currentIndexChanged.connect(self._on_schedule_interval_changed)
        self._rebuild_sched_interval_combo(
            normalize_schedule_interval_id(str(gui_sound.get("schedule_interval") or "1h"))
        )
        row_iv.addWidget(self._sched_interval, 1)
        sl.addLayout(row_iv)
        self.update_status = QLabel("")
        self.update_status.setObjectName("settingsStatus")
        self.update_status.setWordWrap(True)
        sl.addWidget(self.update_status)
        self._sched_summary_lbl = QLabel("")
        self._sched_summary_lbl.setObjectName("settingsFormLabel")
        self._sched_summary_lbl.setWordWrap(True)
        self._sched_summary_lbl.setStyleSheet(f"color: {PALETTE['text_secondary']};")
        sl.addWidget(self._sched_summary_lbl)

        left.addWidget(sync_card)
        left.addSpacing(_SETTINGS_SECTION_VGAP)

        self._add_settings_group(left, "settings.export.title", "settings.export.blurb")
        export_card = _make_settings_group_card(card_parent)
        ex_l = QVBoxLayout(export_card)
        ex_l.setContentsMargins(14, 12, 14, 12)
        ex_l.setSpacing(8)
        self._btn_export_csv = QPushButton(tr("settings.export.btn"))
        self._btn_export_csv.setMinimumHeight(36)
        self._btn_export_csv.clicked.connect(self._on_export_daily_csv_clicked)
        ex_l.addWidget(self._btn_export_csv)
        left.addWidget(export_card)
        left.addSpacing(_SETTINGS_SECTION_VGAP)

        self._add_settings_group(left, "settings.group.purge", "settings.purge.blurb")
        purge_card = _make_settings_group_card(card_parent)
        pr = QVBoxLayout(purge_card)
        pr.setContentsMargins(14, 12, 14, 12)
        pr.setSpacing(10)
        self._purge_btn = QPushButton(tr("settings.purge.btn"))
        self._purge_btn.setStyleSheet(
            f"background-color: {PALETTE['error']}; color: #ffffff; border: none; "
            f"border-radius: 10px; font-weight: 600; padding: 8px 18px;"
        )
        self._purge_btn.clicked.connect(self._master_clear_login_and_history)
        pr.addWidget(self._purge_btn)
        left.addWidget(purge_card)
        left.addSpacing(_SETTINGS_SECTION_VGAP)

        self._refresh_schedule_button_and_status()
        self._refresh_sched_summary_line()

        if not PLAYWRIGHT_AVAILABLE:
            self._lbl_playwright_miss = QLabel(tr("settings.playwright.missing"))
            self._lbl_playwright_miss.setStyleSheet(f"color: {PALETTE['warning']};")
            left.addWidget(self._lbl_playwright_miss)
            left.addSpacing(_SETTINGS_SECTION_VGAP)

        self._add_settings_group(right, "settings.group.accounts")
        acc_card = _make_settings_group_card(card_parent)
        acc_l = QVBoxLayout(acc_card)
        acc_l.setContentsMargins(0, 2, 0, 2)
        acc_l.setSpacing(0)
        self._plat_hint_label = QLabel(tr("settings.platform.hint"))
        self._plat_hint_label.setWordWrap(True)
        self._plat_hint_label.setObjectName("settingsFormLabel")
        self._plat_hint_label.setStyleSheet(
            f"font-size: 14px !important; "
            f"padding: 12px 14px; margin: 8px 12px 0 12px; "
            f"background-color: {PALETTE['bg_elevated']}; "
            f"border-left: 3px solid {PALETTE['accent']}; border-radius: 6px;"
        )
        acc_l.addWidget(self._plat_hint_label)
        _plat_div = QFrame()
        _plat_div.setObjectName("settingsDivider")
        _plat_div.setFixedHeight(1)
        acc_l.addWidget(_plat_div)
        for j, (name, desc, key, color) in enumerate(
            [
                ("Patreon", "", "patreon", PALETTE["patreon"]),
                ("Fanbox", "", "fanbox", PALETTE["fanbox"]),
                ("Fantia", "", "fantia", PALETTE["fantia"]),
            ]
        ):
            if j > 0:
                div = QFrame()
                div.setObjectName("settingsDivider")
                div.setFixedHeight(1)
                acc_l.addWidget(div)
            roww = QWidget()
            rl = QVBoxLayout(roww)
            rl.setContentsMargins(12, 8, 12, 8)
            rl.setSpacing(6)
            top = QHBoxLayout()
            dot = QLabel("\u25cf")
            dot.setStyleSheet(f"color: {color};")
            top.addWidget(dot)
            top.addWidget(QLabel(name))
            cfg = self.config.get(key, {})
            if key in ("patreon", "fanbox"):
                logged = bool((cfg.get("cookies") or "").strip() and "xxx" not in (cfg.get("cookies") or ""))
            else:
                _sid = (cfg.get("session_id") or "").strip()
                logged = bool(_sid) and "\u4f60\u7684" not in _sid and not _sid.lower().startswith("your ")
            st = QLabel(tr("settings.account.in") if logged else tr("settings.account.out"))
            st.setStyleSheet(f"color: {PALETTE['success'] if logged else PALETTE['text_tertiary']};")
            st.setToolTip("")
            top.addStretch()
            top.addWidget(st)
            setattr(self, f"{key}_status", st)
            rl.addLayout(top)
            if (desc or "").strip():
                desc_l = QLabel(desc)
                desc_l.setObjectName("settingsFormLabel")
                desc_l.setWordWrap(True)
                rl.addWidget(desc_l)
            bl = QHBoxLayout()
            bl.setSpacing(8)
            btn = QPushButton(tr("settings.login"))
            btn.setStyleSheet(
                f"background-color: {color}; color: #ffffff; border: none; "
                f"border-radius: 10px; font-weight: 600; padding: 8px 18px;"
            )
            btn.clicked.connect(getattr(self, f"_{key}_login_start"))
            setattr(self, f"{key}_btn", btn)
            done_btn = QPushButton(tr("settings.done"))
            done_btn.setEnabled(False)
            done_btn.clicked.connect(getattr(self, f"_{key}_login_done"))
            setattr(self, f"{key}_done_btn", done_btn)
            logout_btn = QPushButton(tr("settings.logout"))
            logout_btn.clicked.connect(partial(self._platform_login_logout, key))
            setattr(self, f"{key}_logout_btn", logout_btn)
            bl.addWidget(btn)
            bl.addWidget(done_btn)
            bl.addWidget(logout_btn)
            bl.addStretch()
            rl.addLayout(bl)
            sw_vis = QCheckBox(tr("settings.platform.show_overview"))
            _g_vis = self.config.get("gui") or {}
            _sp_vis = _g_vis.get("show_platforms") or {}
            sw_vis.setChecked(True if _sp_vis.get(key) is None else bool(_sp_vis.get(key)))
            sw_vis.toggled.connect(partial(self._on_platform_visibility_toggled, key))
            setattr(self, f"_sw_plat_vis_{key}", sw_vis)
            rl.addWidget(sw_vis)
            acc_l.addWidget(roww)
        right.addWidget(acc_card)
        right.addSpacing(_SETTINGS_SECTION_VGAP)

        if not PLAYWRIGHT_AVAILABLE:
            for key in ("patreon", "fanbox", "fantia"):
                getattr(self, f"{key}_btn").setEnabled(False)
                getattr(self, f"{key}_logout_btn").setEnabled(False)

        left.addStretch(1)
        right.addStretch(1)

    def _on_switch_close_to_tray(self, c):
        self._close_to_tray = bool(c)
        self._save_tray_gui_prefs()

    def _on_switch_minimize_to_tray(self, c):
        self._minimize_to_tray = bool(c)
        self._save_tray_gui_prefs()

    def _on_switch_start_tray(self, c):
        self._start_minimized_to_tray = bool(c)
        self._save_tray_gui_prefs()

    def _sync_windows_autostart(self):
        if sys.platform != "win32":
            return
        from src.win_autostart import apply_start_with_windows

        apply_start_with_windows(self._start_with_windows)

    def _on_switch_autostart(self, c):
        self._start_with_windows = bool(c)
        self._save_tray_gui_prefs()
        if sys.platform != "win32":
            return
        from src.win_autostart import apply_start_with_windows

        ok, msg = apply_start_with_windows(self._start_with_windows)
        if not ok and msg:
            if msg.startswith("REG:"):
                detail = msg[4:]
                body = tr("win.err.registry", e=detail)
            elif msg == "LAUNCH":
                body = tr("win.err.launch")
            else:
                body = msg
            QMessageBox.warning(self, tr("autostart.fail.title"), body)

    def _on_sound_volume_slider(self, v):
        self._sound_volume_lbl.setText(f"{int(v)}%")
        if self._sound_vol_timer is None:
            self._sound_vol_timer = QTimer(self)
            self._sound_vol_timer.setSingleShot(True)
            self._sound_vol_timer.timeout.connect(self._persist_sound_volume_from_slider)
        self._sound_vol_timer.stop()
        self._sound_vol_timer.start(400)

    def _persist_sound_volume_from_slider(self):
        val = max(0, min(100, int(self._sound_volume_slider.value())))
        self.config = load_config()
        self.config.setdefault("gui", {})["increase_sound_volume"] = val
        save_config(self.config)

    def _on_increase_sound_preset_changed(self, _idx: int = 0) -> None:
        key = self._increase_sound_preset.currentData()
        if not isinstance(key, str):
            return
        self.config = load_config()
        self.config.setdefault("gui", {})["increase_sound"] = key
        save_config(self.config)

    def _on_increase_sound_wav_done(self):
        self.config = load_config()
        self.config.setdefault("gui", {})["increase_sound_wav"] = self._increase_sound_wav_entry.text().strip()
        save_config(self.config)

    def _test_increase_sound(self):
        snap = load_config()
        gui = snap.setdefault("gui", {})
        key = self._increase_sound_preset.currentData() or "asterisk"
        gui["increase_sound"] = key
        if key == "alert_bundle":
            gui["increase_sound_wav"] = ""
        else:
            gui["increase_sound_wav"] = self._increase_sound_wav_entry.text().strip()
        gui["increase_sound_volume"] = int(self._sound_volume_slider.value())
        play_increase_sound(snap)

    def _on_discord_webhook_done(self):
        self.config = load_config()
        self.config.setdefault("gui", {})["discord_webhook_url"] = self._discord_webhook_entry.text().strip()
        save_config(self.config)

    def _test_discord_webhook(self):
        url = self._discord_webhook_entry.text().strip()
        if not url:
            QMessageBox.warning(self, tr("discord.title"), tr("discord.need_url"))
            return
        if not is_discord_webhook_url(url):
            QMessageBox.critical(
                self,
                tr("discord.title"),
                tr("discord.bad_url"),
            )
            return
        _msg = tr("discord.test.msg")
        _lg = get_language()

        def _run():
            ok, err = post_discord_webhook(url, _msg, lang=_lg)

            def _done():
                if ok:
                    QMessageBox.information(self, tr("discord.title"), tr("discord.test.ok"))
                else:
                    QMessageBox.critical(
                        self, tr("discord.title"), tr("discord.test.fail", err=err or "")
                    )

            QTimer.singleShot(0, _done)

        threading.Thread(target=_run, daemon=True).start()

    def _on_daily_report_switch(self, c):
        self.config = load_config()
        self.config.setdefault("gui", {})["daily_report_enabled"] = bool(c)
        save_config(self.config)

    def _on_daily_report_time_done(self):
        raw = self._daily_report_time_entry.text().strip()
        parsed = parse_jst_hhmm(raw)
        norm = f"{parsed[0]:02d}:{parsed[1]:02d}" if parsed else "09:00"
        self._daily_report_time_entry.setText(norm)
        self.config = load_config()
        self.config.setdefault("gui", {})["daily_report_time_jst"] = norm
        save_config(self.config)

    def _test_discord_daily_report(self):
        url = self._discord_webhook_entry.text().strip()
        if not url:
            QMessageBox.warning(self, tr("discord.report.title"), tr("discord.need_url"))
            return
        if not is_discord_webhook_url(url):
            QMessageBox.critical(self, tr("discord.report.title"), tr("discord.bad_url"))
            return
        _lg = get_language()

        def _run():
            try:
                s = get_dashboard_stats()
                period = get_total_vs_days_ago(7)
            except Exception as ex:

                def _fail():
                    QMessageBox.critical(
                        self, tr("discord.report.title"), tr("discord.report.read_fail", ex=ex)
                    )

                QTimer.singleShot(0, _fail)
                return
            text = format_daily_dashboard_report(
                s,
                period,
                time_jst=f"{now_jst():%Y-%m-%d %H:%M} JST",
                lang=_lg,
            )
            ok, err = post_discord_webhook_long(url, text, lang=_lg)

            def _done():
                if ok:
                    QMessageBox.information(self, tr("discord.report.title"), tr("discord.report.sent"))
                else:
                    QMessageBox.critical(
                        self, tr("discord.report.title"), tr("discord.report.send_fail", err=err or "")
                    )

            QTimer.singleShot(0, _done)

        threading.Thread(target=_run, daemon=True).start()

    def _ensure_daily_report_thread(self):
        if self._daily_report_thread_started:
            return
        self._daily_report_thread_started = True
        threading.Thread(target=self._daily_report_loop, daemon=True).start()

    def _daily_report_loop(self):
        while True:
            time.sleep(25)
            try:
                cfg = load_config()
                gui = cfg.get("gui") or {}
                if not gui.get("daily_report_enabled"):
                    continue
                url = (gui.get("discord_webhook_url") or "").strip()
                if not url or not is_discord_webhook_url(url):
                    continue
                hhmm = parse_jst_hhmm(gui.get("daily_report_time_jst") or "09:00")
                if hhmm is None:
                    continue
                th, tm = hhmm
                now = now_jst()
                if now.hour != th or now.minute != tm:
                    continue
                d = now.strftime("%Y-%m-%d")
                if self._last_daily_report_sent_jst_date == d:
                    continue
                try:
                    s = get_dashboard_stats()
                    period = get_total_vs_days_ago(7)
                except Exception:
                    continue
                _lg = effective_ui_language(cfg)
                text = format_daily_dashboard_report(
                    s,
                    period,
                    time_jst=f"{now:%Y-%m-%d %H:%M} JST",
                    lang=_lg,
                )
                ok, _ = post_discord_webhook_long(url, text, lang=_lg)
                if ok:
                    self._last_daily_report_sent_jst_date = d
            except Exception:
                pass

    def _clear_platform_login_state(self, key: str, *, persist: bool = True) -> None:
        self._login_flow_active[key] = False
        if ce := self.browser_cancel_events.get(key):
            ce.set()
        if ev := self.browser_done_events.get(key):
            ev.set()
        if key == "fantia":
            self.config.setdefault("fantia", {})["session_id"] = ""
        else:
            self.config.setdefault(key, {})["cookies"] = ""
        if persist:
            save_config(self.config)
        st = getattr(self, f"{key}_status")
        st.setText(tr("settings.account.out"))
        st.setStyleSheet(f"color: {PALETTE['text_tertiary']};")
        st.setToolTip("")
        getattr(self, f"{key}_btn").setEnabled(True)
        getattr(self, f"{key}_done_btn").setEnabled(False)

    def _platform_login_logout(self, key: str) -> None:
        self._clear_platform_login_state(key)

    def _master_clear_login_and_history(self) -> None:
        r = QMessageBox.question(
            self,
            tr("purge.title"),
            tr("purge.question"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if r != QMessageBox.StandardButton.Yes:
            return
        for k in ("patreon", "fanbox", "fantia"):
            self._clear_platform_login_state(k, persist=False)
        save_config(self.config)
        clear_sponsorship_data()
        self._refresh_dashboard()

    # --- login ---
    def _on_browser_login_payload(self, platform: str, generation: int, payload: str) -> None:
        """\u7531 Signal \u5f9e Playwright \u57f7\u7dd2\u56de\u5230\u4e3b\u57f7\u7dd2\u8655\u7406\u3002

        generation \u8207\u7576\u524d\u767b\u5165\u6b21\u6578\u4e00\u81f4\u624d\u8655\u7406\uff0c\u907f\u514d\u91cd\u6309\u300c\u767b\u5165\u300d\u6216\u820a\u57f7\u7dd2\u5148\u56de\u50b3\u7a7a\u503c\u6642\u8aa4\u6e05\u72c0\u614b\u3002
        """
        if self._browser_login_generation.get(platform) != generation:
            return
        if platform == "patreon":
            self._on_patreon_cookie(payload)
        elif platform == "fanbox":
            self._on_fanbox_cookie(payload)
        elif platform == "fantia":
            self._on_fantia_session(payload)

    def _patreon_login_start(self):
        if ce := self.browser_cancel_events.get("patreon"):
            ce.set()
        self.browser_done_events["patreon"] = threading.Event()
        self.browser_cancel_events["patreon"] = threading.Event()
        self._browser_login_generation["patreon"] += 1
        _gen = self._browser_login_generation["patreon"]
        self._login_flow_active["patreon"] = True
        self.patreon_btn.setEnabled(False)
        self.patreon_done_btn.setEnabled(True)
        self.patreon_status.setText(tr("login.browser"))
        self.patreon_status.setStyleSheet(f"color: {PALETTE['warning']};")
        patreon_login(
            self.browser_done_events["patreon"],
            lambda s, g=_gen: self._browser_login_payload.emit("patreon", g, s),
            self.browser_cancel_events["patreon"],
        )

    def _patreon_login_done(self):
        if ev := self.browser_done_events.get("patreon"):
            ev.set()

    def _on_patreon_cookie(self, s):
        self.patreon_done_btn.setEnabled(False)
        if not self._login_flow_active.get("patreon"):
            self.patreon_btn.setEnabled(True)
            return
        self._login_flow_active["patreon"] = False
        if s:
            self.config.setdefault("patreon", {})["cookies"] = s
            save_config(self.config)
            self.patreon_status.setText(tr("settings.account.in"))
            self.patreon_status.setStyleSheet(f"color: {PALETTE['success']};")
            self.patreon_status.setToolTip("")
        else:
            self.patreon_status.setText(tr("login.missing"))
            self.patreon_status.setStyleSheet(f"color: {PALETTE['error']};")
            self.patreon_status.setToolTip(tr("login.tip.patreon"))
        self.patreon_btn.setEnabled(True)

    def _fanbox_login_start(self):
        if ce := self.browser_cancel_events.get("fanbox"):
            ce.set()
        self.browser_done_events["fanbox"] = threading.Event()
        self.browser_cancel_events["fanbox"] = threading.Event()
        self._browser_login_generation["fanbox"] += 1
        _gen = self._browser_login_generation["fanbox"]
        self._login_flow_active["fanbox"] = True
        self.fanbox_btn.setEnabled(False)
        self.fanbox_done_btn.setEnabled(True)
        self.fanbox_status.setText(tr("login.browser"))
        self.fanbox_status.setStyleSheet(f"color: {PALETTE['warning']};")
        fanbox_login(
            self.browser_done_events["fanbox"],
            lambda s, g=_gen: self._browser_login_payload.emit("fanbox", g, s),
            self.browser_cancel_events["fanbox"],
        )

    def _fanbox_login_done(self):
        if ev := self.browser_done_events.get("fanbox"):
            ev.set()

    def _on_fanbox_cookie(self, s):
        self.fanbox_done_btn.setEnabled(False)
        if not self._login_flow_active.get("fanbox"):
            self.fanbox_btn.setEnabled(True)
            return
        self._login_flow_active["fanbox"] = False
        if s:
            self.config.setdefault("fanbox", {})["cookies"] = s
            save_config(self.config)
            self.fanbox_status.setText(tr("settings.account.in"))
            self.fanbox_status.setStyleSheet(f"color: {PALETTE['success']};")
            self.fanbox_status.setToolTip("")
        else:
            self.fanbox_status.setText(tr("login.missing"))
            self.fanbox_status.setStyleSheet(f"color: {PALETTE['error']};")
            self.fanbox_status.setToolTip(tr("login.tip.fanbox"))
        self.fanbox_btn.setEnabled(True)

    def _fantia_login_start(self):
        if ce := self.browser_cancel_events.get("fantia"):
            ce.set()
        self.browser_done_events["fantia"] = threading.Event()
        self.browser_cancel_events["fantia"] = threading.Event()
        self._browser_login_generation["fantia"] += 1
        _gen = self._browser_login_generation["fantia"]
        self._login_flow_active["fantia"] = True
        self.fantia_btn.setEnabled(False)
        self.fantia_done_btn.setEnabled(True)
        self.fantia_status.setText(tr("login.browser"))
        self.fantia_status.setStyleSheet(f"color: {PALETTE['warning']};")
        fantia_login(
            self.browser_done_events["fantia"],
            lambda s, g=_gen: self._browser_login_payload.emit("fantia", g, s),
            self.browser_cancel_events["fantia"],
        )

    def _fantia_login_done(self):
        if ev := self.browser_done_events.get("fantia"):
            ev.set()

    def _on_fantia_session(self, s):
        self.fantia_done_btn.setEnabled(False)
        if not self._login_flow_active.get("fantia"):
            self.fantia_btn.setEnabled(True)
            return
        self._login_flow_active["fantia"] = False
        if s:
            self.config.setdefault("fantia", {})["session_id"] = s
            save_config(self.config)
            self.fantia_status.setText(tr("settings.account.in"))
            self.fantia_status.setStyleSheet(f"color: {PALETTE['success']};")
            self.fantia_status.setToolTip("")
        else:
            self.fantia_status.setText(tr("login.missing"))
            self.fantia_status.setStyleSheet(f"color: {PALETTE['error']};")
            self.fantia_status.setToolTip(tr("login.tip.fantia"))
        self.fantia_btn.setEnabled(True)

def main():
    detach_windows_console_if_present()
    _cfg0 = load_config()
    if migrate_config_schedule_interval(_cfg0):
        save_config(_cfg0)
    set_language(effective_ui_language(_cfg0))
    _g = _cfg0.setdefault("gui", {})
    if _g.get("qt_theme") != "dark":
        _g["qt_theme"] = "dark"
        save_config(_cfg0)
    palette_apply()
    # Per-monitor DPI: avoid wrong logical size when moving windows between screens.
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    _ico0 = _app_icon_path()
    if _ico0 is not None:
        app.setWindowIcon(QIcon(str(_ico0)))
    app.setStyle("Fusion")
    _base = QFont()
    _base.setFamilies(list(FONT_FALLBACKS))
    _base.setPointSize(13)
    app.setFont(_base)
    app.setStyleSheet(_app_stylesheet())
    _sync_qapplication_palette()
    win = SponsorMainWindow()
    win.show()
    sys.exit(app.exec())
