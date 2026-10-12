# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Attach a verified PDF or HTML snapshot to existing Zotero items through the local write API, one item or a stream of records.

Works the same for a just-created item and for an old one. Flow per file:
pre-checks (file, url, item, existing children) -> identity check -> create
the child attachment, or reuse an empty one left by an interrupted run ->
3-step upload -> read back the md5. A child that already holds a file with
the same md5 is reported as already attached and never uploaded twice.

The identity check gates every upload, --dry-run included, with no way
around it. What writes nothing to the library needs no check: a file already
attached (same md5), and a record skipped as library_has_attachment.
- with a record (stream mode, --record): the md5 of the file about to be
  uploaded equals the record's `pdf.md5` and `pdf.code` is a pass (ok,
  ok_on_page_2, ok_on_page_3, ok_by_words), or it equals `pdf_accepted.md5`
  and `pdf_accepted.reason` is not empty (the agent read page 1 and took the
  file). Otherwise not_verified (exit 1): run check_pdf.py -i on the record
  first, or read page 1 and write pdf_accepted. HTML snapshots alike.
- without a record (--key/--cite --file --url): the parent item and the file
  (with --file-version, if given) go to check_pdf.py (next to this script,
  as one record on stdin); a code that is not a pass, or check_pdf unable to
  check, refuses with not_verified, the check code and a short evidence
  summary — unless --accept "<reason>" is given, which attaches and puts
  `accepted` and `check_code` in the output.

