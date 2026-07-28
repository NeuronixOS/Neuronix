#!/usr/bin/env bash
# Calamares: apt-install server-section packages onto the slim unpacked image.
# Runs for every profile (Desktop and Server).
set -euo pipefail

PKG_LIST="${NEURONIX_SERVER_PACKAGES_LIST:-/etc/calamares/neuronix-server-packages.list}"

echo "[neuronix-server-pkgs] Installing server packages…"

if [[ ! -r "$PKG_LIST" ]]; then
	echo "[neuronix-server-pkgs] Missing package list: $PKG_LIST" >&2
	exit 1
fi

mapfile -t _pkgs < <(awk '
	/^[[:space:]]*#/ { next }
	/^[[:space:]]*$/ { next }
	{ print $1 }
' "$PKG_LIST")

if ((${#_pkgs[@]} == 0)); then
	# default/install-list may have an empty # --- server --- section (live keepers
	# already cover NM/SSH/console). Treat as success so Calamares can continue.
	echo "[neuronix-server-pkgs] Package list is empty — nothing to install (OK)."
	exit 0
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq

_to_install=()
for pkg in "${_pkgs[@]}"; do
	if dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q ' install ok installed'; then
		continue
	fi
	_to_install+=("$pkg")
done

if ((${#_to_install[@]} > 0)); then
	echo "[neuronix-server-pkgs] Installing ${#_to_install[@]} packages…"
	apt-get install -y "${_to_install[@]}"
else
	echo "[neuronix-server-pkgs] All listed server packages already installed."
fi

echo "[neuronix-server-pkgs] Server package install complete."
