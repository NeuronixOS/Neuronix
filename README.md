# Neuronix

**Neuronix** is a Debian Trixie workstation live ISO built around **Hyprland** on Wayland. After a Desktop install, LightDM autologins into the `neuronix-hyprland` session.

| | |
|---|---|
| **Target machine** | `neuronix` |
| **Base layer** | Debian 13 Trixie (trixie-backports for kernel ~7.0.x and Hyprland) |
| **Compositor** | Hyprland (Wayland native) |
| **Look** | GTK **Adwaita-dark**; icons **Papirus** (yellow/manila folders); Hyprland chrome **black / red / white** |

Canonical packages: [`default/install-list`](default/install-list) — a **bare minimum** so live / Desktop / Server can boot and run. Optional apps and branding go in a gitignored [`personalize/`](personalize.example/) overlay that mirrors `default/` (start from [`personalize.example/`](personalize.example/)). The live ISO is **slim** (Hyprland chrome + net/browser). Calamares apt-installs stacks after unpack — **Desktop** (server + desktop) or **Server** (console + SSH, purge live GUI). Disk installs need **network**.

## What you get

| Session | Behavior |
|---------|----------|
| **Live ISO** | Slim Hyprland + Waybar + Firefox; Calamares starts automatically |
| **Desktop install** (default) | Apt-install server + desktop stacks → LightDM autologin → `neuronix-hyprland` (+ Chrome; Cursor via `personalize/install` only) |
| **Server install** | Apt-install server stack → purge slim-live GUI + Hyprland runtime → strip desktop skel/gtk-apps → console + SSH |

---

## Architecture — backports & Hyprland

To get a modern, hardware-accelerated Wayland desktop while keeping Debian’s stability, use the official **backports** channel for the graphics stack. The live ISO already does this via hook 997; the steps below are the manual equivalent.

### Add Debian Backports

Edit `/etc/apt/sources.list` or create `/etc/apt/sources.list.d/backports.list`:

```text
deb http://deb.debian.org/debian trixie-backports main contrib non-free non-free-firmware
```

```bash
sudo apt update
```

### Install compositor stack (from backports)

```bash
sudo apt install -t trixie-backports \
  hyprland xdg-desktop-portal-hyprland hyprpaper hyprpicker \
  linux-image-amd64 linux-headers-amd64
```

Associated infrastructure (also on the ISO):

- **Waybar** — status & system telemetry bar
- **Fuzzel** — Wayland-native application menu
- **Mako** — minimalist notification daemon

### Toolkit integration (`hyprland.conf`)

GNOME/GTK apps assume GNOME Shell. Pass environment flags so themes and dark mode behave on Hyprland. Append to `~/.config/hypr/hyprland.conf` (the ISO skel already ships equivalent settings):

```conf
# --- Toolkit & Portal Tweaks ---
env = ADW_DISABLE_PORTAL,1
env = GTK_THEME,Adwaita-dark

# --- Performance & Window Styling Rules ---
decoration {
    rounding = 10
    blur {
        enabled = true
        size = 8
        passes = 3
    }
}

exec-once = dbus-update-activation-environment --systemd WAYLAND_DISPLAY XDG_CURRENT_DESKTOP=Hyprland
```

---

## Hyprland desktop tech stack

What is **baked into the slim live ISO** and what **Calamares apt-installs on disk** are not the same. The stack below is the Hyprland experience (live chrome + full Desktop install).

### Boot → session

```text
GRUB → Linux (trixie-backports ~7.0.x) → LightDM → neuronix-hyprland → start-hyprland
```

| Layer | Component | Notes |
|-------|-----------|--------|
| Display manager | **LightDM** + gtk greeter | Live ISO autologins as `live`; installed disk autologins into Hyprland |
| Wayland compositor | **Hyprland** (backports) | Tiling WM; `start-hyprland` + `hyprland-guiutils` |
| Session entry | `neuronix-hyprland-session.sh` | Sets env, execs `start-hyprland` |
| Session startup | `neuronix-hyprland-session-start.sh` | `exec-once` from `hyprland.conf` |
| Wallpaper | **hyprpaper** | Neuronix background via `hyprpaper.conf` |

### Started automatically at login

These daemons/apps are launched by `neuronix-hyprland-session-start.sh` (or Hyprland `exec-once`):

| Role | Running app |
|------|-------------|
| Status bar | **Waybar** (Font Awesome icons, black/red/white CSS) |
| Notifications | **Mako** |
| Wallpaper | **hyprpaper** |
| Privilege prompts | **mate-polkit** authentication agent |
| Portals | **xdg-desktop-portal-hyprland** + gtk portal (restarted after compositor up) |
| Live ISO only | **Calamares** (single-instance flock) |

### Shell UI (keybind-driven)

| Role | App | Default bind |
|------|-----|--------------|
| App launcher | **Fuzzel** | `Ctrl+Super`, `Super+A` |
| Workspace overview | **Hyprspace** (4 persistent desktops) | `Super` (release alone) |
| Settings hub | **neuronix-settings** (layer-shell card menu) | `Super+,` |
| File manager | **gtk-files** | `Super+E` |
| Text editor | **gtk-edit** | `Super+G` |
| Terminal | **gtk-term** | `Super+Enter` / `Super+T` |
| Monitor layout | **nwg-displays** | `Super+Shift+M` |
| Screenshot region | **grim** + **slurp** → **wl-clipboard** | `Super+Print` |
| Brightness | **brightnessctl** | Fn keys |
| Volume | **PipeWire** / **wpctl** | Fn keys |

