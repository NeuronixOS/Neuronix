"""Aggregated color swatches across config files (Qt)."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from configs_lib import colors_fmt


def _qcolor(c: colors_fmt.RGBA) -> QColor:
    return QColor.fromRgbF(c.r, c.g, c.b, c.a)


def _rgba(c: QColor) -> colors_fmt.RGBA:
    return colors_fmt.RGBA(c.redF(), c.greenF(), c.blueF(), c.alphaF())


class ColorsPage(QWidget):
    def __init__(
        self,
        store,
        on_change: Callable[[], None] | None = None,
        on_jump: Callable[[str], None] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.store = store
        self.on_change = on_change
        self.on_jump = on_jump
        self._filter = ""
        self._hits: list[colors_fmt.ColorHit] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 16)
        root.setSpacing(8)

        hint = QLabel(
            "Every color token found under the configs root. "
            "Changing a swatch writes back in that file’s native format."
        )
        hint.setWordWrap(True)
        hint.setObjectName("statusLabel")
        root.addWidget(hint)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter colors…")
        self.search.textChanged.connect(self._on_search)
        root.addWidget(self.search)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        self._list_host = QWidget()
        self._list = QVBoxLayout(self._list_host)
        self._list.setContentsMargins(0, 0, 0, 0)
        self._list.setSpacing(4)
        self._list.addStretch()
        scroll.setWidget(self._list_host)
        root.addWidget(scroll, stretch=1)

    def set_filter(self, q: str) -> None:
        self._filter = q
        if self.search.text() != q:
            self.search.setText(q)

    def rebuild(self) -> None:
        while self._list.count() > 1:
            item = self._list.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        self._hits = self.store.scan_colors()
        q = (self._filter or self.search.text() or "").lower()
        for hit in self._hits:
            blob = f"{hit.path_key} {hit.token} {hit.context}".lower()
            if q and q not in blob:
                continue
            self._list.insertWidget(self._list.count() - 1, self._make_row(hit))

    def _make_row(self, hit: colors_fmt.ColorHit) -> QWidget:
        row = QWidget()
        box = QHBoxLayout(row)
        box.setContentsMargins(4, 4, 4, 4)
        box.setSpacing(10)

        rgba = colors_fmt.parse_color(hit.token, hit.kind) or colors_fmt.RGBA(0, 0, 0)
        btn = QPushButton()
        btn.setFixedSize(36, 28)
        btn.setStyleSheet(
            f"QPushButton {{ background: {_qcolor(rgba).name(QColor.HexArgb)}; "
            f"border: 1px solid #666; border-radius: 4px; }}"
        )
        btn.setProperty("hit", hit)
        btn.setProperty("rgba", rgba)
        tok = QLabel(hit.token)
        tok.setTextInteractionFlags(Qt.TextSelectableByMouse)

        def pick(*_a, button=btn, token_lbl=tok, h=hit):
            current = button.property("rgba") or colors_fmt.RGBA(0, 0, 0)
            color = QColorDialog.getColor(
                _qcolor(current),
                self,
                "Pick color",
                QColorDialog.ColorDialogOption.ShowAlphaChannel,
            )
            if not color.isValid():
                return
            new = _rgba(color)
            self.store.set_color_hit(h, new)
            button.setProperty("rgba", new)
            button.setStyleSheet(
                f"QPushButton {{ background: {color.name(QColor.HexArgb)}; "
                f"border: 1px solid #666; border-radius: 4px; }}"
            )
            token_lbl.setText(colors_fmt.rewrite_token(h.token, new))
            if self.on_change:
                self.on_change()

        btn.clicked.connect(pick)
        box.addWidget(btn)

        info = QVBoxLayout()
        info.setSpacing(2)
        path_l = QLabel(hit.path_key)
        path_l.setObjectName("statusLabel")
        ctx = QLabel(hit.context)
        ctx.setObjectName("statusLabel")
        ctx.setWordWrap(True)
        info.addWidget(path_l)
        info.addWidget(tok)
        info.addWidget(ctx)
        box.addLayout(info, stretch=1)

        jump = QPushButton("Raw")
        jump.clicked.connect(lambda *_a, p=hit.path_key: self.on_jump(p) if self.on_jump else None)
        box.addWidget(jump)
        return row

    def _on_search(self, text: str) -> None:
        self._filter = text
        self.rebuild()
