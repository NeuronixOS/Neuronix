# Hyprland personalize overlay

Stock session config lives in `Neuronix/Build/default/configs/hypr/`
(`hyprland.conf`, `hyprpaper.conf`, …).

**Do not replace `hyprland.conf` here** unless you intend a full fork.

To add machine-specific keybinds:

1. Put binds in `binds-personal.conf` (stock `hyprland.conf` ends with
   `source = ./binds-personal.conf`).
2. Deep-merge keeps default siblings — only same-named files are overwritten.

Example (private `personalize/configs/hypr/binds-personal.conf`):

```conf
bind = CTRL ALT, J, exec, neuronix-launch gtk-files /home/you/SORT
```

Secrets (tokens, etc.) go under `configs/secrets/` and land at
`~/configs/secrets/` after merge — not under `hypr/`.
