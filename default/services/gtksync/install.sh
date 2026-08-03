#!/usr/bin/env bash
# Neuronix default: gtksync (Waybar gtk-sync status/menu).
set -euo pipefail

ROOT="${NEURONIX_SERVICE_ROOT:-$(cd "$(dirname "$0")" && pwd)}"
NAME="${NEURONIX_SERVICE_NAME:-$(basename "$ROOT")}"

chmod +x "$ROOT/waybar/gtk-sync-status.sh" "$ROOT/waybar/gtk-sync-menu.sh" 2>/dev/null || true

mkdir -p /usr/local/bin
ln -sfn "${ROOT}/waybar/gtk-sync-status.sh" /usr/local/bin/gtk-sync-status
ln -sfn "${ROOT}/waybar/gtk-sync-menu.sh" /usr/local/bin/gtk-sync-menu

echo "[$NAME] installed waybar/{gtk-sync-status,gtk-sync-menu}"
