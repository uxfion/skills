#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Step 0 of work in Zotero: the facts it needs, and with --dir an import's directory.

One call answers: is Zotero's local API up; is a usable write key stored (with --authorize and none usable, obtain
one: Zotero shows a dialog and the user must click Always Allow); what the config file holds (presence only, never a
value); and it prints the library's collection tree with paths ("自然图像/Diffusion"). With --dir (an import:
<scratch>/paper-to-zotero) it makes the directory's records/ and scratch/, lists what already lies there (deleting
nothing) and names the records an older version left (old_format: their computed blocks are redone by p2z.py
prepare). Fetching (Downloads, the browser, poppler) is paper-fetch's, checked by its own ready.

Config: $PAPER_TO_ZOTERO_CONFIG or ~/.config/paper-to-zotero/config.json, mode 600: {"zotero": {"key", "serverID"}};
--authorize writes the "zotero" block and keeps the rest. The openalex key and institution an older version kept
there are paper-fetch's now: `moved` names those still in the file.

stdout: one JSON object {code, ...the facts}. Exit 0 = ready; 1 = not ready (no_key: tell the user Zotero will show
a dialog where they click Always Allow, then rerun with --authorize; authorize_denied, authorize_timeout,
authorize_single_use, authorize_failed; dir_unwritable); 2 = cannot check (zotero_unreachable, local_api_disabled,
server_mismatch, config_unreadable).
"""
import json
import time

from p2zlib import cli, config, run, zotero

APP_NAME = "paper-to-zotero"
AUTHORIZE_WAIT = 300  # seconds the user gets to click Always Allow
MOVED = ("openalex_key", "institution")  # paper-fetch's settings, in its own config since the split

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
    path, zot = config.path(), conf.get("zotero") if isinstance(conf.get("zotero"), dict) else {}
    out = {"file": str(path), "exists": path.is_file(), "zotero_key": bool(zot.get("key"))}
    moved = [k for k in MOVED if conf.get(k)]
    if moved:
        out["moved"] = moved
        out["moved_hint"] = ("paper-fetch keeps these in its own config now (~/.config/paper-fetch/config.json): once "
                             "the user has used the new version, ask them before removing them from this file")
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


def prepare_dir(work):
    """Make the import's records/ and scratch/ -> {dir, records_dir, leftovers, old_format?}."""
    try:
        work.records.mkdir(parents=True, exist_ok=True)
        work.scratch.mkdir(exist_ok=True)
    except OSError as e:
        raise cli.Stop("dir_unwritable", hint="Pass a writable directory with --dir.", dir=str(work.root),
                       detail=str(e)) from None
    leftovers, old = [], []
    for entry in sorted(work.root.iterdir()):
        if entry == work.scratch:
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
    return {"dir": str(work.root), "records_dir": str(work.records), "leftovers": leftovers,
            **({"old_format": old} if old else {})}


def main(argv=None):
    p = cli.parser(__doc__)
    p.add_argument("--dir", metavar="DIR", help="an import's directory, <scratch>/paper-to-zotero: made with records/ "
                                                "and scratch/")
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
        facts = {"zotero": {"reachable": True, "base_url": zot.base}, "key": key, "config": config_summary(conf),
                 **(prepare_dir(run.Work(args.dir)) if args.dir else {}),
                 "collections": sorted(({k: c[k] for k in ("key", "name", "parent", "path")} for c in zot.collections().values()),
                                       key=lambda c: c["path"])}
        if facts.get("old_format"):
            facts["old_format_hint"] = "Records from an older version: run p2z.py prepare on them before saving."
        cli.emit({"code": code, **({"hint": hint} if hint else {}), **facts, **extra})
        return cli.OK if code == "ok" else cli.ACT

    return cli.run(go)


if __name__ == "__main__":
    raise SystemExit(main())
