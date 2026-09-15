# Screensaver

Fullscreen GTK4 screensaver for Wayland (and X11). Covers every connected monitor.

Staged as KvNix personalize service → `/usr/local/lib/neuronix/services/screensaver/`
on the ISO (no Dropbox paths).

## Manual run

```bash
/usr/local/lib/neuronix/services/screensaver/screensaver.py
/usr/local/lib/neuronix/services/screensaver/screensaver.py --mode aurora
```

## Idle service

systemd user unit `neuronix-screensaver-idle` launches after **5 minutes** without
keyboard/mouse input (evdev). Unplugged receivers are dropped (a hung fd would
otherwise pin a CPU core). Config: `~/.config/neuronix-screensaver/config.ini`

```ini
[idle]
seconds = 300

[screensaver]
mode = clock
```

```bash
systemctl --user status neuronix-screensaver-idle
journalctl --user -u neuronix-screensaver-idle -f
```

## Prerequisites

- `python3-evdev`, `python3-gi`, `python3-cairo`, `gir1.2-gtk-4.0`
- `gir1.2-gtk4layershell-1.0` (overlay layer so floating windows cannot sit on top)
- User in the `input` group (Calamares `neuronix-add-user-input-group.sh`)
