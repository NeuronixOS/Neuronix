# Neuronix default services

Stock services staged via `share/merge-personalize-dropins.sh`
(`default/services` first; `personalize/services` overlays same names).

A service directory with `SCOPE=desktop` is skipped when the overlay is a
server tree (`personalize-server`, or `NEURONIX_LIVE_HOSTNAME=*-server`).
Calamares **Server** profile also strips remux / screensaver / gtksync if they
were on the live squashfs. Active-User and HostReporter stay.

Each `<name>/` → `/usr/local/lib/neuronix/services/<name>/`. Chroot hook
`9930-neuronix-personalize-services.hook.chroot` runs each `install.sh`.

| Service | SCOPE | Notes |
|---------|-------|--------|
| gtksync | desktop | Waybar `custom/gtk-sync` status/menu for gtk-sync-client |
| screensaver | desktop | GTK4 idle screensaver (`neuronix-screensaver-idle` user unit) |

KvNix desktop personalize adds remux (desktop) plus activeuser/hostreporter
(both profiles). See `personalize.example/services/` for the drop-in contract.
