# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Write a child note on one Zotero item from a small Markdown subset, creating it or updating the note that carries a marker.

Markdown -> note HTML: paragraphs -> <p>, "- " lists -> <ul><li>, "# " / "## "
(/ "### ") -> <h1>/<h2>/<h3>, **x** -> <strong>, *x* -> <em>, [t](u) ->
<a href>; everything else is escaped literally. With --marker M the note's
first element is the marker line, and a child note of the item whose first
paragraph reads M is the one to update (PATCH with If-Unmodified-Since-Version,
one retry on 412); `unchanged` when its HTML is already identical. Without
--marker every run creates a new note.

Marker form: a plain first paragraph `<p>M</p>`. Probed 2026-09-23 against the
local API under the tmp collection: `<p data-p2z-marker="M">`, `<p><em>M</em></p>`,
`<p>M</p>`, a `<div data-schema-version>` wrapper and `<h1>M</h1>` all came back
byte-for-byte, so the simplest form wins. It also survives the note editor,
which keeps only its own schema (a data-* attribute would be dropped once the
user edits the note) and shows the first line as the note's title, so the
marker doubles as the note's name in the item's child list. Detection strips
an editor wrapper and inline tags before comparing the first paragraph's text.

stdout: exactly one JSON object {code, note_key, action, item_key} with a
stable `code` (`ok` on success; action created | updated | unchanged);
--dry-run adds the HTML it would write. Diagnostics go to stderr. Exit 0 =
done, 1 = not done (item_not_found, not_a_parent, cite_not_found,
cite_ambiguous, marker_ambiguous, empty_note, version_conflict, write_denied,
write_failed, verify_failed), 2 = cannot check (Zotero unreachable, local API
disabled, no key, key rejected, key belongs to another Zotero instance).

Examples:
  uv run scripts/note.py --cite liu2022progressive --file notes/liu.md --marker "p2z: verification" --dry-run
  uv run scripts/note.py --key ABCD1234 --text "# Read 2026-09-23\n- claims X\n- **no** code" --marker "p2z: reading"
