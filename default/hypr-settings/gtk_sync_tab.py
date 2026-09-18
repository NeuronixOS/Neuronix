"""GTK-Sync status and client controls for hypr-settings."""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from shutil import which

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from common import make_centered, run, separator

CFG = Path.home() / ".config/gtk-sync/client.toml"


def _runtime() -> str:
    return os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"


def _status_json() -> Path:
    return Path(_runtime()) / "gtk-sync" / "status.json"


def _which(name: str) -> str | None:
    local = os.path.expanduser(f"~/.local/bin/{name}")
    if os.path.isfile(local) and os.access(local, os.X_OK):
        return local
    return which(name)


def _launch(argv: list[str]) -> None:
    if not argv:
        return
    env = os.environ.copy()
    local = os.path.expanduser("~/.local/bin")
    env["PATH"] = f"{local}:/usr/local/bin:/usr/bin:/bin:" + env.get("PATH", "")
    run_cmd = [
        "systemd-run",
        "--user",
        "--collect",
        "--quiet",
        "--property=KillMode=process",
    ]
    for key in (
        "WAYLAND_DISPLAY",
        "XDG_RUNTIME_DIR",
        "HYPRLAND_INSTANCE_SIGNATURE",
        "DBUS_SESSION_BUS_ADDRESS",
        "DISPLAY",
        "PATH",
        "HOME",
        "XDG_CURRENT_DESKTOP",
    ):
        val = env.get(key)
        if val:
            run_cmd.append(f"--setenv={key}={val}")
    run_cmd.extend(["--", *argv])
    try:
        if subprocess.run(run_cmd, check=False).returncode == 0:
            return
    except FileNotFoundError:
        pass
    subprocess.Popen(
        argv,
        start_new_session=True,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _sync_root() -> str:
    if not CFG.is_file():
        return ""
    try:
        text = CFG.read_text(encoding="utf-8")
    except OSError:
        return ""
    m = re.search(r'(?m)^\s*root\s*=\s*["\']([^"\']+)["\']', text)
    return m.group(1) if m else ""


def _client_active() -> bool:
    _, ok = run(["systemctl", "--user", "is-active", "--quiet", "gtk-sync-client"], timeout=2)
    return ok


def _client_state() -> str:
    if _client_active():
        return "Running"
    _, en = run(["systemctl", "--user", "is-enabled", "--quiet", "gtk-sync-client"], timeout=2)
    if en:
        return "Stopped (enabled at login)"
    if CFG.is_file():
        return "Stopped"
    return "Not set up"


def _activity_line() -> str:
    path = _status_json()
    if not _client_active():
        if not CFG.is_file():
            return "Open Files → Setup Sync to get started"
        return "Client is not running"
    if not path.is_file():
        return "Connected — waiting for status"
    try:
        st = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return "Connected"
    phase = str(st.get("phase") or "idle")
    files = st.get("files") or {}
    pending = sum(1 for v in files.values() if v in ("pending", "syncing"))
    active = st.get("active") or []
    if phase in ("pulling", "pushing") or (st.get("busy") and phase != "scanning"):
        if active:
            a0 = active[0] if isinstance(active[0], dict) else {}
            name = os.path.basename(str(a0.get("path") or "")) or "file"
            direction = str(a0.get("direction") or "")
            arrow = (
                "Downloading"
                if direction == "down"
                else ("Uploading" if direction == "up" else "Syncing")
            )
            extra = max(0, len(active) - 1) + pending
            return f"{arrow} {name}" + (f"  (+{extra} more)" if extra else "")
        if pending:
            return f"Syncing ({pending} files)"
        return f"Syncing ({phase})"
    if phase == "scanning":
        return "Scanning library…"
    if pending:
        return f"Pending ({pending} files)"
    return "Up to date"


def _status_text() -> str:
    state = _client_state()
    root = _sync_root() or "(not configured)"
    line = _activity_line()
    parts = [
        f"Client: {state}",
        f"Activity: {line}",
        f"Folder: {root}",
    ]
    path = _status_json()
    if _client_active() and path.is_file():
        try:
            st = json.loads(path.read_text(encoding="utf-8"))
            parts.append(f"Phase: {st.get('phase') or 'idle'}")
        except Exception:
            pass
    return "\n".join(parts)


def _journal_text() -> str:
    out, _ = run(
        ["journalctl", "--user", "-u", "gtk-sync-client", "-n", "60", "--no-pager"],
        timeout=6,
    )
    return out.strip() or "No recent activity for the sync client yet."


def _server_text() -> str:
    _, sys_ok = run(["systemctl", "is-active", "--quiet", "gtk-sync"], timeout=2)
    if sys_ok:
        body, _ = run(["systemctl", "status", "gtk-sync", "--no-pager", "-l"], timeout=4)
        return "System service: Running\n\n" + "\n".join(body.splitlines()[:20])
    _, user_ok = run(["systemctl", "--user", "is-active", "--quiet", "gtk-sync"], timeout=2)
    if user_ok:
        body, _ = run(
            ["systemctl", "--user", "status", "gtk-sync", "--no-pager", "-l"], timeout=4
        )
        return "User service: Running\n\n" + "\n".join(body.splitlines()[:20])
    return (
        "Not running on this machine.\n\n"
        "That is normal for a client-only setup.\n"
        "The server usually runs on your sync host."
    )


class GtkSyncTab(QWidget):
    def __init__(self):
        super().__init__()
        self._build_ui()
        self._load()
        self._timer = QTimer(self)
        self._timer.setInterval(3000)
        self._timer.timeout.connect(self._load)
        self._timer.start()

    def _build_ui(self):
        root = QVBoxLayout(make_centered(self))
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("GTK-Sync")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._load)
        header.addWidget(refresh)
        root.addLayout(header)

        self._summary = QLabel("Loading…")
        self._summary.setObjectName("statusLabel")
        self._summary.setWordWrap(True)
        self._summary.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self._summary)
        root.addWidget(separator())

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        actions = [
            ("Open folder", self._open_folder),
            ("Start", self._start),
            ("Stop", self._stop),
            ("Restart", self._restart),
            ("Activity log", self._show_journal),
            ("Server", self._show_server),
        ]
        for i, (label, cb) in enumerate(actions):
            btn = QPushButton(label)
            btn.clicked.connect(cb)
            grid.addWidget(btn, i // 2, i % 2)
        root.addLayout(grid)

        self._detail = QTextEdit()
        self._detail.setReadOnly(True)
        self._detail.setMinimumHeight(160)
        self._detail.setPlaceholderText("Details appear here…")
        root.addWidget(self._detail, stretch=1)

    def _load(self):
        self._summary.setText(_status_text())

    def _show(self, text: str):
        self._detail.setPlainText(text)

    def _open_folder(self):
        root = _sync_root()
        if not root or not os.path.isdir(root):
            self._show("No sync folder yet.\nOpen Files and choose Setup Sync first.")
            return
        files = _which("gtk-files") or _which("xdg-open") or "xdg-open"
        _launch([files, root])

    def _start(self):
        if not CFG.is_file():
            self._show("Sync is not set up yet.\nOpen Files and choose Setup Sync first.")
            return
        _, ok = run(
            ["systemctl", "--user", "enable", "--now", "gtk-sync-client"], timeout=10
        )
        self._load()
        self._show("Sync client started." if ok else "Could not start the sync client.")

    def _stop(self):
        run(["systemctl", "--user", "stop", "gtk-sync-client"], timeout=8)
        try:
            path = _status_json()
            if path.is_file():
                path.unlink()
        except Exception:
            pass
        self._load()
        self._show("Sync client stopped.")

    def _restart(self):
        if not CFG.is_file():
            self._show("Sync is not set up yet.\nOpen Files and choose Setup Sync first.")
            return
        _, ok = run(["systemctl", "--user", "restart", "gtk-sync-client"], timeout=10)
        self._load()
        self._show("Sync client restarted." if ok else "Could not restart the sync client.")

    def _show_journal(self):
        self._show(_journal_text())

    def _show_server(self):
        self._show(_server_text())
