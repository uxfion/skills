# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Resolve DOIs or arXiv ids into Zotero item drafts, one record per identifier.

Fetches the CSL JSON record from doi.org (content negotiation) and maps it
onto a Zotero item using the live Zotero schema (GET /api/schema: csl.types,
csl.fields, csl.names) plus a small built-in table for Crossref's own type
vocabulary.

Single mode (v1): `--doi ID --out item.json` writes the draft and prints one
report object. Stream mode: identifiers from repeated --doi, an --ids list
(`identifier[<TAB>citation key]` per line), a --bib file, existing record
files (their `item` is filled) or stdin (either identifier lines or records
as JSONL / an array / one object) each become a record {slug, id,
citationKey?, item}. --out-dir writes DIR/<slug>.json and prints one summary
line per record (a record already there for the same identifier is skipped,
never overwritten); -i writes record files back in place; otherwise the
full records go to stdout as JSONL and the summary to stderr. A failed
identifier yields a record with slug, id and `code` and does not stop the
others. Exit 0 = every record ok or skipped, 1 = some failed, 2 = Zotero
unreachable / local API disabled.

Only GET requests. doi.org goes through the normal proxy settings (env
DOI_BASE_URL overrides the host, for tests); the Zotero local API bypasses
the proxy. Tags are never written (Crossref `subject` is a journal category,
not author keywords).
"""

import argparse
import html
import json
import os
import re
import sys
import tempfile
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_BASE_URL = "http://127.0.0.1:23119"
DOI_BASE_URL = os.environ.get("DOI_BASE_URL", "https://doi.org").rstrip("/")
CSL_ACCEPT = "application/vnd.citationstyles.csl+json"
USER_AGENT = "paper-to-zotero/doi_to_item (stdlib urllib)"

# Crossref type vocabulary -> Zotero itemType (Crossref does not use CSL types).
CROSSREF_TYPES = {
    "journal-article": "journalArticle",
    "proceedings-article": "conferencePaper",
    "book-chapter": "bookSection",
    "book-part": "bookSection",
    "book-section": "bookSection",
    "posted-content": "preprint",
    "book": "book",
    "monograph": "book",
    "edited-book": "book",
    "reference-book": "book",
    "dataset": "dataset",
    "report": "report",
    "report-component": "report",
    "dissertation": "thesis",
    "reference-entry": "encyclopediaArticle",
    "standard": "standard",
}
# Crossref-only keys that Zotero would also read; CSL proper uses `event-title`.
EVENT_KEYS = ("event-title", "event")
DATE_FALLBACKS = ("published", "published-online", "published-print", "created")

EPILOG = """\
codes (stdout `code`, exit status):
  ok                   0  draft written
  unknown_type         1  CSL/Crossref type not in the map; draft written as journalArticle
  not_found            1  doi.org returned 404
  no_csl_record        1  doi.org answered but not with CSL JSON (HTML page, 406, bad JSON)
  invalid_identifier   1  input is neither a DOI nor an arXiv id
  doi_org_unreachable  2  network error, timeout or 5xx from doi.org
  zotero_unreachable   2  Zotero local API not answering (Zotero not running?)
  local_api_disabled   2  Zotero answered 403: local API is switched off
  no_identifier        1  (stream) a --bib entry without DOI / arXiv id; id = its title
  no_records           1  (stream) nothing to do
  skipped              -  (stream summary) reason exists | has_item | duplicate

input forms accepted by --doi:
  10.1109/CVPR.2016.90   doi:10.1109/CVPR.2016.90   https://doi.org/10.1109/CVPR.2016.90
  2006.11239   2006.11239v2   arXiv:2006.11239   https://arxiv.org/abs/2006.11239
