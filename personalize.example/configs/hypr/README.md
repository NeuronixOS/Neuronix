# personalize/configs/hypr/

Stock session config lives in `default/configs/hypr/`. Deep-merge overlays
same-named files only — **do not** replace `hyprland.conf` unless you want a full fork.

Stock `hyprland.conf` sources `./monitors.conf` then ends with
`source = ./binds-personal.conf`. Put extra binds and workspace rules here
(or in `workspaces.conf` if you source it from binds-personal).

Do not use `monitor=…,addreserved,…` to leave a float strip: Hyprland clamps
xdg-popups to the non-reserved work area, so GTK/Chrome context menus fail on
windows in that zone. The KvNix overlay floats HDMI windows instead of using
a tiled `gapsout` inset.

KvNix parking lives in `window-manager.py` (HDMI 3×3 slots, slight cascade when
a slot is occupied, DP-3/DP-4 tiling, gtk-photos bottom-left then up, dialogs
centered). `binds-personal.conf` runs `$window_manager watch` and Ctrl+Super+Alt
parks windows. Do not name this script `hdmi-window-half.py` — that path is retired.

## Example `binds-personal.conf`

```conf
# Optional personalize binds (sourced by stock hyprland.conf)
bind = CTRL ALT, J, exec, neuronix-launch gtk-files /home/$USER/SORT
bind = CTRL ALT, T, exec, gtk-term
```
