#!/usr/bin/env bash
# Debian live-build: Neuronix Hyprland live ISO profile.
# Run from Build/neuronix-iso/. Overlay is merged into NEURONIX_BUILD_ROOT.
# Branding: default/images/ + optional personalize/images/ (prefer personalize).

set -euo pipefail
SCRIPT_ROOT="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_ROOT/.." && pwd)"
METADATA_DEFAULT="$REPO_ROOT/default/metadata"
PERSONALIZE="$REPO_ROOT/personalize"
IMAGES_DEFAULT="$REPO_ROOT/default/images"
IMAGES_PERSONALIZE="$PERSONALIZE/images"

# shellcheck source=/dev/null
source "$REPO_ROOT/share/neuronix-personalize.sh"
# shellcheck source=/dev/null
source "$METADATA_DEFAULT/debian.env"
if [[ -r "$PERSONALIZE/metadata/debian.env" ]]; then
  # shellcheck source=/dev/null
  source "$PERSONALIZE/metadata/debian.env"
fi

_build_var="${NEURONIX_BUILD_ROOT_VAR}"
BUILD_ROOT="${!_build_var:-$NEURONIX_BUILD_ROOT_DEFAULT}"
OVERLAY="$SCRIPT_ROOT/overlay"
DESIGN_SHARE="$OVERLAY/includes.chroot/etc/skel/.local/share/neuronix"

mkdir -p "$BUILD_ROOT"

_live_bg="$(neuronix_resolve_image "$IMAGES_DEFAULT" "$IMAGES_PERSONALIZE" "live/background" || true)"
if [[ -n "${_live_bg:-}" ]]; then
  mkdir -p "$DESIGN_SHARE"
  # Always stage as background.png for skel/session consumers.
  if command -v convert >/dev/null 2>&1 && [[ "${_live_bg##*.}" != "png" ]]; then
    convert "$_live_bg" PNG:"$DESIGN_SHARE/background.png"
  else
    cp -a "$_live_bg" "$DESIGN_SHARE/background.png"
  fi
fi
cd "$BUILD_ROOT"

if ! command -v lb >/dev/null 2>&1; then
  echo "lb (live-build) not found. Install: sudo apt install live-build live-boot-doc" >&2
  exit 1
fi

# Groups: Hyprland needs input/render/video; LightDM autologin expects "autologin".
# Without these the compositor fails and LightDM falls back to the greeter.
_live_groups="audio,cdrom,dip,floppy,video,plugdev,netdev,scanner,bluetooth,sudo,autologin,input,render"
_bootappend="boot=live components username=live user-default-groups=${_live_groups}"
if [[ -n "${LB_LIVE_USER_PASSWORD:-}" ]]; then
  _bootappend="${_bootappend} user-password=${LB_LIVE_USER_PASSWORD}"
fi
_bootappend="${_bootappend} hostname=${NEURONIX_LIVE_HOSTNAME}"
lb config \
  --distribution "$LB_DISTRIBUTION" \
  --debootstrap-options "--variant=minbase" \
  --debian-installer none \
  --archive-areas "$LB_ARCHIVE_AREAS" \
  --binary-image iso-hybrid \
  --bootloaders "grub-pc grub-efi" \
  --bootappend-live "$_bootappend"

MERGE_GRUB="$REPO_ROOT/share/merge-grub-branding.sh"
if [[ -x "$MERGE_GRUB" ]]; then
  "$MERGE_GRUB"
else
  echo "WARNING: missing $MERGE_GRUB — live ISO may show ${NEURONIX_GRUB_FALLBACK_MSG}." >&2
fi

mkdir -p config/package-lists config/includes.chroot \
  config/hooks/normal config/bootloaders
