# personalize/gtk-apps/skel-config/

Optional files overlaid onto `etc/skel/.config/gtk-apps/` at build time
(defaults for new users). Prefer `personalize/configs/gtk-apps/` for the managed
`~/configs` symlink map when possible.

## Example

```text
skel-config/
  theme.toml
  gtk-edit/config.toml
```
