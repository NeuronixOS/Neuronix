#!/usr/bin/env bash
# Resolve live-build output + generated recipe paths under scratch (never the git tree).
# Sourced by build.sh, setup.sh, and validate-manifest.sh after debian.env.
set -euo pipefail

neuronix_build_user() {
	printf '%s' "${USER:-build}"
}

# Default live-build cwd (config/, chroot/, binary/, iso, cache/).
# /var/tmp, not /tmp: /tmp is often a RAM-backed tmpfs and a full build
# (chroot + squashfs + apt cache) needs 20-40 GB of real disk.
neuronix_default_build_root() {
	printf '/var/tmp/neuronix-build-%s' "$(neuronix_build_user)"
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

# True if path is a scratch dir (/var/tmp, /tmp, $TMPDIR).
# Build artifacts must never land in a git tree.
neuronix_is_tmp_path() {
	local p="${1%/}"
	local tmp="${TMPDIR:-/tmp}"
	tmp="${tmp%/}"
	[[ "$p" == /var/tmp || "$p" == /var/tmp/* \
		|| "$p" == /tmp || "$p" == /tmp/* \
		|| "$p" == "$tmp" || "$p" == "$tmp"/* ]]
}

# Set NEURONIX_BUILD_ROOT (export) and generated recipe dirs under it.
# Always relocates to scratch if personalize/metadata (or an old $HOME default)
# would write into a checkout and dirty git.
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

	if ! neuronix_is_tmp_path "$NEURONIX_BUILD_ROOT"; then
		local relocated
		relocated="$(neuronix_default_build_root)"
		echo "neuronix-build-staging: ${NEURONIX_BUILD_ROOT} is not a scratch dir — using ${relocated} (keeps personalize from clobbering git trees)" >&2
		NEURONIX_BUILD_ROOT="$relocated"
	fi

	export NEURONIX_BUILD_ROOT
	export NEURONIX_GEN_DIR="${NEURONIX_BUILD_ROOT}/generated"
	export NEURONIX_LIST_DIR="${NEURONIX_GEN_DIR}/package-lists"
	export NEURONIX_CALAMARES_GEN="${NEURONIX_GEN_DIR}/calamares"
}
