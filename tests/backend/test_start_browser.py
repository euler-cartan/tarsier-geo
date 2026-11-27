"""TRS-105 (TAD §2.2): `tarsier-geo start` opens the browser only once the server answers."""

import argparse
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from tarsier.cli import main as cli


@pytest.fixture(autouse=True)
def opened(monkeypatch, tmp_path):
    """Record browser openings instead of opening a real browser."""
    urls = []
    monkeypatch.setattr(cli.webbrowser, "open", urls.append)
    monkeypatch.setattr(cli, "run_state_path", lambda: tmp_path / "run.json")
    monkeypatch.setenv("TARSIER_SCHEDULER", "0")  # `start` sets it; restore afterwards
    return urls


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _fake_server(port, asked, answer):
    """A health endpoint that notes each request and replies only once `answer` is set."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            asked.set()
            answer.wait(10)
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _browser_threads():
    return [t for t in threading.enumerate() if t.name == "tarsier-open-browser"]


def test_browser_opens_only_after_a_slow_server_answers(monkeypatch, opened):
    port = _free_port()
    asked, answer = threading.Event(), threading.Event()
    seen = {}

    def slow_run(*args, **kwargs):
        time.sleep(0.6)  # not listening yet
        seen["before_listening"] = list(opened)
        server = _fake_server(port, asked, answer)
        try:
            assert asked.wait(5), "the server was never asked"
            time.sleep(0.6)  # listening, but not answering yet
            seen["before_answer"] = list(opened)
            answer.set()
            for thread in _browser_threads():
                thread.join(5)
        finally:
            server.shutdown()
            server.server_close()

    monkeypatch.setattr(cli.uvicorn, "run", slow_run)

    assert cli._cmd_start(argparse.Namespace(port=port, no_browser=False)) == 0
    assert seen == {"before_listening": [], "before_answer": []}
    assert opened == [f"http://localhost:{port}"]


def test_gives_up_after_30_seconds_and_prints_the_address(monkeypatch, opened, capsys):
    now = [0.0]
    checks = []

    def never_answers(port, timeout):
        checks.append(now[0])
        return False

    fake_clock = SimpleNamespace(monotonic=lambda: now[0], sleep=lambda s: now.__setitem__(0, now[0] + s))
    monkeypatch.setattr(cli, "time", fake_clock)
    monkeypatch.setattr(cli, "_server_answers", never_answers)

    cli._open_browser_when_ready(38899, "http://localhost:38899")

    assert now[0] == 30
    assert checks == [n * 0.25 for n in range(120)]
    assert opened == []
    output = capsys.readouterr().out
    assert "browser was not opened" in output
    assert "http://localhost:38899" in output


def test_no_browser_never_opens(monkeypatch, opened):
    port = _free_port()
    asked, answer = threading.Event(), threading.Event()
    answer.set()

    def ready_run(*args, **kwargs):
        server = _fake_server(port, asked, answer)
        try:
            time.sleep(0.6)
            assert _browser_threads() == []
        finally:
            server.shutdown()
            server.server_close()

    monkeypatch.setattr(cli.uvicorn, "run", ready_run)

    assert cli._cmd_start(argparse.Namespace(port=port, no_browser=True)) == 0
    assert not asked.is_set()
    assert opened == []
