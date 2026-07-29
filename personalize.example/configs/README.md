# personalize/configs/

Managed home + system configs. Everything here (except `links.json` `skip` entries)
is copied to `~/configs` on the ISO. `links.json` `links` create home symlinks;
`system` rows make `/etc/...` → `~/configs/...` (via `neuronix-link-system-configs.sh`).

This example tree is **stub-only** (READMEs). Copy real files into your private
`../personalize/configs/` — merge skips stub dirs so stock `default/configs/` is kept.

## Example layout

```text
configs/
  links.json                 # REQUIRED when customizing destinations
  bashrc
  bash_profile
  vimrc
  ssh/
  file-templates/
  gtk-apps/
  hypr/binds-personal.conf
  waybar/{config,style.css}
  fuzzel/fuzzel.ini
  mako/config
  gtk-3.0/  gtk-4.0/  gtkrc-2.0
  icons/default/
  xsettingsd/xsettingsd.conf
  crontab/crontab.conf       # skipped from ~/configs copy
  apache/  nginx/  hosts  htpasswd
  secrets/github-token       # private only
```

## Example `links.json`

```json
{
  "skip": ["links.json", "apache", "nginx", "crontab"],
  "links": [
    { "from": "bashrc", "to": ".bashrc", "type": "symlink" },
    { "from": "bash_profile", "to": ".bash_profile", "type": "symlink" },
    { "from": "vimrc", "to": ".vimrc", "type": "symlink" },
    { "from": "ssh", "to": ".ssh", "type": "symlink" },
    { "from": "ssh/profile", "to": ".profile", "type": "symlink" },
    { "from": "file-templates", "to": "Templates", "type": "symlink" },
    { "from": "gtk-apps", "to": ".config/gtk-apps", "type": "symlink" },
    { "from": "hypr", "to": ".config/hypr", "type": "symlink" },
    { "from": "waybar", "to": ".config/waybar", "type": "symlink" },
    { "from": "fuzzel", "to": ".config/fuzzel", "type": "symlink" },
    { "from": "mako", "to": ".config/mako", "type": "symlink" },
    { "from": "gtk-3.0", "to": ".config/gtk-3.0", "type": "symlink" },
    { "from": "gtk-4.0", "to": ".config/gtk-4.0", "type": "symlink" },
    { "from": "gtkrc-2.0", "to": ".gtkrc-2.0", "type": "symlink" },
    { "from": "icons/default", "to": ".icons/default", "type": "symlink" },
    { "from": "xsettingsd", "to": ".config/xsettingsd", "type": "symlink" }
  ],
  "system": [
    { "from": "hosts", "to": "/etc/hosts", "type": "symlink" },
    { "from": "htpasswd", "to": "/etc/apache2/.htpasswd", "type": "symlink" },
    { "from": "apache/apache2.conf", "to": "/etc/apache2/apache2.conf", "type": "symlink" },
    { "from": "apache/envvars", "to": "/etc/apache2/envvars", "type": "symlink" },
    { "from": "apache/sites-available", "to": "/etc/apache2/sites-available", "type": "symlink" },
    { "from": "apache/sites-enabled", "to": "/etc/apache2/sites-enabled", "type": "symlink" },
    { "from": "nginx/nginx.conf", "to": "/etc/nginx/nginx.conf", "type": "symlink" },
    { "from": "nginx/sites-available", "to": "/etc/nginx/sites-available", "type": "symlink" },
    { "from": "nginx/sites-enabled", "to": "/etc/nginx/sites-enabled", "type": "symlink" }
  ]
}
```

If `links.json` is missing, the build uses `share/configs-links.default.json`.
See each subdirectory README for file-level examples.
