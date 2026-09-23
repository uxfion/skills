# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Attach a PDF or HTML snapshot to existing Zotero items through the local write API, one item or a stream of records.

Works the same for a just-created item and for an old one. Flow per file:
pre-checks (file, item, existing children) -> create the child attachment, or
reuse an empty one left by an interrupted run -> 3-step upload -> read back
the md5. A child that already holds a file with the same md5 is reported as
already attached and never uploaded twice.

Single mode (--key --file --url; v1, unchanged): stdout is exactly one JSON
object with a stable `code` (`ok` or `already_attached` on success).

Stream mode (record paths, or records on stdin as JSONL / a JSON array / one
object): the item key is the record's `saved.key`, else `found.key`; the file
is the record's `file` (relative to the record's directory; stdin records:
the working directory), else --file; the url is `item.url`, else
https://doi.org/<item.DOI>, else --url. A record whose `attach.md5_ok` is
already true is skipped; a file already attached (same md5) is skipped too,
and `attach` is filled in either way. On success the record gains
`attach = {key, md5_ok, filename, url, attached_at}`. Without -i the updated
records go to stdout one per line, and one summary line per record plus the
final {"summary": ...} go to stderr; with -i each changed record is written
back to its file and stdout carries those summary lines instead. Exit 0 =
every record ok or skipped, 1 = some failed (no_item_key, no_file, no_url,
file_not_found, item_not_found, upload_failed, ...), 2 = cannot check (Zotero
unreachable, local API disabled, no key, key rejected, key belongs to another
Zotero instance).

Diagnostics go to stderr; the API key is never printed.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_BASE_URL = "http://127.0.0.1:23119"
DEFAULT_KEY_FILE = "~/.config/zotero/local-api-key"
LIB = "/api/users/0"
TITLE_MAX = 120
ILLEGAL_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')
CHILD_TYPES = {"attachment", "note", "annotation"}


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


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
        if isinstance(body, (bytes, bytearray)):
            data = bytes(body)
        elif isinstance(body, (dict, list)):
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            h.setdefault("Content-Type", "application/json")
        elif body is not None:
            data = str(body).encode("utf-8")
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


def write_headers(key, server_id):
    return {"Zotero-API-Key": key, "Zotero-Server-ID": server_id}


def get_list(api, path):
    status, _, body = api.request("GET", path)
    check_common(status, body)
    if status != 200:
        raise Stop("unexpected_response", 1, "Unexpected local API reply; see status and body.", path=path, status=status, body=text(body))
    rows = json.loads(body)
    if not isinstance(rows, list):
        raise Stop("unexpected_response", 1, "Expected a JSON list from the local API.", path=path)
    return rows


def is_top(row):
    data = row.get("data") or {}
    return data.get("itemType") not in ("note", "attachment", "annotation") and not data.get("parentItem")


def resolve_cite(api, cite):
    """Item key for a citationKey: a q=everything search first (verified to hit on the local API, 2026-09-23),
    then a paged scan of /items/top as the fallback."""
    query = urllib.parse.urlencode({"q": cite, "qmode": "everything", "limit": 50})
    rows = get_list(api, f"{LIB}/items?{query}")
    hits = [r["key"] for r in rows if is_top(r) and (r.get("data") or {}).get("citationKey") == cite]
    if not hits:
        log(f"no search hit for citationKey {cite!r}; scanning /items/top (fallback)")
        start = 0
        while True:
            page = get_list(api, f"{LIB}/items/top?limit=100&start={start}")
            hits += [r["key"] for r in page if (r.get("data") or {}).get("citationKey") == cite]
            if len(page) < 100:
                break
            start += 100
    if not hits:
        raise Stop("cite_not_found", 1, "No item carries this citationKey; check it with read_library.py items --q, or pass --key.", cite=cite)
    if len(hits) > 1:
        raise Stop("cite_ambiguous", 1, "Several items carry this citationKey; pass --key for the one you mean.", cite=cite, keys=hits)
    log(f"citationKey {cite!r} -> item {hits[0]}")
    return hits[0]


def clean_filename(name):
    """Replace characters that are illegal on common filesystems, collapse whitespace."""
    return re.sub(r"\s+", " ", ILLEGAL_CHARS.sub(" ", name)).strip()


