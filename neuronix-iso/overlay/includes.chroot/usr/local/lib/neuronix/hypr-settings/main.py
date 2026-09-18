import configparser
import fcntl
import os
import shutil
import subprocess
import sys
import tempfile
from PySide6.QtGui import QFont, QGuiApplication, QIcon, QKeySequence, QShortcut
from PySide6.QtCore import QFileSystemWatcher, Qt
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFrame, QHBoxLayout,
    QLabel, QMainWindow, QPushButton, QSplitter, QStackedWidget, QVBoxLayout, QWidget,
)

from wifi_tab import WifiTab
from ethernet_tab import EthernetTab
from bluetooth_tab import BluetoothTab
from displays_tab import DisplaysTab
from sound_tab import SoundTab
from battery_tab import BatteryTab
from apps_tab import AppsTab
from appearance_tab import ConfigsTab
from system_tab import SystemTab
from gtk_sync_tab import GtkSyncTab
from datetime_tab import DateTimeTab
from keyboard_tab import KeyboardTab
from screensaver_tab import ScreensaverTab
from about_tab import AboutTab

_LOCK_FILE = os.path.join(tempfile.gettempdir(), f"hypr-settings-{os.getenv('USER', 'user')}.lock")
_lock_fh   = None
_is_dark   = True
_base_font = 13


def _acquire_lock():
    global _lock_fh
    _lock_fh = open(_LOCK_FILE, "w")
    try:
        fcntl.flock(_lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_fh.write(str(os.getpid()))
        _lock_fh.flush()
        return True
    except OSError:
        return False


def _hyprctl(*args: str) -> None:
    subprocess.run(
        ["hyprctl", "dispatch", *args],
        timeout=2,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _focus_existing() -> None:
    """Raise the already-running Settings window instead of failing silently."""
    pid = ""
    try:
        pid = open(_LOCK_FILE, encoding="utf-8").read().strip()
    except Exception:
        pid = ""
    try:
        if pid.isdigit():
            _hyprctl("focuswindow", f"pid:{pid}")
        _hyprctl("focuswindow", "class:hypr-settings")
        _hyprctl("focuswindow", "title:Settings")
        _hyprctl("alterzorder", "top")
    except Exception:
        pass


def _detect_icon_theme():
    try:
        r = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "icon-theme"],
            capture_output=True, text=True, timeout=2,
        )
        val = r.stdout.strip().strip("'\"")
        if val:
            return val
    except Exception:
        pass
    try:
        cp = configparser.RawConfigParser()
        cp.read(os.path.expanduser("~/.config/gtk-3.0/settings.ini"))
        val = cp.get("Settings", "gtk-icon-theme-name", fallback="")
        if val:
            return val
    except Exception:
        pass
    return "hicolor"


def _detect_dark():
    try:
        from suite_theme import suite_is_dark

        suite_dark = suite_is_dark()
        if suite_dark is not None:
            return suite_dark
    except Exception:
        pass
    try:
        r = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
            capture_output=True, text=True, timeout=2,
        )
        val = r.stdout.strip().strip("'\"")
        if val == "prefer-light":
            return False
        if val == "prefer-dark":
            return True
    except Exception:
        pass
    try:
        cp = configparser.RawConfigParser()
        cp.read(os.path.expanduser("~/.config/gtk-3.0/settings.ini"))
        val = cp.get("Settings", "gtk-application-prefer-dark-theme", fallback="1")
        return val.lower() not in ("0", "false")
    except Exception:
        pass
    return True


