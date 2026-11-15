"""Files on the machine the Workbench runs on: browse, upload, download as .zip.

On someone's own computer the Workbench opens the operating system's file
picker, and the files are right there. On a server the browser is on another
computer: no native picker can open, the inputs may still be on the laptop,
and the results are wanted back on it. So the page can also

* browse the server's folders itself (``browse``), the picker drawn in the
  page instead of by the operating system;
* upload files into a fresh folder on the server (``parse_upload``), streamed
  to disk so a folder of VCFs never sits in memory;
* download a whole results folder as one .zip (``archive_plan`` and
  ``archive_write``).

Only the standard library is used.
"""

from __future__ import annotations

import os
import re
import sys
import time
import zipfile
from pathlib import Path

MAX_LISTING = 500          # a folder of 100k VCFs should not become 100k rows
MAX_UPLOAD = 8 << 30       # 8 GB, which is a folder of VCFs, not a typo
CHUNK = 1 << 16
WINDOWS = sys.platform == "win32"

# What the picker marks, so an input or a results folder can be seen without
# opening it. The extensions SigProfilerMatrixGenerator reads (inputs.py).
_CALLS = (".vcf", ".vcf.gz", ".maf", ".genome")
_RESERVED = re.compile(r"^(con|prn|aux|nul|com[0-9]|lpt[0-9])$", re.IGNORECASE)
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


class FilesError(ValueError):
    pass


# ------------------------------------------------------------------ browse

def _hidden(entry: os.DirEntry) -> bool:
    """A leading dot on macOS and Linux; the hidden or system attribute on
    Windows, which keeps $Recycle.Bin and the like out of a drive's listing."""
    if entry.name.startswith("."):
        return True
    if not WINDOWS:
        return False
    try:
        attrs = entry.stat(follow_symlinks=False).st_file_attributes
    except (OSError, AttributeError):
        return False
    return bool(attrs & 0x6)        # FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM


def drives() -> list[str]:
    """The drive roots the picker can switch between (Windows only: "up"
    stops at the top of a drive there). Read from the drive bitmask rather
    than by probing letters, which can stall on an empty card reader."""
    if not WINDOWS:
        return []
    try:
        import ctypes
        mask = ctypes.windll.kernel32.GetLogicalDrives()
    except (ImportError, AttributeError, OSError):
        return []
    return [f"{chr(65 + i)}:\\" for i in range(26) if mask >> i & 1]


def _looks_like_results(folder: Path) -> bool:
    try:
        return ((folder / "JOB_METADATA.txt").is_file()
                or any((folder / name / "All_Solutions").is_dir()
                       for name in ("SBS96", "DBS78", "ID83", "CNV48", "SV32")))
    except OSError:
        return False


def _file_hint(name: str) -> str:
    low = name.lower()
    if low.endswith(_CALLS):
        return "calls"
    if ".bedpe" in low:
        return "bedpe"
    if low.endswith((".all", ".tsv", ".txt")) and re.search(r"\.(sbs|dbs|id|cnv|sv)\d+\.", low):
        return "matrix"
    return ""


def browse(path) -> dict:
    """One folder's listing for the in-page picker: folders first, then files
    with their size, each tagged with a cheap guess at what it holds."""
    p = Path(str(path)).expanduser()
    if not p.is_absolute():
        raise FilesError(f"not a full path: {p}")
    # A file, or a folder that does not exist yet (a planned output folder),
    # opens the nearest folder that does.
    while not p.is_dir() and p.parent != p:
        p = p.parent
    if not p.is_dir():
        raise FilesError(f"no such folder: {path}")
    p = p.resolve()
    entries, truncated = [], False
    try:
        with os.scandir(p) as it:
            items = sorted(it, key=lambda e: (not e.is_dir(), e.name.lower()))
    except PermissionError as exc:
        raise FilesError(f"permission denied: {p}") from exc
    for e in items:
        if _hidden(e):
            continue
        if len(entries) >= MAX_LISTING:
            truncated = True
            break
        try:
            is_dir = e.is_dir()
        except OSError:
            continue
        item = {"name": e.name, "dir": is_dir, "path": str(Path(e.path))}
        if is_dir:
            item["hint"] = "results" if _looks_like_results(Path(e.path)) else ""
        else:
            try:
                item["bytes"] = e.stat().st_size
            except OSError:
                item["bytes"] = None
            item["hint"] = _file_hint(e.name)
        entries.append(item)
    return {"path": str(p), "parent": str(p.parent) if p.parent != p else None,
            "entries": entries, "truncated": truncated, "drives": drives()}


# ------------------------------------------------------------------ upload

def safe_name(filename: str) -> str:
    """The last path component only, with anything surprising replaced.

    Browsers send a bare name for a file input. Only the final component may
    become a file here, and it may not be '.', '..', empty, or a name Windows
    keeps for a device.
    """
    base = str(filename).replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = _UNSAFE.sub("_", base).strip("._") or "upload"
    stem = cleaned.split(".", 1)[0]
    if _RESERVED.match(stem):
        cleaned = stem + "_" + cleaned[len(stem):]
    return cleaned


def new_upload_folder(root, kind: str) -> Path:
    """A folder no earlier upload used, so files from two uploads never mix
    (a folder of variant calls is read whole)."""
    root = Path(root)
    base = f"{_UNSAFE.sub('_', kind) or 'upload'}_{time.strftime('%Y%m%d-%H%M%S')}"
    for n in range(1, 1000):
        folder = root / (base if n == 1 else f"{base}_{n}")
        try:
            folder.mkdir(parents=True, exist_ok=False)
            return folder
        except FileExistsError:
            continue
    raise FilesError("could not make a new upload folder")


