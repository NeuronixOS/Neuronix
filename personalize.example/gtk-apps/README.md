# personalize/gtk-apps/

Additional GTK binaries layered **on top of** committed `default/gtk-apps/`.
Same-named files replace defaults. Suite settings still belong under
`configs/gtk-apps/` (→ `~/.config/gtk-apps`).

## Example layout

```text
gtk-apps/
  bin/my-tool                 # → /usr/local/lib/neuronix/gtk-apps/my-tool
                              #   + /usr/local/bin/my-tool symlink
  applications/my-tool.desktop
  apps/my-tool/               # optional multi-file payload
    my-tool                   # real binary/script
  gtk-theme/                  # optional overlay of /usr/share/neuronix/gtk-theme/
  skel-config/                # optional → etc/skel/.config/gtk-apps/
```

See subfolder READMEs for file examples.
