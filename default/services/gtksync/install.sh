#!/usr/bin/env bash
# Neuronix default: gtksync (Waybar gtk-sync status/menu).
set -euo pipefail

ROOT="${NEURONIX_SERVICE_ROOT:-$(cd "$(dirname "$0")" && pwd)}"
NAME="${NEURONIX_SERVICE_NAME:-$(basename "$ROOT")}"

chmod +x "$ROOT/waybar/gtk-sync-status.sh" "$ROOT/waybar/gtk-sync-menu" 2>/dev/null || true

mkdir -p /usr/local/bin
ln -sfn "${ROOT}/waybar/gtk-sync-status.sh" /usr/local/bin/gtk-sync-status
# KvNix configs/neuronix/gtk-sync-menu is the centered menu. Keep that copy
# when the ISO staged it; otherwise use the stock service script.
if [[ -f /etc/skel/configs/neuronix/gtk-sync-menu ]]; then
  cp -a /etc/skel/configs/neuronix/gtk-sync-menu /usr/local/bin/gtk-sync-menu
  chmod 0755 /usr/local/bin/gtk-sync-menu
else
  ln -sfn "${ROOT}/waybar/gtk-sync-menu" /usr/local/bin/gtk-sync-menu
fi

echo "[$NAME] installed waybar/{gtk-sync-status,gtk-sync-menu}"
