"""Everything that talks to Zotero's local API: requests, pages, reads, citation keys, writes, attachments and files.

How a reply becomes a result code is decided here and nowhere else:
  no answer                        zotero_unreachable  (exit 2)
  403 whose body says "not enabled"  local_api_disabled  (exit 2)
  401                              key_rejected        (exit 2)
  412 whose body names the server id server_mismatch     (exit 2)
  any other 403 on a write         write_denied        (detail: Zotero's words)
  any other 412 on a PATCH         a version conflict: the item is read again and the write tried once more,
                                   then version_conflict
  anything else unexpected         write_failed on a write, unexpected_response on a read
The local API answers GETs without a key; writes carry the key ready.py --authorize stored and the server id.
"""
import hashlib
import json
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import config, paper
from .cli import CANNOT, Stop, log, skipped

DEFAULT_BASE_URL = "http://127.0.0.1:23119"
LIB = "/api/users/0"
PAGE = 100
CHUNK = 50
TIMEOUT = 120
FILENAME_ILLEGAL = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')
FILENAME_TITLE_MAX = 120
HTML_CHARSET = re.compile(rb"<meta[^>]*?charset\s*=\s*[\"']?\s*([a-z0-9_.:-]+)", re.I)

HINT_UNREACHABLE = ("Zotero does not answer: ask the user to start it (never restart it from here), then rerun; "
                    "check --base-url if it is not the default.")
HINT_DISABLED = ("Ask the user to enable the local API in Zotero Settings > Advanced ('Allow other applications on this "
                 "computer to communicate with Zotero'), then rerun.")
HINT_NOT_FOUND = "No item with that key; find it with read_library.py items --q, or by --cite."
HINT_CITE_NOT_FOUND = "No item carries this citationKey (case matters); find it with read_library.py items --q, or name it by its item key."
HINT_CITE_AMBIGUOUS = "Several items carry this citationKey; name the one you mean by its item key."
SUBTITLE_SEPARATORS = (": ", " - ", " – ", " — ")


def detail(body, limit=400):
    return body.decode("utf-8", errors="replace").strip()[:limit]


def data(row):
    return (row or {}).get("data") or {}


def is_top(row):
    return paper.is_top(data(row))


def chunks(seq, size=CHUNK):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def types_of(schema):
    """Each item type of a schema: {itemType: {order: [title, ... its fields in the schema's order], fields: the same
    as a set, base_of: {field: its base field, or itself}, by_base: {base field: the type's field for it},
    creator_types: [in the schema's order], primary: its primary creator type}}."""
    types = {}
    for t in schema.get("itemTypes") or []:
        rows, creators = t.get("fields") or [], t.get("creatorTypes") or []
        order = [f["field"] for f in rows]
        types[t["itemType"]] = {"order": order, "fields": set(order),
                                "base_of": {f["field"]: f.get("baseField") or f["field"] for f in rows},
                                "by_base": {f["baseField"]: f["field"] for f in rows if f.get("baseField")},
                                "creator_types": [c["creatorType"] for c in creators],
                                "primary": next((c["creatorType"] for c in creators if c.get("primary")), "author")}
    return types


def own_field(t, field):
    """A type's name for a field: the field itself, or the type's field for that base field (proceedingsTitle for
    publicationTitle in a conferencePaper); None when it has neither."""
    return field if field in t["fields"] else t["by_base"].get(field)


