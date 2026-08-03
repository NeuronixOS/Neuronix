# personalize/services/

Drop-in services. Each `<ServiceName>/` is copied to
`/usr/local/lib/neuronix/services/<ServiceName>/`. Neuronix runs `install.sh`
inside the live-build chroot (`9930-neuronix-personalize-services.hook.chroot`).

Stock services ship from **`default/services/`** (e.g. `gtksync` Waybar helpers).
Personalize overlays the same tree — same folder name replaces the default.

## Example layout

```text
services/
  Remux/
    install.sh              # REQUIRED (preferred)
    remux.service
    remux.py                # your scripts/config
```

Environment when `install.sh` runs:

| Variable | Value |
|----------|--------|
| `cwd` | `/usr/local/lib/neuronix/services/<ServiceName>` |
| `NEURONIX_SERVICE_ROOT` | same |
| `NEURONIX_SERVICE_NAME` | `<ServiceName>` |

Must be executable, idempotent, and use `NEURONIX_SERVICE_ROOT` (never host-only paths).
In units, `__SCRIPT_DIR__` is a common placeholder for the staged root.

## Example `install.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT="${NEURONIX_SERVICE_ROOT:-$(cd "$(dirname "$0")" && pwd)}"
NAME="${NEURONIX_SERVICE_NAME:-$(basename "$ROOT")}"
UNIT_SRC=""
shopt -s nullglob
for u in "$ROOT"/*.service; do
	UNIT_SRC="$u"
	break
done
shopt -u nullglob

if [[ -z "$UNIT_SRC" ]]; then
	echo "[$NAME] no *.service to install" >&2
	exit 0
fi

UNIT_NAME="$(basename "$UNIT_SRC")"
if grep -qiE '^WantedBy=.*(graphical-session|default\.target)' "$UNIT_SRC"; then
	DEST_DIR=/etc/skel/.config/systemd/user
	WANTS_DIR="$DEST_DIR/default.target.wants"
	mkdir -p "$DEST_DIR" "$WANTS_DIR"
	sed -E -e "s#__SCRIPT_DIR__#${ROOT}#g" "$UNIT_SRC" >"$DEST_DIR/$UNIT_NAME"
	ln -sfn "../$UNIT_NAME" "$WANTS_DIR/$UNIT_NAME"
	echo "[$NAME] installed user unit $UNIT_NAME"
else
	DEST=/etc/systemd/system/$UNIT_NAME
	WANTS=/etc/systemd/system/multi-user.target.wants
	mkdir -p /etc/systemd/system "$WANTS"
	sed -E \
		-e "s#__SCRIPT_DIR__#${ROOT}#g" \
		-e '/^User=root[[:space:]]*$/b' \
		-e '/^User=[a-z][a-z0-9]*[[:space:]]*$/d' \
		"$UNIT_SRC" >"$DEST"
	if ! grep -qE '^WorkingDirectory=' "$DEST"; then
		sed -i "/^\[Service\]/a WorkingDirectory=${ROOT}" "$DEST"
	fi
	ln -sfn "/etc/systemd/system/$UNIT_NAME" "$WANTS/$UNIT_NAME"
	echo "[$NAME] installed system unit $UNIT_NAME"
fi
```

## Example `remux.service` (system)

```ini
[Unit]
Description=Remux helper
After=network.target

[Service]
Type=simple
ExecStart=__SCRIPT_DIR__/remux.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

User units: use `WantedBy=default.target` (or `graphical-session.target`) so the
example installer places them under `/etc/skel/.config/systemd/user/`.
