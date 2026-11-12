"""Run matrix-generation jobs as subprocesses and track their lifecycle.

Each job runs in its own process (and, on POSIX, its own process group /
session) so a long matrix-generation run never blocks the dashboard server,
and stopping a job stops exactly the processes it started -- never the
server itself. Job records are written atomically (write-then-rename) so a
server restart mid-write never leaves a half-written record behind, and a
finished job survives a restart: ``JobManager`` rebuilds its in-memory view
by rescanning the jobs directory rather than keeping state only in memory.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

RUNJOB_MODULE = "SigProfilerExtractor.web.runjob"


class JobError(RuntimeError):
    pass


def _write_json_atomic(path: Path, payload: dict) -> None:
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _popen_kwargs() -> dict:
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _kill(pid: int) -> None:
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(pid)],
            capture_output=True,
            check=False,
        )
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass


_JOB_ID = re.compile(r"[0-9a-f]{12}")


class JobManager:
    def __init__(self, jobs_dir: str | Path):
        self.jobs_dir = Path(jobs_dir)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        # Popen handles for jobs started by this instance, kept only so their
        # exit status can be reaped (see _refresh) -- a job started by a
        # previous server instance has no entry here, which is fine: an
        # orphan's exit is reaped by the OS once its original parent is gone.
        self._processes: dict[str, subprocess.Popen] = {}

    def _job_dir(self, job_id: str) -> Path:
        # Ids come from request URLs and name folders this class deletes, so
        # only the shape start() creates is accepted.
        if not _JOB_ID.fullmatch(str(job_id)):
            raise JobError(f"no such job: {job_id}")
        return self.jobs_dir / job_id

    def _meta_path(self, job_id: str) -> Path:
        return self._job_dir(job_id) / "meta.json"

    def _is_alive(self, job_id: str, pid: int) -> bool:
        # A signal-0 kill reports a zombie (exited, not yet reaped) as alive,
        # since it still holds a PID. poll() on a Popen handle this instance
        # itself owns reaps it and returns its real exit status.
        process = self._processes.get(job_id)
        if process is not None and process.poll() is not None:
            return False
        return _is_alive(pid)

    def _refresh(self, meta: dict) -> dict:
        """Reconcile a job's recorded status against reality.

        A pidfile naming a live pid is not proof the job is still running --
        it may have crashed without writing result.json (killed externally,
        or the machine lost power). Only three things can be true: a
        result.json exists (the job finished, successfully or not), the pid
        is still alive (still running), or neither (it died without
        reporting -- "failed", with a generic explanation).
        """
        if meta["status"] not in ("running",):
            return meta
        result_path = self._job_dir(meta["id"]) / "result.json"
        result = _read_json(result_path)
        if result is not None:
            meta["status"] = result["status"]
            meta.update({k: v for k, v in result.items() if k != "status"})
            _write_json_atomic(self._meta_path(meta["id"]), meta)
            return meta
        if not self._is_alive(meta["id"], meta["pid"]):
            meta["status"] = "failed"
            meta["error"] = "the job process exited without reporting a result"
            _write_json_atomic(self._meta_path(meta["id"]), meta)
        return meta

    def start(
        self,
        config: dict,
        name: str,
        cwd: str | Path | None = None,
        extra: dict | None = None,
    ) -> dict:
        job_id = uuid.uuid4().hex[:12]
        job_dir = self._job_dir(job_id)
        job_dir.mkdir(parents=True)
        config_path = job_dir / "config.json"
        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        log_path = job_dir / "job.log"

        argv = [sys.executable, "-u", "-m", RUNJOB_MODULE, str(config_path)]
        with open(log_path, "wb") as log_handle:
            process = subprocess.Popen(
                argv,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                cwd=str(cwd) if cwd else None,
                **_popen_kwargs(),
            )
        self._processes[job_id] = process

        meta = dict(extra or {})
        meta.update(
            {
                "id": job_id,
                "name": name,
                "pid": process.pid,
                "status": "running",
                "created_at": time.time(),
            }
        )
        _write_json_atomic(self._meta_path(job_id), meta)
        return meta

    def get(self, job_id: str) -> dict | None:
        if not _JOB_ID.fullmatch(str(job_id)):
            return None
        meta = _read_json(self._meta_path(job_id))
        if meta is None:
            return None
        return self._refresh(meta)

    def listing(self, include_hidden: bool = False) -> list[dict]:
        """Every job, newest first; hidden ones (removed from the list) only on request."""
        jobs = []
        for job_dir in sorted(self.jobs_dir.iterdir()):
            meta = _read_json(job_dir / "meta.json")
            if meta is not None:
                meta = self._refresh(meta)
                if include_hidden or not meta.get("hidden"):
                    jobs.append(meta)
        return sorted(jobs, key=lambda j: j["created_at"], reverse=True)

    def set_hidden(self, job_id: str, hidden: bool) -> dict:
        """Remove a finished job from the list, or bring it back. Nothing is deleted."""
        meta = self.get(job_id)
        if meta is None:
            raise JobError(f"no such job: {job_id}")
        if hidden and meta["status"] == "running":
            raise JobError("stop the run before removing it from the list")
        meta["hidden"] = bool(hidden)
        _write_json_atomic(self._meta_path(job_id), meta)
        return meta

    def delete_record(self, job_id: str) -> None:
        """Delete a finished job's record (settings, log, result) for good."""
        meta = self.get(job_id)
        if meta is None:
            raise JobError(f"no such job: {job_id}")
        if meta["status"] == "running":
            raise JobError("stop the run before deleting it")
        shutil.rmtree(self._job_dir(job_id))
        self._processes.pop(job_id, None)

    def live(self) -> list[dict]:
        return [j for j in self.listing() if j["status"] == "running"]

    def log(self, job_id: str, offset: int = 0) -> dict:
        log_path = self._job_dir(job_id) / "job.log"
        if not log_path.is_file():
            raise JobError(f"no such job: {job_id}")
        with open(log_path, "rb") as handle:
            handle.seek(offset)
            chunk = handle.read()
        return {
            "text": chunk.decode("utf-8", errors="replace"),
            "offset": offset + len(chunk),
        }

    def stop(self, job_id: str) -> bool:
        meta = self.get(job_id)
        if meta is None:
            raise JobError(f"no such job: {job_id}")
        if meta["status"] != "running":
            return True
        _kill(meta["pid"])
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if not self._is_alive(job_id, meta["pid"]):
                break
            time.sleep(0.05)
        meta["status"] = "stopped"
        _write_json_atomic(self._meta_path(job_id), meta)
        return True

    def stop_all(self) -> None:
        for job in self.live():
            self.stop(job["id"])
