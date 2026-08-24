#!/usr/bin/env bash
# Merge personalize drop-ins into live-build includes.chroot.
# Usage: merge-personalize-dropins.sh <includes.chroot> <personalize_root>
#
#   configs/             → etc/skel/configs + links from configs/links.json
#                          system rows → /etc/* → ~/configs/*
#                          (neuronix-link-system-configs.sh)
#                          notes/ → ~/Notes (copy)
#                          www/  → /var/www (real files) + ~/www → /var/www
#   browser-extensions/  → usr/share/neuronix/browser-extensions + Chrome registration
#   services/            → usr/local/lib/neuronix/services + install.sh
#                          (default/services first, personalize/services overlays)
#   gtk-apps/            → overlay onto usr/local/lib/neuronix/gtk-apps (+ bin + desktops)
#   install/*.sh         → usr/share/neuronix/personalize-install (default then personalize)
#   hooks/*.sh           → usr/share/neuronix/user-hooks (default then personalize)
set -euo pipefail

INCLUDES="${1:?usage: merge-personalize-dropins.sh <includes.chroot> <personalize_root>}"
PERSONALIZE="${2:?}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEFAULT_LINKS="$SCRIPT_DIR/configs-links.default.json"

_info() { echo "merge-personalize-dropins: $*"; }

_is_meta_name() {
	case "$1" in
	# Note: .git is intentionally NOT meta — personalize/configs/.git is staged to ~/configs
	.gitkeep | .gitkeep.txt | README.md | README | links.json | install.sh.example) return 0 ;;
	*.example) return 0 ;;
	esac
	return 1
}

# True if dir has payload beyond docs / stubs
_has_dropin_content() {
	local dir="$1"
	[[ -d "$dir" ]] || return 1
	local f base
	while IFS= read -r -d '' f; do
		base="$(basename "$f")"
		_is_meta_name "$base" && continue
		if [[ -d "$f" ]]; then
			if find "$f" -type f \
				! -name '.gitkeep' ! -name '.gitkeep.txt' \
				! -name 'README.md' ! -name 'README' ! -name '*.example' \
				2>/dev/null | grep -q .; then
				return 0
			fi
			continue
		fi
		return 0
	done < <(find "$dir" -mindepth 1 -maxdepth 1 -print0 2>/dev/null)
	return 1
}

# True if path is only stubs/docs (skip when overlaying personalize onto default)
_is_stub_only() {
	local path="$1"
	if [[ -f "$path" ]]; then
		_is_meta_name "$(basename "$path")" && return 0
		# empty placeholder file
		[[ ! -s "$path" ]] && return 0
		return 1
	fi
	[[ -d "$path" ]] || return 1
	if find "$path" -type f \
		! -name '.gitkeep' ! -name '.gitkeep.txt' \
		! -name 'README.md' ! -name 'README' ! -name '*.example' \
		2>/dev/null | grep -q .; then
		return 1
	fi
	return 0
}

_rel_path_for_symlink() {
	# Echo relative symlink target from $1 (absolute link path under skel) to $2 (absolute dest under skel/configs/...)
	# Uses python for reliable relative paths.
	python3 - "$1" "$2" <<'PY'
import os, sys
link, target = sys.argv[1], sys.argv[2]
print(os.path.relpath(target, start=os.path.dirname(link)))
PY
}

_rel_symlink_abs() {
	local link="$1" target_abs="$2" rel
	mkdir -p "$(dirname "$link")"
	rel="$(_rel_path_for_symlink "$link" "$target_abs")"
	rm -rf "$link"
	ln -s "$rel" "$link"
}

