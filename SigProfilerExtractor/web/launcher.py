"""Idempotent venv management and process lifecycle for the local dashboard.

Reached two different ways, matching SigProfilerPlotting's dashboard
launcher pattern:

* The double-click launcher scripts (``launch_web.sh`` / ``.command`` /
  ``.bat``) manage a private, repo-local virtualenv and must install/upgrade
  the package into it -- but only when something relevant changed, never on
  every launch. That is :func:`managed_main`.
* The ``sigprofilerextractor-web`` console script, installed by pip
  into whatever environment the user chose, where dependency resolution
  already happened at install time. That is :func:`main`.

Both share the same argument parser, the same pidfile-based ``--stop``, and
the same server start-up.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

_PACKAGING_FILES = ("setup.py", "pyproject.toml")


def _repo_root() -> Path:
    # SigProfilerExtractor/web/launcher.py -> .../web -> .../SigProfilerExtractor -> repo root
    return Path(__file__).resolve().parents[2]


def compute_fingerprint(repo_root: Path) -> str:
    """Hash everything that determines what needs to be installed."""
    hasher = hashlib.sha256()
    for name in _PACKAGING_FILES:
        candidate = repo_root / name
        if candidate.is_file():
            hasher.update(candidate.read_bytes())
    hasher.update(f"{sys.version_info.major}.{sys.version_info.minor}".encode("ascii"))
    return hasher.hexdigest()


def needs_install(repo_root: Path, fingerprint_path: Path, force: bool) -> bool:
    """Pure decision function: should an install run? (unit-testable without a real venv)"""
    if force:
        return True
    if not fingerprint_path.is_file():
        return True
    try:
        stored = fingerprint_path.read_text(encoding="utf-8").strip()
    except OSError:
        return True
    return stored != compute_fingerprint(repo_root)


def _fingerprint_path() -> Path:
    return Path(sys.prefix) / ".fingerprint"


def ensure_dependencies(repo_root: Path, force: bool = False) -> None:
    fingerprint_path = _fingerprint_path()
    if needs_install(repo_root, fingerprint_path, force):
        print("Installing the Workbench's dependencies (the first time takes a few minutes)...", flush=True)
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "-e", str(repo_root)],
            check=True,
        )
        fingerprint_path.write_text(compute_fingerprint(repo_root), encoding="utf-8")
    else:
        print("Dependencies already installed; skipping install.", flush=True)


def _state_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        directory = base / "SigProfilerExtractor"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
        directory = base / "sigprofilerextractor"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _pidfile() -> Path:
    return _state_dir() / "dashboard.pid"


def _lockfile() -> Path:
    return _state_dir() / "dashboard.lock"


def _read_pidfile(pidfile: Path) -> tuple[int, int, str] | None:
    if not pidfile.is_file():
        return None
    try:
        pid_text, port_text, token = pidfile.read_text(encoding="utf-8").strip().split(":", 2)
        return int(pid_text), int(port_text), token
    except (OSError, ValueError):
        return None


def _write_pidfile_atomic(pidfile: Path, pid: int, port: int, token: str) -> None:
    tmp = pidfile.with_name(pidfile.name + f".tmp{pid}")
    tmp.write_text(f"{pid}:{port}:{token}", encoding="utf-8")
    os.replace(tmp, pidfile)


def _is_process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _fetch_identity(port: int, timeout: float = 1.0) -> dict | None:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/identity", timeout=timeout
        ) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _verify_identity(pid: int, port: int, token: str) -> bool:
    identity = _fetch_identity(port)
    return bool(identity) and identity.get("pid") == pid and identity.get("token") == token


def _running_dashboard_url(pidfile: Path) -> str | None:
    existing = _read_pidfile(pidfile)
    if existing is None:
        return None
    pid, port, token = existing
    if _verify_identity(pid, port, token):
        return f"http://127.0.0.1:{port}/"
    pidfile.unlink(missing_ok=True)
    return None


def _remove_pidfile_if_matches(pidfile: Path, pid: int, port: int, token: str) -> None:
    if _read_pidfile(pidfile) == (pid, port, token):
        pidfile.unlink(missing_ok=True)


def _wait_for_identity_gone(port: int, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _fetch_identity(port) is None:
            return True
        time.sleep(0.05)
    return _fetch_identity(port) is None


def _acquire_startup_lock(timeout: float = 5.0) -> Path | None:
    lock_path = _lockfile()
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode("ascii"))
            os.close(fd)
            return lock_path
        except FileExistsError:
            try:
                holder_pid = int(lock_path.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                holder_pid = None
            if holder_pid is None or not _is_process_alive(holder_pid):
                lock_path.unlink(missing_ok=True)
                continue
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.05)


def stop_server() -> bool:
    """Stop the running dashboard, if any. Returns False only on a real failure."""
    pidfile = _pidfile()
    existing = _read_pidfile(pidfile)
    if existing is None:
        pidfile.unlink(missing_ok=True)
        print("No running Workbench found.", flush=True)
        return True
    pid, port, token = existing
    if not _verify_identity(pid, port, token):
        pidfile.unlink(missing_ok=True)
        print("No running Workbench found.", flush=True)
        return True
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/shutdown",
            data=b"{}",
            method="POST",
            headers={
                "Origin": f"http://127.0.0.1:{port}",
                "Content-Type": "application/json",
                "X-Dashboard-Token": token,
            },
        )
        urllib.request.urlopen(request, timeout=5.0)
    except (OSError, urllib.error.HTTPError) as exc:
        print(
            f"Could not stop the Workbench: {exc} "
            "(it may still be running -- the pidfile has been kept; try again).",
            flush=True,
        )
        return False

    if not _wait_for_identity_gone(port):
        print(
            f"Dashboard server (pid {pid}) did not confirm shutdown in time "
            "-- it may still be running; the pidfile has been kept.",
            flush=True,
        )
        return False

    lock_path = _acquire_startup_lock()
    if lock_path is None:
        print(
            f"Stopped the Workbench (pid {pid}); its pidfile will be "
            "cleaned up by the next launch.",
            flush=True,
        )
        return True
    try:
        _remove_pidfile_if_matches(pidfile, pid, port, token)
    finally:
        lock_path.unlink(missing_ok=True)
    print(f"Stopped the Workbench (pid {pid}).", flush=True)
    return True


def _run_server(no_launch: bool, volume: str | None = None) -> None:
    pidfile = _pidfile()
    lock_path = _acquire_startup_lock()
    if lock_path is None:
        print(
            "Another Workbench launch is already in progress; try again in a moment.",
            flush=True,
        )
        return
    try:
        existing_url = _running_dashboard_url(pidfile)
        if existing_url is not None:
            print(f"SigProfilerExtractor Workbench is already running at {existing_url}", flush=True)
            print("Run with --stop first if you want to restart it.", flush=True)
            return

        from .server import make_server  # deferred: requires the package to be importable

        server = make_server("127.0.0.1", 0, _state_dir() / "jobs", volume=volume)
        port = server.server_address[1]
        token = server.instance_token
        _write_pidfile_atomic(pidfile, os.getpid(), port, token)
    finally:
        lock_path.unlink(missing_ok=True)

    def _handle_term(signum, frame):
        raise SystemExit(0)

    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_term)

    url = f"http://127.0.0.1:{port}/"
    print(f"SigProfilerExtractor Workbench running at {url}", flush=True)
    print("Press Ctrl+C to stop, or run with --stop from another terminal.", flush=True)
    if not no_launch:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        server.manager.stop_all()
        server.server_close()
        cleanup_lock = _acquire_startup_lock()
        if cleanup_lock is not None:
            try:
                _remove_pidfile_if_matches(pidfile, os.getpid(), port, token)
            finally:
                cleanup_lock.unlink(missing_ok=True)


def _build_parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog, description="Launch the local SigProfilerExtractor Workbench."
    )
    parser.add_argument(
        "--no-launch", action="store_true", help="Start the server without opening a browser tab."
    )
    parser.add_argument(
        "--reinstall",
        action="store_true",
        help="Force a fresh dependency install even if the fingerprint matches.",
    )
    parser.add_argument(
        "--stop", action="store_true", help="Stop a running Workbench and exit."
    )
    parser.add_argument(
        "--volume",
        metavar="PATH",
        default=None,
        help="Folder of installed reference genomes and reference files (same as the --volume parameter).",
    )
    parser.add_argument("--ensure-deps-only", action="store_true", help=argparse.SUPPRESS)
    return parser


def managed_main(argv: list[str] | None = None) -> int:
    args = _build_parser("SigProfilerExtractor Workbench launcher").parse_args(argv)
    if args.stop:
        return 0 if stop_server() else 1
    if args.ensure_deps_only:
        ensure_dependencies(_repo_root(), force=args.reinstall)
        return 0
    ensure_dependencies(_repo_root(), force=args.reinstall)
    _run_server(no_launch=args.no_launch, volume=args.volume)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point for the installed ``sigprofilerextractor-web`` console script."""
    args = _build_parser("sigprofilerextractor-web").parse_args(argv)
    if args.stop:
        return 0 if stop_server() else 1
    if args.reinstall:
        print(
            "--reinstall has no effect for the installed console command; "
            "reinstall the package with pip directly.",
            flush=True,
        )
    _run_server(no_launch=args.no_launch, volume=args.volume)
    return 0


if __name__ == "__main__":
    sys.exit(managed_main())