def first_creator(creators):
    """Zotero's firstCreator: authors first, else editors, else contributors, else anyone."""
    names = []
    for ctype in ("author", "editor", "contributor", None):
        chosen = [c for c in creators if ctype is None or c.get("creatorType") == ctype]
        names = [(c.get("lastName") or c.get("name") or "").strip() for c in chosen]
        names = [n for n in names if n]
        if names:
            break
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return f"{names[0]} et al."


def default_filename(data, ext=".pdf"):
    """Zotero's default pattern: '<firstCreator> - <year> - <title>' plus the extension."""
    parts = []
    creator = clean_filename(first_creator(data.get("creators") or []))
    if creator:
        parts.append(creator)
    year = re.search(r"\d{4}", data.get("date") or "")
    if year:
        parts.append(year.group())
    title = clean_filename(data.get("title") or "")[:TITLE_MAX].rstrip()
    if title:
        parts.append(title)
    return (" - ".join(parts) or "attachment") + ext


def get_json(api, path, not_found):
    status, _, body = api.request("GET", path)
    check_common(status, body)
    if status == 404:
        raise Stop(not_found[0], 1, not_found[1], **not_found[2])
    if status != 200:
        raise Stop("unexpected_response", 1, "Unexpected local API reply; see status and body.",
                   path=path, status=status, body=text(body))
    return json.loads(body)


def upload_file(api, wh, akey, pdf_bytes, md5, filename, mtime, content_type):
    """3-step upload: authorize -> transfer bytes -> register. Returns 'exists' or 'uploaded'."""
    form_headers = dict(wh, **{"Content-Type": "application/x-www-form-urlencoded", "If-None-Match": "*"})
    # quote_via=quote: Zotero's form parser does not turn '+' back into spaces, so spaces must be %20
    form = urllib.parse.urlencode({"md5": md5, "filename": filename, "filesize": len(pdf_bytes), "mtime": mtime},
                                  quote_via=urllib.parse.quote)
    status, _, body = api.request("POST", f"{LIB}/items/{akey}/file", form, form_headers)
    check_common(status, body)
    if status == 403:
        raise Stop("files_not_editable", 1, "This library does not allow file edits; the attachment item exists without a file.",
                   attachment_key=akey, status=status, body=text(body))
    if status != 200:
        hint = "Fix the cause and re-run the same command; the attachment item is reused, not recreated."
        if status == 412:
            hint = "The attachment already records a file; check it in Zotero (open the item) before re-running."
        raise Stop("upload_failed", 1, hint, step="authorize", status=status, body=text(body), attachment_key=akey)
    auth = json.loads(body)
    if auth.get("exists"):
        log("file already present on the attachment; skipping transfer")
        return "exists"
    parsed = urllib.parse.urlparse(auth["url"])
    upload_path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
    status, _, body = api.request("POST", upload_path, pdf_bytes, {"Content-Type": content_type})
    if status != 201:
        raise Stop("upload_failed", 1, "Re-run the same command; the attachment item is reused, not recreated.",
                   step="transfer", status=status, body=text(body), attachment_key=akey)
    status, _, body = api.request("POST", f"{LIB}/items/{akey}/file",
                                  urllib.parse.urlencode({"upload": auth["uploadKey"]}), form_headers)
    check_common(status, body)
    if status != 204:
        raise Stop("upload_failed", 1, "Re-run the same command; the attachment item is reused, not recreated.",
                   step="register", status=status, body=text(body), attachment_key=akey)
    return "uploaded"


# ---- the pre-checks and the attach itself, shared by both modes ----------------

def check_url(url):
    """The canonical source URL to store on the attachment; proxy hosts are refused."""
    url = (url or "").strip()
    parsed_url = urllib.parse.urlparse(url)
    if not url or parsed_url.scheme not in ("http", "https") or not parsed_url.hostname:
        raise Stop("invalid_pdf_url", 1, "Pass the canonical source URL with --url; fall back to https://doi.org/<DOI>.",
                   pdf_url=url)
    host = parsed_url.hostname.lower()
    if ".idm.oclc.org" in host or "ezproxy" in host:
        raise Stop("proxied_url", 1, "That is a proxy hostname; store the canonical URL instead (publisher page or https://doi.org/<DOI>).",
                   pdf_url=url)
    return url


