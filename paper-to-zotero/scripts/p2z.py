#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""paper-to-zotero: put papers into Zotero, read the library, keep it tidy. `p2z.py WORD ...`; each word has its -h.

Each word runs one script of scripts/ (through uv, so the script's own dependencies load), its exit code passed
through; prepare and save run two in turn. An unknown word exits 2 with this list.

Exit codes, every word: 0 done (stderr empty); 1 something is yours to act on: a line's code says what, and a word
over several things ends stderr with {"summary": ...}; 2 cannot go on (Zotero not running, no key, a usage error):
stderr's last line is {code, hint}, and a word over several things lists each one not done as not_run.

A list read through - takes a value a line, or our JSON lines by the field that names the thing; a JSON line without
that field which reports a skip or a failure upstream is passed on as it is, so a failure reaches the pipeline's end.

Examples:
  p2z.py search POCUS | p2z.py pdf -
  p2z.py tag -n --add-tag method/diffusion madhusoodananPOCUSNetBeamformingInclusive2026
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from p2zlib import cli, run

HERE = Path(__file__).resolve().parent
SELF = Path(__file__).name

# word: (script, whether the word is also the script's own command, what it does)
WORDS = {
    "items": ("read_library", True, "items' data: those named, or a collection's, a tag's"),
    "search": ("read_library", True, "the items a quick search finds"),
    "children": ("read_library", True, "items' attachments and notes, an attachment's annotations"),
    "pdf": ("read_library", True, "where items' PDFs are on disk, best version first"),
    "collections": ("read_library", True, "the collections, with their paths"),
    "tags": ("read_library", True, "the tags, with their item counts"),
    "schema": ("read_library", True, "Zotero's schema: item types, fields, creator types"),
    "ready": ("ready", False, "is Zotero ready for an import; --authorize stores a write key"),
    "draft": ("draft_item", False, "draft records from paper-fetch's results"),
    "prepare": (None, False, "have, then check, over records"),
    "save": (None, False, "create, then attach, over records"),
    "have": ("find_in_library", False, "is a record's paper, or a file, in the library already"),
    "check": ("check_item", False, "check records' drafted items against the schema"),
    "create": ("create_item", False, "create records' items"),
    "attach": ("attach_file", False, "attach records' files to their items"),
    "recognize": ("recognize", False, "send records' PDFs to Zotero's recognizer"),
    "answer": ("answer", False, "record a judge's or the user's answer to a handoff"),
    "report": ("report", False, "what an import did, record by record"),
    "ids": ("read_bib", False, "a .bib's DOIs and arXiv ids with their citation keys"),
    "lint": ("lint_items", False, "flag items' problems: fields, versions, tags, duplicates"),
    "update": ("update_item", False, "change items' fields"),
    "tag": ("file_and_tag", False, "change items' tags and collections"),
    "merge": ("merge_items", False, "merge a duplicate into the item that stays"),
    "trash": ("trash_item", False, "move items to the trash, or restore them"),
    "mkcol": ("make_collection", False, "make a collection"),
    "fill": ("fields_from_results", False, "change lines for fields paper-fetch found"),
    "retitle": ("titles_from_labels", False, "change lines for attachment titles from paper-fetch's labels"),
    "export": ("export_bib", False, "BibTeX keyed by citation key"),
    "note": ("note", False, "notes out of Zotero as Markdown, and back"),
    "convert": ("note_md", False, "note HTML to Markdown, and back"),
    "package": ("structured", False, "PDFs' structured packages: take, put, names"),
    "annotate": ("annotate", False, "boxes on a PDF as Zotero annotations"),
}
STEPS = {"prepare": ("find_in_library", "check_item"), "save": ("create_item", "attach_file")}

PREPARE = """Fill the blocks computed from records: have (found, near_matches), then check (checks).

Each script skips a block that is done, so after any change to a record run prepare again. One line per record:
{slug, code: decide | failed | ok, decide?: [what is still open], failed?: [the words whose line for it is not done],
steps: {word: its code}}. `decide` comes from the record and its result, each entry naming who settles it:
  same_paper      the open handoff's path and waiting_on: judge (it answers with p2z.py answer) | user (a judge
                  answered pair or unknown; the agent records the user's word with p2z.py answer --by user). Several
                  library items carrying the paper's identifier come this way too, as candidates with matched_by
  tags            the paper's tags file (tags/<slug>.json) is not written yet, and its item is still to be created:
                  whoever tags it writes it (references/tagging.md); save creates nothing for the paper until then
  published_versions  a preprint item whose result lists published versions: paper-fetch's pf.py redraft and
                  p2z.py draft --redraft, or keep_preprint with the reason
  checks, warnings    check's flags (mapped:publicationTitle, missing_minimum:date, ...) and draft's warnings that
                  `accepted` does not hold: revise the item, or accept them
  unanswered      sources that did not answer: prepare (for versions, identify) again later; a source that stays
                  silent is accepted by adding "unanswered:<source>" to the record's `accepted`
Exit 0 = nothing to settle; 1 = something is, then stderr's last line is {"summary": {total, ok, decide, failed}}; 2 = a
step could not go on (the next did not run), then stderr's last line is that step's {code, hint}.

Examples:
  p2z.py prepare <scratch>/paper-to-zotero/records/*.json
  ls <scratch>/paper-to-zotero/records/*.json | p2z.py prepare -
"""
SAVE = """Create the records' items, then attach their files: create, then attach.

Each skips what it has done, so save can run after every pass of paper-fetch's fetch. One line per record, as
prepare's: {slug, code: decide | failed | ok, decide?, failed?, steps: {word: its code}}.
Exit 0 = every record saved; 1 = something is to settle or failed, then stderr's last line is {"summary": ...}; 2 = a
step could not go on (the next did not run), then stderr's last line is that step's {code, hint}.

Examples:
  p2z.py save -n <scratch>/paper-to-zotero/records/*.json
  p2z.py save <scratch>/paper-to-zotero/records/*.json
"""
WORD_OF = {script: word for word, (script, _, _) in WORDS.items() if script}


def command(script, *args):
    """The command line that runs scripts/<script>.py: through uv, which loads the script's own dependencies."""
    return ["uv", "run", "--quiet", "--script", str(HERE / f"{script}.py"), *args]


def listing():
    width = max(map(len, WORDS)) + 2
    first, _, rest = __doc__.strip().partition("\n")
    words = "\n".join(f"  {word:<{width}}{text}" for word, (_, _, text) in WORDS.items())
    return f"usage: {SELF} WORD [options] [operands]   ({SELF} WORD -h for each)\n\n{first}\n\nwords:\n{words}\n\n{rest.strip()}\n"


def decisions(rec):
    """What the record leaves for the agent to settle, read from the record and its result."""
    block = lambda name: rec.get(name) if isinstance(rec.get(name), dict) else {}  # noqa: E731
    res = run.result_of(rec)[0] if rec.get("fetched") else {}
    versions = res.get("versions") if isinstance(res.get("versions"), dict) else {}
    accepted, out, still = set(rec.get("accepted") or []), [], set(run.unsettled(rec))
    if still:
        h = run.open_handoff(rec)
        waiting = {k for k, a in run.latest_answers(rec).items() if a.get("answer") in ("pair", "unknown")}
        out.append({"same_paper": h["path"] if h else None, "waiting_on": "user" if h and still <= waiting else "judge"})
    if rec.item and run.item_key(rec) is None and not run.tags_file(rec).exists():
        out.append({"tags": str(run.tags_file(rec))})
    if res.get("record_of") == "preprint" and versions.get("published") and not rec.get("keep_preprint"):
        out.append({"published_versions": len(versions["published"])})
    flags = [f for f in run.check_flags(block("checks")) if f not in accepted]
    if flags:
        out.append({"checks": flags})
    warnings = [w for w in rec.get("warnings") or [] if isinstance(w, str) and w not in accepted]
    if warnings:
        out.append({"warnings": warnings})
    unanswered = sorted({s for name in run.PREPARED for s in block(name).get("incomplete") or []}
                        | set(versions.get("incomplete") or [] if res.get("record_of") == "preprint" else []))
    unanswered = [s for s in unanswered if f"unanswered:{s}" not in accepted]
    if unanswered:
        out.append({"unanswered": unanswered})
    return out


def compound(word, argv):
    """Run the word's scripts in turn over the records -> the exit code."""
    p = cli.parser(PREPARE if word == "prepare" else SAVE, sub=word)
    p.add_argument("records", nargs="*", metavar="RECORD",
                   help="record files: <scratch>/paper-to-zotero/records/*.json; - reads their paths from stdin")
    cli.add_dry_run(p)
    cli.add_base_url(p)
    args = cli.parse(p, argv)
    if not args.records:
        p.error("name the record files, or - to read their paths from stdin")
    paths = cli.paths(args.records)
    if not paths:   # `-` with an empty list: nothing to do
        return cli.OK
    env = {**os.environ, cli.BASE_URL_ENV: args.base_url}   # every script takes it from there
    env.pop(cli.PROG_ENV, None)
    steps, stopped = {Path(path).stem: {} for path in paths}, None
    for script in STEPS[word]:
        done = subprocess.run(command(script, *(["-n"] if args.dry_run else []), *paths), capture_output=True,
                              text=True, env=env)
        name = WORD_OF[script]
        for raw in done.stdout.splitlines():
            try:
                line = json.loads(raw)
            except ValueError:
                continue
            slug = line.get("slug") if isinstance(line, dict) else None
            if slug in steps:
                code = line.get("code")
                steps[slug][name] = f"skipped: {line.get('reason')}" if code == "skipped" else code
                if "hint" in line:  # a script gives a hint only on a line that is not done (cli.tidy)
                    steps[slug].setdefault("_failed", []).append(name)
        for got in steps.values():
            if name not in got and done.returncode:  # the script ended without a line for it
                got[name] = f"exit {done.returncode}"
                got.setdefault("_failed", []).append(name)
        if done.returncode == cli.CANNOT:
            last = (done.stderr.strip().splitlines() or [""])[-1]
            try:
                stopped = json.loads(last)
            except ValueError:
                stopped = {"code": "step_failed", "step": name, "detail": last}
            break
    counts = {"total": len(paths), "ok": 0, "decide": 0, "failed": 0}
    for path in paths:
        slug = Path(path).stem
        try:
            settle = decisions(run.read(path))
        except cli.Stop as stop:
            line = stop.line(slug=slug)
        else:
            failed = steps[slug].pop("_failed", [])
            line = {"slug": slug, "code": "decide" if settle else "failed" if failed else "ok",
                    **({"decide": settle} if settle else {}), **({"failed": failed} if failed else {}), "steps": steps[slug]}
        counts[line["code"] if line["code"] in counts else "failed"] += 1
        cli.emit(line)
    if stopped is not None:
        cli.emit(stopped, sys.stderr)
        return cli.CANNOT
    if counts["decide"] or counts["failed"]:
        cli.emit({"summary": counts}, sys.stderr)
        return cli.ACT
    return cli.OK


def main(argv):
    if argv and argv[0] in ("-h", "--help"):
        cli.write(listing())
        return cli.OK
    word = argv[0] if argv else None
    if word not in WORDS:
        sys.stderr.write(listing())
        cli.emit({"code": "usage", "detail": f"no word {word!r}" if word else "name a word", "hint": f"See {SELF} -h."},
                 sys.stderr)
        return cli.CANNOT
    if word in STEPS:
        return compound(word, argv[1:])
    script, is_command, _ = WORDS[word]
    os.environ[cli.PROG_ENV] = SELF if is_command else f"{SELF} {word}"
    os.execvp("uv", command(script, *([word] if is_command else []), *argv[1:]))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
