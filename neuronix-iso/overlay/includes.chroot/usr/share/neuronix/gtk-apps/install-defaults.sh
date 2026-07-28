#!/usr/bin/env bash
# Install / refresh Neuronix GTK-Apps as MIME + terminal defaults.
# ISO skel already ships mimeapps.list / xdg-terminals.list; re-run this on a
# live or installed system to re-apply after personalize overrides.
#
# Manual:
#   /usr/share/neuronix/gtk-apps/install-defaults.sh
#   # or from the build tree during development:
#   ./default/gtk-apps/applications/install-defaults.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}"
LOCAL_BIN="${HOME}/.local/bin"

DESKTOPS=(
	gtk-edit.desktop
	gtk-image.desktop
	gtk-files.desktop
	gtk-term.desktop
	gtk-calc.desktop
	gtk-colors.desktop
)

# Prefer system desktops staged by the ISO; fall back to this directory.
_desk_src() {
	local name="$1"
	if [[ -f "/usr/share/applications/$name" ]]; then
		printf '%s\n' "/usr/share/applications/$name"
	elif [[ -f "$SCRIPT_DIR/$name" ]]; then
		printf '%s\n' "$SCRIPT_DIR/$name"
	else
		return 1
	fi
}

LAUNCHER="$(command -v gtk-term-launch.sh 2>/dev/null || true)"
if [[ -z "$LAUNCHER" ]]; then
	for cand in /usr/local/bin/gtk-term-launch.sh "$SCRIPT_DIR/gtk-term-launch.sh"; do
		[[ -x "$cand" ]] && LAUNCHER="$cand" && break
	done
fi

mkdir -p "$APP_DIR" "$CONFIG_DIR" "$LOCAL_BIN"

echo "Installing desktop launchers to $APP_DIR ..."
for desk in "${DESKTOPS[@]}"; do
	src="$(_desk_src "$desk" || true)"
	if [[ -z "$src" ]]; then
		echo "  skip missing: $desk" >&2
		continue
	fi
	cp -a "$src" "$APP_DIR/$desk"
	echo "  $desk"
done

if command -v update-desktop-database >/dev/null 2>&1; then
	update-desktop-database "$APP_DIR" 2>/dev/null || true
fi

echo "Setting MIME defaults ..."

for mime in \
	text/plain \
	text/markdown \
	text/x-markdown \
	text/css \
	text/xml \
	text/x-csrc \
	text/x-c++src \
	text/x-python \
	text/x-shellscript \
	text/x-makefile \
	text/x-java \
	text/x-rust \
	text/javascript \
	application/javascript \
	application/json \
	application/xml \
	application/x-desktop \
	application/x-zerosize \
	inode/x-empty \
	text/x-log \
	text/x-patch \
	text/x-diff
do
	xdg-mime default gtk-edit.desktop "$mime" 2>/dev/null || true
done

for mime in \
	image/png \
	image/jpeg \
	image/gif \
	image/webp \
	image/bmp \
	image/tiff \
	image/svg+xml \
	image/x-icon \
	image/vnd.microsoft.icon \
	image/x-xpixmap \
	image/x-portable-anymap \
	image/x-portable-bitmap \
	image/x-portable-graymap \
	image/x-portable-pixmap
do
	xdg-mime default gtk-image.desktop "$mime" 2>/dev/null || true
done

xdg-mime default gtk-files.desktop inode/directory 2>/dev/null || true
xdg-mime default gtk-files.desktop inode/mount-point 2>/dev/null || true
xdg-mime default gtk-files.desktop x-directory/normal 2>/dev/null || true
xdg-mime default gtk-files.desktop application/x-directory 2>/dev/null || true

printf '%s\n' 'gtk-term.desktop' >"$CONFIG_DIR/xdg-terminals.list"
printf '%s\n' 'gtk-term.desktop' >"$CONFIG_DIR/gnome-xdg-terminals.list"

if [[ -n "${LAUNCHER:-}" && -x "$LAUNCHER" ]]; then
	ln -sfn "$LAUNCHER" "$LOCAL_BIN/x-terminal-emulator"
	ln -sfn "$LAUNCHER" "$LOCAL_BIN/gtk-term-launch"
	echo "  user PATH: $LOCAL_BIN/x-terminal-emulator → $LAUNCHER"

	if command -v gsettings >/dev/null 2>&1; then
		gsettings set org.gnome.desktop.default-applications.terminal exec \
			"$LAUNCHER" 2>/dev/null || true
		gsettings set org.gnome.desktop.default-applications.terminal exec-arg '' \
			2>/dev/null || true
	fi

	if [[ "$(id -u)" -eq 0 ]] && command -v update-alternatives >/dev/null 2>&1; then
		update-alternatives --install /usr/bin/x-terminal-emulator x-terminal-emulator \
			"$LAUNCHER" 100 2>/dev/null || true
		update-alternatives --set x-terminal-emulator "$LAUNCHER" 2>/dev/null || true
		echo "  system   : update-alternatives x-terminal-emulator → $LAUNCHER"
	elif command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
		sudo update-alternatives --install /usr/bin/x-terminal-emulator x-terminal-emulator \
			"$LAUNCHER" 100 2>/dev/null || true
		sudo update-alternatives --set x-terminal-emulator "$LAUNCHER" 2>/dev/null || true
		echo "  system   : update-alternatives x-terminal-emulator → $LAUNCHER (via sudo)"
	fi
else
	echo "  warning: gtk-term-launch.sh not found; terminal defaults incomplete" >&2
fi

echo ""
echo "Installed GTK-Apps as defaults:"
echo "  Text editor : gtk-edit.desktop"
echo "  Image viewer: gtk-image.desktop"
echo "  File manager: gtk-files.desktop"
echo "  Terminal    : gtk-term.desktop / gtk-term-launch.sh"
echo "  Calculator  : gtk-calc.desktop (launcher only)"
echo "  Colors      : gtk-colors.desktop (launcher only)"
echo ""
echo "Verify:"
echo "  xdg-mime query default text/plain"
echo "  xdg-mime query default image/png"
echo "  xdg-mime query default inode/directory"
echo "  cat ~/.config/xdg-terminals.list"
echo "  readlink -f \"\$(command -v x-terminal-emulator)\""
echo "  gsettings get org.gnome.desktop.default-applications.terminal exec"
