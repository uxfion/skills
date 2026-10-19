# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Report the facts an import run needs and prepare its work directory (paper-to-zotero, step 0).

One call answers: is Zotero's local API up; is a usable write key stored
(with --authorize and no usable key, obtain one: Zotero shows a dialog and
the user must click Always Allow); are pdftotext and pdfinfo (poppler-utils)
on PATH; what the config file holds; where the browser puts downloads; is
opencli on PATH. It creates <work>/records/, <work>/scratch/ and the
<work>/.started marker (an existing marker is left alone and its mtime
reported: that is a resumed run), lists what already lies in <work>
(never deleting anything) and prints the library's collection tree with
paths such as "自然图像/Diffusion".

Config: one JSON file, $PAPER_TO_ZOTERO_CONFIG or
~/.config/paper-to-zotero/config.json, mode 0600, every field optional:
{"zotero": {"key", "serverID"}, "openalex_key", "institution": {"proxy",
"discovery"}}. --authorize writes the "zotero" block and keeps the rest.
Only presence is reported, never a value.

Downloads directory: --downloads > $PAPER_TO_ZOTERO_DOWNLOADS > under WSL
the Windows Downloads folder (powershell.exe, then cmd.exe %USERPROFILE%)
> xdg-user-dir DOWNLOAD > ~/Downloads; a directory that does not exist
gives null, not a failure.

stdout: exactly one JSON object with a stable `code` (`ok` when ready);
diagnostics go to stderr; the key itself is never printed. Exit 0 = ready,
1 = not ready (no_key, authorize_denied, authorize_timeout,
authorize_single_use, authorize_failed), 2 = cannot check
(zotero_unreachable, local_api_disabled, server_mismatch, config_unreadable,
no_pdftotext: install poppler-utils, see references/install.md).
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

DEFAULT_BASE_URL = "http://127.0.0.1:23119"
DEFAULT_WORK = os.path.join(os.environ.get("TMPDIR") or "/tmp", "paper-to-zotero")
DEFAULT_SESSION = "p2z"
ENV_CONFIG = "PAPER_TO_ZOTERO_CONFIG"
ENV_DOWNLOADS = "PAPER_TO_ZOTERO_DOWNLOADS"
APP_NAME = "paper-to-zotero"
AUTHORIZE_WAIT = 300  # seconds the user gets to click Always Allow
LIB = "/api/users/0"
PAGE = 100
KINDS = {".pdf": "pdf", ".html": "html", ".htm": "html", ".json": "json"}
PS_DOWNLOADS = ("[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
                "(New-Object -ComObject Shell.Application).NameSpace('shell:Downloads').Self.Path")
WIN_PATH_RE = re.compile(r"^[A-Za-z]:\\")

HINT_NO_KEY = ("No usable local API key. Tell the user that Zotero will show an authorization dialog and that they "
               "must click Always Allow (Allow gives a single-use key); then re-run with --authorize.")
HINT_DENIED = "The user declined or closed the authorization dialog; ask before re-running with --authorize."
HINT_TIMEOUT = ("Nobody clicked within the wait; the dialog may still be open in Zotero. Ask the user to click "
                "Always Allow, then re-run with --authorize.")
HINT_SINGLE_USE = ("The user clicked Allow, so the key would die after one write; nothing was saved. Ask for "
                   "Always Allow, then re-run with --authorize.")
HINT_MISMATCH = ("The stored key was issued by another Zotero instance; re-run with --authorize to authorize "
                 "this one (the config's zotero block is replaced).")
HINT_NO_PDFTOTEXT = ("pdftotext and pdfinfo (poppler-utils, a system package) are required to check PDFs; tell the "
                     "user and install it only with their OK (references/install.md).")
HINT_UNREACHABLE = "Start Zotero, then retry; check --base-url if it is not the default."
HINT_DISABLED = ("Ask the user to enable the local API in Zotero Settings > Advanced ('Allow other applications "
                 "on this computer to communicate with Zotero'), then retry.")


class Stop(Exception):
    """Carry a result code out of any depth; main() turns it into JSON + exit."""

    def __init__(self, code, exit_code=1, hint=None, **extra):
        super().__init__(code)
        self.code, self.exit_code, self.hint, self.extra = code, exit_code, hint, extra


