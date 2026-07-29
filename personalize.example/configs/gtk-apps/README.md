# personalize/configs/gtk-apps/

Suite settings → `~/.config/gtk-apps`. Overlay same-named files onto
`default/configs/gtk-apps/` (deep-merge).

## Example top-level files

```text
gtk-apps/
  theme.toml                 # active profile / theme selection
  custom-profiles.json       # optional custom color profiles
  gtk-edit/config.toml
  gtk-files/{config.toml,places.toml}
  gtk-term/state.toml
```

## Example `theme.toml` (snippet)

```toml
profile = "Adwaita-dark"
```

Per-app examples live in the subfolder READMEs.
