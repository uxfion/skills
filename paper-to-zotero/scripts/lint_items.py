#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Check Zotero items for problems worth tidying, read-only: duplicates, citation keys, stray webpages, attachment titles, fields.

The whole library is read once (every page of /items: items, attachments and notes; trashed ones dropped), so
duplicates and citation-key clashes are found across the library whatever the scope. The scope only chooses which
items are reported: --collection KEY (--recursive takes its subcollections too), --key / --cite (several, or
comma-separated), or nothing for every top-level item. Paths and --collection see only collections outside the trash.

Problem codes (each problem is {"code", ...}: a fact and its evidence; what it means is a judge's):
  duplicate_of            other items with the same DOI or arXiv id ({"keys", "by": doi | arxiv}; a doi.org url
                          counts as the DOI): the same paper. By title ({"by": "title", "paper", "candidates",
                          "more"?}): the items a Zotero quick search for the title would find (every word of one of
                          paper.title_queries inside a word of their title, creator names or year), less those found
                          by DOI or arXiv id; ranked by paper.candidates as the import's lookup ranks its hits, each
                          {key, title, year, first_author, doi, arxiv, itemType, venue, similarity, attachments (their
                          titles)}, 10 at most, `more` counting the rest; `paper` is this item's own evidence. A title
                          confirms nothing: one paper twice, a preprint and its published version, or two papers alike
  citation_key            {"problem": "missing"}; {"problem": "duplicate", "keys"}: the other items carrying the same
                          citationKey; {"problem": "tex_special", "suggested"}: a character TeX treats specially
                          (renaming a key breaks the user's \\cite{}: ask first)
  unfiled_webpage         a webpage item in no collection
  nonstandard_title       a PDF or HTML snapshot whose title is outside the scheme <Version>-<Source>-<detail>
                          (paper.py; Zotero's "Full Text PDF", an older run's "Preprint (arXiv)"), or a snapshot in
                          it without a source while its url's site has a name ({"why": "outside_scheme" |
                          "no_source"}). The evidence to name it from, no name: {attachment, title, contentType, url,
                          host, url_site (the url's site by paper.SOURCES, else null: where the item lives or the page
                          was saved from, not proof of the file's source), filename, md5, doi (the item's)}. What the
                          file itself is, paper-fetch judges (references/organize.md, "Attachment titles")
  label_clash             two or more PDFs or snapshots of the item with one title ({"title", "attachments": [keys],
                          "same_file"}): same_file true when their md5s are all there and equal (the same file twice),
                          false when they differ (two files under one title: paper-fetch labels them), null when an
                          md5 is missing
  superseded              a file another one from the same source replaces (paper.superseded: an older arXiv vN, an
                          in_press copy beside the final one, an older snapshot): {"attachment", "title", "by",
                          "by_title"}
  date_unparseable        a date Zotero cannot parse (no meta.parsedDate), e.g. "十一月 23, 2021"
  abbreviation_misplaced  journalAbbreviation longer than publicationTitle, both set ({"publicationTitle",
                          "journalAbbreviation"}): maybe swapped
  missing_doi             a journal article or conference paper with no DOI in its DOI field or an Extra "DOI:" line
                          (an arXiv DOI is not one; venues that issue none - ICML, ICLR - are expected here: their
                          official page is the url); paper-fetch's identify --search looks a DOI up by title
  missing_abstract        a research item with no abstract
  no_identifier           no DOI, no arXiv id and no url: nothing locates the paper
  url_not_record          an item with a DOI, not a preprint, whose url is not https://doi.org/<DOI> (http, dx.doi.org
                          and case aside): {"url", "host", "doi"}; "patch" sets https://doi.org/<DOI> when the url is
                          empty. Whether the url is the version of record - the publisher's page, a copy, a library
                          proxy, a venue's own page - is the judge's

stdout: one compact JSON line per reported item with problems {key, citationKey, title, itemType, collections (paths
from the root, "/" between names), problems}, then {"summary": {items, with_problems, by_code}}. A --key
or --cite that names no top-level item prints its {key | cite, code, hint} line first (not_found, cite_not_found,
cite_ambiguous); --collection naming no collection prints one collection_not_found line. "patch" appears only where
the fix is mechanical (an empty url); it is a fields object for one item: the "set" of an `update_item.py --batch`
line {"key", "set"}, or a file for `--key KEY --patch FILE`. Every other problem is the agent's to judge and the
user's to confirm. Nothing here goes online.

Exit 0 = no problems; 1 = problems listed, a target or collection that does not resolve, or unexpected_response
(a page of the library Zotero sent wrong: nothing was checked); 2 = cannot check (zotero_unreachable,
local_api_disabled).

Examples:
  uv run scripts/lint_items.py --collection 9EYXTC2I --recursive
  uv run scripts/lint_items.py --cite liu2022progressive,smith2024deep