class RequestTimeout(Exception):
    """Zotero accepted the connection but did not answer in time (e.g. the dialog is still open)."""


def log(msg):
    print(msg, file=sys.stderr)


def emit(code, exit_code=0, hint=None, **extra):
    out = {"code": code, **extra}
    if hint and exit_code != 0:
        out["hint"] = hint
    print(json.dumps(out, ensure_ascii=False, indent=2))
    sys.exit(exit_code)


def text(body, limit=400):
    return body.decode("utf-8", errors="replace").strip()[:limit]


class Api:
    """Minimal client for the local API; bypasses any proxy from the environment."""

    def __init__(self, base_url, timeout=30):
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self, method, path, body=None, headers=None, timeout=None):
        h = {"Accept": "application/json"}
        h.update(headers or {})
        data = None
        if isinstance(body, (dict, list)):
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            h.setdefault("Content-Type", "application/json")
        elif body is not None:
            data = str(body).encode("utf-8")
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=h)
        try:
            with self.opener.open(req, timeout=timeout or self.timeout) as resp:
                return resp.status, resp.headers, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()
        except urllib.error.URLError as e:
            if isinstance(e.reason, TimeoutError):
                raise RequestTimeout() from e
            raise Stop("zotero_unreachable", 2, HINT_UNREACHABLE, base_url=self.base, error=str(e.reason))
        except TimeoutError as e:
            raise RequestTimeout() from e
        except OSError as e:
            raise Stop("zotero_unreachable", 2, HINT_UNREACHABLE, base_url=self.base, error=str(e))


def get(api, path):
    """GET that turns the 'cannot check' answers into Stop; returns (status, headers, body) otherwise."""
    try:
        status, headers, body = api.request("GET", path)
    except RequestTimeout:
        raise Stop("zotero_unreachable", 2, HINT_UNREACHABLE, base_url=api.base, error="timed out")
    if status == 403:
        raise Stop("local_api_disabled", 2, HINT_DISABLED, status=status, body=text(body))
    return status, headers, body


def live_server_id(api):
    status, headers, body = get(api, "/api/")
    sid = headers.get("Zotero-Server-ID")
    if status != 200 or not sid:
        raise Stop("zotero_unreachable", 2, "The endpoint does not behave like Zotero's local API (Zotero 10 or newer "
                   "sends Zotero-Server-ID); check --base-url.", status=status, body=text(body))
    log(f"GET /api/ -> {status}, server {sid}")
    return sid


def config_path():
    return Path(os.environ.get(ENV_CONFIG) or Path.home() / ".config" / "paper-to-zotero" / "config.json")


def read_config():
    """The config file as a dict; {} when it does not exist. An unparseable file stops the run: --authorize must not
    overwrite what it cannot read."""
    path = config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        raise Stop("config_unreadable", 2, "Fix or remove the config file, then retry.", config=str(path), error=str(e))
    if not isinstance(data, dict):
        raise Stop("config_unreadable", 2, "The config file must hold one JSON object.", config=str(path))
    return data


def config_summary(config):
    """Which settings are present, never their values; plus a warning when others can read the file."""
    path = config_path()
    inst = config.get("institution") if isinstance(config.get("institution"), dict) else {}
    zot = config.get("zotero") if isinstance(config.get("zotero"), dict) else {}
    out = {"file": str(path), "exists": path.is_file(), "zotero_key": bool(zot.get("key")),
           "openalex_key": bool(config.get("openalex_key")),
           "institution": {"proxy": bool(inst.get("proxy")), "discovery": bool(inst.get("discovery"))}}
    if not inst.get("discovery"):
        out["ask_user"] = ("institution.discovery: the chain's discovery route needs the library's search page (a Primo "
                           "search URL); ask the user for it in your first message and add it to the config")
    try:
        if path.is_file() and path.stat().st_mode & 0o077:
            out["warning"] = "loose_permissions: run chmod 600 on the config file"
    except OSError:
        pass
    return out


def key_status(config, server_id):
    """What is known about the write key without ever reading it into the output: present, issued by this instance."""
    zot = config.get("zotero") if isinstance(config.get("zotero"), dict) else {}
    status = {"present": False, "server_match": None}
    if not isinstance(zot.get("key"), str) or not zot["key"]:
        log(f"no zotero key in {config_path()}")
        return status
    status["present"] = True
    saved = zot.get("serverID")
    status["server_match"] = None if not saved else saved == server_id
    if status["server_match"] is False:
        log(f"zotero key issued by server {saved}, the running server is {server_id}")
    return status


