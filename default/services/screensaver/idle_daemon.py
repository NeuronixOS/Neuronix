#!/usr/bin/env python3
"""
Idle watcher — launch the GTK screensaver after a period without input.

Uses evdev to observe keyboard/mouse activity (requires read access to
/dev/input/event*; user should be in the ``input`` group).

Usage:
  idle_daemon.py
  idle_daemon.py --config ~/.config/neuronix-screensaver/config.ini
  idle_daemon.py --idle 30 --mode matrix    # override for testing
"""

from __future__ import annotations

import argparse
import configparser
import logging
import os
import select
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

try:
    import evdev
    from evdev import InputDevice, ecodes, list_devices
except ImportError:
    evdev = None  # type: ignore[assignment]

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = Path.home() / ".config" / "neuronix-screensaver" / "config.ini"
ACTIVITY_TYPES = frozenset(
    {
        ecodes.EV_KEY,
        ecodes.EV_REL,
        ecodes.EV_ABS,
        ecodes.EV_MSC,
    }
    if evdev
    else ()
)


def load_config(path: Path) -> tuple[int, str]:
    idle_seconds = 300
    mode = "clock"
    if path.is_file():
        cfg = configparser.ConfigParser()
        cfg.read(path)
        if cfg.has_section("idle"):
            idle_seconds = cfg.getint("idle", "seconds", fallback=idle_seconds)
        if cfg.has_section("screensaver"):
            mode = cfg.get("screensaver", "mode", fallback=mode).strip() or mode
    return idle_seconds, mode


def screensaver_command(mode: str) -> list[str]:
    return [sys.executable, str(SCRIPT_DIR / "screensaver.py"), "--mode", mode]


def session_env() -> dict[str, str]:
    """Environment for launching the GTK screensaver in the graphical session."""
    env = os.environ.copy()
    uid = os.getuid()
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{uid}")
    # User units often lack WAYLAND_DISPLAY; common Hyprland / wlroots default.
    env.setdefault("WAYLAND_DISPLAY", "wayland-0")
    env.setdefault("DISPLAY", ":0")
    return env


class IdleWatcher:
    def __init__(self, idle_seconds: int, cmd: list[str]):
        self.idle_seconds = max(1, idle_seconds)
        self.cmd = cmd
        self._lock = threading.Lock()
        self._last_activity = time.monotonic()
        self._running = True
        self._proc: subprocess.Popen | None = None
        self._devices: list[InputDevice] = []

    def stop(self) -> None:
        self._running = False
        proc = self._proc
        if proc is not None and proc.poll() is None:
            proc.terminate()

    def bump(self) -> None:
        with self._lock:
            self._last_activity = time.monotonic()

    def idle_for(self) -> float:
        with self._lock:
            return time.monotonic() - self._last_activity

    def screensaver_active(self) -> bool:
        proc = self._proc
        return proc is not None and proc.poll() is None

    def launch_screensaver(self) -> None:
        if self.screensaver_active():
            return
        try:
            self._proc = subprocess.Popen(
                self.cmd,
                env=session_env(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logging.info("screensaver started (pid %s)", self._proc.pid)
        except OSError as exc:
            logging.error("failed to start screensaver: %s", exc)

    def reap_screensaver(self) -> None:
        proc = self._proc
        if proc is None:
            return
        rc = proc.poll()
        if rc is None:
            return
        logging.info("screensaver exited (code %s)", rc)
        self._proc = None
        self.bump()

    def open_input_devices(self) -> int:
        if evdev is None:
            return 0
        opened = 0
        for path in list_devices():
            try:
                dev = InputDevice(path)
            except (OSError, PermissionError) as exc:
                logging.debug("skip %s: %s", path, exc)
                continue
            # Keyboards, mice, touchpads, tablets — not power buttons etc.
            caps = dev.capabilities(verbose=False)
            if ecodes.EV_KEY not in caps and ecodes.EV_REL not in caps and ecodes.EV_ABS not in caps:
                dev.close()
                continue
            self._devices.append(dev)
            opened += 1
            logging.info("watching input: %s (%s)", dev.name, path)
        return opened

    def input_thread(self) -> None:
        if not self._devices:
            return
        fds = {dev.fd: dev for dev in self._devices}
        while self._running:
            try:
                ready, _, _ = select.select(list(fds.keys()), [], [], 0.5)
            except OSError:
                break
            for fd in ready:
                dev = fds[fd]
                try:
                    for event in dev.read():
                        if event.type in ACTIVITY_TYPES:
                            self.bump()
                except (BlockingIOError, OSError):
                    continue

    def run(self) -> int:
        n = self.open_input_devices()
        if n == 0:
            logging.error(
                "no input devices opened — install python3-evdev and ensure "
                "your user is in the 'input' group, then log out and back in"
            )
            return 1

        thread = threading.Thread(target=self.input_thread, name="evdev-input", daemon=True)
        thread.start()
        logging.info("idle timeout: %ds", self.idle_seconds)

        while self._running:
            self.reap_screensaver()
            if not self.screensaver_active() and self.idle_for() >= self.idle_seconds:
                self.launch_screensaver()
            time.sleep(0.5)

        for dev in self._devices:
            try:
                dev.close()
            except OSError:
                pass
        return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Idle screensaver daemon")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"Config file (default: {DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "--idle",
        type=int,
        default=None,
        metavar="SEC",
        help="Override idle seconds from config",
    )
    parser.add_argument(
        "--mode",
        choices=("clock", "stars", "aurora", "matrix"),
        default=None,
        help="Override screensaver mode from config",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )
    args = parse_args(argv)

    if evdev is None:
        logging.error(
            "python3-evdev is required (sudo apt install python3-evdev)"
        )
        return 1

    idle_seconds, mode = load_config(args.config)
    if args.idle is not None:
        idle_seconds = args.idle
    if args.mode is not None:
        mode = args.mode

    watcher = IdleWatcher(idle_seconds, screensaver_command(mode))

    def on_signal(signum: int, _frame) -> None:
        logging.info("signal %s — stopping", signal.Signals(signum).name)
        watcher.stop()

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    return watcher.run()


if __name__ == "__main__":
    sys.exit(main())
