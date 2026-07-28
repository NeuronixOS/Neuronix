# Neuronix personalize overlay

This directory is a **TEMPLATE**. Your real overrides go in `../personalize/`
(gitignored — never committed).

Stock defaults live under `../default/`. Optional drop-ins under `personalize/`
are staged by [`share/merge-personalize-dropins.sh`](../share/merge-personalize-dropins.sh).

```text
personalize/
  install-list / images / metadata   # packages + branding (existing)
  browser-extensions/                # Chrome extensions (see contract below)
  configs/                           # managed ~/configs + links.json map
    crontab/crontab.conf             # user crontab (overrides default/; skipped from skel copy)
  services/                          # custom services with install.sh
  install/                           # Calamares Desktop-only scripts (e.g. Cursor)
  gtk-apps/                          # extra/override GTK binaries (on top of default/)
```

## Quick start

```bash
cp -a personalize.example personalize

# Optional Devices drop-ins (private — never commit):
cp -a ~/Dropbox/Devices/Browser/.          personalize/browser-extensions/
cp -a ~/Dropbox/Devices/Cloud-Configs/.    personalize/configs/
cp -a ~/Dropbox/Devices/Services/.         personalize/services/
# Optional: extra GTK apps (beyond default/gtk-apps core suite)
# mkdir -p personalize/gtk-apps/bin personalize/gtk-apps/applications
# cp /path/to/my-gtk-app personalize/gtk-apps/bin/
# cp /path/to/my-gtk-app.desktop personalize/gtk-apps/applications/
# Optional: your real user crontab (overrides default blank template)
# cp ~/Dropbox/Devices/Backups/backedup-desktop-*/crontab/crontab.conf \
#    personalize/configs/crontab/crontab.conf

# Keep / refresh the Neuronix link map after copying Devices configs:
cp -n personalize.example/configs/links.json personalize/configs/links.json
# Web configs → configs/apache + configs/nginx + hosts + htpasswd (new layout only)

# Ensure each service has an install.sh (see example):
# cp personalize.example/services/install.sh.example \
#    personalize/services/<Name>/install.sh

./build.sh
```

---

## `configs/` — managed home configs + JSON map

### Layout

```text
configs/
  links.json              # REQUIRED mapping (home + system)
  bashrc
  bash_profile
  vimrc
  ssh/                    # → ~/.ssh
  file-templates/         # → ~/Templates
  gtk-apps/               # → ~/.config/gtk-apps
  hypr/                   # → ~/.config/hypr
  waybar/                 # → ~/.config/waybar
  fuzzel/                 # → ~/.config/fuzzel
  mako/                   # → ~/.config/mako
  gtk-3.0/                # → ~/.config/gtk-3.0  (nwg-look)
  gtk-4.0/                # → ~/.config/gtk-4.0  (nwg-look)
  gtkrc-2.0               # → ~/.gtkrc-2.0       (nwg-look)
  icons/default/          # → ~/.icons/default   (nwg-look cursor)
  xsettingsd/             # → ~/.config/xsettingsd (nwg-look)
  apache/                 # → /etc/apache2/* (system; personalize only — not in default/)
  nginx/                  # → /etc/nginx/* (system; personalize only — not in default/)
  hosts                   # → /etc/hosts
  htpasswd                # → /etc/apache2/.htpasswd
  …                       # anything else you want under ~/configs
```

Everything under `configs/` is copied to **`~/configs`** (`/etc/skel/configs` on the ISO).
Home paths then **symlink** into that folder per `links.json` (real locations → `~/configs/…`).

```text
~/configs/hypr/hyprland.conf     ← stock from default/, overlay from personalize/
~/.config/hypr  ──symlink──►  ~/configs/hypr
```

Personalize `.gitkeep` stubs do **not** wipe default trees (merge skips stub-only dirs).

**Git tracking:** if `personalize/configs/.git` exists, it is staged to
`/etc/skel/configs/.git` → **`~/configs/.git`** on live/installed systems, so the user’s
config repo moves with the machine. Prefer `git init` inside `configs/` (not the parent
`personalize/` tree). A bare `personalize/.git` is only used as a fallback when
`configs/.git` is missing.

