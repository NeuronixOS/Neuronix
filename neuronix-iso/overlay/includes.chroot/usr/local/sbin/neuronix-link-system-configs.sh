#!/bin/sh
# Point /etc system paths at the primary user's ~/configs tree (single git-managed source).
# Map file: /etc/neuronix/system-config-links.tsv  (type\tfrom_rel\tto_abs)
# from_rel is relative to /home/<user>/configs/
set -eu

MAP=/etc/neuronix/system-config-links.tsv
[ -f "$MAP" ] || exit 0

. /usr/share/neuronix/neuronix-lightdm-user.sh 2>/dev/null || true

_pick_user() {
	_u="$(neuronix_lightdm_autologin_user 2>/dev/null || true)"
	if [ -n "${_u:-}" ] && [ -d "/home/${_u}/configs" ]; then
		printf '%s\n' "$_u"
		return 0
	fi
	# Live ISO default
	if [ -d /home/live/configs ]; then
		printf '%s\n' live
		return 0
	fi
	# First normal user with ~/configs
	_u="$(getent passwd | awk -F: '$3 >= 1000 && $3 < 65534 { print $1 }' | while read -r cand; do
		[ -d "/home/${cand}/configs" ] && { printf '%s\n' "$cand"; break; }
	done)"
	[ -n "${_u:-}" ] && printf '%s\n' "$_u"
}

_u="$(_pick_user || true)"
[ -n "${_u:-}" ] || {
	echo "[neuronix-link-system-configs] no user ~/configs yet — skip" >&2
	exit 0
}

ROOT="/home/${_u}/configs"
[ -d "$ROOT" ] || {
	echo "[neuronix-link-system-configs] missing $ROOT — skip" >&2
	exit 0
}

# Allow daemons (www-data, etc.) to traverse into configs
chmod 755 "/home/${_u}" 2>/dev/null || true
chmod 755 "$ROOT" 2>/dev/null || true

count=0
while IFS="$(printf '\t')" read -r typ from_rel to_abs || [ -n "${typ:-}" ]; do
	[ -n "${typ:-}" ] || continue
	case "$typ" in
	\#*|'') continue ;;
	esac
	src="${ROOT}/${from_rel}"
	[ -e "$src" ] || continue
	mkdir -p "$(dirname "$to_abs")"
	rm -rf "$to_abs"
	ln -sfn "$src" "$to_abs"
	count=$((count + 1))
	echo "[neuronix-link-system-configs] $to_abs → $src"
done <"$MAP"

echo "[neuronix-link-system-configs] linked ${count} path(s) for user ${_u}"
exit 0
