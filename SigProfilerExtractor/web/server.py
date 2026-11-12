"""Local HTTP server for the SigProfilerExtractor Workbench.

A single-user, local-only tool bound to the loopback interface, with no
login. Instead (the same model as SigProfilerMatrixGenerator's web app):

* Every request's Host header must name this machine, which stops DNS
  rebinding (a public page resolving its own name to 127.0.0.1).
* GET and HEAD only ever read. Anything that acts (starting or stopping a
  run, installing a genome, building a dashboard, opening a native picker,
  quitting) is a POST, and a POST must carry an Origin that is exactly this
  server (scheme, host and port) plus this launch's token, which is written
  into the page this server serves. Another site, or another local server on
  a different port, can send the request but cannot read the page, so cannot
  supply the token.
* SigProfilerExtractor's own results dashboard (reports.html) runs inline
  scripts, so it is served on its own route with its own policy: sandboxed,
  without access to this origin, unable to fetch anything or call this API.

Do not bind this to a public interface.
"""

from __future__ import annotations

import json
import mimetypes
import os
import secrets
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import genomes, inputs, jobs, native_dialog, params, progress, results

STATIC = Path(__file__).resolve().parent / "static"
ALLOWED_HOSTS = {"localhost", "127.0.0.1", "::1"}

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'self'"
)
# reports.html: everything inline, nothing fetched, and a sandbox without
# allow-same-origin, so it runs as an opaque origin that cannot read this
# app's page or token. allow-downloads keeps its CSV and SVG exports working.
DASHBOARD_POLICY = (
    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
    "img-src data: blob:; font-src data:; frame-ancestors 'self'; "
    "sandbox allow-scripts allow-downloads allow-popups"
)
TOKEN_PLACEHOLDER = "__WORKBENCH_TOKEN__"

# The only native pickers a request can open. Requests name a purpose; the
# dialog kind and title are fixed here, so no request text reaches a dialog.
PICKERS = {
    "input_vcf": ("folder", "Choose the folder of variant calls"),
    "input_matrix": ("file", "Choose the mutation matrix"),
    "input_bedpe": ("folder", "Choose the folder of BEDPE files"),
    "input_seg": ("file", "Choose the segmentation file"),
    "output": ("folder", "Choose where the results go"),
    "results": ("folder", "Open a SigProfilerExtractor results folder"),
    "seeds": ("file", "Choose a Seeds.txt file"),
    "volume": ("folder", "Choose the reference files folder"),
}

_CLIENT_ERRORS = (
    inputs.InputError,
    results.ResultsError,
    native_dialog.DialogError,
    jobs.JobError,
)


