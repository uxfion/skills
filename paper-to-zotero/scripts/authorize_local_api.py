# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Obtain and store a key for Zotero's local write API (paper-to-zotero, step 0).

Zotero 10 grants write access to its local API per application: POST
/api/local/authorize makes Zotero show a dialog, and "Always Allow" returns a
persistent key. This script stores that key together with the instance's
Zotero-Server-ID so the write scripts can find it, and when a key already
exists it only reports whether the key still belongs to the running instance.

Output: exactly one JSON object on stdout with a stable `code`; diagnostics
go to stderr. The key itself is never printed (only its first 4 characters).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

DEFAULT_BASE_URL = "http://127.0.0.1:23119"
DEFAULT_KEY_FILE = Path.home() / ".config" / "zotero" / "local-api-key"
DEFAULT_APP_NAME = "paper-to-zotero"
DEFAULT_TIMEOUT = 330  # the authorize request blocks until the user clicks
ENV_KEY = "ZOTERO_LOCAL_API_KEY"

EXIT_OK, EXIT_FAIL, EXIT_CANNOT = 0, 1, 2

# Ignore http_proxy & co.: the local API only listens on the loopback interface.
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

EPILOG = """\
exit codes:
  0  ok                  a usable key is stored (or was found)
  1  not passed          denied | single_use_key | rate_limited | timeout |
                         key_file_invalid | authorize_failed
  2  cannot check        zotero_unreachable | local_api_disabled | server_mismatch |
                         server_id_required | no_server_id | unexpected_response

The authorize request is a gate: Zotero shows a dialog and the request blocks
until the user clicks. Tell the user to click "Always Allow" before running
this ("Allow" gives a single-use key). Zotero limits the dialog to 5 requests
per minute (429 + retry_after).

examples:
  uv run authorize_local_api.py                 # report or authorize
  uv run authorize_local_api.py --force         # authorize again (e.g. new Zotero profile)
"""


class Unreachable(Exception):
    pass


class RequestTimeout(Exception):
    pass


def log(message: str) -> None:
    print(message, file=sys.stderr)


def emit(code: str, exit_code: int = EXIT_OK, **fields) -> None:
    print(json.dumps({"code": code, **fields}, ensure_ascii=False, indent=2))
    sys.exit(exit_code)


def request(base_url: str, method: str, path: str, body=None, headers=None, timeout: float = 30):
    """Return (status, headers, bytes). Raises Unreachable or RequestTimeout."""
    h = {"Accept": "application/json", **(headers or {})}
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(base_url + path, data=data, method=method, headers=h)
    try:
        with OPENER.open(req, timeout=timeout) as resp:
            return resp.status, resp.headers, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()
    except urllib.error.URLError as e:
        if isinstance(e.reason, TimeoutError):
            raise RequestTimeout() from e
        raise Unreachable(str(e.reason)) from e
    except TimeoutError as e:
        raise RequestTimeout() from e
    except OSError as e:
        raise Unreachable(str(e)) from e


def text(body: bytes, limit: int = 300) -> str:
    return body.decode("utf-8", errors="replace").strip()[:limit]


def live_server_id(base_url: str) -> str:
    """GET /api/ and return the running instance's Zotero-Server-ID."""
    try:
        status, headers, body = request(base_url, "GET", "/api/")
    except (Unreachable, RequestTimeout) as e:
        emit("zotero_unreachable", EXIT_CANNOT, base_url=base_url, detail=str(e) or "timed out",
             hint="Zotero is not listening there: wait at the gate (ask the user to start Zotero), then re-run")
    if status == 403:
        emit("local_api_disabled", EXIT_CANNOT, detail=text(body),
             hint="the local API is off: wait at the gate (ask the user to enable it in Zotero Settings > Advanced, "
                  "'Allow other applications on this computer to communicate with Zotero'), then re-run")
    if status != 200:
        emit("unexpected_response", EXIT_CANNOT, status=status, detail=text(body),
             hint="GET /api/ should answer 200; check what is listening on this port")
    server_id = headers.get("Zotero-Server-ID")
    if not server_id:
        emit("no_server_id", EXIT_CANNOT,
             hint="this Zotero sends no Zotero-Server-ID, so it has no local write API; it needs Zotero 10 or newer")
    log(f"GET /api/ -> {status}, server {server_id}")
    return server_id


def read_key_file(path: Path) -> dict | None:
    """Return the stored record, None when the file is absent; exit on a corrupt file."""
    if not path.exists():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(record, dict) or not isinstance(record.get("key"), str) or not record["key"]:
            raise ValueError("no 'key' string")
        return record
    except (OSError, ValueError) as e:
        emit("key_file_invalid", EXIT_FAIL, path=str(path), detail=str(e),
             hint="the key file is unreadable: re-run with --force to replace it")


