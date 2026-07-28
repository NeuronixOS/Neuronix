# shellcheck shell=sh
# Hyprland session environment — Layer B defaults for GTK/Qt/libadwaita apps.

neuronix_libadwaita_dark_mode() {
	command -v python3 >/dev/null 2>&1 || return 0
	DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS}" python3 - <<'PY' 2>/dev/null || true
import gi
gi.require_version("Gio", "2.0")
from gi.repository import Gio

iface = Gio.Settings.new("org.gnome.desktop.interface")
iface.set_string("color-scheme", "prefer-dark")
iface.set_string("gtk-theme", "Adwaita-dark")
if iface.get_string("icon-theme") != "Papirus":
    iface.set_string("icon-theme", "Papirus")
PY
}

neuronix_hyprland_session_env() {
	export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
	export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=${XDG_RUNTIME_DIR}/bus}"
	export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/games${PATH:+:$PATH}"

	export GTK_THEME=Adwaita-dark
	export GSK_RENDERER=cairo
	export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-wayland;xcb}"
	# Make Qt5/Qt6 apps follow GTK Adwaita-dark (Deskflow, VLC, …)
	export QT_QPA_PLATFORMTHEME="${QT_QPA_PLATFORMTHEME:-gtk3}"
	export XDG_CURRENT_DESKTOP=Hyprland
	export XDG_SESSION_DESKTOP=Hyprland
	export GTK_ICON_THEME=Papirus
	export XDG_ICON_THEME=Papirus

	# XWayland for root/X11 GUI helpers (pkexec apps).
	if [ -z "${DISPLAY:-}" ]; then
		if [ -S /tmp/.X11-unix/X0 ]; then
			export DISPLAY=:0
		elif [ -S /tmp/.X11-unix/X1 ]; then
			export DISPLAY=:1
		fi
	fi
	if [ -z "${WAYLAND_DISPLAY:-}" ]; then
		if [ -S "${XDG_RUNTIME_DIR}/wayland-1" ]; then
			export WAYLAND_DISPLAY=wayland-1
		elif [ -S "${XDG_RUNTIME_DIR}/wayland-0" ]; then
			export WAYLAND_DISPLAY=wayland-0
		fi
	fi

	if [ -f /usr/lib/libreoffice/program/libvclplug_gtk3lo.so ]; then
		export SAL_USE_VCLPLUGIN=gtk3
	fi

	neuronix_libadwaita_dark_mode
}
