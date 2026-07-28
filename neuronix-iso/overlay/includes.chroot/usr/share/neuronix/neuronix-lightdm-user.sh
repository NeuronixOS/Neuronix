# Shared helpers for LightDM autologin user paths (sourced by enable-* scripts as root).

neuronix_lightdm_autologin_user() {
	_u=""
	for _f in /etc/lightdm/lightdm.conf /etc/lightdm/lightdm.conf.d/*.conf; do
		[ -f "$_f" ] || continue
		_u="$(grep -h '^autologin-user=' "$_f" 2>/dev/null | tail -n 1 | cut -d= -f2- | tr -d ' ')"
		[ -n "$_u" ] && break
	done
	if [ -z "$_u" ]; then
		_u="$(getent passwd | awk -F: '$3 >= 1000 && $3 < 65534 { print $1; exit }')"
	fi
	printf '%s\n' "$_u"
}

neuronix_lightdm_user_home() {
	_u="$(neuronix_lightdm_autologin_user)"
	[ -n "$_u" ] || return 1
	getent passwd "$_u" | cut -d: -f6
}
