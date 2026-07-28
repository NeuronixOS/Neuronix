# Example browser-extensions layout
#
# personalize/browser-extensions/<ExtensionName>/
#   manifest.json       # REQUIRED (MV2 or MV3)
#   … extension files …
#
# Neuronix stages each folder to /usr/share/neuronix/browser-extensions/<Name>/
# and registers them with Google Chrome / Chromium (CRX + External Extensions)
# via neuronix-chrome and neuronix-chromium when those browsers are installed.
# See ../README.md § browser-extensions/