def save_key_file(path: Path, key: str, server_id: str, app_name: str, remember: bool) -> None:
    """Write the record with mode 0600, replacing any previous file atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "key": key,
        "serverID": server_id,
        "appName": app_name,
        "remember": remember,
        "created": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def authorize(base_url: str, app_name: str, server_id: str, timeout: float):
    """POST /api/local/authorize; returns (status, headers, body, waited_s)."""
    log("Zotero is showing an authorization dialog — click Always Allow")
    started = time.monotonic()
    try:
        status, headers, body = request(base_url, "POST", "/api/local/authorize", {"appName": app_name},
                                        {"Zotero-Server-ID": server_id}, timeout=timeout)
    except RequestTimeout:
        emit("timeout", EXIT_FAIL, waited_s=round(time.monotonic() - started),
             hint="nobody clicked within the wait: the dialog may still be open in Zotero; "
                  "ask the user to click Always Allow, then re-run")
    except Unreachable as e:
        emit("zotero_unreachable", EXIT_CANNOT, detail=str(e),
             hint="the connection dropped while waiting for the dialog: check Zotero is still running, then re-run")
    return status, headers, body, round(time.monotonic() - started)


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Obtain and store a key for Zotero's local write API, or report whether the stored key "
                    "still matches the running Zotero instance.",
        epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--key-file", type=Path, default=DEFAULT_KEY_FILE,
                        help="where the key is stored as JSON, mode 0600 (default: %(default)s); "
                             f"the environment variable {ENV_KEY} overrides the stored key")
    parser.add_argument("--app-name", default=DEFAULT_APP_NAME,
                        help="name shown in Zotero's authorization dialog (default: %(default)s)")
    parser.add_argument("--force", action="store_true",
                        help="authorize again even if a key is already stored (replaces the key file)")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL,
                        help="Zotero's local server (default: %(default)s)")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                        help="seconds to wait for the user's click on the dialog (default: %(default)s)")
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    base_url = args.base_url.rstrip("/")
    server_id = live_server_id(base_url)

    if not args.force:
        env_key = os.environ.get(ENV_KEY)
        if env_key:
            log(f"key from {ENV_KEY}")
            emit("ok", EXIT_OK, source="env", key_prefix=env_key[:4], server_id=server_id,
                 server_match=None)
        record = read_key_file(args.key_file)
        if record is not None:
            stored = record.get("serverID")
            log(f"key file {args.key_file}: stored server {stored}")
            if stored != server_id:
                emit("server_mismatch", EXIT_CANNOT, source="file", path=str(args.key_file),
                     key_prefix=record["key"][:4], server_match=False,
                     stored_server_id=stored, server_id=server_id,
                     hint="the stored key belongs to another Zotero instance: "
                          "re-run with --force to authorize this Zotero instance")
            emit("ok", EXIT_OK, source="file", path=str(args.key_file), key_prefix=record["key"][:4],
                 server_match=True, server_id=server_id, remember=record.get("remember"))
        log("no key stored")

    status, headers, body, waited_s = authorize(base_url, args.app_name, server_id, args.timeout)
    log(f"POST /api/local/authorize -> {status} after {waited_s}s")

    if status == 200:
        try:
            granted = json.loads(body)
            key = granted["key"]
            remember = bool(granted.get("remember"))
            if not isinstance(key, str) or not key:
                raise ValueError("empty key")
        except (ValueError, KeyError, TypeError) as e:
            emit("authorize_failed", EXIT_FAIL, status=status, detail=f"unexpected body: {e}",
                 hint="Zotero answered 200 without a key; report the response body")
        save_key_file(args.key_file, key, server_id, args.app_name, remember)
        common = dict(source="authorize", remember=remember, key_prefix=key[:4], path=str(args.key_file),
                      server_id=server_id, waited_s=waited_s)
        if remember:
            emit("ok", EXIT_OK, **common)
        emit("single_use_key", EXIT_FAIL, **common,
             hint="the user clicked Allow, so this key dies after one write: "
                  "re-run with --force and ask for Always Allow")

    if status == 403:
        try:
            denied = json.loads(body).get("denied") is True
        except (ValueError, AttributeError):
            denied = False
        if denied:
            emit("denied", EXIT_FAIL, waited_s=waited_s,
                 hint="the user declined (or closed) the dialog: ask before re-running")
        emit("local_api_disabled", EXIT_CANNOT, detail=text(body),
             hint="the local API was switched off: wait at the gate (ask the user to enable it), then re-run")

    if status == 429:
        try:
            retry_after = int(headers.get("Retry-After", ""))
        except ValueError:
            retry_after = None
        emit("rate_limited", EXIT_FAIL, retry_after=retry_after,
             hint="Zotero limits authorization dialogs to 5 per minute: wait retry_after seconds, then re-run")

    if status == 428:
        emit("server_id_required", EXIT_CANNOT, detail=text(body),
             hint="Zotero says Zotero-Server-ID was missing although it was sent; report this as a script bug")

    if status == 412:
        emit("server_mismatch", EXIT_CANNOT, detail=text(body), server_id=server_id,
             hint="the server ID changed between the two requests (Zotero restarted?): re-run")

    emit("authorize_failed", EXIT_FAIL, status=status, detail=text(body),
         hint="unexpected answer from /api/local/authorize; report status and detail")


if __name__ == "__main__":
    main()
