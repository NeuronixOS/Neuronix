#!/bin/sh
# Hyprland exec-once: waybar, mako, hyprpaper, polkit, live Calamares.

set -e

if [ -r /usr/share/neuronix/neuronix-hyprland-session-env.sh ]; then
	# shellcheck source=/usr/share/neuronix/neuronix-hyprland-session-env.sh
	. /usr/share/neuronix/neuronix-hyprland-session-env.sh
	neuronix_hyprland_session_env
fi

if [ -r /usr/share/neuronix/neuronix-session-log.sh ]; then
	# shellcheck source=/usr/share/neuronix/neuronix-session-log.sh
	. /usr/share/neuronix/neuronix-session-log.sh
	neuronix_session_log "hyprland" ""
fi

# Drop stale Hyprland instance dirs left after an unclean logout (old sockets confuse tools).
_hypr_rt="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/hypr"
if [ -d "${_hypr_rt}" ]; then
	_cur="${HYPRLAND_INSTANCE_SIGNATURE:-}"
	for _d in "${_hypr_rt}"/*/; do
		[ -d "${_d}" ] || continue
		_name="$(basename "${_d}")"
		[ -n "${_cur}" ] && [ "${_name}" = "${_cur}" ] && continue
		rm -rf "${_d}" 2>/dev/null || true
	done
fi

# Wallpaper via hyprpaper (0.8+ uses wallpaper { path = ... }, not preload=)
_wall=""
_live=0
grep -qw boot=live /proc/cmdline 2>/dev/null && _live=1

if [ "${_live}" -eq 1 ] && [ -r "${HOME}/.local/share/neuronix/background.png" ]; then
	_wall="${HOME}/.local/share/neuronix/background.png"
else
	for _cand in \
		"${HOME}/.local/share/neuronix/background.png" \
		/usr/share/backgrounds/neuronix-installed/background.png \
		/usr/share/backgrounds/neuronix-installed/background.jpg
	do
		if [ -r "${_cand}" ]; then
			_wall="${_cand}"
			break
		fi
	done
fi

# Last resort: any image in the installed wallpapers dir
if [ -z "${_wall}" ] && [ -d /usr/share/backgrounds/neuronix-installed ]; then
	_wall="$(find /usr/share/backgrounds/neuronix-installed -type f \( -name '*.png' -o -name '*.jpg' -o -name '*.jpeg' -o -name '*.webp' \) | head -1 || true)"
fi

if [ -n "${_wall}" ] && [ -r /usr/share/neuronix/neuronix-wallpaper-hyprpaper.sh ]; then
	# shellcheck disable=SC1091
	. /usr/share/neuronix/neuronix-wallpaper-hyprpaper.sh
	_conf="${HOME}/.config/hypr/hyprpaper.conf"
	_rewrite=0
	if [ ! -f "${_conf}" ]; then
		_rewrite=1
	elif grep -qE 'preload\s*=' "${_conf}" 2>/dev/null; then
		# Migrate pre-0.8 configs so wallpaper actually shows.
		_old="$(sed -n 's/^wallpaper\s*=\s*[^,]*,\s*//p;s/^[[:space:]]*path[[:space:]]*=[[:space:]]*//p' "${_conf}" | head -1)"
		[ -r "${_old}" ] && _wall="${_old}"
		_rewrite=1
	else
		_cur="$(sed -n 's/^[[:space:]]*path[[:space:]]*=[[:space:]]*//p' "${_conf}" | head -1)"
		# Rewrite when missing path, or path points at a non-existent file (common
		# skel bug: background.jpg vs background.png).
		if [ -z "${_cur}" ] || [ ! -r "${_cur}" ]; then
			_rewrite=1
		fi
		# Live session: always pin the live wallpaper on session start.
		if [ "${_live}" -eq 1 ]; then
			_rewrite=1
		fi
	fi
	if [ "${_rewrite}" -eq 1 ]; then
		neuronix_wallpaper_write_conf "${_wall}"
	fi