class Handler(BaseHTTPRequestHandler):
    server_version = "SigProfilerExtractorWeb"
    protocol_version = "HTTP/1.1"

    # ------------------------------------------------------------ plumbing

    def log_message(self, fmt, *args):
        if self.server.verbose:
            sys.stderr.write("  %s\n" % (fmt % args))

    def _origin_is_this_server(self, origin: str) -> bool:
        parsed = urlparse(origin)
        try:
            port = parsed.port
        except ValueError:
            return False
        return (
            parsed.scheme == "http"
            and (parsed.hostname or "").lower() in ALLOWED_HOSTS
            and port == self.server.server_address[1]
        )

    def _local_only(self) -> bool:
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
        if host.lower() not in ALLOWED_HOSTS:
            return False
        origin = self.headers.get("Origin")
        return not origin or self._origin_is_this_server(origin)

    def _may_act(self) -> bool:
        # A GET legitimately arrives without an Origin (a page load), so GETs
        # only read. A POST from this server's own page always carries its
        # exact Origin and the token from the page; anything else is refused.
        origin = self.headers.get("Origin")
        if not origin or not self._origin_is_this_server(origin):
            return False
        token = self.headers.get("X-Dashboard-Token") or ""
        return secrets.compare_digest(token, self.server.instance_token)

    def _send(self, status, body=b"", ctype="application/json", extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, status=200):
        self._send(status, json.dumps(obj), "application/json")

    def _fail(self, message, status=400, **extra):
        self._json({"ok": False, "error": str(message), **extra}, status)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return {}

    def _file(self, path: Path, download: bool = False, policy: str | None = CONTENT_SECURITY_POLICY):
        if not path.is_file():
            return self._fail(f"not found: {path.name}", 404)
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(path.stat().st_size))
        if policy:
            self.send_header("Content-Security-Policy", policy)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store, must-revalidate")
        if download:
            self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(path, "rb") as handle:
            while chunk := handle.read(1 << 16):
                self.wfile.write(chunk)

    # -------------------------------------------------------------- routes

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not self._local_only():
            return self._fail("requests must come from this machine", 403)
        url = urlparse(self.path)
        path, query = unquote(url.path), parse_qs(url.query)
        try:
            return self._get(path, query)
        except ConnectionError:
            # The browser went away (page closed or reloaded): nothing to answer.
            self.close_connection = True
            return
        except _CLIENT_ERRORS as exc:
            sys.stderr.write(f"  [400] GET {path}: {type(exc).__name__}: {exc}\n")
            return self._fail(str(exc), 400)
        except Exception as exc:  # noqa: BLE001 - request boundary
            sys.stderr.write(f"  [500] GET {path}:\n")
            traceback.print_exc()
            return self._fail(f"{type(exc).__name__}: {exc}", 500)

    def _get(self, path: str, query: dict):
        srv = self.server
        if path in ("/", "/index.html"):
            page = (STATIC / "index.html").read_text(encoding="utf-8")
            page = page.replace(TOKEN_PLACEHOLDER, srv.instance_token)
            return self._send(200, page, "text/html; charset=utf-8",
                              {"Cache-Control": "no-store, must-revalidate"})
        if path.startswith("/static/"):
            target = (STATIC / path[len("/static/"):]).resolve()
            static_root = STATIC.resolve()
            if static_root != target and static_root not in target.parents:
                return self._fail("forbidden", 403)
            return self._file(target)

        if path == "/api/identity":
            return self._json({"pid": os.getpid(), "token": srv.instance_token})
        if path == "/api/env":
            return self._json({
                "ok": True,
                "version": _package_version(),
                "genomes": genomes.status(srv.volume),
                "examples": inputs.examples(),
                "settings": params.page_settings(),
                "cuda": _cuda_available(),
                "cpus": os.cpu_count() or 1,
                "results_root": str(Path.home() / "SigProfilerExtractor_results"),
            })
        if path == "/api/genomes":
            volume = _one(query, "volume") or srv.volume
            return self._json({"ok": True, **genomes.status(volume)})
        if path == "/api/inspect":
            return self._json({"ok": True, **inputs.inspect(_one(query, "type"), _one(query, "path"))})
        if path == "/api/seeds":
            problem = params.seed_file_problem(_one(query, "path"))
            return self._json({"ok": True, "problem": problem})
        if path == "/api/output":
            out, data = _one(query, "path"), _one(query, "input")
            found = results.earlier_results(out)
            return self._json({
                "ok": True, "path": out, **found,
                "suggested": results.next_free_folder(out) if found["found"] else None,
                "replace_problem": results.replace_problem(out, data) if found["found"] and data else None,
            })

        if path == "/api/jobs":
            return self._json({"ok": True, "jobs": srv.manager.listing()})
        if path.startswith("/api/jobs/") and path.endswith("/log"):
            job_id = path.split("/")[3]
            try:
                offset = int(_one(query, "offset", "0"))
            except ValueError:
                return self._fail("offset must be an integer", 400)
            return self._json({"ok": True, **srv.manager.log(job_id, offset)})
        if path.startswith("/api/jobs/") and path.endswith("/delete-preview"):
            job = srv.manager.get(path.split("/")[3])
            if job is None:
                return self._fail("no such run", 404)
            return self._json({"ok": True, **_delete_plan(srv, job)})
        if path.startswith("/api/jobs/"):
            job = srv.manager.get(path.split("/")[3])
            if job is None:
                return self._json({"ok": False, "job": None})
            return self._json({"ok": True, "job": job, "progress": _progress(srv, job)})

        if path == "/api/results":
            return self._json({"ok": True, **results.scan(_one(query, "path"))})
        if path == "/api/results/dashboard":
            target = results.dashboard_path(_one(query, "path"))
            return self._file(target, policy=DASHBOARD_POLICY)
        if path == "/api/results/download":
            return self._file(Path(_one(query, "path")), download=True)
        if path == "/api/results/view":
            # Shown in the browser rather than downloaded, so PDFs only: any
            # other file served inline from this origin could run as this app.
            target = Path(_one(query, "path"))
            if target.suffix.lower() != ".pdf":
                return self._fail("only PDF plots can be viewed here", 400)
            return self._file(target, policy=None)

        return self._fail("not found", 404)

    def do_POST(self):
        if not self._local_only():
            return self._fail("requests must come from this machine", 403)
        if not self._may_act():
            return self._fail("actions must come from this app's own page", 403)
        path = unquote(urlparse(self.path).path)
        try:
            return self._post(path)
        except ConnectionError:
            self.close_connection = True
            return
        except _CLIENT_ERRORS as exc:
            sys.stderr.write(f"  [400] POST {path}: {type(exc).__name__}: {exc}\n")
            return self._fail(str(exc), 400)
        except Exception as exc:  # noqa: BLE001 - request boundary
            sys.stderr.write(f"  [500] POST {path}:\n")
            traceback.print_exc()
            return self._fail(f"{type(exc).__name__}: {exc}", 500)

    def _post(self, path: str):
        srv = self.server
        body = self._body()

        if path == "/api/run":
            return self._start_run(dict(body.get("settings") or {}))
        if path == "/api/genomes/install":
            genome = body.get("genome")
            if not genome:
                return self._fail("genome is required", 400)
            config = {"mode": "install", "reference_genome": genome,
                      "volume": body.get("volume") or srv.volume}
            meta = srv.manager.start(config, f"Install {genome}",
                                     extra={"kind": "install", "reference_genome": genome})
            return self._json({"ok": True, "job": meta})
        if path == "/api/dashboard/build":
            folder = str(body.get("path") or "").strip()
            results.scan(folder)  # refuses a folder without SigProfilerExtractor results
            busy = [j for j in srv.manager.live()
                    if j.get("kind") == "dashboard" and _same_folder(j.get("output_dir", ""), folder)]
            if busy:
                return self._json({"ok": True, "job": busy[0]})
            meta = srv.manager.start({"mode": "dashboard", "output": folder},
                                     f"Dashboard for {Path(folder).name}",
                                     extra={"kind": "dashboard", "output_dir": folder})
            return self._json({"ok": True, "job": meta})
        if path.startswith("/api/jobs/") and path.endswith(("/hide", "/unhide")):
            meta = srv.manager.set_hidden(path.split("/")[3], path.endswith("/hide"))
            return self._json({"ok": True, "job": meta})
        if path.startswith("/api/jobs/") and path.endswith("/delete"):
            job = srv.manager.get(path.split("/")[3])
            if job is None:
                return self._fail("no such run", 404)
            if job["status"] == "running":
                return self._fail("This run is still going; stop it first.", 409)
            plan = _delete_plan(srv, job)
            removed = []
            if plan["deletes_files"]:
                removed = results.delete_output(plan["output_dir"], job.get("input") or "")
            srv.manager.delete_record(job["id"])
            return self._json({"ok": True, "removed": len(removed), "output_dir": plan["output_dir"]})
        if path.startswith("/api/jobs/") and path.endswith("/stop"):
            return self._json({"ok": srv.manager.stop(path.split("/")[3])})
        if path == "/api/dialog":
            picker = PICKERS.get(body.get("purpose"))
            if picker is None:
                return self._fail(f"purpose must be one of {sorted(PICKERS)}", 400)
            kind, title = picker
            return self._json({"ok": True, "path": native_dialog.choose(kind, title)})
        if path == "/api/shutdown":
            self._json({"ok": True})
            threading.Thread(target=srv.shutdown, daemon=True).start()
            return
        if path == "/api/quit":
            srv.manager.stop_all()
            self._json({"ok": True})
            threading.Thread(target=srv.shutdown, daemon=True).start()
            return

        return self._fail("not found", 404)

    def _start_run(self, settings: dict):
        srv = self.server
        settings.setdefault("volume", srv.volume)
        try:
            kwargs = params.validate(settings, cuda_available=_cuda_available())
        except params.ParamsError as exc:
            return self._fail("The run cannot start yet: " + " ".join(exc.problems), 400,
                              problems=exc.problems)
        output = kwargs["output"]
        replace = bool(settings.get("replace_existing"))
        if replace:
            problem = results.replace_problem(output, kwargs["input_data"])
            if problem:
                return self._fail(problem, 400)
        elif results.earlier_results(output)["found"]:
            return self._fail("The output folder already holds results from an earlier run. "
                              "Choose a new folder, or replace the earlier results.", 409)
        found = inputs.inspect(settings["input_type"], kwargs["input_data"])
        contexts = (kwargs["context_type"].split(",") if settings["input_type"] == "vcf"
                    else found.get("contexts") or [])
        # Bundled VCF examples are copied first (SigProfilerMatrixGenerator writes
        # into the folder it reads); a user's own folder must be writable.
        copy_input = False
        if settings["input_type"] == "vcf":
            data_dir = inputs._data_dir().resolve()
            here = Path(kwargs["input_data"]).expanduser().resolve()
            copy_input = here == data_dir or data_dir in here.parents
            if not copy_input and not found.get("writable", True):
                return self._fail("SigProfilerMatrixGenerator writes its matrices into the folder of "
                                  "variant calls, and this folder is not writable. Copy the calls "
                                  "somewhere writable first.", 400)
        config = {"mode": "run", "kwargs": kwargs, "replace_existing": replace, "copy_input": copy_input}
        name = str(settings.get("name") or Path(output).name or "run")
        extra = {
            "kind": "run",
            "input": kwargs["input_data"],
            "input_type": settings["input_type"],
            "output_dir": output,
            "contexts": contexts,
            "samples": found.get("sample_count"),
            "reference_genome": kwargs.get("reference_genome") if settings["input_type"] == "vcf"
            else kwargs.get("opportunity_genome"),
            "minimum_signatures": kwargs["minimum_signatures"],
            "maximum_signatures": kwargs["maximum_signatures"],
            "nmf_replicates": kwargs["nmf_replicates"],
            "assignment": not kwargs["stop_after_extraction"],
            "effort": params.effort(kwargs, len(contexts), found.get("sample_count")),
        }
        meta = srv.manager.start(config, name, extra=extra)
        return self._json({"ok": True, "job": meta})


