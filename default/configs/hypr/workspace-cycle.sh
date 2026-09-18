#!/bin/sh
# Cycle workspaces on the focused monitor (wrap). Personalize may replace this.
# Usage: workspace-cycle.sh [+1|-1] [move]
set -eu
dir="${1:-+1}"
move="${2:-}"

python3 - "$dir" "$move" <<'PY'
import json, subprocess, sys

dir_, move = sys.argv[1], sys.argv[2]


def hypr(*args: str) -> str:
    return subprocess.check_output(["hyprctl", *args], text=True)


try:
    monitors = json.loads(hypr("monitors", "-j"))
except Exception:
    raise SystemExit(0)

mon = next((m for m in monitors if m.get("focused")), monitors[0] if monitors else None)
if not mon:
    raise SystemExit(0)

aws = mon.get("activeWorkspace") or {}
try:
    cur = int(aws.get("id") or 0)
except (TypeError, ValueError):
    raise SystemExit(0)

try:
    workspaces = json.loads(hypr("workspaces", "-j"))
except Exception:
    raise SystemExit(0)

ids = sorted(
    {
        int(w["id"])
        for w in workspaces
        if w.get("monitor") == mon.get("name")
        and not str(w.get("name") or "").startswith("special")
        and str(w.get("id", "")).lstrip("-").isdigit()
    }
)
if cur and cur not in ids:
    ids = sorted(set(ids) | {cur})
if not ids:
    raise SystemExit(0)

i = ids.index(cur) if cur in ids else 0
step = 1 if dir_ in ("+1", "next", "1") else -1
nxt = ids[(i + step) % len(ids)]
argv = ["hyprctl", "dispatch"]
if move == "move":
    argv += ["movetoworkspace", str(nxt)]
else:
    argv += ["workspace", str(nxt)]
subprocess.run(argv, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
PY