fi
if command -v hyprpaper >/dev/null 2>&1; then
	# Restart cleanly so a bad first conf cannot leave a blank desktop.
	pkill -x hyprpaper 2>/dev/null || true
	hyprpaper &
fi

# Publish compositor env to user systemd, then bring portals up cleanly.
# Never "restart" portals before WAYLAND_DISPLAY is imported — that races on re-login
# and leaves xdg-desktop-portal-hyprland failed ("Start request repeated too quickly").
if command -v dbus-update-activation-environment >/dev/null 2>&1; then
	dbus-update-activation-environment --systemd \
		WAYLAND_DISPLAY DISPLAY XDG_CURRENT_DESKTOP XDG_SESSION_DESKTOP \
		HYPRLAND_INSTANCE_SIGNATURE \
		GSK_RENDERER GTK_THEME QT_QPA_PLATFORM QT_QPA_PLATFORMTHEME GTK_ICON_THEME XDG_ICON_THEME \
		DBUS_SESSION_BUS_ADDRESS XDG_RUNTIME_DIR 2>/dev/null || true
fi
if command -v systemctl >/dev/null 2>&1; then
	systemctl --user reset-failed \
		xdg-desktop-portal-hyprland.service \
		xdg-desktop-portal-gtk.service \
		xdg-desktop-portal.service \
		2>/dev/null || true
	systemctl --user stop \
		xdg-desktop-portal-hyprland.service \
		xdg-desktop-portal-gtk.service \
		xdg-desktop-portal.service \
		2>/dev/null || true
	(
		# Brief settle so the Wayland socket is accepting clients.
		i=0
		while [ "${i}" -lt 50 ]; do
			[ -n "${WAYLAND_DISPLAY:-}" ] && [ -S "${XDG_RUNTIME_DIR}/${WAYLAND_DISPLAY}" ] && break
			i=$((i + 1))
			sleep 0.1
		done
		systemctl --user start xdg-desktop-portal-gtk.service 2>/dev/null || true
		systemctl --user start xdg-desktop-portal-hyprland.service 2>/dev/null || true
		systemctl --user start xdg-desktop-portal.service 2>/dev/null || true
	) &
fi

waybar &
mako &
# Ensure common XDG dirs exist (screenshots → ~/Pictures, recordings → ~/Videos).
mkdir -p "${HOME}/Pictures" "${HOME}/Videos" "${HOME}/Downloads" "${HOME}/Documents" 2>/dev/null || true
# Volume / brightness OSD (binds use swayosd-client)
if command -v swayosd-server >/dev/null 2>&1; then
	swayosd-server &
fi

# Power manager: no display blank/sleep; no auto brightness reduction
if [ -x /usr/local/bin/neuronix-ensure-power-manager ]; then
	/usr/local/bin/neuronix-ensure-power-manager &
elif command -v xfce4-power-manager >/dev/null 2>&1; then
	xfce4-power-manager --daemon &
fi

# Titlebar buttons (hyprbars) for windows without GTK CSD
if [ -x /usr/local/bin/neuronix-ensure-hyprbars ]; then
	/usr/local/bin/neuronix-ensure-hyprbars &
fi

# Match hyprbars + Waybar / shell chrome to the active GTK suite theme.
# Delay until Hyprland answers. Soft sync only: NEURONIX_THEME_NO_HYPR_RELOAD
# skips `hyprctl reload`, waybar kill/respawn, and portal restarts — those
# freeze the compositor when run during logout→login bring-up.
if [ -f /usr/share/neuronix/gtk-theme/python/gtk_theme.py ]; then
	(
		_i=0
		while [ "${_i}" -lt 40 ]; do
			if command -v hyprctl >/dev/null 2>&1 && hyprctl version >/dev/null 2>&1; then
				break
			fi
			_i=$((_i + 1))
			sleep 0.25
		done
		# Let hyprbars / waybar / portals finish first paint + activation.
		sleep 5
		export NEURONIX_THEME_NO_HYPR_RELOAD=1
		export PYTHONPATH="/usr/share/neuronix/gtk-theme/python${PYTHONPATH:+:$PYTHONPATH}"
		python3 -c "from gtk_theme import sync_desktop_theme; sync_desktop_theme()" >/dev/null 2>&1 || true
	) &