"""
import re
import unicodedata
from urllib.parse import unquote

from p2zlib import cli, paper, zotero
from p2zlib.zotero import LIB

RESEARCH_TYPES = {"journalArticle", "conferencePaper", "preprint", "bookSection", "thesis", "report"}
DOI_TYPES = {"journalArticle", "conferencePaper"}
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
        self.by = {"doi": {}, "arxiv": {}}
        self.words, self.held = {}, {}  # word -> the keys of the items holding it (searchable_words); holding()'s answers
        for key, r in self.top.items():
            d = zotero.data(r)
            doi, aid = paper.identifiers(d)
            for by, value in (("doi", doi), ("arxiv", aid)):
                if value:
                    self.by[by].setdefault(value, []).append(key)
            for w in searchable_words(d):
                self.words.setdefault(w, set()).add(key)
        self.cites = cite_problems({key: zotero.data(r) for key, r in self.top.items()})

    def paths(self, data):
        return [self.tree[c]["path"] for c in data.get("collections") or [] if c in self.tree]

    def in_collection(self, zot, key, recursive):
        wanted = set(zot.collection_scope(key, recursive, self.tree))
        return [r for r in self.top.values() if wanted & set(zotero.data(r).get("collections") or [])]

    def title_hits(self, title):
        """The keys a quick search for the title would find: the items where every word of one of
        paper.title_queries is inside one of their words, as Zotero matches a word ("network" finds "Networks")."""
        hits = set()
        for q in paper.title_queries(title):
            postings = sorted((self.holding(w) for w in words(q)), key=len)
            if postings:
                hits |= postings[0].intersection(*postings[1:])
        return hits

    def holding(self, w):
        """The keys of the items with a word that contains w (worked out once per word)."""
        if w not in self.held:
            self.held[w] = set().union(*(keys for v, keys in self.words.items() if w in v))
        return self.held[w]


def words(text):
    """A text's words, as a quick search compares them here: runs of letters and digits, NFKC, casefolded."""
    return set(re.findall(r"\w+", unicodedata.normalize("NFKC", text or "").casefold()))


def searchable_words(data):
    """The words a quick search (titleCreatorYear) looks in: the item's title, its creators' names, its year."""
    names = [c.get(f) or "" for c in data.get("creators") or [] if isinstance(c, dict) for f in ("lastName", "firstName", "name")]
    year = re.search(r"\d{4}", data.get("date") or "")
    return words(" ".join([data.get("title") or "", *names, year.group(0) if year else ""]))


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
        files.append({"key": c["key"], "title": d.get("title"), "dateAdded": d.get("dateAdded"), "md5": d.get("md5"), **label})
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
        by_title.setdefault(f["title"], []).append(f)
    for title, clash in by_title.items():
        if len(clash) > 1:
            md5s = {f["md5"] for f in clash}
            out.append({"code": "label_clash", "title": title, "attachments": [f["key"] for f in clash],
                        "same_file": len(md5s) == 1 if all(md5s) else None})
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
    hits = sorted(lib.title_hits(data.get("title")) - others - {key})
    if hits:
        near, more = paper.candidates(data, [(k, zotero.data(lib.top[k]), None) for k in hits])
        for c in near:
            c["attachments"] = paper.file_titles(zotero.attachment_rows(lib.children.get(c["key"], [])))
        mine = {**paper.evidence(data), "attachments": paper.file_titles(zotero.attachment_rows(lib.children.get(key, [])))}
        out.append({"code": "duplicate_of", "by": "title", "paper": mine, "candidates": near, **({"more": more} if more else {})})
    out += lib.cites.get(key, [])
    if data.get("itemType") == "webpage" and not data.get("collections"):
        out.append({"code": "unfiled_webpage", "url": data.get("url")})
    out += title_problems(data, lib.children.get(key, []))
    if (data.get("date") or "").strip() and not meta.get("parsedDate"):
        out.append({"code": "date_unparseable", "date": data["date"]})
    full, abbr = (data.get("publicationTitle") or "").strip(), (data.get("journalAbbreviation") or "").strip()
    if full and abbr and len(abbr) > len(full):
        out.append({"code": "abbreviation_misplaced", "publicationTitle": full, "journalAbbreviation": abbr})
    # A DOI only in the url still leaves the DOI field empty; an arXiv DOI (identifiers gives '') is not the article's.
    if data.get("itemType") in DOI_TYPES and not (doi and paper.doi_of(data, url=False)):
        out.append({"code": "missing_doi", "url": data.get("url") or None})
    if data.get("itemType") in RESEARCH_TYPES and not (data.get("abstractNote") or "").strip():
        out.append({"code": "missing_abstract"})
    url = (data.get("url") or "").strip()
    if not doi and not aid and not url and data.get("itemType") in RESEARCH_TYPES:
        out.append({"code": "no_identifier"})
    if doi and data.get("itemType") != "preprint" and paper.normalize_doi(unquote(url)) != doi:
        field = (data.get("DOI") or "").strip()
        record = field if paper.DOI_FORM.match(field) else doi  # the field's own case
        out.append({"code": "url_not_record", "url": url or None, "host": paper.host_of(url) or None, "doi": record,
                    **({} if url else {"patch": {"url": f"https://doi.org/{record}"}})})
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
