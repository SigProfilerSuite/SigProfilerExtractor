"""Serve the SigProfilerExtractor Workbench from a server (a cluster node, a
container) to the browser on another computer.

The Workbench (SigProfilerExtractor/web/server.py) is built for one person on
their own computer: it binds 127.0.0.1, has no login, and refuses any request
whose Host or Origin is not this machine. On a server the browser is on a
laptop, so this wrapper runs the very same server and handler, but:

* binds 0.0.0.0, and admits a request only with this job's token (given once
  as ?token=..., or typed on /gateway/login, then kept in an HttpOnly cookie),
  the same model as a Jupyter server;
* after that check, rewrites Host (and a same-origin Origin) to the loopback
  address, so the Workbench's own Host/Origin/token checks still run unchanged
  and still refuse cross-site actions;
* adds what a remote browser needs and a local one does not: uploading files
  to the server, and downloading a whole results folder as one .zip
  (/gateway/). The native file picker cannot open on a headless node, so it
  is answered with a pointer to that page instead.

Run it with the Workbench's own interpreter (it imports the installed
package); run_workbench.sbatch does that. The token comes from the
SPE_GATEWAY_TOKEN environment variable, never argv, which other users on the
node can read with ps.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import os
import re
import secrets
import signal
import shutil
import socket
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse

import psutil  # a SigProfilerExtractor dependency, so always in the venv
from SigProfilerExtractor.web import server as workbench
from SigProfilerExtractor.web.launcher import _state_dir

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
# Added to the Workbench's page: the job-resources pill (filled by status.js)
# and the link to the upload/download page, fixed at the bottom right.
LAUNCHER_LINK = (
    '<link rel="stylesheet" href="/gateway/status.css">'
    '<div id="spe-gw"><a class="spe-gw-files" href="/gateway/" target="_blank" rel="noopener" '
    'title="Upload inputs to the server, download results as .zip">Upload &amp; download</a></div>'
    '<script src="/gateway/status.js" defer></script>'
)
GATEWAY_FILES = ("files.js", "files.css", "status.js", "status.css")
NO_PICKER = (
    "There is no file browser on the server. Paste a path on the server instead, or "
    "upload your files first with Upload & download (bottom right), which shows the "
    "path to paste."
)


class GatewayHandler(workbench.Handler):
    """The Workbench's handler, behind a token check and the gateway routes."""

    # ------------------------------------------------------------ access

    def _cookie_name(self) -> str:
        # Browsers share cookies across ports, so name it after this port.
        return f"spe_gateway_{self.server.server_address[1]}"

    def _has_cookie(self) -> bool:
        for part in (self.headers.get("Cookie") or "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == self._cookie_name():
                return secrets.compare_digest(value, self.server.gateway_token)
        return False

    def _set_cookie_and_go(self, target: str) -> None:
        self.send_response(303)
        self.send_header("Location", target)
        self.send_header(
            "Set-Cookie",
            f"{self._cookie_name()}={self.server.gateway_token}; Path=/; HttpOnly; SameSite=Lax",
        )
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _same_origin(self) -> bool:
        origin = (self.headers.get("Origin") or "").lower()
        return origin == f"http://{(self.headers.get('Host') or '').lower()}"

    def _gate(self) -> bool:
        """True if the request may go on; otherwise it has been answered."""
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
        # None: any name or address (--public-host '*'), for a container that
        # cannot know how it is reached. The token check below still applies,
        # and the cookie is bound to the name the browser used.
        if self.server.public_hosts is not None and host not in self.server.public_hosts:
            self._fail("unknown host name", 403)
            return False
        url = urlparse(self.path)
        query = parse_qs(url.query)
        given = (query.get("token") or [""])[0]
        if self.command in ("GET", "HEAD") and given:
            if secrets.compare_digest(given, self.server.gateway_token):
                rest = urlencode([(k, v) for k, vs in query.items() if k != "token" for v in vs])
                self._set_cookie_and_go(url.path + (f"?{rest}" if rest else ""))
                return False
        if url.path == "/gateway/login":
            self._login()
            return False
        if self._has_cookie():
            return True
        if self.command in ("GET", "HEAD") and not url.path.startswith(("/api/", "/gateway/api/")):
            self.send_response(303)
            self.send_header("Location", "/gateway/login?next=" + quote(self.path, safe=""))
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            self._fail("not signed in: open the URL with the token first", 401)
        return False

    def _login(self) -> None:
        if self.command == "POST":
            length = int(self.headers.get("Content-Length") or 0)
            form = parse_qs(self.rfile.read(length).decode("utf-8", "replace"))
            token = (form.get("token") or [""])[0].strip()
            target = (form.get("next") or ["/"])[0]
            if not target.startswith("/") or target.startswith("//"):
                target = "/"
            if secrets.compare_digest(token, self.server.gateway_token):
                return self._set_cookie_and_go(target)
            time.sleep(1)  # slow down guessing
            return self._send(403, _login_page(target, wrong=True), "text/html; charset=utf-8")
        target = (parse_qs(urlparse(self.path).query).get("next") or ["/"])[0]
        return self._send(200, _login_page(target), "text/html; charset=utf-8")

    def _as_local(self) -> None:
        """Present an admitted request to the Workbench as if it came from this node."""
        local = f"127.0.0.1:{self.server.server_address[1]}"
        same = self._same_origin()
        had_origin = "Origin" in self.headers
        del self.headers["Host"]
        self.headers["Host"] = local
        if had_origin:
            del self.headers["Origin"]
            # A cross-site Origin stays foreign, so the Workbench refuses it.
            self.headers["Origin"] = f"http://{local}" if same else "null"

    # ------------------------------------------------------------ methods

    def do_GET(self):
        if not self._gate():
            return
        path = unquote(urlparse(self.path).path)
        if path == "/gateway" or path.startswith("/gateway/"):
            return self._guard(self._gateway_get, path, parse_qs(urlparse(self.path).query))
        self._as_local()
        return super().do_GET()

    def do_HEAD(self):
        self.do_GET()

    def do_POST(self):
        if not self._gate():
            return
        if unquote(urlparse(self.path).path) == "/api/dialog":
            return self._fail(NO_PICKER, 400)
        self._as_local()
        return super().do_POST()

    def do_PUT(self):
        if not self._gate():
            return
        if not self._same_origin():
            return self._fail("uploads must come from this app's own page", 403)
        path = unquote(urlparse(self.path).path)
        if path != "/gateway/api/upload":
            return self._fail("not found", 404)
        return self._guard(self._upload, parse_qs(urlparse(self.path).query))

    def _get(self, path: str, query: dict):
        if path in ("/", "/index.html"):
            page = (workbench.STATIC / "index.html").read_text(encoding="utf-8")
            page = page.replace(workbench.TOKEN_PLACEHOLDER, self.server.instance_token)
            page = page.replace("</body>", LAUNCHER_LINK + "</body>", 1)
            return self._send(200, page, "text/html; charset=utf-8",
                              {"Cache-Control": "no-store, must-revalidate"})
        return super()._get(path, query)

    def _start_run(self, settings: dict):
        # The Workbench accepts any CPU count; a run asking for more than this
        # job holds would oversubscribe it. The page caps the fields too
        # (status.js); this catches anything sent around the page.
        limit = self.server.resources.allowed_cpus
        problems = []
        for key, label in (("cpu", "CPUs for extraction"), ("assignment_cpu", "CPUs for assignment")):
            try:
                value = int(settings.get(key, -1))
            except (TypeError, ValueError):
                continue  # the Workbench's own validation reports it
            if value > limit:
                problems.append(f"{label} can be at most {limit}, the CPUs this job has "
                                "(leave it blank to use all of them).")
        if problems:
            return self._fail("The run cannot start yet: " + " ".join(problems), 400,
                              problems=problems)
        return super()._start_run(settings)

    def _guard(self, func, *args):
        try:
            return func(*args)
        except ConnectionError:
            self.close_connection = True
        except (ValueError, OSError) as exc:
            sys.stderr.write(f"  [400] {self.command} {self.path.split('?')[0]}: {exc}\n")
            self._fail(str(exc), 400)

    # ------------------------------------------------------------ gateway routes

    def _gateway_get(self, path: str, query: dict):
        if path in ("/gateway", "/gateway/"):
            return self._file(STATIC / "files.html")
        if path.startswith("/gateway/") and path[len("/gateway/"):] in GATEWAY_FILES:
            return self._file(STATIC / path[len("/gateway/"):])
        if path == "/gateway/api/resources":
            return self._json({"ok": True, **self.server.resources.snapshot()})
        if path == "/gateway/api/list":
            return self._json({"ok": True, "uploads_root": str(self.server.uploads),
                               "uploads": _folders(self.server.uploads),
                               "runs": _runs(self.server)})
        if path == "/gateway/api/zip":
            return self._zip(Path((query.get("path") or [""])[0]).expanduser())
        return self._fail("not found", 404)

    def _upload(self, query: dict):
        folder = (query.get("folder") or [""])[0]
        relative = (query.get("path") or [""])[0]
        if not SAFE_NAME.match(folder) or folder in (".", ".."):
            raise ValueError("folder names may use letters, digits, '.', '_' and '-' only")
        parts = relative.replace("\\", "/").split("/")
        if not relative or any(p in ("", ".", "..") or "\0" in p for p in parts):
            raise ValueError(f"bad file name: {relative!r}")
        length = self.headers.get("Content-Length")
        if length is None:
            raise ValueError("Content-Length is required")
        remaining = int(length)
        target = self.server.uploads / folder / Path(*parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(target.name + ".uploading")
        with open(partial, "wb") as out:
            while remaining:
                chunk = self.rfile.read(min(remaining, 1 << 20))
                if not chunk:
                    raise ConnectionError("upload interrupted")
                out.write(chunk)
                remaining -= len(chunk)
        os.replace(partial, target)
        return self._json({"ok": True, "path": str(target),
                           "folder": str(self.server.uploads / folder)})

    def _zip(self, root: Path):
        if not root.is_dir():
            raise ValueError(f"not a folder: {root}")
        root = root.resolve()
        name = root.name or "files"
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", f'attachment; filename="{name}.zip"')
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        # Streamed as it is built (zipfile handles an unseekable output), so a
        # large results folder starts downloading at once and is never staged.
        with zipfile.ZipFile(self.wfile, "w", zipfile.ZIP_DEFLATED,
                             compresslevel=1, allowZip64=True) as archive:
            for item in sorted(root.rglob("*")):
                if item.is_file() and not item.name.endswith(".uploading"):
                    archive.write(item, f"{name}/{item.relative_to(root)}")


# ------------------------------------------------------------------ resources

class Resources:
    """What this job was given and how much of it is in use, for the status panel.

    SLURM's environment says what was requested; the cpuset, the job's cgroup
    and nvidia-smi (all confined to this job) say what is actually in use;
    scontrol says how busy the rest of the node is.

    A sampler thread reads the fast-changing numbers (CPU load, job memory,
    each GPU's load and memory) every INTERVAL seconds and keeps the last
    KEEP samples, so the panel can draw recent trends the moment it opens.
    The slow ones (time left, how full the node is) come from squeue and
    scontrol at most every TTL seconds, however many tabs are polling.
    """

    INTERVAL = 2.0
    KEEP = 300  # 10 minutes
    TTL = 10.0

    def __init__(self):
        self._lock = threading.Lock()
        self._samples: collections.deque = collections.deque(maxlen=self.KEEP)
        self._slow: dict | None = None
        self._slow_at = 0.0
        self._cpus = sorted(os.sched_getaffinity(0))
        self.allowed_cpus = allowed_cpus()
        self._cgroup = cgroup_dir()
        self._cpu_usage = self._cgroup_cpu_usage()  # baselines: first readings
        self._cpu_usage_at = time.monotonic()
        psutil.cpu_percent(percpu=True)
        threading.Thread(target=self._sample_forever, name="resources", daemon=True).start()

    def _cgroup_cpu_usage(self) -> int | None:
        if self._cgroup is None:
            return None
        try:
            stat = dict(row.split() for row in (self._cgroup / "cpu.stat").read_text().splitlines())
            return int(stat["usage_usec"])
        except (OSError, ValueError, KeyError):
            return None

    def _cpu_busy(self) -> float | None:
        """Share of the allowed CPUs in use since the previous sample.

        From the cgroup's CPU time when there is one, which counts exactly
        this job or container even when its CPUs are shared (a docker --cpus
        quota); else the load of the CPUs in this process's CPU set.
        """
        usage, now = self._cgroup_cpu_usage(), time.monotonic()
        before, before_at = self._cpu_usage, self._cpu_usage_at
        self._cpu_usage, self._cpu_usage_at = usage, now
        per_cpu = psutil.cpu_percent(percpu=True)  # keeps its own interval current
        if usage is not None and before is not None and now > before_at:
            share = (usage - before) / 1e6 / (now - before_at) / self.allowed_cpus
            return round(max(0.0, min(1.0, share)) * 100, 1)
        busy = [per_cpu[i] for i in self._cpus if i < len(per_cpu)]
        return round(sum(busy) / len(busy), 1) if busy else None

    def _sample_forever(self) -> None:
        while True:
            time.sleep(self.INTERVAL)
            try:
                sample = self._sample()
            except Exception as exc:  # noqa: BLE001 - keep sampling whatever happens
                sys.stderr.write(f"  resources: sample failed: {exc}\n")
                continue
            with self._lock:
                self._samples.append(sample)

    def _sample(self) -> dict:
        # Both CPU readings cover the time since the previous sample: the
        # sampler's steady INTERVAL, which is why nothing else may take one.
        return {
            "t": round(time.time(), 1),
            "cpu": self._cpu_busy(),
            "mem": _memory_used(self._cgroup),
            "gpus": _gpus(),
        }

    def _measure_slow(self) -> dict:
        env = os.environ
        job = env.get("SLURM_JOB_ID")
        # SPE_HOST_NAME: the server's own name, which the launcher passes in
        # (a container's hostname is otherwise a random id).
        node = (env.get("SLURMD_NODENAME") or env.get("SPE_HOST_NAME")
                or socket.gethostname()).split(".")[0]
        mem_mb = env.get("SLURM_MEM_PER_NODE")
        if mem_mb is None and env.get("SLURM_MEM_PER_CPU"):
            mem_mb = int(env["SLURM_MEM_PER_CPU"]) * len(self._cpus)
        return {
            "job_id": job,
            "node": node,
            "time_left_seconds": _time_left(job),
            "node_usage": _node_usage(node) if job else None,
            "memory_allocated_bytes": (int(mem_mb) * 2**20 if mem_mb
                                       else _cgroup_memory_limit(self._cgroup)),
        }

    def snapshot(self) -> dict:
        with self._lock:
            if self._slow is None or time.monotonic() - self._slow_at > self.TTL:
                self._slow = self._measure_slow()
                self._slow_at = time.monotonic()
            if not self._samples:
                self._samples.append(self._sample())
            samples = list(self._samples)
            slow = dict(self._slow)
        now = samples[-1]
        gpu_history: dict[str, dict[str, list]] = {}
        for i, sample in enumerate(samples):
            for gpu in sample["gpus"]:
                series = gpu_history.setdefault(
                    str(gpu["index"]), {"busy": [None] * len(samples), "mem": [None] * len(samples)})
                series["busy"][i] = gpu["busy_percent"]
                series["mem"][i] = gpu["memory_used_bytes"]
        return {
            "job_id": slow["job_id"],
            "node": slow["node"],
            "time_left_seconds": slow["time_left_seconds"],
            "cpus": {
                "allocated": self.allowed_cpus,
                # os.cpu_count() follows PYTHON_CPU_COUNT; sysconf is the node.
                "node_total": os.sysconf("SC_NPROCESSORS_ONLN"),
                "busy_percent": now["cpu"],
            },
            "memory": {
                "allocated_bytes": slow["memory_allocated_bytes"],
                "used_bytes": now["mem"],
                "node_total_bytes": psutil.virtual_memory().total,
            },
            "gpus": now["gpus"],
            "node_usage": slow["node_usage"],
            "history": {
                "interval_seconds": self.INTERVAL,
                "t": [s["t"] for s in samples],
                "cpu": [s["cpu"] for s in samples],
                "mem": [s["mem"] for s in samples],
                "gpus": gpu_history,
            },
        }


def _run_quiet(args: list[str]) -> str | None:
    if not shutil.which(args[0]):
        return None
    try:
        done = subprocess.run(args, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout if done.returncode == 0 else None


def _time_left(job: str | None) -> int | None:
    # squeue %L: [days-]hours:minutes:seconds, or minutes:seconds.
    text = (_run_quiet(["squeue", "-h", "-j", job, "-o", "%L"]) or "").strip() if job else ""
    match = re.fullmatch(r"(?:(\d+)-)?(?:(\d+):)?(\d+):(\d+)", text)
    if not match:
        return None
    days, hours, minutes, seconds = (int(g or 0) for g in match.groups())
    return ((days * 24 + hours) * 60 + minutes) * 60 + seconds


def cgroup_dir() -> Path | None:
    """The cgroup (v2) holding exactly this app's resources, if there is one.

    In a SLURM job: the job's cgroup (job_N), shared by all its steps. In a
    container with its own cgroup namespace (Docker, Podman): the namespace
    root, which is the container. Anywhere else the cgroup is a whole login
    session, which says nothing about this app, so None.
    """
    try:
        lines = Path("/proc/self/cgroup").read_text().splitlines()
    except OSError:
        return None
    path = next((line[3:] for line in lines if line.startswith("0::")), None)
    if path is None:
        return None
    match = re.match(r"(.*/job_\d+)", path)
    if match:
        base = Path("/sys/fs/cgroup" + match.group(1))
    elif path == "/" and (Path("/.dockerenv").exists() or Path("/run/.containerenv").exists()):
        base = Path("/sys/fs/cgroup")
    else:
        return None
    return base if (base / "memory.current").is_file() else None


def allowed_cpus() -> int:
    """CPUs this app may use: its CPU set, capped by a cgroup CPU quota (docker --cpus)."""
    count = len(os.sched_getaffinity(0))
    base = cgroup_dir()
    if base is not None:
        try:
            quota, period = (base / "cpu.max").read_text().split()
            if quota != "max":
                count = min(count, max(1, math.ceil(int(quota) / int(period))))
        except (OSError, ValueError):
            pass
    return count


def _cgroup_memory_limit(base: Path | None) -> int | None:
    """A container's memory limit (docker --memory), if it has one."""
    if base is None:
        return None
    try:
        text = (base / "memory.max").read_text().strip()
    except OSError:
        return None
    return int(text) if text.isdigit() else None


def _memory_used(base: Path | None) -> int:
    """Memory in use by the whole job or container, else by this process tree.

    From the cgroup, the working set: memory.current less the inactive file
    cache, which the kernel reclaims at will (the measure docker stats and
    kubectl top use). memory.current alone counts every file the job read.
    """
    if base is not None:
        try:
            current = int((base / "memory.current").read_text())
            stat = dict(row.split() for row in (base / "memory.stat").read_text().splitlines())
            return max(0, current - int(stat.get("inactive_file", 0)))
        except (OSError, ValueError):
            pass
    me = psutil.Process()
    total = 0
    for proc in (me, *me.children(recursive=True)):
        try:
            total += proc.memory_info().rss
        except psutil.Error:
            pass
    return total


def _gpus() -> list[dict]:
    text = _run_quiet(["nvidia-smi", "--query-gpu=index,name,memory.used,memory.total,utilization.gpu",
                       "--format=csv,noheader,nounits"]) or ""
    gpus = []
    for row in text.strip().splitlines():
        cells = [c.strip() for c in row.split(",")]
        if len(cells) != 5:
            continue
        index, name, used, total, util = cells
        try:
            gpus.append({"index": int(index), "name": name, "memory_used_bytes": int(used) * 2**20,
                         "memory_total_bytes": int(total) * 2**20, "busy_percent": int(util)})
        except ValueError:
            continue
    return gpus


def _node_usage(node: str) -> dict | None:
    """How much of the node all jobs together hold (CfgTRES vs AllocTRES)."""
    text = _run_quiet(["scontrol", "show", "node", node, "-o"])
    if not text:
        return None
    fields = dict(item.split("=", 1) for item in text.split() if "=" in item)

    def tres(key: str) -> dict:
        return dict(part.split("=", 1) for part in fields.get(key, "").split(",") if "=" in part)

    total, held = tres("CfgTRES"), tres("AllocTRES")
    return {
        "state": fields.get("State"),
        "cpus_total": int(total.get("cpu", 0)),
        "cpus_allocated": int(held.get("cpu", 0)),
        "gpus_total": int(total.get("gres/gpu", 0)),
        "gpus_allocated": int(held.get("gres/gpu", 0)),
    }


# ------------------------------------------------------------------ helpers

def _folders(base: Path) -> list[dict]:
    found = []
    for folder in sorted(base.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not folder.is_dir():
            continue
        files = [f for f in folder.rglob("*") if f.is_file()]
        found.append({
            "name": folder.name,
            "path": str(folder),
            "files": len(files),
            "bytes": sum(f.stat().st_size for f in files),
            "single_file": str(files[0]) if len(files) == 1 else None,
            "modified": folder.stat().st_mtime,
        })
    return found


def _runs(server) -> list[dict]:
    runs = []
    for job in server.manager.listing(include_hidden=True):
        if job.get("kind") != "run" or not job.get("output_dir"):
            continue
        runs.append({
            "name": job.get("name"),
            "status": job.get("status"),
            "output_dir": job["output_dir"],
            "exists": Path(job["output_dir"]).is_dir(),
            "created_at": job.get("created_at"),
        })
    return runs


def _login_page(target: str, wrong: bool = False) -> str:
    note = '<p class="bad">That token is not right.</p>' if wrong else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Workbench sign-in</title>
<link rel="stylesheet" href="/gateway/files.css"></head>
<body class="login"><main>
<h1>SigProfilerExtractor Workbench</h1>
<p>Paste the token from <code>workbench_endpoint.env</code> or the job log.</p>
{note}
<form method="post" action="/gateway/login">
<input type="hidden" name="next" value="{_attr(target)}">
<input name="token" type="password" autocomplete="current-password" autofocus
       placeholder="Token" aria-label="Token">
<button type="submit">Sign in</button>
</form></main></body></html>"""


def _attr(text: str) -> str:
    return (text.replace("&", "&amp;").replace('"', "&quot;")
            .replace("<", "&lt;").replace(">", "&gt;"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--public-host", action="append", default=[],
                        help="Extra host name the browser may use (repeatable); '*' allows any.")
    parser.add_argument("--uploads", required=True, help="Folder that receives uploads.")
    parser.add_argument("--volume", default=None,
                        help="Folder of installed reference genomes (the volume parameter).")
    args = parser.parse_args(argv)

    token = os.environ.get("SPE_GATEWAY_TOKEN", "")
    if len(token) < 32:
        parser.error("set SPE_GATEWAY_TOKEN to a random token of at least 32 characters")

    # os.cpu_count() reports the whole machine, and SigProfilerExtractor's
    # default cpu=-1 means "all of them". Python 3.13+ reads PYTHON_CPU_COUNT
    # instead, at start-up only: so set it to the CPUs this app may use (its
    # CPU set and any container quota) and start again. Runs inherit it.
    if "PYTHON_CPU_COUNT" not in os.environ:
        os.environ["PYTHON_CPU_COUNT"] = str(allowed_cpus())
        os.execv(sys.executable, [sys.executable, *sys.argv])

    # Runs start as `python -m ...` in this process's working directory. Run
    # from the folder holding the SigProfilerExtractor clone, that folder
    # would shadow the installed package (no __version__, failed runs), so
    # work from the state directory instead.
    os.chdir(_state_dir())

    srv = workbench.make_server(args.bind, args.port, _state_dir() / "jobs", volume=args.volume)
    srv.RequestHandlerClass = GatewayHandler
    srv.gateway_token = token
    srv.resources = Resources()
    srv.uploads = Path(args.uploads).resolve()
    srv.uploads.mkdir(parents=True, exist_ok=True)
    short = socket.gethostname().split(".")[0]
    srv.public_hosts = None if "*" in args.public_host else {h.lower() for h in (
        "localhost", "127.0.0.1", "::1", short, socket.gethostname(), socket.getfqdn(),
        *args.public_host)}

    def _stop(signum, frame):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _stop)
    print(f"Workbench gateway listening on {args.bind}:{args.port}", flush=True)
    try:
        srv.serve_forever()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        # Quit in the Workbench, scancel, or the time limit: stop every run too.
        srv.manager.stop_all()
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