### Session environment (Layer B — one block, all GTK/Qt apps)

Applied in `hyprland.conf`, `neuronix-hyprland-session-env.sh`, and `dbus-update-activation-environment`:

| Variable / service | Purpose |
|--------------------|---------|
| `GSK_RENDERER=cairo` | GTK4 apps that need a stable renderer on Hyprland |
| `GTK_THEME=Adwaita-dark` + dconf `color-scheme` | Dark GTK without deprecated prefer-dark |
| `QT_QPA_PLATFORM=wayland;xcb` | Qt apps (VLC, Kdenlive, …) |
| `XDG_CURRENT_DESKTOP=Hyprland` | Session identity for apps and portals |
| **PipeWire** + **wireplumber** | Audio in/out |
| **NetworkManager** | Wi-Fi / Ethernet (`nm-connection-editor` from settings) |

### Settings hub (`neuronix-settings`)

Layer-shell card menu (shared `neuronix_choice_dialog.py`) — **no GNOME Control Center**. Each item launches a focused tool:

| Category | App |
|----------|-----|
| Display | **nwg-displays** |
| Network | **nm-connection-editor** |
| Sound | **pavucontrol** |
| Bluetooth | **blueman-manager** |
| Appearance | **nwg-look** |
| Background | **neuronix-change-background** (hyprpaper) |
| Keyboard | **gtk-edit** → `~/.config/hypr/hyprland.conf` |
| Power | **xfce4-power-manager** |
| Printers | **system-config-printer** |
| Disks | **gparted** |
| Advanced | **dconf-editor** |

### nwg-* tools (Debian packages — installed, not full nwg-shell)

Neuronix ships the **nwg-* packages available in Debian Trixie**, not the full upstream nwg-shell stack (no nwg-panel / nwg-drawer in apt). Waybar + Fuzzel + Mako remain the primary shell chrome.

| Package | Role | Auto-started? |
|---------|------|---------------|
| **nwg-displays** | Monitor resolution and layout | Via keybind / settings |
| **nwg-look** | GTK theme, icons, cursors | Via settings |
| **nwg-bar** | GTK quick-action button bar | No — launch from menu when needed |
| **nwg-clipman** | Clipboard history GUI (cliphist) | No — launch when needed |
| **nwg-hello** | greetd greeter UI | No — LightDM stays default; optional future use |

Also installed: **kanshi** (monitor hot-plug profiles), **blueman**. Display tool **wdisplays** was replaced by **nwg-displays**.

### Problem apps (Layer C wrappers)

| App | Launch |
|-----|--------|
| **audacity**, **blender** | Menu entries → `neuronix-x11-app` (`GDK_BACKEND=x11` / XWayland) |

### Installed by Calamares Desktop only (not on live ISO)

| App | How |
|-----|-----|
| **google-chrome-stable** | `install-google-chrome.sh` (live hook 996 disabled) |
| **Cursor** | Helper `install-cursor.sh` on ISO; **not** stock Desktop — `personalize/install/cursor.sh` (live hook 9945 disabled) |

Live browser is **firefox-esr**.

### Primary daily apps (Layer B)

**gtk-term** (terminal), **gtk-files** (files), and **gtk-edit** (editor) are the Hyprland daily apps (binaries from `default/gtk-apps/`). foot / thunar / mousepad remain as package fallbacks.

### What this is *not*

- Not GNOME Shell — **no GNOME desktop apps** (keyring PAM only)
- Not full **nwg-shell** — partial nwg-* integration alongside Waybar/Fuzzel/Mako
- Not a fat live image — slim live; full workstation arrives via Calamares apt after unpack

Full package list: [`default/install-list`](default/install-list) (bare minimum) + optional [`personalize/install-list`](personalize.example/install-list). Sections map to:

| Section | Where it goes |
|---------|----------------|
| `live` | `live.list.chroot` — slim live ISO only (must include `live-boot*` / `live-config*`) |
| `installer` | `installer.list.chroot` — Calamares (removed after install) |
| `server` | `neuronix-server-packages.list` — apt on every disk install (bare default is empty; extras via personalize) |
| `desktop` | `neuronix-desktop-packages.list` — apt on Desktop profile only (session + settings tools) |

**What stays in `default/`:** live Hyprland chrome, SSH/NM keepers for Server, Desktop settings-hub tools + hyprpm plugin build deps, Calamares. **What goes in `personalize/`:** git/python/docker/dbs, media apps (VLC, GIMP, Blender, …), extra themes, etc.

Regenerate lists after editing either file:

```bash
./build.sh --lists-only
```

(A normal `./build.sh` regenerates them automatically before building.)

## Personalize overlay (`personalize/`)

Use this for **your** branding, extra packages, and private drop-ins without touching
the committed stock tree. The folder is **gitignored** and never pushed to the main repo.

### 1. Create your overlay

```bash
cp -a personalize.example personalize
```

That copies a sample `install-list` (full previous workstation extras) plus empty
`images/` / `metadata/` stubs and stub folders for `browser-extensions/`, `configs/`, `services/`, and `gtk-apps/`.