def load_file(path):
    """Read the file -> (path, bytes, kind, content_type, ext); only a PDF or an HTML page saved as .html passes."""
    pdf = Path(path).expanduser()
    if not pdf.is_file():
        raise Stop("file_not_found", 1, "Point --file (or the record's `file`) at the downloaded file.", file=str(pdf))
    pdf_bytes = pdf.read_bytes()
    head = pdf_bytes[:2048].lstrip().lower()
    if pdf_bytes.startswith(b"%PDF-"):
        return pdf, pdf_bytes, "pdf", "application/pdf", ".pdf"
    if pdf.suffix.lower() in (".html", ".htm") and (head.startswith(b"<!doctype") or head.startswith(b"<html") or b"<html" in head):
        return pdf, pdf_bytes, "html", "text/html", ".html"
    raise Stop("unsupported_file", 1, "Only a PDF (%PDF- header) or an HTML page saved as .html is accepted; "
               "a \"PDF\" that is really HTML means the download returned a web page.",
               file=str(pdf), size=len(pdf_bytes), head=pdf_bytes[:16].decode("latin-1"))


def attach_one(api, wh, item_key, pdf, pdf_bytes, kind, content_type, ext, url, title, filename_arg, dry_run):
    """Attach one file to one item; returns the result fields with `code` ok | already_attached (v1's output shape)."""
    md5 = hashlib.md5(pdf_bytes).hexdigest()
    mtime = int(pdf.stat().st_mtime * 1000)

    item = get_json(api, f"{LIB}/items/{item_key}",
                    ("item_not_found", "No item with that key; check the key from create_item.py / find_in_library.py.",
                     {"item_key": item_key}))
    data = item.get("data") or {}
    if data.get("itemType") in CHILD_TYPES or data.get("parentItem"):
        raise Stop("not_a_parent", 1, "Attachments hang off a regular item; pass the parent item's key.",
                   item_key=item_key, item_type=data.get("itemType"), parent_item=data.get("parentItem"))
    filename = clean_filename(filename_arg) if filename_arg else default_filename(data, ext)
    if not filename:
        raise Stop("invalid_filename", 1, "Pass a usable --filename.", filename=filename_arg)

    children = get_json(api, f"{LIB}/items/{item_key}/children",
                        ("item_not_found", "No item with that key.", {"item_key": item_key}))
    reuse_key = None
    for child in children:
        cd = child.get("data") or {}
        if cd.get("itemType") != "attachment":
            continue
        if (cd.get("md5") or "").lower() == md5:
            return {"code": "already_attached", "item_key": item_key, "attachment_key": child["key"], "md5_ok": True,
                    "filename": cd.get("filename"), "reused_attachment": False, "md5": md5}
        if (reuse_key is None and cd.get("linkMode") in ("imported_url", "imported_file")
                and not cd.get("md5") and cd.get("filename") == filename):
            reuse_key = child["key"]
    if reuse_key:
        log(f"reusing empty attachment {reuse_key} (same filename, no file)")

    if dry_run:
        return {"code": "ok", "dry_run": True, "item_key": item_key, "kind": kind, "filename": filename, "md5": md5,
                "size": len(pdf_bytes), "pdf_url": url, "reused_attachment": bool(reuse_key), "attachment_key": reuse_key,
                "existing_attachments": sum(1 for c in children if (c.get("data") or {}).get("itemType") == "attachment")}

    if reuse_key:
        akey, reused = reuse_key, True
    else:
        attachment = {"itemType": "attachment", "linkMode": "imported_url", "parentItem": item_key,
                      "title": title, "contentType": content_type, "filename": filename, "url": url}
        if kind == "html":
            attachment["charset"] = "utf-8"
        status, _, body = api.request("POST", f"{LIB}/items", [attachment], wh)
        check_common(status, body)
        if status != 200:
            raise Stop("attachment_create_failed", 1, "The local API rejected the attachment object; see body.",
                       status=status, body=text(body))
        result = json.loads(body)
        failed = (result.get("failed") or {}).get("0")
        if failed or "0" not in (result.get("successful") or {}):
            raise Stop("attachment_create_failed", 1, "The local API rejected the attachment object; see message.",
                       status=status, failed=failed, body=text(body))
        akey, reused = result["successful"]["0"]["key"], False
        log(f"created attachment {akey}")

    outcome = upload_file(api, wh, akey, pdf_bytes, md5, filename, mtime, content_type)
    after = get_json(api, f"{LIB}/items/{akey}",
                     ("attachment_not_found", "The attachment vanished after upload; re-run.", {"attachment_key": akey}))
    read_md5 = ((after.get("data") or {}).get("md5") or "").lower()
    if read_md5 != md5:
        raise Stop("md5_mismatch", 1, "Zotero stored a different file; re-run to upload again, or inspect the attachment in Zotero.",
                   item_key=item_key, attachment_key=akey, md5_sent=md5, md5_read_back=read_md5 or None,
                   filename=(after.get("data") or {}).get("filename"))
    return {"code": "ok", "item_key": item_key, "attachment_key": akey, "md5_ok": True, "md5": md5,
            "filename": (after.get("data") or {}).get("filename") or filename, "reused_attachment": reused,
            "file_existed": outcome == "exists"}