"""
import argparse
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_BASE_URL = "http://127.0.0.1:23119"
DEFAULT_KEY_FILE = "~/.config/zotero/local-api-key"
LIB = "/api/users/0"
PAGE = 100
KEY_RE = re.compile(r"^[A-Z0-9]{8}$")
CHILD_TYPES = {"note", "attachment", "annotation"}

HEADING = re.compile(r"^(#{1,3})\s+(.*)$")
BULLET = re.compile(r"^[-*]\s+(.*)$")
LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
BOLD = re.compile(r"\*\*(.+?)\*\*")
EM = re.compile(r"\*([^*]+)\*")
EDITOR_WRAP = re.compile(r"^\s*<div\b[^>]*data-schema-version[^>]*>(.*)</div>\s*$", re.S)
FIRST_BLOCK = re.compile(r"<(p|h[1-6])\b[^>]*>(.*?)</\1>", re.S)
TAG = re.compile(r"<[^>]+>")


class Stop(Exception):
    """Carry a result code out of any depth; main() turns it into JSON + exit."""

    def __init__(self, code, exit_code=1, hint=None, **extra):
        super().__init__(code)
        self.code, self.exit_code, self.hint, self.extra = code, exit_code, hint, extra


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

    def __init__(self, base_url, timeout=120):
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self, method, path, body=None, headers=None):
        h = {"Accept": "application/json"}
        h.update(headers or {})
        data = None
        if isinstance(body, (dict, list)):
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            h.setdefault("Content-Type", "application/json")
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=h)
        try:
            with self.opener.open(req, timeout=self.timeout) as resp:
                return resp.status, resp.headers, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()
        except (urllib.error.URLError, OSError) as e:
            reason = getattr(e, "reason", None) or e
            raise Stop("zotero_unreachable", 2, "Start Zotero, then retry; check --base-url if it is not the default.",
                       base_url=self.base, error=str(reason))


def check_common(status, body):
    """Failures that mean 'cannot check' regardless of which call produced them."""
    msg = text(body)
    if status == 403 and "not enabled" in msg.lower():
        raise Stop("local_api_disabled", 2, "Ask the user to enable the local API in Zotero settings (Advanced), then retry.",
                   status=status, body=msg)
    if status == 401:
        raise Stop("key_rejected", 2, "The API key is not accepted by this Zotero; run ready.py --authorize again.",
                   status=status, body=msg)
    if status == 412 and "server-id" in msg.lower():
        raise Stop("server_mismatch", 2, "The key belongs to another Zotero instance; run ready.py --authorize again.",
                   status=status, body=msg)


def live_server_id(api):
    status, headers, body = api.request("GET", "/api/")
    check_common(status, body)
    sid = headers.get("Zotero-Server-ID")
    if status != 200 or not sid:
        raise Stop("zotero_unreachable", 2, "The endpoint does not behave like Zotero's local API; check --base-url.",
                   status=status, body=text(body))
    return sid


def load_key(key_file, server_id):
    """Return the API key; ZOTERO_LOCAL_API_KEY overrides the key file. Never printed."""
    env = os.environ.get("ZOTERO_LOCAL_API_KEY")
    if env:
        return env.strip()
    path = Path(key_file).expanduser()
    if not path.is_file():
        raise Stop("no_key", 2, "No local API key yet; run ready.py --authorize first (or set ZOTERO_LOCAL_API_KEY).",
                   key_file=str(path))
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
        key = info["key"]
    except (ValueError, KeyError, TypeError) as e:
        raise Stop("no_key", 2, "The key file is unreadable; run ready.py --authorize again.",
                   key_file=str(path), error=str(e))
    saved = info.get("serverID")
    if saved and saved != server_id:
        raise Stop("server_mismatch", 2, "The saved key was issued by another Zotero instance; run ready.py --authorize again.",
                   key_file=str(path))
    return key


def write_headers(key, server_id, version=None):
    h = {"Zotero-API-Key": key, "Zotero-Server-ID": server_id}
    if version is not None:
        h["If-Unmodified-Since-Version"] = str(version)
    return h


def get_json(api, path):
    status, _, body = api.request("GET", path)
    check_common(status, body)
    if status == 404:
        return None
    if status != 200:
        raise Stop("unexpected_response", 1, "Unexpected local API reply; see status and body.", path=path, status=status, body=text(body))
    try:
        return json.loads(body)
    except ValueError:
        raise Stop("unexpected_response", 1, "The local API did not return JSON.", path=path, body=text(body))


def get_pages(api, path):
    """Every row of a paged listing (limit 100)."""
    rows, start, sep = [], 0, "&" if "?" in path else "?"
    while True:
        page = get_json(api, f"{path}{sep}limit={PAGE}&start={start}")
        if not isinstance(page, list):
            raise Stop("unexpected_response", 1, "Expected a JSON list from the local API.", path=path, start=start)
        rows.extend(page)
        if len(page) < PAGE:
            return rows
        start += PAGE


def is_top(row):
    data = row.get("data") or {}
    return data.get("itemType") not in CHILD_TYPES and not data.get("parentItem")


def resolve_cite(api, cite):
    """Item key for a citationKey: a q=everything search first (verified to hit on the local API, 2026-09-23),
    then a paged scan of /items/top as the fallback."""
    query = urllib.parse.urlencode({"q": cite, "qmode": "everything", "limit": 50})
    rows = get_json(api, f"{LIB}/items?{query}") or []
    hits = [r["key"] for r in rows if is_top(r) and (r.get("data") or {}).get("citationKey") == cite]
    if not hits:
        log(f"no search hit for citationKey {cite!r}; scanning /items/top (fallback)")
        hits = [r["key"] for r in get_pages(api, f"{LIB}/items/top") if (r.get("data") or {}).get("citationKey") == cite]
    if not hits:
        raise Stop("cite_not_found", 1, "No item carries this citationKey; check it with read_library.py items --q, or pass --key.", cite=cite)
    if len(hits) > 1:
        raise Stop("cite_ambiguous", 1, "Several items carry this citationKey; pass --key for the one you mean.", cite=cite, keys=hits)
    log(f"citationKey {cite!r} -> item {hits[0]}")
    return hits[0]


# --- Markdown subset -> note HTML -------------------------------------------


def marks(s):
    """Escape, then **bold** and *em*."""
    s = html.escape(s, quote=False)
    s = BOLD.sub(r"<strong>\1</strong>", s)
    return EM.sub(r"<em>\1</em>", s)


def inline(s):
    """Links first (their text gets the marks too, the URL is escaped as an attribute), marks on the rest."""
    out, pos = [], 0
    for m in LINK.finditer(s):
        out.append(marks(s[pos:m.start()]))
        out.append(f'<a href="{html.escape(m.group(2), quote=True)}">{marks(m.group(1))}</a>')
        pos = m.end()
    out.append(marks(s[pos:]))
    return "".join(out)


def to_html(md):
    """Paragraphs, "- " lists (indented lines continue an item), #/##/### headings; blank lines separate blocks."""
    blocks, para, items = [], [], []

    def flush():
        if para:
            blocks.append("<p>" + "\n".join(inline(line) for line in para) + "</p>")
            para.clear()
        if items:
            blocks.append("<ul>\n" + "\n".join(f"<li>{inline(i)}</li>" for i in items) + "\n</ul>")
            items.clear()

    for raw in md.splitlines():
        stripped = raw.strip()
        if not stripped:
            flush()
            continue
        m = HEADING.match(stripped)
        if m:
            flush()
            level = len(m.group(1))
            blocks.append(f"<h{level}>{inline(m.group(2).strip())}</h{level}>")
            continue
        m = BULLET.match(stripped)
        if m:
            if para:
                flush()
            items.append(m.group(1))
            continue
        if items and raw.startswith((" ", "\t")):
            items[-1] += " " + stripped
            continue
        if items:
            flush()
        para.append(stripped)
    flush()
    return "\n".join(blocks)