### 2. Add or trim packages

Edit `personalize/install-list` with the same format as `default/install-list`:

```text
# --- server ---
git # example
docker.io

# --- desktop ---
vlc
gimp
```

Rules:

- Sections: `live` / `server` / `desktop` / `installer`
- Packages are **appended** onto the base list (same name → base wins)
- Calamares **Desktop** vs **Server** chooser is unchanged — personalize only changes which packages those profiles install
- Omit sections you do not need

To build the **bare** ISO only, delete or empty `personalize/install-list` (or do not create `personalize/` at all).

### 3. Override branding (optional)

Drop files using the same layout as `default/`:

| Path under `personalize/` | Behavior |
|---------------------------|----------|
| `images/calamares/` | `image.png` (welcome pane), `user-login.png` or `user-icon.png` (sidebar above steps) |
| `images/live/` | `background.png` or `.jpg` — live wallpaper |
| `images/installed/` | wallpapers for the installed system |
| `images/grub/` | `grub-16x9.png`, `grub-4x3.png` |
| `images/icons/` | `menu-icon.png` or `.jpg` — greeter / Waybar avatar |
| `metadata/debian.env` | Sourced **after** `default/metadata/debian.env` (e.g. rename product / hostname) |
| `metadata/debian.distro.conf` | Replaces staged `/etc/neuronix/distro.conf` when present |
| `install/*.sh` | Calamares **Desktop** (root): after Chrome; same basename overrides `default/install/` |
| `hooks/*.sh` | First Hyprland login (user, once): overrides `default/hooks/`; see `neuronix-run-user-hooks.sh` |

Any path present under `personalize/` wins over `default/`.

### 4. Drop-ins (browser-extensions / configs / services)

Optional private trees staged by `share/merge-personalize-dropins.sh` during `setup.sh`.
**Contracts and layouts** are documented in [`personalize.example/README.md`](personalize.example/README.md).

```bash
cp -a /path/to/browser-extensions/. personalize/browser-extensions/
cp -a /path/to/configs/. personalize/configs/
cp -a /path/to/services/. personalize/services/
cp -n personalize.example/configs/links.json personalize/configs/links.json
```

| Path under `personalize/` | Contract |
|---------------------------|----------|
| `browser-extensions/<Name>/manifest.json` | Unpacked Chrome/Chromium extensions → staged + `neuronix-chrome` / `neuronix-chromium` + CRX/External Extensions registration when those browsers install |
| `configs/` + `links.json` | Merged to `~/configs`; home paths (`.config/hypr`, …) are **symlinks** into that folder |
| `services/<Name>/install.sh` | Copied to `/usr/local/lib/neuronix/services/<Name>/`; chroot hook runs each `install.sh` |

**GTK apps:** release binaries live in committed [`default/gtk-apps/`](default/gtk-apps/) (Neuronix core daily apps), including **`gtk-theme-editor`** and **`gtk-theme/`** data (the Rust theme crate is statically linked; the editor must be on `PATH` for Profile → Custom…). Put your settings under `personalize/configs/gtk-apps/` so they land in `~/.config/gtk-apps`. Drop **extra or replacement** binaries under `personalize/gtk-apps/` (same `bin/` + `applications/` layout — overlays the default suite). Refresh stock binaries into `default/gtk-apps/` (and extras into `personalize/gtk-apps/`) after rebuilding the GTK suite.

### 5. Build

```bash
./build.sh              # uses default/ + personalize/ if present
./build.sh --lists-only # regenerate package lists only
```

### Layout reminder

```text
default/                 # committed stock
  install-list
  images/
  metadata/
  gtk-apps/              # core GTK binaries (gtk-term / gtk-files / gtk-edit / …)
personalize/             # gitignored — your overrides
  install-list           # optional package extras
  images/                # optional branding
  metadata/              # optional identity overrides
  browser-extensions/    # optional Chrome extensions
  configs/               # optional managed home configs (+ crontab/)
  services/              # optional systemd services
```


## Hyprland app compatibility (4 layers)

The full install-list does **not** need per-app Hyprland rules. Compatibility is handled in four layers:

| Layer | Scope | What the ISO provides |
|-------|--------|------------------------|
| **A — No GUI** | servers, CLI, libs, Python, plugins, themes | Nothing — not desktop windows |
| **B — Session defaults** | GTK/Qt apps | One env block in `hyprland.conf` + `neuronix-hyprland-session-env.sh` |
| **C — Category wrappers** | audacity, blender, … | Shared `neuronix-x11-app` + desktop overrides |
| **D — Hardware / VM** | GPU-heavy apps | Document VirtualBox 3D accel; not fixable by config alone |

**Daily apps (Layer B):** **gtk-term** (`Super+Return`), **gtk-files** (`Super+E`), **gtk-edit** (`Super+G`).

### Layer B session env (applied once)

| Setting | Purpose |
|---------|---------|
| `start-hyprland` + `hyprland-guiutils` | Clean Hyprland startup |
| `GSK_RENDERER=cairo` | Stable GTK4 rendering on Hyprland |
| `GTK_THEME=Adwaita-dark` + dconf `color-scheme` | Dark theme without deprecated gtk-prefer-dark |
| `QT_QPA_PLATFORM=wayland;xcb` | Qt apps (VLC, Kdenlive, …) |
| `xdg-desktop-portal-hyprland` + portal restart | File dialogs, screenshots |
| `dbus-update-activation-environment` | Fuzzel-launched apps inherit env |
| PipeWire + `wireplumber` | Audio (Audacity, VLC, browsers) |