# ------------------------------------------------------------------ helpers

_CUDA: list[bool] = []


def _cuda_available() -> bool:
    """Whether torch sees a CUDA GPU (cached: importing torch is slow)."""
    if not _CUDA:
        try:
            import torch

            _CUDA.append(bool(torch.cuda.is_available()))
        except Exception:  # noqa: BLE001 - no torch, no GPU
            _CUDA.append(False)
    return _CUDA[0]


def _progress(srv, job: dict) -> dict | None:
    if job.get("kind") != "run":
        return None
    try:
        text = srv.manager.log(job["id"], 0)["text"]
    except jobs.JobError:
        return None
    return progress.parse(text, job)


def _same_folder(a: str, b: str) -> bool:
    try:
        return Path(a).expanduser().resolve() == Path(b).expanduser().resolve()
    except OSError:
        return False


def _runs_writing_to(srv, folder: str) -> list[dict]:
    return [job for job in srv.manager.listing(include_hidden=True)
            if job.get("kind") == "run" and job.get("output_dir")
            and _same_folder(job["output_dir"], folder)]


def _delete_plan(srv, job: dict) -> dict:
    """What deleting a run removes: its record always; its results when they can
    be told apart from anything else in the output folder."""
    plan = {"name": job.get("name"), "kind": job.get("kind"), "status": job["status"],
            "output_dir": None, "deletes_files": False, "files": 0, "bytes": 0, "kept_because": None}
    if job.get("kind") != "run" or not job.get("output_dir"):
        return plan
    out = plan["output_dir"] = job["output_dir"]
    later = [other for other in _runs_writing_to(srv, out) if other["created_at"] > job["created_at"]]
    problem = results.replace_problem(out, job.get("input") or "")
    if later:
        plan["kept_because"] = (f"A later run ({later[-1].get('name')}) wrote to the same folder, "
                                "so the files there are left alone.")
    elif problem:
        plan["kept_because"] = problem
    else:
        plan.update(results.generated_size(out))
        plan["deletes_files"] = plan["files"] > 0
    return plan


def _one(query: dict, key: str, default: str = "") -> str:
    values = query.get(key)
    return values[0] if values else default


def _package_version() -> str:
    import SigProfilerExtractor

    return getattr(SigProfilerExtractor, "__version__", "")


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, host: str, port: int, jobs_dir: str | Path, volume: str | None = None,
                 verbose: bool = False):
        super().__init__((host, port), Handler)
        self.verbose = verbose
        self.volume = volume
        self.manager = jobs.JobManager(jobs_dir)
        self.instance_token = secrets.token_hex(16)


def make_server(host: str, port: int, jobs_dir: str | Path, volume: str | None = None,
                verbose: bool = False) -> Server:
    return Server(host, port, jobs_dir, volume=volume, verbose=verbose)
