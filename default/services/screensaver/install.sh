#!/usr/bin/env bash
# Install neuronix-screensaver-idle as a systemd *user* unit.
#
# Invoked by 9930-neuronix-personalize-services.hook.chroot with:
#   NEURONIX_SERVICE_ROOT=/usr/local/lib/neuronix/services/screensaver
#   NEURONIX_SERVICE_NAME=screensaver
#
# Does NOT call systemctl --user in live-build chroot (no user session).
# Units go under /etc/skel so the Calamares-created user inherits them.
#
# Live/workstation: copy this tree to /usr/local/lib/neuronix/services/screensaver
# first, then run ./install.sh (paths never reference Dropbox).
set -euo pipefail

ROOT="${NEURONIX_SERVICE_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
NAME="${NEURONIX_SERVICE_NAME:-$(basename "$ROOT")}"

chmod +x "$ROOT/screensaver.py" "$ROOT/idle_daemon.py" 2>/dev/null || true

UNIT_SRC="$ROOT/neuronix-screensaver-idle.service"
if [[ ! -f "$UNIT_SRC" ]]; then
	echo "[$NAME] missing neuronix-screensaver-idle.service" >&2
	exit 1
fi

# Prefer skel when running as root in ISO/chroot; otherwise install for current user.
if [[ "${EUID:-$(id -u)}" -eq 0 && -d /etc/skel ]]; then
	DEST_DIR=/etc/skel/.config/systemd/user
	CONFIG_DIR=/etc/skel/.config/neuronix-screensaver
	WANTS_DIR="$DEST_DIR/default.target.wants"
else
	DEST_DIR="${HOME}/.config/systemd/user"
	CONFIG_DIR="${HOME}/.config/neuronix-screensaver"
	WANTS_DIR="$DEST_DIR/default.target.wants"
fi

mkdir -p "$DEST_DIR" "$CONFIG_DIR" "$WANTS_DIR"

if [[ ! -f "$CONFIG_DIR/config.ini" ]]; then
	cp "$ROOT/config.example.ini" "$CONFIG_DIR/config.ini"
	echo "[$NAME] Created $CONFIG_DIR/config.ini"
fi

# Rewrite any legacy Dropbox / placeholder paths → staged service root
sed -E \
	-e "s|%h/Dropbox/Devices/Services/Screensaver|${ROOT}|g" \
	-e "s|/home/[^/]+/Dropbox/Devices/Services/Screensaver|${ROOT}|g" \
	-e "s|/usr/local/lib/neuronix/services/screensaver|${ROOT}|g" \
	-e "s|__SCRIPT_DIR__|${ROOT}|g" \
	"$UNIT_SRC" >"$DEST_DIR/neuronix-screensaver-idle.service"

ln -sfn "../neuronix-screensaver-idle.service" \
	"$WANTS_DIR/neuronix-screensaver-idle.service"
echo "[$NAME] installed user unit neuronix-screensaver-idle.service → $DEST_DIR"

# Interactive / already-logged-in install only (never in live-build chroot)
if [[ -n "${XDG_RUNTIME_DIR:-}" ]] && systemctl --user show-environment &>/dev/null; then
	systemctl --user daemon-reload || true
	systemctl --user enable --now neuronix-screensaver-idle.service || true
fi
