#!/usr/bin/env bash
# Build the Neuronix live ISO.
# Usage: ./build.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
PROFILE="Neuronix"
ISO_DIR="${REPO_ROOT}/neuronix-iso"
METADATA="${REPO_ROOT}/default/metadata/debian.env"
SETUP_SH="${ISO_DIR}/setup.sh"
BUILD_SH="${ISO_DIR}/build.sh"
VALIDATE_SH="${ISO_DIR}/packages/validate-manifest.sh"
MANIFEST_LIB="${ISO_DIR}/packages/manifest-lib.sh"

# Package-list generation inputs/outputs (default/install-list is the base source of truth).
MANIFEST="${REPO_ROOT}/default/install-list"
LIST_DIR="${ISO_DIR}/overlay/package-lists"
CALAMARES_ETC="${REPO_ROOT}/share/calamares-neuronix/etc/calamares"

# Sourced at top level so the parser's arrays stay global, not function-local.
if [[ -r "$MANIFEST_LIB" ]]; then
	# shellcheck source=neuronix-iso/packages/manifest-lib.sh
	source "$MANIFEST_LIB"
fi

if ! command -v tput >/dev/null 2>&1; then
	echo "tput is required (install ncurses-bin)." >&2
	exit 1
fi

if ! tput cols >/dev/null 2>&1; then
	export TERM="${TERM:-xterm-256color}"
fi

_bold="$(tput bold 2>/dev/null || true)"
_dim="$(tput dim 2>/dev/null || true)"
_red="$(tput setaf 1 2>/dev/null || true)"
_green="$(tput setaf 2 2>/dev/null || true)"
_yellow="$(tput setaf 3 2>/dev/null || true)"
_cyan="$(tput setaf 6 2>/dev/null || true)"
_reset="$(tput sgr0 2>/dev/null || true)"

_msg() { printf '%s\n' "$*"; }
_info() { _msg "${_cyan}→${_reset} $*"; }
_ok() { _msg "${_green}✓${_reset} $*"; }
_warn() { _msg "${_yellow}!${_reset} $*" >&2; }
_die() { _msg "${_red}✗${_reset} $*" >&2; exit 1; }

_heading() {
	_msg ""
	_msg "${_bold}${_cyan}$*${_reset}"
	_msg "${_dim}$(printf '%.0s─' $(seq 1 "$(tput cols 2>/dev/null || echo 60)"))${_reset}"
}

_home_path() {
	# Expand a leading ~ or leave absolute/relative paths unchanged.
	local path="$1"
	case "$path" in
	"~/"*) printf '%s' "${HOME}/${path#~/}" ;;
	"~") printf '%s' "${HOME}" ;;
	*) printf '%s' "$path" ;;
	esac
}

ensure_root_access() {
	if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
		return 0
	fi
	if ! command -v sudo >/dev/null 2>&1; then
		_die "sudo is required to remove root-owned build artifacts and run lb build."
	fi
	_msg ""
	_warn "This build needs root access (sudo) for live-build."
	if ! sudo -v; then
		_die "Could not obtain root access."
	fi
	_ok "sudo credentials cached for this session."
}

# VirtualBox and KVM both want VT-x; unload kvm_intel on this host so VBox works.
unload_kvm_for_virtualbox() {
	if ! lsmod | grep -q '^kvm_intel\b'; then
		_info "kvm_intel not loaded — nothing to unload for VirtualBox."
		return 0
	fi
	_info "Unloading kvm_intel (frees VT-x for VirtualBox)…"
	if sudo modprobe -r kvm_intel; then
		_ok "kvm_intel unloaded."
	else
		_warn "Could not unload kvm_intel (in use?). VirtualBox may fail until you free it."
	fi
}

# Default: wipe chroot/config/ISO artifacts but keep apt .deb caches in place.
# Never mv cache/ to /tmp — it is root-owned, has device nodes, and can fill /tmp.
# live-build still apt-updates; unchanged packages reuse cache/packages.*.
# Use --clean to drop the package cache too.
_rm() {
	rm -rf "$@" 2>/dev/null || sudo rm -rf "$@"
}