def marker_of(note_html):
    """Text of the note's first paragraph/heading (editor wrapper and inline tags stripped); None without one."""
    inner = note_html or ""
    m = EDITOR_WRAP.match(inner)
    if m:
        inner = m.group(1)
    m = FIRST_BLOCK.match(inner.lstrip())
    if not m:
        return None
    return html.unescape(TAG.sub("", m.group(2))).strip()


# --- library ------------------------------------------------------------------


def get_item(api, key):
    return get_json(api, f"{LIB}/items/{key}")


def child_notes(api, key):
    return [c for c in get_pages(api, f"{LIB}/items/{key}/children")
            if (c.get("data") or {}).get("itemType") == "note" and c["data"].get("parentItem") == key]


def read_source(args):
    if args.text is not None:
        return args.text.replace("\\n", "\n") if "\n" not in args.text else args.text
    p = Path(args.file).expanduser()
    if not p.is_file():
        raise Stop("file_not_found", 1, "--file names the Markdown file to turn into the note.", file=str(p))
    return p.read_text(encoding="utf-8")


def write_check(status, body, key, what):
    check_common(status, body)
    if status == 403:
        raise Stop("write_denied", 1, "This library is not editable.", item_key=key, status=status, body=text(body))
    raise Stop("write_failed", 1, f"The local API rejected the {what}; see body.", item_key=key, status=status, body=text(body))


