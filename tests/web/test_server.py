import http.client
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

from SigProfilerExtractor.web import jobs, server



@pytest.fixture
def running_server(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "RUNJOB_MODULE", "tests.web.fixtures.fake_runjob")
    srv = server.make_server("127.0.0.1", 0, tmp_path / "jobs")
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


def _get(srv, path, headers=None):
    request = urllib.request.Request(_url(srv, path), headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _post(srv, path, payload=None, headers=None, token=True):
    """POST as the app's own page does: exact Origin plus the launch token."""
    data = json.dumps(payload or {}).encode("utf-8")
    hdrs = {"Content-Type": "application/json", "Origin": _url(srv, "")}
    if token:
        hdrs["X-Dashboard-Token"] = srv.instance_token
    hdrs.update(headers or {})
    request = urllib.request.Request(_url(srv, path), data=data, method="POST", headers=hdrs)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _raw(srv, request_bytes):
    import socket

    with socket.create_connection(("127.0.0.1", srv.server_address[1]), timeout=5) as sock:
        sock.sendall(request_bytes)
        return sock.recv(65536)


# ------------------------------------------------------------- security


def test_wrong_host_header_is_refused(running_server):
    request = urllib.request.Request(_url(running_server, "/api/env"))
    request.headers["Host"] = "evil.example.com"
    # urllib won't let us override Host easily via headers dict (it's set
    # from the URL), so hit the socket directly for this one check.
    import socket

    with socket.create_connection(("127.0.0.1", running_server.server_address[1]), timeout=5) as sock:
        sock.sendall(
            b"GET /api/env HTTP/1.1\r\nHost: evil.example.com\r\nConnection: close\r\n\r\n"
        )
        response = sock.recv(4096)
    assert b"403" in response.split(b"\r\n", 1)[0]


def test_cross_site_origin_is_refused(running_server):
    status, body = _post(
        running_server, "/api/quit", headers={"Origin": "http://evil.example.com"}
    )
    assert status == 403
    assert body["ok"] is False


def test_post_without_origin_header_is_refused(running_server):
    # Unlike GET (a top-level page load legitimately has no Origin), a POST
    # with no Origin at all is not something this dashboard's own frontend
    # would ever send, so it's refused outright rather than let through.
    request = urllib.request.Request(
        _url(running_server, "/api/run"),
        data=b"{}",
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            status, body = response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        status, body = exc.code, json.loads(exc.read())
    assert status == 403
    assert body["ok"] is False


def test_post_without_the_token_is_refused(running_server):
    status, _ = _post(running_server, "/api/quit", token=False)
    assert status == 403
    time.sleep(0.2)
    assert _get(running_server, "/api/identity")[0] == 200  # did not quit


def test_post_with_a_wrong_token_is_refused(running_server):
    status, _ = _post(running_server, "/api/quit", headers={"X-Dashboard-Token": "guess"})
    assert status == 403


@pytest.mark.parametrize("origin", [
    "http://127.0.0.1:1",                  # another local server (wrong port)
    "http://localhost",                     # no port at all
    "https://127.0.0.1:{port}",             # wrong scheme
    "http://evil.example.com:{port}",       # another site
    "null",                                 # sandboxed or file:// page
])
def test_post_from_any_other_origin_is_refused_even_with_the_token(running_server, origin):
    origin = origin.format(port=running_server.server_address[1])
    status, _ = _post(running_server, "/api/quit", headers={"Origin": origin})
    assert status == 403


def test_get_with_a_foreign_origin_is_refused(running_server):
    status, _ = _get(running_server, "/api/env", headers={"Origin": "http://127.0.0.1:1"})
    assert status == 403


def test_the_page_carries_this_launch_token(running_server):
    with urllib.request.urlopen(_url(running_server, "/"), timeout=5) as response:
        page = response.read().decode("utf-8")
    assert running_server.instance_token in page
    assert server.TOKEN_PLACEHOLDER not in page


@pytest.fixture
def no_dialogs(monkeypatch):
    opened = []
    monkeypatch.setattr(server.native_dialog, "choose",
                        lambda kind, title: opened.append((kind, title)) or "/picked")
    return opened


@pytest.mark.parametrize("method", [b"GET", b"HEAD"])
def test_a_link_or_image_cannot_open_a_native_picker(running_server, no_dialogs, method):
    # What a cross-site link, image or navigation sends: GET/HEAD, no Origin.
    response = _raw(
        running_server,
        method + b" /api/dialog?purpose=input_vcf&title=x HTTP/1.1\r\nHost: 127.0.0.1\r\n"
        b"Connection: close\r\n\r\n",
    )
    assert b" 200 " not in response.split(b"\r\n", 1)[0]
    assert no_dialogs == []


def test_picker_title_comes_from_the_server_not_the_request(running_server, no_dialogs):
    status, body = _post(running_server, "/api/dialog",
                         {"purpose": "input_vcf", "title": 'x") & (do shell script "id")'})
    assert status == 200
    assert body["path"] == "/picked"
    assert no_dialogs == [server.PICKERS["input_vcf"]]


def test_unknown_picker_purpose_is_a_client_error(running_server, no_dialogs):
    status, body = _post(running_server, "/api/dialog", {"purpose": "anything"})
    assert status == 400
    assert no_dialogs == []


def test_picker_without_the_token_does_not_open(running_server, no_dialogs):
    status, _ = _post(running_server, "/api/dialog", {"purpose": "input_vcf"}, token=False)
    assert status == 403
    assert no_dialogs == []


def test_genome_status_follows_the_requested_install_folder(running_server, tmp_path, monkeypatch):
    from SigProfilerMatrixGenerator.scripts import reference_genome_manager

    if not hasattr(reference_genome_manager, "CHECKSUMS"):
        pytest.skip("this SigProfilerMatrixGenerator has no CHECKSUMS table")
    monkeypatch.delenv("SIGPROFILERMATRIXGENERATOR_VOLUME", raising=False)
    monkeypatch.setitem(reference_genome_manager.CHECKSUMS, "fixtureG", {"1": "x"})
    volume = tmp_path / "genomes"
    (volume / "tsb" / "fixtureG").mkdir(parents=True)
    (volume / "tsb" / "fixtureG" / "1.txt").write_text("data")

    _, elsewhere = _get(running_server, "/api/genomes")
    _, here = _get(running_server, f"/api/genomes?volume={volume}")

    assert "fixtureG" not in elsewhere["installed"]
    assert "fixtureG" in here["installed"]


def test_every_response_has_a_csp_header(running_server):
    request = urllib.request.Request(_url(running_server, "/api/env"))
    with urllib.request.urlopen(request, timeout=5) as response:
        assert "default-src" in response.headers.get("Content-Security-Policy", "")


def test_static_path_cannot_escape_static_root(running_server):
    status, body = _get(running_server, "/static/../../../etc/passwd")
    assert status in (403, 404)


# ------------------------------------------------------------------ pages


def test_root_serves_index_html(running_server):
    request = urllib.request.Request(_url(running_server, "/"))
    with urllib.request.urlopen(request, timeout=5) as response:
        assert response.status == 200
        assert b"SigProfilerExtractor Workbench" in response.read()


def test_unknown_route_is_404(running_server):
    status, body = _get(running_server, "/api/nonexistent")
    assert status == 404


# -------------------------------------------------------------------- env



# --------------------------------------------------------------- SPE routes

DATA = Path(server.__file__).resolve().parents[1] / "data"
SBS = str(DATA / "TextInput" / "Samples_SBS.txt")


def _settings(tmp_path, **over):
    s = {"input_type": "matrix", "input_data": SBS, "output": str(tmp_path / "out")}
    s.update(over)
    return s


def _wait(srv, job_id, timeout=10):
    deadline = time.monotonic() + timeout
    while srv.manager.get(job_id)["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.05)
    return srv.manager.get(job_id)


def test_env_offers_settings_examples_and_hardware(running_server):
    status, env = _get(running_server, "/api/env")
    assert status == 200
    assert env["settings"]["defaults"]["nmf_replicates"] == 100
    assert set(env["settings"]["presets"]) == {"quick", "standard"}
    assert {e["id"] for e in env["examples"]} >= {"sbs96", "vcf"}
    assert isinstance(env["cuda"], bool) and env["cpus"] >= 1
    assert env["results_root"].endswith("SigProfilerExtractor_results")


def test_inspect_recognises_a_matrix(running_server):
    status, body = _get(running_server, "/api/inspect?" + urllib.parse.urlencode({"type": "matrix", "path": SBS}))
    assert status == 200
    assert (body["format"], body["sample_count"]) == ("SBS96", 21)


def test_run_with_problems_lists_them_all(running_server, tmp_path):
    status, body = _post(running_server, "/api/run",
                         {"settings": _settings(tmp_path, nmf_replicates=0, precision="half")})
    assert status == 400
    assert len(body["problems"]) == 2


def test_run_records_what_the_monitor_needs(running_server, tmp_path):
    status, body = _post(running_server, "/api/run", {"settings": _settings(tmp_path, maximum_signatures=5,
                                                                             nmf_replicates=10)})
    assert status == 200
    job = body["job"]
    assert (job["kind"], job["contexts"], job["samples"]) == ("run", ["SBS96"], 21)
    assert job["effort"] == {"contexts": 1, "ranks": 5, "replicates": 10, "fits": 50}
    config = json.loads((Path(running_server.manager.jobs_dir) / job["id"] / "config.json").read_text())
    assert config["mode"] == "run" and config["kwargs"]["nmf_replicates"] == 10
    assert config["copy_input"] is False


def test_a_run_never_lands_silently_on_earlier_results(running_server, tmp_path):
    out = tmp_path / "out"
    (out / "SBS96" / "All_Solutions").mkdir(parents=True)
    status, body = _post(running_server, "/api/run", {"settings": _settings(tmp_path)})
    assert status == 409
    status, body = _post(running_server, "/api/run", {"settings": _settings(tmp_path, replace_existing=True)})
    assert status == 200
    status, body = _get(running_server, "/api/output?" + urllib.parse.urlencode({"path": str(out), "input": SBS}))
    assert body["found"] is True and body["suggested"] == str(tmp_path / "out_2")


def test_the_bundled_vcf_example_is_copied_not_written_into(running_server, tmp_path, monkeypatch):
    monkeypatch.setattr(server.genomes, "installed_genomes", lambda volume=None: ["GRCh37"])
    status, body = _post(running_server, "/api/run", {"settings": {
        "input_type": "vcf", "input_data": str(DATA / "VCFInput"), "output": str(tmp_path / "o"),
        "reference_genome": "GRCh37"}})
    assert status == 200
    config = json.loads((Path(running_server.manager.jobs_dir) / body["job"]["id"] / "config.json").read_text())
    assert config["copy_input"] is True


def test_dashboard_route_serves_only_reports_html_and_sandboxes_it(running_server, tmp_path):
    (tmp_path / "reports.html").write_text("<script>1</script>")
    (tmp_path / "other.html").write_text("<script>1</script>")
    url = _url(running_server, "/api/results/dashboard?" + urllib.parse.urlencode({"path": str(tmp_path / "reports.html")}))
    with urllib.request.urlopen(url, timeout=5) as response:
        policy = response.headers["Content-Security-Policy"]
    assert "sandbox allow-scripts" in policy and "allow-same-origin" not in policy
    assert "default-src 'none'" in policy and "connect-src" not in policy
    status, _ = _get(running_server, "/api/results/dashboard?" + urllib.parse.urlencode({"path": str(tmp_path / "other.html")}))
    assert status == 400


def test_the_dashboard_frame_cannot_act(running_server):
    # A sandboxed frame without allow-same-origin sends Origin: null.
    status, _ = _post(running_server, "/api/quit", headers={"Origin": "null"})
    assert status == 403


def test_only_pdfs_open_inline(running_server, tmp_path):
    (tmp_path / "plot.pdf").write_bytes(b"%PDF-1.4\n")
    (tmp_path / "page.html").write_text("<script>1</script>")
    url = _url(running_server, "/api/results/view?" + urllib.parse.urlencode({"path": str(tmp_path / "plot.pdf")}))
    with urllib.request.urlopen(url, timeout=5) as response:
        assert response.headers["Content-Type"] == "application/pdf"
    status, _ = _get(running_server, "/api/results/view?" + urllib.parse.urlencode({"path": str(tmp_path / "page.html")}))
    assert status == 400


def test_job_detail_includes_progress_for_runs(running_server, tmp_path):
    _, body = _post(running_server, "/api/run", {"settings": _settings(tmp_path)})
    _wait(running_server, body["job"]["id"])
    _, detail = _get(running_server, f"/api/jobs/{body['job']['id']}")
    assert detail["progress"]["phase"] == "done"
    assert [c["name"] for c in detail["progress"]["contexts"]] == ["SBS96"]


def test_deleting_a_run_removes_its_record_and_what_spe_wrote(running_server, tmp_path):
    _, body = _post(running_server, "/api/run", {"settings": _settings(tmp_path)})
    job_id = body["job"]["id"]
    _wait(running_server, job_id)
    out = tmp_path / "out"
    (out / "SBS96" / "All_Solutions").mkdir(parents=True)
    (out / "JOB_METADATA.txt").write_text("x")
    (out / "notes.txt").write_text("mine")
    _, plan = _get(running_server, f"/api/jobs/{job_id}/delete-preview")
    assert plan["deletes_files"] is True and plan["files"] == 1
    status, body = _post(running_server, f"/api/jobs/{job_id}/delete")
    assert status == 200
    assert running_server.manager.get(job_id) is None
    assert not (out / "SBS96").exists() and (out / "notes.txt").is_file()


def test_hide_and_unhide(running_server, tmp_path):
    _, body = _post(running_server, "/api/run", {"settings": _settings(tmp_path)})
    job_id = body["job"]["id"]
    _wait(running_server, job_id)
    assert _post(running_server, f"/api/jobs/{job_id}/hide")[0] == 200
    assert job_id not in [j["id"] for j in _get(running_server, "/api/jobs")[1]["jobs"]]
    assert _post(running_server, f"/api/jobs/{job_id}/unhide")[0] == 200
    assert job_id in [j["id"] for j in _get(running_server, "/api/jobs")[1]["jobs"]]


def test_building_a_dashboard_starts_one_job_per_folder(running_server, tmp_path):
    out = tmp_path / "out"
    (out / "SBS96" / "All_Solutions").mkdir(parents=True)
    (out / "SBS96" / "All_solutions_stat.csv").write_text("Signatures\n1*\n")
    status, body = _post(running_server, "/api/dashboard/build", {"path": str(out)})
    assert status == 200 and body["job"]["kind"] == "dashboard"
    status, _ = _post(running_server, "/api/dashboard/build", {"path": str(tmp_path / "empty")})
    assert status == 400


def test_seeds_check(running_server, tmp_path):
    good = tmp_path / "Seeds.txt"
    good.write_text("\tSeed\n0\t42\n")
    _, body = _get(running_server, "/api/seeds?" + urllib.parse.urlencode({"path": str(good)}))
    assert body["problem"] is None
    _, body = _get(running_server, "/api/seeds?" + urllib.parse.urlencode({"path": str(tmp_path / "no.txt")}))
    assert "does not exist" in body["problem"]


def test_a_browser_that_disconnects_mid_request_is_not_a_server_error(running_server, monkeypatch, capsys):
    def reset(input_type, path):
        raise ConnectionResetError(54, "Connection reset by peer")

    monkeypatch.setattr(server.inputs, "inspect", reset)
    with pytest.raises((urllib.error.URLError, http.client.HTTPException, ConnectionError)):
        _get(running_server, "/api/inspect?type=matrix&path=/tmp")
    assert "[500]" not in capsys.readouterr().err
