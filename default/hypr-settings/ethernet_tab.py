"""Ethernet (wired) NetworkManager settings for hypr-settings."""
from __future__ import annotations

import re
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QButtonGroup,
    QVBoxLayout,
    QWidget,
)

from common import make_centered, run, separator

_SKIP_PREFIXES = ("veth", "docker", "br-", "virbr", "vmnet", "tap", "tun")


def _ethernet_devices() -> list[dict]:
    """Managed ethernet NICs only (skip docker/veth/bridge)."""
    out, ok = run(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device", "status"])
    if not ok:
        return []
    devices: list[dict] = []
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) < 3:
            continue
        dev, typ, state = parts[0], parts[1], ":".join(parts[2:])
        if typ != "ethernet":
            continue
        if state.strip().startswith("unmanaged"):
            continue
        if any(dev.startswith(p) for p in _SKIP_PREFIXES):
            continue
        devices.append({"device": dev, "state": state.strip()})
    return devices


def _device_details(device: str) -> dict:
    out, _ = run(
        [
            "nmcli",
            "-t",
            "-f",
            "GENERAL.DEVICE,GENERAL.STATE,GENERAL.CONNECTION,GENERAL.HWADDR,"
            "WIRED-PROPERTIES.CARRIER,IP4.ADDRESS,IP4.GATEWAY,IP4.DNS",
            "device",
            "show",
            device,
        ]
    )
    info: dict = {"device": device, "dns": []}
    for line in out.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        val = val.strip()
        if not val or val == "--":
            continue
        if key == "GENERAL.STATE":
            info["state"] = val
        elif key == "GENERAL.CONNECTION":
            info["connection"] = val
        elif key == "GENERAL.HWADDR":
            info["mac"] = val
        elif key == "WIRED-PROPERTIES.CARRIER":
            info["carrier"] = val
        elif re.match(r"IP4\.ADDRESS", key):
            info.setdefault("addresses", []).append(val)
            if "ip" not in info:
                parts = val.split("/")
                info["ip"] = parts[0]
                if len(parts) == 2:
                    try:
                        prefix = int(parts[1])
                        mask = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
                        info["subnet"] = ".".join(
                            str((mask >> (8 * i)) & 0xFF) for i in (3, 2, 1, 0)
                        )
                        info["prefix"] = prefix
                    except ValueError:
                        pass
        elif key == "IP4.GATEWAY":
            info["gateway"] = val
        elif re.match(r"IP4\.DNS", key):
            info["dns"].append(val)
    return info


def _connection_for_device(device: str) -> str | None:
    """Active connection name, or first ethernet profile bound to this iface."""
    details = _device_details(device)
    conn = details.get("connection")
    if conn:
        return conn

    out, ok = run(
        ["nmcli", "-t", "-f", "NAME,TYPE,DEVICE", "connection", "show"]
    )
    if not ok:
        return None
    for line in out.splitlines():
        parts = re.split(r"(?<!\\):", line)
        if len(parts) < 3:
            continue
        name, typ, dev = parts[0].replace("\\:", ":"), parts[1], parts[2]
        if typ in ("802-3-ethernet", "ethernet") and (dev == device or not dev):
            return name
    return None


def _ensure_connection(device: str) -> str | None:
    name = _connection_for_device(device)
    if name:
        return name
    con_name = f"Wired connection {device}"
    out, ok = run(
        [
            "nmcli",
            "connection",
            "add",
            "type",
            "ethernet",
            "ifname",
            device,
            "con-name",
            con_name,
        ]
    )
    return con_name if ok else None


def _ipv4_settings(conn: str) -> dict:
    fields = "ipv4.method,ipv4.addresses,ipv4.gateway,ipv4.dns,connection.autoconnect"
    out, ok = run(["nmcli", "-t", "-f", fields, "connection", "show", "id", conn])
    cfg = {"method": "auto", "addresses": "", "gateway": "", "dns": "", "autoconnect": True}
    if not ok:
        return cfg
    for line in out.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        val = val.strip()
        if key == "ipv4.method":
            cfg["method"] = val or "auto"
        elif key == "ipv4.addresses":
            cfg["addresses"] = val
        elif key == "ipv4.gateway":
            cfg["gateway"] = val
        elif key == "ipv4.dns":
            cfg["dns"] = val.replace("|", " ").replace(",", " ")
        elif key == "connection.autoconnect":
            cfg["autoconnect"] = val.lower() == "yes"
    return cfg


class _ApplyThread(QThread):
    done = Signal(bool, str)

    def __init__(self, cmds: list[list[str]]):
        super().__init__()
        self._cmds = cmds

    def run(self):
        last = ""
        for cmd in self._cmds:
            out, ok = run(cmd, timeout=45)
            last = out
            if not ok:
                self.done.emit(False, out or "command failed")
                return
        self.done.emit(True, last)


