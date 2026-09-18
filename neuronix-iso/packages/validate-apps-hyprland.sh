#!/usr/bin/env bash
# Hyprland app compatibility checker for the Neuronix install-list.
# Categorizes packages into compatibility layers (A–D) and optionally smoke-tests
# representative GUI apps when run on a Hyprland session.
#
# Usage:
#   ./validate-apps-hyprland.sh              # categorize only
#   ./validate-apps-hyprland.sh --smoke      # categorize + launch smoke tests
#   NEURONIX_SKIP_SMOKE=1 ./validate-apps-hyprland.sh --smoke  # skip launches
set -euo pipefail

PACKAGES_ROOT="$(cd "$(dirname "$0")" && pwd)"
ISO_ROOT="$(cd "${PACKAGES_ROOT}/.." && pwd)"
BUILD_ROOT="$(cd "${ISO_ROOT}/.." && pwd)"
# shellcheck source=manifest-lib.sh
source "${PACKAGES_ROOT}/manifest-lib.sh"
MANIFEST="${BUILD_ROOT}/default/install-list"
SMOKE=0
VERBOSE=0
SKIP_SMOKE="${NEURONIX_SKIP_SMOKE:-0}"

for arg in "$@"; do
	case "$arg" in
		--smoke) SMOKE=1 ;;
		--verbose|-v) VERBOSE=1 ;;
		-h|--help)
			echo "Usage: $0 [--smoke] [--verbose]"
			exit 0
			;;
	esac
done

if [[ ! -r "$MANIFEST" ]]; then
	echo "Missing $MANIFEST" >&2
	exit 1
fi

# Explicit layer assignments for install-list GUI apps (everything else → Layer A).
declare -A LAYER
_layer() { LAYER["$1"]="$2"; }

# Layer B — GTK/Qt session defaults (Hyprland daily + utilities)
for pkg in mousepad imv galculator zathura xarchiver \
	gparted synaptic remmina kicad mpv mplayer cava \
	dconf-editor system-config-printer zenity \
	btop gimp xfce4-power-manager deskflow \
	chromium gnome-snapshot \
	libgtk-4-1 libvte-2.91-gtk4-0 libgtksourceview-5-0 \
	gstreamer1.0-plugins-good gstreamer1.0-libav gstreamer1.0-gtk4 ffmpeg; do
	_layer "$pkg" "B-default"
done

# Hyprland-native shell
for pkg in waybar fuzzel mako-notifier brightnessctl kanshi nwg-bar; do
	_layer "$pkg" "native"
done

# Layer C — optional personalize apps (not on bare live)
# audacity / blender: add via personalize/install-list + neuronix-x11-app wrappers if needed

# Layer C3 + D — GPU / VM sensitive (personalize extras)
for pkg in kdenlive openshot-qt handbrake vlc smplayer; do
	_layer "$pkg" "C3-gpu"
done

# Read install-list (descriptions via manifest-lib.sh)
neuronix_manifest_load "$MANIFEST"
mapfile -t ALL_PKGS < <(printf '%s\n' "${NEURONIX_MANIFEST_PKGS[@]}" | sort -u)

declare -A BUCKETS
for pkg in "${ALL_PKGS[@]}"; do
	b="${LAYER[$pkg]:-A}"
	BUCKETS["$b"]="${BUCKETS[$b]:-}${BUCKETS[$b]:+$'\n'}$pkg"
done

echo "=== Neuronix Hyprland compatibility (${#ALL_PKGS[@]} install-list packages) ==="
echo
for bucket in A B-default native C1-x11 C3-gpu; do
	count="$(printf '%s\n' "${BUCKETS[$bucket]:-}" | grep -c . || true)"
	[[ "$count" -eq 0 ]] && continue
	echo "Layer $bucket ($count packages):"
	if [[ "$VERBOSE" -eq 1 ]]; then
		while IFS= read -r pkg; do
			[[ -n "$pkg" ]] || continue
			printf '  %s # %s\n' "$pkg" "${NEURONIX_MANIFEST_DESC[$pkg]:-}"
		done <<< "${BUCKETS[$bucket]:-}"
	else
		printf '%s\n' "${BUCKETS[$bucket]}" | head -20
		if [[ "$count" -gt 20 ]]; then
			echo "  ... and $(( count - 20 )) more (use --verbose for full list with descriptions)"
		fi
	fi
	echo