clean_build_root() {
	local dir="$1"
	local full_clean="${2:-0}"
	local entry name

	if [[ ! -e "$dir" ]]; then
		_info "No existing build directory: ${_dim}${dir}${_reset}"
		return 0
	fi

	if [[ "$full_clean" == "1" ]]; then
		_warn "Full clean (including package cache):"
		_msg "  ${_dim}${dir}${_reset}"
		_rm "$dir"
		_ok "Removed."
		return 0
	fi

	_warn "Cleaning build tree (preserving apt package caches in place):"
	_msg "  ${_dim}${dir}${_reset}"

	# Remove everything except cache/; leave cache/packages.* for lb reuse.
	shopt -s nullglob dotglob
	for entry in "$dir"/*; do
		name="$(basename "$entry")"
		[[ "$name" == "cache" ]] && continue
		_info "Removing ${_dim}${name}${_reset}"
		_rm "$entry"
	done
	shopt -u nullglob dotglob

	if [[ -d "$dir/cache" ]]; then
		# Drop bootstrap chroots / nested junk; keep downloaded .debs.
		for entry in "$dir/cache"/*; do
			[[ -e "$entry" ]] || continue
			name="$(basename "$entry")"
			case "$name" in
				packages.chroot|packages.binary|packages.bootstrap|contents.chroot)
					_info "Keeping ${_dim}cache/${name}${_reset}"
					;;
				*)
					_info "Removing ${_dim}cache/${name}${_reset}"
					_rm "$entry"
					;;
			esac
		done
	fi

	# Leftovers from older broken cache-mv logic (filled /tmp).
	if compgen -G "${TMPDIR:-/tmp}/neuronix-lb-cache.*" >/dev/null 2>&1; then
		_warn "Removing leftover ${_dim}${TMPDIR:-/tmp}/neuronix-lb-cache.*${_reset}"
		_rm "${TMPDIR:-/tmp}"/neuronix-lb-cache.*
	fi

	_ok "Build tree cleaned; apt package caches kept for faster rebuilds."
}

# Regenerate derived package lists from install-list.
# live-build gets live + installer only (slim ISO); Calamares gets server +
# desktop lists (apt on target after unpack) plus live-purge for Server.
declare -A SECTION_PKGS=()

_write_section_list() {
	local section="$1" header="$2" out="$3"
	local pkgs="${SECTION_PKGS[$section]:-}"
	local count=0
	{
		printf '%s\n' "$header"
		printf '%s\n' "$pkgs"
	} >"$out"
	[[ -n "$pkgs" ]] && count="$(printf '%s\n' "$pkgs" | grep -c . || true)"
	_info "wrote ${_dim}${out#"$REPO_ROOT/"}${_reset} (${count} packages)"
}

regen_package_lists() {
	local pkg sec
	local desktop_pkgs="${CALAMARES_ETC}/neuronix-desktop-packages.list"
	local server_pkgs="${CALAMARES_ETC}/neuronix-server-packages.list"
	local live_purge="${CALAMARES_ETC}/neuronix-live-purge.list"

	if ! declare -f neuronix_manifest_load >/dev/null 2>&1; then
		_die "Missing package manifest parser: neuronix-iso/packages/manifest-lib.sh"
	fi
	[[ -r "$MANIFEST" ]] || _die "Missing package manifest: default/install-list"

	neuronix_manifest_load "$MANIFEST"
	if [[ -r "${REPO_ROOT}/personalize/install-list" ]]; then
		_info "Appending ${_dim}personalize/install-list${_reset}"
		neuronix_manifest_append "${REPO_ROOT}/personalize/install-list"
	fi

	SECTION_PKGS=()
	for pkg in "${NEURONIX_MANIFEST_PKGS[@]}"; do
		sec="${NEURONIX_MANIFEST_SECTION[$pkg]}"
		case "$sec" in
			live|installer|server|desktop) ;;
			*)
				_die "Unsupported install-list section '$sec' for package '$pkg' (use live, installer, server, or desktop)"
				;;
		esac
		SECTION_PKGS["$sec"]+="${SECTION_PKGS[$sec]:+$'\n'}$pkg"
	done

	mkdir -p "$LIST_DIR" "$CALAMARES_ETC"
	# Fat lists must never ship on the slim live ISO.
	rm -f "$LIST_DIR"/server.list.chroot "$LIST_DIR"/desktop.list.chroot \
		"$LIST_DIR"/base.list.chroot "$LIST_DIR"/dev.list.chroot \
		"$LIST_DIR"/python.list.chroot

	_write_section_list live \
		"# Slim live ISO — net/browser/BT/settings/Hyprland chrome only
# Source of truth: install-list (# --- live ---)
# Full server/desktop stacks are apt-installed by Calamares after unpack.
# Regenerated by build.sh." \
		"$LIST_DIR/live.list.chroot"

	_write_section_list installer \
		"# Installer (removed from disk install via Calamares packages module)
# Source of truth: install-list (# --- installer ---)
# Regenerated by build.sh." \
		"$LIST_DIR/installer.list.chroot"

	{
		echo "# Server packages: apt-installed on every Calamares install (Desktop and Server)."
		echo "# Not in live-build package-lists. Regenerated by build.sh."
		printf '%s\n' "${SECTION_PKGS[server]:-}"
	} >"$server_pkgs"
	_info "wrote ${_dim}${server_pkgs#"$REPO_ROOT/"}${_reset}"

	{
		echo "# Desktop packages: apt-installed on Desktop profile only."
		echo "# Plus Hyprland/Chrome extras (hooks / Calamares shellprocess)."
		echo "# Cursor is personalize/install only — not stock."
		echo "# Regenerated by build.sh."
		printf '%s\n' "${SECTION_PKGS[desktop]:-}"
		printf '%s\n' \
			hyprland hyprpaper hyprpicker xdg-desktop-portal-hyprland hyprland-guiutils \
			ydotool \
			google-chrome-stable
	} >"$desktop_pkgs"
	_info "wrote ${_dim}${desktop_pkgs#"$REPO_ROOT/"}${_reset}"

	# Keepers stay after a Server install; everything else from live is purged.
	local -A live_keep=(
		[live-boot]=1 [live-boot-initramfs-tools]=1
		[live-config]=1 [live-config-systemd]=1 [live-tools]=1
		[sudo]=1 [systemd-sysv]=1 [linux-image-amd64]=1
		[network-manager]=1 [bluez]=1 [bluetooth]=1 [iproute2]=1
		[curl]=1 [ca-certificates]=1 [openssh-client]=1 [openssh-server]=1 [ssh]=1
		[rsync]=1 [vim]=1 [wget]=1 [gnupg]=1 [gzip]=1 [hostname]=1 [grep]=1
		[debconf]=1 [rsyslog]=1 [fontconfig]=1 [zip]=1 [gdisk]=1 [dconf-cli]=1
		[cron]=1 [btop]=1 [hwinfo]=1 [nmap]=1 [rename]=1 [telnet]=1
		[tree]=1 [traceroute]=1 [whois]=1
	)
	{
		echo "# Live GUI packages purged on Server profile (console + SSH)."
		echo "# Regenerated by build.sh from install-list # --- live ---."
		echo "# Also includes Hyprland runtime from hook 997 (not in live section)."
		while IFS= read -r pkg; do
			[[ -n "$pkg" ]] || continue
			[[ -n "${live_keep[$pkg]:-}" ]] && continue
			printf '%s\n' "$pkg"
		done <<<"${SECTION_PKGS[live]:-}"
		# Hook 997 / Desktop extras present on the live squashfs but outside # --- live ---.
		printf '%s\n' \
			hyprland hyprland-guiutils hyprpaper hyprpicker \
			xdg-desktop-portal-hyprland ydotool
	} >"$live_purge"
	_info "wrote ${_dim}${live_purge#"$REPO_ROOT/"}${_reset}"

	rm -f "${CALAMARES_ETC}/neuronix-desktop-purge.list"
}

main() {
	local full_clean=0
	local lists_only=0
	local -a passthrough=()

	for arg in "$@"; do
		case "$arg" in
			-h|--help|help)
				_heading "Neuronix live ISO builder"
				_msg "Build the Neuronix live ISO (no profile argument needed)."
				_msg ""
				_msg "${_bold}Usage:${_reset}"
				_msg "  ./build.sh              # keep apt package cache (faster rebuilds)"
				_msg "  ./build.sh --clean      # also delete cache/ (full re-download)"
				_msg "  ./build.sh --lists-only # regenerate package lists, then stop"
				_msg ""
				_msg "Regenerates package lists from install-list, runs package preflight"
				_msg "(validate-manifest.sh), then live-build."
				_msg "Each run re-merges overlay/config and rebuilds the ISO from current"
				_msg "Debian indexes; cached .debs are reused when versions still match."
				_msg "Requires sudo for live-build. Output path comes from Neuronix metadata."
				exit 0
				;;
			--clean|-c)
				full_clean=1
				;;
			--lists-only|-l)
				lists_only=1
				;;
			*)
				passthrough+=("$arg")
				;;
		esac
	done
	if ((${#passthrough[@]})); then
		_warn "Extra arguments ignored: ${passthrough[*]}"
	fi

	if [[ ! -x "$SETUP_SH" || ! -x "$BUILD_SH" ]]; then
		_die "Neuronix is not set up yet — missing neuronix-iso/setup.sh or build.sh"
	fi
	if [[ ! -x "$VALIDATE_SH" ]]; then
		_die "Missing package preflight script: neuronix-iso/packages/validate-manifest.sh"
	fi

	local build_root
	if [[ -f "$METADATA" ]]; then
		# shellcheck source=/dev/null
		source "$METADATA"
		if [[ -r "${REPO_ROOT}/personalize/metadata/debian.env" ]]; then
			# shellcheck source=/dev/null
			source "${REPO_ROOT}/personalize/metadata/debian.env"
		fi
		build_root="$(_home_path "${NEURONIX_BUILD_ROOT:-$NEURONIX_BUILD_ROOT_DEFAULT}")"
	else
		_warn "Metadata not found; using default build path."
		build_root="$HOME/neuronix-build-iso"
	fi

	_heading "Preflight: package lists"
	_msg "  Regenerates live/installer lists plus Calamares server/desktop/"
	_msg "  live-purge lists from install-list."
	_msg ""
	regen_package_lists
	_ok "Package lists synced from install-list."

	if [[ "$lists_only" == "1" ]]; then
		_msg ""
		_ok "Package lists only (--lists-only) — skipping ISO build."
		exit 0
	fi

	_heading "Preflight: packages"
	_msg "  Checks install-list ↔ package-lists parity and that every"
	_msg "  *.list.chroot package exists in Debian ${NEURONIX_SUITE:-trixie} (not backports-only)."
	_msg ""
	_info "Running validate-manifest.sh …"
	if ! ( cd "${ISO_DIR}/packages" && ./validate-manifest.sh ); then
		_die "Package validation failed — fix install-list / lists before building (see above)."
	fi
	_ok "Package preflight passed."

	ensure_root_access
	unload_kvm_for_virtualbox

	_heading "Building ${PROFILE}"
	_msg "  ISO scripts:  ${_dim}neuronix-iso${_reset}"
	_msg "  Build output: ${_dim}${build_root}${_reset}"
	if [[ "$full_clean" == "1" ]]; then
		_msg "  Cache:        ${_dim}full wipe (--clean)${_reset}"
	else
		_msg "  Cache:        ${_dim}preserve apt package cache${_reset}"
	fi
	_msg ""

	clean_build_root "$build_root" "$full_clean"

	_info "Running setup.sh …"
	( cd "$ISO_DIR" && ./setup.sh )
	_ok "setup.sh finished."

	_info "Running build.sh …"
	( cd "$ISO_DIR" && ./build.sh )
	_ok "build.sh finished."

	_msg ""
	_ok "${_bold}${PROFILE}${_reset} build complete."
	_msg "  Output: ${_dim}${build_root}${_reset}"
}

main "$@"
