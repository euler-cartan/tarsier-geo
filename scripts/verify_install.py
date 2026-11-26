"""Proves TRS-104 (TAD §2): a fresh `pip install` of the built wheel gives a working app.

Needs only Python 3.11+ (no Docker, no Node, no database server). Only Windows
is qualified so far. The data folder is a temporary one. It:

1. makes a brand-new virtual environment,
2. installs the given wheel into it (pulling every dependency from PyPI),
3. starts `tarsier-geo start --port N --no-browser` from that environment,
4. checks the API answers, the bundled UI is served (no separate build step),
   and a deep link falls back to the UI,
5. stops it with `tarsier-geo stop`.

Usage:  python scripts/verify_install.py path/to/tarsier_geo-*.whl
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from test_home_guard import require_test_home
from test_server_guard import validate_test_server_port


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def fetch(url: str) -> tuple[int, str]:
    with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310 - loopback only
        return response.status, response.read().decode("utf-8", errors="replace")


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    print("$", " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=True, **kwargs)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    wheel = args.wheel.resolve()
    if not wheel.exists():
        print(f"No such wheel: {wheel}")
        return 2

    try:
        qa_home = require_test_home()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    qa_home.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="tarsier-install-", dir=qa_home) as scratch:
        scratch_path = Path(scratch)
        venv = scratch_path / "venv"
        run([sys.executable, "-m", "venv", str(venv)])
        bin_dir = venv / ("Scripts" if os.name == "nt" else "bin")
        python = bin_dir / ("python.exe" if os.name == "nt" else "python")
        cli = bin_dir / ("tarsier-geo.exe" if os.name == "nt" else "tarsier-geo")

        # cwd=scratch everywhere: never import a source tree that happens to be nearby
        run([str(python), "-m", "pip", "install", "--quiet", str(wheel)], cwd=scratch)
        assert cli.exists(), "the tarsier-geo command was not installed"
        run([str(python), "-c", "import tarsier, rasterio, pyogrio, geopandas, psycopg; print('imports ok', tarsier.__version__)"], cwd=scratch)

        home = scratch_path / "home"
        env = {**os.environ, "TARSIER_HOME": str(home)}
        port = free_port()
        while port in (5432, 5433):
            port = free_port()
        validate_test_server_port(port)
        server = subprocess.Popen(
            [str(cli), "start", "--port", str(port), "--no-browser"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=scratch,  # not the source tree: only the installed package may be used
        )
        base = f"http://127.0.0.1:{port}"
        try:
            deadline = time.time() + 60
            health = None
            while time.time() < deadline:
                if server.poll() is not None:
                    print(server.stdout.read())
                    print("server exited early")
                    return 1
                try:
                    status, body = fetch(f"{base}/api/health")
                    health = json.loads(body)
                    break
                except Exception:
                    time.sleep(0.5)
            assert health and health["status"] == "ok", "API never became healthy"
            print("health:", health)

            status, home_page = fetch(f"{base}/")
            assert status == 200 and '<div id="root">' in home_page, "bundled UI not served"
            status, deep = fetch(f"{base}/connections/abc/overview")
            assert status == 200 and '<div id="root">' in deep, "deep link did not fall back to the UI"
            asset = next(
                (part.split('"')[0] for part in home_page.split('src="')[1:] if part.startswith("/assets/")), None
            )
            assert asset, "no bundled script referenced by the UI"
            status, _ = fetch(f"{base}{asset}")
            assert status == 200, f"bundled asset {asset} not served"
            status, body = fetch(f"{base}/api/connections/types")
            assert status == 200 and "files" in body
        finally:
            run([str(cli), "stop"], env=env, cwd=scratch)
            try:
                server.wait(timeout=20)
            except subprocess.TimeoutExpired:
                server.kill()
        print("INSTALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
