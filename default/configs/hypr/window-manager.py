#!/usr/bin/env python3
"""Stock Hyprland window helper (no named-output layout).

Workstation parking, overview, and monitor-specific rules belong in
personalize/configs/hypr/window-manager.py. ISO merge overlays that file onto
this one; the live session uses ~/.config/hypr/window-manager.py.
"""
from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    cmd = (argv[0] if argv else "").strip().lower()
    if cmd in ("-h", "--help", "help"):
        print(
            "Stock window-manager.py is a no-op.\n"
            "Add personalize/configs/hypr/window-manager.py to overlay a custom layout.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
