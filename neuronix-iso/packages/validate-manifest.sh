#!/usr/bin/env bash
# Validate overlay/package-lists against a Debian suite (default: trixie).
# Cross-checks install-list (@manifest-format: 1) for parity and descriptions.
#
# Package-list entries must resolve in the *base suite* (main/contrib/non-free),
# not only in suite-backports — live-build installs .list.chroot packages before
# hook 997 enables/uses backports.
#
# Usage:
#   ./validate-manifest.sh              # apt resolve + install-list parity
#   ./validate-manifest.sh --list       # TSV: package, section, description
#   ./validate-manifest.sh --describe PKG
set -euo pipefail

PACKAGES_ROOT="$(cd "$(dirname "$0")" && pwd)"
ISO_ROOT="$(cd "${PACKAGES_ROOT}/.." && pwd)"
BUILD_ROOT="$(cd "${ISO_ROOT}/.." && pwd)"
# shellcheck source=manifest-lib.sh
source "${PACKAGES_ROOT}/manifest-lib.sh"

LIST_DIR="${ISO_ROOT}/overlay/package-lists"
MANIFEST="${BUILD_ROOT}/default/install-list"
METADATA="${BUILD_ROOT}/default/metadata/debian.env"
SUITE="${NEURONIX_VALIDATE_SUITE:-}"
ARCH="${NEURONIX_VALIDATE_ARCH:-amd64}"
MODE=validate
DESCRIBE_PKG=""

if [[ -z "$SUITE" && -r "$METADATA" ]]; then
	# shellcheck source=/dev/null
	source "$METADATA"
	SUITE="${NEURONIX_SUITE:-trixie}"
fi
SUITE="${SUITE:-trixie}"

for arg in "$@"; do
	case "$arg" in
		--list) MODE=list ;;
		--describe) MODE=describe ;;
		-h|--help)
			cat <<'EOF'
Usage: validate-manifest.sh [--list] [--describe PKG]

  (default)  Verify live-build package-lists resolve in apt and match
             install-list live+installer sections; check Calamares lists
  --list     Print install-list as TSV (package, section, description)
  --describe Print one package description from install-list

Checks the base suite only (not *-backports). Packages that exist solely in
backports belong in hook 997 (Hyprland stack), not in *.list.chroot.
Server/desktop packages are validated via Calamares list coverage, not live-build.
EOF
			exit 0
			;;
		-*)
			;;
		*)
			if [[ "$MODE" == "describe" && -z "$DESCRIBE_PKG" ]]; then
				DESCRIBE_PKG="$arg"
			fi
			;;
	esac
done

if [[ ! -d "$LIST_DIR" ]]; then
	echo "Missing $LIST_DIR" >&2
	exit 1
fi

if [[ ! -r "$MANIFEST" ]]; then
	echo "Missing $MANIFEST" >&2
	exit 1
fi

neuronix_manifest_load "$MANIFEST"

if [[ "$MODE" == "describe" ]]; then
	if [[ -z "$DESCRIBE_PKG" ]]; then
		echo "Usage: validate-manifest.sh --describe PACKAGENAME" >&2
		exit 1
	fi
	printf '%s\t%s\t%s\n' \
		"$DESCRIBE_PKG" \
		"${NEURONIX_MANIFEST_SECTION[$DESCRIBE_PKG]:-}" \
		"${NEURONIX_MANIFEST_DESC[$DESCRIBE_PKG]:-missing from install-list}"
	exit 0
fi

if [[ "$MODE" == "list" ]]; then
	neuronix_manifest_print_tsv
	exit 0
fi

declare -A PKG_SOURCE
while IFS= read -r -d '' _list; do
	_list_base="$(basename "$_list")"
	while IFS= read -r _line || [[ -n "$_line" ]]; do
		_pkg="$(neuronix_manifest_pkg_only "$_line")"
		[[ -n "$_pkg" ]] || continue
		if [[ -z "${PKG_SOURCE[$_pkg]:-}" ]]; then
			PKG_SOURCE["$_pkg"]="$_list_base"
		else
			PKG_SOURCE["$_pkg"]+=", $_list_base"
		fi
	done <"$_list"
done < <(find "$LIST_DIR" -maxdepth 1 -name '*.list.chroot' -print0 | sort -z)