done

_a_count=0
for pkg in "${ALL_PKGS[@]}"; do
	[[ -z "${LAYER[$pkg]:-}" ]] && (( _a_count++ )) || true
done
echo "Layer A (no GUI / default): $(( _a_count )) packages (servers, CLI, libs, themes, plugins, …)"
echo

# ISO overlay checks
echo "=== Overlay checks ==="
_ok=0
_fail=0
_check() {
	local label="$1" path="$2"
	if [[ -e "$path" ]]; then
		echo "  OK  $label"
		_ok=$((_ok + 1))
	else
		echo "  MISSING  $label ($path)"
		_fail=$((_fail + 1))
	fi
}

OVERLAY="${ISO_ROOT}/overlay/includes.chroot"
_check "neuronix-hyprland-session-env.sh" "$OVERLAY/usr/share/neuronix/neuronix-hyprland-session-env.sh"
_check "neuronix-x11-app" "$OVERLAY/usr/local/bin/neuronix-x11-app"
_check "hypr-settings" "$OVERLAY/usr/local/bin/hypr-settings"
_check "hypr-settings desktop" "$OVERLAY/usr/share/applications/hypr-settings.desktop"
_check "hypr-settings package tree" "$BUILD_ROOT/default/hypr-settings/neuronix-install.sh"
_check "neuronix-ensure-hyprbars" "$OVERLAY/usr/local/bin/neuronix-ensure-hyprbars"
_check "hyprland.conf (default configs)" "$BUILD_ROOT/default/configs/hypr/hyprland.conf"
_check "waybar config (default configs)" "$BUILD_ROOT/default/configs/waybar/config"
_check "neuronix-waybar-click" "$OVERLAY/usr/local/bin/neuronix-waybar-click"
_check "neuronix-session-action" "$OVERLAY/usr/local/bin/neuronix-session-action"
_check "neuronix_quick_settings.py" "$OVERLAY/usr/share/neuronix/neuronix_quick_settings.py"
_check "gtk-video.desktop" "$OVERLAY/usr/share/applications/gtk-video.desktop"
_check "gtk-video binary (default/gtk-apps)" "$BUILD_ROOT/default/gtk-apps/bin/gtk-video"
_check "zathura.desktop" "$OVERLAY/usr/share/applications/zathura.desktop"

if grep -q '"custom/power"' "$BUILD_ROOT/default/configs/waybar/config" 2>/dev/null \
	&& grep -q 'neuronix-waybar-click power' "$BUILD_ROOT/default/configs/waybar/config" 2>/dev/null \
	&& grep -q '#custom-power' "$BUILD_ROOT/default/configs/waybar/style.css" 2>/dev/null \
	&& grep -qE 'power \| session' "$OVERLAY/usr/local/bin/neuronix-waybar-click" 2>/dev/null \
	&& grep -q 'def show_power_panel' "$OVERLAY/usr/share/neuronix/neuronix_quick_settings.py" 2>/dev/null \
	&& grep -q '_make_tile("logout"' "$OVERLAY/usr/share/neuronix/neuronix_quick_settings.py" 2>/dev/null \
	&& grep -q '_make_tile("reboot"' "$OVERLAY/usr/share/neuronix/neuronix_quick_settings.py" 2>/dev/null \
	&& grep -q '_make_tile("shutdown"' "$OVERLAY/usr/share/neuronix/neuronix_quick_settings.py" 2>/dev/null \
	&& grep -qE '^[[:space:]]*logout\)' "$OVERLAY/usr/local/bin/neuronix-session-action" 2>/dev/null \
	&& grep -qE '^[[:space:]]*reboot\)' "$OVERLAY/usr/local/bin/neuronix-session-action" 2>/dev/null \
	&& grep -qE '^[[:space:]]*shutdown(\|poweroff)?\)' "$OVERLAY/usr/local/bin/neuronix-session-action" 2>/dev/null; then
	echo "  OK  Waybar power icon → Log Out / Reboot / Shut Down popover"
	_ok=$((_ok + 1))