def _qss():
    b = _base_font

    suite = None
    try:
        from suite_theme import suite_colors

        suite = suite_colors()
    except Exception:
        suite = None

    if suite:
        BG = suite["BG"]
        BG_SIDEBAR = suite["BG_SIDEBAR"]
        BG_RAISED = suite["BG_RAISED"]
        BG_HOVER = suite["BG_HOVER"]
        BG_PRESS = suite["BG_PRESS"]
        TEXT = suite["TEXT"]
        TEXT_BRIGHT = suite["TEXT_BRIGHT"]
        TEXT_DIM = suite["TEXT_DIM"]
        TEXT_MUTED = suite["TEXT_MUTED"]
        BORDER = suite["BORDER"]
        BORDER_HOVER = suite["BORDER_HOVER"]
        BORDER_FOCUS = suite["BORDER_FOCUS"]
        BORDER_SUBTLE = suite["BORDER_SUBTLE"]
        SEP = suite["SEP"]
        INPUT_TEXT = suite["INPUT_TEXT"]
        LIST_ITEM = suite["LIST_ITEM"]
        ACCENT = suite["ACCENT"]
        ACCENT_TEXT = suite["ACCENT_TEXT"]
    elif _is_dark:
        BG            = "#0d0d0d"
        BG_SIDEBAR    = "#080808"
        BG_RAISED     = "#111111"
        BG_HOVER      = "#1a1a1a"
        BG_PRESS      = "#050505"
        TEXT          = "#d8d8d8"
        TEXT_BRIGHT   = "#f0f0f0"
        TEXT_DIM      = "#b0b0b0"
        TEXT_MUTED    = "#606060"
        BORDER        = "#303030"
        BORDER_HOVER  = "#787878"
        BORDER_FOCUS  = "#a3b3d4"
        BORDER_SUBTLE = "#282828"
        SEP           = "#1e1e1e"
        INPUT_TEXT    = "#d0d0d0"
        LIST_ITEM     = "#c8c8c8"
        ACCENT        = "#a3b3d4"
        ACCENT_TEXT   = "#101010"
    else:
        BG            = "#f5f5f5"
        BG_SIDEBAR    = "#eaeaea"
        BG_RAISED     = "#ffffff"
        BG_HOVER      = "#e4e4e4"
        BG_PRESS      = "#d4d4d4"
        TEXT          = "#1c1c1c"
        TEXT_BRIGHT   = "#0a0a0a"
        TEXT_DIM      = "#555555"
        TEXT_MUTED    = "#888888"
        BORDER        = "#c8c8c8"
        BORDER_HOVER  = "#999999"
        BORDER_FOCUS  = "#a3b3d4"
        BORDER_SUBTLE = "#e0e0e0"
        SEP           = "#dedede"
        INPUT_TEXT    = "#1c1c1c"
        LIST_ITEM     = "#2a2a2a"
        ACCENT        = "#a3b3d4"
        ACCENT_TEXT   = "#101010"

    RADIUS      = "4px"
    RADIUS_LG   = "6px"

    return f"""
QWidget {{
    background-color: {BG};
    color: {TEXT};
    font-size: {b}px;
}}

QMainWindow {{
    background-color: {BG_SIDEBAR};
}}

/* ── Sidebar ── */

QWidget#sidebar {{
    background-color: {BG_SIDEBAR};
}}

QLabel#appTitle {{
    color: {TEXT_BRIGHT};
    font-size: {b+2}px;
    font-weight: 700;
    padding: 0 4px;
    background: transparent;
}}

QPushButton#navBtn {{
    background: transparent;
    border: none;
    border-radius: 6px;
    color: {TEXT_MUTED};
    font-size: {b}px;
    font-weight: 500;
    text-align: left;
    padding: 9px 14px 9px 18px;
    min-height: 22px;
    min-width: 0;
}}

QPushButton#navBtn QLabel {{
    background: transparent;
    padding: 0;
    font-size: {b}px;
    font-weight: 500;
    color: {TEXT_MUTED};
}}

QPushButton#navBtn:hover {{
    background: {BG_HOVER};
    color: {TEXT_DIM};
}}

QPushButton#navBtn:hover QLabel {{
    color: {TEXT_DIM};
}}

QPushButton#navBtn QLabel#navBtnArrow {{
    color: {TEXT_MUTED};
    font-weight: 400;
    font-size: {b + 1}px;
}}

QPushButton#navBtn:hover QLabel#navBtnArrow {{
    color: {TEXT_DIM};
}}

QPushButton#navBtn:checked {{
    background: {ACCENT};
    color: {ACCENT_TEXT};
    font-weight: 600;
    border-radius: 6px;
}}

QPushButton#navBtn:checked QLabel {{
    color: {ACCENT_TEXT};
    font-weight: 600;
}}

QSplitter::handle {{
    background: {SEP};
}}

/* ── Content labels ── */

QLabel {{
    background: transparent;
    color: {TEXT};
}}

QLabel#pageTitle {{
    font-size: {b+6}px;
    font-weight: 600;
    color: {TEXT_BRIGHT};
}}

QLabel#sectionTitle {{
    font-size: {b}px;
    font-weight: 600;
    color: {TEXT_DIM};
    padding-top: 2px;
    padding-bottom: 2px;
}}

QLabel#detailTitle {{
    font-size: {b+2}px;
    font-weight: 600;
    color: {TEXT_BRIGHT};
}}

QLabel#statusLabel {{
    color: {TEXT_MUTED};
    font-size: {b}px;
}}

QLabel#fieldLabel {{
    color: {TEXT_DIM};
}}

QLabel a {{
    color: {TEXT_DIM};
    text-decoration: underline;
}}

/* ── Buttons ── */

QPushButton {{
    background-color: {BG};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: {RADIUS};
    padding: 5px 12px;
    min-height: 26px;
    min-width: 60px;
}}

QPushButton:hover {{
    background-color: {BG_HOVER};
    border-color: {BORDER_HOVER};
    color: {TEXT_BRIGHT};
}}

QPushButton:pressed {{
    background-color: {BG_PRESS};
    border-color: {BORDER};
    color: {TEXT_DIM};
}}

QPushButton:disabled {{
    color: {TEXT_MUTED};
    background-color: {BG};
    border-color: {BORDER_SUBTLE};
}}

QPushButton:checked {{
    background-color: {ACCENT};
    color: {ACCENT_TEXT};
    border-color: {ACCENT};
}}

QPushButton:default {{
    border-color: {ACCENT};
}}

QPushButton:default:hover {{
    border-color: {BORDER_FOCUS};
}}

/* ── Lists ── */

QListWidget {{
    background: {BG_RAISED};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: {RADIUS_LG};
    outline: none;
    padding: 3px;
}}

QListWidget::item {{
    padding: 12px 14px;
    border-radius: 5px;
    color: {LIST_ITEM};
}}

QListWidget::item:selected {{
    background: {ACCENT};
    color: {ACCENT_TEXT};
}}

QListWidget::item:hover:!selected {{
    background: {BG_HOVER};
}}

/* ── Separators ── */

QFrame[frameShape="4"] {{
    border: none;
    background-color: {SEP};
    max-height: 1px;
    margin: 2px 0;
}}

QFrame[frameShape="5"] {{
    border: none;
    background-color: {SEP};
    max-width: 1px;
}}

/* ── Checkboxes ── */

QCheckBox {{
    spacing: 8px;
    color: {TEXT};
}}

QCheckBox::indicator {{
    width: 15px;
    height: 15px;
    border: 1px solid {BORDER};
    border-radius: 4px;
    background: {BG};
}}

QCheckBox::indicator:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT};
}}

QCheckBox::indicator:hover {{
    border-color: {BORDER_FOCUS};
}}

/* ── Inputs ── */

QComboBox {{
    background: {BG_RAISED};
    border: 1px solid {BORDER};
    border-radius: {RADIUS};
    padding: 4px 10px;
    min-height: 26px;
    color: {INPUT_TEXT};
}}

QComboBox:hover {{ border-color: {BORDER_HOVER}; }}
QComboBox:focus {{ border-color: {BORDER_FOCUS}; }}

QComboBox::drop-down {{
    border: none;
    width: 22px;
}}

QComboBox QAbstractItemView {{
    background: {BG_RAISED};
    border: 1px solid {BORDER};
    border-radius: {RADIUS};
    selection-background-color: {ACCENT};
    selection-color: {ACCENT_TEXT};
    outline: none;
    padding: 3px;
}}

QComboBox QAbstractItemView::item:hover {{
    background: {BG_HOVER};
}}

QSpinBox, QDoubleSpinBox {{
    background: {BG_RAISED};
    border: 1px solid {BORDER};
    border-radius: {RADIUS};
    padding: 4px 8px;
    min-height: 26px;
    color: {INPUT_TEXT};
}}

QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {BORDER_FOCUS}; }}

QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    background: {BG_HOVER};
    border: none;
    width: 18px;
}}

QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{
    background: {BG_PRESS};
}}

QLineEdit {{
    background: {BG_RAISED};
    border: 1px solid {BORDER};
    border-radius: {RADIUS};
    padding: 4px 10px;
    color: {TEXT_BRIGHT};
    min-height: 26px;
}}

QLineEdit:focus {{ border-color: {BORDER_FOCUS}; }}

/* ── Sliders ── */

QSlider::groove:horizontal {{
    height: 3px;
    background: {BORDER_SUBTLE};
    border-radius: 2px;
}}

QSlider::handle:horizontal {{
    background: {TEXT_DIM};
    border: none;
    width: 14px;
    height: 14px;
    border-radius: 7px;
    margin: -6px 0;
}}

QSlider::handle:horizontal:hover {{ background: {ACCENT}; }}

QSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 2px;
}}

/* ── Scrollbars ── */

QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 4px 0;
}}

QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 3px;
    min-height: 24px;
}}

QScrollBar::handle:vertical:hover {{ background: {BORDER_HOVER}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}

QScrollArea {{
    border: none;
    background: transparent;
}}

/* ── Dialogs ── */

QInputDialog, QMessageBox {{ background: {BG}; }}
QMessageBox QLabel, QInputDialog QLabel {{ background: transparent; color: {TEXT}; }}
"""


