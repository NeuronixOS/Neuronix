# shellcheck shell=bash
# Personalize overlay helpers — prefer personalize/ over committed defaults.
#
# Usage (from repo scripts):
#   source "$REPO_ROOT/share/neuronix-personalize.sh"
#   neuronix_resolve_file "$REPO_ROOT/default/images" "$REPO_ROOT/personalize/images" "live/background.png"
#   neuronix_resolve_image "$REPO_ROOT/default/images" "$REPO_ROOT/personalize/images" "icons/menu-icon"

if [[ -n "${NEURONIX_PERSONALIZE_LIB_LOADED:-}" ]]; then
	return 0 2>/dev/null || exit 0
fi
NEURONIX_PERSONALIZE_LIB_LOADED=1

# Echo absolute path if $1/$2 exists (file).
_neuronix_file_if_exists() {
	local root="$1" rel="$2"
	[[ -n "$root" && -n "$rel" && -f "${root%/}/$rel" ]] || return 1
	printf '%s\n' "${root%/}/$rel"
}

_neuronix_has_file() {
	local root="$1" rel="$2"
	[[ -n "$root" && -n "$rel" && -f "${root%/}/$rel" ]]
}

# Prefer personalize_root/rel over defaults_root/rel.
# Usage: neuronix_resolve_file <defaults_root> <personalize_root> <relative_path>
neuronix_resolve_file() {
	local defaults_root="$1" personalize_root="$2" rel="$3"
	if _neuronix_has_file "$personalize_root" "$rel"; then
		_neuronix_file_if_exists "$personalize_root" "$rel"
		return 0
	fi
	if _neuronix_has_file "$defaults_root" "$rel"; then
		_neuronix_file_if_exists "$defaults_root" "$rel"
		return 0
	fi
	return 1
}

# Prefer personalize, then defaults; try each extension for basename_no_ext.
# Usage: neuronix_resolve_image <defaults_root> <personalize_root> <rel_without_ext> [ext...]
# Default extensions: png jpg jpeg webp
neuronix_resolve_image() {
	local defaults_root="$1" personalize_root="$2" rel_base="$3"
	shift 3
	local -a exts=("$@")
	local ext rel
	if ((${#exts[@]} == 0)); then
		exts=(png jpg jpeg webp)
	fi
	for ext in "${exts[@]}"; do
		rel="${rel_base}.${ext}"
		if _neuronix_has_file "$personalize_root" "$rel"; then
			_neuronix_file_if_exists "$personalize_root" "$rel"
			return 0
		fi
	done
	for ext in "${exts[@]}"; do
		rel="${rel_base}.${ext}"
		if _neuronix_has_file "$defaults_root" "$rel"; then
			_neuronix_file_if_exists "$defaults_root" "$rel"
			return 0
		fi
	done
	return 1
}
