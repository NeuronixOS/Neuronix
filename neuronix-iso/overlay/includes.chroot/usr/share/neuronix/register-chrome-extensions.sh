#!/usr/bin/env bash
# Pack Neuronix browser-extensions as CRX and register with Google Chrome /
# Chromium External Extensions so they appear as installed/available.
#
# Called from install-google-chrome.sh and neuronix-apply-desktop-profile.sh;
# safe to re-run. Also shadows google-chrome.desktop (the .deb overwrites it)
# so menus / mime open via neuronix-chrome.
#
# Chrome 137+ ignores --load-extension unless the wrapper passes
# --disable-features=DisableLoadExtensionCommandLineSwitch. Packing as root
# also requires --no-sandbox + an isolated --user-data-dir (Calamares/chroot).
# Packed CRXs must be world-readable (0644) — Chrome runs as the desktop user.
set -euo pipefail

EXT_ROOT="/usr/share/neuronix/browser-extensions"
CRX_ROOT="/var/lib/neuronix/chrome-extensions"
# System-wide External Extensions (Chrome + Chromium paths)
EXT_JSON_DIRS=(
	"/opt/google/chrome/extensions"
	"/usr/share/google-chrome/extensions"
	"/etc/chromium/extensions"
)

_log() { echo "[register-chrome-extensions] $*"; }

_write_wrapper_desktop() {
	local dest="$1" name="$2" exec_bin="$3" try_exec="$4" icon="$5" wmclass="$6"
	mkdir -p "$(dirname "$dest")"
	cat >"$dest" <<DESK
[Desktop Entry]
Version=1.0
Type=Application
Name=$name
Comment=$name with Neuronix extensions
Exec=$exec_bin %U
TryExec=$try_exec
Icon=$icon
Terminal=false
Categories=Network;WebBrowser;
MimeType=text/html;text/xml;application/xhtml+xml;x-scheme-handler/http;x-scheme-handler/https;
StartupNotify=true
StartupWMClass=$wmclass
DESK
}

# google-chrome-stable.deb ships google-chrome.desktop and overwrites the ISO
# wrapper on every apt install. Divert the vendor file, then write ours.
_shadow_chrome_desktops() {
	local apps=/usr/share/applications
	mkdir -p "$apps"

	if [[ -x /usr/local/bin/neuronix-chrome ]]; then
		local vendor="$apps/google-chrome.desktop"
		local diverted="$apps/google-chrome.desktop.vendor"
		if command -v dpkg-divert >/dev/null 2>&1 && [[ -e "$vendor" || -e "$diverted" ]]; then
			if ! dpkg-divert --list "$vendor" 2>/dev/null | grep -q .; then
				# Only divert if the current file is the vendor copy (not already ours).
				if [[ -f "$vendor" ]] && grep -q 'google-chrome-stable' "$vendor" 2>/dev/null; then
					dpkg-divert --local --rename --divert "$diverted" --add "$vendor" 2>/dev/null || true
				fi
			fi
		fi
		_write_wrapper_desktop "$apps/google-chrome.desktop" "Google Chrome" \
			neuronix-chrome neuronix-chrome google-chrome Google-chrome
		_write_wrapper_desktop "$apps/google-chrome-stable.desktop" "Google Chrome" \
			neuronix-chrome neuronix-chrome google-chrome Google-chrome
		_write_wrapper_desktop "$apps/neuronix-chrome.desktop" "Chrome" \
			neuronix-chrome neuronix-chrome google-chrome Google-chrome
	fi

	if [[ -x /usr/local/bin/neuronix-chromium ]]; then
		_write_wrapper_desktop "$apps/neuronix-chromium.desktop" "Chromium" \
			neuronix-chromium neuronix-chromium chromium Chromium-browser
		if command -v chromium >/dev/null 2>&1 || command -v chromium-browser >/dev/null 2>&1; then
			_write_wrapper_desktop "$apps/chromium.desktop" "Chromium Web Browser" \
				neuronix-chromium neuronix-chromium chromium Chromium-browser
		fi
	fi
}

_shadow_chrome_desktops

[[ -d "$EXT_ROOT" ]] || {
	_log "no extensions at $EXT_ROOT"
	exit 0
}

CHROME=""
for c in google-chrome-stable google-chrome chromium chromium-browser; do
	if command -v "$c" >/dev/null 2>&1; then
		CHROME="$c"
		break
	fi
done

