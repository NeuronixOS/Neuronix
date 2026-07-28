#!/usr/bin/env bash
# Calamares Desktop: install Hyprland stack + kernel from suite-backports.
# Kept as a script so Calamares does not interpolate ${...} as GlobalStorage vars.
set -euo pipefail

# shellcheck disable=SC1091
. /etc/os-release 2>/dev/null || true
suite="${VERSION_CODENAME:-trixie}"
backports="${suite}-backports"

echo "[neuronix-backports] Installing Hyprland/kernel from ${backports}…"

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -t "${backports}" \
	linux-image-amd64 linux-headers-amd64 \
	hyprland hyprland-guiutils hyprpaper hyprpicker xdg-desktop-portal-hyprland \
	ydotool

echo "[neuronix-backports] OK."
