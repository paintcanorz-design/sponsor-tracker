# -*- coding: utf-8 -*-
"""PySide6 main window: mirrors app_gui layout, settings, and behavior."""
from __future__ import annotations

import html
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
    QPoint,
    QRect,
    QDateTime,
    QMargins,
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
    QGuiApplication,
    QIcon,
    QPainter,
    QColor,
    QPalette,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
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
    QVBoxLayout,
    QWidget,
    QLayout,
)

from src.paths import project_root
from src.jst import month_start_jst_str, now_jst, today_jst_str, year_start_jst_str
from src.database import (
    clear_sponsorship_data,
    get_chart_combined_daily_between,
    init_db,
    save_record,
    update_daily_summary,
    get_dashboard_stats,
    get_period_comparison,
)
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

from src.qt_app.shared import (
    FONT_FALLBACKS,
    INCREASE_SOUND_PRESET_LABELS,
    PALETTE,
    palette_apply,
    _INCREASE_SOUND_KEY_TO_LABEL,
    _INCREASE_SOUND_LABEL_TO_KEY,
    detach_windows_console_if_present,
    load_config,
    parse_jst_hhmm,
    play_increase_sound,
    save_config,
    normalize_increase_sound_key,
)


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
    QFrame#headerSegment {{
        background-color: {c["segment_bg"]};
        border-radius: 10px; border: none;
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
        background-color: transparent;
    }}
    QWidget#compactPanel {{
        background-color: {c["bg_card"]};
        border: 1px solid {c["border_light"]};
        border-radius: 12px;
    }}
    QLabel {{
        color: {c["text"]} !important;
        background: transparent;
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
    """迷你�表：一般 Tool 視窗 + 系統標題列（由 OS ��理 DPI／拖曳／��放）。"""

    _PLAT_NAMES = {"patreon": "Patreon", "fanbox": "Fanbox", "fantia": "Fantia"}

    def __init__(self, app: SponsorMainWindow):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self._app = app
        self.setWindowTitle("\u8d0a\u52a9\u984d\u8ffd\u8e64 \u00b7 \u8ff7\u4f60\u5100\u8868")
        self.setMinimumWidth(260)
        self.setStyleSheet(_compact_window_stylesheet())
        self.setToolTip(
            "\u53f3\u9375\u958b\u555f\u9078\u55ae\uff08\u7f6e\u9802\u3001\u66f4\u65b0\u3001\u4e3b\u8996\u7a97\uff09"
            "\u3002\u96d9\u64ca\u7a97\u53e3\u958b\u555f\u4e3b\u8996\u7a97\u3002"
        )

        scr = QGuiApplication.primaryScreen()
        if scr is not None:
            g = scr.availableGeometry()
            self.move(g.right() - self.frameSize().width() - 20, g.top() + 20)

        self.setObjectName("compactRoot")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)

        panel = QWidget()
        panel.setObjectName("compactPanel")
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        panel.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        panel.customContextMenuRequested.connect(lambda p: self._show_compact_menu(panel, p))
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(10, 8, 10, 6)
        pl.setSpacing(0)

        row_total = QHBoxLayout()
        row_total.setSpacing(6)
        hl = QHBoxLayout()
        hl.setSpacing(5)
        self._total_lbl = QLabel("\u00a5\u2014")
        self._total_lbl.setFont(_qf(18, True))
        self._total_lbl.setStyleSheet(f"color: {PALETTE['text']} !important;")
        self._total_lbl.setMinimumHeight(0)
        self._total_lbl.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        hl.addWidget(self._total_lbl)
        self._inc_arrow_lbl = QLabel("")
        self._inc_arrow_lbl.setFont(_qf(11, True))
        self._inc_arrow_lbl.setStyleSheet(f"color: {PALETTE['success']} !important;")
        hl.addWidget(self._inc_arrow_lbl)
        hl.addStretch()
        row_total.addLayout(hl, 1)
        self._patron_lbl = QLabel("")
        self._patron_lbl.setFont(_qf(11))
        self._patron_lbl.setStyleSheet(f"color: {PALETTE['text_secondary']} !important;")
        self._patron_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row_total.addWidget(self._patron_lbl)
        pl.addLayout(row_total)

        self._increase_lbl = QLabel("")
        self._increase_lbl.setFont(_qf(10, True))
        self._increase_lbl.setStyleSheet(f"color: {PALETTE['success']} !important;")
        self._increase_lbl.setMinimumHeight(0)
        self._increase_lbl.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self._increase_lbl.hide()
        pl.addWidget(self._increase_lbl)

        pl.addSpacing(5)

        self.sep = QFrame()
        self.sep.setFixedHeight(1)
        self.sep.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.sep.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 transparent, stop:0.1 {PALETTE['border_light']},"
            f"stop:0.9 {PALETTE['border_light']}, stop:1 transparent);"
            f"border:none; max-height:1px;"
        )
        pl.addWidget(self.sep)
        pl.addSpacing(4)

        platform_host = QWidget()
        platform_host.setMinimumHeight(48)
        platform_host.setMaximumHeight(72)
        platform_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        plat_row = QGridLayout(platform_host)
        plat_row.setContentsMargins(0, 0, 0, 2)
        plat_row.setHorizontalSpacing(8)
        plat_row.setVerticalSpacing(0)
        plat_row.setColumnStretch(0, 1)
        plat_row.setColumnStretch(1, 1)
        plat_row.setColumnStretch(2, 1)
        plat_row.setRowMinimumHeight(0, 44)
        self._plat_cells: list[QLabel] = []
        for i in range(3):
            lbl = QLabel()
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setWordWrap(False)
            lbl.setMinimumHeight(42)
            lbl.setMaximumHeight(70)
            lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
            lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            plat_row.addWidget(lbl, 0, i, Qt.AlignmentFlag.AlignTop)
            self._plat_cells.append(lbl)
        pl.addWidget(platform_host)

        root.addWidget(panel, 0, Qt.AlignmentFlag.AlignTop)

        for _cw in [panel] + panel.findChildren(QWidget):
            _cw.installEventFilter(self)

        self._indicator_timer = QTimer(self)
        self._indicator_timer.timeout.connect(self._update_indicator)
        self._indicator_timer.start(30_000)

        self.refresh()
        self._shrink_compact_window()

    def _shrink_compact_window(self) -> None:
        """Resize window to layout sizeHint so no empty client area below the card."""
        lay = self.layout()
        if lay is not None:
            lay.activate()
        self.adjustSize()
        QTimer.singleShot(0, self.adjustSize)

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

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.MouseButtonDblClick:
            self._expand()
            return True
        return super().eventFilter(watched, event)

    def _show_compact_menu(self, host: QWidget, pos: QPoint):
        menu = QMenu(self)
        act_top = QAction("\u7f6e\u9802", self)
        act_top.setCheckable(True)
        act_top.setChecked(bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint))
        act_top.toggled.connect(self._on_topmost_toggled)
        menu.addAction(act_top)
        act_up = QAction("\u7acb\u5373\u66f4\u65b0\u6578\u64da", self)
        act_up.triggered.connect(self._app._run_update)
        menu.addAction(act_up)
        act_main = QAction("\u958b\u555f\u4e3b\u8996\u7a97", self)
        act_main.triggered.connect(self._expand)
        menu.addAction(act_main)
        menu.exec(host.mapToGlobal(pos))

    def _on_topmost_toggled(self, on: bool):
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, bool(on))
        self.show()

    def refresh(self, stats: dict | None = None):
        self._total_lbl.setStyleSheet(f"color: {PALETTE['text']} !important;")
        self._inc_arrow_lbl.setStyleSheet(f"color: {PALETTE['success']} !important;")
        self._patron_lbl.setStyleSheet(f"color: {PALETTE['text_secondary']} !important;")
        self._increase_lbl.setStyleSheet(f"color: {PALETTE['success']} !important;")
        self.sep.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 transparent, stop:0.1 {PALETTE['border_light']},"
            f"stop:0.9 {PALETTE['border_light']}, stop:1 transparent);"
            f"border:none; max-height:1px;"
        )
        if stats is None:
            try:
                s = get_dashboard_stats()
            except Exception:
                return
        else:
            s = stats
        total = s.get("total_amount") or 0
        patrons = s.get("total_patron_count") or 0
        self._total_lbl.setText(f"\u00a5{total:,.0f}")
        self._patron_lbl.setText(f"{patrons} \u4eba")
        rate = float(s.get("fx_usd_jpy") or 150)
        platforms = s.get("by_platform") or []
        tc = PALETTE["text"]
        tct = PALETTE["text_tertiary"]
        tcs = PALETTE["text_secondary"]
        for i, lbl in enumerate(self._plat_cells):
            if i < len(platforms):
                p = platforms[i]
                plat = p.get("platform") or ""
                amt = float(p.get("amount") or 0)
                cur = (p.get("currency") or "JPY").upper()
                if plat == "patreon" and cur == "USD":
                    amt *= rate
                color = {
                    "patreon": PALETTE["patreon"],
                    "fanbox": PALETTE["fanbox"],
                    "fantia": PALETTE["fantia"],
                }.get(plat, PALETTE["accent"])
                name = self._PLAT_NAMES.get(plat, plat)
                name_esc = html.escape(name)
                line1 = (
                    f"<span style='color:{color}; font-weight:600; font-size:10px; "
                    f"letter-spacing:0.2px'>\u25cf {name_esc}</span>"
                )
                line2 = (
                    f"<span style='color:{tc}; font-weight:700; font-size:15px; "
                    f"letter-spacing:-0.4px'>\u00a5{amt:,.0f}</span>"
                    f"<span style='color:{tcs}; font-weight:600; font-size:12px'>"
                    f"&nbsp;&nbsp;{int(p.get('patron_count') or 0)} \u4eba</span>"
                )
                lbl.setText(line1 + "<br>" + line2)
            else:
                lbl.setText(f"<span style='color:{tct}'>\u2014</span>")
        inc_this = getattr(self._app, "_last_update_increase", None) or 0
        if inc_this > 0:
            self._increase_lbl.setText(f"\u25b2 +\u00a5{inc_this:,.0f}")
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
    _browser_login_payload = Signal(str, str)
    # \u80cc\u666f\u57f7\u7dd2\u5b8c\u6210\u8cc7\u6599\u64f7\u53d6\u5f8c\u6392\u968a\u56de\u4e3b\u57f7\u7dd2\uff08\u4e0d\u7528 QTimer.singleShot\uff09
    _manual_update_done = Signal(object, bool)
    _manual_update_failed = Signal(str)
    _dashboard_data_ready = Signal(int, object, object, bool, object)
    _oneclick_check_done = Signal(object)
    _oneclick_dl_done = Signal(object)
    _oneclick_dl_progress = Signal(int, int)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("\u8d0a\u52a9\u984d\u8ffd\u8e64")
        _ico = _app_icon_path()
        if _ico is not None:
            self.setWindowIcon(QIcon(str(_ico)))
        self.resize(1240, 820)
        self.setMinimumSize(980, 700)

        self.config = load_config()
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
        self._stack: QStackedWidget | None = None
        self._btn_settings_nav: QPushButton | None = None
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

        init_db()
        self._build_ui()
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
        self._tray.setToolTip("\u8d0a\u52a9\u984d\u8ffd\u8e64")
        menu = QMenu()
        self._tray_menu = menu
        act_show = QAction("\u986f\u793a\u4e3b\u8996\u7a97", self)
        act_show.triggered.connect(self._tray_show_main)
        menu.addAction(act_show)
        menu.addSeparator()
        self._act_compact = QAction("\u8ff7\u4f60\u76e3\u63a7\u7a97", self)
        self._act_compact.setCheckable(True)
        self._act_compact.triggered.connect(self._tray_toggle_compact)
        menu.addAction(self._act_compact)
        self._act_top = QAction("\u4e3b\u8996\u7a97\u7f6e\u9802", self)
        self._act_top.setCheckable(True)
        self._act_top.triggered.connect(self._toggle_topmost)
        menu.addAction(self._act_top)
        menu.addSeparator()
        self._act_mute = QAction("\u975c\u97f3\uff08\u901a\u77e5\u97f3\u6548\uff09", self)
        self._act_mute.setCheckable(True)
        self._act_mute.triggered.connect(self._tray_toggle_mute)
        menu.addAction(self._act_mute)
        act_up = QAction("\u7acb\u5373\u66f4\u65b0\u6578\u64da", self)
        act_up.triggered.connect(self._run_update)
        menu.addAction(act_up)
        act_copy = QAction("\u8907\u88fd\u76ee\u524d\u7e3d\u91d1\u984d", self)
        act_copy.triggered.connect(self._copy_dashboard_total_to_clipboard)
        menu.addAction(act_copy)
        menu.addSeparator()
        act_restart = QAction("\u91cd\u555f\u7a0b\u5f0f", self)
        act_restart.triggered.connect(self._restart_application)
        menu.addAction(act_restart)
        act_quit = QAction("\u7d50\u675f", self)
        act_quit.triggered.connect(self._quit_fully)
        menu.addAction(act_quit)
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
            if self._btn_settings_nav is not None:
                self._btn_settings_nav.setText("\u8a2d\u5b9a")
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
            s = get_dashboard_stats()
            total = float(s.get("total_amount") or 0)
            text = f"\u00a5{total:,.0f}"
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
        t1 = QLabel("\u8d0a\u52a9\u984d\u8ffd\u8e64")
        t1.setObjectName("appTitle")
        t2 = QLabel("Patreon \u00b7 Fanbox \u00b7 Fantia")
        t2.setObjectName("appSubtitle")
        title_block.addWidget(t1)
        title_block.addWidget(t2)
        hl.addLayout(title_block)
        hl.addStretch()
        seg = QFrame()
        seg.setObjectName("headerSegment")
        seg.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        seg_l = QHBoxLayout(seg)
        seg_l.setContentsMargins(4, 4, 4, 4)
        seg_l.setSpacing(3)
        self._pin_btn = QPushButton("\u7f6e\u9802")
        self._pin_btn.setObjectName("headerPill")
        self._pin_btn.clicked.connect(self._toggle_topmost)
        seg_l.addWidget(self._pin_btn)
        mini = QPushButton("\u8ff7\u4f60\u5100\u8868")
        mini.setObjectName("headerPill")
        mini.clicked.connect(self._show_compact)
        seg_l.addWidget(mini)
        self._btn_settings_nav = QPushButton("\u8a2d\u5b9a")
        self._btn_settings_nav.setObjectName("headerPill")
        self._btn_settings_nav.clicked.connect(self._toggle_settings_view)
        seg_l.addWidget(self._btn_settings_nav)
        hl.addWidget(seg)
        root.addWidget(header)

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
        dash_title = QLabel("\u7d93\u71df\u7e3d\u89bd")
        dash_title.setObjectName("pageHeadline")
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
        plat_title = QLabel("\u5404\u5e73\u53f0\u6578\u64da")
        plat_title.setObjectName("platSectionLabel")
        plat_hdr.addWidget(plat_title)
        bl.addLayout(plat_hdr)
        self._dash_platforms = QWidget()
        self._dash_platforms.setMinimumHeight(102)
        self._dash_plat_grid = QGridLayout(self._dash_platforms)
        self._dash_plat_grid.setSpacing(10)
        bl.addWidget(self._dash_platforms)

        self._build_trend_section(bl, page_dash)

        bl.addStretch(1)

        page_set = QWidget()
        page_set.setObjectName("pageSettings")
        page_set.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        page_set.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        psl = QVBoxLayout(page_set)
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
        self._settings_inner = content
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
        self._build_settings_scroll_content(left_col, right_col)
        scroll.setWidget(content)
        psl.addWidget(scroll, 1)

        self._stack.addWidget(page_dash)
        self._stack.addWidget(page_set)
        root.addWidget(self._stack, 1)

        self._init_dashboard_layout()
        self._bootstrap_dashboard_sync()
        self._refresh_dashboard()
        self._stack.setCurrentIndex(0)

    def _toggle_topmost(self):
        self._is_topmost = not self._is_topmost
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self._is_topmost)
        self.show()
        if self._is_topmost:
            self._pin_btn.setStyleSheet(
                f"background-color: {PALETTE['accent']}; color: #ffffff; border: none; "
                f"border-radius: 8px; font-weight: 600;"
            )
        else:
            self._pin_btn.setStyleSheet("")

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

    def _toggle_settings_view(self):
        if self._stack is None or self._btn_settings_nav is None:
            return
        if self._stack.currentIndex() == 0:
            self._stack.setCurrentIndex(1)
            self._btn_settings_nav.setText("\u56de\u7e3d\u89bd")
        else:
            self._stack.setCurrentIndex(0)
            self._btn_settings_nav.setText("\u8a2d\u5b9a")

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
        self._plat_empty_lbl = QLabel(
            "\u5c1a\u7121\u6578\u64da\n\u8acb\u5148\u958b\u555f\u53f3\u4e0a\u89d2\u300c\u8a2d\u5b9a\u300d\u767b\u5165\u4e26\u6293\u53d6\u8cc7\u6599"
        )
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
        trend_title = QLabel("\u5408\u8a08\u91d1\u984d\u8da8\u52e2")
        trend_title.setObjectName("platSectionLabel")
        hdr = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        title_col.addWidget(trend_title)
        hdr.addLayout(title_col, 1)
        self._trend_range_combo = QComboBox()
        self._trend_range_combo.addItem("\u672c\u6708", "month")
        self._trend_range_combo.addItem("\u672c\u5e74", "year")
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
        mode = combo.currentData() if combo is not None else "month"
        if mode not in ("month", "year"):
            mode = "month"
        end = today_jst_str()
        start = year_start_jst_str() if mode == "year" else month_start_jst_str()
        try:
            data = get_chart_combined_daily_between(start, end)
        except Exception:
            data = []
        for s in list(chart.series()):
            chart.removeSeries(s)
        for ax in list(chart.axes()):
            chart.removeAxis(ax)
        series = QLineSeries()
        for date_str, amt, _ in data:
            dt = QDateTime.fromString(f"{date_str} 12:00:00", "yyyy-MM-dd HH:mm:ss")
            if not dt.isValid():
                continue
            series.append(float(dt.toMSecsSinceEpoch()), float(amt))
        pen = QPen(QColor(PALETTE["accent"]))
        pen.setWidthF(2.5)
        series.setPen(pen)
        chart.addSeries(series)
        axis_x = QDateTimeAxis()
        axis_x.setFormat("M/d" if mode == "month" else "M/d")
        axis_x.setLabelsColor(QColor(PALETTE["text_secondary"]))
        axis_x.setGridLineColor(QColor(PALETTE["hairline"]))
        if data:
            d0 = QDateTime.fromString(f"{data[0][0]} 12:00:00", "yyyy-MM-dd HH:mm:ss")
            d1 = QDateTime.fromString(f"{data[-1][0]} 12:00:00", "yyyy-MM-dd HH:mm:ss")
            if d0.isValid() and d1.isValid():
                axis_x.setRange(d0, d1)
        axis_y = QValueAxis()
        axis_y.setLabelsColor(QColor(PALETTE["text_secondary"]))
        axis_y.setGridLineColor(QColor(PALETTE["hairline"]))
        if data:
            ys = [float(row[1]) for row in data]
            lo, hi = min(ys), max(ys)
            span = max(hi - lo, abs(hi) * 0.02, 500.0)
            axis_y.setRange(lo - span * 0.08, hi + span * 0.12)
        else:
            axis_y.setRange(0, 1)
        axis_y.setLabelFormat("%.0f")
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
            n = len(data)
            axis_x.setTickCount(min(12, max(4, min(n, 12) or 4)))

    def _bootstrap_dashboard_sync(self) -> None:
        try:
            s = get_dashboard_stats()
            p = get_period_comparison(7)
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
                period = get_period_comparison(7)
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
            period = get_period_comparison(7)
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
            sub_parts.append("\u5148\u57f7\u884c\u66f4\u65b0")
        if inc_this > 0:
            sub_parts.append(f"\u672c\u6b21\u66f4\u65b0 +\u00a5{inc_this:,.0f}")
        sub_total = "\n".join(sub_parts)
        h0["title"].setText("\u7e3d\u6536\u76ca")
        h0["title"].setStyleSheet(
            f"color: {PALETTE['text_secondary']} !important; letter-spacing: 0.5px; font-weight: 600; font-size: 12px;"
        )
        h0["value"].setText(f"\u00a5{total:,.0f}")
        h0["value"].setStyleSheet(f"color: {PALETTE['text']} !important; letter-spacing: -0.5px;")
        h0["sub"].setText(sub_total)
        h0["sub"].setStyleSheet(f"color: {PALETTE['text_secondary']} !important;")

        patrons = s.get("total_patron_count") or 0
        pch = s.get("patron_change")
        h1["title"].setText("\u8d0a\u52a9\u4eba\u6578")
        h1["title"].setStyleSheet(
            f"color: {PALETTE['text_secondary']} !important; letter-spacing: 0.5px; font-weight: 600; font-size: 12px;"
        )
        h1["value"].setText(f"{patrons} \u4eba")
        h1["value"].setStyleSheet(f"color: {PALETTE['text']} !important;")
        h1["sub"].setText(f"\u8f03\u6628\u65e5 {pch:+d} \u4eba" if pch is not None else "")
        h1["sub"].setStyleSheet(
            f"color: {PALETTE['success'] if (pch or 0) >= 0 else PALETTE['error']} !important;"
        )

        h2["title"].setText("\u672c\u9031\u8f03\u4e0a\u9031")
        h2["title"].setStyleSheet(
            f"color: {PALETTE['text_secondary']} !important; letter-spacing: 0.5px; font-weight: 600; font-size: 12px;"
        )
        if period:
            c2, pct2 = period["change_amount"], period["change_percent"]
            v2 = f"\u00a5{c2:+,.0f}" + (f" ({pct2:+.1f}%)" if pct2 is not None else "")
            h2["value"].setText(v2)
            if (c2 or 0) > 0:
                c2_col = PALETTE["success"]
            elif (c2 or 0) < 0:
                c2_col = PALETTE["error"]
            else:
                c2_col = PALETTE["text_tertiary"]
            h2["value"].setStyleSheet(f"color: {c2_col} !important;")
            h2["sub"].setText(f"\u8fd1{period['days']}\u5929 vs \u524d{period['days']}\u5929")
        else:
            h2["value"].setText("\u2014")
            h2["value"].setStyleSheet(f"color: {PALETTE['text_tertiary']} !important;")
            h2["sub"].setText("")
        h2["sub"].setStyleSheet(f"color: {PALETTE['text_secondary']} !important;")

        h3["title"].setText("\u8f03\u6628\u65e5\u91d1\u984d")
        h3["title"].setStyleSheet(
            f"color: {PALETTE['text_secondary']} !important; letter-spacing: 0.5px; font-weight: 600; font-size: 12px;"
        )
        if ch is not None:
            pct_s = f" ({pct:+.1f}%)" if pct is not None else ""
            h3["value"].setText(f"\u00a5{ch:+,.0f}{pct_s}")
            if (ch or 0) > 0:
                ch_col = PALETTE["success"]
            elif (ch or 0) < 0:
                ch_col = PALETTE["error"]
            else:
                ch_col = PALETTE["text_tertiary"]
            h3["value"].setStyleSheet(f"color: {ch_col} !important;")
            h3["sub"].setText("\u7e3d\u984d\u8f03\u6628\u65e5")
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
                    cell["amount"].setText(f"{amt:,.0f} {cur}")
                    cell["amount"].setStyleSheet(f"color: {PALETTE['text']} !important;")
                    pc = int(p.get("patron_count") or 0)
                    cell["patron"].setText(f"{pc} \u4eba")
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
        interval = gui.get("schedule_interval")
        opts = ["15 \u5206\u9418", "30 \u5206\u9418", "1 \u5c0f\u6642", "2 \u5c0f\u6642", "4 \u5c0f\u6642"]
        if interval and interval in opts and hasattr(self, "_sched_interval"):
            self._sched_interval.setCurrentText(interval)
        if gui.get("schedule_auto_start") and not self._schedule_running:
            self._start_schedule()

    def _save_schedule_preferences(self, running: bool):
        self.config = load_config()
        self.config.setdefault("gui", {})["schedule_interval"] = self._sched_interval.currentText()
        self.config.setdefault("gui", {})["schedule_auto_start"] = running
        save_config(self.config)

    def _on_schedule_interval_changed(self, _t=None):
        self.config = load_config()
        self.config.setdefault("gui", {})["schedule_interval"] = self._sched_interval.currentText()
        save_config(self.config)

    def _toggle_schedule(self):
        if self._schedule_running:
            self._stop_schedule()
        else:
            self._start_schedule()

    def _start_schedule(self):
        import schedule as sched_mod

        interval_map = {
            "15 \u5206\u9418": 15,
            "30 \u5206\u9418": 30,
            "1 \u5c0f\u6642": 60,
            "2 \u5c0f\u6642": 120,
            "4 \u5c0f\u6642": 240,
        }
        minutes = interval_map.get(self._sched_interval.currentText(), 60)
        sched_mod.clear()
        sched_mod.every(minutes).minutes.do(lambda: self._run_update(True))
        self._schedule_running = True
        self._sched_btn.setText("\u505c\u6b62\u6392\u7a0b")
        self._sched_btn.setObjectName("danger")
        self._sched_btn.setStyleSheet(
            f"background-color: {PALETTE['error']}; color: #ffffff; border: none; "
            f"border-radius: 8px; font-weight: 600;"
        )
        self._sched_interval.setEnabled(False)
        self.update_status.setText(f"\u6392\u7a0b\u555f\u52d5\u4e2d\uff08\u6bcf {self._sched_interval.currentText()}\uff09")
        self.update_status.setStyleSheet(f"color: {PALETTE['success']};")
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
        self._sched_btn.setText("\u555f\u52d5\u6392\u7a0b")
        self._sched_btn.setObjectName("success")
        self._sched_btn.setStyleSheet(
            f"background-color: {PALETTE['success']}; color: #ffffff; border: none; "
            f"border-radius: 8px; font-weight: 600;"
        )
        self._sched_interval.setEnabled(True)
        self.update_status.setText("\u6392\u7a0b\u5df2\u505c\u6b62")
        self.update_status.setStyleSheet(f"color: {PALETTE['text_tertiary']};")
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

        def do():
            try:
                self.config = load_config()
                results = {}
                cfg = self.config

                def fetch_patreon():
                    pc = cfg.get("patreon", {})
                    if not pc.get("cookies"):
                        return ("patreon", None, None)
                    try:
                        url = pc.get("creator_page") or "https://www.patreon.com/c/user"
                        d = PatreonFetcher(pc["cookies"], url).fetch_sponsorship()
                        return ("patreon", d, "\u7121\u6cd5\u53d6\u5f97\u6578\u64da" if not d else None)
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
                        return ("fanbox", None, "\u6578\u64da\u7570\u5e38" if d else "\u7121\u6cd5\u53d6\u5f97\u6578\u64da")
                    except Exception as ex:
                        return ("fanbox", None, str(ex))

                def fetch_fantia():
                    fic = cfg.get("fantia", {})
                    if not fic.get("session_id"):
                        return ("fantia", None, None)
                    try:
                        d = FantiaFetcher(fic["session_id"]).fetch_sponsorship()
                        return ("fantia", d, "\u7121\u6cd5\u53d6\u5f97\u6578\u64da" if not d else None)
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
        self._last_update_lbl.setText(f"\u66f4\u65b0 {now_jst():%H:%M} JST")
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
                        msg = format_scheduled_increase_message(
                            time_jst=f"{now_jst():%Y-%m-%d %H:%M} JST",
                            new_total_jpy=float(new_total),
                            prev_total_jpy=float(prev),
                            increase_jpy=float(increase_this_update),
                            platform_before=dict(platform_before),
                            by_platform=s.get("by_platform") or [],
                            fx_usd_jpy=s.get("fx_usd_jpy"),
                        )

                        def _send_hook():
                            post_discord_webhook(url, msg)

                        threading.Thread(target=_send_hook, daemon=True).start()
                except Exception:
                    pass
        except Exception:
            self._last_update_increase = None
        if s is not None:
            self._apply_dashboard_ui_immediate(s)
        else:
            self._refresh_dashboard()

    def _update_fail(self, msg):
        self.update_btn.setEnabled(True)
        QMessageBox.critical(self, "\u66f4\u65b0\u5931\u6557", msg or "\u672a\u77e5\u932f\u8aa4")

    def _msgbox_version_check_new_release(self, latest: str, ver_local: str) -> bool:
        """\u767c\u73fe\u8f03\u65b0\u7248\u672c\u6642\u8a62\u554f\u662f\u5426\u524d\u5f80\u4e0b\u8f09\u3002\u56de\u50b3 True \u8868\u793a\u958b\u555f\u700f\u89bd\u5668\u3002"""
        mb = QMessageBox(self)
        mb.setWindowTitle("\u7248\u672c\u6aa2\u67e5")
        mb.setIcon(QMessageBox.Icon.Question)
        mb.setText(
            f"\u767c\u73fe\u8f03\u65b0\u7684\u767c\u884c\u7248\u672c\uff1a<b>{html.escape(latest)}</b>"
        )
        mb.setTextFormat(Qt.TextFormat.RichText)
        mb.setInformativeText(
            f"\u60a8\u6b64\u8655\u986f\u793a\u7684\u7248\u672c\u7de8\u865f\u70ba\uff1a{html.escape(ver_local)}\n\n"
            "\u662f\u5426\u958b\u555f\u700f\u89bd\u5668\u524d\u5f80 GitHub Release \u4e0b\u8f09\u9801\u9762\uff1f"
        )
        btn_dl = mb.addButton("\u524d\u5f80\u4e0b\u8f09", QMessageBox.ButtonRole.AcceptRole)
        mb.addButton("\u7a0d\u5f8c\u518d\u8aaa", QMessageBox.ButtonRole.RejectRole)
        mb.setDefaultButton(btn_dl)
        mb.exec()
        return mb.clickedButton() == btn_dl

    def _msgbox_version_check_uptodate(self, latest: str, ver_local: str) -> None:
        mb = QMessageBox(self)
        mb.setWindowTitle("\u7248\u672c\u6aa2\u67e5")
        mb.setIcon(QMessageBox.Icon.Information)
        mb.setText("\u5df2\u70ba\u6700\u65b0\u7248\u672c")
        mb.setInformativeText(
            f"\u60a8\u4f7f\u7528\u7684\u7a0b\u5f0f\u7248\u672c\u5df2\u8207 GitHub \u4e0a\u6700\u65b0 Release \u4e00\u81f4\uff0c\u7121\u9700\u66f4\u65b0\u3002\n\n"
            f"\u76ee\u524d\u7248\u672c\uff1a{ver_local}\n"
            f"\u7dda\u4e0a\u6a19\u7c64\uff1a{latest}"
        )
        mb.setStandardButtons(QMessageBox.StandardButton.Ok)
        mb.exec()

    def _on_update_check_worker_done(self, payload: object) -> None:
        """\u5728\u4e3b\u57f7\u7dd2\u57f7\u884c\uff08\u7531 Signal \u6392\u968a\u9001\u905e\uff09\u3002"""
        self._app_update_busy = False
        self._app_update_btn.setEnabled(True)
        if not isinstance(payload, dict):
            QMessageBox.critical(
                self,
                "\u7248\u672c\u6aa2\u67e5",
                f"\u5167\u90e8\u932f\u8aa4\uff08\u7121\u6548\u8f38\u51fa\uff09\uff1a{payload!r}",
            )
            return
        if payload.get("exc"):
            detail = (payload.get("trace") or payload.get("exc") or "").strip()
            QMessageBox.critical(
                self,
                "\u7248\u672c\u6aa2\u67e5",
                f"\u6aa2\u67e5\u6642\u767c\u751f\u932f\u8aa4\uff1a\n{detail}",
            )
            return

        has_git = bool(payload.get("has_git"))
        repo = str(payload.get("repo") or "")
        git_ok = payload.get("git_ok")
        git_msg = str(payload.get("git_msg") or "")
        latest = payload.get("latest")
        api_err = payload.get("api_err")

        self._app_version_label.setText(f"\u76ee\u524d\u7248\u672c\uff1a {current_app_version()}")
        ver_local = current_app_version()

        if has_git:
            if git_ok:
                box = QMessageBox(self)
                box.setWindowTitle("\u539f\u59cb\u78bc\u540c\u6b65")
                box.setIcon(QMessageBox.Icon.Information)
                box.setText(
                    "\u7a0b\u5f0f\u539f\u59cb\u78bc\u5df2\u8207\u7dda\u4e0a\u5009\u5eab\u540c\u6b65\u3002\n"
                    "\uff08\u82e5\u7121\u65b0\u7248\u672c\uff0c\u8868\u793a\u60a8\u5df2\u4f7f\u7528\u6700\u65b0\u5167\u5bb9\u3002\uff09"
                )
                box.exec()
            else:
                QMessageBox.critical(self, "\u539f\u59cb\u78bc\u540c\u6b65", git_msg)

        if not repo:
            if not has_git:
                mb = QMessageBox(self)
                mb.setWindowTitle("\u7248\u672c\u6aa2\u67e5")
                mb.setIcon(QMessageBox.Icon.Warning)
                mb.setText("\u7121\u6cd5\u6aa2\u67e5\u66f4\u65b0")
                mb.setInformativeText(
                    "\u672a\u8a2d\u5b9a\u66f4\u65b0\u4f86\u6e90\uff0c\u6216\u672a\u4ee5 git \u53d6\u5f97\u5c08\u6848\u3002\n"
                    "\u8acb\u806f\u7e6b\u767c\u884c\u65b9\u6216\u7dad\u8b77\u8005\u53d6\u5f97\u66f4\u65b0\u65b9\u5f0f\u3002"
                )
                mb.setStandardButtons(QMessageBox.StandardButton.Ok)
                mb.exec()
            return

        if latest is None:
            mb = QMessageBox(self)
            mb.setWindowTitle("\u7248\u672c\u6aa2\u67e5")
            mb.setIcon(QMessageBox.Icon.Warning)
            mb.setText("\u7121\u6cd5\u6bd4\u5c0d\u767c\u884c\u7248\u672c")
            detail = (api_err or "").strip() or "\u7121\u6cd5\u9023\u7dda\u81f3 GitHub\u3002"
            mb.setInformativeText(
                f"{detail}\n\n"
                "\u82e5\u5009\u5eab\u5c1a\u672a\u5efa\u7acb Release\uff0c\u5c07\u7121\u6cd5\u6bd4\u5c0d\u7248\u672c\u865f\u3002"
            )
            mb.setStandardButtons(QMessageBox.StandardButton.Ok)
            mb.exec()
            return

        if version_newer_than(str(latest), ver_local):
            if self._msgbox_version_check_new_release(str(latest), ver_local):
                QDesktopServices.openUrl(QUrl(releases_latest_url(repo)))
        else:
            self._msgbox_version_check_uptodate(str(latest), ver_local)

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
                "\u4e00\u9375\u66f4\u65b0",
                "\u50c5\u9069\u7528\u65bc Windows \u4e0b\u4f7f\u7528\u514d\u5b89\u88dd exe \u6642\u3002",
            )
            return
        repo = configured_github_repo()
        if not repo:
            QMessageBox.warning(
                self,
                "\u4e00\u9375\u66f4\u65b0",
                "\u672a\u8a2d\u5b9a GitHub \u5009\u5eab\uff08src/version.py GITHUB_REPO\uff09\u3002",
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
                self._oneclick_check_done.emit({"ok": False, "error": "\u7121\u6548\u7684\u66f4\u65b0\u8cc7\u8a0a\u3002"})
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
                "\u4e00\u9375\u66f4\u65b0",
                str(payload.get("error") or "\u672a\u77e5\u932f\u8aa4"),
            )
            return
        if payload.get("uptodate"):
            self._oneclick_busy = False
            self._app_oneclick_btn.setEnabled(True)
            QMessageBox.information(
                self,
                "\u4e00\u9375\u66f4\u65b0",
                f"\u5df2\u662f\u6700\u65b0\u7248\u672c\uff08{str(payload.get('latest') or '')}\uff09\u3002",
            )
            return
        plan = payload.get("plan")
        if not isinstance(plan, dict):
            self._oneclick_busy = False
            self._app_oneclick_btn.setEnabled(True)
            return
        latest = str(plan.get("latest") or "")
        size = int(plan.get("size") or 0)
        size_txt = f"\u7d04 {size / (1024 * 1024):.1f} MB" if size > 0 else "\u5927\u5c0f\u672a\u77e5"
        q = QMessageBox.question(
            self,
            "\u4e00\u9375\u66f4\u65b0",
            f"\u5075\u6e2c\u5230\u65b0\u7248\u672c\uff1a{latest}\uff08{size_txt}\uff09\u3002\n\n"
            f"\u5c07\u4e0b\u8f09\u4e26\u8986\u5beb\u7a0b\u5f0f\u6a94\u6848\uff0c\u60a8\u7684\u8a2d\u5b9a\uff08config.yaml \u8207\u8cc7\u6599\u5eab\uff09\u6703\u4fdd\u7559\u3002\n"
            f"\u7a0b\u5f0f\u5c07\u95dc\u9589\u5f8c\u81ea\u52d5\u5b8c\u6210\u4e26\u91cd\u958b\u3002\n\n"
            f"\u662f\u5426\u7e7c\u7e8c\uff1f",
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
            QMessageBox.warning(self, "\u4e00\u9375\u66f4\u65b0", "\u7121\u4e0b\u8f09\u7db2\u5740\u3002")
            return
        self._oneclick_prog = QProgressDialog(
            "\u4e0b\u8f09\u66f4\u65b0\u4e2d\u2026",
            None,
            0,
            100,
            self,
        )
        self._oneclick_prog.setWindowTitle("\u4e00\u9375\u66f4\u65b0")
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
                "\u4e00\u9375\u66f4\u65b0",
                str((payload or {}).get("error") or "\u4e0b\u8f09\u5931\u6557"),
            )
            return
        staging_s = str(payload.get("staging") or "").strip()
        work_s = str(payload.get("work_root") or "").strip()
        if not staging_s or not work_s:
            QMessageBox.critical(self, "\u4e00\u9375\u66f4\u65b0", "\u5167\u90e8\u8def\u5f91\u7121\u6548\u3002")
            return
        QMessageBox.information(
            self,
            "\u4e00\u9375\u66f4\u65b0",
            "\u4e0b\u8f09\u5b8c\u6210\u3002\u6309\u300c\u78ba\u5b9a\u300d\u5f8c\u5c07\u95dc\u9589\u7a0b\u5f0f\u4e26\u5957\u7528\u66f4\u65b0\uff0c\u7136\u5f8c\u81ea\u52d5\u91cd\u958b\u3002",
        )
        ok, msg = spawn_lazy_windows_updater(Path(staging_s), Path(work_s))
        if not ok:
            QMessageBox.critical(self, "\u4e00\u9375\u66f4\u65b0", msg or "\u7121\u6cd5\u555f\u52d5\u66f4\u65b0\u52a9\u624b")
            return
        self._quit_fully()

    @staticmethod
    def _switch_is_on(checked: bool) -> bool:
        return bool(checked)

    def _add_settings_group(
        self, column: QVBoxLayout, title: str, blurb: str | None = None
    ) -> None:
        t = QLabel(title)
        t.setObjectName("settingsHeadline")
        column.addWidget(t)
        if blurb:
            b = QLabel(blurb)
            b.setObjectName("settingsBlurb")
            b.setWordWrap(True)
            column.addWidget(b)

    def _build_settings_scroll_content(self, left: QVBoxLayout, right: QVBoxLayout):
        inner = getattr(self, "_settings_inner", None)
        card_parent = inner if inner is not None else self
        gui_sound = self.config.get("gui") or {}

        self._add_settings_group(left, "\u66f4\u65b0\u8207\u6392\u7a0b")
        sync_card = _make_settings_group_card(card_parent)
        sl = QVBoxLayout(sync_card)
        sl.setContentsMargins(14, 12, 14, 12)
        sl.setSpacing(10)
        self.update_btn = QPushButton("\u6293\u53d6\u8d0a\u52a9\u6578\u64da")
        self.update_btn.setObjectName("primary")
        self.update_btn.clicked.connect(self._run_update)
        self.update_btn.setMinimumHeight(38)
        self._sched_btn = QPushButton("\u555f\u52d5\u6392\u7a0b")
        self._sched_btn.setObjectName("success")
        self._sched_btn.setMinimumHeight(38)
        self._sched_btn.clicked.connect(self._toggle_schedule)
        row_sync = QHBoxLayout()
        row_sync.setSpacing(8)
        row_sync.addWidget(self.update_btn, 1)
        row_sync.addWidget(self._sched_btn, 1)
        sl.addLayout(row_sync)
        row_iv = QHBoxLayout()
        row_iv.addWidget(_settings_form_label("\u6392\u7a0b\u9593\u9694"), 0)
        self._sched_interval = QComboBox()
        for v in ["15 \u5206\u9418", "30 \u5206\u9418", "1 \u5c0f\u6642", "2 \u5c0f\u6642", "4 \u5c0f\u6642"]:
            self._sched_interval.addItem(v)
        self._sched_interval.setCurrentText("1 \u5c0f\u6642")
        self._sched_interval.currentTextChanged.connect(self._on_schedule_interval_changed)
        row_iv.addWidget(self._sched_interval, 1)
        sl.addLayout(row_iv)
        self.update_status = QLabel("")
        self.update_status.setObjectName("settingsStatus")
        self.update_status.setWordWrap(True)
        sl.addWidget(self.update_status)
        left.addWidget(sync_card)

        self._add_settings_group(
            left,
            "\u7a0b\u5f0f\u7248\u672c",
            "\u82e5\u767c\u73fe\u7121\u6cd5\u6b63\u5e38\u5237\u65b0\u6578\u64da\uff0c\u8acb\u5617\u8a66\u6aa2\u67e5\u66f4\u65b0\uff1b"
            "\u82e5\u7248\u672c\u5c1a\u672a\u66f4\u65b0\uff0c\u8acb\u7b49\u5f85\u958b\u767c\u8005\u66f4\u65b0\u7a0b\u5f0f\u7248\u672c\u3002",
        )
        ver_card = _make_settings_group_card(card_parent)
        vl = QVBoxLayout(ver_card)
        vl.setContentsMargins(14, 12, 14, 12)
        vl.setSpacing(10)
        self._app_version_label = QLabel(f"\u76ee\u524d\u7248\u672c\uff1a {current_app_version()}")
        self._app_version_label.setObjectName("settingsFormLabel")
        vl.addWidget(self._app_version_label)
        ver_btn_row = QHBoxLayout()
        ver_btn_row.setSpacing(8)
        self._app_update_btn = QPushButton("\u6aa2\u67e5\u66f4\u65b0")
        self._app_update_btn.setMinimumHeight(36)
        self._app_update_btn.clicked.connect(self._on_app_update_clicked)
        ver_btn_row.addWidget(self._app_update_btn, 1)
        self._app_oneclick_btn = QPushButton("\u4e00\u9375\u66f4\u65b0\u7a0b\u5f0f")
        self._app_oneclick_btn.setMinimumHeight(36)
        self._app_oneclick_btn.clicked.connect(self._on_oneclick_update_clicked)
        if not lazy_update_supported():
            self._app_oneclick_btn.setEnabled(False)
            self._app_oneclick_btn.setToolTip(
                "\u50c5\u9069\u7528 Windows \u514d\u5b89\u88dd exe\uff1b\u958b\u767c\u6a21\u5f0f\u8acb\u7528\u300c\u6aa2\u67e5\u66f4\u65b0\u300d\u6216 git\u3002"
            )
        ver_btn_row.addWidget(self._app_oneclick_btn, 1)
        vl.addLayout(ver_btn_row)
        left.addWidget(ver_card)

        self._add_settings_group(left, "\u5e73\u53f0\u767b\u5165")
        acc_card = _make_settings_group_card(card_parent)
        acc_l = QVBoxLayout(acc_card)
        acc_l.setContentsMargins(0, 2, 0, 2)
        acc_l.setSpacing(0)
        _plat_hint = QLabel(
            "Google\u3001X\uff08Twitter\uff09\u7b49\u7db2\u7ad9\u53ef\u80fd\u9650\u5236\u6b64\u7a2e\u81ea\u52d5\u958b\u555f\u7684\u767b\u5165\u65b9\u5f0f\uff1b"
            "\u8acb\u6539\u5728\u7db2\u9801\u4ee5\u5e33\u865f\u5bc6\u78bc\u6216\u901a\u884c\u91d1\u9470\u5b8c\u6210\u767b\u5165\u3002\n"
            "\u767b\u5165\u5b8c\u6210\u5f8c\u8acb\u56de\u5230\u672c\u7a0b\u5f0f\u6309\u300c\u5df2\u5b8c\u6210\u300d\u3002"
        )
        _plat_hint.setWordWrap(True)
        _plat_hint.setObjectName("settingsFormLabel")
        _plat_hint.setStyleSheet(
            f"font-size: 14px !important; "
            f"padding: 12px 14px; margin: 8px 12px 0 12px; "
            f"background-color: {PALETTE['bg_elevated']}; "
            f"border-left: 3px solid {PALETTE['accent']}; border-radius: 6px;"
        )
        acc_l.addWidget(_plat_hint)
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
                logged = bool((cfg.get("session_id") or "").strip() and "\u4f60\u7684" not in (cfg.get("session_id") or ""))
            st = QLabel("\u5df2\u767b\u5165" if logged else "\u672a\u767b\u5165")
            st.setStyleSheet(f"color: {PALETTE['success'] if logged else PALETTE['text_tertiary']};")
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
            btn = QPushButton("\u767b\u5165")
            btn.setStyleSheet(
                f"background-color: {color}; color: #ffffff; border: none; "
                f"border-radius: 10px; font-weight: 600; padding: 8px 18px;"
            )
            btn.clicked.connect(getattr(self, f"_{key}_login_start"))
            setattr(self, f"{key}_btn", btn)
            done_btn = QPushButton("\u5df2\u5b8c\u6210")
            done_btn.setEnabled(False)
            done_btn.clicked.connect(getattr(self, f"_{key}_login_done"))
            setattr(self, f"{key}_done_btn", done_btn)
            logout_btn = QPushButton("\u767b\u51fa")
            logout_btn.clicked.connect(partial(self._platform_login_logout, key))
            setattr(self, f"{key}_logout_btn", logout_btn)
            bl.addWidget(btn)
            bl.addWidget(done_btn)
            bl.addWidget(logout_btn)
            bl.addStretch()
            rl.addLayout(bl)
            acc_l.addWidget(roww)
        left.addWidget(acc_card)

        if not PLAYWRIGHT_AVAILABLE:
            for key in ("patreon", "fanbox", "fantia"):
                getattr(self, f"{key}_btn").setEnabled(False)
                getattr(self, f"{key}_logout_btn").setEnabled(False)
            w = QLabel("Playwright \u672a\u5b89\u88dd\uff1aplaywright install chromium")
            w.setStyleSheet(f"color: {PALETTE['warning']};")
            left.addWidget(w)

        self._add_settings_group(right, "\u901a\u77e5\u97f3\u6548")
        preset_key = normalize_increase_sound_key(gui_sound.get("increase_sound"))
        preset_label = _INCREASE_SOUND_KEY_TO_LABEL.get(
            preset_key, _INCREASE_SOUND_KEY_TO_LABEL["asterisk"]
        )
        sound_card = _make_settings_group_card(card_parent)
        sil = QVBoxLayout(sound_card)
        sil.setContentsMargins(14, 12, 14, 12)
        sil.setSpacing(10)
        r1 = QHBoxLayout()
        r1.addWidget(_settings_form_label("\u7cfb\u7d71\u97f3\u6548"), 0)
        self._increase_sound_preset = QComboBox()
        for lab in INCREASE_SOUND_PRESET_LABELS:
            self._increase_sound_preset.addItem(lab)
        self._increase_sound_preset.setCurrentText(preset_label)
        self._increase_sound_preset.currentTextChanged.connect(self._on_increase_sound_preset_changed)
        r1.addWidget(self._increase_sound_preset, 1)
        test_snd = QPushButton("\u8a66\u807d")
        test_snd.clicked.connect(self._test_increase_sound)
        r1.addWidget(test_snd)
        sil.addLayout(r1)
        vr = QHBoxLayout()
        vr.addWidget(_settings_form_label("\u97f3\u91cf"), 0)
        self._sound_volume_slider = QSlider(Qt.Orientation.Horizontal)
        self._sound_volume_slider.setRange(0, 100)
        _v0 = int(float(gui_sound.get("increase_sound_volume", 100)))
        self._sound_volume_slider.setValue(_v0)
        self._sound_volume_slider.valueChanged.connect(self._on_sound_volume_slider)
        vr.addWidget(self._sound_volume_slider, 1)
        self._sound_volume_lbl = QLabel(f"{_v0}%")
        vr.addWidget(self._sound_volume_lbl)
        sil.addLayout(vr)
        sil.addWidget(_settings_form_label("\u81ea\u8a02 WAV \u8def\u5f91\uff08\u9078\u586b\uff09"))
        self._increase_sound_wav_entry = QLineEdit()
        self._increase_sound_wav_entry.setText(gui_sound.get("increase_sound_wav") or "")
        self._increase_sound_wav_entry.editingFinished.connect(self._on_increase_sound_wav_done)
        sil.addWidget(self._increase_sound_wav_entry)
        right.addWidget(sound_card)

        self._add_settings_group(right, "Discord \u901a\u77e5")
        dc = _make_settings_group_card(card_parent)
        dcl = QVBoxLayout(dc)
        dcl.setContentsMargins(14, 12, 14, 12)
        dcl.setSpacing(10)
        dcl.addWidget(_settings_form_label("Webhook URL"))
        self._discord_webhook_entry = QLineEdit()
        self._discord_webhook_entry.setPlaceholderText("https://discord.com/api/webhooks/...")
        self._discord_webhook_entry.setText(gui_sound.get("discord_webhook_url") or "")
        self._discord_webhook_entry.editingFinished.connect(self._on_discord_webhook_done)
        dcl.addWidget(self._discord_webhook_entry)
        dbtn = QHBoxLayout()
        tdisc = QPushButton("\u6e2c\u8a66\u50b3\u9001")
        tdisc.clicked.connect(self._test_discord_webhook)
        dbtn.addWidget(tdisc)
        dbtn.addStretch()
        dcl.addLayout(dbtn)
        self._sw_daily_report = QCheckBox("\u6bcf\u65e5\u5b9a\u6642\u50b3\u9001\u7e3d\u89bd\u5831\u8868\uff08\u65e5\u672c\u6642\u9593 JST\uff09")
        self._sw_daily_report.setChecked(bool(gui_sound.get("daily_report_enabled")))
        self._sw_daily_report.toggled.connect(self._on_daily_report_switch)
        dcl.addWidget(self._sw_daily_report)
        dtr = QHBoxLayout()
        dtr.addWidget(_settings_form_label("\u6bcf\u65e5\u50b3\u9001\u6642\u9593"), 0)
        self._daily_report_time_entry = QLineEdit()
        _drt = gui_sound.get("daily_report_time_jst") or "09:00"
        _parsed_drt = parse_jst_hhmm(str(_drt))
        if _parsed_drt:
            _drt = f"{_parsed_drt[0]:02d}:{_parsed_drt[1]:02d}"
        self._daily_report_time_entry.setText(_drt)
        self._daily_report_time_entry.editingFinished.connect(self._on_daily_report_time_done)
        dtr.addWidget(self._daily_report_time_entry, 1)
        tdr = QPushButton("\u50b3\u9001\u7e3d\u89bd\u6e2c\u8a66")
        tdr.clicked.connect(self._test_discord_daily_report)
        dtr.addWidget(tdr)
        dcl.addLayout(dtr)
        right.addWidget(dc)

        self._add_settings_group(right, "\u7cfb\u7d71\u532f\u8207\u8996\u7a97")
        tray_card = _make_settings_group_card(card_parent)
        tl = QVBoxLayout(tray_card)
        tl.setContentsMargins(14, 12, 14, 12)
        tl.setSpacing(8)
        self._sw_close_tray = QCheckBox(
            "\u95dc\u9589\u8996\u7a97\u6642\u7e2e\u5230\u7cfb\u7d71\u532f\uff08\u95dc\u9589\u5247\u7d50\u675f\u7a0b\u5f0f\uff09"
        )
        self._sw_close_tray.setChecked(self._close_to_tray)
        self._sw_close_tray.toggled.connect(self._on_switch_close_to_tray)
        self._sw_min_tray = QCheckBox("\u6700\u5c0f\u5316\u6642\u7e2e\u5230\u7cfb\u7d71\u532f")
        self._sw_min_tray.setChecked(self._minimize_to_tray)
        self._sw_min_tray.toggled.connect(self._on_switch_minimize_to_tray)
        self._sw_start_tray = QCheckBox("\u555f\u52d5\u6642\u53ea\u986f\u793a\u7cfb\u7d71\u532f\uff08\u4e3b\u8996\u7a97\u5148\u96b1\u85cf\uff09")
        self._sw_start_tray.setChecked(self._start_minimized_to_tray)
        self._sw_start_tray.toggled.connect(self._on_switch_start_tray)
        self._sw_autostart = QCheckBox(
            "\u958b\u6a5f\u6642\u81ea\u52d5\u555f\u52d5\u7a0b\u5f0f\uff08\u50c5 Windows\uff09"
        )
        with QSignalBlocker(self._sw_autostart):
            self._sw_autostart.setChecked(self._start_with_windows)
        if sys.platform != "win32":
            self._sw_autostart.setEnabled(False)
            self._sw_autostart.setToolTip("\u50c5 Windows \u652f\u63f4\u958b\u6a5f\u81ea\u52d5")
        self._sw_autostart.toggled.connect(self._on_switch_autostart)
        for w in (self._sw_close_tray, self._sw_min_tray, self._sw_start_tray, self._sw_autostart):
            tl.addWidget(w)
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self._sw_close_tray.setEnabled(False)
            self._sw_min_tray.setEnabled(False)
            self._sw_start_tray.setEnabled(False)
        right.addWidget(tray_card)

        self._add_settings_group(
            right,
            "\u8cc7\u6599\u6e05\u9664",
            "\u522a\u9664\u6240\u6709\u5e73\u53f0\u7684\u767b\u5165\u8cc7\u6599\uff0c\u4e26\u6e05\u7a7a\u8cc7\u6599\u5eab\u5167\u7684\u66f4\u65b0\u8a18\u9304\uff08\u8d0a\u52a9\u984d\u6b77\u53f2\u8207\u6bcf\u65e5\u6458\u8981\uff09\u3002",
        )
        purge_card = _make_settings_group_card(card_parent)
        pr = QVBoxLayout(purge_card)
        pr.setContentsMargins(14, 12, 14, 12)
        pr.setSpacing(10)
        purge_btn = QPushButton("\u5fb9\u5e95\u6e05\u9664\u767b\u5165\u8207\u66f4\u65b0\u8a18\u9304")
        purge_btn.setStyleSheet(
            f"background-color: {PALETTE['error']}; color: #ffffff; border: none; "
            f"border-radius: 10px; font-weight: 600; padding: 8px 18px;"
        )
        purge_btn.clicked.connect(self._master_clear_login_and_history)
        pr.addWidget(purge_btn)
        right.addWidget(purge_card)

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
            QMessageBox.warning(self, "\u958b\u6a5f\u81ea\u52d5", msg)

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

    def _on_increase_sound_preset_changed(self, label: str):
        self.config = load_config()
        self.config.setdefault("gui", {})["increase_sound"] = _INCREASE_SOUND_LABEL_TO_KEY.get(label, "asterisk")
        save_config(self.config)

    def _on_increase_sound_wav_done(self):
        self.config = load_config()
        self.config.setdefault("gui", {})["increase_sound_wav"] = self._increase_sound_wav_entry.text().strip()
        save_config(self.config)

    def _test_increase_sound(self):
        snap = load_config()
        gui = snap.setdefault("gui", {})
        key = _INCREASE_SOUND_LABEL_TO_KEY.get(self._increase_sound_preset.currentText(), "asterisk")
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
            QMessageBox.warning(self, "Discord Webhook", "\u8acb\u5148\u8cbc\u4e0a Webhook \u7db2\u5740\u3002")
            return
        if not is_discord_webhook_url(url):
            QMessageBox.critical(
                self,
                "Discord Webhook",
                "\u7db2\u5740\u683c\u5f0f\u4e0d\u7b26\uff08\u9808\u70ba https://discord.com/api/webhooks/\u2026 \uff09\u3002",
            )
            return

        def _run():
            ok, err = post_discord_webhook(url, "\u3010\u8d0a\u52a9\u984d\u8ffd\u8e64\u3011\u6e2c\u8a66\uff1aWebhook \u9023\u7dda\u6210\u529f")

            def _done():
                if ok:
                    QMessageBox.information(self, "Discord Webhook", "\u5df2\u9001\u51fa\u6e2c\u8a66\u8a0a\u606f\u3002")
                else:
                    QMessageBox.critical(self, "Discord Webhook", f"\u9001\u51fa\u5931\u6557\uff1a{err or ''}")

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
            QMessageBox.warning(self, "\u7e3d\u89bd\u5831\u8868", "\u8acb\u5148\u8cbc\u4e0a Webhook \u7db2\u5740\u3002")
            return
        if not is_discord_webhook_url(url):
            QMessageBox.critical(self, "\u7e3d\u89bd\u5831\u8868", "\u7db2\u5740\u683c\u5f0f\u4e0d\u7b26\u3002")
            return

        def _run():
            try:
                s = get_dashboard_stats()
                period = get_period_comparison(7)
            except Exception as ex:

                def _fail():
                    QMessageBox.critical(self, "\u7e3d\u89bd\u5831\u8868", f"\u8b80\u53d6\u5931\u6557\uff1a{ex}")

                QTimer.singleShot(0, _fail)
                return
            text = format_daily_dashboard_report(
                s,
                period,
                time_jst=f"{now_jst():%Y-%m-%d %H:%M} JST",
            )
            ok, err = post_discord_webhook_long(url, text)

            def _done():
                if ok:
                    QMessageBox.information(self, "\u7e3d\u89bd\u5831\u8868", "\u5df2\u9001\u51fa\u3002")
                else:
                    QMessageBox.critical(self, "\u7e3d\u89bd\u5831\u8868", f"\u5931\u6557\uff1a{err or ''}")

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
                    period = get_period_comparison(7)
                except Exception:
                    continue
                text = format_daily_dashboard_report(
                    s,
                    period,
                    time_jst=f"{now:%Y-%m-%d %H:%M} JST",
                )
                ok, _ = post_discord_webhook_long(url, text)
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
        st.setText("\u672a\u767b\u5165")
        st.setStyleSheet(f"color: {PALETTE['text_tertiary']};")
        getattr(self, f"{key}_btn").setEnabled(True)
        getattr(self, f"{key}_done_btn").setEnabled(False)

    def _platform_login_logout(self, key: str) -> None:
        self._clear_platform_login_state(key)

    def _master_clear_login_and_history(self) -> None:
        r = QMessageBox.question(
            self,
            "\u78ba\u8a8d",
            "\u5c07\u522a\u9664\u6240\u6709\u5e73\u53f0\u7684\u767b\u5165\u8cc7\u6599\uff0c\u4e26\u6e05\u7a7a\u8cc7\u6599\u5eab\u5167\u7684\u66f4\u65b0\u8a18\u9304\uff08\u8d0a\u52a9\u984d\u6b77\u53f2\u8207\u6bcf\u65e5\u6458\u8981\uff09\u3002\u6b64\u64cd\u4f5c\u7121\u6cd5\u9084\u539f\u3002\n\u78ba\u5b9a\u8981\u7e7c\u7e8c\u55ce\uff1f",
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
    def _on_browser_login_payload(self, platform: str, payload: str) -> None:
        """\u7531 Signal \u5f9e Playwright \u57f7\u7dd2\u56de\u5230\u4e3b\u57f7\u7dd2\u8655\u7406\u3002"""
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
        self._login_flow_active["patreon"] = True
        self.patreon_btn.setEnabled(False)
        self.patreon_done_btn.setEnabled(True)
        self.patreon_status.setText("\u700f\u89bd\u5668\u767b\u5165\u4e2d...")
        self.patreon_status.setStyleSheet(f"color: {PALETTE['warning']};")
        patreon_login(
            self.browser_done_events["patreon"],
            lambda s: self._browser_login_payload.emit("patreon", s),
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
            self.patreon_status.setText("\u5df2\u767b\u5165")
            self.patreon_status.setStyleSheet(f"color: {PALETTE['success']};")
        else:
            self.patreon_status.setText("\u5931\u6557\uff0c\u8acb\u91cd\u8a66")
            self.patreon_status.setStyleSheet(f"color: {PALETTE['error']};")
        self.patreon_btn.setEnabled(True)

    def _fanbox_login_start(self):
        if ce := self.browser_cancel_events.get("fanbox"):
            ce.set()
        self.browser_done_events["fanbox"] = threading.Event()
        self.browser_cancel_events["fanbox"] = threading.Event()
        self._login_flow_active["fanbox"] = True
        self.fanbox_btn.setEnabled(False)
        self.fanbox_done_btn.setEnabled(True)
        self.fanbox_status.setText("\u700f\u89bd\u5668\u767b\u5165\u4e2d...")
        self.fanbox_status.setStyleSheet(f"color: {PALETTE['warning']};")
        fanbox_login(
            self.browser_done_events["fanbox"],
            lambda s: self._browser_login_payload.emit("fanbox", s),
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
            self.fanbox_status.setText("\u5df2\u767b\u5165")
            self.fanbox_status.setStyleSheet(f"color: {PALETTE['success']};")
        else:
            self.fanbox_status.setText("\u5931\u6557\uff0c\u8acb\u91cd\u8a66")
            self.fanbox_status.setStyleSheet(f"color: {PALETTE['error']};")
        self.fanbox_btn.setEnabled(True)

    def _fantia_login_start(self):
        if ce := self.browser_cancel_events.get("fantia"):
            ce.set()
        self.browser_done_events["fantia"] = threading.Event()
        self.browser_cancel_events["fantia"] = threading.Event()
        self._login_flow_active["fantia"] = True
        self.fantia_btn.setEnabled(False)
        self.fantia_done_btn.setEnabled(True)
        self.fantia_status.setText("\u700f\u89bd\u5668\u767b\u5165\u4e2d...")
        self.fantia_status.setStyleSheet(f"color: {PALETTE['warning']};")
        fantia_login(
            self.browser_done_events["fantia"],
            lambda s: self._browser_login_payload.emit("fantia", s),
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
            self.fantia_status.setText("\u5df2\u767b\u5165")
            self.fantia_status.setStyleSheet(f"color: {PALETTE['success']};")
        else:
            self.fantia_status.setText("\u5931\u6557\uff0c\u8acb\u91cd\u8a66")
            self.fantia_status.setStyleSheet(f"color: {PALETTE['error']};")
        self.fantia_btn.setEnabled(True)

def main():
    detach_windows_console_if_present()
    _cfg0 = load_config()
    _g = _cfg0.setdefault("gui", {})
    if _g.get("qt_theme") != "dark":
        _g["qt_theme"] = "dark"
        save_config(_cfg0)
    palette_apply()
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