def key_usable(status):
    return status["present"] and status["server_match"] is not False


def save_key(key, server_id):
    """Write the "zotero" block into the config file, keeping every other field; mode 0600, replaced atomically."""
    path = config_path()
    config = read_config()
    config["zotero"] = {"key": key, "serverID": server_id,
                        "created": datetime.now().astimezone().isoformat(timespec="seconds")}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def find_poppler():
    return {name: shutil.which(name) for name in ("pdftotext", "pdfinfo")}


def retry_after(headers, body):
    """Seconds Zotero asks us to wait after a 429: the Retry-After header, else the JSON body, else 15."""
    try:
        return max(1, int(headers.get("Retry-After", "")))
    except ValueError:
        pass
    try:
        info = json.loads(body)
        return max(1, int(info.get("retryAfter") or info.get("retry_after")))
    except (ValueError, TypeError, AttributeError):
        return 15


def authorize(api, server_id, wait):
    """POST /api/local/authorize: Zotero shows a dialog and answers when the user clicks; 429 waits Retry-After.

    Returns (code, hint, extra). Saves the key on success; a single-use key (Allow) is not saved.
    """
    log("Zotero is showing an authorization dialog: the user must click Always Allow")
    started = time.monotonic()
    deadline = started + wait
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return "authorize_timeout", HINT_TIMEOUT, {"waited_s": round(time.monotonic() - started)}
        try:
            status, headers, body = api.request("POST", "/api/local/authorize", {"appName": APP_NAME},
                                                {"Zotero-Server-ID": server_id}, timeout=remaining)
        except RequestTimeout:
            return "authorize_timeout", HINT_TIMEOUT, {"waited_s": round(time.monotonic() - started)}
        waited = round(time.monotonic() - started)
        log(f"POST /api/local/authorize -> {status} after {waited}s")
        if status != 429:
            break
        delay = retry_after(headers, body)
        if time.monotonic() + delay > deadline:
            return "authorize_timeout", HINT_TIMEOUT, {"waited_s": waited, "retry_after": delay}
        log(f"rate limited (5 dialogs per minute); waiting {delay}s")
        time.sleep(delay)

    if status == 200:
        try:
            granted = json.loads(body)
            key = granted["key"]
            if not isinstance(key, str) or not key:
                raise ValueError("empty key")
        except (ValueError, KeyError, TypeError):
            return "authorize_failed", "Zotero answered 200 without a key; report this.", {"status": status, "waited_s": waited}
        if not granted.get("remember"):
            return "authorize_single_use", HINT_SINGLE_USE, {"waited_s": waited}
        save_key(key, server_id)
        log(f"key saved to the zotero block of {config_path()} (mode 0600)")
        return "ok", None, {"waited_s": waited}
    if status == 403:
        try:
            denied = json.loads(body).get("denied") is True
        except (ValueError, AttributeError):
            denied = False
        if denied:
            return "authorize_denied", HINT_DENIED, {"waited_s": waited}
        raise Stop("local_api_disabled", 2, HINT_DISABLED, status=status, body=text(body))
    if status == 412:
        raise Stop("server_mismatch", 2, "The server ID changed between the two requests (Zotero restarted?); re-run.",
                   status=status, body=text(body))
    return ("authorize_failed", "Unexpected answer from /api/local/authorize; report status and body.",
            {"status": status, "body": text(body), "waited_s": waited})


def is_wsl():
    try:
        return "microsoft" in Path("/proc/version").read_text(encoding="utf-8", errors="replace").lower()
    except OSError:
        return False


def command_output(argv, timeout, cwd=None):
    """First non-empty stdout line of a command, or None on any failure (missing binary, non-zero exit, timeout)."""
    try:
        done = subprocess.run(argv, capture_output=True, timeout=timeout, cwd=cwd)
    except (OSError, subprocess.TimeoutExpired) as e:
        log(f"{argv[0]}: {e.__class__.__name__}")
        return None
    if done.returncode != 0:
        log(f"{argv[0]}: exit {done.returncode}")
        return None
    for line in done.stdout.decode("utf-8", errors="replace").splitlines():
        if line.strip():
            return line.strip()
    return None


