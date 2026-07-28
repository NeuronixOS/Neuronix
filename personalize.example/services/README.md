# Example service drop-in layout (do not use this stub as a real service).
#
# personalize/services/<ServiceName>/
#   install.sh          # REQUIRED — Neuronix runs this in the ISO chroot
#   *.service           # optional if install.sh installs units itself
#   TYPE                # optional: "system" or "user" (fallback when no install.sh)
#   … your scripts/config …
#
# See ../README.md § services/
