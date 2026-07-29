# personalize/configs/waybar/

Override stock bar from `default/configs/waybar/` (CPU/RAM %, click → `btop`).
Drop `config` and/or `style.css` here; they merge into `~/configs/waybar` → `~/.config/waybar`.

## Example `config` (snippet)

```json
{
  "layer": "top",
  "position": "top",
  "height": 32,
  "modules-left": ["custom/menu", "hyprland/workspaces"],
  "modules-center": ["hyprland/window"],
  "modules-right": ["pulseaudio", "network", "cpu", "memory", "battery", "clock", "tray"],
  "cpu": {
    "interval": 2,
    "format": "\uf2db {usage}%",
    "on-click": "foot -T btop -a org.neuronix.btop btop"
  },
  "memory": {
    "interval": 2,
    "format": "\uf1c0 {percentage}%",
    "on-click": "foot -T btop -a org.neuronix.btop btop"
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