# ---- records (stream mode) -------------------------------------------------

def slug_of(path, record):
    slug = record.get("slug")
    if isinstance(slug, str) and slug:
        return slug
    return path.stem if path is not None else None


def parse_stream(raw):
    """Records from stdin text: JSONL, a JSON array or one object (any sequence of JSON values, really)."""
    decoder, records, i, n = json.JSONDecoder(), [], 0, len(raw)
    while True:
        while i < n and raw[i].isspace():
            i += 1
        if i >= n:
            break
        try:
            value, i = decoder.raw_decode(raw, i)
        except ValueError as e:
            raise Stop("input_invalid", 1, "stdin must carry records as JSONL, a JSON array or one JSON object", error=str(e))
        for rec in (value if isinstance(value, list) else [value]):
            if not isinstance(rec, dict):
                raise Stop("input_invalid", 1, "every record is a JSON object", got=type(rec).__name__)
            records.append(rec)
    return records


def load_records(paths):
    """[(path or None, record)] from the record files, else from stdin; none at all -> no_records."""
    if paths:
        entries = []
        for p in paths:
            path = Path(p)
            try:
                rec = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                raise Stop("record_invalid", 1, "every record file holds one JSON object; nothing was done",
                           path=str(path), error=str(e))
            if not isinstance(rec, dict):
                raise Stop("record_invalid", 1, "every record file holds one JSON object; nothing was done", path=str(path))
            entries.append((path, rec))
    else:
        entries = [(None, rec) for rec in parse_stream(sys.stdin.read())]
    if not entries:
        raise Stop("no_records", 1, "pass record files, or pipe records (JSONL, a JSON array or one object) to stdin")
    return entries


def save_record(path, record):
    """Write the record back atomically: a temp file in the same directory, then os.replace."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class Outcome:
    """One record's result: status ok | skipped | failed, its summary line, and whether the record changed."""

    def __init__(self, path, record):
        self.path, self.record, self.changed = path, record, False
        self.status, self.line = "failed", {"slug": slug_of(path, record), "code": "not_run"}

    def set(self, status, code, /, changed=False, **fields):
        self.status, self.changed = status, changed
        self.line = {"slug": self.line["slug"], "code": code, **fields}

    def fail(self, stop, changed=False):
        self.set("failed", stop.code, changed, **stop.extra, **({"hint": stop.hint} if stop.hint else {}))


def write_results(outcomes, in_place, stopped=None):
    """Print the stream output; return the exit code (0 all ok/skipped, 1 any failed, the Stop's when stopped early)."""
    counts = {"total": len(outcomes), "ok": 0, "skipped": 0, "failed": 0}
    for o in outcomes:
        if in_place and o.changed and o.path is not None:
            try:
                save_record(o.path, o.record)
            except OSError as e:
                o.set("failed", "write_failed", path=str(o.path), error=str(e),
                      hint="the record file could not be rewritten; what was written to Zotero stands")
        counts[o.status] += 1
        line = json.dumps(o.line, ensure_ascii=False)
        if in_place:
            print(line)
        else:
            print(json.dumps(o.record, ensure_ascii=False))
            log(line)
    if stopped is not None:
        counts["stopped"] = stopped.code
        log(f"stopped early: {stopped.code}" + (f" - {stopped.hint}" if stopped.hint else ""))
    summary = json.dumps({"summary": counts}, ensure_ascii=False)
    print(summary) if in_place else log(summary)
    if stopped is not None:
        return stopped.exit_code
    return 1 if counts["failed"] else 0


