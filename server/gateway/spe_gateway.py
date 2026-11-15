"""Serve the SigProfilerExtractor Workbench from a server (a lab machine, a
cluster node) to the browser on another computer.

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
* tells the Workbench to draw its own file picker from the server's folders
  (no native picker can open on a headless node), to put uploads in the data
  folder's uploads/, and to offer the user's home and the data folder as
  places to start from. Upload and the .zip download of results are the
  Workbench's own (SigProfilerExtractor/web/files.py);
* reports the CPUs, memory and GPUs the job has, with recent trends, in a
  panel under the top bar's "ready" pill (static/status.js), and holds runs
  to those CPUs.

Run it with the Workbench's own interpreter (it imports the installed
package); the launcher, ../spe-server, does that. The token comes from the
SPE_GATEWAY_TOKEN environment variable, never argv, which other users on the
node can read with ps.
"""

from __future__ import annotations

import argparse
import collections
import errno
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
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse

import psutil  # a SigProfilerExtractor dependency, so always in the venv
from SigProfilerExtractor.web import server as workbench
from SigProfilerExtractor.web.launcher import _state_dir

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
# Added to the Workbench's page: the job-resources panel (status.js).
ADDON = (
    '<link rel="stylesheet" href="/gateway/status.css">'
    '<div id="spe-gw"></div>'
    '<script src="/gateway/status.js" defer></script>'
)
GATEWAY_FILES = ("login.css", "status.js", "status.css")
LOGIN_BODY_MAX = 1 << 16   # the sign-in form: a token and a path


def token_matches(given: str, token: str) -> bool:
    """Constant-time, on bytes: compare_digest refuses a str that is not
    ASCII, and a cookie or form may hold anything."""
    return secrets.compare_digest(given.encode("utf-8", "surrogateescape"),
                                  token.encode("utf-8"))


def safe_target(target: str) -> str:
    """Where to go after sign-in: a path on this server, else "/".

    "//host" and "/\\host" both mean another site to a browser (it reads a
    backslash as a slash), so neither may follow a sign-in; nor may anything
    with a scheme, a host, or control characters.
    """
    if (not isinstance(target, str) or not target.startswith("/")
            or target[1:2] in ("/", "\\") or "\\" in target
            or any(ord(c) < 0x20 or ord(c) == 0x7F for c in target)):
        return "/"
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return "/"
    return target


def cpu_set() -> list:
    """The CPUs this process may run on (all of them where the system cannot
    say, as on macOS)."""
    try:
        return sorted(os.sched_getaffinity(0))
    except AttributeError:
        return list(range(os.cpu_count() or 1))


