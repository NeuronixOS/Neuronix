"""Qt typed field widgets for the Configs file editor."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QWidget,
)

from configs_lib import colors_fmt
from configs_lib.schema import FieldDef, get_field_value, set_field_value


def _qcolor(c: colors_fmt.RGBA) -> QColor:
    return QColor.fromRgbF(c.r, c.g, c.b, c.a)


def _rgba(c: QColor) -> colors_fmt.RGBA:
    return colors_fmt.RGBA(c.redF(), c.greenF(), c.blueF(), c.alphaF())


class FieldRow(QWidget):
    def __init__(
        self,
        store,
        field: FieldDef,
        on_change: Callable[[], None] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.store = store
        self.field = field
        self.on_change = on_change
        self._updating = False

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(12)

        label = QLabel(field.label)
        label.setFixedWidth(200)
        label.setObjectName("fieldLabel")
        row.addWidget(label)

        self._widget_box = QHBoxLayout()
        self._widget_box.setContentsMargins(0, 0, 0, 0)
        self._widget_box.setSpacing(6)
        row.addLayout(self._widget_box, stretch=1)

        self._build()
        self.refresh()

    def _notify(self) -> None:
        if self.on_change and not self._updating:
            self.on_change()

    def _build(self) -> None:
        kind = self.field.kind
        if kind == "color":
            self.color_btn = QPushButton()
            self.color_btn.setFixedSize(36, 28)
            self.color_btn.clicked.connect(self._pick_color)
            self.hex_entry = QLineEdit()
            self.hex_entry.setPlaceholderText("#rrggbb")
            self.hex_entry.setMaximumWidth(160)
            self.hex_entry.editingFinished.connect(self._on_hex)
            self._widget_box.addWidget(self.color_btn)
            self._widget_box.addWidget(self.hex_entry)
            self._widget_box.addStretch()
        elif kind == "int":
            self.spin = QSpinBox()
            self.spin.setRange(
                int(self.field.min_v) if self.field.min_v is not None else -1_000_000,
                int(self.field.max_v) if self.field.max_v is not None else 1_000_000,
            )
            self.spin.valueChanged.connect(self._on_spin)
            self._widget_box.addWidget(self.spin)
            self._widget_box.addStretch()
        elif kind == "float":
            self.spin = QDoubleSpinBox()
            self.spin.setDecimals(2)
            self.spin.setSingleStep(self.field.step or 0.01)
            self.spin.setRange(
                float(self.field.min_v) if self.field.min_v is not None else -1e6,
                float(self.field.max_v) if self.field.max_v is not None else 1e6,
            )
            self.spin.valueChanged.connect(self._on_spin)
            self._widget_box.addWidget(self.spin)
            self._widget_box.addStretch()
        elif kind == "bool":
            self.switch = QCheckBox()
            self.switch.toggled.connect(self._on_switch)
            self._widget_box.addWidget(self.switch)
            self._widget_box.addStretch()
        elif kind == "choice":
            self.dropdown = QComboBox()
            self.dropdown.addItems(self.field.choices or [""])
            self.dropdown.currentIndexChanged.connect(self._on_choice)
            self._widget_box.addWidget(self.dropdown, stretch=1)
        else:
            self.entry = QLineEdit()
            self.entry.editingFinished.connect(self._on_entry)
            self._widget_box.addWidget(self.entry, stretch=1)

    def _set_swatch(self, rgba: colors_fmt.RGBA) -> None:
        c = _qcolor(rgba)
        self.color_btn.setStyleSheet(
            f"QPushButton {{ background: {c.name(QColor.HexArgb)}; border: 1px solid #666; "
            f"border-radius: 4px; }}"
        )
        self.color_btn.setProperty("rgba", rgba)

    def refresh(self) -> None:
        self._updating = True
        val = get_field_value(self.store, self.field)
        kind = self.field.kind
        if kind == "color":
            raw = (val or "").strip()
            rgba = colors_fmt.parse_color(raw, self.field.color_kind) if raw else None  # type: ignore[arg-type]
            if rgba is None and raw:
                rgba = colors_fmt.parse_color(raw, "auto")
            if rgba is None:
                rgba = colors_fmt.RGBA(0, 0, 0, 1)
            self._set_swatch(rgba)
            if raw:
                self.hex_entry.setText(raw)
            elif self.field.color_kind == "fuzzel":
                self.hex_entry.setText(colors_fmt.format_color(rgba, "fuzzel"))
            elif self.field.color_kind == "hypr":
                self.hex_entry.setText(colors_fmt.format_color(rgba, "hypr"))
            else:
                self.hex_entry.setText(rgba.hex6())
        elif kind in ("int", "float"):
            try:
                self.spin.setValue(float(val) if val is not None else 0)
            except (TypeError, ValueError):
                self.spin.setValue(0)
        elif kind == "bool":
            self.switch.setChecked(str(val).lower() in ("1", "true", "yes", "on"))
        elif kind == "choice":
            choices = self.field.choices or []
            idx = choices.index(val) if val in choices else 0
            self.dropdown.setCurrentIndex(idx)
        else:
            self.entry.setText(val or "")
        self._updating = False

    def _pick_color(self) -> None:
        if self._updating:
            return
        current = self.color_btn.property("rgba") or colors_fmt.RGBA(0, 0, 0, 1)
        color = QColorDialog.getColor(
            _qcolor(current), self, "Pick color", QColorDialog.ColorDialogOption.ShowAlphaChannel
        )
        if not color.isValid():
            return
        rgba = _rgba(color)
        old = get_field_value(self.store, self.field) or ""
        if old.strip():
            token = colors_fmt.rewrite_token(old.strip(), rgba)
        else:
            kind = self.field.color_kind if self.field.color_kind != "auto" else "hex"
            token = colors_fmt.format_color(rgba, kind)  # type: ignore[arg-type]
        self._updating = True
        self._set_swatch(rgba)
        self.hex_entry.setText(token)
        self._updating = False
        set_field_value(self.store, self.field, token)
        self._notify()

    def _on_hex(self) -> None:
        if self._updating:
            return
        text = self.hex_entry.text().strip()
        rgba = colors_fmt.parse_color(text, self.field.color_kind)  # type: ignore[arg-type]
        if rgba is None:
            rgba = colors_fmt.parse_color(text, "auto")
        if rgba is None:
            return
        self._updating = True
        self._set_swatch(rgba)
        self._updating = False
        set_field_value(self.store, self.field, text)
        self.refresh()
        self._notify()

    def _on_spin(self, *_a) -> None:
        if self._updating:
            return
        if self.field.kind == "int":
            set_field_value(self.store, self.field, str(int(self.spin.value())))
        else:
            set_field_value(self.store, self.field, f"{self.spin.value():.2f}")
        self._notify()

    def _on_switch(self, checked: bool) -> None:
        if self._updating:
            return
        set_field_value(self.store, self.field, "true" if checked else "false")
        self._notify()

    def _on_choice(self, idx: int) -> None:
        if self._updating:
            return
        choices = self.field.choices or []
        if 0 <= idx < len(choices):
            set_field_value(self.store, self.field, choices[idx])
            self._notify()

    def _on_entry(self) -> None:
        if self._updating:
            return
        set_field_value(self.store, self.field, self.entry.text())
        self._notify()

    def matches_filter(self, q: str) -> bool:
        if not q:
            return True
        blob = (
            f"{self.field.label} {self.field.id} {self.field.key} "
            f"{self.field.search_tags} {self.field.file}"
        ).lower()
        return q.lower() in blob
