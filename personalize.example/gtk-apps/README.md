# Example gtk-apps drop-in (do not ship empty stubs as real apps)

Additional GTK binaries layered **on top of** committed `default/gtk-apps/`.

```text
personalize/gtk-apps/
  bin/                 # preferred — executables → /usr/local/bin/<name>
  applications/        # *.desktop → /usr/share/applications/
  apps/<name>/         # optional multi-file payloads (bin/<name> wrappers launch these)
  gtk-theme/           # optional overlay of /usr/share/neuronix/gtk-theme/
  skel-config/         # optional files → ~/.config/gtk-apps/ (skel)
```

Same layout as `default/gtk-apps/` (plus optional `apps/`). Same-named binaries **replace** the default.
Suite settings still belong under `configs/gtk-apps/` (→ `~/.config/gtk-apps`).

See `../README.md` § gtk-apps/.
