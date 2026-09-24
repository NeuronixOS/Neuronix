#!/usr/bin/env bash
# Calamares Desktop: install Hyprland stack from suite-backports.
# Keep stock trixie 6.12 LTS kernel — NVIDIA DKMS (550.x) does not build on
# linux 7.x from backports.
set -euo pipefail

# shellcheck disable=SC1091
. /etc/os-release 2>/dev/null || true
suite="${VERSION_CODENAME:-trixie}"
backports="${suite}-backports"

echo "[neuronix-backports] Installing Hyprland from ${backports} (kernel stays on ${suite} 6.12 LTS)…"

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -t "${backports}" \
	hyprland hyprland-guiutils hyprpaper hyprpicker xdg-desktop-portal-hyprland \
	ydotool

echo "[neuronix-backports] OK."