def _open_gtk_theme_editor() -> None:
    exe = shutil.which("gtk-theme-editor") or "gtk-theme-editor"
    subprocess.Popen([exe], start_new_session=True)


def _nav_button(label: str, *, external: bool = False) -> QPushButton:
    """Sidebar row. External items get a ↗ to show they open another app."""
    btn = QPushButton()
    btn.setObjectName("navBtn")
    row = QHBoxLayout(btn)
    row.setContentsMargins(10, 0, 4, 0)
    row.setSpacing(4)
    text = QLabel(label)
    text.setObjectName("navBtnText")
    text.setAttribute(Qt.WA_TransparentForMouseEvents)
    row.addWidget(text)
    if external:
        arrow = QLabel("↗")
        arrow.setObjectName("navBtnArrow")
        arrow.setAttribute(Qt.WA_TransparentForMouseEvents)
        row.addWidget(arrow)
    row.addStretch()
    return btn


_PAGES = [
    ("Wi-Fi",       "network-wireless",                         WifiTab),
    ("Ethernet",    "network-wired",                            EthernetTab),
    ("Bluetooth",   "bluetooth",                                BluetoothTab),
    ("Displays",    "video-display",                            DisplaysTab),
    ("Sound",       "audio-volume-high",                        SoundTab),
    ("Battery",     "battery",                                  BatteryTab),
    ("Apps",        "preferences-desktop-default-applications", AppsTab),
    ("Themes",      "preferences-desktop-theme",                "gtk-theme-editor"),
    ("Configs",     "folder",                                   ConfigsTab),
    ("Screensaver", "preferences-desktop-screensaver",          ScreensaverTab),
    ("System",      "preferences-system",                       SystemTab),
    ("GTK-Sync",    "folder-sync",                              GtkSyncTab),
    ("Date & Time", "preferences-system-time",                  DateTimeTab),
    ("Keyboard",    "input-keyboard",                           KeyboardTab),
]