def windows_downloads():
    """The Windows Downloads folder as a WSL path: the shell's known folder, else %USERPROFILE%\\Downloads."""
    cwd = "/mnt/c" if os.path.isdir("/mnt/c") else None  # a Linux cwd makes cmd.exe complain about UNC paths
    win = command_output(["powershell.exe", "-NoProfile", "-Command", PS_DOWNLOADS], 20, cwd)
    if not win:
        profile = command_output(["cmd.exe", "/c", "echo", "%USERPROFILE%"], 10, cwd)
        win = profile + "\\Downloads" if profile and "%" not in profile else None
    if not win or not WIN_PATH_RE.match(win):
        return None
    return command_output(["wslpath", "-u", win], 5)


def resolve_downloads(flag):
    """The first source that answers wins; if that directory does not exist the answer is None (not a failure)."""
    if flag:
        candidate, source = flag, "--downloads"
    elif os.environ.get(ENV_DOWNLOADS):
        candidate, source = os.environ[ENV_DOWNLOADS], ENV_DOWNLOADS
    else:
        candidate = source = None
        if is_wsl():
            candidate, source = windows_downloads(), "Windows Downloads"
        if not candidate:
            candidate, source = command_output(["xdg-user-dir", "DOWNLOAD"], 5), "xdg-user-dir"
            if candidate and Path(candidate) == Path.home():  # xdg-user-dir answers $HOME when nothing is configured
                candidate = None
        if not candidate:
            candidate, source = str(Path.home() / "Downloads"), "~/Downloads"
    path = Path(candidate).expanduser()
    if not path.is_dir():
        log(f"downloads ({source}): {path} does not exist")
        return None
    log(f"downloads ({source}): {path}")
    return str(path)


def find_opencli():
    path = shutil.which("opencli")
    return {"found": path is not None, "path": path}


def tree_bytes(root):
    total = 0
    for dirpath, _, files in os.walk(root):
        for name in files:
            try:
                total += os.lstat(os.path.join(dirpath, name)).st_size
            except OSError:
                pass
    return total


def describe(path, work):
    rel = str(path.relative_to(work))
    if path.is_dir():
        return {"path": rel, "bytes": tree_bytes(path), "kind": "dir"}
    return {"path": rel, "bytes": path.stat().st_size, "kind": KINDS.get(path.suffix.lower(), "other")}


def leftovers(work):
    """Everything already in <work> except .started, scratch/ and an empty records/; records/ is listed file by file."""
    found = []
    for entry in sorted(work.iterdir()):
        if entry.name in (".started", "scratch"):
            continue
        if entry.name == "records" and entry.is_dir():
            found.extend(describe(child, work) for child in sorted(entry.iterdir()))
        else:
            found.append(describe(entry, work))
    return found


def prepare_work(work_dir):
    work = Path(work_dir).expanduser().absolute()
    records, marker = work / "records", work / ".started"
    try:
        records.mkdir(parents=True, exist_ok=True)
        (work / "scratch").mkdir(exist_ok=True)
        resumed = marker.exists()
        if not resumed:
            marker.touch()
        started = datetime.fromtimestamp(marker.stat().st_mtime).astimezone().isoformat(timespec="seconds")
        found = leftovers(work)
    except OSError as e:
        raise Stop("work_dir_unwritable", 1, "Pass a writable directory with --work.", work_dir=str(work), error=str(e))
    log(f"work dir {work}: {'resumed, started ' + started if resumed else 'new'}, {len(found)} leftover(s)")
    return {"work_dir": str(work), "records_dir": str(records), "started": started, "resumed": resumed, "leftovers": found}


