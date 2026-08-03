#!/usr/bin/env bash
# Waybar gtk-sync menu — roomy GTK (zenity) dialogs; no terminals.
#
# IMPORTANT: waybar tears down the on-click process group when this script
# exits, so dialogs/apps must be launched via systemd-run --user (or setsid).
set -euo pipefail

if [[ -z "${XDG_RUNTIME_DIR:-}" ]]; then
	export XDG_RUNTIME_DIR="/run/user/$(id -u)"
fi
if [[ -z "${DBUS_SESSION_BUS_ADDRESS:-}" && -S "${XDG_RUNTIME_DIR}/bus" ]]; then
	export DBUS_SESSION_BUS_ADDRESS="unix:path=${XDG_RUNTIME_DIR}/bus"
fi

CFG="${HOME}/.config/gtk-sync/client.toml"
STATUS_JSON="${XDG_RUNTIME_DIR}/gtk-sync/status.json"
TITLE="GTK-Sync"
SELF="$(readlink -f "$0" 2>/dev/null || printf '%s' "$0")"

launch() {
	if command -v systemd-run >/dev/null 2>&1; then
		systemd-run --user --collect --quiet -- "$@" >/dev/null
		return
	fi
	if command -v setsid >/dev/null 2>&1; then
		setsid -f "$@" >/dev/null 2>&1
		return
	fi
	nohup "$@" >/dev/null 2>&1 &
	disown || true
}

have_zenity() { command -v zenity >/dev/null 2>&1; }

dlg_info() {
	local msg="$1"
	if have_zenity; then
		launch zenity --info --title="$TITLE" --width=440 --height=180 \
			--ok-label="OK" --text="$msg"
	else
		notify-send "$TITLE" "$msg" 2>/dev/null || true
	fi
}

dlg_warn() {
	local msg="$1"
	if have_zenity; then
		launch zenity --warning --title="$TITLE" --width=440 --height=180 \
			--ok-label="OK" --text="$msg"
	else
		notify-send "$TITLE" "$msg" 2>/dev/null || true
	fi
}

dlg_error() {
	local msg="$1"
	if have_zenity; then
		launch zenity --error --title="$TITLE" --width=440 --height=180 \
			--ok-label="OK" --text="$msg"
	else
		notify-send "$TITLE" "$msg" 2>/dev/null || true
	fi
}

dlg_text_file() {
	local subtitle="$1" file="$2"
	if have_zenity; then
		launch bash -c 'zenity --text-info --title="$1" --width=580 --height=400 --font="Cantarell 12" --filename="$2"; rm -f "$2"' \
			bash "$TITLE — $subtitle" "$file"
	else
		notify-send "$TITLE — $subtitle" "$(head -c 200 "$file")" 2>/dev/null || true
		rm -f "$file"
	fi
}

sync_root() {
	[[ -f "$CFG" ]] || return 0
	python3 - "$CFG" <<'PY' 2>/dev/null || true
import re, sys
text = open(sys.argv[1], encoding="utf-8").read()
m = re.search(r'(?m)^\s*root\s*=\s*["\']([^"\']+)["\']', text)
if m:
    print(m.group(1))
PY
}

client_active() {
	systemctl --user is-active --quiet gtk-sync-client 2>/dev/null
}

client_state_label() {
	if client_active; then
		echo "Running"
	elif systemctl --user is-enabled --quiet gtk-sync-client 2>/dev/null; then
		echo "Stopped (enabled at login)"
	elif [[ -f "$CFG" ]]; then
		echo "Stopped"
	else
		echo "Not set up"
	fi
}

