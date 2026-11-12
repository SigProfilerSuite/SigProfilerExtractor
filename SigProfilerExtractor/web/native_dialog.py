"""Open the operating system's own file/folder picker.

A browser page cannot hand a server a real filesystem path (the File API
only exposes file contents, not locations), so when the user needs to point
the dashboard at an existing folder or file on this machine, the server
opens a native dialog instead of asking the page to fake one.

The title is never written into script text: AppleScript receives it as an
argument and PowerShell as an environment variable, so quotes or script
syntax in it are shown as text, not run.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

PICK = ("folder", "file")

_MAC_SCRIPTS = {
    "folder": "return POSIX path of (choose folder with prompt (item 1 of argv))",
    "file": "return POSIX path of (choose file with prompt (item 1 of argv))",
}

_WINDOWS_SCRIPTS = {
    "folder": (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "$f = New-Object System.Windows.Forms.FolderBrowserDialog;"
        "$f.Description = $env:SPE_DIALOG_TITLE;"
        "if ($f.ShowDialog() -eq 'OK') { Write-Output $f.SelectedPath }"
    ),
    "file": (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "$f = New-Object System.Windows.Forms.OpenFileDialog;"
        "$f.Title = $env:SPE_DIALOG_TITLE;"
        "if ($f.ShowDialog() -eq 'OK') { Write-Output $f.FileName }"
    ),
}


class DialogError(RuntimeError):
    pass


def _run(args: list[str], env: dict | None = None) -> str:
    try:
        completed = subprocess.run(
            args, capture_output=True, text=True, timeout=300, env=env
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DialogError(str(exc)) from exc
    return completed.stdout.strip()


def _macos(kind: str, title: str) -> str | None:
    args = ["osascript", "-e", "on run argv", "-e", _MAC_SCRIPTS[kind], "-e", "end run", title]
    return _run(args) or None


def _windows(kind: str, title: str) -> str | None:
    env = dict(os.environ, SPE_DIALOG_TITLE=title)
    args = ["powershell", "-NoProfile", "-NonInteractive", "-Command", _WINDOWS_SCRIPTS[kind]]
    return _run(args, env=env) or None


def _linux(kind: str, title: str) -> str | None:
    # Arguments go straight to the program (no shell), so the title is data.
    if shutil.which("zenity"):
        args = ["zenity", "--file-selection", f"--title={title}"]
        if kind == "folder":
            args.append("--directory")
        return _run(args) or None
    if shutil.which("kdialog"):
        args = ["kdialog", "--title", title,
                "--getexistingdirectory" if kind == "folder" else "--getopenfilename"]
        return _run(args) or None
    try:
        import tkinter
        import tkinter.filedialog
    except ImportError as exc:
        raise DialogError(
            "no native file picker available (install zenity, kdialog, or "
            "a tkinter-enabled Python)"
        ) from exc
    root = tkinter.Tk()
    root.withdraw()
    try:
        if kind == "folder":
            selected = tkinter.filedialog.askdirectory(title=title)
        else:
            selected = tkinter.filedialog.askopenfilename(title=title)
    finally:
        root.destroy()
    return selected or None


def choose(kind: str, title: str = "Choose a location") -> str | None:
    """Open a native folder/file picker. Returns the chosen path, or None if cancelled."""
    if kind not in PICK:
        raise DialogError(f"kind must be one of {PICK}, got {kind!r}")
    title = str(title)
    if sys.platform == "darwin":
        return _macos(kind, title)
    if sys.platform == "win32":
        return _windows(kind, title)
    return _linux(kind, title)
