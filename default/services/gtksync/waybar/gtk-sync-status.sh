#!/usr/bin/env bash
# Waybar custom module: gtk-sync client status (JSON text + tooltip).
# Reads $XDG_RUNTIME_DIR/gtk-sync/status.json only while gtk-sync-client is active.
set -euo pipefail

if [[ -z "${XDG_RUNTIME_DIR:-}" ]]; then
	export XDG_RUNTIME_DIR="/run/user/$(id -u)"
fi
if [[ -z "${DBUS_SESSION_BUS_ADDRESS:-}" && -S "${XDG_RUNTIME_DIR}/bus" ]]; then
	export DBUS_SESSION_BUS_ADDRESS="unix:path=${XDG_RUNTIME_DIR}/bus"
fi

emit() {
	export WB_TEXT="$1" WB_TIP="$2" WB_CLASS="$3"
	python3 - <<'PY'
import json, os
print(json.dumps({
    "text": os.environ["WB_TEXT"],
    "tooltip": os.environ["WB_TIP"],
    "class": os.environ["WB_CLASS"],
}, ensure_ascii=False))
PY
}

have_client_bin() {
	command -v gtk-sync-client >/dev/null 2>&1 \
		|| [[ -x "${HOME}/.local/bin/gtk-sync-client" ]] \
		|| [[ -x /usr/local/bin/gtk-sync-client ]]
}

client_active() {
	systemctl --user is-active --quiet gtk-sync-client 2>/dev/null
}

client_enabled() {
	systemctl --user is-enabled --quiet gtk-sync-client 2>/dev/null
}

sync_root() {
	local cfg="${HOME}/.config/gtk-sync/client.toml"
	[[ -f "$cfg" ]] || return 0
	python3 - "$cfg" <<'PY' 2>/dev/null || true
import re, sys
text = open(sys.argv[1], encoding="utf-8").read()
m = re.search(r'(?m)^\s*root\s*=\s*["\']([^"\']+)["\']', text)
if m:
    print(m.group(1))
PY
}

status_path() {
	local p="${XDG_RUNTIME_DIR}/gtk-sync/status.json"
	if [[ -f "$p" ]]; then
		printf '%s' "$p"
		return
	fi
	p="${HOME}/.config/gtk-sync/status.json"
	[[ -f "$p" ]] && printf '%s' "$p"
}

if ! have_client_bin; then
	emit "Sync ✗" "gtk-sync-client not installed" "missing"
	exit 0
fi

if ! client_active; then
	root="$(sync_root)"
	tip="gtk-sync-client stopped"
	if [[ -n "$root" ]]; then
		tip+=$'\n'"root: ${root}"
	fi
	if client_enabled; then
		tip+=$'\n'"unit enabled but inactive"
	elif [[ ! -f "${HOME}/.config/gtk-sync/client.toml" ]]; then
		tip+=$'\n'"no client.toml — set up Sync in gtk-files"
		emit "Sync ✗" "$tip" "missing"
		exit 0
	fi
	emit "Sync ✗" "$tip" "stopped"
	exit 0
fi

path="$(status_path || true)"
if [[ -z "${path:-}" ]]; then
	root="$(sync_root)"
	tip="gtk-sync-client active (no status.json yet)"
	[[ -n "$root" ]] && tip+=$'\n'"root: ${root}"
	emit "Sync ✓" "$tip" "ok"
	exit 0
fi

python3 - "$path" "$(sync_root)" <<'PY'
import json, os, sys

path = sys.argv[1]
root = sys.argv[2] if len(sys.argv) > 2 else ""

try:
    with open(path, encoding="utf-8") as f:
        st = json.load(f)
except Exception as e:
    print(json.dumps({
        "text": "Sync ⚠",
        "tooltip": f"Could not read status.json:\n{e}",
        "class": "warning",
    }, ensure_ascii=False))
    raise SystemExit(0)

busy = bool(st.get("busy"))
phase = str(st.get("phase") or "idle")
active = st.get("active") or []
files = st.get("files") or {}
pending = sum(1 for v in files.values() if v in ("pending", "syncing"))
transferring = phase in ("pulling", "pushing") or (busy and phase != "scanning")

text = "Sync ✓"
klass = "ok"
line = "Up to date"

if transferring or (busy and phase in ("pulling", "pushing")):
    text = "Sync ↻"
    klass = "syncing"
    if active:
        a0 = active[0] if isinstance(active[0], dict) else {}
        name = os.path.basename(str(a0.get("path") or "")) or "file"
        direction = str(a0.get("direction") or "")
        arrow = "↓" if direction == "down" else ("↑" if direction == "up" else "↻")
        extra = max(0, len(active) - 1) + pending
        if extra:
            line = f"Syncing {arrow} {name} (+{extra} more)"
        else:
            line = f"Syncing {arrow} {name}"
    elif pending:
        line = f"Syncing ({pending} files)"
    else:
        line = f"Syncing ({phase})"
elif phase == "scanning":
    text = "Sync …"
    klass = "syncing"
    line = "Scanning…"
elif pending:
    text = "Sync ↻"
    klass = "syncing"
    line = f"Pending ({pending} files)"

tips = [line, f"phase: {phase}"]
if root:
    tips.append(f"root: {root}")
if active:
    tips.append(f"active transfers: {len(active)}")
if pending:
    tips.append(f"pending/syncing files: {pending}")

print(json.dumps({
    "text": text,
    "tooltip": "\n".join(tips),
    "class": klass,
}, ensure_ascii=False))
PY
