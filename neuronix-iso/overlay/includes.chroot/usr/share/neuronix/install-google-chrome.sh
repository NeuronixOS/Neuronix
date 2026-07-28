#!/bin/sh
# Add Google Chrome apt repo and install google-chrome-stable (ISO chroot + Calamares target).
set -eu

KEYRING=/usr/share/keyrings/google-chrome.gpg
LIST=/etc/apt/sources.list.d/google-chrome.list
CHROME=/usr/bin/google-chrome-stable

install_google_chrome() {
	if [ -x "${CHROME}" ]; then
		echo "[install-google-chrome] already installed"
		_set_default_browser
		if [ -x /usr/share/neuronix/register-chrome-extensions.sh ]; then
			/usr/share/neuronix/register-chrome-extensions.sh || true
		fi
		return 0
	fi

	if ! command -v apt-get >/dev/null 2>&1; then
		echo "[install-google-chrome] apt-get not found" >&2
		return 1
	fi

	if ! command -v gpg >/dev/null 2>&1; then
		echo "[install-google-chrome] gpg not found" >&2
		return 1
	fi

	mkdir -p "$(dirname "${KEYRING}")"
	if [ ! -s "${KEYRING}" ]; then
		if command -v curl >/dev/null 2>&1; then
			curl -fsSL https://dl.google.com/linux/linux_signing_key.pub \
				| gpg --dearmor -o "${KEYRING}.tmp"
		elif command -v wget >/dev/null 2>&1; then
			wget -qO- https://dl.google.com/linux/linux_signing_key.pub \
				| gpg --dearmor -o "${KEYRING}.tmp"
		else
			echo "[install-google-chrome] need curl or wget" >&2
			return 1
		fi
		mv -f "${KEYRING}.tmp" "${KEYRING}"
		chmod 0644 "${KEYRING}"
	fi

	if [ ! -f "${LIST}" ]; then
		printf '%s\n' \
			"deb [arch=amd64 signed-by=${KEYRING}] https://dl.google.com/linux/chrome/deb/ stable main" \
			>"${LIST}"
		chmod 0644 "${LIST}"
	fi

	export DEBIAN_FRONTEND=noninteractive
	apt-get update -qq
	apt-get install -y -qq google-chrome-stable

	if [ ! -x "${CHROME}" ]; then
		echo "[install-google-chrome] install finished but ${CHROME} missing" >&2
		return 1
	fi

	_set_default_browser
	if [ -x /usr/share/neuronix/register-chrome-extensions.sh ]; then
		/usr/share/neuronix/register-chrome-extensions.sh || true
	fi
	echo "[install-google-chrome] OK"
}

_set_default_browser() {
	if ! command -v update-alternatives >/dev/null 2>&1; then
		return 0
	fi
	# Prefer Neuronix wrapper so personalize browser-extensions load automatically
	if [ -x /usr/local/bin/neuronix-chrome ]; then
		update-alternatives --install /usr/bin/x-www-browser x-www-browser /usr/local/bin/neuronix-chrome 200 \
			2>/dev/null || true
		update-alternatives --install /usr/bin/gnome-www-browser gnome-www-browser /usr/local/bin/neuronix-chrome 200 \
			2>/dev/null || true
		update-alternatives --set x-www-browser /usr/local/bin/neuronix-chrome 2>/dev/null || true
		update-alternatives --set gnome-www-browser /usr/local/bin/neuronix-chrome 2>/dev/null || true
		return 0
	fi
	if [ ! -x "${CHROME}" ]; then
		return 0
	fi
	update-alternatives --install /usr/bin/x-www-browser x-www-browser "${CHROME}" 100 \
		2>/dev/null || true
	update-alternatives --install /usr/bin/gnome-www-browser gnome-www-browser "${CHROME}" 100 \
		2>/dev/null || true
	update-alternatives --set x-www-browser "${CHROME}" 2>/dev/null || true
	update-alternatives --set gnome-www-browser "${CHROME}" 2>/dev/null || true
}

install_google_chrome "$@"