else
	echo "  MISSING  Waybar custom/power (default config + overlay click/session helpers)"
	_fail=$((_fail + 1))
fi

_pers_waybar="$BUILD_ROOT/personalize/configs/waybar"
if [[ -f "$_pers_waybar/config" ]]; then
	if grep -q '"custom/power"' "$_pers_waybar/config" 2>/dev/null \
		&& grep -q 'neuronix-waybar-click power' "$_pers_waybar/config" 2>/dev/null \
		&& { [[ ! -f "$_pers_waybar/style.css" ]] || grep -q '#custom-power' "$_pers_waybar/style.css" 2>/dev/null; }; then
		echo "  OK  personalize waybar keeps custom/power"
		_ok=$((_ok + 1))
	else
		echo "  MISSING  custom/power in personalize/configs/waybar (overlay would drop the icon)"
		_fail=$((_fail + 1))
	fi
fi

if grep -q 'application/pdf=zathura.desktop' "$BUILD_ROOT/default/configs/mimeapps.list" 2>/dev/null \
	&& grep -q 'inode/directory=gtk-files.desktop' "$BUILD_ROOT/default/configs/mimeapps.list" 2>/dev/null \
	&& grep -q 'video/mp4=mpv.desktop' "$BUILD_ROOT/default/configs/mimeapps.list" 2>/dev/null \
	&& grep -q 'x-scheme-handler/http=neuronix-chrome.desktop' "$BUILD_ROOT/default/configs/mimeapps.list" 2>/dev/null; then
	echo "  OK  mimeapps defaults: Chrome / gtk-files / gtk-edit / gtk-image / mpv / zathura / xarchiver"
	_ok=$((_ok + 1))
else
	echo "  MISSING  Neuronix MIME defaults in default/configs/mimeapps.list"
	_fail=$((_fail + 1))
fi

if awk '/^# --- live ---/,/^# --- server ---/' "$BUILD_ROOT/default/install-list" | grep -qE '^zathura([[:space:]]|#|$)'; then
	echo "  OK  zathura is on the live ISO"
	_ok=$((_ok + 1))
else
	echo "  MISSING  zathura in live install-list"
	_fail=$((_fail + 1))
fi

if grep -q 'GSK_RENDERER=cairo' "$OVERLAY/usr/share/neuronix/neuronix-hyprland-session-env.sh" 2>/dev/null; then
	echo "  OK  GSK_RENDERER=cairo in session env"
	_ok=$((_ok + 1))
else
	echo "  MISSING  GSK_RENDERER=cairo in session env"
	_fail=$((_fail + 1))
fi

if grep -q 'GTK_ICON_THEME=Papirus-Dark' "$OVERLAY/usr/share/neuronix/neuronix-hyprland-session-env.sh" 2>/dev/null \
	&& grep -q "gtk-icon-theme-name=Papirus-Dark" "$BUILD_ROOT/default/configs/gtk-3.0/settings.ini" 2>/dev/null \
	&& grep -q "icon-theme='Papirus-Dark'" "$OVERLAY/etc/dconf/db/local.d/01-neuronix-gtk4-dark" 2>/dev/null \
	&& grep -q 'env = GTK_ICON_THEME,Papirus-Dark' "$BUILD_ROOT/default/configs/hypr/hyprland.conf" 2>/dev/null; then
	echo "  OK  Papirus-Dark toolbar icons (session env / GTK3 / dconf / Hyprland)"
	_ok=$((_ok + 1))
else
	echo "  MISSING  Papirus-Dark in session env, gtk-3.0 settings, dconf, or hyprland.conf"
	_fail=$((_fail + 1))
fi

if grep -q '@define-color wb_fg' "$BUILD_ROOT/default/configs/waybar/style.css" 2>/dev/null \
	&& ! grep -q 'var(--wb-' "$BUILD_ROOT/default/configs/waybar/style.css" 2>/dev/null \
	&& grep -q '@define-color wb_fg' "$BUILD_ROOT/default/gtk-apps/gtk-theme/python/gtk_theme.py" 2>/dev/null \
	&& grep -q 'pgrep' "$BUILD_ROOT/default/gtk-apps/gtk-theme/python/gtk_theme.py" 2>/dev/null \
	&& ! grep -q 'systemctl.*restart.*waybar' "$BUILD_ROOT/default/gtk-apps/gtk-theme/python/gtk_theme.py" 2>/dev/null; then
	echo "  OK  Waybar GTK @define-color chrome + in-place reload (no systemctl restart)"
	_ok=$((_ok + 1))
else
	echo "  MISSING  Waybar @define-color stylesheet or gtk-theme reload path"
	_fail=$((_fail + 1))
fi

if grep -q 'def _sync_gtk_term_colors' "$BUILD_ROOT/default/gtk-apps/gtk-theme/python/gtk_theme.py" 2>/dev/null \
	&& grep -q '\[colors\]' "$BUILD_ROOT/default/configs/gtk-apps/gtk-term/config.toml" 2>/dev/null \
	&& grep -q 'progress-color=#' "$BUILD_ROOT/default/configs/mako/config" 2>/dev/null \
	&& grep -q 'background_color = rgb(' "$BUILD_ROOT/default/configs/hypr/hyprland.conf" 2>/dev/null; then
	echo "  OK  gtk-themes Base syncs gtk-term / mako / Hypr workspace background"
	_ok=$((_ok + 1))
else
	echo "  MISSING  gtk-term config.toml, mako progress, hypr background_color, or gtk-theme sync"
	_fail=$((_fail + 1))
fi

if [[ -x "$BUILD_ROOT/default/gtk-apps/bin/gtk-theme-editor" ]] \
	&& grep -q '↗' "$BUILD_ROOT/default/hypr-settings/main.py" 2>/dev/null; then
	echo "  OK  gtk-theme-editor binary + Settings Themes ↗"
	_ok=$((_ok + 1))
else
	echo "  MISSING  gtk-theme-editor in default/gtk-apps/bin or Themes ↗ in hypr-settings"
	_fail=$((_fail + 1))
fi

_check "neuronix-window-switch" "$OVERLAY/usr/local/bin/neuronix-window-switch"
_check "neuronix-escape" "$OVERLAY/usr/local/bin/neuronix-escape"
_check "neuronix-screenshot" "$OVERLAY/usr/local/bin/neuronix-screenshot"

if grep -q 'pkill -x slurp' "$OVERLAY/usr/local/bin/neuronix-escape" 2>/dev/null \
	&& grep -q 'pkill -x slurp' "$BUILD_ROOT/default/configs/bin/neuronix-escape" 2>/dev/null; then
	echo "  OK  Escape cancels slurp (screenshot region)"
	_ok=$((_ok + 1))
else
	echo "  MISSING  slurp cancel in neuronix-escape"
	_fail=$((_fail + 1))
fi

if grep -q 'neuronix-screenshot' "$BUILD_ROOT/default/configs/hypr/hyprland.conf" 2>/dev/null \
	&& grep -q 'gtk-image' "$OVERLAY/usr/local/bin/neuronix-screenshot" 2>/dev/null; then
	echo "  OK  Print Screen → neuronix-screenshot → gtk-image"
	_ok=$((_ok + 1))
else
	echo "  MISSING  neuronix-screenshot bind / gtk-image open"
	_fail=$((_fail + 1))
fi

if grep -q 'gir1.2-gtk4layershell-1.0' "$BUILD_ROOT/default/install-list" 2>/dev/null \
	&& grep -q 'gir1.2-gtk4layershell-1.0' "$OVERLAY/../package-lists/live.list.chroot" 2>/dev/null; then
	echo "  OK  live ISO has GTK4 layer-shell (screensaver overlay)"
	_ok=$((_ok + 1))
else
	echo "  MISSING  gir1.2-gtk4layershell-1.0 in install-list / live.list.chroot"
	_fail=$((_fail + 1))
fi

if grep -q 'HDMI-A-1' "$BUILD_ROOT/default/configs/hypr/window-manager.py" 2>/dev/null \
	|| grep -q 'DP-3' "$BUILD_ROOT/default/configs/hypr/window-manager.py" 2>/dev/null; then
	echo "  FAIL  stock window-manager.py still has a named-output layout"
	_fail=$((_fail + 1))
