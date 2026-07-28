#!/usr/bin/env bash
# Compatibility launcher for gtk-term as the desktop default terminal.
# Accepts common gnome-terminal / xdg-terminal-exec flags:
#   --working-directory DIR
#   -e / -- / --command  <argv...>
set -euo pipefail

BIN="$(command -v gtk-term 2>/dev/null || true)"
if [[ -z "$BIN" || ! -x "$BIN" ]]; then
	for cand in /usr/local/bin/gtk-term /usr/bin/gtk-term; do
		if [[ -x "$cand" ]]; then
			BIN="$cand"
			break
		fi
	done
fi
if [[ -z "${BIN:-}" || ! -x "$BIN" ]]; then
	echo "gtk-term binary missing on PATH" >&2
	exit 1
fi

workdir=""
cmd_args=()
while (($# > 0)); do
	case "$1" in
	-e | -- | --command | -x)
		shift
		cmd_args=("$@")
		break
		;;
	--working-directory=*)
		workdir="${1#*=}"
		shift
		;;
	--working-directory | -w)
		workdir="${2:-}"
		shift 2 || true
		;;
	--app-id=* | --title=* | --class=* | --name=*)
		shift
		;;
	--app-id | --title | --class | --name)
		shift 2 || true
		;;
	-*)
		shift
		;;
	*)
		cmd_args=("$@")
		break
		;;
	esac
done

if [[ -n "$workdir" && -d "$workdir" ]]; then
	cd "$workdir"
fi

if ((${#cmd_args[@]} > 0)); then
	wrapper="$(mktemp --tmpdir gtk-term-cmd.XXXXXX.sh)"
	{
		echo '#!/bin/bash'
		echo "rm -f $(printf '%q' "$wrapper")"
		printf 'exec '
		printf '%q ' "${cmd_args[@]}"
		echo
	} >"$wrapper"
	chmod +x "$wrapper"
	export SHELL="$wrapper"
fi

exec "$BIN"
