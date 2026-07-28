# shellcheck shell=bash
# Shared parser for default/install-list (@manifest-format: 1)
#
# Package line:  PACKAGENAME # description
# Section line:  # --- section-name ---
#
# Usage:
#   source "$(dirname "$0")/manifest-lib.sh"   # from neuronix-iso/packages/
#   neuronix_manifest_load /path/to/default/install-list
#   printf '%s\n' "${NEURONIX_MANIFEST_PKGS[@]}"
#   echo "${NEURONIX_MANIFEST_DESC[sudo]}"
#   echo "${NEURONIX_MANIFEST_SECTION[nwg-look]}"

if [[ -n "${NEURONIX_MANIFEST_LIB_LOADED:-}" ]]; then
	return 0 2>/dev/null || exit 0
fi
NEURONIX_MANIFEST_LIB_LOADED=1

declare -a NEURONIX_MANIFEST_PKGS=()
declare -A NEURONIX_MANIFEST_DESC=()
declare -A NEURONIX_MANIFEST_SECTION=()

# Parse one manifest line into NEURONIX_MANIFEST_LINE_PKG / NEURONIX_MANIFEST_LINE_DESC.
# Returns 0 if line defines a package, 1 otherwise.
neuronix_manifest_parse_line() {
	local line="${1-}" section_ref="${2:-}"
	NEURONIX_MANIFEST_LINE_PKG=""
	NEURONIX_MANIFEST_LINE_DESC=""

	line="${line%%$'\r'}"
	[[ -z "${line//[[:space:]]/}" ]] && return 1

	if [[ "$line" =~ ^[[:space:]]*# ]]; then
		if [[ -n "$section_ref" && "$line" =~ ^[[:space:]]*#[[:space:]]*---[[:space:]]*(.+)[[:space:]]*---[[:space:]]*$ ]]; then
			printf -v "$section_ref" '%s' "${BASH_REMATCH[1]%%[[:space:]]}"
		fi
		return 1
	fi

	if [[ "$line" == *" # "* ]]; then
		NEURONIX_MANIFEST_LINE_PKG="${line%% # *}"
		NEURONIX_MANIFEST_LINE_DESC="${line#* # }"
	else
		NEURONIX_MANIFEST_LINE_PKG="${line%% *}"
		NEURONIX_MANIFEST_LINE_DESC=""
	fi

	NEURONIX_MANIFEST_LINE_PKG="${NEURONIX_MANIFEST_LINE_PKG#"${NEURONIX_MANIFEST_LINE_PKG%%[![:space:]]*}"}"
	NEURONIX_MANIFEST_LINE_PKG="${NEURONIX_MANIFEST_LINE_PKG%"${NEURONIX_MANIFEST_LINE_PKG##*[![:space:]]}"}"
	NEURONIX_MANIFEST_LINE_DESC="${NEURONIX_MANIFEST_LINE_DESC#"${NEURONIX_MANIFEST_LINE_DESC%%[![:space:]]*}"}"
	NEURONIX_MANIFEST_LINE_DESC="${NEURONIX_MANIFEST_LINE_DESC%"${NEURONIX_MANIFEST_LINE_DESC##*[![:space:]]}"}"
	[[ -n "$NEURONIX_MANIFEST_LINE_PKG" ]] || return 1
	return 0
}

# Load manifest file into NEURONIX_MANIFEST_* globals (replaces prior contents).
neuronix_manifest_load() {
	local file="$1" line section=""
	NEURONIX_MANIFEST_PKGS=()
	NEURONIX_MANIFEST_DESC=()
	NEURONIX_MANIFEST_SECTION=()

	[[ -r "$file" ]] || {
		echo "manifest-lib: unreadable file: $file" >&2
		return 1
	}

	while IFS= read -r line || [[ -n "$line" ]]; do
		if neuronix_manifest_parse_line "$line" section; then
			NEURONIX_MANIFEST_PKGS+=("$NEURONIX_MANIFEST_LINE_PKG")
			NEURONIX_MANIFEST_DESC["$NEURONIX_MANIFEST_LINE_PKG"]="$NEURONIX_MANIFEST_LINE_DESC"
			NEURONIX_MANIFEST_SECTION["$NEURONIX_MANIFEST_LINE_PKG"]="$section"
		fi
	done <"$file"
}

# Append packages from another manifest (e.g. personalize/install-list).
# Skips names already present (base wins). Section comes from the append file.
neuronix_manifest_append() {
	local file="$1" line section="" pkg
	[[ -r "$file" ]] || {
		echo "manifest-lib: unreadable file: $file" >&2
		return 1
	}

	while IFS= read -r line || [[ -n "$line" ]]; do
		if neuronix_manifest_parse_line "$line" section; then
			pkg="$NEURONIX_MANIFEST_LINE_PKG"
			[[ -n "${NEURONIX_MANIFEST_SECTION[$pkg]+x}" ]] && continue
			NEURONIX_MANIFEST_PKGS+=("$pkg")
			NEURONIX_MANIFEST_DESC["$pkg"]="$NEURONIX_MANIFEST_LINE_DESC"
			NEURONIX_MANIFEST_SECTION["$pkg"]="$section"
		fi
	done <"$file"
}

# Print TSV: package<TAB>section<TAB>description
neuronix_manifest_print_tsv() {
	local pkg
	for pkg in "${NEURONIX_MANIFEST_PKGS[@]}"; do
		printf '%s\t%s\t%s\n' \
			"$pkg" \
			"${NEURONIX_MANIFEST_SECTION[$pkg]:-}" \
			"${NEURONIX_MANIFEST_DESC[$pkg]:-}"
	done
}

# Strip description from a package line (for .list.chroot compatibility).
neuronix_manifest_pkg_only() {
	local line="${1-}" pkg=""
	if neuronix_manifest_parse_line "$line"; then
		pkg="$NEURONIX_MANIFEST_LINE_PKG"
	else
		line="${line%%#*}"
		line="${line#"${line%%[![:space:]]*}"}"
		line="${line%"${line##*[![:space:]]}"}"
		[[ -n "$line" ]] && pkg="${line%% *}"
	fi
	[[ -n "$pkg" ]] && printf '%s' "$pkg"
	return 0
}
