#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Draft records from paper-fetch's result files: each record's Zotero item, made from the result's CSL by Zotero's
own CSL tables (its schema) plus the rules below.

  uv run scripts/draft_item.py <scratch>/paper-to-zotero/fetch/results/*.json
  uv run scripts/draft_item.py --redraft <scratch>/paper-to-zotero/fetch/results/<slug>.json

The results are the arguments, or lines on stdin. A record is <records>/<slug>.json, under its result's slug; the
records directory is -o, by default records/ beside the result's fetch/ (an import's layout: <scratch>/paper-to-
zotero/{fetch,records}/). Drafting writes:
  fetched      the result file's absolute path
  item         the Zotero item to create; the agent may revise it
  citationKey  the key given (the result's `cite`, verbatim: a .bib key); otherwise Better BibTeX makes the key
  tags         with automatic tags on (the config's automatic_tags, or --automatic-tags for this run; off by default),
               the source's own keywords as automatic tags, added to the record's tags: arXiv's subject classes, named as
               Zotero's arXiv translator names them, and the authors' keywords (the result's csl.keyword). OpenAlex's
               keywords, its model's, never.
  warnings     what drafting noticed: a type guessed, a role stored as contributor, the DOI put in extra, fields the
               type has no place for. What the metadata itself is suspected of stays in the result's warnings.
A record with an item is skipped; --redraft drafts its item again (after pf.py identify --redraft chose another
version) and keeps the agent's fields, unless the item is in Zotero already. A result renamed since its record was
drafted (its renamed_from) takes the record along: the record is renamed and points at it (`renamed_from` on the
line).

Rules beyond the tables:
  - record_of preprint makes a preprint, whatever the CSL's type; an arXiv one gets url arxiv.org/abs/<id> (with
    the vN the request named), repository arXiv, archiveID arXiv:<id>. Any other item's url is https://doi.org/<DOI>,
    or the CSL's URL (a paper's page) when there is no DOI.
  - A journalArticle gets no publisher, as in Zotero's own DOI import; a type without a field for the DOI, PMID or
    PMCID gets it in extra ("PMID: <n>"), where Zotero reads it.
  - A published version whose result keeps versions.preprint takes the preprint's abstract and authors when its own
    record has none, and "arXiv: <id>" in extra.
  - The CSL's `version` is the metadata record's (DataCite's), not the paper's: not written.

stdout: one line per result {slug, code, itemType?, title?, warnings?}, then {"summary"}.
  ok              drafted
  skipped         reason exists: the record has an item (--redraft drafts it again)
  already_saved   --redraft on a record whose item is in Zotero: change it there with update_item.py
  stub            the result has no metadata (paper-fetch could not identify the paper): the record holds only
                  `fetched`, and recognize.py takes it from the PDF
  result_invalid  not one of paper-fetch's result files
Exit 0 = every result drafted or skipped; 1 = some not; 2 = Zotero (asked for its schema once a run) not running.
"""
import argparse
import json
import re
import sys
from pathlib import Path

from p2zlib import cli, config, run, zotero

# arXiv archives that Zotero's arXiv translator writes as "<Archive> - <Category>"; a category without a subject
# class (quant-ph, hep-th, gr-qc, ...) is written as its name alone.
ARXIV_ARCHIVES = {
    "cs": "Computer Science", "econ": "Economics", "eess": "Electrical Engineering and Systems Science",
    "math": "Mathematics", "nlin": "Nonlinear Sciences", "physics": "Physics", "q-bio": "Quantitative Biology",
    "q-fin": "Quantitative Finance", "stat": "Statistics", "astro-ph": "Astrophysics", "cond-mat": "Condensed Matter",
}
ARXIV_CATEGORY = re.compile(r"(.+?)\s*\(([a-z][a-z-]*)(?:\.([A-Za-z][A-Za-z-]*))?\)")
# CSL variables the rules write, or that are not the paper's; the other variables go through the schema's table.
BY_RULE = {"URL", "DOI", "citation-key", "version"}
# Identifiers kept in extra ("PMID: <n>", as Zotero reads it) when the type has no field for them; DOI by its own rule.
IDENTIFIERS = ("PMID", "PMCID")


def first_str(value):
    """CSL gives a title as a string or a list; DataCite records carry numbers."""
    if isinstance(value, list):
        value = value[0] if value else ""
    if value is None or isinstance(value, (dict, list)):
        return ""
    return str(value).strip()


def join_list(value):
    return ", ".join(str(v) for v in value if v) if isinstance(value, list) else first_str(value)


def format_date(value):
    """A CSL date -> 'YYYY-MM-DD' / 'YYYY-MM' / 'YYYY'; '' when absent."""
    if not isinstance(value, dict):
        return ""
    parts = value.get("date-parts") or []
    if not parts or not parts[0]:
        return first_str(value.get("raw") or value.get("literal") or "")
    nums = [int(p) for p in parts[0] if p not in (None, "")]
    return "-".join([str(nums[0])] + [f"{n:02d}" for n in nums[1:3]]) if nums else ""


def arxiv_category_tags(categories):
    """arXiv's categories (DataCite's subjects) -> tag names as Zotero's arXiv translator writes them; FOS entries and
    repeats dropped."""
    tags = []
    for raw in categories if isinstance(categories, list) else [categories]:
        text = raw.strip() if isinstance(raw, str) else ""
        if not text or text.casefold().startswith("fos:"):
            continue
        m = ARXIV_CATEGORY.fullmatch(text)
        if m and not m.group(3):
            tag = m.group(1)  # a category of a single-archive group: quant-ph, hep-th
        elif m and m.group(2) in ARXIV_ARCHIVES:
            tag = f"{ARXIV_ARCHIVES[m.group(2)]} - {m.group(1)}"
        else:
            tag = text
        if tag not in tags:
            tags.append(tag)
    return tags


def author_keywords(csl):
    """The authors' keywords paper-fetch put in csl.keyword (a list; a CSL string is comma-separated), each once."""
    value = csl.get("keyword")
    words = value if isinstance(value, list) else str(value or "").split(",")
    return list(dict.fromkeys(w.strip() for w in words if isinstance(w, str) and w.strip()))


def own(t, *names):
    """The type's own field for the first of the names it has (directly or as a base field); None when none."""
    return next((f for f in (zotero.own_field(t, n) for n in names) if f), None)


def ordered(item, t):
    """The item's fields in the schema's order, after itemType, title and creators."""
    order = ["itemType", "title", "creators"] + t["order"]
    return {**{k: item[k] for k in order if k in item}, **{k: v for k, v in item.items() if k not in order}}


def creators_of(csl, schema, t, item_type, warnings):
    by_var = {}
    for zotero_type, csl_var in schema["csl"]["names"].items():
        by_var.setdefault(csl_var, []).append(zotero_type)
    creators = []
    for csl_var, zotero_types in by_var.items():
        people = csl.get(csl_var)
        if not isinstance(people, list) or not people:
            continue
        if csl_var == "author":  # CSL's author is the type's primary creator (programmer, artist, ...)
            zotero_types = [t["primary"]] + zotero_types
        ctype = next((z for z in zotero_types if z in t["creator_types"]), None)
        if ctype is None and "contributor" in t["creator_types"]:
            ctype = "contributor"
            warnings.append(f"{csl_var} stored as contributor (no matching creatorType in {item_type})")
        elif ctype is None:
            warnings.append(f"{csl_var} dropped (no creatorType for it in {item_type})")
            continue
        for p in people:
            if not isinstance(p, dict):
                continue
            family, given = first_str(p.get("family")), first_str(p.get("given"))
            literal = first_str(p.get("literal") or p.get("name"))
            if family and given:
                creators.append({"creatorType": ctype, "firstName": given, "lastName": family})
            elif family or literal:
                creators.append({"creatorType": ctype, "name": family or literal})
    return creators


def item_of(res, schema, warnings):
    """A result -> (the Zotero item, the source's own keywords as tag names: arXiv's subject classes, the authors')."""
    csl, ids = res["csl"], res.get("ids") or {}
    preprint = (res.get("versions") or {}).get("preprint") or {}
    is_preprint = res.get("record_of") == "preprint"
    csl_type = first_str(csl.get("type"))
    item_type = "preprint" if is_preprint else (schema["csl"]["types"].get(csl_type) or [None])[0]
    if item_type is None:
        item_type = "journalArticle"
        warnings.append(f"CSL type {csl_type!r} is not in Zotero's table: drafted as journalArticle, check the type")
    t = zotero.types_of(schema)[item_type]
    by_rule = BY_RULE | ({"publisher"} if item_type == "journalArticle" else set())
    item, dropped, id_lines = {"itemType": item_type}, [], []
    for csl_key, fields in schema["csl"]["fields"]["text"].items():
        value = csl.get(csl_key)
        if csl_key in by_rule or value is None:
            continue
        if isinstance(value, dict) or (isinstance(value, list) and not all(isinstance(v, (str, int)) for v in value)):
            continue
        value = join_list(value)
        if value:
            target = own(t, *fields)
            if target:
                item[target] = value
            elif csl_key in IDENTIFIERS:
                id_lines.append(f"{csl_key}: {value}")
            else:
                dropped.append(csl_key)
    for csl_key, field in schema["csl"]["fields"]["date"].items():
        value = format_date(csl.get(csl_key)) if csl_key != "accessed" else ""
        if value and own(t, field):
            item[own(t, field)] = value
    item["creators"] = creators_of(csl, schema, t, item_type, warnings)
    if not item["creators"] and preprint.get("author"):
        item["creators"] = creators_of({"author": preprint["author"]}, schema, t, item_type, warnings)
        warnings.append("the record has no authors: the preprint's are drafted")
    if not item.get("abstractNote") and preprint.get("abstract"):
        item["abstractNote"] = preprint["abstract"]
        warnings.append("the record has no abstract: the preprint's is drafted")

    doi, aid = ids.get("doi") or first_str(csl.get("DOI")), ids.get("arxiv") if is_preprint else None
    if aid:
        given = re.search(re.escape(aid) + r"(v\d+)", str((res.get("request") or {}).get("given") or ""), re.I)
        item.update(url=f"https://arxiv.org/abs/{aid}{given.group(1) if given else ''}", repository="arXiv",
                    archiveID=f"arXiv:{aid}")
    elif doi or csl.get("URL"):
        item["url"] = f"https://doi.org/{doi}" if doi else first_str(csl["URL"])
    lines = [ln for ln in str(item.get("extra") or "").splitlines() if ln.strip()]
    if doi and own(t, "DOI"):
        item["DOI"] = doi
    elif doi:
        lines.insert(0, f"DOI: {doi}")
        warnings.append(f"{item_type} has no DOI field; DOI written to extra")
    lines += [ln for ln in id_lines if ln not in lines]
    pre_aid = None if is_preprint else (preprint.get("ids") or {}).get("arxiv")
    if pre_aid and not any(re.match(rf"arxiv:\s*{re.escape(pre_aid)}\b", ln, re.I) for ln in lines):
        lines.append(f"arXiv: {pre_aid}")
    if lines:
        item["extra"] = "\n".join(lines)
    if dropped:
        warnings.append(f"fields not in {item_type}, dropped: {', '.join(sorted(dropped))}")
    keywords = arxiv_category_tags(csl.get("categories") or preprint.get("categories")) + author_keywords(csl)
    return ordered(item, t), list(dict.fromkeys(keywords))


def records_dir(result, out):
    """Where the result's record goes: -o, else the records/ of the import the result belongs to; None when neither."""
    if out:
        return Path(out).expanduser()
    p = Path(result).absolute()
    return p.parents[2] / "records" if p.parent.name == "results" and p.parents[1].name == "fetch" else None


def draft(path, out, redraft, schema_of, automatic=False):
    try:
        res = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise cli.Stop("result_invalid", path=str(path), detail=str(e), hint="Give paper-fetch's result files: "
                                                                          "<scratch>/paper-to-zotero/fetch/results/*.json.") from None
    if not isinstance(res, dict) or not res.get("slug"):
        raise cli.Stop("result_invalid", path=str(path), hint="Give paper-fetch's result files: "
                                                               "<scratch>/paper-to-zotero/fetch/results/*.json.")
    records = records_dir(path, out)
    if records is None:
        raise cli.Stop("no_records_dir", path=str(path), hint="The result is not in an import's fetch/results/: give "
                                                              "-o <scratch>/paper-to-zotero/records.")
    records.mkdir(parents=True, exist_ok=True)
    target = records / f"{res['slug']}.json"
    if not isinstance(res.get("csl"), dict):  # a stub: no metadata to draft from, its PDF is the way in
        if not target.exists():
            run.Record(target, {"fetched": str(Path(path).absolute())}).save()
        return {"code": "stub", "warnings": [w for w in res.get("warnings") or [] if isinstance(w, str)],
                "hint": "paper-fetch found no metadata for this paper: once its PDF is in hand, recognize.py has "
                        "Zotero's recognizer identify it from the PDF (references/no-doi-record.md)."}
    moved = next((old for old in res.get("renamed_from") or [] if not target.exists() and (records / f"{old}.json").exists()), None)
    if moved:  # the result was renamed after its record was drafted: the record follows it
        (records / f"{moved}.json").rename(target)
    rec = run.read(target) if target.exists() else run.Record(target, {})
    if moved:
        rec["fetched"] = str(Path(path).absolute())
        rec.save()
    if rec.item and not redraft:
        return cli.skipped("exists", **({"renamed_from": moved} if moved else {}))
    if rec.item and (rec.get("saved") or rec.get("attach")):
        return {"code": "already_saved", "hint": "The item is in Zotero already (or being created): change it there "
                                                 "with update_item.py."}
    warnings = []
    item, tags = item_of(res, schema_of(records), warnings)
    rec["fetched"] = str(Path(path).absolute())
    rec["item"] = item
    if res.get("cite") and not rec.get("citationKey"):
        rec["citationKey"] = res["cite"]
    have = {t.get("tag") for t in rec.get("tags") or [] if isinstance(t, dict)}
    if automatic and any(n not in have for n in tags):
        rec["tags"] = list(rec.get("tags") or []) + [{"tag": n, "type": 1} for n in tags if n not in have]
    rec.pop("warnings", None)
    if warnings:
        rec["warnings"] = warnings
    rec.save()
    return cli.ok(itemType=item["itemType"], title=(item.get("title") or "")[:80],
                  **({"warnings": warnings} if warnings else {}))


def main(argv=None):
    p = cli.parser(__doc__)
    p.add_argument("results", nargs="*", metavar="RESULT", help="paper-fetch's result files (default: paths on stdin)")
    p.add_argument("-o", "--out", metavar="DIR", help="the records directory (default: records/ beside the result's fetch/)")
    p.add_argument("--redraft", action="store_true", help="draft the items of records that have one again")
    p.add_argument("--automatic-tags", action=argparse.BooleanOptionalAction, default=None,
                   help="the source's own keywords as automatic tags, this run (default: the config's automatic_tags, off)")
    cli.add_base_url(p)
    args = p.parse_args(argv)
    automatic = config.automatic_tags() if args.automatic_tags is None else args.automatic_tags
    paths = args.results or [ln.strip() for ln in sys.stdin if ln.strip()]
    if not paths:
        p.error("give the result files, or their paths on stdin")
    zot, schemas = zotero.Zotero(args.base_url), {}

    def schema_of(records):  # one read of Zotero a run, kept in the import's scratch/schema.json
        if records not in schemas:
            schemas[records] = zot.schema(cache=run.Work(records.parent).schema_file)
        return schemas[records]

    def loop():
        out = cli.Lines()
        for path in paths:
            out.add({"slug": Path(path).stem}, lambda: draft(path, args.out, args.redraft, schema_of, automatic))
        return out.finish()

    return cli.run(loop)


if __name__ == "__main__":
    raise SystemExit(main())