"""


class Failure(Exception):
    def __init__(self, code, exit_code, hint=None, **extra):
        super().__init__(code)
        self.code, self.exit_code, self.hint, self.extra = code, exit_code, hint, extra


def log(msg):
    print(msg, file=sys.stderr)


def emit(code, exit_code, hint=None, **fields):
    out = {"code": code, **fields}
    if hint and code != "ok":
        out["hint"] = hint
    print(json.dumps(out, ensure_ascii=False, indent=2))
    sys.exit(exit_code)


# ---------------------------------------------------------------- identifier

ARXIV_ID = r"(?:\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})"


def parse_identifier(raw):
    """Return (doi, arxiv_id, arxiv_version) from a DOI / DOI URL / arXiv id / arXiv URL."""
    s = raw.strip()
    s = re.sub(r"^(?:https?://)?(?:www\.)?arxiv\.org/(?:abs|pdf)/", "arXiv:", s, flags=re.I)
    s = re.sub(r"^(?:https?://)?(?:dx\.)?doi\.org/", "", s, flags=re.I)
    s = re.sub(r"^doi:\s*", "", s, flags=re.I)
    s = re.sub(r"[\s.,;:'\"<>\]}]+$", "", s)
    if s.endswith(")") and s.count("(") < s.count(")"):
        s = s[:-1]
    m = re.fullmatch(rf"(?:arxiv:)?\s*({ARXIV_ID})(v\d+)?(?:\.pdf)?", s, flags=re.I)
    if m:
        return f"10.48550/arXiv.{m.group(1)}", m.group(1), m.group(2) or ""
    m = re.fullmatch(rf"10\.48550/arxiv\.({ARXIV_ID})(v\d+)?", s, flags=re.I)
    if m:
        return f"10.48550/arXiv.{m.group(1)}", m.group(1), m.group(2) or ""
    if re.fullmatch(r"10\.\d{4,9}/\S+", s):
        return s, None, ""
    raise Failure("invalid_identifier", 1,
                  "pass a DOI (10.xxxx/...), a doi.org URL, or an arXiv id such as 2006.11239", input=raw)


# ------------------------------------------------------------------- network

def fetch_csl(doi):
    url = DOI_BASE_URL + "/" + urllib.parse.quote(doi, safe="/")
    req = urllib.request.Request(url, headers={"Accept": CSL_ACCEPT, "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status, ctype, body, final = resp.status, resp.headers.get("Content-Type", ""), resp.read(), resp.geturl()
    except urllib.error.HTTPError as e:
        log(f"GET {url} -> {e.code}")
        if e.code == 404:
            raise Failure("not_found", 1, "check the DOI for typos; if it is fresh, the registration agency may "
                          "not have indexed it yet - search the title instead", url=url)
        if e.code in (406, 415) or 400 <= e.code < 500:
            raise Failure("no_csl_record", 1, "hand-write item.json or use the recognizer fallback",
                          url=url, status=e.code)
        raise Failure("doi_org_unreachable", 2, "doi.org returned a server error; retry later", url=url, status=e.code)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        log(f"GET {url} -> {e}")
        raise Failure("doi_org_unreachable", 2, "check network / proxy and retry", url=url, error=str(e))
    log(f"GET {url} -> {status} {ctype} (final: {final})")
    if "json" not in ctype.lower():
        raise Failure("no_csl_record", 1, "hand-write item.json or use the recognizer fallback",
                      url=url, content_type=ctype, final_url=final)
    try:
        record = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise Failure("no_csl_record", 1, "hand-write item.json or use the recognizer fallback",
                      url=url, content_type=ctype, final_url=final)
    if not isinstance(record, dict):
        raise Failure("no_csl_record", 1, "hand-write item.json or use the recognizer fallback", url=url)
    # Registration agency, for libraryCatalog: Crossref says so in `source`; DataCite answers from crosscite.org.
    agency = first_str(record.get("source")) or ("Datacite" if "crosscite.org" in final or "datacite" in final else "")
    return record, agency


def fetch_schema(base_url):
    url = base_url.rstrip("/") + "/api/schema"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with opener.open(req, timeout=15) as resp:
            body = resp.read()
    except urllib.error.HTTPError as e:
        log(f"GET {url} -> {e.code}")
        if e.code == 403:
            raise Failure("local_api_disabled", 2,
                          "ask the user to enable the local API in Zotero (Settings > Advanced), then rerun", url=url)
        raise Failure("zotero_unreachable", 2, "Zotero answered unexpectedly; ask the user to check Zotero",
                      url=url, status=e.code)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        log(f"GET {url} -> {e}")
        raise Failure("zotero_unreachable", 2, "ask the user to start Zotero, then rerun", url=url, error=str(e))
    log(f"GET {url} -> 200")
    return json.loads(body)


# ------------------------------------------------------------------- mapping

def first_str(value):
    """CSL allows string-or-list for titles; numbers show up in DataCite records."""
    if isinstance(value, list):
        value = value[0] if value else ""
    if value is None or isinstance(value, (dict, list)):
        return ""
    return str(value).strip()


def join_list(value):
    if isinstance(value, list):
        return ", ".join(str(v) for v in value if v)
    return first_str(value)


def strip_markup(text):
    """Drop JATS/HTML tags (<jats:p>, <i>, ...) and collapse whitespace."""
    text = re.sub(r"</?[A-Za-z][^<>]*>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def format_date(value):
    """CSL date -> 'YYYY-MM-DD' / 'YYYY-MM' / 'YYYY' (or '' when absent)."""
    if not isinstance(value, dict):
        return ""
    parts = value.get("date-parts") or []
    if not parts or not parts[0]:
        return first_str(value.get("raw") or value.get("literal") or "")
    nums = [int(p) for p in parts[0] if p not in (None, "")]
    if not nums:
        return ""
    return "-".join([str(nums[0])] + [f"{n:02d}" for n in nums[1:3]])


def map_type(csl_type, schema):
    if csl_type in CROSSREF_TYPES:
        return CROSSREF_TYPES[csl_type]
    zotero_types = schema.get("csl", {}).get("types", {}).get(csl_type)
    if zotero_types:
        return zotero_types[0]
    return None


class TypeFields:
    """Field/creator tables of one Zotero itemType, with baseField-aware lookup."""

    def __init__(self, schema, item_type):
        entry = next(t for t in schema["itemTypes"] if t["itemType"] == item_type)
        self.order = ["itemType", "title", "creators"] + [f["field"] for f in entry["fields"]]
        self.base = {f["field"]: f.get("baseField") for f in entry["fields"]}
        self.creator_types = [c["creatorType"] for c in entry["creatorTypes"]]
        self.primary = next((c["creatorType"] for c in entry["creatorTypes"] if c.get("primary")), None)

    def resolve(self, candidates):
        """First candidate that is a field of this type, directly or as a baseField."""
        for c in candidates:
            if c in self.base:
                return c
            for field, base in self.base.items():
                if base == c:
                    return field
        return None


def build_creators(record, schema, tf, warnings):
    csl_to_zotero = {}
    for zotero_type, csl_var in schema["csl"]["names"].items():
        csl_to_zotero.setdefault(csl_var, []).append(zotero_type)
    creators = []
    for csl_var, zotero_types in csl_to_zotero.items():
        people = record.get(csl_var)
        if not isinstance(people, list) or not people:
            continue
        if csl_var == "author" and tf.primary:  # CSL author = the type's primary creator (programmer, artist, ...)
            zotero_types = [tf.primary] + zotero_types
        ctype = next((z for z in zotero_types if z in tf.creator_types), None)
        if ctype is None:
            if "contributor" in tf.creator_types:
                ctype = "contributor"
                warnings.append(f"{csl_var} stored as contributor (no matching creatorType in {tf.order[0]})")
            else:
                warnings.append(f"{csl_var} dropped (no creatorType for it)")
                continue
        for p in people:
            if not isinstance(p, dict):
                continue
            family = first_str(p.get("family"))
            given = first_str(p.get("given"))
            literal = first_str(p.get("literal") or p.get("name"))
            if family and given:
                creators.append({"creatorType": ctype, "firstName": given, "lastName": family})
            elif family or literal:
                creators.append({"creatorType": ctype, "name": family or literal})
    return creators


def build_item(record, schema, doi, arxiv_id, arxiv_version, agency, warnings):
    csl_type = first_str(record.get("type"))
    is_arxiv = doi.lower().startswith("10.48550/arxiv.")
    item_type = "preprint" if is_arxiv else map_type(csl_type, schema)
    unknown = item_type is None
    if unknown:
        item_type = "journalArticle"
        warnings.append(f"unknown CSL/Crossref type {csl_type!r}; itemType defaulted to journalArticle")
    tf = TypeFields(schema, item_type)
    text_map = schema["csl"]["fields"]["text"]
    date_map = schema["csl"]["fields"]["date"]
    item = {"itemType": item_type}
    dropped = []
    # Handled below, or not wanted: `version` is the metadata record version, `source` the agency.
    special = {"title", "abstract", "URL", "DOI", "container-title", "ISSN", "ISBN", "source", "citation-key", "version"}
    if item_type == "journalArticle":
        special.add("publisher")  # Zotero's own DOI import leaves it blank for journal articles

    item["title"] = strip_markup(first_str(record.get("title")))
    if not item["title"]:
        warnings.append("record has no title")

    for csl_key, candidates in text_map.items():
        if csl_key in special or csl_key not in record:
            continue
        value = record[csl_key]
        if isinstance(value, (dict, list)) and not (isinstance(value, list) and all(isinstance(v, (str, int)) for v in value)):
            continue
        value = join_list(value) if isinstance(value, list) else first_str(value)
        if not value:
            continue
        target = tf.resolve(candidates)
        if target:
            item[target] = value
        else:
            dropped.append(csl_key)

    container = first_str(record.get("container-title"))
    if container:
        target = tf.resolve(["publicationTitle"])
        if target:
            item[target] = container
        else:
            dropped.append("container-title")
        if csl_type == "book-chapter" and record.get("ISSN"):
            warnings.append("book-chapter with an ISSN: container-title is probably the series name "
                            "(e.g. LNCS); check bookTitle / series")
    elif item_type in ("journalArticle", "conferencePaper", "bookSection"):
        warnings.append("record has no container-title")

    for key, field in (("ISSN", "ISSN"), ("ISBN", "ISBN")):
        if record.get(key):
            target = tf.resolve([field])
            if target:
                item[target] = join_list(record[key])
            else:
                dropped.append(key)

    abstract = strip_markup(first_str(record.get("abstract")))
    if abstract:
        item["abstractNote"] = abstract
    else:
        warnings.append("record has no abstract")

    for csl_key, field in date_map.items():
        if csl_key == "accessed" or csl_key not in record:
            continue
        value = format_date(record[csl_key])
        if value and tf.resolve([field]):
            item[tf.resolve([field])] = value
    if not item.get("date"):
        for key in DATE_FALLBACKS:
            value = format_date(record.get(key))
            if value:
                item["date"] = value
                warnings.append(f"date taken from {key!r} (no usable 'issued')")
                break
    if not item.get("date"):
        warnings.append("record has no date")
    elif re.fullmatch(r"\d{4}", item["date"]):
        warnings.append("date is year-only")

    event = None
    for key in EVENT_KEYS:
        raw = record.get(key)
        event = first_str(raw.get("name") if isinstance(raw, dict) else raw)
        if event:
            break
    if event:
        target = tf.resolve(["conferenceName", "meetingName"])
        if target:
            item[target] = event
    place = first_str(record.get("publisher-place") or record.get("publisher-location"))
    if place and tf.resolve(["place"]):
        item[tf.resolve(["place"])] = place

    item["creators"] = build_creators(record, schema, tf, warnings)
    if not item["creators"]:
        warnings.append("record has no creators")

    record_url = first_str(record.get("URL"))
    doi_url = f"https://doi.org/{doi}"
    if is_arxiv:
        item["url"] = f"https://arxiv.org/abs/{arxiv_id}{arxiv_version}"
        item["repository"] = "arXiv"
        item["archiveID"] = f"arXiv:{arxiv_id}"
    elif not record_url or re.match(r"^https?://(dx\.)?doi\.org/", record_url, re.I):
        item["url"] = doi_url
    else:
        item["url"] = record_url

    if tf.resolve(["DOI"]):
        item["DOI"] = doi
    else:
        item["extra"] = "\n".join(x for x in (f"DOI: {doi}", item.get("extra", "")) if x)
        warnings.append(f"{item_type} has no DOI field; DOI written to extra")

    if tf.resolve(["libraryCatalog"]):
        item["libraryCatalog"] = f"DOI.org ({agency})" if agency else "DOI.org"

    if dropped:
        warnings.append(f"fields not in {item_type}, dropped: {', '.join(sorted(dropped))}")

    ordered = {k: item[k] for k in tf.order if k in item}
    ordered.update({k: v for k, v in item.items() if k not in ordered})
    return ordered, csl_type, unknown


# ------------------------------------------------------------------- records

def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json_records(text, source):
    """Parse JSONL, a JSON array or one object into a list of [record|None, error|None]."""
    text = text.strip()
    if not text:
        return []
    entries = []
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        obj = None
        for n, ln in enumerate(text.splitlines(), 1):
            if not ln.strip():
                continue
            try:
                rec = json.loads(ln)
            except json.JSONDecodeError as e:
                entries.append([None, {"code": "invalid_json", "detail": f"{source} line {n}: {e.msg}"}])
                continue
            entries.append([rec, None] if isinstance(rec, dict) else [None, {"code": "invalid_record", "detail": f"{source} line {n}: not an object"}])
        return entries
    for rec in (obj if isinstance(obj, list) else [obj]):
        entries.append([rec, None] if isinstance(rec, dict) else [None, {"code": "invalid_record", "detail": f"{source}: not an object"}])
    return entries


def load_record_files(paths):
    """One entry per path: {path, record, orig, error}; unreadable files become failed entries, never written back."""
    entries = []
    for raw in paths:
        path = Path(raw)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            entries.append({"path": path, "record": None, "orig": None, "error": {"code": "unreadable", "detail": f"{path}: {e}"}})
            continue
        parsed = read_json_records(text, str(path))
        if len(parsed) != 1 or parsed[0][0] is None:
            err = parsed[0][1] if parsed and parsed[0][1] else {"code": "invalid_record", "detail": f"{path}: expected one JSON object"}
            entries.append({"path": path, "record": None, "orig": None, "error": err})
            continue
        entries.append({"path": path, "record": parsed[0][0], "orig": json.dumps(parsed[0][0], sort_keys=True), "error": None})
    return entries


def write_record(path, record):
    """Atomic write: temp file in the same directory, then os.replace."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.stem}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(record, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        umask = os.umask(0)
        os.umask(umask)
        os.chmod(tmp, 0o666 & ~umask)  # mkstemp gives 0600; behave like an ordinary file write
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_results(results, quiet):
    """results: [(path, record, summary, outcome)], outcome ok|skipped|failed.

    quiet (-i / --out-dir): records were written to files; stdout gets one summary line per record and the
    final {"summary"} line. Otherwise stdout gets the full records as JSONL and the summary goes to stderr.
    Returns the exit status: 1 when anything failed."""
    counts = {"total": len(results), "ok": 0, "skipped": 0, "failed": 0}
    for path, record, summary, outcome in results:
        counts[outcome] += 1
        if quiet:
            print(json.dumps(summary, ensure_ascii=False))
        elif record is not None:
            print(json.dumps(record, ensure_ascii=False))
        else:
            print(json.dumps(summary, ensure_ascii=False))
    summary_line = json.dumps({"summary": counts}, ensure_ascii=False)
    print(summary_line, file=sys.stdout if quiet else sys.stderr)
    return 1 if counts["failed"] else 0