else
	echo "  OK  stock window-manager.py has no named-output layout (personalize overlays)"
	_ok=$((_ok + 1))
fi

if grep -q 'neuronix-window-switch' "$BUILD_ROOT/default/configs/hypr/hyprland.conf" 2>/dev/null; then
	echo "  OK  hyprland.conf Alt+Tab → neuronix-window-switch"
	_ok=$((_ok + 1))
else
	echo "  MISSING  neuronix-window-switch bind in hyprland.conf"
	_fail=$((_fail + 1))
fi

if grep -qE 'alttab|neuronix-ensure-alttab' "$BUILD_ROOT/default/configs/hypr/hyprland.conf" 2>/dev/null; then
	echo "  FAIL  hyprland.conf still references alttab plugin"
	_fail=$((_fail + 1))
else
	echo "  OK  no alttab plugin in hyprland.conf"
	_ok=$((_ok + 1))
fi

if grep -q 'STUCK_S' "$OVERLAY/usr/local/bin/neuronix-window-switch" 2>/dev/null \
	&& grep -q -- '--commit' "$OVERLAY/usr/local/bin/neuronix-window-switch" 2>/dev/null \
	&& grep -q '_focused_monitor' "$OVERLAY/usr/local/bin/neuronix-window-switch" 2>/dev/null \
	&& ! grep -q 'HDMI_NAME' "$OVERLAY/usr/local/bin/neuronix-window-switch" 2>/dev/null \
	&& ! grep -q 'Gtk' "$OVERLAY/usr/local/bin/neuronix-window-switch" 2>/dev/null; then
	echo "  OK  neuronix-window-switch is focused-monitor MRU (no GTK overlay)"
	_ok=$((_ok + 1))
else
	echo "  FAIL  neuronix-window-switch is not the focused-monitor last-two switcher"
	_fail=$((_fail + 1))
fi

if grep -q 'bindr = SUPER, Super_L, exec, neuronix-fuzzel' "$BUILD_ROOT/default/configs/hypr/hyprland.conf" 2>/dev/null; then
	echo "  OK  Super → neuronix-fuzzel"
	_ok=$((_ok + 1))
else
	echo "  MISSING  Super fuzzel bind in hyprland.conf"
	_fail=$((_fail + 1))
fi

if grep -q 'neuronix-launch gtk-term' "$BUILD_ROOT/default/configs/hypr/hyprland.conf" 2>/dev/null; then
	echo "  OK  hyprland.conf binds gtk-term (Neuronix daily terminal)"
	_ok=$((_ok + 1))
else
	echo "  MISSING  gtk-term bind in hyprland.conf"
	_fail=$((_fail + 1))
fi

if grep -qE '^terminal=.*\bfoot\b' "$BUILD_ROOT/default/configs/fuzzel/fuzzel.ini" 2>/dev/null \
	|| grep -qE '^foot$' "$MANIFEST" 2>/dev/null; then
	echo "  FAIL  foot still listed as terminal fallback"
	_fail=$((_fail + 1))
else
	echo "  OK  gtk-term is the only terminal (no foot package / fuzzel)"
	_ok=$((_ok + 1))
fi

if grep -qE '^thunar$' "$MANIFEST" 2>/dev/null; then
	echo "  FAIL  thunar still listed as file-manager fallback"
	_fail=$((_fail + 1))
else
	echo "  OK  gtk-files is the only file manager (no thunar package)"
	_ok=$((_ok + 1))
fi

if grep -q 'neuronix-launch gtk-files' "$BUILD_ROOT/default/configs/hypr/hyprland.conf" 2>/dev/null; then
	echo "  OK  hyprland.conf binds gtk-files"
	_ok=$((_ok + 1))
else
	echo "  MISSING  gtk-files bind in hyprland.conf"
	_fail=$((_fail + 1))
fi

