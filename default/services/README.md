# Neuronix default services

Stock services staged into every ISO via `share/merge-personalize-dropins.sh`
(`default/services` first; `personalize/services` overlays same names).

Each `<name>/` → `/usr/local/lib/neuronix/services/<name>/`. Chroot hook
`9930-neuronix-personalize-services.hook.chroot` runs each `install.sh`.

| Service | Notes |
|---------|--------|
| gtksync | Waybar `custom/gtk-sync` status/menu for gtk-sync-client |

Personalize-only services (hostreporter, remux, …) stay under
`personalize/services/` — see `personalize.example/services/`.
