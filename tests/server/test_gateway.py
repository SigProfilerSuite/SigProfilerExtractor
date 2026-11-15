"""The server gateway (server/gateway/spe_gateway.py): who gets in, and where to.

The gateway is what stands between the Workbench, which has no login, and a
network. These tests run it in-process on a free port, as spe-server does,
and check its sign-in, its cookie, the Workbench's own POST checks behind it,
and the requests it refuses.
"""

import http.client
import json
import os
import socket
import sys
import threading
import time
from pathlib import Path
from urllib.parse import quote

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server" / "gateway"))
import spe_gateway as gw  # noqa: E402
from SigProfilerExtractor.web import server as workbench  # noqa: E402

TOKEN = "t" * 48
FORM = {"Content-Type": "application/x-www-form-urlencoded"}


@pytest.fixture
def gateway(tmp_path):
    srv = workbench.make_server("127.0.0.1", 0, tmp_path / "state" / "jobs")
    srv.RequestHandlerClass = gw.GatewayHandler
    srv.gateway_token = TOKEN
    srv.resources = gw.Resources()
    srv.picker = "page"
    srv.public_hosts = None
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield srv
    finally:
        srv.shutdown()
        thread.join(timeout=5)
        srv.server_close()


def _req(srv, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=10)
    try:
        conn.request(method, path, body=body, headers=headers or {})
        r = conn.getresponse()
        return r.status, dict(r.getheaders()), r.read()
    finally:
        conn.close()


def _host(srv):
    return f"127.0.0.1:{srv.server_address[1]}"


def _cookie(srv):
    return {"Cookie": f"spe_gateway_{srv.server_address[1]}={TOKEN}"}


# ------------------------------------------------------------ signing in


def test_without_the_cookie_pages_go_to_sign_in_and_the_api_is_refused(gateway):
    status, headers, _ = _req(gateway, "GET", "/")
    assert status == 303 and headers["Location"].startswith("/gateway/login?next=")
    status, _, _ = _req(gateway, "GET", "/api/env")
    assert status == 401


def test_a_wrong_token_stays_out(gateway):
    status, headers, _ = _req(gateway, "GET", "/?token=" + "x" * 48)
    assert status == 303 and "Set-Cookie" not in headers
    status, _, _ = _req(gateway, "POST", "/gateway/login", body="token=wrong&next=/", headers=FORM)
    assert status == 403


def test_the_token_sets_a_private_cookie_and_leaves_the_address(gateway):
    status, headers, _ = _req(gateway, "GET", f"/?token={TOKEN}&view=results")
    assert status == 303 and headers["Location"] == "/?view=results"
    cookie = headers["Set-Cookie"]
    assert f"={TOKEN}" in cookie and "HttpOnly" in cookie and "SameSite=Lax" in cookie
    status, _, _ = _req(gateway, "GET", "/api/env", headers=_cookie(gateway))
    assert status == 200


def test_a_token_that_is_not_ascii_is_refused_not_a_crash(gateway):
    status, _, _ = _req(gateway, "GET", "/api/env",
                        headers={"Cookie": f"spe_gateway_{gateway.server_address[1]}=été"})
    assert status == 401
    status, _, _ = _req(gateway, "POST", "/gateway/login",
                        body=b"token=%C3%A9t%C3%A9&next=/", headers=FORM)
    assert status == 403


@pytest.mark.parametrize("given, kept", [
    ("/\\evil.example", "/"),
    ("//evil.example", "/"),
    ("/%5Cevil.example", "/%5Cevil.example"),   # still encoded: a path here, not a host
    ("https://evil.example/", "/"),
    ("evil.example", "/"),
    ("/ok\r\nSet-Cookie: x=1", "/"),
    ("/ok?a=1", "/ok?a=1"),
    ("/", "/"),
])
def test_sign_in_goes_only_to_a_path_on_this_server(gateway, given, kept):
    status, headers, _ = _req(gateway, "POST", "/gateway/login",
                              body=f"token={TOKEN}&next={quote(given, safe='')}", headers=FORM)
    assert status == 303 and headers["Location"] == kept


def test_the_sign_in_page_does_not_carry_a_foreign_target(gateway):
    status, _, body = _req(gateway, "GET", "/gateway/login?next=/%5Cevil.example")
    assert status == 200
    assert b'name="next" value="/"' in body


def test_a_bad_sign_in_length_is_refused_at_once(gateway):
    for length in ("-1", "70000", "lots"):
        start = time.monotonic()
        with socket.create_connection(("127.0.0.1", gateway.server_address[1]), timeout=5) as s:
            s.sendall(f"POST /gateway/login HTTP/1.1\r\nHost: {_host(gateway)}\r\n"
                      f"Content-Type: application/x-www-form-urlencoded\r\n"
                      f"Content-Length: {length}\r\n\r\ntoken=".encode())
            reply = s.recv(4096)
        assert reply.split(b" ", 2)[1] == b"400", (length, reply[:80])
        assert time.monotonic() - start < 3


# ------------------------------------------------------------ once signed in


def test_a_cross_site_post_is_refused_and_a_same_origin_one_passes(gateway):
    base = {**_cookie(gateway), "Content-Type": "application/json",
            "X-Dashboard-Token": gateway.instance_token}
    body = json.dumps({}).encode()
    status, _, _ = _req(gateway, "POST", "/api/jobs/none/hide", body=body,
                        headers={**base, "Origin": "http://evil.example"})
    assert status == 403
    status, _, _ = _req(gateway, "POST", "/api/jobs/none/hide", body=body,
                        headers={**base, "Origin": f"http://{_host(gateway)}"})
    assert status != 403


def test_a_page_token_that_is_not_ascii_is_refused_not_a_crash(gateway):
    status, _, _ = _req(gateway, "POST", "/api/jobs/none/hide", body=b"{}", headers={
        **_cookie(gateway), "Content-Type": "application/json",
        "Origin": f"http://{_host(gateway)}", "X-Dashboard-Token": "été"})
    assert status == 403


# ------------------------------------------------------------ the link


def test_the_printed_link_has_no_token_and_the_url_file_is_private(tmp_path, capsys):
    url_file = tmp_path / "url"
    gw.announce(8765, TOKEN, url_file)
    assert TOKEN not in capsys.readouterr().out
    assert TOKEN in url_file.read_text()
    if os.name == "posix":
        assert url_file.stat().st_mode & 0o777 == 0o600