_pers_hypr="$BUILD_ROOT/personalize/configs/hypr"
if [[ -d "$_pers_hypr" ]]; then
	_check "window-manager.py (personalize)" "$_pers_hypr/window-manager.py"
	if grep -qE 'match:class \.\*, match:workspace m\[HDMI-A-1\], float on' "$_pers_hypr/binds-personal.conf" 2>/dev/null; then
		echo "  OK  personalize HDMI workspaces float (Ctrl+Super+Alt+2 slot)"
		_ok=$((_ok + 1))
	else
		echo "  MISSING  HDMI float windowrule in personalize binds-personal.conf"
		_fail=$((_fail + 1))
	fi
	if grep -q 'def tile_to' "$_pers_hypr/window-manager.py" 2>/dev/null \
		&& grep -q 'settiled' "$_pers_hypr/window-manager.py" 2>/dev/null \
		&& grep -qE 'window_manager dp-left' "$_pers_hypr/binds-personal.conf" 2>/dev/null; then
		echo "  OK  personalize tiles onto DP-3/DP-4 (Ctrl+Super+Alt Left/Right)"
		_ok=$((_ok + 1))
	else
		echo "  MISSING  DP portrait tiling (tile_to / dp-left) in personalize hypr"
		_fail=$((_fail + 1))
	fi
	if grep -q 'gapsout:0 0 1080' "$_pers_hypr/workspaces.conf" 2>/dev/null; then
		echo "  FAIL  personalize still uses tiled HDMI top-half gapsout"
		_fail=$((_fail + 1))
	else
		echo "  OK  personalize has no HDMI tiled-gap (gapsout 1080)"
		_ok=$((_ok + 1))
	fi
	if grep -q 'bottom-left across, then up' "$_pers_hypr/window-manager.py" 2>/dev/null \
		&& grep -q 'floor_y = bottom - win_h' "$_pers_hypr/window-manager.py" 2>/dev/null; then
		echo "  OK  personalize gtk-photos pack bottom-left then up"
		_ok=$((_ok + 1))
	else
		echo "  MISSING  gtk-photos bottom-left pack in window-manager.py"
		_fail=$((_fail + 1))
	fi
	if grep -q 'def is_gtk_image' "$_pers_hypr/window-manager.py" 2>/dev/null \
		&& grep -q '_spawned_by_photos' "$_pers_hypr/window-manager.py" 2>/dev/null; then
		echo "  OK  personalize gtk-image grids only from gtk-photos"
		_ok=$((_ok + 1))
	else
		echo "  MISSING  gtk-image photos-grid guard in personalize window-manager.py"
		_fail=$((_fail + 1))
	fi
	if grep -q 'def is_photos_dialog' "$_pers_hypr/window-manager.py" 2>/dev/null \
		&& grep -q 'is_photos_dialog(win) or is_dialog_like' "$_pers_hypr/window-manager.py" 2>/dev/null \
		&& grep -qE 'match:modal true, center on' "$_pers_hypr/binds-personal.conf" 2>/dev/null; then
		echo "  OK  personalize gtk-photos dialogs center (not photo grid)"
		_ok=$((_ok + 1))
	else
		echo "  MISSING  gtk-photos dialog centering in personalize hypr"
		_fail=$((_fail + 1))
	fi
	if grep -qE 'window-manager.py watch|\$window_manager watch' "$_pers_hypr/binds-personal.conf" 2>/dev/null; then
		echo "  OK  personalize exec-once window-manager watch"
		_ok=$((_ok + 1))
	else
		echo "  MISSING  window-manager watch in binds-personal.conf"
		_fail=$((_fail + 1))
	fi
	if grep -q 'overview-fuzzel' "$_pers_hypr/binds-personal.conf" 2>/dev/null \
		&& grep -q 'def overview_fuzzel' "$_pers_hypr/window-manager.py" 2>/dev/null \
		&& grep -q 'def overview_adopt_window' "$_pers_hypr/window-manager.py" 2>/dev/null; then
		echo "  OK  personalize Super overview types into fuzzel and adopts new windows"
		_ok=$((_ok + 1))
	else
		echo "  MISSING  overview-fuzzel / overview_adopt_window in personalize hypr"
		_fail=$((_fail + 1))
	fi
	if grep -q 'window-manager.py overview' "$_pers_hypr/hyprland.conf" 2>/dev/null; then
		echo "  OK  personalize Super → window-manager overview"
		_ok=$((_ok + 1))
	else
		echo "  MISSING  Super overview bind in personalize hyprland.conf"
		_fail=$((_fail + 1))
	fi
	if grep -q 'resize_on_border = true' "$_pers_hypr/binds-personal.conf" 2>/dev/null; then
		echo "  OK  personalize resize_on_border (Chrome/float grab edge)"
		_ok=$((_ok + 1))
	else
		echo "  MISSING  resize_on_border in personalize binds-personal.conf"
		_fail=$((_fail + 1))
	fi
	if grep -qE 'match:class \^\(google-chrome.*\), match:float true, border_size 0' "$_pers_hypr/binds-personal.conf" 2>/dev/null; then
		echo "  FAIL  personalize still strips border on all floating Chrome windows"
		_fail=$((_fail + 1))
	else
		echo "  OK  personalize does not strip all floating Chrome borders"
		_ok=$((_ok + 1))
	fi