# ---------------------------------------------------------------- id sources

def parse_id_lines(text, source):
    """`identifier[<TAB>citation key]` per line; '#' comments and blank lines skipped."""
    out = []
    for n, ln in enumerate(text.splitlines(), 1):
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        ident, _, key = s.partition("\t")
        ident, key = ident.strip(), key.strip()
        if not ident:
            log(f"{source} line {n}: no identifier before the tab, skipped")
            continue
        out.append({"id": ident, "citationKey": key or None})
    return out


def bib_close(text, start, close_ch):
    """Index of the closing delimiter of an entry body starting at `start`, honouring nested braces."""
    depth = 0
    for pos in range(start, len(text)):
        c = text[pos]
        if c == "{":
            depth += 1
        elif c == "}":
            if depth == 0 and close_ch == "}":
                return pos
            depth -= 1
        elif c == close_ch and depth == 0:
            return pos
    return len(text)


def bib_value(body, pos):
    """Parse one field value at pos: {braced}, "quoted", or a bare token; '#' concatenation joined. Returns (value, pos)."""
    parts = []
    n = len(body)
    while True:
        while pos < n and body[pos].isspace():
            pos += 1
        if pos >= n:
            break
        c = body[pos]
        if c == "{":
            depth, start = 0, pos
            while pos < n:
                if body[pos] == "{":
                    depth += 1
                elif body[pos] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                pos += 1
            parts.append(body[start + 1:pos])
            pos += 1
        elif c == '"':
            depth, start = 0, pos + 1
            pos += 1
            while pos < n:
                if body[pos] == "{":
                    depth += 1
                elif body[pos] == "}":
                    depth -= 1
                elif body[pos] == '"' and depth == 0:
                    break
                pos += 1
            parts.append(body[start:pos])
            pos += 1
        else:
            m = re.match(r"[^,#\s]+", body[pos:])
            if not m:
                break
            parts.append(m.group(0))
            pos += m.end()
        while pos < n and body[pos].isspace():
            pos += 1
        if pos < n and body[pos] == "#":
            pos += 1
            continue
        break
    return "".join(parts), pos