# Plain multi-line summary for text dialogs.
status_summary() {
	local state root phase busy pending active_n line
	state="$(client_state_label)"
	root="$(sync_root)"
	phase="—"
	busy="no"
	pending=0
	active_n=0
	line="Up to date"

	if client_active && [[ -f "$STATUS_JSON" ]]; then
		eval "$(python3 - "$STATUS_JSON" <<'PY'
import json, os, sys
st = json.load(open(sys.argv[1], encoding="utf-8"))
phase = str(st.get("phase") or "idle")
busy = "yes" if st.get("busy") else "no"
files = st.get("files") or {}
pending = sum(1 for v in files.values() if v in ("pending", "syncing"))
active = st.get("active") or []
active_n = len(active)
line = "Up to date"
if phase in ("pulling", "pushing") or (st.get("busy") and phase != "scanning"):
    if active:
        a0 = active[0] if isinstance(active[0], dict) else {}
        name = os.path.basename(str(a0.get("path") or "")) or "file"
        direction = str(a0.get("direction") or "")
        arrow = "Downloading" if direction == "down" else ("Uploading" if direction == "up" else "Syncing")
        extra = max(0, len(active) - 1) + pending
        line = f"{arrow} {name}" + (f"  (+{extra} more)" if extra else "")
    elif pending:
        line = f"Syncing ({pending} files)"
    else:
        line = f"Syncing ({phase})"
elif phase == "scanning":
    line = "Scanning library…"
elif pending:
    line = f"Pending ({pending} files)"
def q(s):
    return "'" + str(s).replace("'", "'\"'\"'") + "'"
print(f"phase={q(phase)}")
print(f"busy={q(busy)}")
print(f"pending={pending}")
print(f"active_n={active_n}")
print(f"line={q(line)}")
PY
)"
	elif client_active; then
		phase="idle"
		line="Connected — waiting for status"
	elif [[ "$state" == "Not set up" ]]; then
		line="Open Files → Setup Sync to get started"
	else
		line="Client is not running"
	fi

	{
		printf '%s\n\n' "Sync status"
		printf 'Client\n  %s\n\n' "$state"
		printf 'Activity\n  %s\n\n' "$line"
		if [[ -n "$root" ]]; then
			printf 'Folder\n  %s\n' "$root"
		else
			printf 'Folder\n  (not configured)\n'
		fi
		if client_active; then
			printf '\nPhase\n  %s\n\n' "$phase"
			if [[ "${pending:-0}" -gt 0 || "${active_n:-0}" -gt 0 ]]; then
				printf 'Transfers\n  %s active · %s pending\n' "$active_n" "$pending"
			fi
		fi
	}
}

cmd_status_once() {
	if ! have_zenity; then
		notify-send "$TITLE" "$(status_summary | head -c 400)" 2>/dev/null || true
		return 0
	fi
	local tmp
	tmp="$(mktemp)"
	status_summary >"$tmp"
	zenity --text-info --title="$TITLE" --width=460 --height=380 \
		--font="Cantarell 12" --filename="$tmp" --ok-label="Close" || true
	rm -f "$tmp"
}

open_folder() {
	local root
	root="$(sync_root)"
	if [[ -z "$root" || ! -d "$root" ]]; then
		dlg_warn "No sync folder yet.\n\nOpen Files and choose Setup Sync first."
		return
	fi
	if command -v gtk-files >/dev/null 2>&1; then
		launch gtk-files "$root"
	elif command -v xdg-open >/dev/null 2>&1; then
		launch xdg-open "$root"
	else
		dlg_error "No file manager found.\n\n$root"
	fi
}

show_status() {
	launch bash "$SELF" --status
}

start_client() {
	if [[ ! -f "$CFG" ]]; then
		dlg_warn "Sync is not set up yet.\n\nOpen Files and choose Setup Sync first."
		return
	fi
	if systemctl --user enable --now gtk-sync-client 2>/dev/null; then
		dlg_info "Sync client started."
	else
		dlg_error "Could not start the sync client.\n\nIs gtk-sync-client installed?"
	fi
}

stop_client() {
	systemctl --user stop gtk-sync-client 2>/dev/null || true
	rm -f "$STATUS_JSON" 2>/dev/null || true
	rmdir "$(dirname "$STATUS_JSON")" 2>/dev/null || true
	dlg_info "Sync client stopped."
}