mkdir -p "$CRX_ROOT"
for d in "${EXT_JSON_DIRS[@]}"; do
	mkdir -p "$d" 2>/dev/null || true
done

# Chrome extension id from PEM: sha256(DER pubkey) → first 32 hex → a-p alphabet
_extid_from_pem() {
	local pem="$1"
	openssl rsa -in "$pem" -pubout -outform DER 2>/dev/null \
		| sha256sum | awk '{print $1}' | head -c 32 \
		| tr '0-9a-f' 'a-p'
}

_manifest_version() {
	python3 - "$1" <<'PY'
import json, sys
print(json.load(open(sys.argv[1])).get("version", "1.0"))
PY
}

# Pack as root/headless: Chrome refuses to start without --no-sandbox and a
# private user-data-dir (Calamares / chroot / systemd oneshot).
_pack_extension() {
	local work="$1" pem="$2" log="$3"
	[[ -n "$CHROME" ]] || return 1
	local ud
	ud="$(dirname "$work")/pack-ud-$(basename "$work")"
	rm -rf "$ud"
	mkdir -p "$ud"
	local -a pack_args=(
		--no-sandbox
		--headless=new
		--disable-gpu
		--disable-extensions
		--no-first-run
		--no-default-browser-check
		--user-data-dir="$ud"
		--pack-extension="$work"
	)
	[[ -f "$pem" ]] && pack_args+=(--pack-extension-key="$pem")
	# Isolated from the user's running Chrome singleton.
	HOME="$ud" "$CHROME" "${pack_args[@]}" >"$log" 2>&1 || true
	rm -rf "$ud"
	[[ -f "${work}.crx" ]]
}

shopt -s nullglob
count=0
for ext in "$EXT_ROOT"/*/; do
	[[ -f "$ext/manifest.json" ]] || continue
	name="$(basename "$ext")"
	crx="$CRX_ROOT/${name}.crx"
	pem="$CRX_ROOT/${name}.pem"
	ver="$(_manifest_version "$ext/manifest.json")"

	if [[ ! -f "$crx" || ! -f "$pem" ]]; then
		if [[ -z "$CHROME" ]]; then
			_log "skip pack $name (Chrome not installed yet)"
			continue
		fi
		_log "packing $name"
		work="$CRX_ROOT/work-$name"
		rm -rf "$work" "${work}.crx" "${work}.pem"
		cp -a "$ext" "$work"
		# Chrome-generated indexes are not part of the source tree
		rm -rf "$work/_metadata"
		log="$CRX_ROOT/${name}.pack.log"
		if _pack_extension "$work" "$pem" "$log"; then
			mv -f "${work}.crx" "$crx"
			[[ -f "${work}.pem" ]] && mv -f "${work}.pem" "$pem"
		fi
		# Chrome runs as the desktop user and must be able to read the CRX.
		# PEMs stay root-only (private keys).
		[[ -f "$crx" ]] && chmod 0644 "$crx"
		[[ -f "$pem" ]] && chmod 0600 "$pem"
		rm -rf "$work"
		if [[ ! -f "$crx" || ! -f "$pem" ]]; then
			_log "pack failed for $name — see $log (wrapper --load-extension still applies)"
			continue
		fi
	fi

	id="$(_extid_from_pem "$pem")"
	if [[ -z "$id" || ${#id} -ne 32 ]]; then
		_log "could not derive extension id for $name"
		continue
	fi

	# Already-packed CRXs from an older run may still be 0600
	[[ -f "$crx" ]] && chmod 0644 "$crx"
	[[ -f "$pem" ]] && chmod 0600 "$pem"
	json_body=$(printf '{\n  "external_crx": "%s",\n  "external_version": "%s"\n}\n' "$crx" "$ver")
	for d in "${EXT_JSON_DIRS[@]}"; do
		[[ -d "$d" ]] || continue
		printf '%s' "$json_body" >"$d/${id}.json"
		chmod 0644 "$d/${id}.json"
	done
	_log "registered $name → $id (v$ver)"
	count=$((count + 1))
done
shopt -u nullglob

# Prefer neuronix-chrome as the system browser when the wrapper exists
if [[ -x /usr/local/bin/neuronix-chrome ]] && command -v update-alternatives >/dev/null 2>&1; then
	update-alternatives --install /usr/bin/x-www-browser x-www-browser /usr/local/bin/neuronix-chrome 200 \
		2>/dev/null || true
	update-alternatives --set x-www-browser /usr/local/bin/neuronix-chrome 2>/dev/null || true
fi

_log "done ($count registered)"
