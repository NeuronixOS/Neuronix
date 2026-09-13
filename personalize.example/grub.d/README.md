# personalize/grub.d/

Optional GRUB drop-in. When `neuronix-product.cfg` is present it **replaces**
stock `default/grub.d/neuronix-product.cfg` in the ISO chroot
(`/etc/default/grub.d/neuronix-product.cfg`).

Debian sources every file in that directory after `/etc/default/grub`, so this
is how a KvNix (or other) overlay sets `GRUB_DISTRIBUTOR` without editing
Neuronix overlay files.

## Example `neuronix-product.cfg`

```bash
GRUB_DISTRIBUTOR="KvNix"
```

Leave this folder as README-only to keep the stock Neuronix distributor.
