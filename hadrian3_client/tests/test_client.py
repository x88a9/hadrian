"""Unit tests for hadrian3_client.Client using httpx.MockTransport."""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys

import httpx
import pytest

from hadrian3_client import Client, Hadrian3ClientError


def make_client(handler) -> Client:
    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport, base_url="http://testserver")
    # api_url must match base_url so absolute URLs resolve through the transport.
    return Client(api_url="http://testserver", http_client=http)


# -- create_system --------------------------------------------------------


def test_create_system_url_and_payload_drops_none():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        captured["json"] = json.loads(request.content)
        return httpx.Response(201, json={"id": 1, "name": "EMA-M1-900.demo"})

    client = make_client(handler)
    out = client.create_system("EMA-M1-900.demo", entry_rule="cross", tp_rule="Demo")

    assert captured["method"] == "POST"
    assert captured["url"] == "http://testserver/systems"
    assert captured["json"] == {
        "name": "EMA-M1-900.demo",
        "entry_rule": "cross",
        "tp_rule": "Demo",
    }
    # None fields (sl_rule, notes, status) must be absent.
    assert "sl_rule" not in captured["json"]
    assert "notes" not in captured["json"]
    assert "status" not in captured["json"]
    assert out == {"id": 1, "name": "EMA-M1-900.demo"}


# -- log_trade ------------------------------------------------------------


def test_log_trade_payload_and_datetime_serialisation():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json={"id": 5})

    client = make_client(handler)
    when = dt.datetime(2024, 3, 4, 15, 0, 0)
    client.log_trade(
        system_name="EMA-M1-900.demo",
        r_value=2.1,
        trade_datetime=when,
        direction="long",
        entry=64123.5,
    )

    assert captured["url"] == "http://testserver/trades"
    assert captured["json"] == {
        "system_name": "EMA-M1-900.demo",
        "r_value": 2.1,
        "trade_datetime": "2024-03-04T15:00:00",
        "direction": "long",
        "entry": 64123.5,
    }
    # Untouched optional fields must not appear.
    assert "system_id" not in captured["json"]
    assert "sl" not in captured["json"]


def test_log_trade_accepts_date_object():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json={"id": 6})

    client = make_client(handler)
    client.log_trade(system_id=3, trade_datetime=dt.date(2025, 1, 2), r_value=-1.0)
    assert captured["json"]["trade_datetime"] == "2025-01-02"
    assert captured["json"]["system_id"] == 3


# -- bulk_import ----------------------------------------------------------


class _StubDF:
    """Minimal DataFrame stand-in exposing .to_csv(index=False) -> str."""

    def __init__(self, csv: str) -> None:
        self._csv = csv
        self.calls: list = []

    def to_csv(self, index=True):  # noqa: ARG002 - mirror pandas signature
        self.calls.append(index)
        return self._csv


def _parse_multipart(request: httpx.Request) -> dict:
    content_type = request.headers["content-type"]
    boundary = content_type.split("boundary=")[1].encode()
    body = request.content
    parts = body.split(b"--" + boundary)
    result: dict = {}
    for part in parts:
        # Each real part looks like: b"\r\n<headers>\r\n\r\n<payload>\r\n".
        # Strip exactly the leading/trailing CRLF delimiters (not the
        # payload's own trailing newline).
        if part.startswith(b"\r\n"):
            part = part[2:]
        if part.endswith(b"\r\n"):
            part = part[:-2]
        if not part or part == b"--":
            continue
        headers, sep, payload = part.partition(b"\r\n\r\n")
        if not sep:
            continue
        disp = headers.decode()
        name = disp.split('name="')[1].split('"')[0]
        result[name] = payload
    return result


def test_bulk_import_with_dataframe_like():
    captured: dict = {}
    csv_content = "entry_time,net_r\n2024-01-01T00:00:00,2.0\n"

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["parts"] = _parse_multipart(request)
        return httpx.Response(200, json={"tabs_total": 1, "trades_imported": 1})

    client = make_client(handler)
    stub = _StubDF(csv_content)
    out = client.bulk_import(stub, "EMA-M1-900.demo", replace=True)

    assert stub.calls == [False]  # to_csv(index=False)
    assert captured["url"] == "http://testserver/import/csv"
    parts = captured["parts"]
    assert parts["system_name"] == b"EMA-M1-900.demo"
    assert parts["replace"] == b"true"
    assert parts["file"] == csv_content.encode("utf-8")
    assert out == {"tabs_total": 1, "trades_imported": 1}


def test_bulk_import_replace_false_flag():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["parts"] = _parse_multipart(request)
        return httpx.Response(200, json={})

    client = make_client(handler)
    client.bulk_import(b"a,b\n1,2\n", "SYS-1", replace=False)
    assert captured["parts"]["replace"] == b"false"


def test_bulk_import_with_bytes():
    captured: dict = {}
    raw = b"entry_time,net_r\n2024-05-05T00:00:00,-1.0\n"

    def handler(request: httpx.Request) -> httpx.Response:
        captured["parts"] = _parse_multipart(request)
        return httpx.Response(200, json={})

    client = make_client(handler)
    client.bulk_import(raw, "SYS-2")
    assert captured["parts"]["file"] == raw


def test_bulk_import_with_str_csv_content():
    captured: dict = {}
    csv_str = "entry_time,net_r\n2024-06-06T00:00:00,1.5\n"

    def handler(request: httpx.Request) -> httpx.Response:
        captured["parts"] = _parse_multipart(request)
        return httpx.Response(200, json={})

    client = make_client(handler)
    # Not an existing path -> treated as raw CSV content.
    client.bulk_import(csv_str, "SYS-3")
    assert captured["parts"]["file"] == csv_str.encode("utf-8")


def test_bulk_import_with_file_path(tmp_path):
    captured: dict = {}
    p = tmp_path / "trades.csv"
    content = "entry_time,net_r\n2024-07-07T00:00:00,0.5\n"
    p.write_text(content)

    def handler(request: httpx.Request) -> httpx.Response:
        captured["parts"] = _parse_multipart(request)
        return httpx.Response(200, json={})

    client = make_client(handler)
    client.bulk_import(str(p), "SYS-4")
    assert captured["parts"]["file"] == content.encode("utf-8")


# -- error handling -------------------------------------------------------


def test_error_response_raises_with_detail():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "System not found"})

    client = make_client(handler)
    with pytest.raises(Hadrian3ClientError) as exc:
        client.log_trade(system_name="nope", r_value=1.0)
    assert exc.value.status_code == 404
    assert exc.value.detail == "System not found"


def test_error_response_non_json_falls_back_to_text():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    client = make_client(handler)
    with pytest.raises(Hadrian3ClientError) as exc:
        client.create_system("x")
    assert exc.value.status_code == 500
    assert exc.value.detail == "boom"


# -- pandas isolation guard ----------------------------------------------


def test_import_does_not_pull_pandas():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import hadrian3_client, sys; "
            "assert 'pandas' not in sys.modules; print('ok')",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout
