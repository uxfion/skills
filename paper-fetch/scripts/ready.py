#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Before fetching: the facts a run needs, and its directory.

One call answers: are pdftotext and pdfinfo (poppler-utils) on PATH; what the config file holds (presence only,
never a value); where the browser puts downloads; is opencli there and its Chrome extension connected (opencli's own
`doctor`: its version, the issues it names). It makes <dir> with results/, links/, inbox/, stray/, unverified/,
scratch/ and the .started marker (an existing marker is left alone: a resumed run), writes <dir>/run.json
(downloads, session: what the later scripts read), and lists what already lies in <dir>, deleting nothing: a PDF that
never reached anyone belongs to the user.

<dir>: --dir, <scratch>/paper-fetch where <scratch> is the session's scratchpad, else ${TMPDIR:-/tmp} (the
default). An import passes its own, <scratch>/paper-to-zotero/fetch.
Config: $PAPER_FETCH_CONFIG or ~/.config/paper-fetch/config.json, mode 600, every field optional:
{"openalex_key", "institution": {"proxy", "discovery"}}.
Downloads: --downloads > $PAPER_FETCH_DOWNLOADS > under WSL the Windows Downloads folder (powershell.exe, then
cmd.exe %USERPROFILE%) > xdg-user-dir DOWNLOAD > ~/Downloads; a folder that does not exist gives null.

stdout: one JSON object {code, ...the facts}. Exit 0 = ready; 1 = not ready (dir_unwritable: pass a writable --dir);
2 = cannot check (config_unreadable, no_pdftotext: install poppler-utils, references/install.md).

Example:
  uv run scripts/pf.py ready --dir <scratch>/paper-fetch
"""
import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from pflib import cli, config, run

DEFAULT_DIR = os.path.join(os.environ.get("TMPDIR") or "/tmp", "paper-fetch")
SESSION = "pf"  # the opencli browser session of every run
LAYOUT = ("results", "links", "inbox", "stray", "unverified")  # listed file by file; scratch/ is never a leftover
NOT_LEFTOVERS = (".started", "scratch", "run.json", "pace.json", "pace.json.lock")
PS_DOWNLOADS = ("[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
                "(New-Object -ComObject Shell.Application).NameSpace('shell:Downloads').Self.Path")
WIN_PATH_RE = re.compile(r"^[A-Za-z]:\\")


def config_summary(conf):
    """Which settings are present, never their values; a warning when others can read the file."""
    path, inst = config.path(), conf.get("institution") if isinstance(conf.get("institution"), dict) else {}
    out = {"file": str(path), "exists": path.is_file(), "openalex_key": bool(conf.get("openalex_key")),
           "institution": {"proxy": bool(inst.get("proxy")), "discovery": bool(inst.get("discovery"))}}
    if not inst.get("discovery"):
        out["ask_user"] = ("institution.discovery: the discovery route needs the library's search page (a Primo search "
                           "URL); ask the user for it in your first message and add it to the config")
    if path.is_file() and path.stat().st_mode & 0o077:
        out["warning"] = "loose_permissions: run chmod 600 on the config file"
    return out


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
    candidate = flag or os.environ.get("PAPER_FETCH_DOWNLOADS")
    if not candidate and is_wsl():
        candidate = windows_downloads()
    if not candidate:
        candidate = command_output(["xdg-user-dir", "DOWNLOAD"], 5)
        if candidate and Path(candidate) == Path.home():  # its answer when nothing is configured
            candidate = None
    path = Path(candidate or Path.home() / "Downloads").expanduser()
    return str(path) if path.is_dir() else None


def prepare_dir(work, downloads):
    """Make the directory, its layout and its marker, write run.json -> {dir, results_dir, started, resumed,
    leftovers}. A leftover is a file in one of the layout's folders, or anything else at the top."""
    try:
        work.root.mkdir(parents=True, exist_ok=True)
        for name in (*LAYOUT, "scratch"):
            getattr(work, name).mkdir(exist_ok=True)
        resumed = work.started.exists()
        if not resumed:
            work.started.touch()
        work.set(downloads=downloads, session=SESSION)
    except OSError as e:
        raise cli.Stop("dir_unwritable", hint="Pass a writable directory with --dir.", dir=str(work.root),
                       detail=str(e)) from None
    layout, leftovers = {getattr(work, name) for name in LAYOUT}, []
    for entry in sorted(work.root.iterdir()):
        if entry.name in NOT_LEFTOVERS:
            continue
        for path in sorted(entry.iterdir()) if entry in layout else [entry]:
            size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) if path.is_dir() else path.stat().st_size
            leftovers.append({"path": str(path.relative_to(work.root)), "bytes": size})
    started = datetime.fromtimestamp(work.started.stat().st_mtime).astimezone().isoformat(timespec="seconds")
    return {"dir": str(work.root), "results_dir": str(work.results), "started": started, "resumed": resumed,
            "leftovers": leftovers}


def main(argv=None):
    p = cli.parser(__doc__)
    p.add_argument("--dir", default=DEFAULT_DIR, metavar="DIR", help="the directory of the run (default: %(default)s)")
    p.add_argument("--downloads", metavar="DIR", help="the browser's Downloads folder (default: detected)")
    args = p.parse_args(argv)

    def go():
        conf = config.read(strict=True)
        code, hint = "ok", None
        poppler = {name: shutil.which(name) for name in ("pdftotext", "pdfinfo")}
        if not all(poppler.values()):
            code = "no_pdftotext"
            hint = "pdftotext and pdfinfo (poppler-utils) are needed to check PDFs: tell the user, install it only on their OK."
        downloads = resolve_downloads(args.downloads)
        facts = {"config": config_summary(conf), "poppler": poppler, "downloads_dir": downloads,
                 "opencli": opencli_status(), "session": SESSION, **prepare_dir(run.Work(args.dir), downloads)}
        cli.emit({"code": code, **({"hint": hint} if hint else {}), **facts})
        return cli.OK if code == "ok" else cli.CANNOT

    return cli.run(go)


if __name__ == "__main__":
    raise SystemExit(main())