def bib_clean(value):
    """Drop braces and collapse whitespace (titles and identifiers only; no LaTeX decoding)."""
    return re.sub(r"\s+", " ", value.replace("{", "").replace("}", "")).strip()


def parse_bib(text):
    """Minimal BibTeX reader: yields (entry_type, key, fields) with lower-cased field names; @comment/@string/@preamble skipped."""
    pos = 0
    while True:
        at = text.find("@", pos)
        if at < 0:
            return
        m = re.match(r"@\s*([A-Za-z]+)\s*([{(])", text[at:])
        if not m:
            pos = at + 1
            continue
        etype, open_ch = m.group(1).lower(), m.group(2)
        body_start = at + m.end()
        end = bib_close(text, body_start, "}" if open_ch == "{" else ")")
        body = text[body_start:end]
        pos = end + 1
        if etype in ("comment", "string", "preamble"):
            continue
        key, _, rest = body.partition(",")
        fields = {}
        p = 0
        while True:
            fm = re.match(r"\s*,?\s*([^\s=,]+)\s*=\s*", rest[p:])
            if not fm:
                break
            value, p = bib_value(rest, p + fm.end())
            fields[fm.group(1).lower()] = bib_clean(value)
        yield etype, key.strip(), fields


def bib_identifier(fields):
    """DOI, else an arXiv id (eprint / a URL or journal mentioning arXiv), else None."""
    doi = (fields.get("doi") or "").strip()
    if doi:
        return re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", doi, flags=re.I)
    eprint = (fields.get("eprint") or "").strip()
    prefix = (fields.get("archiveprefix") or fields.get("eprinttype") or "").strip().lower()
    m = re.fullmatch(rf"(?:arxiv:)?({ARXIV_ID})(v\d+)?", eprint, flags=re.I)
    if eprint and (prefix == "arxiv" or m):
        return "arXiv:" + (m.group(1) + (m.group(2) or "") if m else eprint)
    for name in ("url", "journal", "howpublished", "note", "eprint"):
        m = re.search(rf"(?:arxiv\.org/(?:abs|pdf)/|arxiv:\s*)({ARXIV_ID})(v\d+)?", fields.get(name) or "", flags=re.I)
        if m:
            return "arXiv:" + m.group(1) + (m.group(2) or "")
    return None