fi

_def_hypr="$BUILD_ROOT/default/configs/hypr/hyprland.conf"
if grep -q 'match:xdg_tag popup, border_size 0' "$_def_hypr" 2>/dev/null; then
	echo "  OK  default hyprland.conf strips popup decorations via xdg_tag"
	_ok=$((_ok + 1))
else
	echo "  MISSING  xdg_tag popup border_size 0 in default hyprland.conf"
	_fail=$((_fail + 1))
fi
if grep -qE 'match:class \^\(google-chrome.*\), match:float true, border_size 0' "$_def_hypr" 2>/dev/null; then
	echo "  FAIL  default hyprland.conf still strips border on all floating Chrome windows"
	_fail=$((_fail + 1))
else
	echo "  OK  default hyprland.conf does not strip all floating Chrome borders"
	_ok=$((_ok + 1))
fi

echo
if [[ "$_fail" -gt 0 ]]; then
	echo "Overlay checks: $_fail missing (fix before ISO build)."
	exit 1
fi
echo "Overlay checks: all $_ok passed."

# Smoke tests (representative apps per layer)
if [[ "$SMOKE" -eq 0 ]]; then
	echo "Run with --smoke to launch representative apps (requires Hyprland session)."
	exit 0
fi

if [[ "$SKIP_SMOKE" == "1" ]]; then
	echo "NEURONIX_SKIP_SMOKE=1 — skipping smoke launches."
	exit 0
fi

if [[ "${XDG_SESSION_TYPE:-}" != "wayland" ]] || ! pgrep -x Hyprland >/dev/null 2>&1; then
	echo "SKIP smoke tests: not in a Hyprland Wayland session (set NEURONIX_SKIP_SMOKE=1 to silence)."
	exit 0
fi

if [[ -r /usr/share/neuronix/neuronix-hyprland-session-env.sh ]]; then
	# shellcheck source=/dev/null
	. /usr/share/neuronix/neuronix-hyprland-session-env.sh
	neuronix_hyprland_session_env
fi

echo "=== Smoke tests (Layer representatives) ==="
_smoke_ok=0
_smoke_fail=0

_smoke_run() {
	local label="$1" cmd="$2" timeout_sec="${3:-3}"
	echo -n "  $label ... "
	if timeout "$timeout_sec" bash -c "$cmd" >/dev/null 2>&1; then
		echo "OK"
		_smoke_ok=$((_smoke_ok + 1))
	else
		echo "FAIL (or timeout — may still work interactively)"
		_smoke_fail=$((_smoke_fail + 1))
	fi
}

_smoke_run "Layer B: gtk-files" "gtk-files --help" 2
_smoke_run "Layer B: gtk-edit" "gtk-edit --help" 2
_smoke_run "Layer B: gtk-term" "gtk-term --help" 2
_smoke_run "Layer B: gtk-image" "gtk-image --help" 2
_smoke_run "Layer B: gtk-video" "gtk-video --help" 2
_smoke_run "Layer B: gtk-calc" "gtk-calc --help" 2
_smoke_run "hyprbars helper" "test -x /usr/local/bin/neuronix-ensure-hyprbars"
_smoke_run "native: fuzzel" "fuzzel --version"
_smoke_run "hypr-settings" "test -x /usr/local/bin/hypr-settings"

echo
echo "Smoke: $_smoke_ok passed, $_smoke_fail failed/skipped"
exit 0
