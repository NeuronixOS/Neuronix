"""Configs tab — Neuronix ~/configs file editor (former gtk-configs)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from configs_lib import apply as applymod
from configs_lib import root as rootmod
from configs_lib.field_widgets import FieldRow
from configs_lib.raw_page import RawPage
from configs_lib.schema import SectionDef, build_schema
from configs_lib.store import ConfigStore


class ConfigsTab(QWidget):
    def __init__(self):
        super().__init__()
        root_path = rootmod.default_root()
        self.store = ConfigStore(root_path)
        self.sections = build_schema()
        self._field_rows: list[FieldRow] = []
        self._section_pages: dict[str, QWidget] = {}
        self._nav_ids: list[str] = []
        self._raw_boxes: dict[str, QVBoxLayout] = {}

        if root_path.is_dir():
            self.store.load_all()

        self._build_ui()
        if root_path.is_dir():
            self._update_files_section()
            self._mark_dirty()
            if "files" in self._nav_ids:
                self.nav.setCurrentRow(self._nav_ids.index("files"))
            elif self.nav.count():
                self.nav.setCurrentRow(0)
        else:
            self.status.setText(
                f"Configs root not found: {root_path}\n"
                "Create ~/configs or symlink your Neuronix configs tree there."
            )

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self._title = QLabel("Configs")
        self._title.setObjectName("pageTitle")
        toolbar.addWidget(self._title)
        self.root_label = QLabel(str(self.store.root))
        self.root_label.setObjectName("statusLabel")
        self.root_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        toolbar.addWidget(self.root_label, stretch=1)

        open_btn = QPushButton("Open folder")
        open_btn.clicked.connect(self._open_folder)
        reload_btn = QPushButton("Reload")
        reload_btn.setToolTip("Reload all files from disk (discards unsaved)")
        reload_btn.clicked.connect(self._reload_disk)
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save)
        apply_btn = QPushButton("Apply")
        apply_btn.setToolTip("Save all + reload Hypr/Waybar/Mako if possible")
        apply_btn.setObjectName("primaryButton")
        apply_btn.clicked.connect(self._save_apply)
        for btn in (open_btn, reload_btn, save_btn, apply_btn):
            toolbar.addWidget(btn)
        outer.addLayout(toolbar)

        body = QHBoxLayout()
        body.setSpacing(10)

        side = QVBoxLayout()
        side.setSpacing(6)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search…")
        self.search.textChanged.connect(self._on_search)
        side.addWidget(self.search)

        self.nav = QListWidget()
        self.nav.setFixedWidth(200)
        self.nav.currentRowChanged.connect(self._on_nav)
        side.addWidget(self.nav, stretch=1)

        self.status = QLabel("No unsaved changes")
        self.status.setObjectName("statusLabel")
        self.status.setWordWrap(True)
        side.addWidget(self.status)
        body.addLayout(side)

        self.stack = QStackedWidget()
        body.addWidget(self.stack, stretch=1)
        outer.addLayout(body, stretch=1)

        for sec in self.sections:
            page = self._build_section_page(sec)
            self._section_pages[sec.id] = page
            self._add_page(sec.id, sec.title, page)

        self.raw_page = RawPage(self.store, on_change=self._mark_dirty)
        self._add_page("raw", "Raw", self.raw_page)

    def _add_page(self, page_id: str, title: str, widget: QWidget) -> None:
        self._nav_ids.append(page_id)
        item = QListWidgetItem(title)
        item.setData(Qt.UserRole, page_id)
        self.nav.addItem(item)
        self.stack.addWidget(widget)

    def _build_section_page(self, sec: SectionDef) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        host = QWidget()
        outer = QVBoxLayout(host)
        outer.setContentsMargins(16, 12, 16, 16)
        outer.setSpacing(10)

        title = QLabel(sec.title)
        title.setObjectName("pageTitle")
        outer.addWidget(title)
        blurb = QLabel(sec.blurb)
        blurb.setWordWrap(True)
        blurb.setObjectName("statusLabel")
        outer.addWidget(blurb)

        fields_box = QVBoxLayout()
        fields_box.setSpacing(6)
        for fdef in sec.fields:
            row = FieldRow(self.store, fdef, on_change=self._on_field_change)
            fields_box.addWidget(row)
            self._field_rows.append(row)
        if sec.fields:
            outer.addLayout(fields_box)

        if sec.raw_files or sec.id == "files":
            raw_frame = QFrame()
            raw_frame.setObjectName("groupFrame")
            raw_layout = QVBoxLayout(raw_frame)
            raw_layout.setContentsMargins(10, 10, 10, 10)
            raw_layout.setSpacing(4)
            raw_title = QLabel("Raw files")
            raw_title.setObjectName("fieldLabel")
            raw_layout.addWidget(raw_title)
            files_box = QVBoxLayout()
            files_box.setSpacing(4)
            raw_layout.addLayout(files_box)
            self._raw_boxes[sec.id] = files_box
            for rel in sec.raw_files:
                self._add_raw_button(files_box, rel)
            outer.addWidget(raw_frame)

        outer.addStretch()
        scroll.setWidget(host)
        return scroll

    def _add_raw_button(self, box: QVBoxLayout, rel: str) -> None:
        exists = self.store.abs(rel).is_file() or rel in getattr(self.store, "_texts", {})
        btn = QPushButton(rel + ("" if exists else " (missing)"))
        btn.setFlat(True)
        btn.setStyleSheet("text-align: left; padding: 4px 6px;")
        if not exists and not self.store.abs(rel).exists():
            btn.setEnabled(False)
        btn.clicked.connect(lambda *_a, r=rel: self.open_raw(r))
        box.addWidget(btn)

    def _update_files_section(self) -> None:
        box = self._raw_boxes.get("files")
        if box is None:
            return
        while box.count():
            item = box.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        for path in rootmod.list_text_files(self.store.root):
            self._add_raw_button(box, self.store.rel(path))
        sec_dir = self.store.root / "secrets"
        if sec_dir.is_dir():
            note = QLabel(
                "secrets/ is present — open via file manager; tokens are not edited here."
            )
            note.setWordWrap(True)
            note.setObjectName("statusLabel")
            box.addWidget(note)

    def open_raw(self, rel: str) -> None:
        self.raw_page.open_file(rel)
        if "raw" in self._nav_ids:
            self.nav.setCurrentRow(self._nav_ids.index("raw"))

    def _on_nav(self, row: int) -> None:
        if row < 0 or row >= len(self._nav_ids):
            return
        self.stack.setCurrentIndex(row)

    def _on_search(self, q: str) -> None:
        q = q.strip()
        for row in self._field_rows:
            row.setVisible(row.matches_filter(q))

    def _update_root_label(self) -> None:
        self.root_label.setText(str(self.store.root))
        dirty = " • modified" if self.store.is_dirty() else ""
        self._title.setText(f"Configs{dirty}")

    def _mark_dirty(self) -> None:
        dirty = self.store.dirty_files()
        if dirty:
            self.status.setText(
                f"{len(dirty)} file(s) modified: " + ", ".join(dirty[:5])
            )
        else:
            self.status.setText("No unsaved changes")
        self._update_root_label()

    def _on_field_change(self) -> None:
        self._mark_dirty()
        self._maybe_theme_reload()

    def _maybe_theme_reload(self) -> None:
        """Refresh hypr-settings chrome when GTK color-scheme keys change."""
        dirty = set(self.store.dirty_files())
        if not dirty.intersection(
            {
                "gtk-3.0/settings.ini",
                "gtk-4.0/settings.ini",
                "xsettingsd/xsettingsd.conf",
            }
        ):
            return
        try:
            from common import on_theme_change

            if not on_theme_change:
                return
            scheme = self.store.get_ini(
                "gtk-4.0/settings.ini", "AdwStyleManager", "color-scheme"
            ) or self.store.get_ini(
                "gtk-3.0/settings.ini", "Settings", "gtk-application-prefer-dark-theme"
            )
            dark = False
            if scheme:
                s = scheme.strip().lower()
                dark = s in ("prefer-dark", "1", "true", "yes", "on")
            on_theme_change(dark)
        except Exception:
            pass

    def _save(self) -> None:
        if not self.store.root.is_dir():
            self.status.setText(f"Missing root: {self.store.root}")
            return
        saved = self.store.save()
        self._mark_dirty()
        self.status.setText("Saved: " + (", ".join(saved) if saved else "(nothing)"))

    def _save_apply(self) -> None:
        if not self.store.root.is_dir():
            self.status.setText(f"Missing root: {self.store.root}")
            return
        saved = self.store.save()
        notes = applymod.apply_for_files(saved)
        self._mark_dirty()
        self.status.setText(" | ".join(["Saved " + ",".join(saved or ["—"])] + notes))
        self._maybe_theme_reload()

    def _reload_disk(self) -> None:
        if not self.store.root.is_dir():
            self.status.setText(f"Missing root: {self.store.root}")
            return
        self.store.reload_from_disk()
        for row in self._field_rows:
            row.refresh()
        self.raw_page.refresh_if_current()
        self._update_files_section()
        self._mark_dirty()
        self.status.setText("Reloaded from disk")

    def _open_folder(self) -> None:
        path = str(self.store.root)
        for cmd in (["xdg-open", path], ["gio", "open", path]):
            try:
                subprocess.Popen(cmd, start_new_session=True)
                return
            except OSError:
                continue


AppearanceTab = ConfigsTab