def _boundary(content_type: str) -> bytes:
    m = re.search(r'boundary="?([^";]+)"?', content_type or "")
    if not m:
        raise FilesError("multipart request has no boundary")
    return m.group(1).encode("latin-1")


class _Body:
    """The request body, read in chunks: never more than one buffer in memory."""

    def __init__(self, fh, length: int, limit: int):
        self.fh, self.remaining, self.limit = fh, int(length), int(limit)
        self.read_total = 0
        self.buf = b""

    def _fill(self) -> bool:
        if self.remaining <= 0:
            return False
        chunk = self.fh.read(min(CHUNK, self.remaining))
        if not chunk:
            self.remaining = 0
            return False
        self.remaining -= len(chunk)
        self.read_total += len(chunk)
        if self.read_total > self.limit:
            raise FilesError(f"the upload is larger than the {self.limit >> 30} GB limit")
        self.buf += chunk
        return True

    def read_exact(self, n: int) -> bytes:
        while len(self.buf) < n:
            if not self._fill():
                raise FilesError("the upload ended early")
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def read_until(self, token: bytes, cap: int = 1 << 20) -> bytes:
        while token not in self.buf:
            if len(self.buf) > cap:
                raise FilesError("multipart header is implausibly long")
            if not self._fill():
                raise FilesError("the upload ended early")
        i = self.buf.index(token)
        out, self.buf = self.buf[:i], self.buf[i + len(token):]
        return out

    def stream_until(self, token: bytes, sink) -> None:
        """Hand everything before ``token`` to ``sink`` a chunk at a time. The
        tail is held back because the token may straddle two reads."""
        keep = len(token)
        while True:
            i = self.buf.find(token)
            if i >= 0:
                if i:
                    sink(self.buf[:i])
                self.buf = self.buf[i + len(token):]
                return
            if len(self.buf) > keep:
                sink(self.buf[:-keep])
                self.buf = self.buf[-keep:]
            if not self._fill():
                raise FilesError("the upload ended early")


def _disposition(headers: bytes) -> tuple:
    text = headers.decode("utf-8", "replace")
    name = re.search(r'name="([^"]*)"', text)
    filename = re.search(r'filename="([^"]*)"', text)
    return (name.group(1) if name else ""), (filename.group(1) if filename else None)


def parse_upload(fh, content_type: str, content_length: int, dest,
                 limit: int = MAX_UPLOAD) -> list:
    """Read one multipart/form-data request, writing each file into ``dest``.

    Returns the files written. A name that repeats gets a numeric suffix
    rather than replacing the earlier file. Each file is written as
    name.uploading and renamed when complete, so an interrupted upload never
    leaves a file that looks whole.
    """
    delim = b"--" + _boundary(content_type)
    body = _Body(fh, content_length, limit)
    body.read_until(delim)                      # skip the preamble
    dest = Path(dest)
    files, used = [], set()
    while True:
        sep = body.read_exact(2)
        if sep == b"--":
            break
        if sep != b"\r\n":
            raise FilesError("malformed multipart separator")
        _name, filename = _disposition(body.read_until(b"\r\n\r\n"))
        end = b"\r\n" + delim
        if not filename or not filename.strip():  # a plain field or an empty input
            body.stream_until(end, lambda _b: None)
            continue
        stem = safe_name(filename)
        final, n = stem, 2
        while final in used:
            root, dot, ext = stem.partition(".")
            final = f"{root}_{n}{dot}{ext}"
            n += 1
        used.add(final)
        target = dest / final
        partial = target.with_name(target.name + ".uploading")
        written = 0
        with open(partial, "wb") as out:
            def sink(chunk, _out=out):
                nonlocal written
                written += len(chunk)
                _out.write(chunk)
            body.stream_until(end, sink)
        os.replace(partial, target)
        files.append({"name": final, "original": filename, "bytes": written,
                      "path": str(target)})
    return files


# ------------------------------------------------------------------ download

SKIP_NAMES = {".DS_Store"}


def archive_contents(folder) -> list:
    """(file on disk, name inside the archive) for everything worth sending.
    Names start with the folder's own name, so unzipping makes one folder."""
    folder = Path(folder)
    out = []
    for p in sorted(folder.rglob("*")):
        if not p.is_file() or p.is_symlink():
            continue
        rel = p.relative_to(folder)
        if any(part.startswith(".") for part in rel.parts) or p.name in SKIP_NAMES:
            continue
        if p.name.endswith((".uploading", ".tmp")):
            continue
        out.append((p, str(Path(folder.name) / rel)))
    return out


def archive_plan(folder) -> dict:
    """What the archive would hold, without building it."""
    items = archive_contents(folder)
    total = 0
    for p, _ in items:
        try:
            total += p.stat().st_size
        except OSError:
            pass
    return {"files": len(items), "bytes": total, "name": Path(folder).name}


def archive_write(folder, dest) -> dict:
    """Build the archive at ``dest``.

    Built to a file rather than streamed, which costs a moment and some
    scratch space and buys a real Content-Length: the browser can then show
    progress and time left, and a failure happens before anything is sent.
    """
    folder, dest = Path(folder), Path(dest)
    items = archive_contents(folder)
    if not items:
        raise FilesError(f"{folder.name} has no files to download")
    dest.parent.mkdir(parents=True, exist_ok=True)
    written = skipped = 0
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=6,
                         allowZip64=True) as z:
        for p, name in items:
            try:
                z.write(p, name)
                written += 1
            except OSError:
                # a file that vanished mid-build costs that entry, not the archive
                skipped += 1
    return {"files": written, "skipped": skipped, "bytes": dest.stat().st_size}