def item_key_of(rec):
    """The record's item key: saved.key, else found.key (spec 3.2)."""
    for section in ("saved", "found"):
        block = rec.get(section)
        if isinstance(block, dict) and block.get("key"):
            return block["key"]
    return None


def url_of(rec, fallback):
    """The attachment url: item.url, else https://doi.org/<item.DOI>, else the --url fallback."""
    item = rec.get("item") if isinstance(rec.get("item"), dict) else {}
    url = item.get("url")
    if isinstance(url, str) and url.strip():
        return url.strip()
    doi = item.get("DOI")
    if isinstance(doi, str) and doi.strip():
        return "https://doi.org/" + doi.strip()
    return fallback


def attach_record(api, wh, o, args):
    """Run the stream flow for one record, filling its Outcome; per-record failures come back as Stop."""
    rec = o.record
    item_key = item_key_of(rec)
    if not item_key:
        raise Stop("no_item_key", 1, "the record has neither saved.key nor found.key: run create_item.py "
                   "(or find_in_library.py) first")
    attach = rec.get("attach")
    if isinstance(attach, dict) and attach.get("md5_ok") is True:
        o.set("skipped", "skipped", reason="attach.md5_ok", key=item_key, attachment_key=attach.get("key"))
        return

    name = rec.get("file")
    if isinstance(name, str) and name.strip():
        file_path = Path(name.strip()).expanduser()
        if not file_path.is_absolute():
            file_path = (o.path.parent if o.path is not None else Path.cwd()) / file_path
    elif args.file:
        file_path = Path(args.file).expanduser()
    else:
        raise Stop("no_file", 1, "put the file name (relative to the record) in the record's `file`, or pass --file")
    url = url_of(rec, args.url)
    if not url:
        raise Stop("no_url", 1, "the record has neither item.url nor item.DOI: pass --url (the canonical article page)")
    url = check_url(url)
    pdf, pdf_bytes, kind, content_type, ext = load_file(file_path)
    title = args.title or ("PDF" if kind == "pdf" else "Snapshot")

    res = attach_one(api, wh, item_key, pdf, pdf_bytes, kind, content_type, ext, url, title, None, args.dry_run)
    if res["code"] == "already_attached":
        rec["attach"] = {"key": res["attachment_key"], "md5_ok": True, "filename": res["filename"], "url": url,
                         "attached_at": now_iso()}
        o.set("skipped", "skipped", changed=True, reason="already_attached", key=item_key,
              attachment_key=res["attachment_key"], filename=res["filename"])
    elif res.get("dry_run"):
        o.set("ok", "ok", dry_run=True, key=item_key, kind=kind, filename=res["filename"], url=url, size=res["size"],
              reused_attachment=res["reused_attachment"], attachment_key=res["attachment_key"])
    else:
        rec["attach"] = {"key": res["attachment_key"], "md5_ok": True, "filename": res["filename"], "url": url,
                         "attached_at": now_iso()}
        o.set("ok", "ok", changed=True, key=item_key, attachment_key=res["attachment_key"], filename=res["filename"],
              reused_attachment=res["reused_attachment"], file_existed=res["file_existed"])


def run_stream(api, args):
    entries = load_records(args.records)
    if args.url:
        check_url(args.url)
    server_id = live_server_id(api)
    wh = write_headers(load_key(args.key_file, server_id), server_id)
    outcomes, stopped = [], None
    for path, rec in entries:
        o = Outcome(path, rec)
        outcomes.append(o)
        if stopped is not None:  # Zotero went away: the rest cannot be checked
            o.fail(stopped)
            continue
        try:
            attach_record(api, wh, o, args)
        except Stop as stop:
            if stop.exit_code == 2:
                stopped = stop
            o.fail(stop)
    sys.exit(write_results(outcomes, args.in_place, stopped))


