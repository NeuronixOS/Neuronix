#!/usr/bin/env bash
# Calamares Server profile: purge slim-live GUI + Hyprland runtime, boot to console + SSH.
# Also strip desktop skel/home configs and gtk-apps staged for the live Desktop image.
set -euo pipefail

PURGE_LIST="${NEURONIX_LIVE_PURGE_LIST:-/etc/calamares/neuronix-live-purge.list}"

# Hook 997 installs these into the squashfs outside install-list # --- live ---,
# so they are not always present in the generated purge list. Always include them.
HYPRLAND_RUNTIME=(
	hyprland
	hyprland-guiutils
	hyprpaper
	hyprpicker
	xdg-desktop-portal-hyprland
	ydotool
)

# Desktop-oriented paths under configs/ (~/configs) and matching ~/.config links.
DESKTOP_CONFIG_NAMES=(
	hypr
	waybar
	gtk-3.0
	gtk-4.0
	gtk-apps
	file-templates
	mimeapps.list
	xdg-terminals.list
	gnome-xdg-terminals.list
)

echo "[neuronix-server] Applying Server profile (console + SSH)…"

_collect_installed() {
	local -n _out=$1
	shift
	local pkg
	for pkg in "$@"; do
		[[ -n "$pkg" ]] || continue
		if dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q ' install ok installed'; then
			_out+=("$pkg")
		fi
	done
}

_to_purge=()

if [[ -r "$PURGE_LIST" ]]; then
	mapfile -t _pkgs < <(awk '
		/^[[:space:]]*#/ { next }
		/^[[:space:]]*$/ { next }
		{ print $1 }
	' "$PURGE_LIST")
	_collect_installed _to_purge "${_pkgs[@]}"
else
	echo "[neuronix-server] WARNING: missing $PURGE_LIST — continuing with Hyprland runtime purge only." >&2
fi

_collect_installed _to_purge "${HYPRLAND_RUNTIME[@]}"

# Deduplicate while preserving order
if ((${#_to_purge[@]} > 0)); then
	mapfile -t _to_purge < <(printf '%s\n' "${_to_purge[@]}" | awk 'NF && !seen[$0]++')
fi

if ((${#_to_purge[@]} > 0)); then
	echo "[neuronix-server] Purging ${#_to_purge[@]} GUI / Hyprland packages…"
	export DEBIAN_FRONTEND=noninteractive
	apt-get purge -y "${_to_purge[@]}" || apt-get purge -y --allow-remove-essential "${_to_purge[@]}" || true
	apt-get autoremove -y --purge || true
else
	echo "[neuronix-server] No GUI packages to purge."
fi

rm -f /etc/lightdm/lightdm.conf.d/50-neuronix-live-autologin.conf \
	/etc/lightdm/lightdm.conf.d/98-neuronix-autologin.conf \
	/etc/lightdm/lightdm.conf.d/88-neuronix-hyprland-session.conf \
	/etc/lightdm/lightdm.conf.d/10-neuronix-lightdm-debug.conf 2>/dev/null || true

# Remove staged Desktop session / gtk-apps helpers (not apt packages).
rm -rf /usr/local/lib/neuronix/gtk-apps \
	/usr/share/neuronix/gtk-apps \
	/usr/share/neuronix/gtk-theme \
	/usr/lib/x86_64-linux-gnu/hyprland/plugins \
	/usr/lib/hyprland/plugins 2>/dev/null || true
rm -f /usr/local/bin/gtk-* \
	/usr/share/wayland-sessions/neuronix-hyprland.desktop \
	/usr/share/neuronix/neuronix-hyprland-session*.sh \
	/usr/share/neuronix/neuronix-hyprland-session-env.sh \
	/usr/share/neuronix/neuronix-wallpaper-hyprpaper.sh \
	/usr/share/applications/neuronix-files.desktop \
	/usr/share/applications/neuronix-logout.desktop \
	/usr/share/applications/neuronix-restart.desktop \
	/usr/share/applications/neuronix-reboot.desktop \
	/usr/share/applications/neuronix-shutdown.desktop 2>/dev/null || true
rm -f /usr/local/bin/neuronix-settings \
	/usr/local/bin/neuronix-change-background \
	/usr/local/bin/neuronix-desktop-rmb \
	/usr/local/bin/neuronix-datetime \
	/usr/local/bin/neuronix-calendar \
	/usr/local/bin/neuronix-power-settings \
	/usr/local/bin/neuronix-ensure-power-manager \
	/usr/local/bin/neuronix-ensure-hyprspace \
	/usr/local/bin/neuronix-ensure-hyprbars \
	/usr/local/bin/neuronix-session-action 2>/dev/null || true

_strip_desktop_configs_from() {
	local root="$1"
	local name
	[[ -d "$root" ]] || return 0
	for name in "${DESKTOP_CONFIG_NAMES[@]}"; do
		rm -rf "${root}/configs/${name}" 2>/dev/null || true
	done
	rm -rf "${root}/.config/hypr" \
		"${root}/.config/waybar" \
		"${root}/.config/gtk-3.0" \
		"${root}/.config/gtk-4.0" \
		"${root}/.config/gtk-apps" 2>/dev/null || true
	rm -f "${root}/.config/mimeapps.list" \
		"${root}/.config/xdg-terminals.list" \
		"${root}/.config/gnome-xdg-terminals.list" 2>/dev/null || true
	rm -rf "${root}/Templates" \
		"${root}/.local/share/neuronix" \
		"${root}/.local/bin/x-terminal-emulator" 2>/dev/null || true
}

_strip_desktop_configs_from /etc/skel

# users module runs before this script — clear desktop drop-ins from created homes.
if [[ -d /home ]]; then
	for _home in /home/*; do
		[[ -d "$_home" ]] || continue
		_strip_desktop_configs_from "$_home"
	done
fi

if command -v systemctl >/dev/null 2>&1; then
	systemctl set-default multi-user.target || true
	systemctl disable lightdm.service 2>/dev/null || true
	systemctl mask lightdm.service 2>/dev/null || true
fi

if [[ -x /usr/local/sbin/neuronix-enable-ssh ]]; then
	/usr/local/sbin/neuronix-enable-ssh || true
else
	rm -f /etc/ssh/sshd_not_to_be_run
	systemctl enable ssh.service 2>/dev/null || systemctl enable ssh.socket 2>/dev/null || true
fi

echo "[neuronix-server] Server profile complete (console + SSH)."