shopt -s nullglob
for f in "$OVERLAY"/package-lists/*.list.chroot; do
  cp -a "$f" config/package-lists/
done
if [[ -d "$OVERLAY/bootloaders" ]]; then
  cp -a "$OVERLAY/bootloaders/." config/bootloaders/
fi

if [[ -d "$OVERLAY/includes.chroot" ]]; then
  cp -a "$OVERLAY/includes.chroot/." config/includes.chroot/
fi

# Dropbox / sync often strips +x — force script modes into the live-build tree.
while IFS= read -r -d '' _script; do
  chmod 0755 "$_script"
done < <(find "$BUILD_ROOT/config/includes.chroot/usr/local/bin" \
  "$BUILD_ROOT/config/includes.chroot/usr/local/sbin" \
  "$BUILD_ROOT/config/includes.chroot/usr/local/libexec" \
  "$BUILD_ROOT/config/includes.chroot/usr/share/neuronix" \
  -type f \( -name 'neuronix-*' -o -name 'gparted' -o -name 'synaptic' -o -name 'synaptic-pkexec' \) -print0 2>/dev/null)

while IFS= read -r -d '' _sh; do
  chmod 0755 "$_sh"
done < <(find "$BUILD_ROOT/config/includes.chroot/usr/share/neuronix" \
  -type f -name '*.sh' -print0 2>/dev/null)

_distro_conf="$(neuronix_resolve_file "$METADATA_DEFAULT" "$PERSONALIZE/metadata" "${NEURONIX_DISTRO_CONF}" || true)"
if [[ -n "${_distro_conf:-}" ]]; then
  mkdir -p "$BUILD_ROOT/config/includes.chroot/etc/neuronix"
  cp -a "$_distro_conf" \
    "$BUILD_ROOT/config/includes.chroot/etc/neuronix/distro.conf"
fi

INST_BG_DEST="$BUILD_ROOT/config/includes.chroot/usr/share/backgrounds/neuronix-installed"
mkdir -p "$INST_BG_DEST"
# Defaults first, then personalize overwrites same basenames.
for _dir in "$IMAGES_DEFAULT/installed" "$IMAGES_PERSONALIZE/installed"; do
  [[ -d "$_dir" ]] || continue
  shopt -s nullglob
  for _bg in "$_dir"/*.png "$_dir"/*.jpg "$_dir"/*.jpeg "$_dir"/*.webp; do
    [[ -f "$_bg" ]] || continue
    cp -a "$_bg" "$INST_BG_DEST/"
  done
done
# Ensure a canonical background.png exists for skel hyprpaper.conf / live fallback.
if [[ ! -f "$INST_BG_DEST/background.png" ]]; then
  if [[ -n "${_live_bg:-}" && -f "${_live_bg}" ]]; then
    if command -v convert >/dev/null 2>&1 && [[ "${_live_bg##*.}" != "png" ]]; then
      convert "$_live_bg" PNG:"$INST_BG_DEST/background.png"
    else
      cp -a "$_live_bg" "$INST_BG_DEST/background.png"
    fi
  else
    _any="$(find "$INST_BG_DEST" -type f \( -name '*.png' -o -name '*.jpg' \) | head -1 || true)"
    if [[ -n "${_any:-}" ]]; then
      cp -a "$_any" "$INST_BG_DEST/background.png"
    fi
  fi
fi
# Also mirror live wallpaper into the picker folder when distinct.
if [[ -n "${_live_bg:-}" && -f "$DESIGN_SHARE/background.png" ]]; then
  cp -a "$DESIGN_SHARE/background.png" "$INST_BG_DEST/live-background.png"
fi

NEURONIX_PIX="$BUILD_ROOT/config/includes.chroot/usr/share/pixmaps"
_menu_icon="$(neuronix_resolve_image "$IMAGES_DEFAULT" "$IMAGES_PERSONALIZE" "icons/menu-icon" || true)"
if [[ -n "${_menu_icon:-}" ]]; then
  mkdir -p "$NEURONIX_PIX"
  if command -v convert >/dev/null 2>&1; then
    convert "$_menu_icon" PNG:"$NEURONIX_PIX/menu-icon.png"
  else
    cp -a "$_menu_icon" "$NEURONIX_PIX/menu-icon.png"
  fi
  SKEL="$BUILD_ROOT/config/includes.chroot/etc/skel"
  mkdir -p "$SKEL"
  if command -v convert >/dev/null 2>&1; then
    convert "$_menu_icon" -resize '512x512^' -gravity center -extent 512x512 PNG:"$SKEL/.face"
    convert "$_menu_icon" -resize '96x96^' -gravity center -extent 96x96 PNG:"$SKEL/.face.icon"
  else
    echo "warning: ImageMagick convert not found; install imagemagick on the build host for sized .face / .face.icon (using full-size copies)." >&2
    cp -a "$_menu_icon" "$SKEL/.face"
    cp -a "$_menu_icon" "$SKEL/.face.icon"
  fi
  chmod 0644 "$SKEL/.face" "$SKEL/.face.icon"
fi
if [[ -x "$MERGE_GRUB" ]]; then
  "$MERGE_GRUB" "$BUILD_ROOT/config"
fi

_merge="$REPO_ROOT/share/merge-calamares-neuronix.sh"
if [[ -f "$_merge" ]]; then
  chmod +x "$_merge"
  "$_merge" "$BUILD_ROOT/config/includes.chroot" "$IMAGES_DEFAULT" "$IMAGES_PERSONALIZE"
fi

# Core GTK apps from default/gtk-apps → /usr/local/lib/neuronix/gtk-apps + bin + desktops
_gtk_apps="$REPO_ROOT/default/gtk-apps"
if [[ -d "$_gtk_apps/bin" ]]; then
  _gtk_lib="$BUILD_ROOT/config/includes.chroot/usr/local/lib/neuronix/gtk-apps"
  _gtk_bin="$BUILD_ROOT/config/includes.chroot/usr/local/bin"
  _gtk_desk="$BUILD_ROOT/config/includes.chroot/usr/share/applications"
  mkdir -p "$_gtk_lib" "$_gtk_bin" "$_gtk_desk"
  shopt -s nullglob
  for _bin in "$_gtk_apps"/bin/*; do
    [[ -f "$_bin" ]] || continue
    _name="$(basename "$_bin")"
    cp -a "$_bin" "$_gtk_lib/$_name"
    chmod 0755 "$_gtk_lib/$_name"
    ln -sfn "../lib/neuronix/gtk-apps/$_name" "$_gtk_bin/$_name"
  done
  for _desk in "$_gtk_apps"/applications/*.desktop; do
    [[ -f "$_desk" ]] || continue
    cp -a "$_desk" "$_gtk_desk/"
  done
  # Multi-file app payloads (e.g. gtk-colors): apps/<name>/ → lib/apps/<name>/
  if [[ -d "$_gtk_apps/apps" ]]; then
    mkdir -p "$_gtk_lib/apps"
    for _appdir in "$_gtk_apps"/apps/*/; do
      [[ -d "$_appdir" ]] || continue
      _appname="$(basename "$_appdir")"
      [[ "$_appname" == .* ]] && continue
      rm -rf "$_gtk_lib/apps/$_appname"
      cp -a "$_appdir" "$_gtk_lib/apps/$_appname"
    done
  fi
  # Terminal compatibility launcher + MIME re-apply helper
  if [[ -f "$_gtk_apps/applications/gtk-term-launch.sh" ]]; then
    install -m 0755 "$_gtk_apps/applications/gtk-term-launch.sh" \
      "$BUILD_ROOT/config/includes.chroot/usr/local/bin/gtk-term-launch.sh"
  fi
  if [[ -f "$_gtk_apps/applications/install-defaults.sh" ]]; then
    mkdir -p "$BUILD_ROOT/config/includes.chroot/usr/share/neuronix/gtk-apps"
    install -m 0755 "$_gtk_apps/applications/install-defaults.sh" \
      "$BUILD_ROOT/config/includes.chroot/usr/share/neuronix/gtk-apps/install-defaults.sh"
  fi
  # User-local x-terminal-emulator early on PATH (skel)
  _skel_local_bin="$BUILD_ROOT/config/includes.chroot/etc/skel/.local/bin"
  mkdir -p "$_skel_local_bin"
  ln -sfn /usr/local/bin/gtk-term-launch.sh "$_skel_local_bin/x-terminal-emulator"
  shopt -u nullglob

  # Shared gtk-theme data (profiles.json + python); editor is on PATH via bin/ above
  if [[ -d "$_gtk_apps/gtk-theme" ]]; then
    _theme_share="$BUILD_ROOT/config/includes.chroot/usr/share/neuronix/gtk-theme"
    mkdir -p "$_theme_share"
    cp -a "$_gtk_apps/gtk-theme/." "$_theme_share/"
  fi

  # Stock gtk-apps theme.toml lives in default/configs/gtk-apps/ (→ ~/configs via merge).
  # Do not write ~/.config/gtk-apps here; merge-personalize-dropins creates the symlink.
  echo "Staged default/gtk-apps (suite + gtk-theme-editor + gtk-theme data + MIME defaults) into includes.chroot"