def run(api, args, api_key, server_id):
    body_html = to_html(read_source(args))
    if not body_html:
        raise Stop("empty_note", 1, "The Markdown converts to nothing; give the note some text.")
    marker = args.marker.strip() if args.marker else None
    note_html = (f"<p>{html.escape(marker, quote=False)}</p>\n" if marker else "") + body_html

    key = args.key or resolve_cite(api, args.cite)
    item = get_item(api, key)
    if item is None:
        raise Stop("item_not_found", 1, "No item with that key; check it with find_in_library.py.", item_key=key)
    data = item.get("data") or {}
    if data.get("itemType") in CHILD_TYPES or data.get("parentItem"):
        raise Stop("not_a_parent", 1, "Notes hang off regular items; pass the parent item's key.",
                   item_key=key, item_type=data.get("itemType"), parent_item=data.get("parentItem"))

    target = None
    if marker:
        hits = [n for n in child_notes(api, key) if marker_of((n.get("data") or {}).get("note")) == marker]
        if len(hits) > 1:
            raise Stop("marker_ambiguous", 1, "Several child notes start with this marker; delete the extras in Zotero, then re-run.",
                       item_key=key, marker=marker, note_keys=[n["key"] for n in hits])
        target = hits[0] if hits else None
    if target and target["data"].get("note") == note_html:
        emit("ok", 0, note_key=target["key"], action="unchanged", item_key=key, marker=marker, version=target.get("version"))
    if args.dry_run:
        emit("ok", 0, dry_run=True, note_key=target["key"] if target else None, action="updated" if target else "created",
             item_key=key, marker=marker, html=note_html)

    if target:
        note_key, retried = target["key"], False
        for attempt in (1, 2):
            status, _, body = api.request("PATCH", f"{LIB}/items/{note_key}", {"note": note_html},
                                          write_headers(api_key, server_id, target["version"]))
            if status == 204:
                break
            if status == 412 and "server-id" not in text(body).lower() and attempt == 1:
                log(f"412 on PATCH ({text(body, 120)}); re-reading the note and retrying once")
                retried = True
                target = get_item(api, note_key)
                if target is None:
                    raise Stop("item_not_found", 1, "The note disappeared while patching; re-run to create it afresh.", note_key=note_key)
                if target["data"].get("note") == note_html:
                    emit("ok", 0, note_key=note_key, action="unchanged", item_key=key, marker=marker, retried=True, version=target.get("version"))
                continue
            if status == 412 and "server-id" not in text(body).lower():
                raise Stop("version_conflict", 1, "The note keeps changing under us (Zotero sync or the user editing); wait, then re-run.",
                           note_key=note_key, status=status, body=text(body))
            write_check(status, body, key, "patch")
        action = "updated"
    else:
        status, _, body = api.request("POST", f"{LIB}/items", [{"itemType": "note", "parentItem": key, "note": note_html}],
                                      write_headers(api_key, server_id))
        if status != 200:
            write_check(status, body, key, "note")
        try:
            resp = json.loads(body)
            ok = (resp.get("successful") or {}).get("0")
        except (ValueError, AttributeError):
            raise Stop("write_failed", 1, "The POST reply is not the expected JSON.", item_key=key, body=text(body))
        if not ok:
            failed = (resp.get("failed") or {}).get("0") or {}
            raise Stop("write_failed", 1, "Zotero reported the note as failed; nothing was created.",
                       item_key=key, status=failed.get("code"), message=failed.get("message"))
        note_key, retried, action = ok.get("key"), False, "created"

    after = get_item(api, note_key)
    if after is None or (after.get("data") or {}).get("note") != note_html:
        raise Stop("verify_failed", 1, "The write was accepted but the note reads back differently; inspect it in Zotero.",
                   note_key=note_key, action=action, item_key=key, marker=marker,
                   read_back=(after or {}).get("data", {}).get("note"))
    emit("ok", 0, note_key=note_key, action=action, item_key=key, marker=marker, version=after.get("version"), retried=retried)


def parse_args():
    p = argparse.ArgumentParser(
        description="Write a child note on one Zotero item from a Markdown subset; with --marker, update the note that carries it.",
        epilog="Exit 0 = done (action created | updated | unchanged); 1 = not done, see code/hint; "
               "2 = cannot check (zotero_unreachable, local_api_disabled, no_key, key_rejected, server_mismatch). "
               "Output is one JSON object on stdout.")
    who = p.add_mutually_exclusive_group(required=True)
    who.add_argument("--key", metavar="ITEMKEY", help="key of the parent item")
    who.add_argument("--cite", metavar="CITEKEY", help="the parent item's citationKey (resolved to its key)")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--file", metavar="NOTE.md", help="Markdown file with the note's text")
    src.add_argument("--text", metavar="TEXT", help="the note's Markdown inline (a literal \\n counts as a line break)")
    p.add_argument("--marker", metavar="M", help="first line of the note; an existing child note starting with it is updated instead")
    p.add_argument("--dry-run", action="store_true", help="resolve the item and the marker, print the HTML; write nothing")
    p.add_argument("--key-file", default=DEFAULT_KEY_FILE, metavar="PATH",
                   help="JSON file holding the local API key (default: %(default)s); env ZOTERO_LOCAL_API_KEY overrides")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL, help="local API base URL (default: %(default)s)")
    args = p.parse_args()
    if args.key and not KEY_RE.match(args.key):
        p.error("--key is an 8-character item key")
    if args.marker is not None and not args.marker.strip():
        p.error("--marker must not be empty")
    return args


def main():
    args = parse_args()
    api = Api(args.base_url)
    server_id = live_server_id(api)
    api_key = load_key(args.key_file, server_id)
    run(api, args, api_key, server_id)


if __name__ == "__main__":
    try:
        main()
    except Stop as stop:
        emit(stop.code, stop.exit_code, stop.hint, **stop.extra)