### `links.json` contract

```json
{
  "skip": ["links.json"],
  "links": [
    { "from": "bashrc", "to": ".bashrc", "type": "symlink" },
    { "from": "gtk-apps", "to": ".config/gtk-apps", "type": "symlink" }
  ],
  "system": [
    { "from": "hosts", "to": "/etc/hosts", "type": "symlink" },
    { "from": "htpasswd", "to": "/etc/apache2/.htpasswd", "type": "symlink" },
    { "from": "apache/apache2.conf", "to": "/etc/apache2/apache2.conf", "type": "symlink" }
  ]
}
```

| Field | Meaning |
|-------|---------|
| `from` | Path relative to `configs/` (source file or directory) |
| `to` | Home-relative path (`links`) or absolute `/etc/...` path (`system`) |
| `type` | `symlink` or `copy` |
| `skip` | Top-level names under `configs/` **not** copied into `~/configs` |
| `system` | Maps into `/etc` (source staged at `/etc/neuronix/configs/`) |

Rules:

- A link is applied **only if** `configs/<from>` exists after the copy.
- Home symlinks are **relative**, so they survive skel → `/home/<user>` copy.
- System entries symlink `/etc/...` → `/etc/neuronix/configs/<from>` (managed central copy, not `$HOME`).
- If `links.json` is missing, the build uses [`share/configs-links.default.json`](../share/configs-links.default.json).
- Ship your map as `configs/links.json` whenever you customize destinations.
- A sample map is in this template: [`configs/links.json`](configs/links.json).

### Default mapping (Neuronix) — home

| `~/…` | `~/configs/…` |
|-------|----------------|
| `.bashrc` | `bashrc` |
| `.bash_profile` | `bash_profile` |
| `.vimrc` | `vimrc` |
| `.ssh` | `ssh/` |
| `.profile` | `ssh/profile` |
| `Templates` | `file-templates/` |
| `.config/gtk-apps` | `gtk-apps/` |
| `.config/hypr` | `hypr/` |
| `.config/waybar` | `waybar/` |
| `.config/fuzzel` | `fuzzel/` |
| `.config/mako` | `mako/` |
| `.config/gtk-3.0` | `gtk-3.0/` |
| `.config/gtk-4.0` | `gtk-4.0/` |
| `.gtkrc-2.0` | `gtkrc-2.0` |
| `.icons/default` | `icons/default/` |
| `.config/xsettingsd` | `xsettingsd/` |

Waybar stock (CPU/RAM %, click → `btop`) is in [`default/configs/waybar/`](../default/configs/waybar/).
Override with [`configs/waybar/`](configs/waybar/) in this template (see that folder’s README).

Hyprland: stock `hyprland.conf` sources `./binds-personal.conf`. Put extra binds in
[`configs/hypr/binds-personal.conf`](configs/hypr/binds-personal.conf) only — configs
deep-merge so you do **not** replace the whole `hypr/` tree. See
[`configs/hypr/README.md`](configs/hypr/README.md).

Secrets: empty reference at [`configs/secrets/`](configs/secrets/) (see README +
`github-token.example`). Real tokens belong only in private `personalize/configs/secrets/`.

### Default mapping (Neuronix) — system (`/etc`)

Web server trees are **personalize-only** (not under `default/configs/`). Stock Desktop/Server
does not install apache2/nginx; drop site configs here and list the packages under
`personalize/install-list` `# --- server ---` (or rely on the chroot hook when site trees exist).

| `/etc/…` | `configs/…` (also `/etc/neuronix/configs/…`) |
|----------|-----------------------------------------------|
| `/etc/hosts` | `hosts` |
| `/etc/apache2/.htpasswd` | `htpasswd` |
| `/etc/apache2/apache2.conf` | `apache/apache2.conf` |
| `/etc/apache2/envvars` | `apache/envvars` |
| `/etc/apache2/sites-available` | `apache/sites-available/` |
| `/etc/apache2/sites-enabled` | `apache/sites-enabled/` |
| `/etc/nginx/nginx.conf` | `nginx/nginx.conf` |
| `/etc/nginx/sites-available` | `nginx/sites-available/` |
| `/etc/nginx/sites-enabled` | `nginx/sites-enabled/` |