### Layer C wrappers

| App | Wrapper |
|-----|---------|
| **audacity** | `audacity.desktop` → `neuronix-x11-app audacity` (wxWidgets / XWayland) |
| **blender** | `blender.desktop` → `neuronix-x11-app blender` (GPU / XWayland) |
| **Settings** | `neuronix-settings` hub (nwg-displays, nm-connection-editor, nwg-look, xfce4-power-manager, …) |

Shared launcher: `/usr/local/bin/neuronix-x11-app` runs `GDK_BACKEND=x11` for apps that refuse native Wayland.

### Layer D — VM / GPU limits

| Situation | Affected apps | User action |
|-----------|---------------|-------------|
| VirtualBox without 3D acceleration | blender, kdenlive, gimp (slow) | Enable VBox 3D + Guest Additions |
| Corrupt Blender prefs (Vulkan) | blender | Reset `~/.config/blender` |
| wxWidgets on Wayland | audacity | Use menu entry **Audacity** (neuronix wrapper) or `neuronix-x11-app audacity` |

### GUI install-list apps → layer

| Layer | Apps |
|-------|------|
| **B** default | gtk-term, gtk-files, gtk-edit, gtk-calc, gtk-image, imv, zathura, xarchiver, gparted, synaptic, remmina, kicad, mpv, gimp, pavucontrol, deskflow, … |
| **C1** x11 | audacity |
| **C3** + **D** GPU | blender, kdenlive, openshot-qt, handbrake, vlc, smplayer |
| **native** | waybar, fuzzel, mako-notifier, nwg-displays, nwg-bar, nwg-clipman, blueman, kanshi |

Run [`validate-apps-hyprland.sh`](neuronix-iso/packages/validate-apps-hyprland.sh) before building to verify overlay files and layer categorization. Add `--smoke` on a Hyprland host to version-check representative apps.

---

## Build the ISO

The repo-root `./build.sh` is the single entry point. It regenerates the package
lists from `default/install-list`, runs the package preflight, then drives `live-build`:

```bash
./build.sh              # regenerate lists → validate → setup → lb build
./build.sh --clean      # same, but also wipe the apt .deb cache
./build.sh --lists-only # only regenerate package lists, then stop
```

Manual / step-by-step equivalent (rarely needed):

```bash
./build.sh --lists-only                    # sync derived lists from install-list
cd neuronix-iso/packages
./validate-manifest.sh                      # check package names
./validate-apps-hyprland.sh                 # Hyprland layer + overlay checks
cd ..
./setup.sh                                  # lb config + overlay/branding merge
./build.sh                                  # sudo lb build (in neuronix-iso/)
```

Build output defaults to `~/neuronix-build-iso` (override with `NEURONIX_BUILD_ROOT`).

**Build host:** `live-build`, **network** (debootstrap, backports), optional ImageMagick for avatar sizing.

**Calamares install path** (needs network on the target):

```text
unpackfs (slim live)
  → strip live autologin leftovers
  → apt-install server packages          # every profile
  → packages (remove live/calamares)
  → Desktop: apt-install desktop + backports Hyprland + Chrome (+ Cursor only if personalize/install)
  → displaymanager
  → Server: purge slim-live GUI + console/SSH
```

**Chrome:** Not on the live ISO (hook `.disabled`). Calamares Desktop installs Chrome from the network.
**Cursor:** Same helper on the ISO, but stock Desktop does **not** run it — only `personalize/install/cursor.sh`.

After editing branding under [`default/images/`](default/images/) (or `personalize/images/`), re-run:

```bash
cd neuronix-iso
./setup.sh
./build.sh
```

