#!/bin/sh
# Calamares shellprocess (target chroot): fix NetworkManager keyfile ownership lines.
#
# networkcfg copies live /etc/NetworkManager/system-connections/* into the target but
# only rewrites `permissions=user:<live>:` when it can detect the live username.
# Calamares often runs as root with no utmp login, so detection fails and copied files
# still reference user `live` (see live-build: username=live). NM then ignores those
# profiles for the real desktop user — no Wi‑Fi after install / no passphrase flow.
set -eu

NM_DIR=/etc/NetworkManager/system-connections
[ -d "$NM_DIR" ] || exit 0

MIN_UID="$(awk '/^UID_MIN/{print $2; exit}' /etc/login.defs 2>/dev/null || true)"
MIN_UID="${MIN_UID:-1000}"

# Lowest non-system UID (primary Calamares-created user is almost always first >= UID_MIN).
USERNAME="$(
	awk -F: -v min="$MIN_UID" '$3+0 >= min+0 && $3+0 < 65000 { print $1, $3+0 }' /etc/passwd \
		| sort -k2 -n \
		| awk 'NR==1 { print $1; exit }'
)"
[ -n "${USERNAME:-}" ] || exit 0

fixed=0
for f in "$NM_DIR"/*; do
	[ -f "$f" ] || continue
	if grep -qF 'permissions=user:live:' "$f" 2>/dev/null; then
		sed -i "s/permissions=user:live:/permissions=user:${USERNAME}:/g" "$f"
		fixed=$((fixed + 1))
	fi
done

if [ "$fixed" -gt 0 ]; then
	echo "[neuronix-nm-user-perms] updated permissions=user:live: -> user:${USERNAME}: in ${fixed} file(s)"
fi
exit 0
