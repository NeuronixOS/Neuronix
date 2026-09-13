#!/bin/sh
# Cycle HDMI desks 1–4 only (wrap). Portrait desks 11/12 are left alone.
# Usage: workspace-cycle.sh [+1|-1] [move]
set -eu
dir="${1:-+1}"
move="${2:-}"

ws=$(hyprctl -j activeworkspace 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])' 2>/dev/null || true)
[ -n "${ws:-}" ] || exit 0

case "$ws" in
11|12)
	exit 0
	;;
esac

case "$dir" in
+1|next|1)
	next=$((ws + 1))
	[ "$next" -gt 4 ] && next=1
	;;
-1|prev)
	next=$((ws - 1))
	[ "$next" -lt 1 ] && next=4
	;;
*)
	exit 1
	;;
esac

if [ "$move" = "move" ]; then
	hyprctl dispatch movetoworkspace "$next"
else
	hyprctl dispatch workspace "$next"
fi
