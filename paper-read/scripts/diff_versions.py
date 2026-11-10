#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Compare two versions of a paper section by section, or any two pieces of text: where their words differ.

OLD and NEW are each a structured package's folder, a Markdown file or a text file. Text with headings is cut into
sections at them, and a section of OLD is compared with the section of NEW under the same heading, its numbering
aside ("II. RELATED WORK", "2 Related work"); text without headings is one section. Two sections the headings did not
pair, a caption that moved, a reference list in another style: put each piece in a file and compare the two files.

A word is a run of letters and digits, a number with its points and commas ("1,067", "91.2"), compared lowercased
with LaTeX commands dropped, so spacing, case, punctuation and a formula's spelling make no difference; the places are
printed as the texts have them. The lines are the facts only. Whether a difference is the parse's misreading, the typesetting, or the paper's content is
the reader's to judge, with the PDF where a number is at stake.

stdout: one JSON line per section, OLD's order, then NEW's sections without a partner.
  same      {section, code, words}
  differs   {section, code, old_words, new_words, only_old, only_new, places: [{old, new}]}: only_old and only_new
            count the words on one side alone; places are the first 8, each side cut at 160 characters (-a: every
            place, whole); new_section when NEW's heading reads otherwise
  only_old  {section, code, words}: no section of NEW under this heading
  only_new  {section, code, words}: no section of OLD under this heading
Exit 0 = every section the same; 1 = some line is not `same`; 2 = cannot go on (a path that is no file or folder, a
folder without its Markdown, a usage error): stderr's last line is {code, hint}.

Examples:
  pr.py diff <scratch>/kim2024.Accepted-arXiv-v3 <scratch>/kim2024.Published-ICLR | jq -c 'select(.code != "same")'
  pr.py diff old-datasets.txt new-datasets.txt
"""
import difflib
import re
import sys
import unicodedata
from pathlib import Path

from check_quotes import COMMENT, LATEX, TAG
from prlib import cli

PLACES, PLACE_CHARS = 8, 160
HEADING = re.compile(r"^#{1,6}\s+(.*\S)\s*$")
IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
# A heading's own number: "3", "3.1.", "IV.", "A.", "B)"; a lone letter or roman numeral only before a point or bracket.
NUMBER = re.compile(r"^\s*(?:\d+(?:\.\d+)*[.)]?|[IVXLC]+[.)]|[A-Z][.)])\s+")
WORD = re.compile(r"\d+(?:[.,]\d+)+|[^\W_]+")   # as check_quotes.canon keeps them: a point or comma between digits stays


def text_of(path):
    """The text to compare: a file as it is, or a package folder's Markdown (<folder>/<folder's name>.md)."""
    p = Path(path)
    if p.is_dir():
        md = p / f"{p.name}.md"
        if not md.is_file():
            raise cli.Stop("no_markdown", exit=cli.CANNOT, path=str(p),
                           hint=f"A package folder holds <name>/<name>.md; {p.name}.md is not in this one.")
        p = md
    if not p.is_file():
        raise cli.Stop("file_not_found", exit=cli.CANNOT, path=str(path), hint="Name a package folder or a text file.")
    return p.read_text(encoding="utf-8", errors="replace")


def words_of(text):
    """[(the word lowercased, its start, its end)] in `text`."""
    return [(m.group().lower(), m.start(), m.end()) for m in WORD.finditer(text)]


def sections(text):
    """[(heading, the section's text, its words)], in order; the text before the first heading is "(start)", and text
    without headings is that one section. Markup that is not the paper's words is dropped."""
    text = unicodedata.normalize("NFKC", IMAGE.sub(" ", COMMENT.sub(" ", text)))
    out, name, lines = [], "(start)", []
    for line in [*text.splitlines(), None]:
        m = HEADING.match(line) if line is not None else None
        if m or line is None:
            body = LATEX.sub(" ", TAG.sub(" ", " ".join(lines)))
            out.append((name, body, words_of(body)))
            name, lines = (m.group(1), []) if m else (None, [])
        else:
            lines.append(line)
    return [s for s in out if s[2]]


def key(heading):
    return "".join(w for w, _, _ in words_of(LATEX.sub(" ", NUMBER.sub("", heading))))


def printed(body, words):
    """The stretch of a section's text that these words span, on one line."""
    return " ".join(body[words[0][1]:words[-1][2]].split()) if words else ""


def compare(old, new, every=False):
    """The differs fields of two sections (text, words), or None when their words are the same."""
    (old_body, old), (new_body, new) = old, new
    a, b = [w for w, _, _ in old], [w for w, _, _ in new]
    places, only_old, only_new = [], 0, 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        only_old, only_new = only_old + i2 - i1, only_new + j2 - j1
        if every or len(places) < PLACES:
            side = [printed(old_body, old[i1:i2]), printed(new_body, new[j1:j2])]
            places.append(dict(zip(("old", "new"), side if every else [s[:PLACE_CHARS] for s in side])))
    if not places:
        return None
    return {"old_words": len(a), "new_words": len(b), "only_old": only_old, "only_new": only_new, "places": places}


def lines(old_text, new_text, every=False):
    old, new = sections(old_text), sections(new_text)
    waiting = {}   # heading key -> NEW's sections under it, in order
    for n, (name, _, _) in enumerate(new):
        waiting.setdefault(key(name), []).append(n)
    taken = set()
    for name, body, words in old:
        partners = waiting.get(key(name)) or []
        if not partners:
            yield {"section": name, "code": "only_old", "words": len(words)}
            continue
        n = partners.pop(0)
        taken.add(n)
        other, their_body, theirs = new[n]
        found = compare((body, words), (their_body, theirs), every)
        renamed = {"new_section": other} if other != name else {}
        if found is None:
            yield {"section": name, **renamed, "code": "same", "words": len(words)}
        else:
            yield {"section": name, **renamed, "code": "differs", **found}
    for n, (name, _, words) in enumerate(new):
        if n not in taken:
            yield {"section": name, "code": "only_new", "words": len(words)}


def main(argv=None):
    p = cli.parser(__doc__)
    p.add_argument("old", metavar="OLD", help="the earlier version: a package folder, or a Markdown or text file")
    p.add_argument("new", metavar="NEW", help="the later version, the same way")
    p.add_argument("-a", "--all", action="store_true", help="every differing place of a section, whole")
    args = cli.parse(p, argv)

    def run():
        code = cli.OK
        for line in lines(text_of(args.old), text_of(args.new), args.all):
            cli.emit(line)
            if line["code"] != "same":
                code = cli.ACT
        return code

    return cli.run(run)


if __name__ == "__main__":
    sys.exit(main())
