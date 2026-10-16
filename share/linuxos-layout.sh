# shellcheck shell=bash
# Monorepo layout helpers — shared by neuronix-iso/setup.sh and Packages tools.
#
# Expected siblings of this Neuronix checkout:
#   ../Packages/gtk-apps
#   ../Packages/hyprframes
#   ../KvNix/
#
# ISO setup and syn-to-devices resolve the monorepo root from this layout
# (parent of Neuronix/, or walk-up from Packages/). No on-disk marker files.
#
# Usage:
#   source "$REPO_ROOT/share/linuxos-layout.sh"
#   MONOREPO_ROOT="$(neuronix_linuxos_root "$REPO_ROOT")" || true
#   PACKAGES="$(neuronix_packages_dir "$REPO_ROOT")" || true

if [[ -n "${NEURONIX_LINUXOS_LAYOUT_LOADED:-}" ]]; then
	return 0 2>/dev/null || exit 0
fi
NEURONIX_LINUXOS_LAYOUT_LOADED=1

# Echo absolute path of the Neuronix checkout (parent of share/).
neuronix_repo_root_from_share() {
	cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd
}

# True when $1 is a monorepo root (has Neuronix stock gtk-apps).
neuronix_is_linuxos_root() {
	local d="${1:-}"
	[[ -n "$d" && -d "$d" ]] || return 1
	[[ -d "$d/Neuronix/default/gtk-apps" || -d "$d/Neuronix/Build/default/gtk-apps" ]]
}

# Monorepo root for a Neuronix checkout: parent directory when it has the
# expected siblings. Echoes absolute path.
# Usage: neuronix_linuxos_root [neuronix_repo_root]
neuronix_linuxos_root() {
	local repo="${1:-}"
	if [[ -z "$repo" ]]; then
		repo="$(neuronix_repo_root_from_share)"
	fi
	repo="$(cd "$repo" && pwd)"
	local root
	root="$(cd "$repo/.." && pwd)"
	if neuronix_is_linuxos_root "$root"; then
		printf '%s\n' "$root"
		return 0
	fi
	# Parent has Packages/ even if Neuronix path layout differs slightly.
	if [[ -d "$root/Packages" && -d "$repo/default/gtk-apps" ]]; then
		printf '%s\n' "$root"
		return 0
	fi
	return 1
}

# Echo <monorepo>/Packages when present.
# Usage: neuronix_packages_dir [neuronix_repo_root]
neuronix_packages_dir() {
	local root
	root="$(neuronix_linuxos_root "${1:-}")" || return 1
	[[ -d "$root/Packages" ]] || return 1
	printf '%s\n' "$root/Packages"
}
