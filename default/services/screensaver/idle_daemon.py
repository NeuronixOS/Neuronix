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
    }
    if evdev
    else ()
)

# Synthetic / firmware nodes that fire without a person at the desk.
# Active-User jiggles the pointer via ydotoold about once a second — that
# must not count as user activity or the screensaver never starts.
SKIP_NAME_SUBSTR = (
    "ydotool",
    "uinput",
    "virtual device",
    "video bus",
    "power button",
    "sleep button",
    "intel hid",
    "wmi hotkey",
    "hd audio",
    "pc speaker",
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
    runtime = Path(env.get("XDG_RUNTIME_DIR") or f"/run/user/{uid}")
    env.setdefault("XDG_RUNTIME_DIR", str(runtime))
    display = env.get("WAYLAND_DISPLAY", "")
    socket = runtime / display if display else None
    if not display or not socket or not socket.exists():
        for path in sorted(runtime.glob("wayland-*")):
            if path.is_socket() and not path.name.endswith(".lock"):
                env["WAYLAND_DISPLAY"] = path.name
                break
        else:
            env.setdefault("WAYLAND_DISPLAY", "wayland-1")
    env.setdefault("DISPLAY", ":0")
    return env


def skip_device_name(name: str) -> bool:
    lower = name.lower()
    return any(part in lower for part in SKIP_NAME_SUBSTR)


def is_keyboard_or_pointer(dev: InputDevice) -> bool:
    """True for real keyboards, mice, and touchpads — not LED/hotkey-only nodes."""
    caps = dev.capabilities(verbose=False)
    keys = set(caps.get(ecodes.EV_KEY, ()))
    rels = set(caps.get(ecodes.EV_REL, ()))
    abses = set(caps.get(ecodes.EV_ABS, ()))
    if ecodes.KEY_A in keys or ecodes.KEY_ENTER in keys:
        return True
    if ecodes.REL_X in rels or ecodes.REL_Y in rels:
        return True
    if ecodes.ABS_X in abses and (
        ecodes.BTN_LEFT in keys
        or ecodes.BTN_TOUCH in keys
        or ecodes.BTN_TOOL_FINGER in keys
    ):
        return True
    return False


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

    def _close_dev(self, fds: dict[int, InputDevice], fd: int, reason: str) -> None:
        """Unplug / hangup: drop the fd so select() cannot busy-loop on it."""
        dev = fds.pop(fd, None)
        if dev is None:
            return
        logging.info(
            "stop watching %s (%s): %s",
            getattr(dev, "name", "?"),
            getattr(dev, "path", "?"),
            reason,
        )
        try:
            dev.close()
        except OSError:
            pass
        try:
            self._devices.remove(dev)
        except ValueError:
            pass

    def _open_one(self, path: str, fds: dict[int, InputDevice] | None) -> bool:
        watched = {dev.path for dev in (fds.values() if fds is not None else self._devices)}
        if path in watched:
            return False
        try:
            dev = InputDevice(path)
        except (OSError, PermissionError) as exc:
            logging.debug("skip %s: %s", path, exc)
            return False
        if skip_device_name(dev.name):
            logging.info("ignore synthetic/firmware: %s (%s)", dev.name, path)
            dev.close()
            return False
        if not is_keyboard_or_pointer(dev):
            logging.debug("ignore non-pointer/keyboard: %s (%s)", dev.name, path)
            dev.close()
            return False
        self._devices.append(dev)
        if fds is not None:
            fds[dev.fd] = dev
        logging.info("watching input: %s (%s)", dev.name, path)
        return True

    def open_input_devices(self) -> int:
        if evdev is None:
            return 0
        opened = 0
        for path in list_devices():
            if self._open_one(path, None):
                opened += 1
        return opened

    def input_thread(self) -> None:
        fds = {dev.fd: dev for dev in self._devices}
        last_scan = time.monotonic()
        while self._running:
            now = time.monotonic()
            if now - last_scan >= 2.0:
                if evdev is not None:
                    for path in list_devices():
                        self._open_one(path, fds)
                last_scan = now
            if not fds:
                time.sleep(0.5)
                continue
            try:
                ready, _, _ = select.select(list(fds.keys()), [], [], 0.5)
            except OSError:
                for fd in list(fds):
                    try:
                        os.fstat(fd)
                    except OSError:
                        self._close_dev(fds, fd, "invalid fd")
                continue
            for fd in ready:
                if fd not in fds:
                    continue
                try:
                    for event in fds[fd].read():
                        if event.type in ACTIVITY_TYPES:
                            self.bump()
                except BlockingIOError:
                    continue
                except OSError as exc:
                    self._close_dev(fds, fd, str(exc))

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