fi

# crontab.conf: personalize/configs/crontab wins over default/configs/crontab → /usr/share/neuronix/crontab.conf
_crontab="$(neuronix_resolve_file "$REPO_ROOT/default/configs/crontab" "$PERSONALIZE/configs/crontab" "crontab.conf" || true)"
if [[ -n "${_crontab:-}" ]]; then
  mkdir -p "$BUILD_ROOT/config/includes.chroot/usr/share/neuronix"
  cp -a "$_crontab" "$BUILD_ROOT/config/includes.chroot/usr/share/neuronix/crontab.conf"
  echo "Staged crontab.conf → usr/share/neuronix/crontab.conf"
fi

# Personalize drop-ins: browser-extensions / configs / services / gtk-apps
_merge_dropins="$REPO_ROOT/share/merge-personalize-dropins.sh"
if [[ -x "$_merge_dropins" || -f "$_merge_dropins" ]]; then
  chmod +x "$_merge_dropins"
  "$_merge_dropins" "$BUILD_ROOT/config/includes.chroot" "$PERSONALIZE"
fi

for f in "$OVERLAY"/hooks/normal/*.hook.chroot "$OVERLAY"/hooks/normal/*.hook.binary; do
  [[ -f "$f" ]] || continue
  cp -a "$f" config/hooks/normal/
  chmod +x "config/hooks/normal/$(basename "$f")"
done

# Hooks emitted by merge-personalize-dropins into config/hooks/normal — ensure +x
shopt -s nullglob
for _h in "$BUILD_ROOT"/config/hooks/normal/9925-neuronix-personalize-ssh.hook.chroot \
	"$BUILD_ROOT"/config/hooks/normal/9930-neuronix-personalize-services.hook.chroot \
	"$BUILD_ROOT"/config/hooks/normal/9931-neuronix-web-servers.hook.chroot; do
  [[ -f "$_h" ]] && chmod +x "$_h"
done
shopt -u nullglob

echo "Resetting bootstrap state (next lb build will rerun debootstrap)..."
for _p in chroot "cache/bootstrap" "cache/packages.bootstrap"; do
  if [[ -e "$_p" ]]; then
    rm -rf "$_p" 2>/dev/null || sudo rm -rf "$_p"
  fi
done
for _f in .build/bootstrap .build/bootstrap_cache.restore .build/bootstrap_cache.save; do
  if [[ -e "$_f" ]]; then
    rm -f "$_f" 2>/dev/null || sudo rm -f "$_f"
  fi
done

echo "Configured: overlay merged into $BUILD_ROOT/config"
echo "Artifacts (binary/, iso) go to: $BUILD_ROOT"
echo "From here: cd $SCRIPT_ROOT && ./build.sh"
