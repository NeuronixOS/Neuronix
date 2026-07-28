#!/bin/sh
# Install /usr/share/neuronix/crontab.conf for the default (autologin / first) user.
# Used by Calamares shellprocess and optional live chroot hook.
set -eu

CONF=/usr/share/neuronix/crontab.conf
[ -f "$CONF" ] || exit 0

. /usr/share/neuronix/neuronix-lightdm-user.sh 2>/dev/null || exit 0

_u="$(neuronix_lightdm_autologin_user 2>/dev/null || true)"
[ -n "${_u:-}" ] || exit 0

if ! command -v crontab >/dev/null 2>&1; then
	echo "[neuronix-install-crontab] crontab not installed; skip" >&2
	exit 0
fi

# Load as the target user so the spool belongs to them
if su -s /bin/sh "${_u}" -c "crontab -" <"$CONF"; then
	echo "[neuronix-install-crontab] installed crontab for ${_u}"
else
	# Fallback: root installs for user
	crontab -u "${_u}" "$CONF"
	echo "[neuronix-install-crontab] installed crontab for ${_u} (via -u)"
fi
exit 0
