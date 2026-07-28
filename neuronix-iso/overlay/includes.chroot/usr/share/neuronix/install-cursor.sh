#!/bin/sh
# Add Cursor apt repo and install cursor (ISO helper; Calamares only when
# personalize/install/cursor.sh is present).
set -eu

KEYRING=/etc/apt/keyrings/cursor.gpg
LIST=/etc/apt/sources.list.d/cursor.list
CURSOR=/usr/bin/cursor

install_cursor() {
	if [ -x "${CURSOR}" ]; then
		echo "[install-cursor] already installed"
		return 0
	fi

	if ! command -v apt-get >/dev/null 2>&1; then
		echo "[install-cursor] apt-get not found" >&2
		return 1
	fi

	if ! command -v gpg >/dev/null 2>&1; then
		echo "[install-cursor] gpg not found" >&2
		return 1
	fi

	mkdir -p "$(dirname "${KEYRING}")"
	if [ ! -s "${KEYRING}" ]; then
		if command -v curl >/dev/null 2>&1; then
			curl -fsSL https://downloads.cursor.com/keys/anysphere.asc \
				| gpg --dearmor -o "${KEYRING}.tmp"
		elif command -v wget >/dev/null 2>&1; then
			wget -qO- https://downloads.cursor.com/keys/anysphere.asc \
				| gpg --dearmor -o "${KEYRING}.tmp"
		else
			echo "[install-cursor] need curl or wget" >&2
			return 1
		fi
		mv -f "${KEYRING}.tmp" "${KEYRING}"
		chmod 0644 "${KEYRING}"
	fi

	if [ ! -f "${LIST}" ]; then
		_arch="$(dpkg --print-architecture 2>/dev/null || echo amd64)"
		printf '%s\n' \
			"deb [arch=${_arch} signed-by=${KEYRING}] https://downloads.cursor.com/aptrepo stable main" \
			>"${LIST}"
		chmod 0644 "${LIST}"
	fi

	export DEBIAN_FRONTEND=noninteractive
	apt-get update -qq
	apt-get install -y -qq cursor

	if [ ! -x "${CURSOR}" ]; then
		echo "[install-cursor] install finished but ${CURSOR} missing" >&2
		return 1
	fi

	echo "[install-cursor] OK"
}

install_cursor "$@"
