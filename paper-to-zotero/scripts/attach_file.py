# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Attach a PDF file to an existing Zotero item through the local write API.

Works the same for a just-created item and for an old one. Flow: pre-checks
(file, item, existing children) -> create the child attachment, or reuse an
empty one left by an interrupted run -> 3-step upload -> read back the md5.

stdout: exactly one JSON object with a stable `code` (`ok` on success);
diagnostics go to stderr. Exit 0 = done, 1 = not done (the agent decides),
2 = cannot check (Zotero unreachable, local API disabled, no key, key
rejected, key belongs to another Zotero instance).
"""
import argparse
import hashlib
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
        raise Stop("key_rejected", 2, "The API key is not accepted by this Zotero; run authorize_local_api.py again.",
                   status=status, body=msg)
    if status == 412 and "server-id" in msg.lower():
        raise Stop("server_mismatch", 2, "The key belongs to another Zotero instance; run authorize_local_api.py again.",
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
        raise Stop("no_key", 2, "No local API key yet; run authorize_local_api.py first (or set ZOTERO_LOCAL_API_KEY).",
                   key_file=str(path))
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
        key = info["key"]
    except (ValueError, KeyError, TypeError) as e:
        raise Stop("no_key", 2, "The key file is unreadable; run authorize_local_api.py again.",
                   key_file=str(path), error=str(e))
    saved = info.get("serverID")
    if saved and saved != server_id:
        raise Stop("server_mismatch", 2, "The saved key was issued by another Zotero instance; run authorize_local_api.py again.",
                   key_file=str(path))
    return key


def write_headers(key, server_id):
    return {"Zotero-API-Key": key, "Zotero-Server-ID": server_id}


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


def parse_args():
    p = argparse.ArgumentParser(
        description="Attach a file — a PDF, or an HTML snapshot of the article page when no PDF can be had — "
                    "to an existing Zotero item via the local write API (3-step upload, md5 read back).",
        epilog="Exit 0 = done (code ok or already_attached); 1 = not done, see code/hint; 2 = cannot check "
               "(zotero_unreachable, local_api_disabled, no_key, key_rejected, server_mismatch). "
               "Output is one JSON object on stdout.")
    p.add_argument("--key", required=True, metavar="ITEMKEY", help="key of the parent item (8 characters)")
    p.add_argument("--file", "--pdf", dest="file", required=True, metavar="PATH",
                   help="the file to upload: a PDF, or an .html page saved from the browser (--pdf is an alias)")
    p.add_argument("--url", "--pdf-url", dest="url", required=True, metavar="URL",
                   help="canonical source URL stored on the attachment (fall back to https://doi.org/<DOI>); "
                        "EZproxy-style hosts are rejected")
    p.add_argument("--filename", metavar="NAME",
                   help="filename inside Zotero; default '<firstCreator> - <year> - <title>.<ext>' from the parent item")
    p.add_argument("--title", help="attachment title (default: PDF, or Snapshot for an HTML file)")
    p.add_argument("--dry-run", action="store_true", help="run the pre-checks only; write nothing")
    p.add_argument("--key-file", default=DEFAULT_KEY_FILE, metavar="PATH",
                   help="JSON file holding the local API key (default: %(default)s); env ZOTERO_LOCAL_API_KEY overrides")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL, help="local API base URL (default: %(default)s)")
    return p.parse_args()


def main():
    args = parse_args()
    pdf_url = args.url.strip()
    parsed_url = urllib.parse.urlparse(pdf_url)
    if not pdf_url or parsed_url.scheme not in ("http", "https") or not parsed_url.hostname:
        raise Stop("invalid_pdf_url", 1, "Pass the canonical source URL with --pdf-url; fall back to https://doi.org/<DOI>.",
                   pdf_url=pdf_url)
    host = parsed_url.hostname.lower()
    if ".idm.oclc.org" in host or "ezproxy" in host:
        raise Stop("proxied_url", 1, "That is a proxy hostname; store the canonical URL instead (publisher page or https://doi.org/<DOI>).",
                   pdf_url=pdf_url)

    pdf = Path(args.file).expanduser()
    if not pdf.is_file():
        raise Stop("file_not_found", 1, "Point --file at the downloaded file.", file=str(pdf))
    pdf_bytes = pdf.read_bytes()
    head = pdf_bytes[:2048].lstrip().lower()
    if pdf_bytes.startswith(b"%PDF-"):
        kind, content_type, ext = "pdf", "application/pdf", ".pdf"
    elif pdf.suffix.lower() in (".html", ".htm") and (head.startswith(b"<!doctype") or head.startswith(b"<html") or b"<html" in head):
        kind, content_type, ext = "html", "text/html", ".html"
    else:
        raise Stop("unsupported_file", 1, "Only a PDF (%PDF- header) or an HTML page saved as .html is accepted; "
                   "a \"PDF\" that is really HTML means the download returned a web page.",
                   file=str(pdf), size=len(pdf_bytes), head=pdf_bytes[:16].decode("latin-1"))
    title = args.title or ("PDF" if kind == "pdf" else "Snapshot")
    md5 = hashlib.md5(pdf_bytes).hexdigest()
    mtime = int(pdf.stat().st_mtime * 1000)

    api = Api(args.base_url)
    server_id = live_server_id(api)
    key = load_key(args.key_file, server_id)

    item = get_json(api, f"{LIB}/items/{args.key}",
                    ("item_not_found", "No item with that key; check the key from create_item.py / find_in_library.py.",
                     {"item_key": args.key}))
    data = item.get("data") or {}
    if data.get("itemType") in CHILD_TYPES or data.get("parentItem"):
        raise Stop("not_a_parent", 1, "Attachments hang off a regular item; pass the parent item's key.",
                   item_key=args.key, item_type=data.get("itemType"), parent_item=data.get("parentItem"))
    filename = clean_filename(args.filename) if args.filename else default_filename(data, ext)
    if not filename:
        raise Stop("invalid_filename", 1, "Pass a usable --filename.", filename=args.filename)

    children = get_json(api, f"{LIB}/items/{args.key}/children",
                        ("item_not_found", "No item with that key.", {"item_key": args.key}))
    reuse_key = None
    for child in children:
        cd = child.get("data") or {}
        if cd.get("itemType") != "attachment":
            continue
        if (cd.get("md5") or "").lower() == md5:
            emit("already_attached", 0, item_key=args.key, attachment_key=child["key"], md5_ok=True,
                 filename=cd.get("filename"), reused_attachment=False, md5=md5)
        if (reuse_key is None and cd.get("linkMode") in ("imported_url", "imported_file")
                and not cd.get("md5") and cd.get("filename") == filename):
            reuse_key = child["key"]
    if reuse_key:
        log(f"reusing empty attachment {reuse_key} (same filename, no file)")

    if args.dry_run:
        emit("ok", 0, dry_run=True, item_key=args.key, kind=kind, filename=filename, md5=md5, size=len(pdf_bytes),
             pdf_url=pdf_url, reused_attachment=bool(reuse_key), attachment_key=reuse_key,
             existing_attachments=sum(1 for c in children if (c.get("data") or {}).get("itemType") == "attachment"))

    wh = write_headers(key, server_id)
    if reuse_key:
        akey, reused = reuse_key, True
    else:
        attachment = {"itemType": "attachment", "linkMode": "imported_url", "parentItem": args.key,
                      "title": title, "contentType": content_type, "filename": filename, "url": pdf_url}
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
                   item_key=args.key, attachment_key=akey, md5_sent=md5, md5_read_back=read_md5 or None,
                   filename=(after.get("data") or {}).get("filename"))
    emit("ok", 0, item_key=args.key, attachment_key=akey, md5_ok=True, md5=md5,
         filename=(after.get("data") or {}).get("filename") or filename, reused_attachment=reused,
         file_existed=(outcome == "exists"))


if __name__ == "__main__":
    try:
        main()
    except Stop as stop:
        emit(stop.code, stop.exit_code, stop.hint, **stop.extra)
