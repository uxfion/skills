"""A fake of Zotero's local API for the tests: one in-memory library served over real HTTP on a free port.

    zot = FakeZotero()                  # serving at zot.base_url until zot.close()
    zot.reset()                         # an empty library and default hooks (call it in setUp)
    key = zot.add_item("PAPER001", itemType="journalArticle", title="...", citationKey="smith2024")
    zot.add_collection("COLL0001", "tmp")

What the real local API does that the fake keeps: GETs need no key; writes need Zotero-API-Key and
Zotero-Server-ID (401, then 412 "Zotero-Server-ID mismatch"); listings page with `start`/`limit` (25 by default,
at most 100) and send Total-Results and a rel="next" Link; `/items/<unknown>/children` answers with the whole
library; `itemKey` also returns the children of the keys asked for; trashed items are left out of listings; an
attachment's /file redirects to its file:// address; a PATCH or a POSTed update with a stale version fails with 412.

A file reaches a stored-file attachment (imported_url / imported_file) in three steps; the first and the last are
writes (key, server id and write_status apply), the transfer needs no key:
  authorize  POST /items/<key>/file, form md5, filename, filesize, mtime, with If-None-Match: * (else 428) ->
             {url, contentType, prefix, suffix, uploadKey}; {"exists": 1} when the attachment holds that md5
             already; 412 when it holds another file
  transfer   POST the bytes to that url (/api/local/uploads/<uploadKey>) -> 201
  register   POST /items/<key>/file, form upload=<uploadKey> -> 204 (400 when the bytes do not match the md5);
             the attachment then carries md5, filename and mtime, and its /file redirects to a stored copy
The form is read as Zotero reads it: %XX decoded, '+' left as it is.

Search (`q`): titleCreatorYear (the default) looks at title, creator names and the year; `fields` and `everything`
at every string field (`citationKey` only while `search_sees_citekey`).

Hooks, all reset by reset():
  disabled               every request answers 403 "Local API is not enabled"
  search_sees_citekey    q matches citationKey (False: only the fallback scan finds it)
  bump_before_write      this many writes find the item one version newer (a concurrent edit), each running
                         `concurrent_edit(item)` when set
  ignore_writes          writes are acknowledged but change nothing
  write_status           (status, body) answered to every write
  reject(obj)            -> (code, message) to fail one POSTed object, or None
  thin_post_reply        successful POST entries carry only key and version
  on_write(item)         runs on an item after Zotero applied a write (to emulate Zotero's normalizations)
  file_step_status       {step: (status, body)}: what that upload step ("authorize", "transfer", "register")
                         answers instead (a dict body goes as JSON: (200, {"exists": 1}) works too)
  file_md5               the md5 the register step records instead of the uploaded file's (another file stored)
The authorize step counts for bump_before_write / concurrent_edit, and the register step for ignore_writes.

`requests` logs (method, path, query dict, body) for every request; `uploads` holds {uploadKey: bytes} received by
the transfer step.
"""
import hashlib
import json
import shutil
import tempfile
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

API_KEY = "fake-key-never-printed"
SERVER_ID = "FAKESRV1"
LIB = "/api/users/0"
CHILD_TYPES = ("attachment", "note", "annotation")
UPLOADS = "/api/local/uploads/"

SCHEMA = {"version": 44, "itemTypes": [
    {"itemType": "journalArticle", "fields": [{"field": "title"}, {"field": "abstractNote"}, {"field": "publicationTitle"},
                                              {"field": "journalAbbreviation"}, {"field": "volume"}, {"field": "pages"},
                                              {"field": "date"}, {"field": "DOI"}, {"field": "url"}, {"field": "extra"},
                                              {"field": "PMID"}, {"field": "citationKey"}],
     "creatorTypes": [{"creatorType": "author", "primary": True}, {"creatorType": "editor"}]},
    {"itemType": "conferencePaper", "fields": [{"field": "title"}, {"field": "abstractNote"},
                                               {"field": "proceedingsTitle", "baseField": "publicationTitle"},
                                               {"field": "conferenceName"}, {"field": "pages"}, {"field": "date"},
                                               {"field": "DOI"}, {"field": "url"}, {"field": "extra"},
                                               {"field": "citationKey"}],
     "creatorTypes": [{"creatorType": "author", "primary": True}, {"creatorType": "editor"}]},
    {"itemType": "preprint", "fields": [{"field": "title"}, {"field": "abstractNote"},
                                        {"field": "repository", "baseField": "publisher"}, {"field": "archiveID", "baseField": "number"},
                                        {"field": "date"}, {"field": "DOI"}, {"field": "url"}, {"field": "extra"},
                                        {"field": "citationKey"}],
     "creatorTypes": [{"creatorType": "author", "primary": True}]},
    {"itemType": "webpage", "fields": [{"field": "title"}, {"field": "url"}, {"field": "date"}, {"field": "extra"}],
     "creatorTypes": [{"creatorType": "author", "primary": True}]},
    {"itemType": "attachment", "fields": [{"field": "title"}, {"field": "url"}], "creatorTypes": []},
    {"itemType": "note", "fields": [], "creatorTypes": []},
]}


