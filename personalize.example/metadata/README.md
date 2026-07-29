# personalize/metadata/

Optional branding / distro identity overlays. Copied into private
`personalize/metadata/` (no `.sample` suffix).

## Example `debian.env`

Sourced **after** `default/metadata/debian.env` — set only keys you want to change:

```bash
# NEURONIX_PRODUCT_NAME=MyNeuronix
# NEURONIX_LIVE_HOSTNAME=my-neuronix
# NEURONIX_PRODUCT_VERSION=0.1
```

## Example `debian.distro.conf`

Replaces `/etc/neuronix/distro.conf` when present:

```bash
# NEURONIX_DISTRO=debian
# NEURONIX_SUITE=trixie
# NEURONIX_PRODUCT_NAME=MyNeuronix
# NEURONIX_LIVE_HOSTNAME=my-neuronix
# NEURONIX_DESKTOP_SESSION=neuronix-hyprland
# NEURONIX_CALAMARES_INSTALLER=calamares-install-debian
# NEURONIX_ENABLE_BACKPORTS=1
# NEURONIX_FLATPAK_DECIBELS=0
```
