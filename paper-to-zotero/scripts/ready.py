#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Step 0 of an import: the facts the run needs, and its work directory.

One call answers: is Zotero's local API up; is a usable write key stored (with --authorize and none usable, obtain
one: Zotero shows a dialog and the user must click Always Allow); are pdftotext and pdfinfo (poppler-utils) on PATH;
what the config file holds (presence only, never a value); where the browser puts downloads; is opencli there and
its Chrome extension connected (opencli's own `doctor`: its version, the issues it names). It
makes <work>/records/, scratch/ and the .started marker (an existing marker is left alone: a resumed run), writes
<work>/run.json (downloads, session: what the later scripts read), lists what already lies in <work> (deleting
nothing), names the records an older version left (old_format: their computed blocks are redone by p2z.py
prepare), and prints the library's collection tree with paths ("自然图像/Diffusion").

Config: $PAPER_TO_ZOTERO_CONFIG or ~/.config/paper-to-zotero/config.json, mode 600, every field optional:
{"zotero": {"key", "serverID"}, "openalex_key", "institution": {"proxy", "discovery"}}. --authorize writes the
"zotero" block and keeps the rest.
Downloads: --downloads > $PAPER_TO_ZOTERO_DOWNLOADS > under WSL the Windows Downloads folder (powershell.exe, then
cmd.exe %USERPROFILE%) > xdg-user-dir DOWNLOAD > ~/Downloads; a folder that does not exist gives null.

stdout: one JSON object {code, ...the facts}. Exit 0 = ready; 1 = not ready (no_key: tell the user Zotero will show
a dialog where they click Always Allow, then rerun with --authorize; authorize_denied, authorize_timeout,
authorize_single_use, authorize_failed); 2 = cannot check (zotero_unreachable, local_api_disabled, server_mismatch,
config_unreadable, no_pdftotext: install poppler-utils, references/install.md).
"""
import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

from p2zlib import cli, config, run, zotero

DEFAULT_WORK = os.path.join(os.environ.get("TMPDIR") or "/tmp", "paper-to-zotero")
SESSION = "p2z"  # the opencli browser session of every run
APP_NAME = "paper-to-zotero"
AUTHORIZE_WAIT = 300  # seconds the user gets to click Always Allow
PS_DOWNLOADS = ("[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
                "(New-Object -ComObject Shell.Application).NameSpace('shell:Downloads').Self.Path")
WIN_PATH_RE = re.compile(r"^[A-Za-z]:\\")

HINT_NO_KEY = ("No usable local API key. Tell the user that Zotero will show an authorization dialog and that they must "
               "click Always Allow (Allow gives a single-use key); then rerun with --authorize.")
HINT_DENIED = "The user declined or closed the authorization dialog; ask before rerunning with --authorize."
HINT_TIMEOUT = ("Nobody clicked within the wait; the dialog may still be open in Zotero. Ask the user to click Always "
                "Allow, then rerun with --authorize.")
HINT_SINGLE_USE = ("The user clicked Allow, so the key would die after one write; nothing was saved. Ask for Always "
                   "Allow, then rerun with --authorize.")
HINT_MISMATCH = ("The stored key was issued by another Zotero instance; rerun with --authorize to authorize this one "
                 "(the config's zotero block is replaced).")


def config_summary(conf):
    """Which settings are present, never their values; a warning when others can read the file."""
    path, inst = config.path(), conf.get("institution") if isinstance(conf.get("institution"), dict) else {}
    zot = conf.get("zotero") if isinstance(conf.get("zotero"), dict) else {}
    out = {"file": str(path), "exists": path.is_file(), "zotero_key": bool(zot.get("key")),
           "openalex_key": bool(conf.get("openalex_key")),
           "institution": {"proxy": bool(inst.get("proxy")), "discovery": bool(inst.get("discovery"))}}
    if not inst.get("discovery"):
        out["ask_user"] = ("institution.discovery: the discovery route needs the library's search page (a Primo search "
                           "URL); ask the user for it in your first message and add it to the config")
    if path.is_file() and path.stat().st_mode & 0o077:
        out["warning"] = "loose_permissions: run chmod 600 on the config file"
    return out


def key_status(conf, server_id):
    """{present, server_match}: what is known about the write key, without the key."""
    zot = conf.get("zotero") if isinstance(conf.get("zotero"), dict) else {}
    if not isinstance(zot.get("key"), str) or not zot["key"]:
        return {"present": False, "server_match": None}
    return {"present": True, "server_match": None if not zot.get("serverID") else zot["serverID"] == server_id}


def authorize(zot, server_id, wait):
    """POST /api/local/authorize: Zotero shows a dialog and answers when the user clicks; a 429 waits its Retry-After.
    -> (code, hint, extra); the key is saved on success, a single-use one (Allow) is not."""
    cli.log("Zotero is showing an authorization dialog: the user must click Always Allow")
    started = time.monotonic()
    deadline = started + wait
    while True:
        remaining = deadline - time.monotonic()
        waited = lambda: round(time.monotonic() - started)  # noqa: E731
        if remaining <= 0:
            return "authorize_timeout", HINT_TIMEOUT, {"waited_s": waited()}
        try:
            status, headers, body = zot.request("POST", "/api/local/authorize", {"appName": APP_NAME},
                                                {"Zotero-Server-ID": server_id}, timeout=remaining)
        except cli.Stop as stop:
            if "timed out" in str(stop.extra.get("detail", "")):
                return "authorize_timeout", HINT_TIMEOUT, {"waited_s": waited()}
            raise
        if status != 429:
            break
        try:
            delay = max(1, int(headers.get("Retry-After") or json.loads(body).get("retryAfter")))
        except (ValueError, TypeError, AttributeError):
            delay = 15
        if time.monotonic() + delay > deadline:
            return "authorize_timeout", HINT_TIMEOUT, {"waited_s": waited(), "retry_after": delay}
        cli.log(f"rate limited (5 dialogs a minute); waiting {delay}s")
        time.sleep(delay)
    try:
        answer = json.loads(body)
    except ValueError:
        answer = {}
    answer = answer if isinstance(answer, dict) else {}
    if status == 200:
        if not isinstance(answer.get("key"), str) or not answer["key"]:
            return "authorize_failed", "Zotero answered 200 without a key; report this.", {"status": status, "waited_s": waited()}
        if not answer.get("remember"):
            return "authorize_single_use", HINT_SINGLE_USE, {"waited_s": waited()}
        config.save_key(answer["key"], server_id)
        return "ok", None, {"waited_s": waited()}
    if status == 403 and answer.get("denied") is True:
        return "authorize_denied", HINT_DENIED, {"waited_s": waited()}
    zot.check(status, body)
    return ("authorize_failed", "Unexpected answer from /api/local/authorize; report status and detail.",
            {"status": status, "detail": zotero.detail(body), "waited_s": waited()})


def command_output(argv, timeout, cwd=None):
    """The first non-empty stdout line of a command, or None on any failure."""
    try:
        done = subprocess.run(argv, capture_output=True, timeout=timeout, cwd=cwd)
    except (OSError, subprocess.TimeoutExpired):
        return None
    lines = [ln.strip() for ln in done.stdout.decode("utf-8", errors="replace").splitlines() if ln.strip()]
    return lines[0] if done.returncode == 0 and lines else None


def opencli_status():
    """opencli's own check, `opencli doctor` -> {path, version, connected, issues}; {path: None} when it is missing.
    An OpenCLI before 2.x is named as the issue: the browser calls are 2.x's."""
    path = shutil.which("opencli")
    if not path:
        return {"path": None}
    version = command_output(["opencli", "--version"], 30)
    major = re.match(r"v?(\d+)\.", version or "")
    if not major or int(major.group(1)) < 2:
        return {"path": path, "version": version,
                "issues": [f"OpenCLI {version or '(no version)'}: this skill needs 2.x (references/install.md)"]}
    try:
        data = json.loads(command_output(["opencli", "doctor"], 60) or "")["data"]
    except (ValueError, KeyError, TypeError):
        return {"path": path, "issues": ["opencli doctor gave no answer"]}
    return {"path": path, "version": data.get("cliVersion"), "connected": data.get("extensionConnected"),
            "issues": data.get("issues") or []}


def windows_downloads():
    """The Windows Downloads folder as a WSL path: the shell's known folder, else %USERPROFILE%\\Downloads."""
    cwd = "/mnt/c" if os.path.isdir("/mnt/c") else None  # a Linux cwd makes cmd.exe complain about UNC paths
    win = command_output(["powershell.exe", "-NoProfile", "-Command", PS_DOWNLOADS], 20, cwd)
    if not win:
        profile = command_output(["cmd.exe", "/c", "echo", "%USERPROFILE%"], 10, cwd)
        win = profile + "\\Downloads" if profile and "%" not in profile else None
    return command_output(["wslpath", "-u", win], 5) if win and WIN_PATH_RE.match(win) else None


def is_wsl():
    try:
        return "microsoft" in Path("/proc/version").read_text(encoding="utf-8", errors="replace").lower()
    except OSError:
        return False


def resolve_downloads(flag):
    """The first source that answers wins; None when that folder does not exist."""
    candidate = flag or os.environ.get("PAPER_TO_ZOTERO_DOWNLOADS")
    if not candidate and is_wsl():
        candidate = windows_downloads()
    if not candidate:
        candidate = command_output(["xdg-user-dir", "DOWNLOAD"], 5)
        if candidate and Path(candidate) == Path.home():  # its answer when nothing is configured
            candidate = None
    path = Path(candidate or Path.home() / "Downloads").expanduser()
    return str(path) if path.is_dir() else None


def prepare_work(work, downloads):
    """Make the directory and its marker, write run.json -> {work_dir, started, resumed, leftovers, old_format}."""
    try:
        work.records.mkdir(parents=True, exist_ok=True)
        work.scratch.mkdir(exist_ok=True)
        resumed = work.started.exists()
        if not resumed:
            work.started.touch()
        work.set(downloads=downloads, session=SESSION)
    except OSError as e:
        raise cli.Stop("work_dir_unwritable", hint="Pass a writable directory with --work.", work_dir=str(work.root),
                       detail=str(e)) from None
    leftovers, old = [], []
    for entry in sorted(work.root.iterdir()):
        if entry.name in (".started", "scratch", "run.json", "pace.json", "pace.json.lock"):
            continue
        for path in sorted(entry.iterdir()) if entry == work.records else [entry]:
            size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) if path.is_dir() else path.stat().st_size
            leftovers.append({"path": str(path.relative_to(work.root)), "bytes": size})
            if path.suffix == ".json" and path.parent == work.records:
                try:
                    blocks = run.old_format(run.read(path))
                except cli.Stop:
                    continue
                if blocks:
                    old.append({"slug": path.stem, "blocks": blocks})
    started = datetime.fromtimestamp(work.started.stat().st_mtime).astimezone().isoformat(timespec="seconds")
    return {"work_dir": str(work.root), "records_dir": str(work.records), "started": started, "resumed": resumed,
            "leftovers": leftovers, **({"old_format": old} if old else {})}


