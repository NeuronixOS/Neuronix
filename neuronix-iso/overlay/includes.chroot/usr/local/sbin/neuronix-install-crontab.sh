#!/bin/sh
# Install /usr/share/neuronix/crontab.conf for the default (autologin / first) user.
# Used by Calamares shellprocess (sshprep) and live chroot hook 9926.
# Writes /var/spool/cron/crontabs/<user> (same end state as Devices build-server.sh).
# During live-build chroot the live user often does not exist yet — skip cleanly.
set -eu

CONF=/usr/share/neuronix/crontab.conf
[ -f "$CONF" ] || exit 0

. /usr/share/neuronix/neuronix-lightdm-user.sh 2>/dev/null || exit 0

_u="$(neuronix_lightdm_autologin_user 2>/dev/null || true)"
[ -n "${_u:-}" ] || exit 0

# User must exist in passwd (not true mid-chroot before live-user creation)
if ! getent passwd "$_u" >/dev/null 2>&1; then
	echo "[neuronix-install-crontab] user ${_u} not present yet — skip (Calamares will install)" >&2
	exit 0
fi

if ! command -v crontab >/dev/null 2>&1; then
	echo "[neuronix-install-crontab] crontab not installed; skip" >&2
	exit 0
fi

SPOOL_DIR=/var/spool/cron/crontabs
SPOOL="$SPOOL_DIR/$_u"
mkdir -p "$SPOOL_DIR"

# Preferred: crontab(1) loads the file as the user (validates syntax, updates spool)
if su -s /bin/sh "${_u}" -c "crontab -" <"$CONF" 2>/dev/null; then
	echo "[neuronix-install-crontab] installed via crontab - for ${_u}"
elif crontab -u "${_u}" "$CONF" 2>/dev/null; then
	echo "[neuronix-install-crontab] installed via crontab -u for ${_u}"
else
	# Fallback matching Devices/Build/build-server.sh — direct spool install
	cp "$CONF" "$SPOOL"
	chown "${_u}:crontab" "$SPOOL" 2>/dev/null || chown "${_u}:$_u" "$SPOOL"
	chmod 600 "$SPOOL"
	echo "[neuronix-install-crontab] installed spool copy for ${_u} → $SPOOL"
fi

# Ensure ownership/mode even when crontab(1) created the file
if [ -f "$SPOOL" ]; then
	chown "${_u}:crontab" "$SPOOL" 2>/dev/null || true
	chmod 600 "$SPOOL" 2>/dev/null || true
fi

# cron.service is enabled by Calamares services-systemd; restart if running
if command -v systemctl >/dev/null 2>&1; then
	systemctl restart cron.service 2>/dev/null || systemctl restart cron 2>/dev/null || true
fi

echo "[neuronix-install-crontab] done for ${_u} (spool: $SPOOL)"
exit 0