restart_client() {
	if [[ ! -f "$CFG" ]]; then
		dlg_warn "Sync is not set up yet.\n\nOpen Files and choose Setup Sync first."
		return
	fi
	if systemctl --user restart gtk-sync-client 2>/dev/null; then
		dlg_info "Sync client restarted."
	else
		dlg_error "Could not restart the sync client."
	fi
}

show_journal() {
	local tmp
	tmp="$(mktemp)"
	journalctl --user -u gtk-sync-client -n 80 --no-pager >"$tmp" 2>&1 || true
	if [[ ! -s "$tmp" ]]; then
		printf '%s\n' "No recent activity for the sync client yet." >"$tmp"
	fi
	dlg_text_file "Recent activity" "$tmp"
}

show_server() {
	local tmp
	tmp="$(mktemp)"
	{
		printf '%s\n\n' "Server"
		if systemctl is-active --quiet gtk-sync 2>/dev/null; then
			printf '%s\n\n' "System service: Running"
			systemctl status gtk-sync --no-pager -l 2>&1 | head -n 20 || true
		elif systemctl --user is-active --quiet gtk-sync 2>/dev/null; then
			printf '%s\n\n' "User service: Running"
			systemctl --user status gtk-sync --no-pager -l 2>&1 | head -n 20 || true
		else
			printf '%s\n\n' "Not running on this machine."
			printf '%s\n' "That is normal for a client-only setup."
			printf '%s\n' "The server usually runs on your sync host."
		fi
	} >"$tmp" 2>&1
	dlg_text_file "Server" "$tmp"
}

case "${1:-}" in
	--status|--status-loop)
		cmd_status_once
		exit 0
		;;
esac

# Menu: Neuronix Settings-style card dialog when available.
choice=""
if [[ -f /usr/share/neuronix/neuronix_choice_dialog.py ]]; then
	choice="$(
		python3 /usr/share/neuronix/neuronix_choice_dialog.py \
			"GTK-Sync" \
			"Choose an action." \
			"open|Open folder|Browse your synced files" \
			"status|Status|See if sync is running" \
			"start|Start|Start the sync client" \
			"stop|Stop|Stop the sync client" \
			"restart|Restart|Restart the sync client" \
			"activity|Activity|Recent sync log" \
			"server|Server|Local server status" \
			2>/dev/null || true
	)"
elif have_zenity; then
	choice="$(
		zenity --list --title="$TITLE" \
			--width=480 --height=420 \
			--text="What would you like to do?" \
			--hide-header \
			--column="Action" --column=" " \
			"Open folder" "Browse your synced files" \
			"Status" "See if sync is running" \
			"Start" "Start the sync client" \
			"Stop" "Stop the sync client" \
			"Restart" "Restart the sync client" \
			"Activity" "Recent sync log" \
			"Server" "Local server status" \
			2>/dev/null || true
	)"
	choice="${choice%%|*}"
else
	choice="$(
		printf '%s\n' \
			"Open folder" "Status" "Start" "Stop" "Restart" "Activity" "Server" |
			fuzzel --dmenu --prompt="GTK-Sync: " --width=28 || true
	)"
fi
choice="$(printf '%s' "${choice:-}" | tr -d '\r' | sed 's/[[:space:]]*$//')"
choice="$(printf '%s' "$choice" | sed 's/[[:space:]]*$//')"

[[ -n "${choice}" ]] || exit 0

case "$choice" in
	open|"Open folder"|"Open Sync Folder") open_folder ;;
	status|"Status") show_status ;;
	start|"Start"|"Start Client") start_client ;;
	stop|"Stop"|"Stop Client") stop_client ;;
	restart|"Restart"|"Restart Client") restart_client ;;
	activity|"Activity"|"Recent Activity") show_journal ;;
	server|"Server"|"Server Status") show_server ;;
	*)
		dlg_warn "Unknown menu item:\n\n${choice}"
		;;
esac