mapfile -t PACKAGES < <(printf '%s\n' "${!PKG_SOURCE[@]}" | sort -u)

if ((${#PACKAGES[@]} == 0)); then
	echo "No packages found in $LIST_DIR/*.list.chroot" >&2
	exit 1
fi

# install-list ↔ live-build package-lists parity (live + installer only)
declare -A LIST_SET
for pkg in "${PACKAGES[@]}"; do LIST_SET["$pkg"]=1; done

_expected_live=()
for pkg in "${NEURONIX_MANIFEST_PKGS[@]}"; do
	sec="${NEURONIX_MANIFEST_SECTION[$pkg]}"
	[[ "$sec" == "live" || "$sec" == "installer" ]] || continue
	_expected_live+=("$pkg")
done

declare -A EXPECT_SET
for pkg in "${_expected_live[@]}"; do EXPECT_SET["$pkg"]=1; done

_manifest_only=()
_list_only=()
for pkg in "${_expected_live[@]}"; do
	[[ -z "${LIST_SET[$pkg]:-}" ]] && _manifest_only+=("$pkg")
done
for pkg in "${PACKAGES[@]}"; do
	[[ -z "${EXPECT_SET[$pkg]:-}" ]] && _list_only+=("$pkg")
done

if ((${#_manifest_only[@]} || ${#_list_only[@]})); then
	echo "install-list live/installer ↔ package-lists mismatch:" >&2
	for pkg in "${_manifest_only[@]}"; do
		printf '  in install-list (live/installer) only: %s\n' "$pkg" >&2
	done
	for pkg in "${_list_only[@]}"; do
		printf '  in package-lists only: %s  (%s)\n' "$pkg" "${PKG_SOURCE[$pkg]}" >&2
	done
	echo "Fix: run ./build.sh --lists-only from the repo root." >&2
	exit 1
fi

_host_suite=""
if [[ -r /etc/os-release ]]; then
	# shellcheck disable=SC1091
	. /etc/os-release
	_host_suite="${VERSION_CODENAME:-}"
fi

# True if apt-cache madison lists the package from suite/ (not suite-backports/).
_pkg_in_suite_madison() {
	local pkg="$1"
	apt-cache madison "$pkg" 2>/dev/null | awk -F'|' -v suite="$SUITE" '
	{
		gsub(/^ +| +$/, "", $3)
		if (index($3, " " suite "/") > 0) found = 1
	}
	END { exit found ? 0 : 1 }'
}

_pkg_in_backports_madison() {
	local pkg="$1"
	apt-cache madison "$pkg" 2>/dev/null | awk -F'|' -v suite="$SUITE" '
	{
		gsub(/^ +| +$/, "", $3)
		if (index($3, suite "-backports/") > 0) found = 1
	}
	END { exit found ? 0 : 1 }'
}

echo "Validating ${#PACKAGES[@]} packages from overlay/package-lists for Debian ${SUITE}/${ARCH}..."
echo "install-list: ${#NEURONIX_MANIFEST_PKGS[@]} entries with descriptions (${MANIFEST})"
echo "Rule: packages must exist in ${SUITE}/ (not only ${SUITE}-backports)."

_missing=()
_backports_only=()

if [[ "$_host_suite" == "$SUITE" ]]; then
	echo "Using host apt-cache madison (suite=${SUITE}, excluding backports-only)."
	for pkg in "${PACKAGES[@]}"; do
		if _pkg_in_suite_madison "$pkg"; then
			continue
		elif _pkg_in_backports_madison "$pkg"; then
			_backports_only+=("$pkg")
		else
			_missing+=("$pkg")
		fi
	done
elif command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
	echo "Using one docker debian:${SUITE} run for apt-cache checks (no backports)..."
	mapfile -t _batch_missing < <(
		docker run --rm "debian:${SUITE}" bash -c '
			set -e
			export DEBIAN_FRONTEND=noninteractive
			apt-get update -qq >/dev/null
			missing=""
			for pkg in "$@"; do
				if ! apt-cache show "$pkg" >/dev/null 2>&1; then
					missing="$missing $pkg"
				fi
			done
			missing="${missing# }"
			[ -n "$missing" ] && printf "%s\n" $missing
		' bash "${PACKAGES[@]}"
	)
	_missing=("${_batch_missing[@]+"${_batch_missing[@]}"}")
elif command -v mmdebstrap >/dev/null 2>&1; then
	echo "Using mmdebstrap ${SUITE} minbase for apt-cache checks (no backports)..."
	_tmp="$(mktemp -d)"
	trap 'rm -rf "$_tmp"' EXIT
	mmdebstrap --mode=unshare --variant=minbase --arch="$ARCH" \
		--include=apt,ca-certificates "$SUITE" "$_tmp/root" \
		"deb http://deb.debian.org/debian ${SUITE} main contrib non-free non-free-firmware"
	for pkg in "${PACKAGES[@]}"; do
		if ! mmdebstrap --mode=unshare chroot "$_tmp/root" apt-cache show "$pkg" >/dev/null 2>&1; then
			_missing+=("$pkg")
		fi
	done
else
	echo "Host is not Debian ${SUITE} and docker/mmdebstrap unavailable — using host apt-cache (may be wrong)." >&2
	for pkg in "${PACKAGES[@]}"; do
		if _pkg_in_suite_madison "$pkg"; then
			continue
		elif _pkg_in_backports_madison "$pkg"; then
			_backports_only+=("$pkg")
		elif ! apt-cache show "$pkg" >/dev/null 2>&1; then
			_missing+=("$pkg")
		else
			_missing+=("$pkg")
		fi
	done
fi

_failed=0
if ((${#_missing[@]})); then
	echo "Missing or unavailable packages (${#_missing[@]}):" >&2
	for pkg in "${_missing[@]}"; do
		printf '  %s  (%s)  %s\n' "$pkg" "${PKG_SOURCE[$pkg]}" "${NEURONIX_MANIFEST_DESC[$pkg]:-}" >&2
	done
	_failed=1
fi
if ((${#_backports_only[@]})); then
	echo "Backports-only packages in *.list.chroot (${#_backports_only[@]}) — live-build cannot install these during the package pass:" >&2
	for pkg in "${_backports_only[@]}"; do
		printf '  %s  (%s)  %s\n' "$pkg" "${PKG_SOURCE[$pkg]}" "${NEURONIX_MANIFEST_DESC[$pkg]:-}" >&2
	done
	echo "Move them to neuronix-iso/overlay/hooks/normal/997-neuronix-backports.hook.chroot (and Calamares extras), then remove from install-list / regenerate with ./build.sh --lists-only." >&2
	_failed=1
fi
if ((_failed)); then
	exit 1
fi

echo "OK: all ${#PACKAGES[@]} live-build package-list entries resolve in Debian ${SUITE} (base suite)."
echo "OK: install-list live/installer sections match package-lists."

# Calamares lists must cover server + desktop sections.
SERVER_PKGS="${BUILD_ROOT}/share/calamares-neuronix/etc/calamares/neuronix-server-packages.list"
DESKTOP_PKGS="${BUILD_ROOT}/share/calamares-neuronix/etc/calamares/neuronix-desktop-packages.list"

_check_calamares_list() {
	local list_file="$1" section="$2" label="$3"
	if [[ ! -r "$list_file" ]]; then
		echo "WARNING: missing $list_file (run ./build.sh --lists-only)" >&2
		return 0
	fi
	declare -A SET=()
	local line pkg
	while IFS= read -r line || [[ -n "$line" ]]; do
		pkg="$(neuronix_manifest_pkg_only "$line")"
		[[ -n "$pkg" ]] || continue
		SET["$pkg"]=1
	done <"$list_file"
	local missing=()
	for pkg in "${NEURONIX_MANIFEST_PKGS[@]}"; do
		[[ "${NEURONIX_MANIFEST_SECTION[$pkg]}" == "$section" ]] || continue
		[[ -z "${SET[$pkg]:-}" ]] && missing+=("$pkg")
	done
	if ((${#missing[@]})); then
		echo "$label missing $section packages (run ./build.sh --lists-only):" >&2
		for pkg in "${missing[@]}"; do
			printf '  %s\n' "$pkg" >&2
		done
		return 1
	fi
	echo "OK: $label covers all $section-section packages."
	return 0
}

_cal_failed=0
_check_calamares_list "$SERVER_PKGS" server "neuronix-server-packages.list" || _cal_failed=1
_check_calamares_list "$DESKTOP_PKGS" desktop "neuronix-desktop-packages.list" || _cal_failed=1
if ((_cal_failed)); then
	exit 1
fi