class EthernetTab(QWidget):
    def __init__(self):
        super().__init__()
        self._apply_thread: _ApplyThread | None = None
        self._devices: list[dict] = []
        self._build_ui()
        self._reload()

    def _build_ui(self):
        root = QVBoxLayout(make_centered(self, max_width=720))
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("Ethernet")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch()
        self._reload_btn = QPushButton("Reload")
        self._reload_btn.clicked.connect(self._reload)
        header.addWidget(self._reload_btn)
        root.addLayout(header)

        self._status = QLabel("")
        self._status.setObjectName("statusLabel")
        self._status.setWordWrap(True)
        root.addWidget(self._status)
        root.addWidget(separator())

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)

        self._dev = QComboBox()
        self._dev.currentIndexChanged.connect(self._on_device_changed)
        form.addRow("Interface", self._dev)

        self._info = QLabel("")
        self._info.setObjectName("statusLabel")
        self._info.setWordWrap(True)
        form.addRow("Status", self._info)

        root.addLayout(form)

        btn_row = QHBoxLayout()
        self._connect_btn = QPushButton("Connect")
        self._connect_btn.clicked.connect(self._connect)
        btn_row.addWidget(self._connect_btn)
        self._disconnect_btn = QPushButton("Disconnect")
        self._disconnect_btn.clicked.connect(self._disconnect)
        btn_row.addWidget(self._disconnect_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)
        root.addWidget(separator())

        sec = QLabel("IPv4")
        sec.setObjectName("sectionTitle")
        root.addWidget(sec)

        self._auto = QRadioButton("Automatic (DHCP)")
        self._manual = QRadioButton("Manual")
        self._method_group = QButtonGroup(self)
        self._method_group.addButton(self._auto)
        self._method_group.addButton(self._manual)
        self._auto.setChecked(True)
        self._auto.toggled.connect(self._on_method_changed)
        root.addWidget(self._auto)
        root.addWidget(self._manual)

        ip_form = QFormLayout()
        ip_form.setLabelAlignment(Qt.AlignRight)
        ip_form.setHorizontalSpacing(16)
        ip_form.setVerticalSpacing(8)

        self._address = QLineEdit()
        self._address.setPlaceholderText("192.168.1.10/24")
        ip_form.addRow("Address", self._address)

        self._gateway = QLineEdit()
        self._gateway.setPlaceholderText("192.168.1.1")
        ip_form.addRow("Gateway", self._gateway)

        self._dns = QLineEdit()
        self._dns.setPlaceholderText("8.8.8.8 1.1.1.1")
        ip_form.addRow("DNS", self._dns)

        root.addLayout(ip_form)

        self._autoconnect = QCheckBox("Connect automatically")
        self._autoconnect.setChecked(True)
        root.addWidget(self._autoconnect)

        apply_row = QHBoxLayout()
        apply_row.addStretch()
        self._apply_btn = QPushButton("Apply")
        self._apply_btn.clicked.connect(self._apply)
        apply_row.addWidget(self._apply_btn)
        root.addLayout(apply_row)

        self._msg = QLabel("")
        self._msg.setObjectName("statusLabel")
        self._msg.setWordWrap(True)
        root.addWidget(self._msg)
        root.addStretch()

        self._on_method_changed()

    def _current_device(self) -> str | None:
        data = self._dev.currentData()
        return str(data) if data else None

    def _reload(self):
        self._devices = _ethernet_devices()
        self._dev.blockSignals(True)
        current = self._current_device()
        self._dev.clear()
        for d in self._devices:
            self._dev.addItem(d["device"], d["device"])
        if current:
            idx = self._dev.findData(current)
            if idx >= 0:
                self._dev.setCurrentIndex(idx)
        self._dev.blockSignals(False)

        if not self._devices:
            self._status.setText(
                "No ethernet interfaces found. Is a cable plugged in / NetworkManager running?"
            )
            self._set_controls_enabled(False)
            self._info.setText("—")
            return

        self._set_controls_enabled(True)
        self._status.setText(f"{len(self._devices)} ethernet interface(s)")
        self._load_device()

    def _set_controls_enabled(self, enabled: bool):
        for w in (
            self._connect_btn,
            self._disconnect_btn,
            self._auto,
            self._manual,
            self._address,
            self._gateway,
            self._dns,
            self._autoconnect,
            self._apply_btn,
        ):
            w.setEnabled(enabled)

    def _on_device_changed(self):
        self._load_device()

    def _on_method_changed(self):
        manual = self._manual.isChecked()
        self._address.setEnabled(manual)
        self._gateway.setEnabled(manual)
        self._dns.setEnabled(manual)

    def _load_device(self):
        device = self._current_device()
        if not device:
            return
        details = _device_details(device)
        conn = details.get("connection") or _connection_for_device(device)

        state = details.get("state", "unknown")
        carrier = details.get("carrier", "?")
        mac = details.get("mac", "—")
        lines = [f"{state}", f"Carrier: {carrier}", f"MAC: {mac}"]
        if details.get("ip"):
            lines.append(f"IP: {details['ip']}" + (f"/{details['prefix']}" if details.get("prefix") else ""))
        if details.get("gateway"):
            lines.append(f"Gateway: {details['gateway']}")
        if details.get("dns"):
            lines.append(f"DNS: {', '.join(details['dns'])}")
        if conn:
            lines.append(f"Profile: {conn}")
        self._info.setText("\n".join(lines))

        connected = "connected" in state.lower() and "externally" not in state.lower()
        self._connect_btn.setEnabled(not connected)
        self._disconnect_btn.setEnabled(bool(conn) and connected)

        if conn:
            cfg = _ipv4_settings(conn)
            if cfg["method"] == "manual":
                self._manual.setChecked(True)
            else:
                self._auto.setChecked(True)
            addr = cfg["addresses"] or ""
            if not addr and details.get("ip") and details.get("prefix"):
                addr = f"{details['ip']}/{details['prefix']}"
            self._address.setText(addr)
            self._gateway.setText(cfg["gateway"] or details.get("gateway", ""))
            dns = cfg["dns"]
            if not dns and details.get("dns"):
                dns = " ".join(details["dns"])
            self._dns.setText(dns)
            self._autoconnect.setChecked(cfg["autoconnect"])
        else:
            self._auto.setChecked(True)
            self._address.clear()
            self._gateway.clear()
            self._dns.clear()
            self._autoconnect.setChecked(True)
        self._on_method_changed()

    def _connect(self):
        device = self._current_device()
        if not device:
            return
        conn = _ensure_connection(device)
        if not conn:
            QMessageBox.warning(self, "Ethernet", "Could not create a connection profile.")
            return
        self._msg.setText(f"Connecting {device}…")
        self._run_cmds([["nmcli", "connection", "up", "id", conn]])

    def _disconnect(self):
        device = self._current_device()
        if not device:
            return
        conn = _connection_for_device(device)
        if not conn:
            self._msg.setText("No active connection.")
            return
        self._msg.setText(f"Disconnecting {device}…")
        self._run_cmds([["nmcli", "connection", "down", "id", conn]])

    def _apply(self):
        device = self._current_device()
        if not device:
            return
        conn = _ensure_connection(device)
        if not conn:
            QMessageBox.warning(self, "Ethernet", "Could not create a connection profile.")
            return

        cmds: list[list[str]] = []
        auto = "yes" if self._autoconnect.isChecked() else "no"
        cmds.append(
            ["nmcli", "connection", "modify", "id", conn, "connection.autoconnect", auto]
        )

        if self._auto.isChecked():
            cmds.append(
                [
                    "nmcli",
                    "connection",
                    "modify",
                    "id",
                    conn,
                    "ipv4.method",
                    "auto",
                    "ipv4.addresses",
                    "",
                    "ipv4.gateway",
                    "",
                    "ipv4.dns",
                    "",
                ]
            )
        else:
            address = self._address.text().strip()
            gateway = self._gateway.text().strip()
            dns = self._dns.text().strip()
            if not address:
                QMessageBox.warning(
                    self, "Ethernet", "Enter an address with prefix, e.g. 192.168.1.10/24"
                )
                return
            if "/" not in address:
                QMessageBox.warning(
                    self, "Ethernet", "Address must include a prefix length, e.g. /24"
                )
                return
            modify = [
                "nmcli",
                "connection",
                "modify",
                "id",
                conn,
                "ipv4.method",
                "manual",
                "ipv4.addresses",
                address,
            ]
            if gateway:
                modify += ["ipv4.gateway", gateway]
            else:
                modify += ["ipv4.gateway", ""]
            if dns:
                modify += ["ipv4.dns", dns]
            else:
                modify += ["ipv4.dns", ""]
            cmds.append(modify)

        # Bring up so changes take effect
        cmds.append(["nmcli", "connection", "up", "id", conn])
        self._msg.setText("Applying…")
        self._run_cmds(cmds)

    def _run_cmds(self, cmds: list[list[str]]):
        if self._apply_thread and self._apply_thread.isRunning():
            return
        self._apply_btn.setEnabled(False)
        self._connect_btn.setEnabled(False)
        self._disconnect_btn.setEnabled(False)
        self._apply_thread = _ApplyThread(cmds)
        self._apply_thread.done.connect(self._on_apply_done)
        self._apply_thread.start()

    def _on_apply_done(self, ok: bool, out: str):
        self._apply_btn.setEnabled(True)
        if ok:
            self._msg.setText("Done.")
        else:
            self._msg.setText(f"Failed: {out.strip() or 'unknown error'}")
            QMessageBox.warning(self, "Ethernet", out.strip() or "Command failed")
        self._reload()