# System paths (/etc/hosts, apache, nginx, …) symlink into the primary user's
# ~/configs tree (single git-managed source). Map is applied by
# neuronix-link-system-configs.sh after the user home exists (chroot + Calamares).
_merge_system_web_configs() {
	local src="$1" dest="$2" map="$3"

	local need_apache=0 need_nginx=0
	[[ -d "$dest/apache/sites-available" || -d "$dest/apache/sites-enabled" ]] && need_apache=1
	[[ -d "$dest/nginx/sites-available" || -d "$dest/nginx/sites-enabled" ]] && need_nginx=1
	[[ -f "$dest/apache/apache2.conf" ]] && need_apache=1
	[[ -f "$dest/nginx/nginx.conf" ]] && need_nginx=1

	local has_system=0
	[[ "$need_apache" -eq 1 || "$need_nginx" -eq 1 || -e "$dest/hosts" || -e "$dest/htpasswd" ]] && has_system=1
	if [[ "$has_system" -eq 0 ]] && python3 -c 'import json,sys; raise SystemExit(0 if json.load(open(sys.argv[1])).get("system") else 1)' "$map" 2>/dev/null; then
		has_system=1
	fi
	[[ "$has_system" -eq 1 ]] || return 0

	# Persist system link map for neuronix-link-system-configs.sh
	local map_out="$INCLUDES/etc/neuronix/system-config-links.tsv"
	mkdir -p "$(dirname "$map_out")"
	python3 - "$map" "$dest" <<'PY' >"$map_out"
import json, sys, os
defaults = [
    ("symlink", "hosts", "/etc/hosts"),
    ("symlink", "htpasswd", "/etc/apache2/.htpasswd"),
    ("symlink", "apache/apache2.conf", "/etc/apache2/apache2.conf"),
    ("symlink", "apache/envvars", "/etc/apache2/envvars"),
    ("symlink", "apache/sites-available", "/etc/apache2/sites-available"),
    ("symlink", "apache/sites-enabled", "/etc/apache2/sites-enabled"),
    ("symlink", "nginx/nginx.conf", "/etc/nginx/nginx.conf"),
    ("symlink", "nginx/sites-available", "/etc/nginx/sites-available"),
    ("symlink", "nginx/sites-enabled", "/etc/nginx/sites-enabled"),
]
data = json.load(open(sys.argv[1]))
dest = sys.argv[2]
rows = data.get("system")
if not rows:
    rows = [{"type": t, "from": f, "to": to} for t, f, to in defaults]
print("# type\tfrom_rel (under ~/configs)\tto_abs")
for link in rows:
    typ = link.get("type", "symlink")
    frm = link["from"]
    to = link["to"]
    # Only emit rows whose source exists in the staged ~/configs tree
    if os.path.lexists(os.path.join(dest, frm)):
        print(f"{typ}\t{frm}\t{to}")
PY
	_info "wrote system config link map → etc/neuronix/system-config-links.tsv"

	# Package + enable hooks when site trees / confs are present; re-link after apt
	local hook_dir pkgs=()
	hook_dir="$(cd "$INCLUDES/.." && pwd)/hooks/normal"
	mkdir -p "$hook_dir"
	[[ "$need_apache" -eq 1 ]] && pkgs+=(apache2)
	[[ "$need_nginx" -eq 1 ]] && pkgs+=(nginx)
	if ((${#pkgs[@]} > 0)); then
		local pkg_list
		pkg_list=$(printf '%s ' "${pkgs[@]}")
		cat >"$hook_dir/9931-neuronix-web-servers.hook.chroot" <<HOOK
#!/bin/bash
# Install apache2/nginx when personalize configs include site trees.
# Then point /etc at the live user's ~/configs (git-managed source of truth).
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ${pkg_list}
HOOK
		if [[ "$need_apache" -eq 1 ]]; then
			cat >>"$hook_dir/9931-neuronix-web-servers.hook.chroot" <<'HOOK'
systemctl enable apache2.service 2>/dev/null || true
HOOK
		fi
		if [[ "$need_nginx" -eq 1 ]]; then
			cat >>"$hook_dir/9931-neuronix-web-servers.hook.chroot" <<'HOOK'
systemctl enable nginx.service 2>/dev/null || true
HOOK
		fi
		cat >>"$hook_dir/9931-neuronix-web-servers.hook.chroot" <<'HOOK'
if [[ -x /usr/local/sbin/neuronix-link-system-configs.sh ]]; then
	/usr/local/sbin/neuronix-link-system-configs.sh || true
fi
HOOK
		chmod 0755 "$hook_dir/9931-neuronix-web-servers.hook.chroot"
		_info "wrote web-servers hook (install: ${pkg_list})"
	else
		# hosts-only (or other system rows): still re-link once user home exists
		cat >"$hook_dir/9932-neuronix-link-system-configs.hook.chroot" <<'HOOK'
#!/bin/bash
set -e
if [[ -x /usr/local/sbin/neuronix-link-system-configs.sh ]]; then
	/usr/local/sbin/neuronix-link-system-configs.sh || true
fi
HOOK
		chmod 0755 "$hook_dir/9932-neuronix-link-system-configs.hook.chroot"
		_info "wrote system-config link chroot hook"
	fi
}

# ---------------------------------------------------------------------------
# configs/www → /var/www (real files on the installed system)
# Listed in links.json skip (and always skipped above). Personalize overlays default.
# Home shortcut ~/www → /var/www comes from links.json abs_symlink (or created here).
# ---------------------------------------------------------------------------
_stage_www_tree() {
	local default_src="${1:-}"
	local pers_src="${2:-}"
	local skel="${3:-}"
	local var_www="$INCLUDES/var/www"
	local staged=0

	_copy_www_payload() {
		local src="$1"
		[[ -d "$src" ]] || return 0
		local item base
		shopt -s dotglob nullglob
		for item in "$src"/*; do
			base="$(basename "$item")"
			# live-build drops .git; KvNix overlay tars it separately. Keep README / .gitkeep / *.example.
			[[ "$base" == .git ]] && continue
			if [[ -d "$item" && ! -L "$item" ]]; then
				mkdir -p "$var_www/$base"
				# deep merge directory contents (including hidden files)
				local child cbase
				for child in "$item"/*; do
					[[ -e "$child" ]] || continue
					cbase="$(basename "$child")"
					[[ "$cbase" == .git ]] && continue
					rm -rf "$var_www/$base/$cbase"
					cp -a "$child" "$var_www/$base/"
				done
			else
				rm -rf "$var_www/$base"
				cp -a "$item" "$var_www/"
			fi
			staged=1
		done
		shopt -u dotglob nullglob
	}

	if [[ -d "${default_src}/www" ]] || [[ -n "$pers_src" && -d "${pers_src}/www" ]]; then
		mkdir -p "$var_www"
		# Stub default/www (README-only) must not become the live site tree.
		if [[ -d "${default_src}/www" ]] && ! _is_stub_only "${default_src}/www"; then
			_copy_www_payload "${default_src}/www"
		fi
		[[ -n "$pers_src" ]] && _copy_www_payload "${pers_src}/www"
	fi

	if [[ -d "$var_www" ]] && find "$var_www" -mindepth 1 | grep -q .; then
		_info "staged configs/www → var/www"
		# Ensure ~/www → /var/www even if links.json omits abs_symlink
		if [[ -n "$skel" ]]; then
			rm -rf "$skel/www"
			ln -sfn /var/www "$skel/www"
			_info "  link ~/www → /var/www"
		fi
	elif [[ -d "$var_www" ]]; then
		# Keep an empty /var/www + home link when only stubs were present
		mkdir -p "$var_www"
		if [[ -n "$skel" ]]; then
			rm -rf "$skel/www"
			ln -sfn /var/www "$skel/www"
			_info "  link ~/www → /var/www (empty tree)"
		fi
	fi
}

# ---------------------------------------------------------------------------
# configs → ~/configs + links.json mapping
# Base: default/configs (stock desktop). Overlay: personalize/configs when present.
# ---------------------------------------------------------------------------
merge_configs() {
	local default_src
	default_src="$(cd "$SCRIPT_DIR/.." && pwd)/default/configs"
	local pers_src=""
	if [[ -d "${PERSONALIZE:-}" ]]; then
		pers_src="$PERSONALIZE/configs"
	fi

	local have_default=0 have_pers=0
	_has_dropin_content "$default_src" && have_default=1
	[[ -n "$pers_src" ]] && _has_dropin_content "$pers_src" && have_pers=1
	if [[ "$have_default" -eq 0 && "$have_pers" -eq 0 ]]; then
		return 0
	fi

	local skel="$INCLUDES/etc/skel"
	local dest="$skel/configs"
	local default_map="" pers_map="" map="" _merged_links_map=""
	[[ -f "$default_src/links.json" ]] && default_map="$default_src/links.json"
	[[ -n "$pers_src" && -f "$pers_src/links.json" ]] && pers_map="$pers_src/links.json"
	[[ -z "$default_map" && -f "$DEFAULT_LINKS" ]] && default_map="$DEFAULT_LINKS"

	# Overlay links.json replaces skip/system, but home `links` are unioned with
	# default (overlay wins on the same `to`). Otherwise a server overlay that
	# omits hypr/waybar drops the live Calamares session config.
	if [[ -n "$pers_map" && -n "$default_map" ]]; then
		map="$(mktemp)"
		_merged_links_map="$map"
		python3 - "$default_map" "$pers_map" "$map" <<'PY'
import json, sys
base = json.load(open(sys.argv[1]))
pers = json.load(open(sys.argv[2]))
out = {
    "skip": list(pers.get("skip", base.get("skip", []))),
    "system": list(pers["system"]) if "system" in pers else list(base.get("system", [])),
}
links = {}
for item in base.get("links", []):
    links[item["to"]] = item
for item in pers.get("links", []):
    links[item["to"]] = item
out["links"] = list(links.values())
with open(sys.argv[3], "w") as fh:
    json.dump(out, fh, indent=2)
    fh.write("\n")
PY
		_info "merged default+personalize links.json (overlay wins on same to=)"
	elif [[ -n "$pers_map" ]]; then
		map="$pers_map"
	elif [[ -n "$default_map" ]]; then
		map="$default_map"
	fi
	if [[ ! -f "$map" ]]; then
		_info "ERROR: no configs/links.json and no default map at $DEFAULT_LINKS" >&2
		return 1
	fi

	_info "staging configs → etc/skel/configs (map: $(basename "$map"); default=$have_default personalize=$have_pers)"
	mkdir -p "$skel"
	rm -rf "$dest"
	mkdir -p "$dest"

	# Build skip set from JSON
	local skip_args=()
	mapfile -t skip_args < <(python3 - "$map" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
for s in data.get("skip", []):
    print(s)
print("links.json")
print("www")
PY
	)

	_deep_merge_dir() {
		# Copy src into dest: overwrite same paths, keep dest-only siblings.
		local src="$1" dest="$2"
		mkdir -p "$dest"
		local item base
		shopt -s dotglob nullglob
		for item in "$src"/*; do
			base="$(basename "$item")"
			_is_meta_name "$base" && continue
			if [[ -d "$item" && ! -L "$item" ]]; then
				_deep_merge_dir "$item" "$dest/$base"
			else
				rm -rf "$dest/$base"
				cp -a "$item" "$dest/$base"
			fi
		done
		shopt -u dotglob nullglob
	}

	_copy_configs_tree() {
		local src="$1"
		local skip_stubs="${2:-0}"
		[[ -d "$src" ]] || return 0
		shopt -s dotglob nullglob
		local item base skip s
		for item in "$src"/*; do
			base="$(basename "$item")"
			skip=0
			for s in "${skip_args[@]}"; do
				[[ "$base" == "$s" ]] && skip=1 && break
			done
			[[ "$skip" -eq 1 ]] && continue
			_is_meta_name "$base" && continue
			# Personalize stubs (.gitkeep-only) must not wipe stock default trees
			if [[ "$skip_stubs" -eq 1 ]] && _is_stub_only "$item"; then
				_info "  skip stub overlay configs/$base"
				continue
			fi
			# Personalize overlay: deep-merge dirs so stock siblings (e.g. hyprland.conf) remain
			if [[ "$skip_stubs" -eq 1 && -d "$item" && ! -L "$item" && -d "$dest/$base" ]]; then
				_deep_merge_dir "$item" "$dest/$base"
				_info "  deep-merge configs/$base"
			else
				rm -rf "$dest/$base"
				cp -a "$item" "$dest/"
			fi
		done
		shopt -u dotglob nullglob
	}

	[[ "$have_default" -eq 1 ]] && _copy_configs_tree "$default_src" 0
	[[ "$have_pers" -eq 1 ]] && _copy_configs_tree "$pers_src" 1

	# Keep personalize/configs/.git on the live/installed system as ~/configs/.git.
	# live-build often omits .git from includes.chroot, so also stage a tarball
	# unpacked by 9933-neuronix-restore-git.hook.chroot. Never fall back to
	# personalize/.git (wrong GitHub repo for ~/configs).
	_stage_git_payload() {
		local git_path="$1" payload="$2" label="$3"
		[[ -e "$git_path" ]] || return 0
		mkdir -p "$(dirname "$payload")"
		tar -C "$(dirname "$git_path")" -cf "$payload" .git
		_info "  staged $label → ${payload#"$INCLUDES/"}"
	}

	if [[ -n "$pers_src" && -e "$pers_src/.git" ]]; then
		rm -rf "$dest/.git"
		cp -a "$pers_src/.git" "$dest/.git"
		_info "  copied configs/.git → etc/skel/configs/.git (user config repo)"
		_stage_git_payload "$pers_src/.git" \
			"$INCLUDES/usr/share/neuronix/skel-configs.git.tar" \
			"configs/.git"
	fi

	# configs/www → /var/www before home abs_symlink ~/www → /var/www
	_stage_www_tree "$default_src" "$pers_src" "$skel"

	# Apply link map (only when source exists under dest — except abs_symlink)
	local map_lines
	map_lines="$(mktemp)"
	python3 - "$map" <<'PY' >"$map_lines"
import json, sys
data = json.load(open(sys.argv[1]))
for link in data.get("links", []):
    typ = link.get("type", "symlink")
    print(f"{typ}\t{link['from']}\t{link['to']}")
PY
	while IFS=$'\t' read -r typ from_rel to_rel; do
		[[ -n "${typ:-}" ]] || continue
		local to_abs="$skel/$to_rel"
		case "$typ" in
		abs_symlink)
			# from_rel is an absolute path (e.g. /var/www) → ~/to_rel
			mkdir -p "$(dirname "$to_abs")"
			rm -rf "$to_abs"
			ln -sfn "$from_rel" "$to_abs"
			_info "  link ~/$to_rel → $from_rel"
			;;
		symlink)
			local from_abs="$dest/$from_rel"
			[[ -e "$from_abs" ]] || continue
			_rel_symlink_abs "$to_abs" "$from_abs"
			_info "  link ~/$to_rel → configs/$from_rel"
			;;
		copy)
			local from_abs="$dest/$from_rel"
			[[ -e "$from_abs" ]] || continue
			mkdir -p "$(dirname "$to_abs")"
			cp -a "$from_abs" "$to_abs"
			if [[ -d "$to_abs" ]]; then
				# Drop docs/stubs from the home copy (keep real notes only).
				find "$to_abs" -type f \( -name 'README.md' -o -name 'README' -o -name '.gitkeep' -o -name '.gitkeep.txt' -o -name '*.example' \) -delete 2>/dev/null || true
				find "$to_abs" -type d -empty -delete 2>/dev/null || true
				chmod 0755 "$to_abs" 2>/dev/null || true
			else
				chmod 0644 "$to_abs" 2>/dev/null || true
			fi
			_info "  copy configs/$from_rel → ~/$to_rel"
			;;
		*)
			_info "  skip unknown link type '$typ' for $from_rel"
			;;
		esac
	done <"$map_lines"
	rm -f "$map_lines"

	# System web configs: prefer personalize tree when present, else staged dest / default
	local sys_src="$dest"
	[[ "$have_pers" -eq 1 ]] && sys_src="$pers_src"
	_merge_system_web_configs "$sys_src" "$dest" "$map"
	[[ -n "${_merged_links_map:-}" ]] && rm -f "$_merged_links_map"

	if [[ -d "$dest/ssh" ]]; then
		local hook_dir
		hook_dir="$(cd "$INCLUDES/.." && pwd)/hooks/normal"
		mkdir -p "$hook_dir"
		cat >"$hook_dir/9925-neuronix-personalize-ssh.hook.chroot" <<'HOOK'
#!/bin/bash
# Fix skel configs/ssh permissions (personalize drop-in).
set -e
SKEL_SSH=/etc/skel/configs/ssh
if [[ -d "$SKEL_SSH" ]]; then
	chmod 700 "$SKEL_SSH"
	find "$SKEL_SSH" -type f \( -name 'id_*' ! -name '*.pub' \) -exec chmod 600 {} +
	find "$SKEL_SSH" -type f -name '*.pub' -exec chmod 644 {} +
	[[ -f "$SKEL_SSH/authorized_keys" ]] && chmod 600 "$SKEL_SSH/authorized_keys"
	[[ -f "$SKEL_SSH/config" ]] && chmod 600 "$SKEL_SSH/config"
	[[ -f "$SKEL_SSH/known_hosts" ]] && chmod 644 "$SKEL_SSH/known_hosts"
fi
HOOK
		chmod 0755 "$hook_dir/9925-neuronix-personalize-ssh.hook.chroot"
		_info "wrote ssh perms chroot hook"
	fi
}

# ---------------------------------------------------------------------------
# browser-extensions
# ---------------------------------------------------------------------------
merge_browser_extensions() {
	local src="$PERSONALIZE/browser-extensions"
	_has_dropin_content "$src" || return 0

	local dest="$INCLUDES/usr/share/neuronix/browser-extensions"
	_info "staging browser-extensions → usr/share/neuronix/browser-extensions"
	mkdir -p "$dest"
	local count=0
	shopt -s nullglob
	for ext in "$src"/*/; do
		[[ -d "$ext" ]] || continue
		local name
		name="$(basename "$ext")"
		[[ "$name" == .* ]] && continue
		_is_meta_name "$name" && continue
		if [[ ! -f "$ext/manifest.json" ]]; then
			_info "skip $name (no manifest.json)"
			continue
		fi
		rm -rf "$dest/$name"
		cp -a "$ext" "$dest/$name"
		count=$((count + 1))
	done
	shopt -u nullglob
	_info "staged $count extension(s)"
	[[ "$count" -gt 0 ]] || return 0

	# Wrappers + desktops (overlay ships defaults; refresh from share when extensions stage)
	local bin="$INCLUDES/usr/local/bin"
	local apps="$INCLUDES/usr/share/applications"
	mkdir -p "$bin" "$apps"

	# Google Chrome wrapper (Chrome only — Chromium has neuronix-chromium)
	cat >"$bin/neuronix-chrome" <<'WRAP'
#!/usr/bin/env bash
# Launch Google Chrome with Neuronix unpacked extensions (if staged).
set -euo pipefail
EXT_ROOT="/usr/share/neuronix/browser-extensions"
LOAD_ARGS=()
if [[ -d "$EXT_ROOT" ]]; then
	shopt -s nullglob
	for d in "$EXT_ROOT"/*/; do
		[[ -f "$d/manifest.json" ]] || continue
		LOAD_ARGS+=("$(realpath "$d")")
	done
	shopt -u nullglob
fi
CHROME=""
for c in google-chrome-stable google-chrome; do
	if command -v "$c" >/dev/null 2>&1; then
		CHROME="$c"
		break
	fi
done
if [[ -z "$CHROME" ]]; then
	echo "neuronix-chrome: Google Chrome not found in PATH" >&2
	exit 1
fi
if [[ ${#LOAD_ARGS[@]} -gt 0 ]]; then
	IFS=,
	exec "$CHROME" --load-extension="${LOAD_ARGS[*]}" "$@"
fi
exec "$CHROME" "$@"
WRAP
	chmod 0755 "$bin/neuronix-chrome"

	# Debian Chromium wrapper
	cat >"$bin/neuronix-chromium" <<'WRAP'
#!/usr/bin/env bash
# Launch Debian Chromium with Neuronix unpacked extensions (if staged).
set -euo pipefail
EXT_ROOT="/usr/share/neuronix/browser-extensions"
LOAD_ARGS=()
if [[ -d "$EXT_ROOT" ]]; then
	shopt -s nullglob
	for d in "$EXT_ROOT"/*/; do
		[[ -f "$d/manifest.json" ]] || continue
		LOAD_ARGS+=("$(realpath "$d")")
	done
	shopt -u nullglob
fi
CHROME=""
for c in chromium chromium-browser; do
	if command -v "$c" >/dev/null 2>&1; then
		CHROME="$c"
		break
	fi
done
if [[ -z "$CHROME" ]]; then
	echo "neuronix-chromium: chromium not found in PATH" >&2
	exit 1
fi
if [[ ${#LOAD_ARGS[@]} -gt 0 ]]; then
	IFS=,
	exec "$CHROME" --load-extension="${LOAD_ARGS[*]}" "$@"
fi
exec "$CHROME" "$@"
WRAP
	chmod 0755 "$bin/neuronix-chromium"

	cat >"$apps/neuronix-chrome.desktop" <<'DESK'
[Desktop Entry]
Version=1.0
Type=Application
Name=Chrome
Comment=Google Chrome with Neuronix extensions
Exec=neuronix-chrome %U
TryExec=neuronix-chrome
Icon=google-chrome
Terminal=false
Categories=Network;WebBrowser;
MimeType=text/html;text/xml;application/xhtml+xml;x-scheme-handler/http;x-scheme-handler/https;
StartupNotify=true
StartupWMClass=Google-chrome
DESK
	cat >"$apps/neuronix-chromium.desktop" <<'DESK'
[Desktop Entry]
Version=1.0
Type=Application
Name=Chromium
Comment=Chromium with Neuronix extensions
Exec=neuronix-chromium %U
TryExec=neuronix-chromium
Icon=chromium
Terminal=false
Categories=Network;WebBrowser;
MimeType=text/html;text/xml;application/xhtml+xml;x-scheme-handler/http;x-scheme-handler/https;
StartupNotify=true
StartupWMClass=Chromium-browser
DESK
	# Shadow package desktops so menus / mime open via Neuronix wrappers
	for desk_name in google-chrome.desktop google-chrome-stable.desktop; do
		cat >"$apps/$desk_name" <<'DESK'
[Desktop Entry]
Version=1.0
Type=Application
Name=Google Chrome
Comment=Google Chrome with Neuronix extensions
Exec=neuronix-chrome %U
TryExec=neuronix-chrome
Icon=google-chrome
Terminal=false
Categories=Network;WebBrowser;
MimeType=text/html;text/xml;application/xhtml+xml;x-scheme-handler/http;x-scheme-handler/https;
StartupNotify=true
StartupWMClass=Google-chrome
DESK
	done
	cat >"$apps/chromium.desktop" <<'DESK'
[Desktop Entry]
Version=1.0
Type=Application
Name=Chromium Web Browser
Comment=Chromium with Neuronix extensions
Exec=neuronix-chromium %U
TryExec=neuronix-chromium
Icon=chromium
Terminal=false
Categories=Network;WebBrowser;
MimeType=text/html;text/xml;application/xhtml+xml;x-scheme-handler/http;x-scheme-handler/https;
StartupNotify=true
StartupWMClass=Chromium-browser
DESK

	# Prefer Neuronix wrappers in skel mimeapps when present
	local mime="$INCLUDES/etc/skel/.config/mimeapps.list"
	if [[ -f "$mime" ]]; then
		sed -i \
			-e 's/google-chrome\.desktop/neuronix-chrome.desktop/g' \
			-e 's/google-chrome-stable\.desktop/neuronix-chrome.desktop/g' \
			-e 's/chromium\.desktop/neuronix-chromium.desktop/g' \
			"$mime"
	fi

	# Registration helper (packs CRX + External Extensions when Chrome/Chromium is present)
	local reg="$INCLUDES/usr/share/neuronix/register-chrome-extensions.sh"
	mkdir -p "$(dirname "$reg")"
	cp -a "$SCRIPT_DIR/register-chrome-extensions.sh" "$reg"
	chmod 0755 "$reg"

	# Chroot / post-chrome hook marker list of staged extensions
	mkdir -p "$INCLUDES/usr/share/neuronix"
	: >"$INCLUDES/usr/share/neuronix/browser-extensions.stamp"
}

# ---------------------------------------------------------------------------
# services
# ---------------------------------------------------------------------------
_service_type() {
	local unit="$1" dir="$2"
	if [[ -f "$dir/TYPE" ]]; then
		local t
		t="$(tr -d '[:space:]' <"$dir/TYPE" | tr '[:upper:]' '[:lower:]')"
		case "$t" in
		system | user) echo "$t"; return 0 ;;
		esac
	fi
	if grep -qiE '^WantedBy=.*(graphical-session|default\.target)' "$unit" 2>/dev/null; then
		echo user
		return 0
	fi
	if grep -qiE '^WantedBy=.*multi-user\.target' "$unit" 2>/dev/null; then
		echo system
		return 0
	fi
	if grep -qE '%h|graphical-session' "$unit" 2>/dev/null; then
		echo user
		return 0
	fi
	echo system
}

_adapt_unit() {
	local unit_src="$1" unit_dst="$2" staged="$3" name="$4" stype="$5"
	local tmp
	tmp="$(mktemp)"
	sed -E \
		-e "s#/home/[^/]+/Dropbox/Devices/Services/${name}#${staged}#g" \
		-e "s#%h/Dropbox/Devices/Services/${name}#${staged}#g" \
		-e "s#__SCRIPT_DIR__#${staged}#g" \
		"$unit_src" >"$tmp"
	if [[ "$stype" == system ]]; then
		# Drop developer User=<login> from personal drop-ins (keep root / dashed service accounts).
		sed -i -E '/^User=root[[:space:]]*$/b; /^User=[a-z][a-z0-9]*[[:space:]]*$/d' "$tmp"
	fi
	if ! grep -qE '^WorkingDirectory=' "$tmp"; then
		sed -i "/^\[Service\]/a WorkingDirectory=${staged}" "$tmp"
	fi
	mv "$tmp" "$unit_dst"
}

_enable_system_unit() {
	local unit_name="$1" wanted_by="${2:-multi-user.target}"
	local wants="$INCLUDES/etc/systemd/system/${wanted_by}.wants"
	mkdir -p "$INCLUDES/etc/systemd/system" "$wants"
	ln -sf "/etc/systemd/system/$unit_name" "$wants/$unit_name"
}

_enable_user_unit() {
	local unit_name="$1" wanted_by="${2:-default.target}"
	local wants="$INCLUDES/etc/skel/.config/systemd/user/${wanted_by}.wants"
	mkdir -p "$INCLUDES/etc/skel/.config/systemd/user" "$wants"
	ln -sf "../$unit_name" "$wants/$unit_name"
}

_fallback_enable_units() {
	local staged="$1" runtime="$2" name="$3"
	local units=("$staged"/*.service)
	[[ -e "${units[0]:-}" ]] || {
		_info "  skip enable $name (no install.sh and no *.service)"
		return 0
	}
	local unit
	for unit in "${units[@]}"; do
		[[ -f "$unit" ]] || continue
		local unit_name stype wanted adapted
		unit_name="$(basename "$unit")"
		stype="$(_service_type "$unit" "$staged")"
		wanted="$(grep -iE '^WantedBy=' "$unit" | head -1 | cut -d= -f2- | tr -d '[:space:]' || true)"
		[[ -z "$wanted" ]] && {
			if [[ "$stype" == user ]]; then wanted=default.target; else wanted=multi-user.target; fi
		}
		adapted="$(mktemp)"
		_adapt_unit "$unit" "$adapted" "$runtime" "$name" "$stype"
		if [[ "$stype" == user ]]; then
			mkdir -p "$INCLUDES/etc/skel/.config/systemd/user"
			cp -a "$adapted" "$INCLUDES/etc/skel/.config/systemd/user/$unit_name"
			_enable_user_unit "$unit_name" "$wanted"
			_info "  fallback enabled user unit $unit_name"
		else
			mkdir -p "$INCLUDES/etc/systemd/system"
			cp -a "$adapted" "$INCLUDES/etc/systemd/system/$unit_name"
			_enable_system_unit "$unit_name" "$wanted"
			_info "  fallback enabled system unit $unit_name"
		fi
		rm -f "$adapted"
	done
}

# Stage one services tree into includes.chroot. Sets STAGE_SERVICES_COUNT.
_stage_services_from() {
	local src="$1"
	local label="$2"
	local root="$3"
	local runtime_root="$4"
	local install_list="$5"
	local n=0
	STAGE_SERVICES_COUNT=0

	_has_dropin_content "$src" || return 0

	shopt -s nullglob
	local svc_dir name staged runtime
	for svc_dir in "$src"/*/; do
		[[ -d "$svc_dir" ]] || continue
		name="$(basename "$svc_dir")"
		[[ "$name" == .* ]] && continue
		_is_meta_name "$name" && continue

		staged="$root/$name"
		runtime="$runtime_root/$name"
		rm -rf "$staged"
		cp -a "$svc_dir" "$staged"
		chmod 0755 "$staged/install.sh" 2>/dev/null || true
		# Overlay-only ISO prep (build host). e.g. KvNix apachebringup tars configs/www/.git.
		if [[ -f "$staged/host-stage.sh" ]]; then
			chmod 0755 "$staged/host-stage.sh"
			"$staged/host-stage.sh" "$INCLUDES" "${PERSONALIZE:-}" "$staged"
			_info "  ran $name/host-stage.sh"
		fi
		_info "  service $name ($label)"
		n=$((n + 1))

		if [[ -f "$staged/install.sh" ]]; then
			# Re-append after overlay: drop prior lines for this name
			if [[ -f "$install_list" ]]; then
				grep -vxF "$name" "$install_list" >"${install_list}.tmp" 2>/dev/null || true
				mv -f "${install_list}.tmp" "$install_list"
			fi
			echo "$name" >>"$install_list"
			_info "  will run install.sh via chroot hook"
		else
			_fallback_enable_units "$staged" "$runtime" "$name"
		fi
	done
	shopt -u nullglob
	STAGE_SERVICES_COUNT=$n
}

merge_services() {
	local default_src
	default_src="$(cd "$SCRIPT_DIR/.." && pwd)/default/services"
	local pers_src=""
	if [[ -d "${PERSONALIZE:-}" ]]; then
		pers_src="$PERSONALIZE/services"
	fi

	local have_default=0 have_pers=0
	_has_dropin_content "$default_src" && have_default=1
	[[ -n "$pers_src" ]] && _has_dropin_content "$pers_src" && have_pers=1
	if [[ "$have_default" -eq 0 && "$have_pers" -eq 0 ]]; then
		return 0
	fi

	local root="$INCLUDES/usr/local/lib/neuronix/services"
	local runtime_root="/usr/local/lib/neuronix/services"
	mkdir -p "$root"
	_info "staging services → usr/local/lib/neuronix/services (default=$have_default personalize=$have_pers)"

	local hook_dir install_list
	hook_dir="$(cd "$INCLUDES/.." && pwd)/hooks/normal"
	install_list="$INCLUDES/usr/share/neuronix/personalize-services.list"
	mkdir -p "$(dirname "$install_list")" "$hook_dir"
	: >"$install_list"

	local n_def=0 n_pers=0
	if [[ "$have_default" -eq 1 ]]; then
		_stage_services_from "$default_src" "default" "$root" "$runtime_root" "$install_list"
		n_def=$STAGE_SERVICES_COUNT
	fi
	if [[ "$have_pers" -eq 1 ]]; then
		_stage_services_from "$pers_src" "personalize" "$root" "$runtime_root" "$install_list"
		n_pers=$STAGE_SERVICES_COUNT
	fi
	_info "  staged services (default=$n_def personalize=$n_pers)"

	if [[ -s "$install_list" ]]; then
		cat >"$hook_dir/9930-neuronix-personalize-services.hook.chroot" <<'HOOK'
#!/bin/bash
# Run default + personalize service install.sh scripts inside the live-build chroot.
# Continue after a single service failure so one bad installer does not abort the ISO.
set -u
LIST=/usr/share/neuronix/personalize-services.list
ROOT=/usr/local/lib/neuronix/services
[[ -f "$LIST" ]] || exit 0
failed=0
while IFS= read -r name || [[ -n "$name" ]]; do
	[[ -z "$name" ]] && continue
	dir="$ROOT/$name"
	[[ -x "$dir/install.sh" || -f "$dir/install.sh" ]] || continue
	chmod +x "$dir/install.sh"
	echo "[neuronix-services] installing $name"
	if (
		cd "$dir"
		export NEURONIX_SERVICE_ROOT="$dir"
		export NEURONIX_SERVICE_NAME="$name"
		./install.sh
	); then
		echo "[neuronix-services] $name OK"
	else
		echo "[neuronix-services] ERROR: $name install.sh failed" >&2
		failed=1
	fi
done <"$LIST"
if [[ "$failed" -ne 0 ]]; then
	echo "[neuronix-services] one or more install.sh scripts failed" >&2
	exit 1
fi
HOOK
		chmod 0755 "$hook_dir/9930-neuronix-personalize-services.hook.chroot"
		_info "wrote services install.sh chroot hook"
	fi
}

# ---------------------------------------------------------------------------
# gtk-apps — additional / override binaries on top of default/gtk-apps
# ---------------------------------------------------------------------------
merge_gtk_apps() {
	local src="$PERSONALIZE/gtk-apps"
	_has_dropin_content "$src" || return 0

	local lib="$INCLUDES/usr/local/lib/neuronix/gtk-apps"
	local bin="$INCLUDES/usr/local/bin"
	local desk="$INCLUDES/usr/share/applications"
	mkdir -p "$lib" "$bin" "$desk"
	_info "staging personalize/gtk-apps → usr/local/lib/neuronix/gtk-apps (overlay)"

	local count=0
	shopt -s nullglob
	if [[ -d "$src/bin" ]]; then
		local f name
		for f in "$src"/bin/*; do
			[[ -f "$f" ]] || continue
			name="$(basename "$f")"
			cp -a "$f" "$lib/$name"
			chmod 0755 "$lib/$name"
			ln -sfn "../lib/neuronix/gtk-apps/$name" "$bin/$name"
			count=$((count + 1))
			_info "  bin $name"
		done
	fi
	# Also accept loose binaries at gtk-apps/<name> (no bin/ subdir)
	for f in "$src"/*; do
		[[ -f "$f" ]] || continue
		name="$(basename "$f")"
		_is_meta_name "$name" && continue
		case "$name" in
		*.desktop | *.toml | *.json | *.md) continue ;;
		esac
		[[ -x "$f" || "$name" == gtk-* ]] || continue
		cp -a "$f" "$lib/$name"
		chmod 0755 "$lib/$name"
		ln -sfn "../lib/neuronix/gtk-apps/$name" "$bin/$name"
		count=$((count + 1))
		_info "  bin $name (top-level)"
	done
	if [[ -d "$src/applications" ]]; then
		local d
		for d in "$src"/applications/*.desktop; do
			[[ -f "$d" ]] || continue
			cp -a "$d" "$desk/"
			_info "  desktop $(basename "$d")"
		done
	fi
	# Multi-file app payloads: apps/<name>/ → lib/apps/<name>/
	if [[ -d "$src/apps" ]]; then
		local appdir appname
		mkdir -p "$lib/apps"
		for appdir in "$src"/apps/*/; do
			[[ -d "$appdir" ]] || continue
			appname="$(basename "$appdir")"
			[[ "$appname" == .* ]] && continue
			_is_meta_name "$appname" && continue
			rm -rf "$lib/apps/$appname"
			cp -a "$appdir" "$lib/apps/$appname"
			_info "  apps/$appname"
		done
	fi
	shopt -u nullglob

	if [[ -d "$src/gtk-theme" ]] && ! _is_stub_only "$src/gtk-theme"; then
		local theme_share="$INCLUDES/usr/share/neuronix/gtk-theme"
		mkdir -p "$theme_share" "$lib/gtk-theme"
		cp -a "$src/gtk-theme/." "$theme_share/"
		cp -a "$src/gtk-theme/." "$lib/gtk-theme/"
		_info "  overlaid gtk-theme/ (share + lib sibling)"
	elif [[ -d "$src/gtk-theme" ]]; then
		_info "  skip stub gtk-theme/ overlay"
	fi

	# Optional gtk-sync override (install.sh + prebuilt bins beside gtk-files)
	if [[ -d "$src/gtk-sync" && -f "$src/gtk-sync/install.sh" ]] && ! _is_stub_only "$src/gtk-sync"; then
		rm -rf "$lib/gtk-sync"
		cp -a "$src/gtk-sync" "$lib/gtk-sync"
		chmod 0755 "$lib/gtk-sync/install.sh" "$lib/gtk-sync/uninstall.sh" 2>/dev/null || true
		_info "  overlaid gtk-sync/"
	elif [[ -d "$src/gtk-sync" ]]; then
		_info "  skip stub gtk-sync/ overlay"
	fi

	if [[ -d "$src/skel-config" ]]; then
		local skel_gtk="$INCLUDES/etc/skel/.config/gtk-apps"
		mkdir -p "$skel_gtk"
		cp -a "$src/skel-config/." "$skel_gtk/"
		_info "  overlaid skel-config/ → etc/skel/.config/gtk-apps"
	fi

	_info "staged $count additional/override gtk-apps binary(ies)"
}

# ---------------------------------------------------------------------------
# default/{install,hooks} + personalize/{install,hooks}: default first, same
# basename in personalize clobbers. *.example / meta names skipped.
# ---------------------------------------------------------------------------
_repo_default_root() {
	# share/ → Build/
	cd "$SCRIPT_DIR/.." && pwd
}

# Copy *.sh from src_dir into dest_dir (overwrite). Sets COPY_SH_COUNT.
_copy_sh_scripts() {
	local src_dir="$1" dest_dir="$2" label="$3"
	local f base n=0
	COPY_SH_COUNT=0
	[[ -d "$src_dir" ]] || return 0
	mkdir -p "$dest_dir"
	shopt -s nullglob
	for f in "$src_dir"/*.sh; do
		base="$(basename "$f")"
		_is_meta_name "$base" && continue
		cp -a "$f" "$dest_dir/$base"
		chmod 0755 "$dest_dir/$base"
		n=$((n + 1))
		_info "  $label/$base → ${dest_dir#"$INCLUDES"/}/$base"
	done
	shopt -u nullglob
	COPY_SH_COUNT=$n
}

_calamares_append_install_cmd() {
	local conf="$1" cmd="$2" base="$3"
	[[ -f "$conf" ]] || return 0
	grep -qF "personalize-install/$base" "$conf" 2>/dev/null && return 0
	python3 - "$conf" "$cmd" <<'PY'
import sys
from pathlib import Path
conf, cmd = Path(sys.argv[1]), sys.argv[2]
text = conf.read_text()
needle = '    - command: "/usr/share/neuronix/install-google-chrome.sh"\n'
line = f'    - command: "{cmd}"\n'
if line in text:
    raise SystemExit(0)
if needle in text:
    text = text.replace(needle, needle + line, 1)
else:
    marker = "  server:\n"
    if marker not in text:
        raise SystemExit(f"merge-install-scripts: cannot patch {conf}")
    text = text.replace(marker, line + marker, 1)
conf.write_text(text)
PY
	_info "  Calamares Desktop += personalize-install/$base"
}

# Calamares Desktop: /usr/share/neuronix/personalize-install/*.sh
merge_install_scripts() {
	local default_root pers_root dest conf
	default_root="$(_repo_default_root)/default/install"
	pers_root=""
	[[ -d "${PERSONALIZE:-}" ]] && pers_root="$PERSONALIZE/install"
	dest="$INCLUDES/usr/share/neuronix/personalize-install"
	conf="$INCLUDES/etc/calamares/modules/contextualprocess_neuronix_desktop.conf"

	mkdir -p "$dest"
	local n_def=0 n_pers=0
	_copy_sh_scripts "$default_root" "$dest" "default/install"
	n_def=$COPY_SH_COUNT
	if [[ -n "$pers_root" ]]; then
		_copy_sh_scripts "$pers_root" "$dest" "personalize/install"
		n_pers=$COPY_SH_COUNT
	fi

	# Wire every staged script into Calamares Desktop (sorted).
	local f base count=0
	local -a staged=()
	shopt -s nullglob
	staged=("$dest"/*.sh)
	shopt -u nullglob
	if ((${#staged[@]} > 0)); then
		mapfile -t staged < <(printf '%s\n' "${staged[@]}" | sort)
		for f in "${staged[@]}"; do
			[[ -f "$f" ]] || continue
			base="$(basename "$f")"
			_calamares_append_install_cmd "$conf" "/usr/share/neuronix/personalize-install/$base" "$base"
			count=$((count + 1))
		done
	fi

	if [[ "$n_def" -gt 0 || "$n_pers" -gt 0 || "$count" -gt 0 ]]; then
		_info "staged install scripts (default=$n_def personalize=$n_pers calamares=$count)"
	fi
}

# First-login user hooks: /usr/share/neuronix/user-hooks/*.sh
merge_user_hooks() {
	local default_root pers_root dest
	default_root="$(_repo_default_root)/default/hooks"
	pers_root=""
	[[ -d "${PERSONALIZE:-}" ]] && pers_root="$PERSONALIZE/hooks"
	dest="$INCLUDES/usr/share/neuronix/user-hooks"

	mkdir -p "$dest"
	local n_def=0 n_pers=0
	_copy_sh_scripts "$default_root" "$dest" "default/hooks"
	n_def=$COPY_SH_COUNT
	if [[ -n "$pers_root" ]]; then
		_copy_sh_scripts "$pers_root" "$dest" "personalize/hooks"
		n_pers=$COPY_SH_COUNT
	fi

	if [[ "$n_def" -gt 0 || "$n_pers" -gt 0 ]]; then
		_info "staged user-hooks (default=$n_def personalize=$n_pers)"
	fi
}

# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------
mkdir -p "$INCLUDES"
# Stock default/{configs,services,install,hooks} always considered; personalize overlays when present.
merge_configs
merge_services
# install/ + hooks/ merge default even without personalize/
merge_install_scripts
merge_user_hooks
if [[ ! -d "$PERSONALIZE" ]]; then
	_info "no personalize/ at $PERSONALIZE — skipped personalize-only drop-ins"
	_info "done"
	exit 0
fi

merge_browser_extensions
merge_gtk_apps
_info "done"
