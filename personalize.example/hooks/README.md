# personalize/hooks/

Scripts run **once** as the desktop user on the first Hyprland login after install
(not on the live ISO). Stock scripts live in `default/hooks/`; the same basename
under `personalize/hooks/` **replaces** the default copy.

Merged to `/usr/share/neuronix/user-hooks/`. Runner:
`neuronix-run-user-hooks.sh` → log `~/.local/state/neuronix/user-hooks.log`,
stamp `~/.local/state/neuronix/user-hooks.done` (delete stamp to re-run).

Use for **user** setup (`git config`, dconf, …). Use `personalize/install/` for
**root** Calamares Desktop steps.

## Example `git-meld.sh`

```sh
#!/bin/sh
# First-login: use Neuronix gtk-meld as git diff/merge tool.
set -eu

command -v git >/dev/null 2>&1 || exit 0

MELD=/usr/local/lib/neuronix/gtk-apps/apps/gtk-meld/gtk-meld
if [ ! -x "$MELD" ]; then
	MELD="$(command -v gtk-meld 2>/dev/null || true)"
fi
[ -n "${MELD:-}" ] && [ -x "$MELD" ] || exit 0

git config --global diff.tool meld
git config --global difftool.meld.cmd "$MELD \"\$LOCAL\" \"\$REMOTE\""
git config --global difftool.prompt false
git config --global merge.tool meld
git config --global mergetool.meld.cmd "$MELD \"\$LOCAL\" \"\$REMOTE\""
git config --global mergetool.keepBackup false
```

```bash
# In private personalize/:
install -m 0755 /dev/stdin personalize/hooks/git-meld.sh <<'EOF'
# …paste script above…
EOF
```
