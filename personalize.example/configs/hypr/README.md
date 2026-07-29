# personalize/configs/hypr/

Stock session config lives in `default/configs/hypr/`. Deep-merge overlays
same-named files only — **do not** replace `hyprland.conf` unless you want a full fork.

Stock `hyprland.conf` ends with `source = ./binds-personal.conf`. Put extra binds here.

## Example `binds-personal.conf`

```conf
# Optional personalize binds (sourced by stock hyprland.conf)
bind = CTRL ALT, J, exec, neuronix-launch gtk-files /home/$USER/SORT
bind = CTRL ALT, T, exec, gtk-term
```