# CLI flags → _PAGES index (Themes launches gtk-theme-editor; Configs is the file editor).
_TAB_FLAGS = [
    ({"--wifi"},                          0),
    ({"--ethernet", "--wired", "--lan"},  1),
    ({"--bluetooth"},                     2),
    ({"--displays"},                      3),
    ({"--sound"},                         4),
    ({"--battery"},                       5),
    ({"--apps"},                          6),
    ({"--themes", "--theme", "--appearance", "--appearence"}, 7),
    ({"--configs", "--config"},           8),
    ({"--screensaver", "--idle"},         9),
    ({"--system"},                        10),
    ({"--gtk-sync", "--gtksync"},         11),
    ({"--datetime", "--date-time"},       12),
    ({"--keyboard"},                      13),
]


def main():
    global _is_dark

    if not _acquire_lock():
        _focus_existing()
        sys.exit(0)

    _is_dark = _detect_dark()

    QGuiApplication.setDesktopFileName("hypr-settings")
    app = QApplication(sys.argv)
    app.setFont(QFont("sans", 14))
    app.setStyleSheet(_qss())
    QIcon.setThemeName(_detect_icon_theme())

    import common
    def _apply_theme(dark: bool):
        global _is_dark
        # Prefer live suite profile colors; dark flag is only a fallback.
        suite_dark = None
        try:
            from suite_theme import suite_is_dark

            suite_dark = suite_is_dark()
        except Exception:
            suite_dark = None
        _is_dark = suite_dark if suite_dark is not None else dark
        app.setStyleSheet(_qss())
    common.on_theme_change = _apply_theme

    # Live-reload when Neuronix Profile menu / gtk-theme-editor writes theme.toml.
    try:
        from suite_theme import theme_toml_path

        theme_path = theme_toml_path()
        theme_path.parent.mkdir(parents=True, exist_ok=True)
        if not theme_path.is_file():
            theme_path.write_text('profile = "gruvbox-dark"\n', encoding="utf-8")
        watcher = QFileSystemWatcher([str(theme_path), str(theme_path.parent)])
        watcher.fileChanged.connect(lambda *_: _apply_theme(_is_dark))
        watcher.directoryChanged.connect(lambda *_: _apply_theme(_is_dark))
        app._neuronix_theme_watcher = watcher  # keep alive
    except Exception:
        pass

    _daemon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "monitor_daemon.py")
    if os.path.exists(_daemon_path):
        subprocess.Popen([sys.executable, _daemon_path])

    window = QMainWindow()
    window.setWindowTitle("Settings")
    window.setMinimumSize(960, 620)

    root_widget = QWidget()
    root = QHBoxLayout(root_widget)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)

    splitter = QSplitter()
    splitter.setHandleWidth(1)

    # Sidebar
    sidebar = QWidget()
    sidebar.setObjectName("sidebar")
    sidebar.setMinimumWidth(160)
    sidebar.setMaximumWidth(400)
    sb = QVBoxLayout(sidebar)
    sb.setContentsMargins(14, 28, 14, 28)
    sb.setSpacing(3)

    title_lbl = QLabel("Settings")
    title_lbl.setObjectName("appTitle")
    sb.addWidget(title_lbl)
    sb.addSpacing(18)

    stack = QStackedWidget()
    btn_group = QButtonGroup()
    btn_group.setExclusive(True)
    page_stack = []  # _PAGES index → stack index, or None for launch-only items

    def _goto_stack(stack_idx, nav_idx):
        stack.setCurrentIndex(stack_idx)
        btn = btn_group.button(nav_idx)
        if btn is not None:
            btn.setChecked(True)

    def _activate_page(nav_idx):
        target = _PAGES[nav_idx][2]
        if isinstance(target, str):
            _open_gtk_theme_editor()
            return
        stack_idx = page_stack[nav_idx]
        if stack_idx is not None:
            _goto_stack(stack_idx, nav_idx)

    for i, (label, _, target) in enumerate(_PAGES):
        if isinstance(target, str):
            btn = _nav_button(label, external=True)
            page_stack.append(None)
            btn.setCheckable(False)
            btn.clicked.connect(lambda _, idx=i: _activate_page(idx))
        else:
            btn = _nav_button(label)
            page_stack.append(stack.count())
            stack.addWidget(target())
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, idx=i: _activate_page(idx))
            btn_group.addButton(btn, i)
        sb.addWidget(btn)

    sb.addStretch()

    about_nav = len(_PAGES)
    about_stack = stack.count()
    stack.addWidget(AboutTab())
    about_btn = _nav_button("About")
    about_btn.setCheckable(True)
    about_btn.clicked.connect(lambda: _goto_stack(about_stack, about_nav))
    btn_group.addButton(about_btn, about_nav)
    sb.addWidget(about_btn)

    content = QWidget()
    cl = QVBoxLayout(content)
    cl.setContentsMargins(0, 32, 0, 0)
    cl.setSpacing(0)
    cl.addWidget(stack)

    splitter.addWidget(sidebar)
    splitter.addWidget(content)
    splitter.setSizes([260, 700])
    splitter.setStretchFactor(0, 0)
    splitter.setStretchFactor(1, 1)

    root.addWidget(splitter)
    window.setCentralWidget(root_widget)

    # Initial tab from CLI args
    argv = set(sys.argv[1:])
    if {"--themes", "--theme", "--appearance", "--appearence"} & argv:
        _open_gtk_theme_editor()
    initial_nav = 0
    for flags, idx in _TAB_FLAGS:
        if flags & argv:
            if isinstance(_PAGES[idx][2], str):
                break
            initial_nav = idx
            break
    _activate_page(initial_nav)

    # Alt+N shortcuts
    for i in range(len(_PAGES)):
        QShortcut(QKeySequence(f"Alt+{i + 1}"), window).activated.connect(
            lambda idx=i: _activate_page(idx)
        )

    # Reload current page
    def _reload_current():
        w = stack.currentWidget()
        if hasattr(w, '_load'):
            w._load()
        elif hasattr(w, '_scan'):
            w._scan()

    QShortcut(QKeySequence("F5"),     window).activated.connect(_reload_current)
    QShortcut(QKeySequence("Ctrl+R"), window).activated.connect(_reload_current)

    # Ctrl+Tab / Ctrl+Shift+Tab cycle real pages (skip launch-only Themes)
    real_nav = [i for i, p in enumerate(_PAGES) if not isinstance(p[2], str)]
    def _cycle(delta):
        cur = stack.currentIndex()
        try:
            pos = next(i for i, n in enumerate(real_nav) if page_stack[n] == cur)
        except StopIteration:
            pos = 0
        nxt = real_nav[(pos + delta) % len(real_nav)]
        _activate_page(nxt)
    QShortcut(QKeySequence("Ctrl+Tab"), window).activated.connect(lambda: _cycle(1))
    QShortcut(QKeySequence("Ctrl+Shift+Tab"), window).activated.connect(lambda: _cycle(-1))

    # Zoom
    def zoom(delta):
        global _base_font
        _base_font = max(10, min(32, _base_font + delta))
        app.setStyleSheet(_qss())

    QShortcut(QKeySequence("Ctrl+="), window).activated.connect(lambda: zoom(1))
    QShortcut(QKeySequence("Ctrl++"), window).activated.connect(lambda: zoom(1))
    QShortcut(QKeySequence("Ctrl+-"), window).activated.connect(lambda: zoom(-1))
    QShortcut(QKeySequence("Ctrl+0"), window).activated.connect(lambda: zoom(16 - _base_font))

    window.show()
    window.raise_()
    window.activateWindow()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