class FakeZotero:
    def __init__(self):
        self.storage = None  # the directory of stored files, made on the first upload
        self.reset()
        fake = self

        class Handler(_Handler):
            zot = fake

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        if self.storage:
            shutil.rmtree(self.storage, ignore_errors=True)

    def reset(self):
        self.lock = threading.RLock()
        self.items, self.collections, self.files, self.tag_meta = {}, {}, {}, None
        self.schema = json.loads(json.dumps(SCHEMA))
        self.version = 100
        self.requests = []
        self.counter = 0
        self.disabled = False
        self.search_sees_citekey = True
        self.bump_before_write = 0
        self.concurrent_edit = None
        self.ignore_writes = False
        self.write_status = None
        self.reject = None
        self.thin_post_reply = False
        self.on_write = None
        self.file_step_status = {}
        self.file_md5 = None
        self.uploads, self.pending_uploads, self.upload_counter = {}, {}, 0

    # ---- building the library ---------------------------------------------------------------------------------

    def next_version(self):
        self.version += 1
        return self.version

    def new_key(self):
        self.counter += 1
        return f"NEW{self.counter:05d}"

    def add_item(self, key=None, *, version=None, meta=None, **data):
        key = key or self.new_key()
        version = version or self.next_version()
        data.setdefault("tags", [])
        if data.get("itemType") not in CHILD_TYPES:
            data.setdefault("collections", [])
        self.items[key] = {"key": key, "version": version, "meta": meta or {}, "data": {"key": key, "version": version, **data}}
        return key

    def add_collection(self, key, name, parent=None, *, deleted=False, version=None):
        version = version or self.next_version()
        data = {"key": key, "version": version, "name": name, "parentCollection": parent or False}
        if deleted:
            data["deleted"] = True
        self.collections[key] = {"key": key, "version": version, "data": data}
        return key

    def data(self, key):
        return self.items[key]["data"]

    def requested(self, method=None, path=None):
        """The logged requests, filtered by method and path (a prefix ending in * matches every path below it)."""
        out = []
        for m, p, q, body in self.requests:
            if method and m != method:
                continue
            if path and not (p.startswith(path[:-1]) if path.endswith("*") else p == path):
                continue
            out.append((m, p, q, body))
        return out

    def writes(self):
        return [r for r in self.requests if r[0] in ("POST", "PATCH", "PUT", "DELETE")]

    # ---- reading ------------------------------------------------------------------------------------------------

    def visible(self, include_trashed=False):
        return [it for it in self.items.values() if include_trashed or not it["data"].get("deleted")]

    def matches(self, it, q, mode):
        d = it["data"]
        if mode == "titleCreatorYear":
            hay = [d.get("title") or "", (d.get("date") or "")[:4]]
            hay += [f"{c.get('firstName', '')} {c.get('lastName', '')} {c.get('name', '')}" for c in d.get("creators") or []]
        else:
            hay = [v for k, v in d.items() if isinstance(v, str) and (k != "citationKey" or self.search_sees_citekey)]
            hay += [t.get("tag", "") for t in d.get("tags") or []]
        return any(q.casefold() in h.casefold() for h in hay)

    def listing(self, path, query):
        """Rows for an items listing path, before paging; None when the path is not one."""
        parts = path[len(LIB):].strip("/").split("/")
        top = parts[-1] == "top"
        if top:
            parts = parts[:-1]
        if parts == ["items"]:
            rows = self.visible(query.get("includeTrashed") == "1")
        elif len(parts) == 3 and parts[0] == "collections" and parts[2] == "items":
            rows = [it for it in self.visible() if parts[1] in (it["data"].get("collections") or [])]
        else:
            return None
        if "itemKey" in query:
            wanted = query["itemKey"].split(",")
            rows = [it for it in self.visible(True) if it["key"] in wanted or (not top and it["data"].get("parentItem") in wanted)]
        if top:  # top-level: no parent, so standalone notes and attachments too
            rows = [it for it in rows if not it["data"].get("parentItem")]
        if "itemType" in query:
            rows = [it for it in rows if it["data"].get("itemType") == query["itemType"]]
        if "since" in query:
            rows = [it for it in rows if it["version"] > int(query["since"])]
        if "tag" in query:
            wanted = [t.strip() for t in query["tag"].split("||")]
            rows = [it for it in rows if any(t.get("tag") in wanted for t in it["data"].get("tags") or [])]
        if "q" in query:
            rows = [it for it in rows if self.matches(it, query["q"], query.get("qmode", "titleCreatorYear"))]
        if query.get("sort") == "dateAdded":
            rows = sorted(rows, key=lambda it: it["data"].get("dateAdded") or "", reverse=query.get("direction") == "desc")
        return rows

    def tag_rows(self):
        if self.tag_meta is not None:
            return self.tag_meta
        counts = {}
        for it in self.visible():
            for t in it["data"].get("tags") or []:
                key = (t.get("tag"), t.get("type", 0))
                counts[key] = counts.get(key, 0) + 1
        return [{"tag": tag, "meta": {"type": kind, "numItems": n}} for (tag, kind), n in sorted(counts.items())]

    # ---- writing ------------------------------------------------------------------------------------------------

    def concurrent(self, it):
        if self.bump_before_write:
            self.bump_before_write -= 1
            if self.concurrent_edit:
                self.concurrent_edit(it)
            self.touch(it)

    def touch(self, it):
        it["version"] = self.next_version()
        it["data"]["version"] = it["version"]

    def apply(self, it, fields):
        if self.ignore_writes:
            return
        for k, v in fields.items():
            if k in ("key", "version"):
                continue
            if k == "deleted":
                if v:
                    it["data"]["deleted"] = True
                else:
                    it["data"].pop("deleted", None)
            else:
                it["data"][k] = v
        if self.on_write:
            self.on_write(it)
        self.touch(it)

    def create(self, obj, collection=False):
        key = self.new_key()
        if collection:
            self.add_collection(key, obj.get("name"), obj.get("parentCollection") or None)
            row = self.collections[key]
        else:
            fields = {k: v for k, v in obj.items() if k not in ("key", "version")}
            self.add_item(key, **fields)
            row = self.items[key]
            if self.on_write:
                self.on_write(row)
        return row

    def store_file(self, key, filename, content):
        """Keep an uploaded file as Zotero does, at <storage>/<attachment key>/<filename>; returns its path."""
        if self.storage is None:
            self.storage = tempfile.mkdtemp(prefix="fake-zotero-storage-")
        path = Path(self.storage) / key / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path