class _Stay(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Zotero:
    """A client for one Zotero instance; proxies from the environment are bypassed (the API listens on loopback)."""

    def __init__(self, base_url=DEFAULT_BASE_URL, timeout=TIMEOUT):
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.stay = urllib.request.build_opener(urllib.request.ProxyHandler({}), _Stay)
        self._server_id = self._key = self._schema = None

    # ---- requests -------------------------------------------------------------------------------------------

    def request(self, method, path, body=None, headers=None, *, params=None, timeout=None, follow=True):
        """-> (status, headers, body bytes). A dict or list body goes as JSON, a str as it is (a form), bytes raw."""
        url = self.base + path + ("?" + urllib.parse.urlencode(params) if params else "")
        h = {"Accept": "application/json", **(headers or {})}
        payload = None
        if isinstance(body, (bytes, bytearray)):
            payload = bytes(body)
        elif isinstance(body, str):
            payload = body.encode("utf-8")
        elif body is not None:
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
            h.setdefault("Content-Type", "application/json")
        req = urllib.request.Request(url, data=payload, method=method, headers=h)
        try:
            with (self.opener if follow else self.stay).open(req, timeout=timeout or self.timeout) as resp:
                return resp.status, resp.headers, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()
        except (urllib.error.URLError, OSError) as e:
            raise Stop("zotero_unreachable", exit=CANNOT, hint=HINT_UNREACHABLE, base_url=self.base,
                       detail=str(getattr(e, "reason", None) or e)) from None

    @staticmethod
    def check(status, body):
        """Raise for the replies that mean "cannot check", whichever call got them."""
        text = detail(body)
        low = text.lower()
        if status == 403 and "not enabled" in low:
            raise Stop("local_api_disabled", exit=CANNOT, hint=HINT_DISABLED, detail=text)
        if status == 401:
            raise Stop("key_rejected", exit=CANNOT, hint="Zotero does not accept the stored key; run ready.py --authorize again.",
                       detail=text)
        if status == 412 and "server-id" in low:
            raise Stop("server_mismatch", exit=CANNOT,
                       hint="The key belongs to another Zotero instance (or Zotero restarted); run ready.py --authorize again.",
                       detail=text)

    def _get(self, path, params=None, allow_404=False):
        status, headers, body = self.request("GET", path, params=params)
        self.check(status, body)
        if status == 404 and allow_404:
            return None, headers
        if status != 200:
            raise Stop("unexpected_response", hint="Unexpected reply from the local API; see status and detail.",
                       path=path, status=status, detail=detail(body))
        try:
            return json.loads(body), headers
        except ValueError:
            raise Stop("unexpected_response", hint="The local API did not answer with JSON.", path=path,
                       detail=detail(body)) from None

    def get(self, path, params=None, *, allow_404=False):
        return self._get(path, params, allow_404)[0]

    def pages(self, path, params=None, *, limit=None, until=None):
        """Every row of a paged listing (100 a page), up to `limit`, or until until(page) is true for a page read; a
        page that is not a list stops the read."""
        out, start = [], 0
        while limit is None or len(out) < limit:
            size = PAGE if limit is None else min(PAGE, limit - len(out))
            page, headers = self._get(path, {**(params or {}), "limit": size, "start": start})
            if not isinstance(page, list):
                raise Stop("unexpected_response", hint="The local API sent a page that is not a list; nothing past it was read.",
                           path=path, start=start)
            out.extend(page)
            start += len(page)
            if until and until(page):
                break
            total = headers.get("Total-Results")
            if len(page) < size or (total and total.isdigit() and start >= int(total)):
                break
        return out

    # ---- reads ----------------------------------------------------------------------------------------------

    def item(self, key):
        """The item, or None when there is none with that key."""
        row = self.get(f"{LIB}/items/{key}", allow_404=True)
        return row if isinstance(row, dict) and row.get("key") == key else None

    def items(self, keys, path=f"{LIB}/items", params=None):
        """{key: item} for those of `keys` the library has (50 a request; the listing also returns their children)."""
        found = {}
        for part in chunks(list(keys)):
            for row in self.pages(path, {**(params or {}), "itemKey": ",".join(part)}):
                if row.get("key") in part:
                    found[row["key"]] = row
        return found

    def children(self, key):
        """The item's attachments and notes. The local API answers a key it does not know with the whole library,
        so only rows whose parentItem is the key count."""
        return [c for c in self.pages(f"{LIB}/items/{key}/children") if data(c).get("parentItem") == key]

    def resolve_cites(self, cites):
        """{cite: [item keys]}: a q=everything search per citation key, then one scan of every top-level item for
        those the search missed."""
        hits = {}
        for cite in cites:
            rows = self.pages(f"{LIB}/items", {"q": cite, "qmode": "everything"}, limit=50)
            hits[cite] = [r["key"] for r in rows if is_top(r) and data(r).get("citationKey") == cite]
        missing = {c for c in cites if not hits[c]}
        if missing:
            log(f"no search hit for citationKey {', '.join(sorted(map(repr, missing)))}; scanning the top-level items")
            for row in self.pages(f"{LIB}/items/top"):
                cite = data(row).get("citationKey")
                if cite in missing:
                    hits[cite].append(row["key"])
        return hits

    @staticmethod
    def cite_failure(cite, keys):
        if not keys:
            return Stop("cite_not_found", hint=HINT_CITE_NOT_FOUND, cite=cite)
        return Stop("cite_ambiguous", hint=HINT_CITE_AMBIGUOUS, cite=cite, keys=keys)

    def resolve_cite(self, cite):
        keys = self.resolve_cites([cite])[cite]
        if len(keys) != 1:
            raise self.cite_failure(cite, keys)
        return keys[0]

    def targets(self, keys, cites):
        """[(key, cite, failure)] in the order given, keys first; an item named twice (a key and a cite) once."""
        hits = self.resolve_cites(cites) if cites else {}
        out, seen = [], set()
        for key, cite in [(k, None) for k in keys] + [(None, c) for c in cites]:
            if cite is not None:
                if len(hits[cite]) != 1:
                    out.append((None, cite, self.cite_failure(cite, hits[cite])))
                    continue
                key = hits[cite][0]
            if key in seen:
                log(f"{key} is named more than once; handled once")
                continue
            seen.add(key)
            out.append((key, cite, None))
        return out

    def collections(self):
        """{key: {key, name, parent, path, version, data}} for the live collections, parents first. A collection in
        the trash, and every collection under one, is left out; `path` joins the names from the root with "/"."""
        rows = {r["key"]: r for r in self.pages(f"{LIB}/collections") if not data(r).get("deleted")}
        tree = {}

        def place(key, depth=0):
            if key in tree:
                return tree[key]
            tree[key] = None  # a cycle or a dead parent leaves it out
            row = rows.get(key)
            if row is None or depth > 64:
                return None
            d = data(row)
            name, parent = d.get("name") or "", d.get("parentCollection") or None
            up = place(parent, depth + 1) if parent else None
            if parent and up is None:
                return None
            tree[key] = {"key": key, "name": name, "parent": parent, "path": f"{up['path']}/{name}" if up else name,
                         "version": row.get("version"), "data": d}
            return tree[key]

        for key in rows:
            place(key)
        live = [c for c in tree.values() if c]
        return {c["key"]: c for c in sorted(live, key=lambda c: c["path"].casefold())}

    def collection_scope(self, key, recursive=False, tree=None):
        """[key, and with recursive every live collection under it, parents first]; collection_not_found for a key
        that is not a live collection (missing, in the trash, or under one)."""
        tree = self.collections() if tree is None else tree
        if key not in tree:
            raise Stop("collection_not_found", hint="No live collection has this key (it may be in the trash); take it from "
                       "read_library.py collections --tree.", collection=key)
        keys = [key]
        for c in tree.values() if recursive else ():   # parents come first
            if c["parent"] in keys and c["key"] not in keys:
                keys.append(c["key"])
        return keys

    def schema(self, cache=None):
        """Zotero's schema (item types, fields, creator types, CSL mappings); with `cache`, a file that keeps it for
        the whole run (an import run's scratch/schema.json), read from Zotero only when the file is not there."""
        if self._schema is None and cache is not None:
            try:
                self._schema = json.loads(Path(cache).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
        if self._schema is None:
            self._schema = self.get("/api/schema")
            if cache is not None:
                from .run import atomic_write
                Path(cache).parent.mkdir(parents=True, exist_ok=True)
                atomic_write(cache, json.dumps(self._schema, ensure_ascii=False))
        return self._schema

    def item_types(self):
        return types_of(self.schema())

    # ---- is this paper in the library -----------------------------------------------------------------------

    def lookup(self, item, *, distinct_from=(), same_as=None):
        """Is the paper an item describes in the library? -> (found, near_matches), a record's two blocks without
        their `from`. Only an identifier confirms: the DOI, else the arXiv id — unless the item has a DOI of its own
        that the library lacks, which makes an arXiv hit its preprint: a near match. A title never confirms: the same
        title, or one inside the other, is a near match. Items in distinct_from are dropped at every step, and a step
        left empty goes on to the next; same_as names the item outright."""
        if same_as:
            row = self.item(same_as)
            if row is None:
                raise Stop("not_found", hint="same_as names no item of the library; correct it or remove it.", same_as=same_as)
            return {"code": "found", **self.describe(row), "matched_by": "same_as"}, []
        doi, aid = paper.identifiers(item)
        title, excluded, searched = (item.get("title") or "").strip(), set(distinct_from or ()), []
        rows = lambda q, qmode=None: [r for r in self._search(q, qmode, searched) if r["key"] not in excluded]
        matches, near, matched_by = [], [], None
        if doi:
            matches, matched_by = [r for r in rows(doi, "fields") if paper.same_paper(item, data(r)) == "doi"], "doi"
        if not matches and aid:
            hits = [r for r in rows(aid, "fields") if paper.same_paper(item, data(r)) == "arxiv"]
            if hits and doi:
                near = [(r, f"preprint/published pair: the library item matches by arXiv id only, and this item has "
                            f"its own DOI {doi}", "arxiv") for r in hits]
            else:
                matches, matched_by = hits, "arxiv"
        if not matches and not near and paper.norm_title(title):
            near = self._title_near(item, doi, rows)
        if matches:
            more = {"duplicates": [r["key"] for r in matches[1:]]} if len(matches) > 1 else {}
            return {"code": "found", **self.describe(matches[0]), "matched_by": matched_by, **more}, []
        return {"code": "not_found", "searched": searched}, [
            {"key": r["key"], "title": data(r).get("title"), "itemType": data(r).get("itemType"), "reason": why,
             **({"matched_by": by} if by else {})} for r, why, by in near]

    def _search(self, q, qmode, searched):
        """The top-level items a quick search hits; a hit on an attachment or note counts for its parent."""
        found, parents = {}, []
        for r in self.pages(f"{LIB}/items", {"q": q, **({"qmode": qmode} if qmode else {})}):
            if is_top(r):
                found.setdefault(r["key"], r)
            elif data(r).get("parentItem"):
                parents.append(data(r)["parentItem"])
        for key in parents:
            if key not in found:
                parent = self.item(key)
                if parent is not None and is_top(parent):
                    found[key] = parent
        searched.append({"q": q, "qmode": qmode or "titleCreatorYear", "hits": len(found)})
        return list(found.values())

    def _title_near(self, item, doi, rows):
        """[(row, reason, None)] for the library titles equal to the item's (first) or holding it or held by it."""
        title = item["title"].strip()
        found = {r["key"]: r for r in rows(title)}
        if not found:
            found = {r["key"]: r for r in rows(title, "everything")}
        head = next((title.split(sep, 1)[0].strip() for sep in SUBTITLE_SEPARATORS if sep in title), "")
        if head and len(head.split()) >= 2:
            found.update({r["key"]: r for r in rows(head) if r["key"] not in found})
        want, out = paper.norm_title(title), []
        for r in found.values():
            have, other = paper.norm_title(data(r).get("title")), paper.doi_of(data(r))
            if paper.same_paper(item, data(r)) == "title":
                out.append((0, r, f"same title, another DOI: the library item has {other}, this item {doi}"
                            if doi and other and other != doi else "same title; no identifier confirms it"))
            elif have and want in have:
                out.append((1, r, "the library title contains this title"))
            elif have and have in want:
                out.append((1, r, "this title contains the library title"))
        return [(r, why, None) for _, r, why in sorted(out, key=lambda e: e[0])]

    def describe(self, row):
        """What the library holds for an item: {key, version, citationKey, title, date, collections, tags, attachments}."""
        d = data(row)
        return {"key": row["key"], "version": row.get("version"), "citationKey": d.get("citationKey") or "",
                "title": d.get("title") or "", "date": d.get("date") or "", "collections": list(d.get("collections") or []),
                "tags": list(d.get("tags") or []),
                "attachments": [{k: a.get(k) for k in ("key", "title", "kind", "contentType", "linkMode", "filename", "md5")}
                                for a in self.attachments(row["key"])]}

    def files_by_md5(self, md5s):
        """{md5: {attachment, parent, citationKey, title}} for those of the md5s an attachment in the library holds
        (no search matches an md5: the attachments are read newest first, until each has its hit; the parent's
        citationKey and title come along). A publisher that stamps every download never gives two the same md5."""
        wanted, hits = {m.lower() for m in md5s if m}, {}

        def collect(page):
            for r in page:
                md5 = (data(r).get("md5") or "").lower()
                if md5 in wanted and md5 not in hits and not in_trash(r):
                    hits[md5] = r
            return not wanted - set(hits)

        if wanted:
            self.pages(f"{LIB}/items", {"itemType": "attachment", "sort": "dateAdded", "direction": "desc"}, until=collect)
        out = {}
        for md5, r in hits.items():
            parent = data(r).get("parentItem")
            pd = data(self.item(parent)) if parent else {}
            out[md5] = {"attachment": r["key"], "parent": parent, "citationKey": pd.get("citationKey") or None,
                        "title": pd.get("title") or None}
        return out

    # ---- attachments and files ------------------------------------------------------------------------------

    def file_path(self, attachment_key):
        """Where the attachment's file is on this machine (the local API redirects to its file:// address), or None."""
        status, headers, body = self.request("GET", f"{LIB}/items/{attachment_key}/file", follow=False)
        self.check(status, body)
        location = headers.get("Location") if 300 <= status < 400 else None
        return local_path(location) if location and location.startswith("file:") else None

    def attachments(self, key):
        """The item's attachments, the paper's PDFs first (published, accepted, preprint, then by date added):
        [{key, title, kind, contentType, linkMode, filename, md5, dateAdded}]; file_path() says where one is."""
        out = []
        for c in self.children(key):
            d = data(c)
            if d.get("itemType") != "attachment":
                continue
            entry = {"key": c["key"], "title": d.get("title"), "kind": paper.kind_of_attachment(d),
                     **{f: d.get(f) for f in ("contentType", "linkMode", "filename", "md5", "dateAdded")}}
            out.append(entry)
        return sorted(out, key=lambda a: (paper.kind_rank(a["kind"]), a.get("dateAdded") or ""))

    # ---- writes ---------------------------------------------------------------------------------------------

    def server_id(self):
        if self._server_id is None:
            status, headers, body = self.request("GET", "/api/")
            self.check(status, body)
            sid = headers.get("Zotero-Server-ID")
            if status != 200 or not sid:
                raise Stop("zotero_unreachable", exit=CANNOT,
                           hint="This endpoint does not answer like Zotero's local API (no Zotero-Server-ID); check --base-url.",
                           base_url=self.base, status=status, detail=detail(body))
            self._server_id = sid
        return self._server_id

    def write_headers(self, version=None):
        """The headers of a write; the first call checks the server id and the stored key (exit 2 when unusable)."""
        if self._key is None:
            self._key = config.zotero_key(self.server_id())
        h = {"Zotero-API-Key": self._key, "Zotero-Server-ID": self._server_id}
        if version is not None:
            h["If-Unmodified-Since-Version"] = str(version)
        return h

    def write_failure(self, status, body, **where):
        """The Stop for a write Zotero did not take: write_denied, write_failed (cannot-check replies raise)."""
        self.check(status, body)
        if status == 403:
            return Stop("write_denied", hint="Zotero refuses writes to this library; tell the user.", status=status,
                        detail=detail(body), **where)
        return Stop("write_failed", hint="The local API rejected the write; see status and detail.", status=status,
                    detail=detail(body), **where)

    def update(self, key, plan, item=None):
        """PATCH the item with what plan(item) returns (nothing when it returns None), sent with the item's version;
        on a version conflict the item is read again, planned again and the write tried once more.
        -> (the item as planned on, the body sent or None, retried)."""
        item = item or self.item(key)
        if item is None:
            raise Stop("not_found", hint=HINT_NOT_FOUND, key=key)
        retried = False
        for attempt in (1, 2):
            body = plan(item)
            if not body:
                return item, None, retried
            status, _, resp = self.request("PATCH", f"{LIB}/items/{key}", body, self.write_headers(item.get("version")))
            if status == 204:
                return item, body, retried
            self.check(status, resp)
            if status != 412:
                raise self.write_failure(status, resp, key=key)
            if attempt == 2:
                raise Stop("version_conflict", hint="The item keeps changing under us (Zotero sync, or the user editing it); "
                           "wait, then rerun.", key=key, status=status, detail=detail(resp))
            log(f"{key}: 412 ({detail(resp, 120)}); reading the item again and retrying once")
            retried = True
            item = self.item(key)
            if item is None:
                raise Stop("not_found", hint="The item disappeared while it was being written.", key=key)
        raise AssertionError("unreachable")

    def post(self, objects, path=f"{LIB}/items", replan=None):
        """POST objects, 50 a request -> one result per object, in order: {"ok": the object as Zotero now has it} |
        {"unchanged": True} | {"failed": {code, status, detail, hint}}. A request rejected as a whole fails its objects
        only; a cannot-check reply raises. An update with a stale version fails as version_conflict; given
        replan(index, item as it is now) -> the object again, or None when nothing is left to change, such objects are
        read again, planned again and posted once more (their results carry `retried`)."""
        objects = list(objects)
        results = self._post(objects, path)
        stale = [i for i, r in enumerate(results) if (r.get("failed") or {}).get("code") == "version_conflict"]
        if replan and stale:
            log(f"{len(stale)} object(s) changed meanwhile; reading them again and retrying once")
            fresh, again = self.items([objects[i]["key"] for i in stale]), []
            for i in stale:
                item = fresh.get(objects[i]["key"])
                obj = replan(i, item) if item else None
                if item is None:
                    results[i] = {"failed": {"code": "not_found", "detail": "the item disappeared while it was being written",
                                             "hint": HINT_NOT_FOUND}}
                elif not obj:
                    results[i] = {"unchanged": True, "retried": True}
                else:
                    again.append((i, obj))
            for (i, _), result in zip(again, self._post([obj for _, obj in again], path)):
                results[i] = {**result, "retried": True}
        return results

    def _post(self, objects, path):
        results = []
        for part in chunks(objects):
            status, _, body = self.request("POST", path, part, self.write_headers())
            if status != 200:
                failure = self.write_failure(status, body)
                results += [{"failed": {"code": failure.code, **failure.extra, "hint": failure.hint}} for _ in part]
                continue
            try:
                resp = json.loads(body)
                successful, unchanged, failed = (resp.get("successful") or {}, resp.get("unchanged") or {},
                                                 resp.get("failed") or {})
            except (ValueError, AttributeError):
                results += [{"failed": {"code": "unexpected_response", "detail": detail(body),
                                        "hint": "The local API did not answer with JSON."}} for _ in part]
                continue
            for i in range(len(part)):
                idx = str(i)
                if isinstance(successful.get(idx), dict):
                    results.append({"ok": successful[idx]})
                elif idx in unchanged:
                    results.append({"unchanged": True})
                elif (failed.get(idx) or {}).get("code") == 412:
                    results.append({"failed": {"code": "version_conflict", "status": 412, "detail": failed[idx].get("message"),
                                               "hint": "The item changed while it was being written; rerun."}})
                else:
                    f = failed.get(idx) or {}
                    results.append({"failed": {"code": "write_failed", "status": f.get("code"),
                                               "detail": f.get("message") or "no result for this object",
                                               "hint": "Zotero did not take this object; see status and detail."}})
        return results

    def trash(self, key, *, restore=False, item=None, dry_run=False):
        """Move the item to the trash (restore: out of it) and read it back -> {code ok | skipped, reason?, version,
        retried}; dry_run: what would happen, nothing written. Trashing a parent takes its attachments and notes along,
        as in Zotero; nothing here empties the trash."""
        want = not restore
        settled = "not_in_trash" if restore else "already_trashed"
        if dry_run:
            item = item or self.item(key)
            if item is None:
                raise Stop("not_found", hint=HINT_NOT_FOUND, key=key)
            if in_trash(item) == want:
                return skipped(settled, version=item.get("version"))
            return {"code": "ok", "version": item.get("version"), "dry_run": True}
        item, sent, retried = self.update(key, lambda it: None if in_trash(it) == want else {"deleted": 1 if want else 0},
                                          item)
        if sent is None:
            return skipped(settled, version=item.get("version"), retried=retried)
        after = self.item(key)
        if after is None or in_trash(after) != want:
            raise Stop("readback_mismatch", hint="The write was accepted, but the item does not show the new state; look at it in Zotero.",
                       retried=retried)
        return {"code": "ok", "version": after.get("version"), "retried": retried}

    def post_one(self, obj, path=f"{LIB}/items", hint="Zotero did not take the object; see detail."):
        """POST one object -> the object as Zotero now has it; its failure raised as a Stop (nothing was written)."""
        [result] = self.post([obj], path)
        if "failed" in result:
            failure = dict(result["failed"])
            failure.pop("hint", None)
            raise Stop(failure.pop("code"), hint=hint, **failure)
        return result.get("ok") or {"key": obj.get("key")}

    def create_collection(self, name, parent=None):
        """POST one collection -> its key."""
        return self.post_one({"name": name, "parentCollection": parent or False}, f"{LIB}/collections",
                             "Zotero did not create the collection; see detail.")["key"]

    # ---- attaching a file -----------------------------------------------------------------------------------

    def attach(self, parent_key, path, *, title=None, url, filename=None, kind=None, server=None, verify=None,
               dry_run=False):
        """Attach one file, a PDF or an HTML page saved as .html, to one regular item, whatever made the item.

        A child already holding this file (same md5) settles it: skipped, already_attached, nothing uploaded. An empty
        stored-file child with the same filename (left by an interrupted run) is reused. verify(parent data) runs only
        when the file is not attached yet; a Stop from it refuses. The kind is given, else read from the file name; the
        title is given, else the kind's (a preprint's names its server: given, else the url's, else arXiv); the filename is given, else Zotero's default "<firstCreator> - <year> -
        <title>.<ext>". `url` is stored as given (None: a stored file without a source). Then the attachment item, the
        three-step upload and the md5 read back. Children in the trash count for nothing.
        -> {code ok, attachment (its key), md5, filename, title, kind, reused, file_existed}
         | {code skipped, reason already_attached, attachment, md5, filename, title, kind}: the attachment already there
         | dry_run: {code ok, dry_run, attachment (the child it would reuse, else None), md5, filename, title, kind, reused,
                     contentType, url, size}."""
        path = Path(path).expanduser()
        if not path.is_file():
            raise Stop("file_not_found", hint="Point at the file to attach.", file=str(path))
        body = path.read_bytes()
        sniffed = file_type(body, path.name)
        if sniffed is None:
            raise Stop("unsupported_file", hint="Only a PDF (%PDF- header) or an HTML page saved as .html is attached; "
                       "a \"PDF\" that is really HTML means the download returned a web page.",
                       file=str(path), size=len(body), head=body[:16].decode("latin-1"))
        content_type, ext, charset = sniffed
        if kind is None:
            kind = paper.kind_of_file(path.name)
            if kind is None or (kind == "snapshot") != (content_type == "text/html"):
                kind = "snapshot" if content_type == "text/html" else "published"
        elif kind not in paper.KINDS:
            raise ValueError(f"unknown file kind {kind!r}; one of {', '.join(paper.KINDS)}")
        md5 = hashlib.md5(body).hexdigest()

        parent = self.item(parent_key)
        if parent is None:
            raise Stop("not_found", hint=HINT_NOT_FOUND, key=parent_key)
        pdata = data(parent)
        if not paper.is_top(pdata):
            raise Stop("not_a_parent", hint="Files hang off a regular item; pass the parent item's key.", key=parent_key,
                       itemType=pdata.get("itemType"), parentItem=pdata.get("parentItem"))
        filename = clean_filename(filename) if filename else default_filename(pdata, ext)
        if not filename:
            raise Stop("invalid_filename", hint="Pass a filename with usable characters.")

        reuse = None
        for child in self.children(parent_key):
            cd = data(child)
            if cd.get("itemType") != "attachment" or in_trash(child):
                continue
            if (cd.get("md5") or "").lower() == md5:
                return skipped("already_attached", attachment=child["key"], md5=md5, filename=cd.get("filename"),
                               title=cd.get("title"), kind=paper.kind_of_attachment(cd) or kind)
            if (reuse is None and cd.get("linkMode") in ("imported_url", "imported_file") and not cd.get("md5")
                    and cd.get("filename") == filename):
                reuse = child
        if verify is not None:
            verify(pdata)
        if title is None:
            title = paper.attachment_title(kind, server or paper.preprint_server(url) or "arXiv",
                                           parent_type=pdata.get("itemType"))
        if reuse is not None:
            title = data(reuse).get("title") or title
        if dry_run:
            return {"code": "ok", "dry_run": True, "attachment": reuse["key"] if reuse else None, "md5": md5, "filename": filename,
                    "title": title, "kind": kind, "reused": reuse is not None, "contentType": content_type, "url": url,
                    "size": len(body)}

        if reuse is not None:
            key = reuse["key"]
            log(f"{parent_key}: reusing the empty attachment {key} (same filename, no file)")
        else:
            attachment = {"itemType": "attachment", "linkMode": "imported_url" if url else "imported_file",
                          "parentItem": parent_key, "title": title, "contentType": content_type, "filename": filename,
                          **({"url": url} if url else {}), **({"charset": charset} if charset else {})}
            try:
                key = self.post_one(attachment, hint="Zotero did not create the attachment item; see detail.").get("key")
            except Stop as stop:
                stop.extra.setdefault("step", "create")
                raise
            if not key:
                raise Stop("unexpected_response", hint="Zotero's answer names no attachment item; look at the parent in Zotero.",
                           step="create")
            log(f"{parent_key}: created the attachment {key}")
        existed = self._upload(key, body, md5, filename, int(path.stat().st_mtime * 1000), content_type)
        after = data(self.item(key))
        read_back = (after.get("md5") or "").lower()
        if read_back != md5:
            raise Stop("readback_mismatch", hint="Zotero holds another file (or none) on the attachment; rerun to upload "
                       "again, or look at it in Zotero.", attachment=key, md5_sent=md5, md5_read_back=read_back or None)
        return {"code": "ok", "attachment": key, "md5": md5, "filename": after.get("filename") or filename,
                "title": after.get("title") or title, "kind": kind, "reused": reuse is not None, "file_existed": existed}

    def _upload(self, key, body, md5, filename, mtime, content_type):
        """Authorize, send the bytes, register -> True when Zotero already had this file (nothing sent)."""
        headers = {**self.write_headers(), "Content-Type": "application/x-www-form-urlencoded", "If-None-Match": "*"}
        # quote, not quote_plus: Zotero's form parser does not turn '+' back into a space.
        form = urllib.parse.urlencode({"md5": md5, "filename": filename, "filesize": len(body), "mtime": mtime},
                                      quote_via=urllib.parse.quote)
        status, _, resp = self.request("POST", f"{LIB}/items/{key}/file", form, headers)
        if status != 200:
            raise self._step_failure("authorize", status, resp, key)
        try:
            auth = json.loads(resp)
            if auth.get("exists"):
                log(f"{key}: Zotero already has this file")
                return True
            target, upload_key = urllib.parse.urlsplit(auth["url"]), auth["uploadKey"]
        except (ValueError, AttributeError, KeyError, TypeError):
            raise Stop("unexpected_response", hint="Zotero's answer to the upload request is not the one expected.",
                       step="authorize", attachment=key, detail=detail(resp)) from None
        # The url names Zotero's own address; its path goes to the address this client reaches Zotero at.
        status, _, resp = self.request("POST", target.path + (f"?{target.query}" if target.query else ""), body,
                                       {"Content-Type": content_type})
        if status != 201:
            raise self._step_failure("transfer", status, resp, key)
        status, _, resp = self.request("POST", f"{LIB}/items/{key}/file",
                                       urllib.parse.urlencode({"upload": upload_key}, quote_via=urllib.parse.quote), headers)
        if status != 204:
            raise self._step_failure("register", status, resp, key)
        return False

    def _step_failure(self, step, status, body, key):
        failure = self.write_failure(status, body, step=step, attachment=key)
        if failure.code == "write_denied":
            failure.hint = ("Zotero refuses file writes in this library; the attachment item exists without a file (a "
                            "rerun reuses it). Tell the user.")
        elif status == 412:
            failure.hint = "The attachment already records a file; look at it in Zotero before rerunning."
        else:
            failure.hint = "Fix the cause, then rerun: the attachment item is reused, not created again."
        return failure


def in_trash(item):
    # The local API sends `deleted: true` on a trashed item; after a restore the property may be absent.
    return bool(data(item).get("deleted"))


def local_path(url):
    """A file:// address as a path this machine opens: a Windows path (Zotero on Windows) through wslpath in WSL."""
    path = urllib.parse.unquote(urllib.parse.urlsplit(url).path)
    if not re.match(r"/[A-Za-z]:/", path):
        return path
    win = path[1:]
    if shutil.which("wslpath"):
        done = subprocess.run(["wslpath", "-u", win], capture_output=True, text=True)
        if done.returncode == 0 and done.stdout.strip():
            return done.stdout.strip()
    return win


# ---- files to attach ------------------------------------------------------------------------------------------

def file_type(body, name):
    """(content type, extension, charset) of a file attach takes: a PDF, or an HTML page saved as .html (charset:
    utf-8 under a BOM, else its <meta>'s, else utf-8), as paper.file_format reads them; None for anything else."""
    fmt = paper.file_format(body, name)
    if fmt == "pdf":
        return "application/pdf", ".pdf", None
    if fmt != "html" or not name.lower().endswith((".html", ".htm")):
        return None
    bom = body.startswith(b"\xef\xbb\xbf")
    head = body[3 if bom else 0:4096].lstrip().lower()
    m = None if bom else HTML_CHARSET.search(head)
    return "text/html", ".html", m.group(1).decode("ascii") if m else "utf-8"


def clean_filename(name):
    """Characters common filesystems refuse become spaces; runs of whitespace one space."""
    return re.sub(r"\s+", " ", FILENAME_ILLEGAL.sub(" ", name)).strip()


def first_creator(creators):
    """Zotero's firstCreator: authors first, else editors, else contributors, else anyone."""
    names = []
    for ctype in ("author", "editor", "contributor", None):
        chosen = [c for c in creators if isinstance(c, dict) and (ctype is None or c.get("creatorType") == ctype)]
        names = [n for n in ((c.get("lastName") or c.get("name") or "").strip() for c in chosen) if n]
        if names:
            break
    if len(names) > 2:
        return f"{names[0]} et al."
    return " and ".join(names)


def default_filename(data, ext=".pdf"):
    """Zotero's default pattern: "<firstCreator> - <year> - <title>" and the extension."""
    year = re.search(r"\d{4}", data.get("date") or "")
    parts = [clean_filename(first_creator(data.get("creators") or [])), year.group() if year else "",
             clean_filename(data.get("title") or "")[:FILENAME_TITLE_MAX].rstrip()]
    return (" - ".join(p for p in parts if p) or "attachment") + ext
