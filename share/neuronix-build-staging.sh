#!/usr/bin/env bash
# Resolve live-build output + generated recipe paths under /tmp (never the git tree).
# Sourced by build.sh, setup.sh, and validate-manifest.sh after debian.env.
set -euo pipefail

neuronix_build_user() {
	printf '%s' "${USER:-build}"
}

# Default live-build cwd (config/, chroot/, binary/, iso, cache/).
neuronix_default_build_root() {
	printf '/tmp/neuronix-build-%s' "$(neuronix_build_user)"
}

# Expand leading ~ in NEURONIX_BUILD_ROOT when set in metadata.
neuronix_home_path() {
	local path="$1"
	case "$path" in
	"~/"*) printf '%s' "${HOME}/${path#~/}" ;;
	"~") printf '%s' "${HOME}" ;;
	*) printf '%s' "$path" ;;
	esac
}

# Set NEURONIX_BUILD_ROOT (export) and generated recipe dirs under it.
# Honors NEURONIX_BUILD_ROOT / NEURONIX_BUILD_ROOT_DEFAULT from debian.env.
neuronix_apply_build_staging() {
	local from_default="${1:-}"

	if [[ -n "${NEURONIX_BUILD_ROOT:-}" ]]; then
		NEURONIX_BUILD_ROOT="$(neuronix_home_path "$NEURONIX_BUILD_ROOT")"
	elif [[ -n "$from_default" ]]; then
		NEURONIX_BUILD_ROOT="$(neuronix_home_path "$from_default")"
	else
		local def="${NEURONIX_BUILD_ROOT_DEFAULT:-}"
		if [[ -n "$def" ]]; then
			NEURONIX_BUILD_ROOT="$(neuronix_home_path "$def")"
		else
			NEURONIX_BUILD_ROOT="$(neuronix_default_build_root)"
		fi
	fi

	export NEURONIX_BUILD_ROOT
	export NEURONIX_GEN_DIR="${NEURONIX_GEN_DIR:-${NEURONIX_BUILD_ROOT}/generated}"
	export NEURONIX_LIST_DIR="${NEURONIX_LIST_DIR:-${NEURONIX_GEN_DIR}/package-lists}"
	export NEURONIX_CALAMARES_GEN="${NEURONIX_CALAMARES_GEN:-${NEURONIX_GEN_DIR}/calamares}"
}
