# shellcheck shell=sh
# Hyprpaper wallpaper helpers for neuronix-change-background.
# hyprpaper >= 0.8 uses wallpaper { monitor / path / fit_mode } (old preload= is ignored).
#
# NOTE: hyprpaper 0.8.x on Debian backports segfaults when handling
# `hyprctl hyprpaper wallpaper …` IPC. Always change wallpapers by rewriting
# hyprpaper.conf and restarting the daemon.

neuronix_wallpaper_label() {
	_path="$1"
	_base="$(basename "${_path}")"
	printf '%s' "${_base%.*}"
}

neuronix_wallpaper_resolve() {
	_arg="$1"
	_dir="${WALLPAPER_DIR:-/usr/share/backgrounds/neuronix-installed}"
	case "${_arg}" in
		/*)
			[ -r "${_arg}" ] && printf '%s' "${_arg}"
			;;
		*)
			if [ -r "${_dir}/${_arg}" ]; then
				printf '%s' "${_dir}/${_arg}"
			fi
			;;
	esac
}

neuronix_wallpaper_write_conf() {
	_path="$1"
	_conf="${HOME}/.config/hypr/hyprpaper.conf"
	mkdir -p "$(dirname "${_conf}")"
	# monitor = * → all outputs (empty monitor is unreliable on some 0.8 builds)
	cat >"${_conf}" <<EOF
splash = false
ipc = true

wallpaper {
    monitor = *
    path = ${_path}
    fit_mode = cover
}
EOF
}

neuronix_wallpaper_session_env() {
	# Ensure hyprpaper can attach to the running compositor when started from menus/SSH.
	export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
	if [ -z "${WAYLAND_DISPLAY:-}" ]; then
		if [ -S "${XDG_RUNTIME_DIR}/wayland-1" ]; then
			export WAYLAND_DISPLAY=wayland-1
		elif [ -S "${XDG_RUNTIME_DIR}/wayland-0" ]; then
			export WAYLAND_DISPLAY=wayland-0
		fi
	fi
	if [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] && [ -d "${XDG_RUNTIME_DIR}/hypr" ]; then
		# Newest instance dir wins
		_sig="$(ls -1t "${XDG_RUNTIME_DIR}/hypr" 2>/dev/null | head -1 || true)"
		[ -n "${_sig}" ] && export HYPRLAND_INSTANCE_SIGNATURE="${_sig}"
	fi
}

neuronix_wallpaper_persist() {
	# Keep session-start / next login on the same image.
	_path="$1"
	_dest_dir="${HOME}/.local/share/neuronix"
	_dest="${_dest_dir}/background.png"
	mkdir -p "${_dest_dir}"
	# Prefer hardlink/copy; fall back to path reference only if copy fails.
	if [ -r "${_path}" ]; then
		cp -f "${_path}" "${_dest}" 2>/dev/null || ln -f "${_path}" "${_dest}" 2>/dev/null || true
	fi
}

neuronix_wallpaper_set() {
	_path="$1"
	[ -r "${_path}" ] || return 1
	neuronix_wallpaper_session_env
	neuronix_wallpaper_persist "${_path}"
	# Prefer the persisted copy when present (stable path across boots).
	if [ -r "${HOME}/.local/share/neuronix/background.png" ]; then
		_path="${HOME}/.local/share/neuronix/background.png"
	fi
	neuronix_wallpaper_write_conf "${_path}"

	# Do not use `hyprctl hyprpaper wallpaper` — it crashes hyprpaper 0.8.x.
	pkill -x hyprpaper 2>/dev/null || true
	# Brief pause so the old socket is gone before restart.
	sleep 0.15
	hyprpaper >/dev/null 2>&1 &
	disown 2>/dev/null || true
	return 0
}