def collection_tree(api):
    """All collections that are not in the trash, each with its path from the root ('自然图像/Diffusion'), sorted by path."""
    rows, start = [], 0
    while True:
        status, headers, body = get(api, f"{LIB}/collections?limit={PAGE}&start={start}")
        if status != 200:
            raise Stop("unexpected_response", 2, "GET /collections should answer 200; see status and body.",
                       status=status, body=text(body))
        try:
            page = json.loads(body)
        except ValueError:
            page = None
        if not isinstance(page, list):
            raise Stop("unexpected_response", 2, "GET /collections did not return a JSON list.", body=text(body))
        rows.extend(page)
        start += len(page)
        try:
            total = int(headers.get("Total-Results", ""))
        except ValueError:
            total = None
        if not page or len(page) < PAGE or (total is not None and start >= total):
            break
    alive = {}
    for row in rows:
        data = row.get("data") or {}
        if data.get("deleted"):
            continue
        key = row.get("key") or data.get("key")
        alive[key] = {"key": key, "name": data.get("name") or "", "parent": data.get("parentCollection") or None}
    out = []
    for key, entry in alive.items():
        names, cursor, seen = [], key, set()
        while cursor in alive and cursor not in seen:  # stops at a parent in the trash; guards against cycles
            seen.add(cursor)
            names.append(alive[cursor]["name"])
            cursor = alive[cursor]["parent"]
        out.append({**entry, "path": "/".join(reversed(names))})
    log(f"{len(rows)} collections read, {len(out)} not in the trash")
    return sorted(out, key=lambda c: c["path"])


def parse_args():
    p = argparse.ArgumentParser(
        description="Step 0 of paper-to-zotero: check Zotero's local API and the write key, find the Downloads folder "
                    "and opencli, prepare the work directory and print the collection tree.",
        epilog="Exit 0 = ready; 1 = not ready (no_key: tell the user to click Always Allow, then re-run with --authorize; "
               "authorize_denied, authorize_timeout, authorize_single_use, authorize_failed); 2 = cannot check "
               "(zotero_unreachable, local_api_disabled, server_mismatch, config_unreadable, no_pdftotext). Output is "
               f"one JSON object on stdout; no key or other config value is ever printed. Config: ${ENV_CONFIG} or "
               "~/.config/paper-to-zotero/config.json.")
    p.add_argument("--work", default=DEFAULT_WORK, metavar="DIR",
                   help="work directory; records/, scratch/ and the .started marker are created in it (default: %(default)s)")
    p.add_argument("--session", default=DEFAULT_SESSION, metavar="NAME",
                   help="name of the opencli browser session, only echoed back (default: %(default)s)")
    p.add_argument("--downloads", metavar="DIR",
                   help=f"the browser's download directory; else env {ENV_DOWNLOADS}, else detected "
                        "(the Windows Downloads folder under WSL, xdg-user-dir DOWNLOAD, ~/Downloads)")
    p.add_argument("--authorize", action="store_true",
                   help="when no usable key is stored, ask Zotero for one: it shows a dialog and the user must click "
                        "Always Allow; the key is saved in the config file's zotero block (mode 0600)")
    p.add_argument("--timeout", type=float, default=AUTHORIZE_WAIT, metavar="SECONDS",
                   help="how long --authorize waits for the click (default: %(default)s)")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL, help="local API base URL (default: %(default)s)")
    return p.parse_args()


def main():
    args = parse_args()
    api = Api(args.base_url)
    server_id = live_server_id(api)
    config = read_config()
    key = key_status(config, server_id)
    code, hint, extra, exit_code = "ok", None, {}, 0
    if not key_usable(key):
        if args.authorize:
            code, hint, extra = authorize(api, server_id, args.timeout)
            if code == "ok":
                config = read_config()
                key = key_status(config, server_id)
        elif key["server_match"] is False:
            raise Stop("server_mismatch", 2, HINT_MISMATCH, config=str(config_path()))
        else:
            code, hint = "no_key", HINT_NO_KEY
    if code != "ok":
        exit_code = 1
    poppler = find_poppler()
    if code == "ok" and not all(poppler.values()):
        code, hint, exit_code = "no_pdftotext", HINT_NO_PDFTOTEXT, 2
    work = prepare_work(args.work)
    facts = {"zotero": {"reachable": True, "base_url": api.base}, "key": key, "config": config_summary(config),
             "poppler": poppler, "downloads_dir": resolve_downloads(args.downloads), "opencli": find_opencli(),
             "work_dir": work["work_dir"], "records_dir": work["records_dir"], "session": args.session,
             "started": work["started"], "resumed": work["resumed"], "leftovers": work["leftovers"],
             "collections": collection_tree(api)}
    emit(code, exit_code, hint, **facts, **extra)


if __name__ == "__main__":
    try:
        main()
    except Stop as stop:
        emit(stop.code, stop.exit_code, stop.hint, **stop.extra)