class GatewayHandler(workbench.Handler):
    """The Workbench's handler, behind a token check and the gateway routes."""

    def log_message(self, fmt, *args):
        # Should request lines be logged, never with the token.
        super().log_message(fmt, *(re.sub(r"token=[^&\s]*", "token=...", a) if isinstance(a, str)
                                   else a for a in args))

    # ------------------------------------------------------------ access

    def _token_ok(self, given: str) -> bool:
        return token_matches(given, self.server.gateway_token)

    def _cookie_name(self) -> str:
        # Browsers share cookies across ports, so name it after this port.
        return f"spe_gateway_{self.server.server_address[1]}"

    def _has_cookie(self) -> bool:
        for part in (self.headers.get("Cookie") or "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == self._cookie_name():
                return self._token_ok(value)
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
        # None: any name or address (--public-host '*'), for a server that
        # cannot know every name it is reached by. The token check below still applies,
        # and the cookie is bound to the name the browser used.
        if self.server.public_hosts is not None and host not in self.server.public_hosts:
            self._fail("unknown host name", 403)
            return False
        url = urlparse(self.path)
        query = parse_qs(url.query)
        given = (query.get("token") or [""])[0]
        if self.command in ("GET", "HEAD") and given:
            if self._token_ok(given):
                rest = urlencode([(k, v) for k, vs in query.items() if k != "token" for v in vs])
                self._set_cookie_and_go(safe_target(url.path + (f"?{rest}" if rest else "")))
                return False
        if url.path == "/gateway/login":
            self._login()
            return False
        if self._has_cookie():
            return True
        if self.command in ("GET", "HEAD") and not url.path.startswith(("/api/", "/gateway/api/")):
            self.send_response(303)
            self.send_header("Location", "/gateway/login?next=" + quote(safe_target(self.path), safe=""))
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            # Its body, if any, is left unread: end the connection with it.
            self.close_connection = True
            self._fail("not signed in: open the URL with the token first", 401)
        return False

    def _login(self) -> None:
        if self.command == "POST":
            # Read before the token is known, so bounded: a missing, negative
            # or huge length is refused rather than read until the client
            # stops sending.
            try:
                length = int(self.headers.get("Content-Length") or "")
            except ValueError:
                length = -1
            if not 0 <= length <= LOGIN_BODY_MAX:
                self.close_connection = True
                return self._fail("bad sign-in request", 400)
            form = parse_qs(self.rfile.read(length).decode("utf-8", "replace"))
            token = (form.get("token") or [""])[0].strip()
            target = safe_target((form.get("next") or ["/"])[0])
            if self._token_ok(token):
                return self._set_cookie_and_go(target)
            time.sleep(1)  # slow down guessing
            return self._send(403, _login_page(target, wrong=True), "text/html; charset=utf-8")
        target = safe_target((parse_qs(urlparse(self.path).query).get("next") or ["/"])[0])
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
        self._as_local()
        return super().do_POST()

    def _get(self, path: str, query: dict):
        if path in ("/", "/index.html"):
            page = (workbench.STATIC / "index.html").read_text(encoding="utf-8")
            page = page.replace(workbench.TOKEN_PLACEHOLDER, self.server.instance_token)
            page = page.replace("</body>", ADDON + "</body>", 1)
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
        if path.startswith("/gateway/") and path[len("/gateway/"):] in GATEWAY_FILES:
            return self._file(STATIC / path[len("/gateway/"):])
        if path == "/gateway/api/resources":
            return self._json({"ok": True, **self.server.resources.snapshot()})
        return self._fail("not found", 404)


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
        self._cpus = cpu_set()
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
        this job even when its CPUs are shared; else the load of the CPUs in
        this process's CPU set.
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
        # SPE_HOST_NAME: the server's full name, which the launcher passes in.
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

    In a SLURM job: the job's cgroup (job_N), shared by all its steps.
    Anywhere else the cgroup is a whole login session, which says nothing
    about this app, so None.
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
    else:
        return None
    return base if (base / "memory.current").is_file() else None


def allowed_cpus() -> int:
    """CPUs this app may use: its CPU set (a SLURM job's CPUs), capped by a
    cgroup CPU quota and by PYTHON_CPU_COUNT when it is set (the launcher's
    --cpus)."""
    count = len(cpu_set())
    base = cgroup_dir()
    if base is not None:
        try:
            quota, period = (base / "cpu.max").read_text().split()
            if quota != "max":
                count = min(count, max(1, math.ceil(int(quota) / int(period))))
        except (OSError, ValueError):
            pass
    try:
        count = min(count, max(1, int(os.environ.get("PYTHON_CPU_COUNT") or count)))
    except ValueError:
        pass
    return count


def _cgroup_memory_limit(base: Path | None) -> int | None:
    """A SLURM job's memory limit, if it has one."""
    if base is None:
        return None
    try:
        text = (base / "memory.max").read_text().strip()
    except OSError:
        return None
    return int(text) if text.isdigit() else None


def _memory_used(base: Path | None) -> int:
    """Memory in use by the whole SLURM job, else by this process tree.

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

def _login_page(target: str, wrong: bool = False) -> str:
    note = '<p class="bad">That token is not right.</p>' if wrong else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Workbench sign-in</title>
<link rel="stylesheet" href="/gateway/login.css"></head>
<body><main>
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


def open_server(args):
    """The Workbench's server on the first free port of --port and the next
    --port-tries - 1, or None. Binding is the only reliable test: a port can
    be taken on any address, or by someone starting at the same moment."""
    for port in range(args.port, args.port + max(args.port_tries, 1)):
        try:
            return workbench.make_server(args.bind, port, _state_dir() / "jobs", volume=args.volume)
        except OSError as exc:
            if exc.errno not in (errno.EADDRINUSE, errno.EACCES):
                raise
    return None


def announce(port: int, token: str, url_file: Path | None) -> None:
    """Print the link and the SSH tunnel for it, and write the link (owner
    only) where the launcher reads it, now that the port is known."""
    env = os.environ
    host = env.get("SPE_HOST_NAME") or socket.getfqdn()
    user = env.get("SPE_SSH_USER") or "you"
    url = f"http://{host}:{port}/?token={token}"
    if env.get("SPE_SSH_VIA"):
        tunnel = f"ssh -N -L {port}:{host}:{port} {user}@{env['SPE_SSH_VIA']}"
    else:
        tunnel = f"ssh -N -L {port}:localhost:{port} {user}@{host}"
    if url_file is not None:
        fd = os.open(url_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as out:
            out.write(url + "\n")
    # The log this goes to may be readable by others, so no token in it: the
    # full link is in the url file (owner only), which "spe-server url" prints.
    print(f"""
  SigProfilerExtractor Workbench

  Listening at http://{host}:{port}/ ; the link with its token: spe-server url

  If the port is not reachable from your computer, tunnel it over SSH (same
  port on both ends) and open the link with localhost in place of {host}:

    {tunnel}

  Data folder: {env.get("SPE_DATA", "")}
""", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--port-tries", type=int, default=1, metavar="N",
                        help="if the port is taken, try the next ones, N ports in all")
    parser.add_argument("--url-file", type=Path, metavar="FILE",
                        help="write the link here once the port is open")
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
    # CPU set: a SLURM job's) and start again. Runs inherit it. The launcher's
    # --cpus sets it lower.
    if "PYTHON_CPU_COUNT" not in os.environ:
        os.environ["PYTHON_CPU_COUNT"] = str(allowed_cpus())
        os.execv(sys.executable, [sys.executable, *sys.argv])

    # Runs start as `python -m ...` in this process's working directory. Run
    # from the folder holding the SigProfilerExtractor clone, that folder
    # would shadow the installed package (no __version__, failed runs), so
    # work from the state directory instead.
    os.chdir(_state_dir())

    srv = open_server(args)
    if srv is None:
        last = args.port + max(args.port_tries, 1) - 1
        print(f"FATAL: port {args.port}" + (f" to {last}" if last > args.port else "")
              + " already in use on this server", file=sys.stderr, flush=True)
        return 98
    wanted, args.port = args.port, srv.server_address[1]
    if args.port != wanted:
        print(f"port {wanted} is taken; using {args.port}", flush=True)
    srv.RequestHandlerClass = GatewayHandler
    srv.gateway_token = token
    srv.resources = Resources()
    # Files: the page's own picker (no native one can open here), uploads into
    # the data folder, and the user's real home (HOME is the data folder here,
    # see entrypoint.sh) and the data folder as places to start from.
    srv.picker = "page"
    srv.uploads = Path(args.uploads).resolve()
    srv.uploads.mkdir(parents=True, exist_ok=True)
    home = Path(os.environ.get("SPE_HOME") or Path.home())
    if home.is_dir():
        srv.home = home
    if os.environ.get("SPE_DATA"):
        srv.extra_places = [("Data folder", Path(os.environ["SPE_DATA"]))]
    short = socket.gethostname().split(".")[0]
    srv.public_hosts = None if "*" in args.public_host else {h.lower() for h in (
        "localhost", "127.0.0.1", "::1", short, socket.gethostname(), socket.getfqdn(),
        *args.public_host)}

    def _stop(signum, frame):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _stop)
    announce(args.port, token, args.url_file)
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
