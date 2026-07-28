#!/bin/sh
# Register Flathub so `flatpak install` works without a manual remote-add.
# Safe to re-run ( --if-not-exists ). No-op when flatpak is not installed.
set -e
if ! command -v flatpak >/dev/null 2>&1; then
	echo "[neuronix-enable-flathub] flatpak not installed; skip" >&2
	exit 0
fi
if flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo; then
	echo "[neuronix-enable-flathub] Flathub remote ready"
else
	echo "[neuronix-enable-flathub] remote-add failed (network?); skip" >&2
	exit 0
fi
