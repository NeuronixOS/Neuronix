# Neuronix default GTK apps

Prebuilt release binaries for Neuronix daily apps (GTK4 suite). Staged into the ISO
by `neuronix-iso/setup.sh` → `/usr/local/lib/neuronix/gtk-apps/` + `/usr/local/bin/`
wrappers and `/usr/share/applications/` desktop files.

| Binary / tree | Role |
|---------------|------|
| `gtk-term` | Terminal (Super+Return) |
| `gtk-files` | File manager (Super+E) |
| `gtk-edit` | Text editor |
| `gtk-calc` | Calculator |
| `gtk-colors` | Color palette helper (`apps/gtk-colors/` + `bin/gtk-colors` wrapper) |
| `gtk-image` | Image viewer |
| `gtk-video` | Video trimmer (in/out on the timeline, crop/rotate/flip, export selection) |
| `gtk-theme-editor` | Suite color profile editor (Profile → Custom…) |
| `gtk-theme/` | Shared theme data (`profiles.json`, python helpers). The Rust crate is **statically linked** into each app; this tree is still required for tooling and reference profiles. |
| `gtk-sync/` | LAN file sync installer used by gtk-files (Setup Sync): `install.sh` / `uninstall.sh`, systemd units, and prebuilt `target/release/gtk-sync{,-client}` so setup works without cargo on the ISO. |
| `gtk-neuron/` | AI **Self Driving** daemon (`gtk-neurond`), Cursor worker (`python/cursor_worker.py` + optional `.venv`), and credentials template. Also staged as `bin/gtk-neurond` on PATH. |
| `skel-config/theme.toml` | Stock `~/.config/gtk-apps/theme.toml` when personalize does not supply configs/gtk-apps |

Self Driving (ꔮ / Ctrl+D) is built into gtk-files, gtk-term, gtk-edit, gtk-image, and gtk-video. On first use, paste a Gemini / Claude / Cursor API key in the panel (or copy `gtk-neuron/examples/credentials.toml` to `~/.config/gtk-apps/gtk-neuron/credentials.toml`).

Refresh from Devices after rebuilding apps:

```bash
~/Dropbox/Devices/GTK-Apps/syn-to-devices.sh
# or: PROJECTS_ROOT=/path/to/projects DEVICES_GTK_APPS=/path/to/GTK-Apps ./syn-to-devices.sh
```

That script copies the default suite into this tree and optional extras into
`personalize/gtk-apps/`.

Do **not** put personal settings here — use `personalize/configs/gtk-apps/`.
Extra / override binaries: drop them in `personalize/gtk-apps/` (same `bin/` +
`applications/` layout); the personalize merge overlays them onto the ISO after
this tree is staged.

## MIME / terminal defaults

ISO skel ships:

- `~/.config/mimeapps.list` — gtk-edit / gtk-image / gtk-files defaults
- `~/.config/xdg-terminals.list` — gtk-term
- `~/.local/bin/x-terminal-emulator` → `/usr/local/bin/gtk-term-launch.sh`
- chroot hook `1001-x-terminal-emulator` — Debian `update-alternatives`

Re-apply on a running system:

```bash
/usr/share/neuronix/gtk-apps/install-defaults.sh
```

Verify:

```bash
xdg-mime query default text/plain
xdg-mime query default image/png
xdg-mime query default inode/directory
cat ~/.config/xdg-terminals.list
readlink -f "$(command -v x-terminal-emulator)"
```
