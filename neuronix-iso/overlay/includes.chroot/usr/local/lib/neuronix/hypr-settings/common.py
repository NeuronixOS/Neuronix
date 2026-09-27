import subprocess
from PySide6.QtCore import QEasingCurve, QEvent, Property, QPropertyAnimation, Qt, Signal

on_theme_change = None  # set by main.py to (dark: bool) -> None
from PySide6.QtGui import QBrush, QColor, QKeyEvent, QPainter, QPalette
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QStyledItemDelegate,
    QStyle,
    QWidget,
)


def run(cmd, timeout=15):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip(), r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "", False


def separator():
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setFixedHeight(1)
    return f


def make_centered(host, max_width=1100):
    """Wrap host's layout in a centered container with a max width."""
    outer = QHBoxLayout(host)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    inner = QWidget()
    inner.setMaximumWidth(max_width)
    outer.addStretch()
    outer.addWidget(inner, stretch=1)
    outer.addStretch()
    return inner


class ToggleSwitch(QWidget):
    toggled = Signal(bool)

    _W, _H = 48, 24

    def __init__(self):
        super().__init__()
        self._on = False
        self._pos = 0.0  # 0.0 = left (off), 1.0 = right (on)
        self.setFixedSize(self._W, self._H)
        self.setCursor(Qt.PointingHandCursor)

        self._anim = QPropertyAnimation(self, b"handle_pos", self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.InOutQuad)

    def _get_pos(self):
        return self._pos

    def _set_pos(self, val):
        self._pos = val
        self.update()

    handle_pos = Property(float, _get_pos, _set_pos)

    def set_on(self, on, silent=False):
        self._on = on
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()
        if not silent:
            self.toggled.emit(on)

    def is_on(self):
        return self._on

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.set_on(not self._on)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self._W, self._H
        p.setPen(Qt.NoPen)
        # Track: muted surface → suite accent
        off = QColor("#2e2e2e")
        on = QColor("#a3b3d4")
        try:
            from suite_theme import suite_colors

            c = suite_colors()
            if c:
                off = QColor(c["BG_HOVER"])
                on = QColor(c["ACCENT"])
        except Exception:
            pass
        t = self._pos
        tr = int(off.red() + t * (on.red() - off.red()))
        tg = int(off.green() + t * (on.green() - off.green()))
        tb = int(off.blue() + t * (on.blue() - off.blue()))
        p.setBrush(QColor(tr, tg, tb))
        p.drawRoundedRect(0, 0, w, h, h / 2, h / 2)
        m = 3
        d = h - 2 * m
        hx = int(m + self._pos * (w - 2 * m - d))
        handle = QColor("#ffffff")
        try:
            from suite_theme import suite_colors

            c = suite_colors()
            if c:
                handle = QColor(c["ACCENT_TEXT"])
        except Exception:
            pass
        p.setBrush(handle)
        p.drawEllipse(hx, m, d, d)
        p.end()


class _LightRowDelegate(QStyledItemDelegate):
    """Draw list rows in the suite cream, matching QLabel#pageTitle."""

    def paint(self, painter, option, index):
        bg, fg = QColor("#4b4841"), QColor("#ebdbb2")
        accent, on_accent = QColor("#ffbe6f"), QColor("#1d2021")
        hover = QColor("#3c3a36")
        try:
            from suite_theme import suite_colors

            c = suite_colors()
            if c:
                bg = QColor(c["BG_RAISED"])
                fg = QColor(c["TEXT_BRIGHT"])
                accent = QColor(c["ACCENT"])
                on_accent = QColor(c["ACCENT_TEXT"])
                hover = QColor(c["BG_HOVER"])
        except Exception:
            pass
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        fill = accent if selected else (hover if hovered else bg)
        painter.fillRect(option.rect, fill)
        painter.setPen(on_accent if selected else fg)
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        painter.drawText(
            option.rect.adjusted(14, 0, -14, 0),
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            str(text),
        )
        painter.restore()


class NavList(QListWidget):
    """QListWidget with j/k navigation. Opaque cream rows (not GTK black)."""
    _KEY_MAP = {Qt.Key_J: Qt.Key_Down, Qt.Key_K: Qt.Key_Up}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setAutoFillBackground(True)
        self.viewport().setAutoFillBackground(True)
        self.setItemDelegate(_LightRowDelegate(self))
        self._apply_item_chrome()

    def _item_colors(self) -> tuple[QColor, QColor]:
        bg, fg = QColor("#4b4841"), QColor("#ebdbb2")
        try:
            from suite_theme import suite_colors

            c = suite_colors()
            if c:
                bg = QColor(c["BG_RAISED"])
                fg = QColor(c["TEXT_BRIGHT"])
        except Exception:
            pass
        return bg, fg

    def _apply_item_chrome(self) -> None:
        bg, fg = self._item_colors()
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Base, bg)
        pal.setColor(QPalette.ColorRole.AlternateBase, bg)
        pal.setColor(QPalette.ColorRole.Text, fg)
        pal.setColor(QPalette.ColorRole.Window, bg)
        pal.setColor(QPalette.ColorRole.WindowText, fg)
        pal.setColor(QPalette.ColorRole.Button, bg)
        pal.setColor(QPalette.ColorRole.ButtonText, fg)
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#1d2021"))
        self.setPalette(pal)
        self.viewport().setPalette(pal)
        self.viewport().setAutoFillBackground(True)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)

    def addItem(self, item):  # noqa: N802 — Qt API
        if isinstance(item, str):
            item = QListWidgetItem(item)
        _bg, fg = self._item_colors()
        item.setForeground(QBrush(fg))
        super().addItem(item)

    def keyPressEvent(self, e):
        mapped = self._KEY_MAP.get(e.key())
        if mapped is not None:
            e = QKeyEvent(QEvent.KeyPress, mapped, e.modifiers())
        super().keyPressEvent(e)