def main(argv=None):
    p = cli.parser(__doc__)
    p.add_argument("--work", default=DEFAULT_WORK, metavar="DIR", help="the work directory (default: %(default)s)")
    p.add_argument("--downloads", metavar="DIR", help="the browser's Downloads folder (default: detected)")
    p.add_argument("--authorize", action="store_true", help="when no usable key is stored, ask Zotero for one: the user "
                                                            "clicks Always Allow in its dialog; saved in the config (mode 600)")
    p.add_argument("--timeout", type=float, default=AUTHORIZE_WAIT, metavar="SECONDS",
                   help="how long --authorize waits for the click (default: %(default)s)")
    cli.add_base_url(p)
    args = p.parse_args(argv)

    def go():
        zot = zotero.Zotero(args.base_url)
        server_id = zot.server_id()
        conf = config.read(strict=True)
        key = key_status(conf, server_id)
        code, hint, extra = "ok", None, {}
        if not (key["present"] and key["server_match"] is not False):
            if args.authorize:
                code, hint, extra = authorize(zot, server_id, args.timeout)
                conf = config.read(strict=True)
                key = key_status(conf, server_id)
            elif key["server_match"] is False:
                raise cli.Stop("server_mismatch", exit=cli.CANNOT, hint=HINT_MISMATCH, config=str(config.path()))
            else:
                code, hint = "no_key", HINT_NO_KEY
        exit_code = cli.OK if code == "ok" else cli.ACT
        poppler = {name: shutil.which(name) for name in ("pdftotext", "pdfinfo")}
        if code == "ok" and not all(poppler.values()):
            code, exit_code = "no_pdftotext", cli.CANNOT
            hint = "pdftotext and pdfinfo (poppler-utils) are needed to check PDFs: tell the user, install it only on their OK."
        downloads = resolve_downloads(args.downloads)
        facts = {"zotero": {"reachable": True, "base_url": zot.base}, "key": key, "config": config_summary(conf),
                 "poppler": poppler, "downloads_dir": downloads, "opencli": opencli_status(),
                 "session": SESSION, **prepare_work(run.Work(args.work), downloads),
                 "collections": sorted(({k: c[k] for k in ("key", "name", "parent", "path")} for c in zot.collections().values()),
                                       key=lambda c: c["path"])}
        if facts.get("old_format"):
            facts["old_format_hint"] = "Records from an older version: run p2z.py prepare on them before step 3."
        cli.emit({"code": code, **({"hint": hint} if hint else {}), **facts, **extra})
        return exit_code

    return cli.run(go)


if __name__ == "__main__":
    raise SystemExit(main())
