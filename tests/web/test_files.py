"""Files on the Workbench's machine: the page's own picker, upload, and a
results folder as one .zip (SigProfilerExtractor/web/files.py and its routes)."""

import io
import json
import threading
import urllib.error
import urllib.parse
import urllib.request
import zipfile

import pytest

from SigProfilerExtractor.web import files, jobs, server


@pytest.fixture
def running_server(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "RUNJOB_MODULE", "tests.web.fixtures.fake_runjob")
    srv = server.make_server("127.0.0.1", 0, tmp_path / "state" / "jobs")
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield srv
    finally:
        srv.shutdown()
        thread.join(timeout=5)
        srv.server_close()


def _url(srv, path):
    return f"http://127.0.0.1:{srv.server_address[1]}{path}"


def _request(srv, path, data=None, headers=None, method=None):
    request = urllib.request.Request(_url(srv, path), data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers, exc.read()


def _get(srv, path):
    status, _, body = _request(srv, path)
    return status, json.loads(body)


def _multipart(named_files):
    boundary = "----workbench-test-boundary"
    out = io.BytesIO()
    for name, content in named_files:
        out.write(f"--{boundary}\r\n".encode())
        out.write(f'Content-Disposition: form-data; name="files"; filename="{name}"\r\n'.encode())
        out.write(b"Content-Type: application/octet-stream\r\n\r\n")
        out.write(content)
        out.write(b"\r\n")
    out.write(f"--{boundary}--\r\n".encode())
    return out.getvalue(), f"multipart/form-data; boundary={boundary}"


def _upload(srv, purpose, named_files, token=True):
    body, ctype = _multipart(named_files)
    headers = {"Content-Type": ctype, "Origin": _url(srv, "")}
    if token:
        headers["X-Dashboard-Token"] = srv.instance_token
    status, _, raw = _request(srv, f"/api/upload?purpose={purpose}", data=body, headers=headers, method="POST")
    return status, json.loads(raw)


def _results_folder(root):
    (root / "SBS96" / "All_Solutions").mkdir(parents=True)
    (root / "SBS96" / "All_solutions_stat.csv").write_text("Signatures\n1\n")
    (root / "JOB_METADATA.txt").write_text("done\n")
    (root / "reports.html").write_text("<html></html>")
    (root / ".hidden").write_text("not sent")
    return root


# ------------------------------------------------------------------ browse


def test_browse_lists_folders_first_and_marks_inputs_and_results(tmp_path):
    (tmp_path / "b.vcf").write_text("x")
    (tmp_path / "a.SBS96.all").write_text("x")
    (tmp_path / ".secret").write_text("x")
    _results_folder(tmp_path / "zz_results")
    (tmp_path / "plain").mkdir()
    listing = files.browse(str(tmp_path))
    names = [e["name"] for e in listing["entries"]]
    assert names == ["plain", "zz_results", "a.SBS96.all", "b.vcf"]
    hints = {e["name"]: e["hint"] for e in listing["entries"]}
    assert hints == {"plain": "", "zz_results": "results", "a.SBS96.all": "matrix", "b.vcf": "calls"}
    assert listing["parent"] == str(tmp_path.parent)


def test_browse_opens_the_nearest_folder_that_exists(tmp_path):
    (tmp_path / "f.txt").write_text("x")
    assert files.browse(str(tmp_path / "not" / "yet"))["path"] == str(tmp_path)
    assert files.browse(str(tmp_path / "f.txt"))["path"] == str(tmp_path)
    with pytest.raises(files.FilesError):
        files.browse("relative/path")


def test_env_names_the_picker_and_its_places(running_server):
    status, env = _get(running_server, "/api/env")
    assert status == 200
    assert env["picker"] == "native"
    assert env["pickers"]["input_matrix"] == {"kind": "file", "title": "Choose the mutation matrix"}
    assert env["uploads_root"].endswith("uploads")


def test_the_browse_route_starts_at_home_when_given_no_path(running_server, tmp_path):
    running_server.home = tmp_path
    status, listing = _get(running_server, "/api/browse")
    assert status == 200 and listing["path"] == str(tmp_path)


def test_a_server_without_a_native_picker_refuses_the_dialog(running_server):
    running_server.picker = "page"
    body = json.dumps({"purpose": "output"}).encode()
    status, _, raw = _request(running_server, "/api/dialog", data=body, method="POST", headers={
        "Content-Type": "application/json", "Origin": _url(running_server, ""),
        "X-Dashboard-Token": running_server.instance_token})
    assert status == 400 and "draws its own" in json.loads(raw)["error"]


# ------------------------------------------------------------------ upload


def test_a_folder_upload_lands_in_a_new_folder_and_names_it(running_server):
    status, first = _upload(running_server, "input_vcf", [("s1.vcf", b"one"), ("s2.vcf", b"two")])
    assert status == 200, first
    folder = running_server.uploads / first["path"].rsplit("/", 1)[-1]
    assert first["path"] == str(folder) and folder.name.startswith("vcf_")
    assert sorted(p.name for p in folder.iterdir()) == ["s1.vcf", "s2.vcf"]
    _, second = _upload(running_server, "input_vcf", [("s3.vcf", b"three")])
    assert second["path"] != first["path"]  # two uploads never mix


def test_a_one_file_upload_answers_with_the_file(running_server):
    status, body = _upload(running_server, "input_matrix", [("../../m.SBS96.all", b"MutationType\tS1\n")])
    assert status == 200, body
    assert body["path"].endswith("/m.SBS96.all")
    assert body["files"] == [{"name": "m.SBS96.all", "bytes": len(b"MutationType\tS1\n")}]


def test_a_one_file_input_refuses_several_files_and_keeps_nothing(running_server):
    status, body = _upload(running_server, "input_matrix", [("a.all", b"1"), ("b.all", b"2")])
    assert status == 400 and "one file" in body["error"]
    assert not any(running_server.uploads.iterdir())


def test_an_upload_needs_the_pages_token_and_a_known_purpose(running_server):
    status, _ = _upload(running_server, "input_vcf", [("s1.vcf", b"x")], token=False)
    assert status == 403
    status, body = _upload(running_server, "seeds", [("Seeds.txt", b"x")])
    assert status == 400 and "purpose" in body["error"]


def test_repeated_and_reserved_names_are_kept_apart(tmp_path):
    body, ctype = _multipart([("x.vcf", b"1"), ("x.vcf", b"2"), ("nul.vcf", b"3")])
    written = files.parse_upload(io.BytesIO(body), ctype, len(body), tmp_path)
    assert [f["name"] for f in written] == ["x.vcf", "x_2.vcf", "nul_.vcf"]
    assert (tmp_path / "x_2.vcf").read_bytes() == b"2"
    assert not list(tmp_path.glob("*.uploading"))


def test_a_boundary_split_across_reads_is_still_found(tmp_path, monkeypatch):
    monkeypatch.setattr(files, "CHUNK", 7)
    payload = bytes(range(256)) * 40
    body, ctype = _multipart([("big.vcf", payload)])
    files.parse_upload(io.BytesIO(body), ctype, len(body), tmp_path)
    assert (tmp_path / "big.vcf").read_bytes() == payload


def test_an_upload_over_the_limit_is_refused(tmp_path):
    body, ctype = _multipart([("big.vcf", b"x" * 5000)])
    with pytest.raises(files.FilesError):
        files.parse_upload(io.BytesIO(body), ctype, len(body), tmp_path, limit=1000)


# ------------------------------------------------------------------ .zip


def test_a_results_folder_downloads_as_one_zip(running_server, tmp_path):
    folder = _results_folder(tmp_path / "my_run")
    path = urllib.parse.quote(str(folder))
    status, plan = _get(running_server, f"/api/results/archive/plan?path={path}")
    assert status == 200 and plan["files"] == 3 and plan["name"] == "my_run"

    status, headers, _ = _request(running_server, f"/api/results/archive?path={path}", method="HEAD")
    assert status == 200

    status, headers, raw = _request(running_server, f"/api/results/archive?path={path}")
    assert status == 200
    assert headers["Content-Disposition"] == 'attachment; filename="my_run.zip"'
    assert int(headers["Content-Length"]) == len(raw)
    names = sorted(zipfile.ZipFile(io.BytesIO(raw)).namelist())
    assert names == ["my_run/JOB_METADATA.txt", "my_run/SBS96/All_solutions_stat.csv", "my_run/reports.html"]
    assert not list(running_server.scratch.glob("*.zip"))  # the built archive is not kept


def test_only_a_results_folder_is_offered_whole(running_server, tmp_path):
    (tmp_path / "anything").mkdir()
    status, body = _get(running_server, f"/api/results/archive?path={urllib.parse.quote(str(tmp_path / 'anything'))}")
    assert status == 400 and "results" in body["error"]
