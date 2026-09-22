#!/usr/bin/env bash
# Compatibility launcher for gtk-term as the desktop default terminal.
# Accepts common gnome-terminal / xdg-terminal-exec / foot flags:
#   --working-directory DIR
#   --app-id / --class / --title
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
app_id=""
title=""
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
	--app-id=* | --class=* | --name=*)
		app_id="${1#*=}"
		shift
		;;
	--app-id | --class | --name | --gapplication-app-id)
		app_id="${2:-}"
		shift 2 || true
		;;
	--gapplication-app-id=*)
		app_id="${1#*=}"
		shift
		;;
	--title=*)
		title="${1#*=}"
		shift
		;;
	--title | -T)
		title="${2:-}"
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

gtk_args=()
if [[ -n "$workdir" && -d "$workdir" ]]; then
	gtk_args+=(--working-directory "$workdir")
fi
if [[ -n "$app_id" ]]; then
	gtk_args+=(--app-id "$app_id")
fi
if [[ -n "$title" ]]; then
	gtk_args+=(--title "$title")
fi
if ((${#cmd_args[@]} > 0)); then
	gtk_args+=(-e "${cmd_args[@]}")
fi

exec "$BIN" "${gtk_args[@]}"
