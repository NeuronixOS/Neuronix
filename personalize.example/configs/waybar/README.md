# personalize/configs/waybar/

Override stock bar from `default/configs/waybar/` (CPU/RAM %, click popovers, power icon).
Drop `config` and/or `style.css` here; they merge into `~/configs/waybar` → `~/.config/waybar`.
Keep `custom/power` if you replace the full module list (Log Out / Reboot / Shut Down).

## Example `config` (snippet)

```json
{
  "layer": "top",
  "position": "top",
  "height": 32,
  "modules-left": ["custom/menu", "hyprland/workspaces"],
  "modules-center": ["hyprland/window"],
  "modules-right": ["pulseaudio", "network", "cpu", "memory", "battery", "custom/power", "tray"],
  "cpu": {
    "interval": 2,
    "format": "\uf2db {usage}%",
    "on-click": "neuronix-waybar-click cpu"
  },
  "memory": {
    "interval": 2,
    "format": "\uf1c0 {percentage}%",
    "on-click": "neuronix-waybar-click memory"
  }
}
```

## Example `style.css` (snippet)

```css
* {
  font-family: "Cantarell", sans-serif;
  font-size: 13px;
  color: #f5f5f5;
}
window#waybar {
  background-color: #0a0a0a;
  border-bottom: 2px solid #444444;
}
```
