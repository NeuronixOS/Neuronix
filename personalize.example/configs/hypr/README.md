# personalize/configs/hypr/

Stock session config lives in `default/configs/hypr/`. Deep-merge overlays
same-named files only — **do not** replace `hyprland.conf` unless you want a full fork.

Stock `hyprland.conf` sources `./monitors.conf` then ends with
`source = ./binds-personal.conf`. Put extra binds and workspace rules here
(or in `workspaces.conf` if you source it from binds-personal).

To customize window parking / overview / named outputs, drop a full
`window-manager.py` here. It replaces the stock no-op at
`default/configs/hypr/window-manager.py`. Wire it from `binds-personal.conf`:

```conf
$window_manager = $HOME/.config/hypr/window-manager.py
exec-once = $window_manager watch
bind = CTRL SUPER ALT, 2, exec, $window_manager bottom
```

Do not use `monitor=…,addreserved,…` to leave a float strip: Hyprland clamps
xdg-popups to the non-reserved work area, so GTK/Chrome context menus fail on
windows in that zone.

## Example `binds-personal.conf`

```conf
# Optional personalize binds (sourced by stock hyprland.conf)
bind = CTRL ALT, J, exec, neuronix-launch gtk-files /home/$USER/SORT
bind = CTRL ALT, T, exec, gtk-term
```
