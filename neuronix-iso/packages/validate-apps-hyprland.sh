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
	gparted synaptic remmina kicad mpv mplayer pavucontrol \
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
_check "hyprland.conf (skel)" "$OVERLAY/etc/skel/.config/hypr/hyprland.conf"
_check "gtk-video.desktop" "$OVERLAY/usr/share/applications/gtk-video.desktop"
_check "gtk-video binary (default/gtk-apps)" "$BUILD_ROOT/default/gtk-apps/bin/gtk-video"

if grep -q 'GSK_RENDERER=cairo' "$OVERLAY/usr/share/neuronix/neuronix-hyprland-session-env.sh" 2>/dev/null; then
	echo "  OK  GSK_RENDERER=cairo in session env"
	_ok=$((_ok + 1))
else
	echo "  MISSING  GSK_RENDERER=cairo in session env"
	_fail=$((_fail + 1))
fi

if grep -q 'neuronix-ensure-hyprspace' "$OVERLAY/etc/skel/.config/hypr/hyprland.conf" 2>/dev/null; then
	echo "  OK  hyprland.conf exec-once neuronix-ensure-hyprspace"
	_ok=$((_ok + 1))
else
	echo "  MISSING  neuronix-ensure-hyprspace in hyprland.conf"
	_fail=$((_fail + 1))
fi

_check "neuronix-fix-hyprspace-now" "$OVERLAY/usr/local/bin/neuronix-fix-hyprspace-now"
_check "neuronix-overview-toggle" "$OVERLAY/usr/local/bin/neuronix-overview-toggle"
_check "neuronix-overview-defaults" "$OVERLAY/usr/local/bin/neuronix-overview-defaults"

if grep -q 'neuronix-fix-hyprspace-now' "$OVERLAY/etc/skel/.config/hypr/hyprland.conf" 2>/dev/null; then
	echo "  OK  hyprland.conf delayed neuronix-fix-hyprspace-now"
	_ok=$((_ok + 1))
else
	echo "  MISSING  neuronix-fix-hyprspace-now in hyprland.conf"
	_fail=$((_fail + 1))
fi

if grep -q 'neuronix-fix-hyprspace-now' "$OVERLAY/usr/share/neuronix/neuronix-hyprland-session-start.sh" 2>/dev/null; then
	echo "  OK  session-start runs neuronix-fix-hyprspace-now"
	_ok=$((_ok + 1))
else
	echo "  MISSING  neuronix-fix-hyprspace-now in session-start"
	_fail=$((_fail + 1))
fi

if grep -q '_ensure_hyprpaper' "$OVERLAY/usr/local/bin/neuronix-overview-toggle" 2>/dev/null; then
	echo "  OK  overview-toggle revives hyprpaper"
	_ok=$((_ok + 1))
else
	echo "  MISSING  hyprpaper revive in overview-toggle"
	_fail=$((_fail + 1))
fi

if grep -q 'overview:toggle' "$OVERLAY/etc/skel/.config/hypr/hyprland.conf" 2>/dev/null; then
	echo "  OK  Super → overview:toggle (Hyprspace)"
	_ok=$((_ok + 1))
else
	echo "  MISSING  overview:toggle bind in hyprland.conf"
	_fail=$((_fail + 1))
fi

if grep -q 'neuronix-launch gtk-term' "$OVERLAY/etc/skel/.config/hypr/hyprland.conf" 2>/dev/null; then
	echo "  OK  hyprland.conf binds gtk-term (Neuronix daily terminal)"
	_ok=$((_ok + 1))
else
	echo "  MISSING  gtk-term bind in hyprland.conf"
	_fail=$((_fail + 1))
fi

if grep -q 'neuronix-launch gtk-files' "$OVERLAY/etc/skel/.config/hypr/hyprland.conf" 2>/dev/null; then
	echo "  OK  hyprland.conf binds gtk-files"
	_ok=$((_ok + 1))
else
	echo "  MISSING  gtk-files bind in hyprland.conf"
	_fail=$((_fail + 1))
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