Record defaults (resolved as check_pdf.py resolves them, so both scripts
mean the same file): the file is the record's `file` (relative to the
record's directory; stdin records: the working directory), else --file
(stream mode), else <slug>.pdf, else <slug>.html next to the record (<slug>
= the record file's stem; stdin records have no such default).
file_version is the record's `file_version`, else `snapshot` for an HTML
file, else the `version` of the last line in <work>/fetch.jsonl (<work> =
the parent of the record's directory) with the record's slug or stem, code
"ok" and a version (`submitted` read as `preprint`), else `published`.

Attachment title: the record's `attach_title`, else --title, else from
file_version — published -> PDF, accepted -> Accepted manuscript, preprint ->
Preprint, supplement -> Supplement, snapshot -> Snapshot, unknown -> Full
text (version unknown) (any other value as written, first letter
capitalized). In single mode the flags speak for that one item and win:
--title over `attach_title`, as --key/--file/--url/--file-version over the
record's own.

Single mode (--key/--cite --file --url, or --record PATH): stdout is exactly
one JSON object with a stable `code` (`ok` or `already_attached` on
success). Without a record, file_version is --file-version, else snapshot
for an HTML file, else published. --record R takes from R what the flags
leave out — the item key (saved.key, else found.key; a --key/--cite naming
another item -> record_key_mismatch), the file (its default above; a given
--file is taken from the working directory as usual), the url, the
file_version — checks the file against R (--accept does not apply), and
after success writes `attach` back to R.

A record's item key is `saved.key`, else `found.key` — but a `found` with
code near_match (a similar title, or a preprint/published pair: probably
another version of the paper) stops the record with unresolved_match (exit
1; found_key, found_reason): the same paper -> replace found with {"key":
"<key>"}; a different one -> delete found, add the key to distinct_from,
run create_item.py. This holds in stream mode and with --record, whatever
--key says; `saved.key` always wins.

Stream mode (record paths, or records on stdin as JSONL / a JSON array / one
object): the item key as above; the file is the record default above; the
url is `item.url`, else
https://doi.org/<item.DOI>, else --url. A record whose `attach.md5_ok` is
already true is skipped; a record with no file at all whose library state —
`readback` (written by find_in_library.py --readback), else `found` — lists
attachments is skipped as library_has_attachment; a file in hand for an
item that already holds a PDF (another md5) is skipped as library_has_pdf
unless the record says `need_file: true`; a file already attached
(same md5) is skipped too, and `attach` is filled in. On success the record
gains `attach = {key, md5_ok, filename, url, title, file_version,
attached_at}`. Without -i the updated records go to stdout one per line, and
one summary line per record plus the final {"summary": ...} go to stderr;
with -i each changed record is written back to its file and stdout carries
those summary lines instead. Exit 0 = every record ok or skipped, 1 = some
failed (no_item_key, no_file, no_url, file_not_found, not_verified,
item_not_found, upload_failed, ...), 2 = cannot check (Zotero unreachable,
local API disabled, no key, key rejected, key belongs to another Zotero
instance).

Diagnostics go to stderr; the API key is never printed.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

DEFAULT_BASE_URL = "http://127.0.0.1:23119"
DEFAULT_KEY_FILE = "~/.config/zotero/local-api-key"
LIB = "/api/users/0"
TITLE_MAX = 120
ILLEGAL_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')
CHILD_TYPES = {"attachment", "note", "annotation"}

PASS_CODES = ("ok", "ok_on_page_2", "ok_on_page_3", "ok_by_words")
VERSION_TITLES = {"published": "PDF", "accepted": "Accepted manuscript", "preprint": "Preprint",
                  "supplement": "Supplement", "snapshot": "Snapshot", "unknown": "Full text (version unknown)"}
VERSION_ALIASES = {"submitted": "preprint"}  # the older links' word for a preprint, still accepted
CHECK_SCRIPT = Path(__file__).resolve().parent / "check_pdf.py"
CHECK_TIMEOUT = 180
EVIDENCE_KEYS = ("extractor", "title_page", "title_words", "doi_found", "first_author_found", "dois_on_page_1",
                 "erratum_marker", "supplement_marker", "denial_marker", "page_count", "text_chars")
EXCERPT_CHARS = 300
RECORD_HINT = ("run check_pdf.py -i on the record first; if it does not pass, read page 1 and, if it is this paper, "
               "write \"pdf_accepted\": {\"md5\": \"<md5>\", \"reason\": \"<what you read>\"} into the record")
SINGLE_HINT = ("read page 1 (the pdf skill): if it is this paper, run again with --accept \"<what you read>\"; "
               "otherwise get the right file")

EPILOG = """\
single mode (stdout: one JSON object):
  --key K | --cite C  --file F --url U [--file-version V]
                                         checks F with check_pdf.py against the parent item (V passed on as
                                         the file_version); not a pass -> not_verified (check_code, evidence)
                                         unless --accept "<reason>"
  --record R [--key|--cite] [--file] [--url] [--file-version] [--title] [--filename]
                                         what the flags leave out comes from R (saved.key / found.key, the
                                         record's file default, item.url / DOI, file_version); the check comes
                                         from R's pdf / pdf_accepted (--accept is refused: write pdf_accepted
                                         into R); on success R gains `attach`
  a file already attached (same md5) is already_attached without any check: nothing is written
  exit 0 = ok | already_attached; 1 = not done (see code / hint); 2 = cannot check Zotero

stream mode (record paths or stdin; -i writes records back):
  item key saved.key, else found.key (found.code near_match -> unresolved_match, also with --record);
  file: `file`, else --file, else <slug>.pdf, else <slug>.html next to
  the record; url: item.url, else https://doi.org/<DOI>, else --url; title: attach_title, else --title,
  else from file_version; attach.md5_ok -> skipped; no file but readback (else found) lists attachments ->
  skipped (library_has_attachment); both, and an already attached file, need no check
  exit 0 = every record ok or skipped; 1 = some failed; 2 = cannot check Zotero

codes: ok | already_attached (single) / skipped (stream) | not_verified | no_item_key | no_file | no_url |
  file_not_found | unsupported_file | invalid_pdf_url | proxied_url | unresolved_match | record_key_mismatch | record_invalid |
  item_not_found | not_a_parent | upload_failed | md5_mismatch | write_failed | ... ;
  exit 2: zotero_unreachable | local_api_disabled | no_key | key_rejected | server_mismatch

titles from file_version: published PDF | accepted Accepted manuscript | preprint (or submitted) Preprint |
  supplement Supplement | snapshot Snapshot | unknown Full text (version unknown); an HTML file without
  file_version is a snapshot

examples:
  uv run attach_file.py -i <work>/records/*.json
  uv run attach_file.py --record <work>/records/<slug>.json
  uv run attach_file.py --cite <key> --file paper.pdf --url https://doi.org/<DOI> [--accept "<what you read>"]
"""


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


# ---- the pre-checks, shared by both modes ------------------------------------

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


class Loaded(NamedTuple):
    """A file read for upload."""
    path: Path
    data: bytes
    kind: str          # pdf | html
    content_type: str
    ext: str
    md5: str


def load_file(path):
    """Read the file -> Loaded; only a PDF or an HTML page saved as .html passes."""
    pdf = Path(path).expanduser()
    if not pdf.is_file():
        raise Stop("file_not_found", 1, "Point --file (or the record's `file`) at the downloaded file.", file=str(pdf))
    pdf_bytes = pdf.read_bytes()
    md5 = hashlib.md5(pdf_bytes).hexdigest()
    head = pdf_bytes[:2048].lstrip().lower()
    if pdf_bytes.startswith(b"%PDF-"):
        return Loaded(pdf, pdf_bytes, "pdf", "application/pdf", ".pdf", md5)
    if pdf.suffix.lower() in (".html", ".htm") and (head.startswith(b"<!doctype") or head.startswith(b"<html") or b"<html" in head):
        return Loaded(pdf, pdf_bytes, "html", "text/html", ".html", md5)
    raise Stop("unsupported_file", 1, "Only a PDF (%PDF- header) or an HTML page saved as .html is accepted; "
               "a \"PDF\" that is really HTML means the download returned a web page.",
               file=str(pdf), size=len(pdf_bytes), head=pdf_bytes[:16].decode("latin-1"))


def get_parent(api, item_key):
    """The parent item's data; a missing item or a child item stops here."""
    item = get_json(api, f"{LIB}/items/{item_key}",
                    ("item_not_found", "No item with that key; check the key from create_item.py / find_in_library.py.",
                     {"item_key": item_key}))
    data = item.get("data") or {}
    if data.get("itemType") in CHILD_TYPES or data.get("parentItem"):
        raise Stop("not_a_parent", 1, "Attachments hang off a regular item; pass the parent item's key.",
                   item_key=item_key, item_type=data.get("itemType"), parent_item=data.get("parentItem"))
    return data


# ---- the identity check: a precondition of every upload ---------------------

def verify_record(rec, f):
    """The record's own check of this very file -> output fields; anything else is not_verified."""
    pdf = rec.get("pdf") if isinstance(rec.get("pdf"), dict) else None
    code = pdf.get("code") if pdf else None
    checked = pdf is not None and str(pdf.get("md5") or "").strip().lower() == f.md5
    if checked and code in PASS_CODES:
        return {"check_code": code}
    acc = rec.get("pdf_accepted") if isinstance(rec.get("pdf_accepted"), dict) else None
    reason = acc.get("reason") if acc else None
    reason = reason.strip() if isinstance(reason, str) else ""
    if acc and str(acc.get("md5") or "").strip().lower() == f.md5:
        if reason:
            return {"check_code": code if checked else None, "accepted": reason}
        why = "pdf_accepted names this file but gives no reason"
    elif pdf is None:
        why = "the record has no `pdf`: this file was never checked"
    elif not pdf.get("md5"):
        why = "`pdf` has no md5 (checked by an older check_pdf.py): check again"
    elif not checked:
        why = "`pdf.md5` is another file's: the file changed or another one was checked"
    else:
        why = f"pdf.code {code} is not a pass"
    raise Stop("not_verified", 1, RECORD_HINT, file=str(f.path), md5=f.md5, pdf_code=code, why=why)


def json_values(text):
    """Every JSON object found in text, which may mix JSON with log lines."""
    decoder, out, i = json.JSONDecoder(), [], 0
    while True:
        i = text.find("{", i)
        if i < 0:
            return out
        try:
            value, end = decoder.raw_decode(text, i)
        except ValueError:
            i += 1
            continue
        out.append(value)
        i = end


def evidence_summary(evidence):
    if not isinstance(evidence, dict):
        return None
    out = {k: evidence[k] for k in EVIDENCE_KEYS if evidence.get(k) is not None}
    if isinstance(evidence.get("excerpt"), str):
        out["excerpt"] = evidence["excerpt"][:EXCERPT_CHARS]
    return out


def run_check(data, f, file_version=None):
    """check_pdf.py on {item, file[, file_version]} as one stdin record -> (code, exit status, evidence summary)."""
    record = {"item": data, "file": str(f.path.resolve())}
    if file_version:
        record["file_version"] = file_version
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    try:
        proc = subprocess.run([sys.executable, str(CHECK_SCRIPT)], input=json.dumps(record, ensure_ascii=False),
                              capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
                              timeout=CHECK_TIMEOUT)
    except subprocess.TimeoutExpired:
        return "check_timeout", None, None
    except OSError as e:
        return "check_failed", None, {"error": str(e)}
    out = json_values(proc.stdout)
    for value in out:  # the checked record
        if isinstance(value, dict) and isinstance(value.get("pdf"), dict):
            return value["pdf"].get("code"), proc.returncode, evidence_summary(value["pdf"].get("evidence"))
    for value in json_values(proc.stderr) + out:  # its summary line, or a failure of the whole run
        if isinstance(value, dict) and isinstance(value.get("code"), str):
            return value["code"], proc.returncode, None
    tail = proc.stderr.strip()[-400:]
    return "check_failed", proc.returncode, ({"stderr": tail} if tail else None)


def verify_single(data, f, accept, file_version=None):
    """check_pdf.py's verdict on a file without a record -> output fields; not a pass and no --accept -> not_verified."""
    code, status, evidence = run_check(data, f, file_version)
    log(f"check_pdf: {code} (exit {status})")
    if status == 0 and code in PASS_CODES:
        return {"check_code": code}
    if accept:
        log(f"not a pass; attached on --accept: {accept}")
        return {"check_code": code, "accepted": accept}
    extra = {"file": str(f.path), "md5": f.md5, "check_code": code}
    if evidence:
        extra["evidence"] = evidence
    raise Stop("not_verified", 1, SINGLE_HINT, **extra)


# ---- the attach itself, shared by both modes --------------------------------

def attach_one(api, wh, item_key, f, url, title, filename_arg, dry_run, verify):
    """Attach one file to one item; returns the result fields with `code` ok | already_attached (v1's shape).

    verify(parent data) -> output fields, or raises not_verified: the identity check, run once it is clear that
    something would be uploaded (a file already attached writes nothing and needs none), --dry-run included."""
    md5 = f.md5
    mtime = int(f.path.stat().st_mtime * 1000)
    data = get_parent(api, item_key)
    filename = clean_filename(filename_arg) if filename_arg else default_filename(data, f.ext)
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
                    "filename": cd.get("filename"), "title": cd.get("title"), "reused_attachment": False, "md5": md5}
        if (reuse_key is None and cd.get("linkMode") in ("imported_url", "imported_file")
                and not cd.get("md5") and cd.get("filename") == filename):
            reuse_key = child["key"]
    verdict = verify(data)  # an upload is next: the file must be this paper
    if reuse_key:
        log(f"reusing empty attachment {reuse_key} (same filename, no file)")

    if dry_run:
        return {"code": "ok", "dry_run": True, "item_key": item_key, "kind": f.kind, "filename": filename, "title": title,
                "md5": md5, "size": len(f.data), "pdf_url": url, "reused_attachment": bool(reuse_key),
                "attachment_key": reuse_key,
                "existing_attachments": sum(1 for c in children if (c.get("data") or {}).get("itemType") == "attachment"),
                **verdict}

    if reuse_key:
        akey, reused = reuse_key, True
    else:
        attachment = {"itemType": "attachment", "linkMode": "imported_url", "parentItem": item_key,
                      "title": title, "contentType": f.content_type, "filename": filename, "url": url}
        if f.kind == "html":
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

    outcome = upload_file(api, wh, akey, f.data, md5, filename, mtime, f.content_type)
    after = get_json(api, f"{LIB}/items/{akey}",
                     ("attachment_not_found", "The attachment vanished after upload; re-run.", {"attachment_key": akey}))
    read_md5 = ((after.get("data") or {}).get("md5") or "").lower()
    if read_md5 != md5:
        raise Stop("md5_mismatch", 1, "Zotero stored a different file; re-run to upload again, or inspect the attachment in Zotero.",
                   item_key=item_key, attachment_key=akey, md5_sent=md5, md5_read_back=read_md5 or None,
                   filename=(after.get("data") or {}).get("filename"))
    return {"code": "ok", "item_key": item_key, "attachment_key": akey, "md5_ok": True, "md5": md5,
            "filename": (after.get("data") or {}).get("filename") or filename,
            "title": (after.get("data") or {}).get("title") or title, "reused_attachment": reused,
            "file_existed": outcome == "exists", **verdict}


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
    """The record's item key: saved.key, else found.key (spec 3.2). A found that is only a near match (a similar
    title, a preprint/published pair: likely another version) is not an answer yet -> unresolved_match."""
    saved = rec.get("saved")
    if isinstance(saved, dict) and saved.get("key"):
        return saved["key"]
    found = rec.get("found")
    if isinstance(found, dict) and found.get("key"):
        if found.get("code") == "near_match":
            key = found["key"]
            raise Stop("unresolved_match", 1, f'same paper: replace found with {{"key": "{key}"}}; different paper: '
                       "delete found, add the key to distinct_from, run create_item.py",
                       found_key=key, found_reason=found.get("reason"))
        return found["key"]
    return None


def library_state(rec):
    """What the library holds for the record: `readback` (read after this run's writes), else `found`."""
    for section in ("readback", "found"):
        block = rec.get(section)
        if isinstance(block, dict):
            return block
    return {}


def record_dir(path):
    """The record's directory; stdin records: the working directory."""
    return path.parent if path is not None else Path.cwd()


def record_file(path, rec, fallback):
    """The record's file, as check_pdf.py resolves it: `file` (relative to the record), else the fallback (--file),
    else <stem>.pdf, else <stem>.html beside the record file; None when there is none."""
    name = rec.get("file")
    if isinstance(name, str) and name.strip():
        file_path = Path(name.strip()).expanduser()
        return file_path if file_path.is_absolute() else record_dir(path) / file_path
    if fallback:
        return Path(fallback).expanduser()
    if path is not None:
        for suffix in (".pdf", ".html"):
            if (candidate := path.with_suffix(suffix)).is_file():
                return candidate
    return None


def norm_version(value):
    """A file_version as written, trimmed; `submitted` reads as preprint; empty -> None."""
    value = value.strip() if isinstance(value, str) else ""
    return VERSION_ALIASES.get(value, value) or None


def file_version_of(path, rec, kind, override=None):
    """--file-version, else `file_version`, else snapshot for an HTML file, else the `version` of the last ok line of
    <work>/fetch.jsonl for this record (its slug or file stem), else published."""
    given = norm_version(override) or norm_version(rec.get("file_version"))
    if given:
        return given
    if kind == "html":
        return "snapshot"
    version = None
    if path is not None:
        slugs = {slug_of(path, rec), path.stem}
        try:
            lines = (path.absolute().parent.parent / "fetch.jsonl").read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            lines = []
        for line in lines:
            try:
                row = json.loads(line)
            except ValueError:
                continue  # a torn or foreign line
            if (isinstance(row, dict) and row.get("slug") in slugs and row.get("code") == "ok"
                    and isinstance(row.get("version"), str) and row["version"].strip()):
                version = row["version"].strip()
    return norm_version(version) or "published"


def version_title(version):
    """The attachment title a file_version stands for; a value outside the list as written, first letter capitalized."""
    if version in VERSION_TITLES:
        return VERSION_TITLES[version]
    text = version.replace("_", " ").strip()
    return text[:1].upper() + text[1:] if text else "PDF"


def record_title(rec):
    title = rec.get("attach_title")
    return title.strip() if isinstance(title, str) and title.strip() else None


def attach_block(res, url, version):
    """The record's `attach` after an upload or an already-attached file."""
    return {"key": res["attachment_key"], "md5_ok": True, "filename": res["filename"], "url": url,
            "title": res.get("title"), "file_version": version, "attached_at": now_iso()}


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

    file_path = record_file(o.path, rec, args.file)
    if file_path is None:
        existing = library_state(rec).get("attachments")
        if existing:
            # Nothing to upload and the library already holds a file for this item: not a failure.
            o.set("skipped", "skipped", reason="library_has_attachment", key=item_key,
                  attachments=len(existing) if isinstance(existing, list) else existing)
            return
        raise Stop("no_file", 1, "put the file next to the record as <slug>.pdf (or <slug>.html), name it in the "
                   "record's `file`, or pass --file")
    url = url_of(rec, args.url)
    if not url:
        raise Stop("no_url", 1, "the record has neither item.url nor item.DOI: pass --url (the canonical article page)")
    url = check_url(url)
    f = load_file(file_path)
    held = [a for a in library_state(rec).get("attachments") or []
            if isinstance(a, dict) and a.get("contentType") == "application/pdf"]
    if held and rec.get("need_file") is not True and all(a.get("md5") != f.md5 for a in held):
        # The item already has a PDF and nobody asked for another one: a second copy is clutter, not a fix.
        o.set("skipped", "skipped", reason="library_has_pdf", key=item_key, attachment_key=held[0].get("key"),
              hint="the library item already holds a PDF; to add this file as well (the published PDF beside a "
                   "preprint), set need_file: true in the record and list the old attachment for trash_item.py")
        return
    version = file_version_of(o.path, rec, f.kind)
    title = record_title(rec) or args.title or version_title(version)

    res = attach_one(api, wh, item_key, f, url, title, None, args.dry_run, lambda data: verify_record(rec, f))
    verdict = {k: res[k] for k in ("check_code", "accepted") if k in res}
    if res["code"] == "already_attached":
        if not args.dry_run:
            rec["attach"] = attach_block(res, url, version)
        o.set("skipped", "skipped", changed=not args.dry_run, reason="already_attached", key=item_key,
              attachment_key=res["attachment_key"], filename=res["filename"], title=res["title"])
    elif res.get("dry_run"):
        o.set("ok", "ok", dry_run=True, key=item_key, kind=f.kind, filename=res["filename"], title=title, url=url,
              size=res["size"], reused_attachment=res["reused_attachment"], attachment_key=res["attachment_key"],
              **verdict)
    else:
        rec["attach"] = attach_block(res, url, version)
        o.set("ok", "ok", changed=True, key=item_key, attachment_key=res["attachment_key"], filename=res["filename"],
              title=res["title"], file_version=version, reused_attachment=res["reused_attachment"],
              file_existed=res["file_existed"], **verdict)


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
    """One item: from the flags (v1), or from --record with the flags as overrides."""
    path = rec = None
    if args.record:
        path, rec = load_records([args.record])[0]
        rec_key = item_key_of(rec)
        if args.key and rec_key and args.key != rec_key:
            raise Stop("record_key_mismatch", 1, "the record belongs to another item: drop --key / --cite, "
                       "or pass the record of this item", item_key=args.key, record_key=rec_key, record=str(path))
        args.key = args.key or rec_key
        if not args.key:
            raise Stop("no_item_key", 1, "the record has neither saved.key nor found.key: run create_item.py "
                       "(or find_in_library.py) first, or pass --key / --cite", record=str(path))
    file_path = Path(args.file).expanduser() if args.file else record_file(path, rec, None)
    if file_path is None:
        raise Stop("no_file", 1, "put the file next to the record as <slug>.pdf (or <slug>.html), name it in the "
                   "record's `file`, or pass --file", record=str(path))
    url = args.url or (url_of(rec, None) if rec is not None else None)
    if not url:
        raise Stop("no_url", 1, "the record has neither item.url nor item.DOI: pass --url (the canonical article page)",
                   record=str(path))
    pdf_url = check_url(url)
    f = load_file(file_path)
    if rec is not None:
        version = file_version_of(path, rec, f.kind, args.file_version)
        title = args.title or record_title(rec) or version_title(version)
        verify = lambda data: verify_record(rec, f)
    else:
        version = norm_version(args.file_version) or ("snapshot" if f.kind == "html" else "published")
        title = args.title or version_title(version)
        # no record to vouch for the file: check_pdf.py checks it against the parent item
        verify = lambda data: verify_single(data, f, args.accept, norm_version(args.file_version))

    server_id = live_server_id(api)
    wh = write_headers(load_key(args.key_file, server_id), server_id)
    res = attach_one(api, wh, args.key, f, pdf_url, title, args.filename, args.dry_run, verify)
    code = res.pop("code")
    if rec is not None:
        res["record"] = str(path)
        if not args.dry_run:
            rec["attach"] = attach_block(res, pdf_url, version)
            try:
                save_record(path, rec)
            except OSError as e:
                raise Stop("write_failed", 1, "the record file could not be rewritten; what was written to Zotero stands",
                           **res, attach_code=code, error=str(e))
    emit(code, 0, **res)


def parse_args():
    p = argparse.ArgumentParser(
        description="Attach a file — a PDF, or an HTML snapshot of the article page when no PDF can be had — "
                    "to an existing Zotero item via the local write API (3-step upload, md5 read back), only once "
                    "it has passed check_pdf.py or been accepted on a reading of page 1: one item "
                    "(--key/--cite --file --url, or --record) or a stream of records.",
        epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("records", nargs="*", metavar="RECORD",
                   help="record files (stream mode); none, and no --key / --cite / --record: records are read from stdin")
    p.add_argument("-i", "--in-place", action="store_true",
                   help="stream mode: write each updated record back to its file; stdout gets one summary line per record")
    p.add_argument("--key", metavar="ITEMKEY", help="single mode: key of the parent item (8 characters)")
    p.add_argument("--cite", metavar="CITEKEY", help="single mode: the parent item's citationKey, resolved to its key")
    p.add_argument("--record", metavar="PATH",
                   help="single mode: the paper's record; supplies the item key, file and url the flags leave out, "
                        "vouches for the file (pdf / pdf_accepted), and gets `attach` written back")
    p.add_argument("--file", "--pdf", dest="file", metavar="PATH",
                   help="the file to upload: a PDF, or an .html page saved from the browser (--pdf is an alias); "
                        "a relative path is taken from the working directory, also with --record; "
                        "stream mode: for records without `file`, ahead of <slug>.pdf / <slug>.html (as check_pdf.py --pdf)")
    p.add_argument("--url", "--pdf-url", dest="url", metavar="URL",
                   help="canonical source URL stored on the attachment (fall back to https://doi.org/<DOI>); "
                        "EZproxy-style hosts are rejected; stream mode: fallback for records without item.url / item.DOI")
    p.add_argument("--filename", metavar="NAME",
                   help="single mode: filename inside Zotero; default '<firstCreator> - <year> - <title>.<ext>' from the parent item")
    p.add_argument("--title",
                   help="attachment title; default from file_version (PDF, Accepted manuscript, Preprint, Supplement, "
                        "Snapshot, Full text (version unknown)); stream mode: for records without attach_title; "
                        "single mode: wins over attach_title")
    p.add_argument("--file-version", metavar="V",
                   help="single mode: the file's version — published, accepted, preprint (or submitted), supplement, "
                        "snapshot, unknown; without a record it goes to check_pdf.py (doi_mismatch is checked for "
                        "published only) and to the derived title; with --record it overrides the record's file_version")
    p.add_argument("--accept", metavar="REASON",
                   help="single mode without a record: attach although check_pdf.py does not pass the file, "
                        "because you read page 1 and it is this paper; the reason goes into the output")
    p.add_argument("--dry-run", action="store_true",
                   help="run the pre-checks, the identity check included (unless the file is already attached); write nothing")
    p.add_argument("--key-file", default=DEFAULT_KEY_FILE, metavar="PATH",
                   help="JSON file holding the local API key (default: %(default)s); env ZOTERO_LOCAL_API_KEY overrides")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL, help="local API base URL (default: %(default)s)")
    args = p.parse_args()
    if args.key and args.cite:
        p.error("--key and --cite exclude each other")
    if args.accept is not None and not args.accept.strip():
        p.error("--accept needs the reason: what page 1 showed")
    if args.file_version is not None and not args.file_version.strip():
        p.error("--file-version needs a value")
    if args.key or args.cite or args.record:
        if args.records:
            p.error("--key / --cite / --record (single mode) and record paths (stream mode) exclude each other")
        if args.in_place:
            p.error("-i belongs to stream mode; --record writes its record back by itself")
        if args.record and args.accept is not None:
            p.error("--accept is for a file without a record; with --record, write pdf_accepted into the record")
        if not args.record and (not args.file or not args.url):
            p.error("single mode needs --key or --cite, --file and --url (or --record)")
    else:
        if args.filename:
            p.error("--filename belongs to single mode; stream mode names files from the parent item")
        if args.accept is not None:
            p.error("--accept belongs to single mode without a record; records carry pdf_accepted")
        if args.file_version is not None:
            p.error("--file-version belongs to single mode; records carry file_version")
        if not args.records and args.in_place:
            p.error("-i needs record paths: records from stdin have no file to write back to")
        if not args.records and sys.stdin.isatty():
            p.error("pass record files, pipe records to stdin, or use --key --file --url / --record for single mode")
    if args.accept is not None:
        args.accept = args.accept.strip()
    return args


def main():
    args = parse_args()
    api = Api(args.base_url)
    if args.cite:
        args.key = resolve_cite(api, args.cite)
    if args.key or args.record:
        run_single(api, args)
    else:
        run_stream(api, args)


if __name__ == "__main__":
    try:
        main()
    except Stop as stop:
        emit(stop.code, stop.exit_code, stop.hint, **stop.extra)