For pipeline detail, customization map, and live↔recipe sync surfaces, see [ISO build recipe — reference](#iso-build-recipe--reference).

---

## ISO build recipe — reference

### What this project is

**Neuronix** is a **Debian 13 (Trixie) live ISO** for a **Hyprland / Wayland** workstation. Design intent:

- **Slim live image** — Hyprland chrome, Firefox, net/BT, Calamares (not the full workstation)
- **Disk install via Calamares** (needs network):
  - **Desktop** (default) — apt-install server + desktop stacks, backports Hyprland/kernel, Chrome → LightDM autologin → `neuronix-hyprland` (Cursor: `personalize/install` only)
  - **Server** — apt-install server stack, purge live GUI + Hyprland runtime, clear desktop skel/gtk-apps → console + SSH

Tooling is **Debian `live-build` (`lb config` / `lb build`)**, not a hand-rolled `mkisofs` recipe. Output is an **iso-hybrid** (BIOS GRUB + UEFI GRUB).

Default build tree (outside the repo): `~/neuronix-build-iso` — holds a built `live-image-amd64.hybrid.iso` (~2.1 GB).

### Top-level layout

| Path | Role |
|------|------|
| `README.md` | Primary documentation |
| `default/` | Stock `install-list`, `images/`, `metadata/` (committed baseline) |
| `build.sh` | Top-level ISO builder; also regenerates package lists (`--lists-only`) |
| `personalize.example/` | Template for local `personalize/` (packages, branding, browser-extensions/configs/services/gtk-apps stubs) |
| `neuronix-iso/` | live-build profile: `setup.sh`, `build.sh`, `overlay/`, `packages/` |
| `share/` | Build-host merge scripts + Calamares merge tree |

---

### How the ISO is built (pipeline)

#### Entry points

```text
./build.sh                 # recommended (repo root)
  → regenerate package lists from default/install-list (+ personalize/install-list)
  → validate-manifest.sh                          (package preflight)
  → clean build root (keep apt .deb cache unless --clean)
  → neuronix-iso/setup.sh
  → neuronix-iso/build.sh → sudo lb build

# Or manually:
cd neuronix-iso && ./setup.sh && ./build.sh
```

Derived lists are rebuilt from the base `default/install-list` plus any append-only
`personalize/install-list`. Use `./build.sh --lists-only` to regenerate without
building. Branding prefers `personalize/` over `default/` for images and metadata when present.

#### Stage A — `setup.sh` (`neuronix-iso/setup.sh`)

Runs in `NEURONIX_BUILD_ROOT` (from `default/metadata/debian.env`):

1. Sources `default/metadata/debian.env` (+ optional `personalize/metadata/debian.env`)
2. **`lb config`**:
   - `--distribution trixie`
   - `--debootstrap-options "--variant=minbase"`
   - `--debian-installer none`
   - `--archive-areas "main contrib non-free non-free-firmware"`
   - `--binary-image iso-hybrid`
   - `--bootloaders "grub-pc grub-efi"`
   - `--bootappend-live "boot=live components username=live user-password=live hostname=neuronix-hyprland"`
3. Merges **overlay** into `$BUILD_ROOT/config/`:
   - `package-lists/*.list.chroot`
   - `bootloaders/`
   - `includes.chroot/`
   - `hooks/normal/*.hook.chroot` and `*.hook.binary` (`.disabled` hooks are **not** copied)
4. Stages branding/scripts:
   - GRUB via `share/merge-grub-branding.sh` (prefers `personalize/images/grub/`)
   - Calamares via `share/merge-calamares-neuronix.sh` (prefers `personalize/images/`)
   - Chrome/Cursor/APT target helpers from overlay `usr/share/neuronix/`
   - Installed wallpapers from `default/images/installed/` (+ `personalize/images/installed/`)
   - Menu icon / `.face` from `default/images/icons/` (png/jpg; personalize wins)
   - `default/metadata/debian.distro.conf` (or `personalize/metadata/…`) → `etc/neuronix/distro.conf`
5. Resets bootstrap state so next `lb build` re-runs debootstrap

#### Stage B — `build.sh` (`neuronix-iso/build.sh`)

Clears stale `.build/binary_*` markers, then:

```bash
cd "$BUILD_ROOT" && sudo lb build
```

`live-build` does: debootstrap → apt package lists → chroot hooks → squashfs → GRUB binary hooks → hybrid ISO.

**Artifact:** `$BUILD_ROOT/live-image-amd64.hybrid.iso`

#### Package flow (slim live vs install)

```text
install-list
  ├── live      → live.list.chroot      → baked into squashfs by live-build
  ├── installer → installer.list.chroot → Calamares on live; removed after install
  ├── server    → neuronix-server-packages.list  → Calamares apt (every profile)
  └── desktop   → neuronix-desktop-packages.list → Calamares apt (Desktop only)

Hook 997 (live): Hyprland + kernel from trixie-backports (not in .list.chroot)
Calamares Desktop: same backports + Chrome (Cursor only via personalize/install; live hooks 996/9945 disabled)
```

#### Calamares exec sequence (disk install)

From `share/calamares-neuronix/etc/calamares/settings.conf`:

`unpackfs` → strip live LightDM leftovers → apt server packages → `packages` (remove live/Calamares) → Desktop hooks (desktop pkgs + backports Hyprland + Chrome [+ personalize/install e.g. Cursor]) → `displaymanager` → Server profile purge → SSH prep → GRUB/bootloader/initramfs

---

### Where customizations live

#### Packages

| File | Purpose |
|------|---------|
| `default/install-list` | Source of truth (`live` / `server` / `desktop` / `installer`) |
| `neuronix-iso/overlay/package-lists/live.list.chroot` | Slim live apt list |
| `neuronix-iso/overlay/package-lists/installer.list.chroot` | Calamares on live |
| `share/calamares-neuronix/etc/calamares/neuronix-server-packages.list` | Post-unpack server |
| `share/calamares-neuronix/etc/calamares/neuronix-desktop-packages.list` | Post-unpack desktop (+ Hyprland/Chrome names; Cursor via personalize) |
| `share/calamares-neuronix/etc/calamares/neuronix-live-purge.list` | GUI pkgs purged on Server |

#### Chroot overlay (live filesystem)

Root: `neuronix-iso/overlay/includes.chroot/`

Notable areas:

- **Session:** `usr/share/neuronix/neuronix-hyprland-session*.sh`, `usr/share/wayland-sessions/neuronix-hyprland.desktop`
- **Skel desktop:** `etc/skel/.config/hypr/`, `waybar/`, `fuzzel/`, `mako/`, GTK, portals
- **LightDM:** `etc/lightdm/` (live autologin, Hyprland session, greeter)
- **Helpers:** `usr/local/bin/neuronix-*` (settings, launchers, X11 wrappers, Calamares live)
- **APT:** `etc/apt/sources.list.d/neuronix-backports.list`, `preferences.d/neuronix-backports-kernel`
- **SSH live:** `etc/ssh/`, systemd prep units
- **Desktop entries:** Audacity/Blender wrappers, Neuronix settings apps

#### Hooks (`overlay/hooks/normal/`)

| Hook | Role |
|------|------|
| `990` | Live SSH |
| `991` chmod | Fix +x on helper scripts |
| `991` binary / `992` chroot | GRUB branding |
| `993` | Enable bluetooth |
| `994` | `dconf update` |
| `9945` **`.disabled`** | Cursor on live |
| `995` | contrib/non-free |
| `996` **`.disabled`** | Chrome on live |
| `997` | **trixie-backports:** kernel ~7.0 + Hyprland stack |
| `999` | Icon cache + perms |
| `1000` | `x-www-browser` alternatives |

#### Bootloaders

`neuronix-iso/overlay/bootloaders/` — `grub-pc/`, `grub-efi/`, `isolinux/` themes/splash (refreshed by `share/merge-grub-branding.sh` from `images/grub/`).

#### Calamares / install-time

`share/calamares-neuronix/` — modules, branding, `usr/local/sbin/neuronix-*.sh` (apply profiles, strip desktop, NM perms, backports install).

Merged at setup by `share/merge-calamares-neuronix.sh`.

#### Target install scripts

`neuronix-iso/overlay/includes.chroot/usr/share/neuronix/` — runtime helpers copied into the live ISO and installed target, including `ensure-apt-contrib-nonfree.sh`, `install-google-chrome.sh`, and `install-cursor.sh`.

Build-host staging stays separate under `share/`: `merge-grub-branding.sh` and `merge-calamares-neuronix.sh`.

#### Branding images

`images/{calamares,live,installed,grub,icons}/`

**Note:** README/setup often expect `.png`; the tree currently has many `.jpg` assets. Live wallpaper copy in `setup.sh` only looks for `images/live/background.png`, while installed backgrounds accept png/jpg. Session scripts already fall back across `.jpg`/`.png`.

#### Metadata

| File | Use |
|------|-----|
| `default/metadata/debian.env` | Build vars (`LB_*`, product, profile, build root) |
| `default/metadata/debian.distro.conf` | Staged to `/etc/neuronix/distro.conf` on the ISO |

#### Validation helpers

`neuronix-iso/packages/` — `manifest-lib.sh`, `validate-manifest.sh`, `validate-apps-hyprland.sh`, `test-desktop-apps-hyprland.sh`.

---

### Building / rebuilding

Day-to-day commands are in [Build the ISO](#build-the-iso). Practical rebuild checklist:

```bash
# After package edits:
./build.sh --lists-only
cd neuronix-iso/packages && ./validate-manifest.sh && ./validate-apps-hyprland.sh

# Full ISO:
./build.sh            # preserve apt cache
./build.sh --clean    # wipe cache too
```

After branding PNG/JPG edits: re-run `neuronix-iso/setup.sh` then `build.sh` (or top-level `./build.sh`).

Override output dir: `NEURONIX_BUILD_ROOT=...`

---

### Key files that must stay in sync for live-system changes

#### Package changes (highest leverage)

1. Edit **`default/install-list`** (or append via `personalize/install-list`)
2. Run **`./build.sh --lists-only`** (or any `./build.sh`) so these stay aligned:
   - `neuronix-iso/overlay/package-lists/live.list.chroot`
   - `neuronix-iso/overlay/package-lists/installer.list.chroot`
   - `share/calamares-neuronix/etc/calamares/neuronix-{server,desktop,live-purge}.list`
3. If Hyprland/kernel/Chrome/Cursor change, also keep in sync:
   - Hook **`997-neuronix-backports.hook.chroot`**
   - **`neuronix-install-hyprland-backports.sh`**
   - **`contextualprocess_neuronix_desktop.conf`** + `neuronix-apply-desktop-profile.sh` skip list
   - Live hooks **996/9945** (enabled vs Desktop-only)
4. Run **`validate-manifest.sh`** before build (live lists must resolve in **base** suite, not only backports)

#### Live desktop / session behavior

Keep these consistent together:

- `etc/skel/.config/hypr/hyprland.conf` ↔ `neuronix-hyprland-session-start.sh` ↔ `neuronix-hyprland-session-env.sh` ↔ `neuronix-hyprland.desktop`
- LightDM drop-ins ↔ `NEURONIX_DESKTOP_SESSION=neuronix-hyprland` in metadata
- Waybar/Fuzzel/Mako skel configs ↔ packages in `live` section
- `neuronix-settings` / keybinds in `hyprland.conf` ↔ tools actually in live or desktop lists
- Layer C wrappers: `audacity.desktop` / `blender.desktop` ↔ `neuronix-x11-app`

#### Install vs live divergence

- Live-only: `50-neuronix-live-autologin.conf`, Calamares autostart — stripped by `neuronix-strip-desktop.sh`
- Server purge: `neuronix-live-purge.list` + `neuronix-apply-server-profile.sh` (Hyprland runtime + desktop skel/gtk-apps)
- Calamares `packages.conf` remove list ↔ installer packages in `install-list`

#### Branding

- Edit **`default/images/`** or **`personalize/images/`**, then **`setup.sh`**
- GRUB: `images/grub/` ↔ `share/merge-grub-branding.sh` ↔ overlay bootloaders ↔ hooks 991/992
- Live wallpaper path: `setup.sh` resolves `live/background` as png/jpg/webp (personalize preferred) and stages `background.png`
- Greeter background path in `lightdm-gtk-greeter.conf` vs files under `usr/share/backgrounds/neuronix-installed/`

#### Profile / product identity

- `default/metadata/debian.env` ↔ `debian.distro.conf` ↔ Calamares branding / hostname / session names (+ personalize overlay)

#### Permissions

`setup.sh` and hooks **991/999** re-apply `+x` on `neuronix-*` scripts — if you add new helpers under `usr/local/bin` or `usr/share/neuronix`, ensure those chmod paths cover them.

---

### Pipeline diagram

```text
┌─────────────────┐
│ default/install-list │  ← base packages
└────────┬────────┘
         │ build.sh (package-list stage)
         ▼
┌────────────────────────────────────────────┐
│ live/installer .list.chroot                │
│ Calamares server/desktop/purge lists       │
└────────┬───────────────────────────────────┘
         │
┌────────▼────────┐     ┌──────────────────────┐
│ neuronix-iso/      │     │ share/ + images/     │
│ overlay/        │────▶│ merged by setup.sh   │
└────────┬────────┘     └──────────────────────┘
         │
         ▼
   lb config (trixie, iso-hybrid, GRUB)
         │
         ▼
   lb build → debootstrap → apt → hooks (esp. 997)
         │
         ▼
   squashfs + hybrid ISO
   (~/neuronix-build-iso/live-image-amd64.hybrid.iso)
         │
         ▼ (on target, Calamares)
   unpack slim live → apt server/desktop → Desktop or Server profile
```

**Bottom line:** Slim live-build ISO + Calamares Desktop/Server. Stock bare minimum lives in **`default/`** (including **`default/gtk-apps/`**); put extras, branding, and private drop-ins (`browser-extensions/`, `configs/`, `services/`, `gtk-apps/`) in gitignored **`personalize/`** (see `personalize.example/`). Other sync surfaces: **`neuronix-iso/overlay/`**, **`share/calamares-neuronix/`**.

---

## Project layout

| Path | Purpose |
|------|---------|
| `default/install-list` | Bare-minimum packages so live / Desktop / Server can run |
| `default/images/`, `default/metadata/` | Stock branding and build/runtime identity |
| `personalize.example/` | Template for gitignored `personalize/` (packages, branding, drop-ins) |
| `default/gtk-apps/` | Core GTK daily-app binaries staged into the ISO |
| `default/services/` | Stock services (e.g. gtksync Waybar); personalize/services overlays |
| `personalize/gtk-apps/` | Optional extra/override GTK binaries (same layout) |
| `default/configs/crontab/crontab.conf` | Stock blank user crontab (comments only) |
| `personalize/configs/crontab/crontab.conf` | Optional override installed for the default user |
| `build.sh` | Build the ISO; regenerates slim `live`/`installer` lists + Calamares server/desktop/live-purge lists (`--lists-only` to stop after) |
| `neuronix-iso/packages/manifest-lib.sh` | Shared parser for install-list |
| `neuronix-iso/packages/validate-manifest.sh` | Apt check for live lists + Calamares server/desktop coverage |
| `neuronix-iso/packages/validate-apps-hyprland.sh` | Hyprland compatibility layers + overlay checks |
| `neuronix-iso/overlay/package-lists/` | Slim live-build lists (`live.list.chroot`, `installer.list.chroot`) |
| `neuronix-iso/overlay/includes.chroot/usr/share/neuronix/` | Runtime session, APT, Chrome, and Cursor helpers shipped on the ISO |
| `share/calamares-neuronix/` | Installer modules, branding, apt package lists |
| `share/merge-grub-branding.sh` | Stages GRUB/isolinux artwork into the overlay and live-build tree |
| `share/merge-calamares-neuronix.sh` | Stages Calamares configuration and branding into the live-build tree |
| `share/merge-personalize-dropins.sh` | Stages personalize browser-extensions / configs / services into includes.chroot |

---

## Metadata (`default/metadata/`)

Canonical Debian-specific values under `default/metadata/` (Hyprland desktop).

`neuronix-iso/setup.sh` and `build.sh` source `default/metadata/debian.env` (then optional `personalize/metadata/debian.env`). `setup.sh` also stages `debian.distro.conf` to `/etc/neuronix/distro.conf` on the ISO.

### Files

| File | Profile | Used by |
|------|---------|---------|
| `debian.env` | Debian trixie | `neuronix-iso/setup.sh`, `neuronix-iso/build.sh` |
| `debian.distro.conf` | Debian | Staged to `/etc/neuronix/distro.conf` on ISO |

### Key reference

| Key | Value | Consumer |
|-----|-------|----------|
| `NEURONIX_PROFILE_ID` | `debian` | `setup.sh` |
| `NEURONIX_DISTRO` | `debian` | `/etc/neuronix/distro.conf` |
| `NEURONIX_SUITE` | `trixie` | `/etc/neuronix/distro.conf`, `lb config` |
| `NEURONIX_PRODUCT_NAME` | `Neuronix` | `/etc/neuronix/distro.conf`, Calamares branding |
| `NEURONIX_LIVE_HOSTNAME` | `neuronix-hyprland` | `lb --bootappend-live`, `/etc/neuronix/distro.conf` |
| `NEURONIX_BUILD_ROOT_VAR` | `NEURONIX_BUILD_ROOT` | `setup.sh`, `build.sh` |
| `LB_DISTRIBUTION` | `trixie` | `lb config` |
| `LB_ARCHIVE_AREAS` | contrib/non-free/non-free-firmware | `lb config` |
| `NEURONIX_DESKTOP_SESSION` | `neuronix-hyprland` | LightDM autologin |
| `NEURONIX_CALAMARES_INSTALLER` | `calamares-install-debian` | live session |
| `NEURONIX_ENABLE_BACKPORTS` | `1` | hook 997, Calamares Desktop profile hooks |
| `NEURONIX_FLATPAK_DECIBELS` | `0` | disabled (not in install-list) |

### Build-time environment (not in debian.env)

| Variable | Purpose |
|----------|---------|
| `NEURONIX_BUILD_ROOT` | Override live-build output directory |

### Still profile-specific (not in metadata)

- Package lists under `neuronix-iso/overlay/package-lists/`
- Hyprland session scripts under `overlay/includes.chroot/`
- Hooks `991`–`1000`
- Calamares modules under `share/calamares-neuronix/`

---

## Images (`default/images/`)

Edit stock branding under `default/images/`, or override via `personalize/images/`, then rebuild with `neuronix-iso/setup.sh` and `build.sh`.

The current tree ships mostly `.jpg` assets (except `grub/` and `calamares/image.png`, which are `.png`). Filenames below show the current on-disk extension.

### calamares/

| File | Used for |
|------|----------|
| `user-login.png` | Calamares sidebar logo + window icon (`user-icon.png` also accepted) |
| `image.png` | Calamares welcome screen + slideshow hero |

### live/

| File | Used for |
|------|----------|
| `background.jpg` | Live ISO desktop wallpaper |

**Caveat:** `setup.sh` resolves `default/images/live/background` (and `personalize/images/live/background`) with png/jpg/webp fallbacks and stages it as `background.png` for the live skel.

### installed/

| File | Used for |
|------|----------|
| `background.jpg` | Default installed wallpaper + LightDM greeter background |
| `background2.jpg` … `backgroundN.jpg` | Extra wallpapers (`neuronix-change-background`) |

All PNG/JPG files in this folder are copied to `/usr/share/backgrounds/neuronix-installed/` at build time.

Recommended size: ~16:9 (e.g. 2752×1536).

### grub/

| File | Used for |
|------|----------|
| `grub-16x9.png` | Live USB GRUB menu + installed system GRUB background |
| `grub-4x3.png` | 4:3 displays / isolinux fallback (optional but recommended) |

Recommended size: 1024×640 and 1024×768.

### icons/

| File | Used for |
|------|----------|
| `menu-icon.jpg` | Waybar menu button, LightDM greeter avatar, new user `.face` icons |

Do not add extra icons here — only this file is copied by the build scripts. `setup.sh` accepts `menu-icon.png` or `.jpg` (and prefers `personalize/images/icons/`).

---

## Build hooks

| Hook | Purpose |
|------|---------|
| 990 | SSH on live |
| 991–992 | GRUB branding |
| 993 | Bluetooth |
| 994 | dconf compile |
| 9945 | Cursor on live — **disabled**; stock Desktop also skips Cursor (`personalize/install`) |
| 995 | APT contrib/non-free |
| 996 | Google Chrome — **disabled** on slim live (Calamares Desktop only) |
| 997 | trixie-backports: kernel ~7.0.x + Hyprland stack |
| 999 | Papirus yellow folders + icon cache + script permissions |
| 1000 | x-www-browser alternative (Chrome if present) |

## Verification checklist

1. `./build.sh --lists-only` then `packages/validate-manifest.sh` and `packages/validate-apps-hyprland.sh` pass.
2. `./setup.sh && ./build.sh` completes without errors.
3. Boot live ISO → slim Hyprland + Waybar + Firefox; Calamares opens (no Chrome/Cursor on live).
4. **Desktop** install (with network) → reboot → autologin lands in Hyprland; Chrome present (Cursor only if `personalize/install/cursor.sh`).
5. **Server** install (with network) → reboot → console + SSH; live GUI purged.
6. `uname -r` shows **7.0.x**; `apt-cache policy linux-image-amd64` shows `trixie-backports` `~bpo13+1`.
7. Desktop: `hyprland`, `waybar`, `fuzzel`, `mako`, `nwg-displays`, `nwg-look`, `gtk-term`, `gtk-files`, `gtk-edit`, `google-chrome-stable`, SSH.
8. **Super+Return** opens gtk-term; **Super+E** opens gtk-files; **Super+G** opens gtk-edit; **Super+,** opens `neuronix-settings`.
9. Audacity and Blender launch from menu (XWayland wrappers).
10. Optional: `cursor --version`, `mariadb --version`, `docker --version`.
