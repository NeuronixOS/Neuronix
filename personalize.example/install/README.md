# personalize/install/

Scripts run during **Calamares Desktop** install (target chroot), after Chrome.
Stock scripts may live in `default/install/`; the same basename under
`personalize/install/` **replaces** the default.

Merged to `/usr/share/neuronix/personalize-install/` and appended to
`contextualprocess_neuronix_desktop.conf`.

## Example `cursor.sh`

Cursor is **not** a stock Desktop package — add this only when you want it:

```sh
#!/bin/sh
# Install Cursor IDE during Calamares Desktop install.
set -eu
if [ -x /usr/share/neuronix/install-cursor.sh ]; then
	exec /usr/share/neuronix/install-cursor.sh "$@"
fi
echo "[personalize-install/cursor] missing /usr/share/neuronix/install-cursor.sh" >&2
exit 1
```

```bash
install -m 0755 /dev/stdin personalize/install/cursor.sh <<'EOF'
# …paste script above…
EOF
```
