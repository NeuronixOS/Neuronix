#!/usr/bin/env bash
# Pack Neuronix browser-extensions as CRX and register with Google Chrome /
# Chromium External Extensions so they appear as installed/available.
#
# Called from install-google-chrome.sh and neuronix-apply-desktop-profile.sh;
# safe to re-run. Launch wrappers neuronix-chrome / neuronix-chromium still
# apply --load-extension even if packing fails.
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
		# Chrome writes <dir>.crx next to the extension folder; use a work copy
		work="$CRX_ROOT/work-$name"
		rm -rf "$work"
		cp -a "$ext" "$work"
		rm -f "${work}.crx" "${work}.pem"
		# Prefer existing pem for stable IDs across rebuilds
		pack_args=(--pack-extension="$work")
		[[ -f "$pem" ]] && pack_args+=(--pack-extension-key="$pem")
		"$CHROME" "${pack_args[@]}" >/dev/null 2>&1 || true
		if [[ -f "${work}.crx" ]]; then
			mv -f "${work}.crx" "$crx"
			[[ -f "${work}.pem" ]] && mv -f "${work}.pem" "$pem"
		fi
		rm -rf "$work"
		if [[ ! -f "$crx" || ! -f "$pem" ]]; then
			_log "pack failed for $name — neuronix-chrome / neuronix-chromium --load-extension still applies"
			continue
		fi
	fi

	id="$(_extid_from_pem "$pem")"
	if [[ -z "$id" || ${#id} -ne 32 ]]; then
		_log "could not derive extension id for $name"
		continue
	fi

	json_body=$(printf '{\n  "external_crx": "%s",\n  "external_version": "%s"\n}\n' "$crx" "$ver")
	for d in "${EXT_JSON_DIRS[@]}"; do
		[[ -d "$d" ]] || continue
		printf '%s' "$json_body" >"$d/${id}.json"
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
