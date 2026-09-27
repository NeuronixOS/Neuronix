#!/bin/sh
# Super+Alt+= / − — Hyprland cursor zoom (no compositor reload).
set -eu
step=0.1
min=1.0
max=3.0
cur=$(hyprctl getoption cursor:zoom_factor -j | python3 -c 'import json,sys; print(float(json.load(sys.stdin).get("float") or 1.0))')
case "${1:-in}" in
	in|+)  next=$(python3 -c "print(min($max, $cur + $step))") ;;
	out|-) next=$(python3 -c "print(max($min, $cur - $step))") ;;
	reset) next=$min ;;
	*)
		echo "usage: $0 in|out|reset" >&2
		exit 1
		;;
esac
hyprctl keyword cursor:zoom_factor "$next"