If `apache/sites-*` (or `apache2.conf`) is present, the ISO chroot hook installs/enables **apache2**.  
If `nginx/sites-*` (or `nginx.conf`) is present, it installs/enables **nginx**.

Copy Devices web configs into the new layout:

```bash
mkdir -p personalize/configs/apache personalize/configs/nginx
cp Apache-Localhost/apache2.conf Apache-Localhost/envvars personalize/configs/apache/
cp -a Apache-Localhost/sites-available Apache-Localhost/sites-enabled personalize/configs/apache/
cp Apache-Localhost/Nginx/nginx.conf personalize/configs/nginx/
cp -a Apache-Localhost/Nginx/sites-available Apache-Localhost/Nginx/sites-enabled personalize/configs/nginx/
cp Apache-Localhost/hosts Apache-Localhost/htpasswd personalize/configs/
```

SSH keys under `configs/ssh/` are fine — `personalize/` is gitignored.

---

## `install/` — Calamares Desktop-only scripts

Scripts here run on the **installed target** during Calamares Desktop (after Chrome),
not on the live ISO squashfs.

| Script | Role |
|--------|------|
| `cursor.sh` | Install Cursor IDE via `/usr/share/neuronix/install-cursor.sh` |

Stock Neuronix Desktop no longer installs Cursor. Copy
[`install/cursor.sh.example`](install/cursor.sh.example) → `personalize/install/cursor.sh`
and `chmod +x` it when you want Cursor on a personal build.

See [`install/README.md`](install/README.md).

---

## `services/` — drop-in services with `install.sh`

### Layout

```text
services/
  <ServiceName>/
    install.sh            # REQUIRED (preferred install path)
    *.service             # unit file(s) — used by install.sh or fallback
    TYPE                  # optional: system|user (fallback only)
    …                     # scripts, configs, python, etc.
```

Each `<ServiceName>/` is copied to **`/usr/local/lib/neuronix/services/<ServiceName>/`**.

### `install.sh` contract (required)

Neuronix runs `install.sh` **inside the live-build chroot** via hook
`9930-neuronix-personalize-services.hook.chroot`.

Environment when invoked:

| Variable | Value |
|----------|--------|
| `cwd` | `/usr/local/lib/neuronix/services/<ServiceName>` |
| `NEURONIX_SERVICE_ROOT` | same directory |
| `NEURONIX_SERVICE_NAME` | `<ServiceName>` |

Your script **must**:

1. Be executable (`chmod +x install.sh`)
2. Be **idempotent**
3. Install using **`NEURONIX_SERVICE_ROOT`** (never Dropbox / `/home/USER/...` paths)
4. Place systemd units under `/etc/systemd/system/` (system) or
   `/etc/skel/.config/systemd/user/` (user) and enable them with `.wants/` symlinks

Starter template: [`services/install.sh.example`](services/install.sh.example).

```bash
cp personalize.example/services/install.sh.example \
   personalize/services/Remux/install.sh
chmod +x personalize/services/Remux/install.sh
# edit paths / unit handling as needed
```

### Fallback (no `install.sh`)

If `install.sh` is missing, Neuronix adapts any `*.service` files (rewrites Dropbox /
`__SCRIPT_DIR__` paths) and enables them from `WantedBy` / optional `TYPE` file.
Prefer writing a real `install.sh` for anything non-trivial.

---

## `browser-extensions/` — Chrome extensions

### Layout

```text
browser-extensions/
  <ExtensionName>/
    manifest.json         # REQUIRED (MV2 or MV3)
    …                     # background.js, icons/, etc.
```

Each folder with a `manifest.json` is staged to:

`/usr/share/neuronix/browser-extensions/<ExtensionName>/`

### How Chrome / Chromium get them (automatic)

