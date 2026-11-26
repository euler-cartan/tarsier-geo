"""`tarsier-geo` command-line entry point: start/stop (TAD §2.2, §2.3)."""

import argparse
import json
import os
import signal
import sys
import webbrowser

import uvicorn

from tarsier.cli.ports import DEFAULT_PORT, find_free_port, is_port_free
from tarsier.storage.paths import run_state_path


def _cmd_start(args: argparse.Namespace) -> int:
    state_file = run_state_path()
    if state_file.exists():
        if _recorded_server_is_up(state_file):
            print(
                "Tarsier appears to already be running "
                f"(state file: {state_file}). Run `tarsier-geo stop` first."
            )
            return 1
        # Left behind by a crash, a closed terminal or a power cut. Nothing is
        # listening on the recorded port, so it is safe to start again.
        state_file.unlink(missing_ok=True)

    if args.port is not None:
        port = args.port
        if not is_port_free(port):
            print(f"Port {port} is already in use. Choose a different --port.")
            return 1
    else:
        port = find_free_port(DEFAULT_PORT)

    os.environ.setdefault("TARSIER_SCHEDULER", "1")
    url = f"http://localhost:{port}"
    print(f"Tarsier is running at {url}", flush=True)

    state_file.write_text(json.dumps({"pid": os.getpid(), "port": port}))

    if not args.no_browser:
        webbrowser.open(url)

    try:
        uvicorn.run("tarsier.api.app:create_app", factory=True, host="127.0.0.1", port=port)
    finally:
        state_file.unlink(missing_ok=True)

    return 0


def _recorded_server_is_up(state_file) -> bool:
    try:
        port = int(json.loads(state_file.read_text()).get("port"))
    except (OSError, ValueError, TypeError):
        return False
    return not is_port_free(port)


def _cmd_stop(args: argparse.Namespace) -> int:
    state_file = run_state_path()
    if not state_file.exists():
        print("Tarsier is not running.")
        return 0

    # Only signal the recorded process while its port is still being served:
    # after a crash the operating system may have given that PID to an
    # unrelated program.
    if not _recorded_server_is_up(state_file):
        state_file.unlink(missing_ok=True)
        print("Tarsier was not running (stale state file removed).")
        return 0

    pid = json.loads(state_file.read_text()).get("pid")
    try:
        os.kill(pid, signal.SIGTERM)
        print(f"Stopped Tarsier (pid {pid}).")
    except (ProcessLookupError, OSError, TypeError):
        print("Tarsier was not running (stale state file removed).")
    finally:
        state_file.unlink(missing_ok=True)

    return 0


def _cmd_archive(args: argparse.Namespace) -> int:
    from tarsier.cli.backup import backup, restore
    try:
        result = (backup if args.command == "backup" else restore)(args.path)
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"{args.command.title()} complete: {result}. Credentials excluded; re-enter passwords and AI/notification settings after restore.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tarsier-geo")
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="Start the Tarsier server")
    start.add_argument("--port", type=int, default=None, help="Force a specific port")
    start.add_argument(
        "--no-browser", action="store_true", help="Don't auto-open the browser"
    )
    start.set_defaults(func=_cmd_start)

    stop = sub.add_parser("stop", help="Stop the running Tarsier server")
    stop.set_defaults(func=_cmd_stop)

    for command in ("backup", "restore"):
        archive = sub.add_parser(command, help=f"{command.title()} Tarsier state without credentials")
        archive.add_argument("path")
        archive.set_defaults(func=_cmd_archive)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
