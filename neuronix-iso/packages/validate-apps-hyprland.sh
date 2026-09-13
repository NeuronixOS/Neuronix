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
for pkg in foot thunar mousepad imv galculator zathura xarchiver \
	gparted synaptic remmina kicad mpv mplayer pavucontrol cava \
	dconf-editor system-config-printer zenity nwg-displays blueman \
	nm-connection-editor btop gimp nwg-look xfce4-power-manager deskflow \
	chromium gnome-snapshot \
	libgtk-4-1 libvte-2.91-gtk4-0 libgtksourceview-5-0 \
	gstreamer1.0-plugins-good gstreamer1.0-libav gstreamer1.0-gtk4 ffmpeg; do
	_layer "$pkg" "B-default"
done

# Hyprland-native shell
for pkg in waybar fuzzel mako-notifier brightnessctl kanshi; do
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
_check "neuronix-settings" "$OVERLAY/usr/local/bin/neuronix-settings"
_check "neuronix-ensure-hyprbars" "$OVERLAY/usr/local/bin/neuronix-ensure-hyprbars"
_check "hyprland.conf (default configs)" "$BUILD_ROOT/default/configs/hypr/hyprland.conf"
_check "gtk-video.desktop" "$OVERLAY/usr/share/applications/gtk-video.desktop"
_check "gtk-video binary (default/gtk-apps)" "$BUILD_ROOT/default/gtk-apps/bin/gtk-video"

if grep -q 'GSK_RENDERER=cairo' "$OVERLAY/usr/share/neuronix/neuronix-hyprland-session-env.sh" 2>/dev/null; then
	echo "  OK  GSK_RENDERER=cairo in session env"
	_ok=$((_ok + 1))
else
	echo "  MISSING  GSK_RENDERER=cairo in session env"
	_fail=$((_fail + 1))
fi

_check "neuronix-window-switch" "$OVERLAY/usr/local/bin/neuronix-window-switch"
_check "neuronix-escape" "$OVERLAY/usr/local/bin/neuronix-escape"

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
	&& grep -q 'HDMI_NAME' "$OVERLAY/usr/local/bin/neuronix-window-switch" 2>/dev/null \
	&& ! grep -q 'Gtk' "$OVERLAY/usr/local/bin/neuronix-window-switch" 2>/dev/null; then
	echo "  OK  neuronix-window-switch is HDMI MRU (no GTK overlay)"
	_ok=$((_ok + 1))
else
	echo "  FAIL  neuronix-window-switch is not the HDMI last-two switcher"
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
_smoke_run "Layer B fallback: foot" "foot --version"
_smoke_run "hyprbars helper" "test -x /usr/local/bin/neuronix-ensure-hyprbars"
_smoke_run "native: fuzzel" "fuzzel --version"
_smoke_run "settings hub" "test -x /usr/local/bin/neuronix-settings"

echo
echo "Smoke: $_smoke_ok passed, $_smoke_fail failed/skipped"
exit 0