1. **Launch path** — `neuronix-chrome` wraps Google Chrome and `neuronix-chromium`
   wraps Debian Chromium, each with `--load-extension=…` for every staged unpacked
   extension.
2. **Desktop / MIME** — stock `google-chrome*.desktop` / `chromium.desktop` and skel
   `mimeapps.list` are pointed at the Neuronix wrappers so normal launches include
   the extensions.
3. **Installed/available registration** — when Chrome or Chromium is installed
   ([`install-google-chrome.sh`](../neuronix-iso/overlay/includes.chroot/usr/share/neuronix/install-google-chrome.sh)
   or Desktop apt via `neuronix-apply-desktop-profile.sh`),
   [`register-chrome-extensions.sh`](../share/register-chrome-extensions.sh) packs
   each extension as a `.crx` and writes **External Extensions** JSON under
   `/opt/google/chrome/extensions/` and `/etc/chromium/extensions/` so they show up
   as available/installed (not only via `--load-extension`).

No per-extension install script is required — drop the folder and rebuild.

---

## Packages & branding

### Crontab (`configs/crontab/crontab.conf`)

User crontab installed for the **default user** (Calamares-created / LightDM autologin user)
via `neuronix-install-crontab.sh`.

| Source | Behavior |
|--------|----------|
| `default/configs/crontab/crontab.conf` | Stock blank template (comments only) |
| `personalize/configs/crontab/crontab.conf` | **Wins** when present — drop your real jobs here |

Staged to `/usr/share/neuronix/crontab.conf` at build time. Listed in `links.json` `skip` so it is not copied into `~/configs`. Example personal jobs:

```bash
cp ~/Dropbox/Devices/Backups/backedup-desktop-*/crontab/crontab.conf \
   personalize/configs/crontab/crontab.conf
```

### Packages (`install-list`)

Same format as `default/install-list`. Sections: `live` / `server` / `desktop` / `installer`.
Packages are **appended** onto the base list (duplicate names → base wins).

| Section | When installed |
|---------|----------------|
| `server` | **Every** disk install (Server + Desktop) |
| `desktop` | **Desktop profile only** (skipped on Server) |
| `live` / `installer` | Rarely needed in personalize (ISO bake / Calamares) |

Put daemons and CLI tools under `# --- server ---` (apache, nginx, docker, mariadb, git, …).
Put GUI and media apps under `# --- desktop ---` (gimp, blender, vlc, …).

Configs, gtk-apps, browser-extensions, and services are staged into the ISO for
**both** profiles (not stripped on Server unless the Server profile script clears
desktop skel paths).

### Branding

| Path | Purpose |
|------|---------|
| `images/calamares/` | welcome / sidebar images |
| `images/live/` | live wallpaper |
| `images/installed/` | installed wallpapers |
| `images/grub/` | GRUB backgrounds |
| `images/icons/` | menu / greeter icon |
| `metadata/debian.env` | sourced after `default/metadata/debian.env` |
| `metadata/debian.distro.conf` | replaces `/etc/neuronix/distro.conf` |

---

## `gtk-apps/` — additional / override GTK binaries

Core suite binaries live in committed [`default/gtk-apps/`](../default/gtk-apps/).
Drop **extra** apps (or replacements) here; the merge overlays them onto the same
ISO paths after defaults are staged.

### Layout

```text
gtk-apps/
  bin/<name>                 # → /usr/local/lib/neuronix/gtk-apps/<name>
                             #   + /usr/local/bin/<name> symlink
  applications/<name>.desktop
  apps/<name>/               # optional multi-file payloads (wrappers in bin/ use these)
  gtk-theme/                 # optional — overlays /usr/share/neuronix/gtk-theme/
                             #   (+ sibling copy under lib for Python discovery)
  skel-config/               # optional — overlays etc/skel/.config/gtk-apps/
```

Same-named files **replace** `default/gtk-apps` copies. Personal theme settings
still go under `configs/gtk-apps/` (linked to `~/.config/gtk-apps`).

Stub layout: [`gtk-apps/`](gtk-apps/).
