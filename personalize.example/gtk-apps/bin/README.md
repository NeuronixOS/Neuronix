# personalize/gtk-apps/bin/

Wrapper or single-file executables. Each file `bin/<name>` is staged to
`/usr/local/lib/neuronix/gtk-apps/<name>` with a symlink at `/usr/local/bin/<name>`.

## Example `bin/my-tool`

```bash
#!/usr/bin/env bash
set -euo pipefail
SCRIPT="$(readlink -f "$0")"
LIB="$(cd "$(dirname "$SCRIPT")" && pwd)"
APP="$LIB/apps/my-tool"
exec "$APP/my-tool" "$@"
```

For a self-contained binary, place the executable directly as `bin/my-tool`
(no `apps/` tree required).
