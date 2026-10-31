#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Check existing Zotero items for problems worth tidying, read-only: duplicates, citation keys, stray webpages, attachment titles, bad fields.

The whole library is read once (every page of /items: items, attachments and notes; trashed ones dropped), so
duplicates and citation-key clashes are found across the library whatever the scope. The scope only chooses which
items are reported: --collection KEY (--recursive takes its subcollections too), --key / --cite (several, or
comma-separated), or nothing for every top-level item. Paths and --collection see only collections outside the trash.

Problem codes (each problem is {"code", ...}):
  duplicate_of            other items with the same DOI or arXiv id ({"keys", "by": doi | arxiv}; a doi.org url
                          counts as the DOI), or the same title ({"by": "title"}: a near match, maybe a
                          preprint/published pair - "pair" says so)
  citation_key            {"problem": "missing"}; {"problem": "duplicate", "keys"}: the other items carrying the same
                          citationKey; {"problem": "tex_special", "suggested"}: a character TeX treats specially
                          (renaming a key breaks the user's \\cite{}: ask first)
  unfiled_webpage         a webpage item in no collection
  nonstandard_title       a PDF or HTML snapshot whose title is outside the scheme <Version>-<Source>-<detail>
                          (paper.py; Zotero's "Full Text PDF", an older run's "Preprint (arXiv)"), or a snapshot in it
                          without a source while its url's site has a name ({"why": "outside_scheme" | "no_source"}). The
                          evidence to name it from, no name: {attachment, title, contentType, url, host, url_site (the
                          url's site by paper.SOURCES, else null: where the item lives or the page was saved from, not
                          proof of the file's source), filename, md5, doi (the item's)}. What the file itself is,
                          paper-fetch judges (references/organize.md, "Attachment titles")
  label_clash             two or more PDFs or snapshots of the item with one title ({"title", "attachments": [keys]}):
                          most likely the same file twice
  superseded              a file another one from the same source replaces (paper.superseded: an older arXiv vN, an
                          in_press copy beside the final one, an older snapshot): {"attachment", "title", "by", "by_title"}
  date_unparseable        a date Zotero cannot parse (no meta.parsedDate), e.g. "十一月 23, 2021"
  abbreviation_misplaced  journalAbbreviation longer than publicationTitle (they are swapped: "patch" swaps them
                          back), or publicationTitle looks abbreviated with no journalAbbreviation
  missing_doi             a journal article or conference paper with no DOI in its DOI field or an Extra "DOI:" line
                          (an arXiv DOI is not one; venues that issue none - ICML, ICLR - are expected here: their
                          official page is the url); paper-fetch's identify --search looks a DOI up by title
  missing_abstract        a research item with no abstract
  no_identifier           no DOI, no arXiv id and no url: nothing locates the paper
  url_not_record          a published item whose url is not its version of record: empty, or a copy (CVF, MICCAI, arXiv, ProQuest, PMC, a
                          library proxy: an EZproxy-style host, OTHER_PROXIES) beside a DOI ("patch" sets
                          https://doi.org/<DOI>); for a NeurIPS DOI (10.52202, the printed proceedings), a url that is
                          not the paper's NeurIPS page
  name_not_tagged         the abstract names a model or system ("we propose EchoWDiff") that no tag carries
                          ({"name"}: a bare tag, or dataset/ for a benchmark - the agent decides)

stdout: one compact JSON line per reported item with problems {key, citationKey, title, itemType, collections (paths
from the root, "/" between names), problems}, then {"summary": {items, with_problems, by_code}}. A --key
or --cite that names no top-level item prints its {key | cite, code, hint} line first (not_found, cite_not_found,
cite_ambiguous); --collection naming no collection prints one collection_not_found line. "patch" appears only where
the fix is mechanical; it is a fields object for one item: write it to a file for `update_item.py --key KEY --patch
FILE`. Every other problem is the agent's to judge and the user's to confirm. Nothing here goes online.

Exit 0 = no problems; 1 = problems listed, a target or collection that does not resolve, or unexpected_response
(a page of the library Zotero sent wrong: nothing was checked); 2 = cannot check (zotero_unreachable,
local_api_disabled).

Examples:
  uv run scripts/lint_items.py --collection 9EYXTC2I --recursive
  uv run scripts/lint_items.py --cite liu2022progressive,smith2024deep
"""
import re

from p2zlib import cli, paper, zotero
from p2zlib.zotero import LIB

RESEARCH_TYPES = {"journalArticle", "conferencePaper", "preprint", "bookSection", "thesis", "report"}
DOI_TYPES = {"journalArticle", "conferencePaper"}
# "we propose EchoWDiff", "Here we present AMIFound", "an approach, PromptIR, for": a capitalised token with a
# second capital or a digit, so ordinary words ("We propose Deep ...") stay out, and not followed by another
# capitalised word, which makes it the start of a phrase ("We propose Weight-Decomposed Low-Rank Adaptation").
NAME = r"([A-Z][\w^+\-]*[A-Z0-9][\w^+\-]*)(?![\w^+\-])(?!\s+[A-Z][a-z])"
NAME_PATTERNS = (re.compile(r"\b[Ww]e\s+(?:propose|present|introduce|develop|name|call)\s+(?:it\s+)?" + NAME),
                 re.compile(r"\b(?:approach|framework|model|method|system|network|pipeline|agent),\s+" + NAME + r","))
# Hosts of copies, not of a version of record (references/import.md step 3: url is the version of record). A living list.
COPY_HOSTS = {"openaccess.thecvf.com", "papers.miccai.org", "arxiv.org", "www.arxiv.org", "www.proquest.com",
              "openreview.net", "europepmc.org", "pmc.ncbi.nlm.nih.gov", "www.ncbi.nlm.nih.gov", "www.ecva.net",
              "www.biorxiv.org", "www.medrxiv.org", "www.researchgate.net", "www.semanticscholar.org"}
# Library proxies, by the form of their hosts (copied from paper-fetch's pflib/web.py, commit 6ea7d15; the
# institution's own proxy is paper-fetch's config, not read here): EZproxy's hostname mode (*.ezproxy.*), OCLC's hosted
# EZproxy (*.idm.oclc.org), WebVPN gateways.
OTHER_PROXIES = re.compile(r"\.idm\.oclc\.org$|(?:^|[.-])(?:ezproxy|webvpn)(?:[.-]|$)", re.I)


class Library:
    """The library, read once: the live top-level items, their children, the collection tree, what duplicates
    and citation-key clashes are found by."""

    def __init__(self, zot):
        rows = [r for r in zot.pages(f"{LIB}/items") if not zotero.data(r).get("deleted")]
        self.top = {r["key"]: r for r in rows if zotero.is_top(r)}
        self.children = {}
        for r in rows:
            parent = zotero.data(r).get("parentItem")
            if parent:
                self.children.setdefault(parent, []).append(r)
        self.tree = zot.collections()
        self.by = {"doi": {}, "arxiv": {}, "title": {}}
        for key, r in self.top.items():
            d = zotero.data(r)
            doi, aid = paper.identifiers(d)
            for by, value in (("doi", doi), ("arxiv", aid), ("title", paper.norm_title(d.get("title")))):
                if value:
                    self.by[by].setdefault(value, []).append(key)
        self.cites = cite_problems({key: zotero.data(r) for key, r in self.top.items()})

    def paths(self, data):
        return [self.tree[c]["path"] for c in data.get("collections") or [] if c in self.tree]

    def in_collection(self, zot, key, recursive):
        wanted = set(zot.collection_scope(key, recursive, self.tree))
        return [r for r in self.top.values() if wanted & set(zotero.data(r).get("collections") or [])]


def cite_problems(items):
    """{item key: its citation_key problems}, from the library-wide check."""
    found, out = paper.cite_problems(items), {}
    for key in found["missing"]:
        out.setdefault(key, []).append({"code": "citation_key", "problem": "missing"})
    for dup in found["duplicates"]:
        for key in dup["keys"]:
            out.setdefault(key, []).append({"code": "citation_key", "problem": "duplicate",
                                            "keys": sorted(k for k in dup["keys"] if k != key)})
    for tex in found["tex"]:
        out.setdefault(tex["key"], []).append({"code": "citation_key", "problem": "tex_special", "suggested": tex["suggested"]})
    return out


def looks_abbreviated(title):
    words = title.split()
    return len(words) >= 2 and sum(w.endswith(".") for w in words) >= 2


def names_in(abstract):
    seen = []
    for pattern in NAME_PATTERNS:
        for m in pattern.finditer(abstract or ""):
            name = m.group(1).rstrip("-")
            if len(name) >= 3 and name not in seen:
                seen.append(name)
    return seen


def unproxy(url):
    """The publisher's url behind a proxy in EZproxy's hostname mode, whose first label is the publisher's host with
    dots as dashes (ieeexplore-ieee-org.<proxy> -> ieeexplore.ieee.org); any other url as it is."""
    host = paper.host_of(url)
    first, _, rest = host.partition(".")
    if not (rest and "-" in first and OTHER_PROXIES.search(host) and not OTHER_PROXIES.search(first)):
        return url
    inner = first.replace("--", "\0").replace("-", ".").replace("\0", "-")
    return re.sub(re.escape(host), inner, url, count=1, flags=re.I)


def title_problems(data, children):
    """nonstandard_title, label_clash and superseded among an item's PDFs and HTML snapshots."""
    files, out, titles = [], [], zotero.pdf_titles(children)
    for c in children:
        d = zotero.data(c)
        if d.get("itemType") != "attachment":
            continue
        label = paper.attachment_label(d, titles)
        if label["version"] is None:  # a link, a note's attachment, a file of another type
            continue
        files.append({"key": c["key"], "title": d.get("title"), "dateAdded": d.get("dateAdded"), **label})
        url = unproxy(d.get("url") or "") or None
        source = paper.source_of(url)
        # A snapshot's url is the page it saved; a PDF's is often the item's, which names no download site.
        no_source = not label["source"] and source and d.get("contentType") == "text/html"
        why = "outside_scheme" if not label["standard"] else "no_source" if no_source else None
        if why:
            out.append({"code": "nonstandard_title", "why": why, "attachment": c["key"], "title": d.get("title"),
                        "contentType": d.get("contentType"), "url": url, "host": paper.host_of(url) or None,
                        "url_site": source, "filename": d.get("filename"), "md5": d.get("md5"),
                        "doi": paper.doi_of(data) or None})
    by_title = {}
    for f in files:
        by_title.setdefault(f["title"], []).append(f["key"])
    out += [{"code": "label_clash", "title": t, "attachments": keys} for t, keys in by_title.items() if len(keys) > 1]
    out += [{"code": "superseded", "attachment": a["key"], "title": a["title"], "by": b["key"], "by_title": b["title"]}
            for a, b in paper.superseded(files) if a["title"] != b["title"]]
    return out


def problems_of(item, lib):
    key, data, meta = item["key"], zotero.data(item), item.get("meta") or {}
    out = []
    doi, aid = paper.identifiers(data)
    others = set()
    for by, value in (("doi", doi), ("arxiv", aid)):
        keys = sorted(k for k in lib.by[by].get(value, ()) if k != key) if value else []
        if keys:
            others.update(keys)
            out.append({"code": "duplicate_of", "by": by, "keys": keys})
    title = paper.norm_title(data.get("title"))
    title_keys = sorted(k for k in lib.by["title"].get(title, ()) if k != key and k not in others) if len(title) >= 12 else []
    if title_keys:
        types = {zotero.data(lib.top[k]).get("itemType") for k in title_keys} | {data.get("itemType")}
        out.append({"code": "duplicate_of", "by": "title", "keys": title_keys,
                    **({"pair": "preprint/published"} if "preprint" in types and len(types) > 1 else {})})
    out += lib.cites.get(key, [])
    if data.get("itemType") == "webpage" and not data.get("collections"):
        out.append({"code": "unfiled_webpage", "url": data.get("url")})
    out += title_problems(data, lib.children.get(key, []))
    if (data.get("date") or "").strip() and not meta.get("parsedDate"):
        out.append({"code": "date_unparseable", "date": data["date"]})
    full, abbr = (data.get("publicationTitle") or "").strip(), (data.get("journalAbbreviation") or "").strip()
    if full and abbr and len(abbr) > len(full):
        out.append({"code": "abbreviation_misplaced", "publicationTitle": full, "journalAbbreviation": abbr,
                    "patch": {"publicationTitle": abbr, "journalAbbreviation": full}})
    elif full and not abbr and "journalAbbreviation" in data and looks_abbreviated(full):
        out.append({"code": "abbreviation_misplaced", "publicationTitle": full,
                    "hint": "publicationTitle looks abbreviated: move it to journalAbbreviation, find the full title"})
    # A DOI only in the url still leaves the DOI field empty; an arXiv DOI (identifiers gives '') is not the article's.
    if data.get("itemType") in DOI_TYPES and not (doi and paper.doi_of(data, url=False)):
        out.append({"code": "missing_doi", "url": data.get("url") or None})
    if data.get("itemType") in RESEARCH_TYPES and not (data.get("abstractNote") or "").strip():
        out.append({"code": "missing_abstract"})
    url = (data.get("url") or "").strip()
    if not doi and not aid and not url and data.get("itemType") in RESEARCH_TYPES:
        out.append({"code": "no_identifier"})
    host = paper.host_of(url)
    if doi and data.get("itemType") != "preprint":
        if doi.startswith("10.52202/"):
            if host not in ("proceedings.neurips.cc", "proceedings.nips.cc"):
                out.append({"code": "url_not_record", "url": url or None,
                            "hint": "a NeurIPS DOI leads to the printed proceedings: url is the paper's NeurIPS page"})
        elif not url or host in COPY_HOSTS or OTHER_PROXIES.search(host):
            field = (data.get("DOI") or "").strip()
            out.append({"code": "url_not_record", "url": url or None,
                        "patch": {"url": f"https://doi.org/{field if paper.DOI_FORM.match(field) else doi}"}})
    tags = {t.get("tag", "") for t in data.get("tags") or []}
    for name in names_in(data.get("abstractNote")):
        if not any(t == name or t.endswith("/" + name) for t in tags):
            out.append({"code": "name_not_tagged", "name": name})
    return out


def lint(zot, args):
    targets = zot.targets(args.key, args.cite) if args.key or args.cite else None
    lib = Library(zot)
    scope = lib.in_collection(zot, args.collection, args.recursive) if args.collection else list(lib.top.values())
    failed = []
    if targets is not None:
        named = set()
        for key, cite, failure in targets:
            head = {"key": key, **({"cite": cite} if cite else {})} if key else {"cite": cite}
            if failure is None and key not in lib.top:
                failure = cli.Stop("not_found", hint=zotero.HINT_NOT_FOUND)
            if failure is not None:
                failed.append(failure.line(**head))
            else:
                named.add(key)
        scope = [r for r in scope if r["key"] in named]
    for line in failed:
        cli.emit(line)
    counts, reported = {}, 0
    for r in scope:
        found = problems_of(r, lib)
        if not found:
            continue
        reported += 1
        for p in found:
            counts[p["code"]] = counts.get(p["code"], 0) + 1
        d = zotero.data(r)
        cli.emit({"key": r["key"], "citationKey": d.get("citationKey") or None, "title": d.get("title"),
                  "itemType": d.get("itemType"), "collections": lib.paths(d), "problems": found})
    summary = {"items": len(scope), "with_problems": reported, "by_code": dict(sorted(counts.items()))}
    cli.emit({"summary": summary})
    return cli.ACT if reported or failed else cli.OK


def main(argv=None):
    p = cli.parser(__doc__)
    p.add_argument("--collection", metavar="KEY", help="report the items of this collection")
    p.add_argument("--recursive", action="store_true", help="with --collection: its subcollections too")
    cli.add_targets(p)
    cli.add_base_url(p)
    args = cli.targets_of(p, p.parse_args(argv), required=False)
    return cli.run(lambda: lint(zotero.Zotero(args.base_url), args))


if __name__ == "__main__":
    raise SystemExit(main())