fi

# Workspace overview (Hyprspace) — every login: soft ensure (NO unload/reload;
# that resets upstream hideRealLayers=true and leaves Super black). Apply
# defaults + revive hyprpaper. Delayed retries beat late plugin races.
if [ -x /usr/local/bin/neuronix-fix-hyprspace-now ] || [ -x /usr/local/bin/neuronix-ensure-hyprspace ]; then
	(
		_i=0
		while [ "${_i}" -lt 30 ]; do
			if command -v hyprctl >/dev/null 2>&1 && hyprctl version >/dev/null 2>&1; then
				break
			fi
			_i=$((_i + 1))
			sleep 0.2
		done
		# Soft only — never --force on login.
		if [ -x /usr/local/bin/neuronix-fix-hyprspace-now ]; then
			/usr/local/bin/neuronix-fix-hyprspace-now -q || true
		else
			/usr/local/bin/neuronix-ensure-hyprspace || true
		fi
		sleep 2
		if [ -x /usr/local/bin/neuronix-fix-hyprspace-now ]; then
			/usr/local/bin/neuronix-fix-hyprspace-now -q || true
		else
			/usr/local/bin/neuronix-ensure-hyprspace || true
		fi
		if command -v hyprpaper >/dev/null 2>&1 && ! pgrep -x hyprpaper >/dev/null 2>&1; then
			hyprpaper >/dev/null 2>&1 &
		fi
	) &
fi

# Prefer GNOME agent when present; mate-polkit on native Wayland often shows a
# blank "Authenticate" surface under Hyprland — force XWayland for that agent.
POLKIT_AGENT=""
for _p in /usr/libexec/polkit-gnome-authentication-agent-1 \
	/usr/lib/policykit-1-gnome/polkit-gnome-authentication-agent-1 \
	/usr/libexec/polkit-mate-authentication-agent-1; do
	if [ -x "${_p}" ]; then POLKIT_AGENT="${_p}"; break; fi
done
if [ -n "${POLKIT_AGENT}" ]; then
	_polkit_display="${DISPLAY:-}"
	if [ -z "${_polkit_display}" ]; then
		if [ -S /tmp/.X11-unix/X0 ]; then
			_polkit_display=:0
		elif [ -S /tmp/.X11-unix/X1 ]; then
			_polkit_display=:1
		fi
	fi
	case "${POLKIT_AGENT}" in
	*polkit-mate*)
		env GDK_BACKEND=x11 DISPLAY="${_polkit_display:-:0}" "${POLKIT_AGENT}" &
		;;
	*)
		"${POLKIT_AGENT}" &
		;;
	esac
fi

if grep -qw boot=live /proc/cmdline 2>/dev/null; then
	_lock="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/neuronix-calamares.lock"
	# Stale wrappers hold flock but never show Calamares (xhost fails on Hyprland).
	if ! pgrep -x calamares >/dev/null 2>&1; then
		pkill -f '/usr/bin/calamares-install-debian' 2>/dev/null || true
		pkill -f 'neuronix-calamares-live' 2>/dev/null || true
		rm -f "${_lock}"
	fi
	if command -v flock >/dev/null 2>&1; then
		(
			flock -n 9 || exit 0
			exec neuronix-calamares-live
		) 9>"${_lock}" &
	else
		if [ ! -f "${_lock}" ]; then
			: >"${_lock}"
			neuronix-calamares-live &
		fi
	fi
fi

# First-login personalize/default user hooks (skip live; once per user).
if [ -x /usr/share/neuronix/neuronix-run-user-hooks.sh ]; then
	/usr/share/neuronix/neuronix-run-user-hooks.sh &
fi
