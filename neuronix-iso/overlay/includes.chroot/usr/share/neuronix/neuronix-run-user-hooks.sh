#!/bin/sh
# Run merged /usr/share/neuronix/user-hooks/*.sh once per user (first Hyprland login).
# Skip live ISO sessions so the once-stamp is not consumed before install.
set -eu

if grep -qw boot=live /proc/cmdline 2>/dev/null; then
	exit 0
fi

HOOKS_DIR=/usr/share/neuronix/user-hooks
STATE_HOME="${XDG_STATE_HOME:-${HOME}/.local/state}"
STATE_DIR="${STATE_HOME}/neuronix"
DONE_STAMP="${STATE_DIR}/user-hooks.done"
LOG_FILE="${STATE_DIR}/user-hooks.log"

[ -d "$HOOKS_DIR" ] || exit 0

# Any *.sh present?
set -- "$HOOKS_DIR"/*.sh
if [ ! -e "$1" ]; then
	exit 0
fi

if [ -f "$DONE_STAMP" ]; then
	exit 0
fi

mkdir -p "$STATE_DIR"
{
	echo "==== neuronix-run-user-hooks $(date -Is) uid=$(id -u) ===="
	rc_all=0
	# shellcheck disable=SC2045
	for hook in $(ls -1 "$HOOKS_DIR"/*.sh 2>/dev/null | sort); do
		[ -f "$hook" ] || continue
		[ -x "$hook" ] || chmod 0755 "$hook" 2>/dev/null || true
		echo "--> running $(basename "$hook")"
		if ! /bin/sh "$hook"; then
			echo "!! $(basename "$hook") failed (continuing)"
			rc_all=1
		fi
	done
	echo "==== done rc=$rc_all ===="
} >>"$LOG_FILE" 2>&1 || true

# Stamp even if some hooks failed — avoids login loops; delete stamp to retry.
: >"$DONE_STAMP"
exit 0
