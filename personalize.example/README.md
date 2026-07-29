# Neuronix personalize overlay

This directory is a **TEMPLATE**. Your real overrides go in `../personalize/`
(gitignored — never committed).

Stock defaults live under `../default/`. Optional drop-ins under `personalize/`
are staged by [`share/merge-personalize-dropins.sh`](../share/merge-personalize-dropins.sh).

**Template rule:** folders here (except `images/`) contain only `README.md`
documenting example content. Copy real files into private `personalize/`.
`README.md` / `.gitkeep` stubs are skipped by the merge so they do not wipe
`default/` trees.

```text
personalize/
  install-list                     # packages (this template keeps a real file)
  images/                          # branding assets (real placeholders OK)
  metadata/                        # debian.env / distro.conf — see README
  browser-extensions/              # Chrome extensions — see README
  configs/                         # ~/configs + links.json — see README
  services/                        # install.sh + units — see README
  install/                         # Calamares Desktop scripts — see README
  hooks/                           # first-login user scripts — see README
  gtk-apps/                        # extra/override GTK binaries — see README
```

## Quick start

```bash
cp -a personalize.example personalize
# Remove README stubs you do not need; add real files per each folder’s README.

# Optional private drop-ins:
# cp -a /path/to/browser-extensions/.  personalize/browser-extensions/
# cp -a /path/to/cloud-configs/.       personalize/configs/
# cp -a /path/to/services/.            personalize/services/

# Create configs/links.json (example in configs/README.md) when customizing maps:
# cp …  personalize/configs/links.json

./build.sh
```

---

## `configs/` — managed home configs + JSON map

See [`configs/README.md`](configs/README.md) for layout and a full `links.json`
example. Subfolders each document their file formats.

Everything under `configs/` is copied to **`~/configs`** (`/etc/skel/configs` on
the ISO). Home paths then **symlink** into that folder per `links.json`.

Personalize README stubs do **not** wipe default trees (merge skips stub-only dirs).

**Git tracking:** if `personalize/configs/.git` exists, it is staged to
`/etc/skel/configs/.git` → **`~/configs/.git`**. Prefer `git init` inside
`configs/` (not the parent `personalize/` tree).

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

Hyprland: stock `hyprland.conf` sources `./binds-personal.conf` — see
[`configs/hypr/README.md`](configs/hypr/README.md).

### Default mapping (Neuronix) — system (`/etc`)

Web server trees are **personalize-only**. See
[`configs/apache/README.md`](configs/apache/README.md) and
[`configs/nginx/README.md`](configs/nginx/README.md).

Everything listed below also lives under **`~/configs`** (git-friendly). After
user creation, `neuronix-link-system-configs.sh` makes `/etc/...` a symlink
**into** that tree (e.g. `/etc/apache2/sites-enabled` →
`~/configs/apache/sites-enabled`).

| `/etc/…` | `~/configs/…` |
|----------|-------------|
| `/etc/hosts` | `hosts` |
| `/etc/apache2/.htpasswd` | `htpasswd` |
| `/etc/apache2/*` | `apache/…` |
| `/etc/nginx/*` | `nginx/…` |

If `apache/sites-*` (or `apache2.conf`) is present, the ISO chroot hook
installs/enables **apache2**. Same for nginx.

SSH keys under `configs/ssh/` are fine — `personalize/` is gitignored.

---

## `install/` — Calamares Desktop scripts

Scripts run on the **installed target** during Calamares Desktop (after Chrome).
Same basename under `personalize/install/` **replaces** `default/install/`.

Example: [`install/README.md`](install/README.md) (`cursor.sh`).

---

## `hooks/` — first-login user scripts

Merged to `/usr/share/neuronix/user-hooks/`; run **once** as the desktop user on
first Hyprland login after install (skipped on live).

Example: [`hooks/README.md`](hooks/README.md) (`git-meld.sh`).

---

## `services/` — drop-in services with `install.sh`

See [`services/README.md`](services/README.md) for `install.sh` + unit examples.

Each `<ServiceName>/` → `/usr/local/lib/neuronix/services/<ServiceName>/`.
Prefer a real `install.sh`; fallback rewrites `__SCRIPT_DIR__` in `*.service` files.

---

## `browser-extensions/` — Chrome extensions

See [`browser-extensions/README.md`](browser-extensions/README.md) for layout and
a sample `manifest.json`. Staged to `/usr/share/neuronix/browser-extensions/`.

---

## Packages & branding

### Crontab

See [`configs/crontab/README.md`](configs/crontab/README.md).
`personalize/configs/crontab/crontab.conf` wins over the default blank template.

### Packages (`install-list`)

Same format as `default/install-list`. Sections: `live` / `server` / `desktop` /
`installer`. Packages are **appended** onto the base list (duplicate names → base wins).

| Section | When installed |
|---------|----------------|
| `server` | **Every** disk install (Server + Desktop) |
| `desktop` | **Desktop profile only** |
| `live` / `installer` | Rarely needed in personalize |

Put daemons/CLI under `# --- server ---`; GUI/media under `# --- desktop ---`.

### Branding

| Path | Purpose |
|------|---------|
| `images/calamares/` | welcome / sidebar images |
| `images/live/` | live wallpaper |
| `images/installed/` | installed wallpapers |
| `images/grub/` | GRUB backgrounds |
| `images/icons/` | menu / greeter icon |
| `metadata/debian.env` | see [`metadata/README.md`](metadata/README.md) |
| `metadata/debian.distro.conf` | see [`metadata/README.md`](metadata/README.md) |

---

## `gtk-apps/` — additional / override GTK binaries

Core suite: [`default/gtk-apps/`](../default/gtk-apps/). Drop extras/replacements
here — see [`gtk-apps/README.md`](gtk-apps/README.md) and subfolder READMEs.
