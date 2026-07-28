#!/bin/sh
# Enable Debian contrib + non-free (firmware, optional drivers). Safe to run repeatedly.

ensure_apt_i386() {
	if dpkg --print-foreign-architectures 2>/dev/null | grep -qx i386; then
		return 0
	fi
	dpkg --add-architecture i386
	echo "[ensure-apt] enabled foreign architecture i386 (required for steam-installer)"
	return 0
}

ensure_apt_contrib_nonfree() {
	_changed=0

	_patch_deb_line() {
		_line="$1"
		case "$_line" in
			\#*|"") printf '%s\n' "$_line"; return 0 ;;
			deb*|deb-src*) ;;
			*) printf '%s\n' "$_line"; return 0 ;;
		esac
		if printf '%s' "$_line" | grep -qE '[[:space:]]non-free([[:space:]]|$)'; then
			printf '%s\n' "$_line"
			return 0
		fi
		printf '%s\n' "$_line" | sed -E \
			's/([[:space:]])main([[:space:]]+non-free-firmware)/\1main contrib non-free\2/; t; s/([[:space:]])main([[:space:]]*$)/\1main contrib non-free non-free-firmware/; t; s/([[:space:]])main([[:space:]]+)/\1main contrib non-free\2/'
	}

	if [ -f /etc/apt/sources.list ]; then
		_tmp="$(mktemp)"
		# shellcheck disable=SC2162
		while IFS= read -r _line || [ -n "$_line" ]; do
			_new="$(_patch_deb_line "$_line")"
			printf '%s\n' "$_new" >>"$_tmp"
			[ "$_new" != "$_line" ] && _changed=1
		done </etc/apt/sources.list
		if [ "$_changed" -eq 1 ]; then
			cp -a /etc/apt/sources.list "/etc/apt/sources.list.bak.$(date +%Y%m%d%H%M%S)" 2>/dev/null || true
			mv "$_tmp" /etc/apt/sources.list
			echo "[ensure-apt-contrib-nonfree] updated /etc/apt/sources.list"
		else
			rm -f "$_tmp"
		fi
	fi

	for _deb822 in /etc/apt/sources.list.d/*.sources; do
		[ -f "$_deb822" ] || continue
		if grep -q '^Components:' "$_deb822" \
			&& grep '^Components:' "$_deb822" | grep -qE '(^|[[:space:]])non-free([[:space:]]|$)'; then
			continue
		fi
		if ! grep -q '^Components:' "$_deb822"; then
			continue
		fi
		cp -a "$_deb822" "${_deb822}.bak.$(date +%Y%m%d%H%M%S)" 2>/dev/null || true
		sed -i -E \
			'/^Components:/{
				s/[[:space:]]+non-free-firmware//g
				s/^Components:[[:space:]]*/Components: main contrib non-free non-free-firmware /
			}' \
			"$_deb822"
		_changed=1
		echo "[ensure-apt-contrib-nonfree] updated $_deb822"
	done

	return 0
}

ensure_apt_backports() {
	_suite="$(. /etc/os-release 2>/dev/null && printf '%s' "${VERSION_CODENAME:-trixie}")"
	[ -n "${_suite}" ] || _suite="trixie"
	_backports="${_suite}-backports"
	if [ -f /etc/apt/sources.list ] && ! grep -qE "[[:space:]]${_backports}[[:space:]]" /etc/apt/sources.list 2>/dev/null; then
		printf '\ndeb http://deb.debian.org/debian %s main contrib non-free non-free-firmware\n' "${_backports}" \
			>>/etc/apt/sources.list
		echo "[ensure-apt-backports] added ${_backports} to sources.list"
	fi
}
