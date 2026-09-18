"""Raw text editor page (Qt)."""

from __future__ import annotations

from typing import Callable

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class RawPage(QWidget):
    def __init__(self, store, on_change: Callable[[], None] | None = None, parent=None):
        super().__init__(parent)
        self.store = store
        self.on_change = on_change
        self._rel: str | None = None
        self._updating = False

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 16)
        root.setSpacing(8)

        bar = QHBoxLayout()
        self.path_label = QLabel()
        self.path_label.setObjectName("statusLabel")
        bar.addWidget(self.path_label, stretch=1)
        reload_btn = QPushButton("Revert file")
        reload_btn.clicked.connect(self._on_revert)
        bar.addWidget(reload_btn)
        root.addLayout(bar)

        self.view = QPlainTextEdit()
        self.view.setFont(QFont("monospace", 11))
        self.view.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.view.textChanged.connect(self._on_buffer)
        root.addWidget(self.view, stretch=1)

        self._empty = QLabel("Select a file from a section or the Files list.")
        self._empty.setObjectName("statusLabel")
        root.addWidget(self._empty)

        self.view.hide()
        self._empty.show()

    def open_file(self, rel: str) -> None:
        self._rel = rel
        self.path_label.setText(rel)
        self._updating = True
        self.view.setPlainText(self.store.get_text(rel))
        self._updating = False
        self.view.show()
        self._empty.hide()

    def refresh_if_current(self) -> None:
        if self._rel:
            self.open_file(self._rel)

    def _on_buffer(self) -> None:
        if self._updating or not self._rel:
            return
        self.store.set_text(self._rel, self.view.toPlainText())
        if self.on_change:
            self.on_change()

    def _on_revert(self) -> None:
        if not self._rel:
            return
        self.store.discard([self._rel])
        self.refresh_if_current()
        if self.on_change:
            self.on_change()
