# gtk-sync Waybar helpers (Neuronix default)

Waybar status module + click menu for the **gtk-sync** client. Shipped from
`Neuronix/default/services/gtksync/` on every Neuronix machine.

## Files

- `waybar/gtk-sync-status.sh` — Waybar JSON (`Sync ✓` / syncing / stopped)
- `waybar/gtk-sync-menu` — centered GTK menu (Open folder, Start/Stop, Status, …)

Status is taken from `$XDG_RUNTIME_DIR/gtk-sync/status.json` only while
`gtk-sync-client.service` is active (same rule as gtk-files).

## Waybar

`install.sh` links:

- `/usr/local/bin/gtk-sync-status` → `waybar/gtk-sync-status.sh`
- `/usr/local/bin/gtk-sync-menu` → `waybar/gtk-sync-menu`

`default/configs/waybar` includes `custom/gtk-sync` on the right side.
Click opens the centered settings dialog; Status / logs open on the right.