class _Handler(BaseHTTPRequestHandler):
    zot: FakeZotero
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def send(self, status, body=None, headers=None):
        if body is None:
            payload, ctype = b"", "application/json"
        elif isinstance(body, bytes):
            payload, ctype = body, "text/plain"
        elif isinstance(body, str):
            payload, ctype = body.encode(), "text/plain"
        else:
            payload, ctype = json.dumps(body).encode(), "application/json"
        self.send_response(status)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Last-Modified-Version", str(self.zot.version))
        self.end_headers()
        self.wfile.write(payload)

    def parse(self):
        url = urllib.parse.urlsplit(self.path)
        query = {k: v[0] for k, v in urllib.parse.parse_qs(url.query, keep_blank_values=True).items()}
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        self.zot.requests.append((self.command, url.path, query, raw))
        return url.path, query, raw

    def page(self, rows, query):
        start, limit = int(query.get("start", 0)), min(int(query.get("limit", 25)), 100)
        headers = {"Total-Results": str(len(rows))}
        if start + limit < len(rows):
            path = urllib.parse.urlsplit(self.path).path
            headers["Link"] = f'<{path}?{urllib.parse.urlencode({**query, "start": start + limit})}>; rel="next"'
        return self.send(200, rows[start:start + limit], headers)

    # ---- GET ----------------------------------------------------------------------------------------------------

    def do_GET(self):
        z = self.zot
        path, query, _ = self.parse()
        if z.disabled:
            return self.send(403, "Local API is not enabled")
        with z.lock:
            if path == "/api/":
                return self.send(200, "Nothing to see here.", {"Zotero-Server-ID": SERVER_ID})
            if path == "/api/schema":
                return self.send(200, z.schema)
            if path == f"{LIB}/tags":
                return self.page(z.tag_rows(), query)
            if path == f"{LIB}/collections":
                return self.page(list(z.collections.values()), query)
            if path.startswith(f"{LIB}/collections/") and path.count("/") == 5:
                c = z.collections.get(path.rsplit("/", 1)[1])
                return self.send(200, c) if c else self.send(404, "Not found")
            rows = z.listing(path, query)
            if rows is not None:
                if query.get("format") == "bibtex":
                    start, limit = int(query.get("start", 0)), min(int(query.get("limit", 25)), 100)
                    return self.send(200, "\n".join(bibtex(it) for it in rows[start:start + limit]))
                return self.page(rows, query)
            parts = path[len(LIB):].strip("/").split("/")
            if len(parts) >= 2 and parts[0] == "items":
                key = parts[1]
                if len(parts) == 2:
                    it = z.items.get(key)
                    return self.send(200, it) if it else self.send(404, "Not found")
                if parts[2:] == ["children"]:
                    rows = ([it for it in z.items.values() if it["data"].get("parentItem") == key]
                            if key in z.items else list(z.items.values()))
                    return self.page(rows, query)
                if parts[2:] == ["file"]:
                    if key in z.files:
                        return self.send(302, None, {"Location": "file://" + urllib.parse.quote(str(z.files[key]))})
                    return self.send(404, "Not found")
            return self.send(404, "Not found")

    # ---- writes -------------------------------------------------------------------------------------------------

    def authorized(self):
        if self.zot.disabled:
            self.send(403, "Local API is not enabled")
            return False
        if self.headers.get("Zotero-API-Key") != API_KEY:
            self.send(401, "Invalid key")
            return False
        if self.headers.get("Zotero-Server-ID") != SERVER_ID:
            self.send(412, "Zotero-Server-ID mismatch")
            return False
        if self.zot.write_status:
            self.send(*self.zot.write_status)
            return False
        return True

    def do_PATCH(self):
        z = self.zot
        path, _, raw = self.parse()
        if not self.authorized():
            return
        with z.lock:
            key = path.rsplit("/", 1)[1]
            it = z.items.get(key)
            if it is None:
                return self.send(404, "Not found")
            z.concurrent(it)
            if self.headers.get("If-Unmodified-Since-Version") != str(it["version"]):
                return self.send(412, "Item has been modified since specified version")
            z.apply(it, json.loads(raw))
            return self.send(204)

    def do_POST(self):
        z = self.zot
        path, _, raw = self.parse()
        if path.startswith(UPLOADS):
            return self.transfer(path[len(UPLOADS):], raw)
        if not self.authorized():
            return
        with z.lock:
            parts = path[len(LIB):].strip("/").split("/")
            if path.startswith(LIB + "/") and len(parts) == 3 and parts[0] == "items" and parts[2] == "file":
                return self.file_step(parts[1], form_fields(raw))
            if path not in (f"{LIB}/items", f"{LIB}/collections"):
                return self.send(404, "Not found")
            collection = path.endswith("/collections")
            objects = json.loads(raw)
            successful, success, unchanged, failed = {}, {}, {}, {}
            for i, obj in enumerate(objects):
                idx = str(i)
                rejected = z.reject(obj) if z.reject else None
                if rejected:
                    failed[idx] = {"key": obj.get("key"), "code": rejected[0], "message": rejected[1]}
                    continue
                if not collection and obj.get("key"):
                    it = z.items.get(obj["key"])
                    if it is None:
                        failed[idx] = {"key": obj["key"], "code": 404, "message": "Item not found"}
                        continue
                    z.concurrent(it)
                    if "version" in obj and obj["version"] != it["version"]:
                        failed[idx] = {"key": obj["key"], "code": 412, "message": "Item has been modified since specified version"}
                        continue
                    changes = {k: v for k, v in obj.items() if k not in ("key", "version") and it["data"].get(k) != v}
                    if not changes:
                        unchanged[idx] = obj["key"]
                        continue
                    z.apply(it, changes)
                    row = it
                else:
                    row = z.create(obj, collection)
                success[idx] = row["key"]
                successful[idx] = ({"key": row["key"], "version": row["version"]} if z.thin_post_reply
                                   else json.loads(json.dumps(row)))
            return self.send(200, {"successful": successful, "success": success, "unchanged": unchanged, "failed": failed})

    # ---- file uploads -------------------------------------------------------------------------------------------

    def file_step(self, key, form):
        """The authorize and register steps of an upload (POST /items/<key>/file)."""
        z = self.zot
        it = z.items.get(key)
        if it is None:
            return self.send(404, "Not found")
        d = it["data"]
        if d.get("itemType") != "attachment" or d.get("linkMode") not in ("imported_url", "imported_file"):
            return self.send(400, "Item is not a stored-file attachment")
        step = "register" if "upload" in form else "authorize"
        if step in z.file_step_status:
            return self.send(*z.file_step_status[step])
        if step == "register":
            pending = z.pending_uploads.get(form["upload"])
            if pending is None or pending["key"] != key:
                return self.send(400, "Upload key not found")
            received = z.uploads.get(form["upload"])
            if received is None or hashlib.md5(received).hexdigest() != pending["md5"]:
                return self.send(400, "Uploaded file does not match the md5")
            del z.pending_uploads[form["upload"]]
            if not z.ignore_writes:
                z.files[key] = z.store_file(key, pending["filename"], received)
                d.update(md5=z.file_md5 or pending["md5"], filename=pending["filename"], mtime=pending["mtime"])
                z.touch(it)
            return self.send(204)
        if self.headers.get("If-None-Match") != "*" and not self.headers.get("If-Match"):
            return self.send(428, "If-Match or If-None-Match header not provided")
        missing = [f for f in ("md5", "filename", "filesize", "mtime") if not form.get(f)]
        if missing:
            return self.send(400, f"{', '.join(missing)} not provided")
        z.concurrent(it)
        if d.get("md5") == form["md5"]:
            return self.send(200, {"exists": 1})
        if d.get("md5") and self.headers.get("If-None-Match") == "*":
            return self.send(412, "If-None-Match: * set but file exists")
        z.upload_counter += 1
        upload_key = f"UPLOAD{z.upload_counter:04d}"
        z.pending_uploads[upload_key] = {"key": key, "md5": form["md5"], "filename": form["filename"],
                                         "mtime": int(form["mtime"])}
        return self.send(200, {"url": f"{z.base_url}{UPLOADS}{upload_key}", "contentType": d.get("contentType") or
                               "application/octet-stream", "prefix": "", "suffix": "", "uploadKey": upload_key})

    def transfer(self, upload_key, raw):
        """The transfer step: the bytes of an authorized upload."""
        z = self.zot
        if z.disabled:
            return self.send(403, "Local API is not enabled")
        with z.lock:
            if "transfer" in z.file_step_status:
                return self.send(*z.file_step_status["transfer"])
            if upload_key not in z.pending_uploads:
                return self.send(404, "Not found")
            z.uploads[upload_key] = raw
            return self.send(201)


def form_fields(raw):
    """A urlencoded form as Zotero's parser reads it: %XX decoded, '+' left as it is."""
    out = {}
    for part in raw.decode("utf-8", errors="replace").split("&"):
        if part:
            name, _, value = part.partition("=")
            out[urllib.parse.unquote(name)] = urllib.parse.unquote(value)
    return out


def bibtex(it):
    d = it["data"]
    kind = {"journalArticle": "article", "conferencePaper": "inproceedings"}.get(d.get("itemType"), "misc")
    return f"@{kind}{{{d.get('citationKey') or it['key']},\n\ttitle = {{{d.get('title', '')}}},\n}}\n"