def entries_from_bib(text):
    out = []
    for etype, key, fields in parse_bib(text):
        ident = bib_identifier(fields)
        entry = {"id": ident or fields.get("title") or "", "citationKey": key or None}
        if not ident:
            entry["no_identifier"] = True
        out.append(entry)
    return out


# ---------------------------------------------------------------------- slugs

SLUG_UNSAFE = re.compile(r'[<>:"/\\|?*\s]+')


def clean(s, limit=None):
    """Lower-case letters and digits only; accents stripped."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if ch.isalnum() and not unicodedata.combining(ch)).lower()
    return s[:limit] if limit else s


def derive_slug(item):
    """<first author surname><year><first title word of >= 4 letters>, e.g. liu2022progressive; '' when nothing usable."""
    creators = item.get("creators") or []
    first = creators[0] if creators and isinstance(creators[0], dict) else {}
    surname = first.get("lastName") or (first.get("name") or "").split()[-1:] or ""
    surname = surname[0] if isinstance(surname, list) else surname
    year = re.match(r"\d{4}", item.get("date") or "")
    word = next((w for w in re.findall(r"[^\W_]+", item.get("title") or "") if sum(ch.isalpha() for ch in w) >= 4), "")
    return clean(surname) + (year.group(0) if year else "") + clean(word)


def slug_for(record, given_key):
    if record.get("slug"):
        return str(record["slug"])
    key = given_key or record.get("citationKey")
    if key:
        return SLUG_UNSAFE.sub("_", key).strip("_") or clean(key)
    slug = derive_slug(record.get("item") or {}) if isinstance(record.get("item"), dict) else ""
    return slug or clean(str(record.get("id") or ""), 60) or "record"


def normalize_id(ident):
    try:
        return parse_identifier(ident)[0].lower()
    except Failure:
        return ident.strip().lower()


# ---------------------------------------------------------------------- main

def fetch_and_map(ident, schema):
    """identifier -> (item, warnings, csl_type, unknown_type, doi); raises Failure."""
    doi, arxiv_id, arxiv_version = parse_identifier(ident)
    record, agency = fetch_csl(doi)
    warnings = []
    record_doi = first_str(record.get("DOI"))
    if record_doi and record_doi.lower() != doi.lower():
        warnings.append(f"record DOI {record_doi!r} differs from requested {doi!r}; using the record's")
        doi = record_doi
    item, csl_type, unknown = build_item(record, schema, doi, arxiv_id, arxiv_version, agency, warnings)
    return item, warnings, csl_type, unknown, doi


def run_single(args):
    """v1: one --doi, one --out; writes the item draft and prints the v1 report."""
    ident = args.doi[0]
    try:
        schema = fetch_schema(args.base_url)
        item, warnings, csl_type, unknown, doi = fetch_and_map(ident, schema)
    except Failure as f:
        emit(f.code, f.exit_code, f.hint, **{"input": ident, **f.extra})

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(item, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    log(f"wrote {args.out} ({item['itemType']}, {len(item['creators'])} creators, {len(warnings)} warnings)")

    result = {"out": args.out, "itemType": item["itemType"], "title": item.get("title", ""), "doi": doi,
              "csl_type": csl_type, "warnings": warnings}
    if unknown:
        emit("unknown_type", 1, "set the right itemType in item.json (check_item.py --help lists the skeleton) "
             "or keep journalArticle if it fits", **result)
    emit("ok", 0, **result)


def collect_entries(args):
    """Every input becomes an entry {path, record, orig, error, given_key, no_identifier}."""
    entries = []

    def from_ids(specs):
        for spec in specs:
            entries.append({"path": None, "record": {"id": spec["id"]}, "orig": None, "error": None,
                            "given_key": spec.get("citationKey"), "no_identifier": spec.get("no_identifier", False)})

    from_ids([{"id": d} for d in args.doi])
    if args.ids:
        from_ids(parse_id_lines(Path(args.ids).read_text(encoding="utf-8"), args.ids))
    if args.bib:
        from_ids(entries_from_bib(Path(args.bib).read_text(encoding="utf-8")))
    if args.records:
        for e in load_record_files(args.records):
            entries.append({**e, "given_key": None, "no_identifier": False})
    if not (args.doi or args.ids or args.bib or args.records):
        text = sys.stdin.read()
        if text.lstrip()[:1] in ("{", "["):
            for rec, err in read_json_records(text, "stdin"):
                entries.append({"path": None, "record": rec, "orig": None, "error": err, "given_key": None, "no_identifier": False})
        else:
            from_ids(parse_id_lines(text, "stdin"))
    return entries


def index_out_dir(out_dir):
    """normalized id -> (path, has_item) for the records already in DIR."""
    index = {}
    for path in sorted(out_dir.glob("*.json")):
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(rec, dict) and isinstance(rec.get("id"), str) and rec["id"].strip():
            index[normalize_id(rec["id"])] = (path, bool(rec.get("item")))
    return index


def unique_slug(base, ident, used, out_dir):
    """First of base, base-2, base-3 ... that is free (or already holds this very identifier)."""
    slug, n = base, 1
    while True:
        holder = used.get(slug)
        if holder is None and out_dir is not None and (out_dir / f"{slug}.json").exists():
            try:
                holder = normalize_id(str(json.loads((out_dir / f"{slug}.json").read_text(encoding="utf-8")).get("id") or "")) or "?"
            except (OSError, ValueError, AttributeError):
                holder = "?"
        if holder is None or holder == ident:
            used[slug] = ident
            return slug
        n += 1
        slug = f"{base}-{n}"


def process_entry(entry, schema, ctx):
    """Fill one entry's record; returns (summary, outcome). The record gets `code` only on failure."""
    rec = entry["record"]
    if entry["error"]:
        stem = entry["path"].stem if entry["path"] else "stdin"
        entry["record"] = {"slug": stem, "code": entry["error"]["code"], "detail": entry["error"]["detail"]}
        return {"slug": stem, "code": entry["error"]["code"], "detail": entry["error"]["detail"]}, "failed"
    if entry["given_key"] and not rec.get("citationKey"):
        rec["citationKey"] = entry["given_key"]
    ident = rec.get("id")
    ident = ident.strip() if isinstance(ident, str) else ""
    if isinstance(rec.get("item"), dict) and rec["item"]:
        # Already filled; with --out-dir it is still copied there, so keep the slug free of collisions.
        rec["slug"] = unique_slug(slug_for(rec, entry["given_key"]), normalize_id(ident) if ident else "?", ctx["used"], ctx["out_dir"])
        return {"slug": rec["slug"], "code": "skipped", "reason": "has_item", "id": ident}, "skipped"
    if not ident:
        rec["slug"] = rec.get("slug") or slug_for(rec, entry["given_key"])
        rec["code"] = "no_id"
        return {"slug": rec["slug"], "code": "no_id", "hint": "the record has no `id` to resolve"}, "failed"
    norm = normalize_id(ident)
    if norm in ctx["seen"]:
        rec["slug"] = rec.get("slug") or ctx["seen"][norm]
        return {"slug": rec["slug"], "code": "skipped", "reason": "duplicate", "id": ident}, "skipped"
    existing = ctx["existing"].get(norm)
    if existing and existing[1]:
        ctx["seen"][norm] = existing[0].stem
        return {"slug": existing[0].stem, "code": "skipped", "reason": "exists", "id": ident, "file": existing[0].name}, "skipped"
    if entry.get("no_identifier"):
        rec["slug"] = ctx["seen"][norm] = unique_slug(slug_for(rec, entry["given_key"]), norm, ctx["used"], ctx["out_dir"])
        rec["code"] = "no_identifier"
        return {"slug": rec["slug"], "code": "no_identifier", "id": ident,
                "hint": "no DOI or arXiv id in the source; search the title, then set `id` by hand"}, "failed"
    try:
        item, warnings, csl_type, unknown, doi = fetch_and_map(ident, schema)
    except Failure as f:
        rec["slug"] = existing[0].stem if existing else unique_slug(slug_for(rec, entry["given_key"]), norm, ctx["used"], ctx["out_dir"])
        ctx["seen"][norm] = rec["slug"]
        rec["code"] = f.code
        for k in ("hint", "detail"):
            rec.pop(k, None)
        if f.hint:
            rec["hint"] = f.hint
        return {"slug": rec["slug"], "code": f.code, "id": ident, **{k: v for k, v in f.extra.items() if k != "input"},
                **({"hint": f.hint} if f.hint else {})}, "failed"
    rec["item"] = item
    for k in ("code", "hint", "detail"):
        rec.pop(k, None)
    if warnings:
        rec["warnings"] = warnings
    else:
        rec.pop("warnings", None)
    rec["slug"] = existing[0].stem if existing else unique_slug(slug_for(rec, entry["given_key"]), norm, ctx["used"], ctx["out_dir"])
    ctx["seen"][norm] = rec["slug"]
    summary = {"slug": rec["slug"], "code": "ok", "id": ident, "itemType": item["itemType"], "title": item.get("title", "")[:80]}
    if rec.get("citationKey"):
        summary["citationKey"] = rec["citationKey"]
    if warnings:
        summary["warnings"] = warnings
    return summary, "ok"