def run_single(api, args):
    pdf_url = check_url(args.url)
    pdf, pdf_bytes, kind, content_type, ext = load_file(args.file)
    title = args.title or ("PDF" if kind == "pdf" else "Snapshot")

    server_id = live_server_id(api)
    key = load_key(args.key_file, server_id)
    wh = write_headers(key, server_id)
    res = attach_one(api, wh, args.key, pdf, pdf_bytes, kind, content_type, ext, pdf_url, title, args.filename, args.dry_run)
    emit(res.pop("code"), 0, **res)


def parse_args():
    p = argparse.ArgumentParser(
        description="Attach a file — a PDF, or an HTML snapshot of the article page when no PDF can be had — "
                    "to an existing Zotero item via the local write API (3-step upload, md5 read back): "
                    "one item (--key --file --url) or a stream of records.",
        epilog="Single mode: exit 0 = done (code ok or already_attached); 1 = not done, see code/hint. "
               "Stream mode: exit 0 = every record ok or skipped; 1 = some record failed (its code is in its summary line). "
               "Both: 2 = cannot check (zotero_unreachable, local_api_disabled, no_key, key_rejected, server_mismatch). "
               "Records: the item key is saved.key, else found.key; the file is `file` (relative to the record), else --file; "
               "the url is item.url, else https://doi.org/<DOI>, else --url; attach.md5_ok already true -> skipped.")
    p.add_argument("records", nargs="*", metavar="RECORD",
                   help="record files (stream mode); none, and no --key: records are read from stdin")
    p.add_argument("-i", "--in-place", action="store_true",
                   help="stream mode: write each updated record back to its file; stdout gets one summary line per record")
    p.add_argument("--key", metavar="ITEMKEY", help="single mode: key of the parent item (8 characters)")
    p.add_argument("--cite", metavar="CITEKEY", help="single mode: the parent item's citationKey, resolved to its key")
    p.add_argument("--file", "--pdf", dest="file", metavar="PATH",
                   help="the file to upload: a PDF, or an .html page saved from the browser (--pdf is an alias); "
                        "stream mode: fallback for records without `file`")
    p.add_argument("--url", "--pdf-url", dest="url", metavar="URL",
                   help="canonical source URL stored on the attachment (fall back to https://doi.org/<DOI>); "
                        "EZproxy-style hosts are rejected; stream mode: fallback for records without item.url / item.DOI")
    p.add_argument("--filename", metavar="NAME",
                   help="single mode: filename inside Zotero; default '<firstCreator> - <year> - <title>.<ext>' from the parent item")
    p.add_argument("--title", help="attachment title (default: PDF, or Snapshot for an HTML file)")
    p.add_argument("--dry-run", action="store_true", help="run the pre-checks only; write nothing")
    p.add_argument("--key-file", default=DEFAULT_KEY_FILE, metavar="PATH",
                   help="JSON file holding the local API key (default: %(default)s); env ZOTERO_LOCAL_API_KEY overrides")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL, help="local API base URL (default: %(default)s)")
    args = p.parse_args()
    if args.key and args.cite:
        p.error("--key and --cite exclude each other")
    if args.key or args.cite:
        if args.records:
            p.error("--key / --cite (single mode) and record paths (stream mode) exclude each other")
        if args.in_place:
            p.error("-i belongs to stream mode")
        if not args.file or not args.url:
            p.error("single mode needs --key or --cite, --file and --url")
    else:
        if args.filename:
            p.error("--filename belongs to single mode; stream mode names files from the parent item")
        if not args.records and args.in_place:
            p.error("-i needs record paths: records from stdin have no file to write back to")
        if not args.records and sys.stdin.isatty():
            p.error("pass record files, pipe records to stdin, or use --key --file --url for single mode")
    return args


def main():
    args = parse_args()
    api = Api(args.base_url)
    if args.cite:
        args.key = resolve_cite(api, args.cite)
    if args.key:
        run_single(api, args)
    else:
        run_stream(api, args)


if __name__ == "__main__":
    try:
        main()
    except Stop as stop:
        emit(stop.code, stop.exit_code, stop.hint, **stop.extra)
