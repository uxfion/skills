# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""DOI (or arXiv id) -> Zotero item JSON draft.

Fetches the CSL JSON record from doi.org (content negotiation) and maps it
onto a Zotero item using the live Zotero schema (GET /api/schema: csl.types,
csl.fields, csl.names) plus a small built-in table for Crossref's own type
vocabulary. Writes the draft to --out and prints one JSON object to stdout.

Only GET requests. doi.org goes through the normal proxy settings; the Zotero
local API bypasses the proxy. Tags are never written (Crossref `subject` is a
journal category, not author keywords).
"""

import argparse
import html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE_URL = "http://127.0.0.1:23119"
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
    url = "https://doi.org/" + urllib.parse.quote(doi, safe="/")
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


# ---------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(
        description="Fetch the CSL JSON record for a DOI or arXiv id from doi.org and write a Zotero item.json draft.",
        epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--doi", required=True, metavar="ID",
                    help="DOI, doi.org URL, 'doi:' form, arXiv id (with or without 'arXiv:' / version) or arXiv URL")
    ap.add_argument("--out", required=True, metavar="FILE", help="where to write the item JSON draft (e.g. item.json)")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL, metavar="URL",
                    help=f"Zotero local API base for GET /api/schema (default {DEFAULT_BASE_URL}; proxy is bypassed)")
    args = ap.parse_args()

    try:
        doi, arxiv_id, arxiv_version = parse_identifier(args.doi)
        schema = fetch_schema(args.base_url)
        record, agency = fetch_csl(doi)
    except Failure as f:
        emit(f.code, f.exit_code, f.hint, **{"input": args.doi, **f.extra})

    warnings = []
    record_doi = first_str(record.get("DOI"))
    if record_doi and record_doi.lower() != doi.lower():
        warnings.append(f"record DOI {record_doi!r} differs from requested {doi!r}; using the record's")
        doi = record_doi
    item, csl_type, unknown = build_item(record, schema, doi, arxiv_id, arxiv_version, agency, warnings)

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


if __name__ == "__main__":
    main()