def run_stream(args):
    entries = collect_entries(args)
    if not entries:
        emit("no_records", 1, "pass --doi / --ids / --bib, record paths, or feed identifiers or records on stdin")
    try:
        schema = fetch_schema(args.base_url)
    except Failure as f:
        emit(f.code, f.exit_code, f.hint, **f.extra)
    out_dir = Path(args.out_dir) if args.out_dir else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
    ctx = {"seen": {}, "used": {}, "out_dir": out_dir, "existing": index_out_dir(out_dir) if out_dir else {}}

    results = []
    for entry in entries:
        summary, outcome = process_entry(entry, schema, ctx)
        rec = entry["record"]
        if out_dir and rec is not None and summary.get("reason") not in ("exists", "duplicate"):
            path = out_dir / f"{rec['slug']}.json"
            write_record(path, rec)
            summary["file"] = path.name
        elif args.in_place and entry["path"] and rec is not None and not entry["error"] \
                and json.dumps(rec, sort_keys=True) != entry["orig"]:
            write_record(entry["path"], rec)
        results.append((entry["path"], rec, summary, outcome))
    return write_results(results, quiet=bool(args.in_place or out_dir))


def parse_args():
    ap = argparse.ArgumentParser(
        description="Resolve DOIs / arXiv ids to Zotero item drafts: one --doi with --out (v1), or a stream of records.",
        epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--doi", action="append", default=[], metavar="ID",
                    help="DOI, doi.org URL, 'doi:' form, arXiv id (with or without 'arXiv:' / version) or arXiv URL; repeatable")
    ap.add_argument("--ids", metavar="FILE", help="list of `identifier[<TAB>citation key]`, one per line; '#' comments and blank lines skipped")
    ap.add_argument("--bib", metavar="FILE", help="BibTeX file: each entry's key becomes citationKey; id from doi / eprint / arXiv URL, else the title")
    ap.add_argument("--out", metavar="FILE", help="v1 single mode (exactly one --doi): write the item JSON draft here")
    ap.add_argument("--out-dir", metavar="DIR", help="stream mode: write one record per identifier to DIR/<slug>.json; existing records are kept")
    ap.add_argument("-i", "--in-place", action="store_true", help="write each record back to its file; stdout gets one summary line per record")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL, metavar="URL",
                    help=f"Zotero local API base for GET /api/schema (default {DEFAULT_BASE_URL}; proxy is bypassed)")
    ap.add_argument("records", nargs="*", metavar="RECORD", help="existing record files whose `item` is to be filled")
    args = ap.parse_args()
    if args.out:
        if len(args.doi) != 1 or args.ids or args.bib or args.records or args.out_dir or args.in_place:
            ap.error("--out is the v1 single mode: exactly one --doi and nothing else (use --out-dir for a batch)")
    if args.in_place and args.out_dir:
        ap.error("-i writes records back to their files; --out-dir writes new ones - pick one")
    if args.in_place and not args.records:
        ap.error("-i needs record paths (stdin input cannot be written back)")
    if args.out_dir and args.records:
        ap.error("record paths are updated with -i, not copied to --out-dir")
    return args


def main():
    args = parse_args()
    if args.out:
        run_single(args)
    sys.exit(run_stream(args))


if __name__ == "__main__":
    main()
