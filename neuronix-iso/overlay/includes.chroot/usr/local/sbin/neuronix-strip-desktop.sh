#!/usr/bin/env bash
# Calamares: after slim unpack — drop live-only LightDM autologin bits.
# Full desktop purge is Server-profile only (neuronix-apply-server-profile.sh).
set -euo pipefail

echo "[neuronix-strip] Cleaning live-session installer leftovers…"

rm -f /etc/lightdm/lightdm.conf.d/50-neuronix-live-autologin.conf \
	/etc/lightdm/lightdm.conf.d/10-neuronix-lightdm-debug.conf 2>/dev/null || true

echo "[neuronix-strip] Done."
