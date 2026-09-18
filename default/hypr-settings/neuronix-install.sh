#!/usr/bin/env bash
# System-wide hypr-settings install for Neuronix (local or ISO overlay/chroot).
#
# Usage:
#   sudo ./neuronix-install.sh
#   sudo DESTDIR=/path/to/includes.chroot ./neuronix-install.sh
#   sudo ./neuronix-install.sh --uninstall
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESTDIR="${DESTDIR:-}"
ACTION=install

for arg in "$@"; do
	case "$arg" in
	--uninstall) ACTION=uninstall ;;
	--help | -h)
		sed -n '2,9p' "$0" | tr -d '#'
		exit 0
		;;
	*)
		echo "Unknown argument: $arg" >&2
		exit 2
		;;
	esac
done

DESTDIR="${DESTDIR%/}"
prefix="${DESTDIR}/usr/local"
libdir="${prefix}/lib/neuronix/hypr-settings"
bindir="${prefix}/bin"
apps="${DESTDIR}/usr/share/applications"
wrapper="${bindir}/hypr-settings"
desktop="${apps}/hypr-settings.desktop"

need_root() {
	if [[ "$(id -u)" -ne 0 && -z "${DESTDIR}" ]]; then
		echo "Run as root (or set DESTDIR=… for an overlay/chroot)." >&2
		exit 1
	fi
}

have() { command -v "$1" >/dev/null 2>&1; }

uninstall() {
	need_root
	echo ">> Removing hypr-settings from ${DESTDIR:-/}…"
	rm -f "${wrapper}" "${desktop}"
	rm -rf "${libdir}"
	if have update-desktop-database && [[ -d "${apps}" ]]; then
		update-desktop-database "${apps}" 2>/dev/null || true
	fi
	echo ">> Done."
}

install_app() {
	need_root
	echo ">> Installing hypr-settings into ${DESTDIR:-/}/usr/local…"
	rm -rf "${libdir}"
	mkdir -p "${libdir}" "${bindir}" "${apps}"

	# App payload (Python modules + assets)
	install -m 0644 \
		"${ROOT}/"*.py \
		"${libdir}/"
	# Configs editor library (Configs tab — former gtk-configs)
	if [[ -d "${ROOT}/configs_lib" ]]; then
		rm -rf "${libdir}/configs_lib"
		mkdir -p "${libdir}/configs_lib"
		install -m 0644 "${ROOT}/configs_lib/"*.py "${libdir}/configs_lib/"
	fi
	# Optional helpers kept for reference / Nix users
	for f in README.md NEURONIX.md default.nix shell.nix run; do
		[[ -f "${ROOT}/$f" ]] && install -m 0644 "${ROOT}/$f" "${libdir}/$f"
	done
	[[ -f "${ROOT}/run" ]] && chmod 0755 "${libdir}/run"

	cat >"${wrapper}" <<'EOF'
#!/usr/bin/env bash
# Neuronix hypr-settings launcher
set -euo pipefail
APP=/usr/local/lib/neuronix/hypr-settings
# Suite theme module (Profile menu / theme.toml)
for _theme in \
	/usr/share/neuronix/gtk-theme/python \
	/usr/local/lib/neuronix/gtk-apps/gtk-theme/python; do
	if [[ -f "$_theme/gtk_theme.py" ]]; then
		export PYTHONPATH="${_theme}${PYTHONPATH:+:$PYTHONPATH}"
		break
	fi
done
cd "$APP"
exec /usr/bin/python3 "$APP/main.py" "$@"
EOF
	chmod 0755 "${wrapper}"

	cat >"${desktop}" <<'EOF'
[Desktop Entry]
Type=Application
Name=Settings
GenericName=System Settings
Comment=Wi‑Fi, Bluetooth, Displays, Sound, Themes, Configs, and more for Hyprland
Exec=hypr-settings
Icon=preferences-system
Terminal=false
Categories=Settings;DesktopSettings;System;
Keywords=settings;wifi;bluetooth;display;sound;themes;appearance;configs;hyprland;
StartupNotify=true
StartupWMClass=hypr-settings
EOF
	chmod 0644 "${desktop}"

	if have update-desktop-database && [[ -d "${apps}" ]]; then
		update-desktop-database "${apps}" 2>/dev/null || true
	fi

	echo ">> hypr-settings installed. Launch: hypr-settings"
}

case "$ACTION" in
install) install_app ;;
uninstall) uninstall ;;
esac
