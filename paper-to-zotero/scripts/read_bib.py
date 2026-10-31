#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Read .bib files into the lines paper-fetch's identify takes: one per entry, `<identifier><TAB><citation key>`.

  uv run scripts/read_bib.py refs.bib | uv run ../paper-fetch/scripts/pf.py identify -o <scratch>/paper-to-zotero/fetch

The files are the arguments, or the text on stdin. An entry's identifier is its doi, else its arXiv id (eprint with
archivePrefix arXiv, or an arXiv url or "arXiv:" mention in url, journal, howpublished, note); an entry with neither
gives `title:<its title>`, which identify answers with needs_pinning: find the paper's DOI or arXiv id, then identify
it with the key. @comment, @string and @preamble are skipped; no LaTeX is decoded (braces dropped).

stdout: the lines, nothing else. stderr: how many entries, and how many have no identifier.
Exit 0 = read (title: lines included); 1 = a file could not be read or holds no entry; 2 = usage.
"""
import re
import sys
from pathlib import Path

from p2zlib import cli, paper


def bib_close(text, start, close_ch):
    """Index of the delimiter closing an entry body that starts at `start`, nested braces honoured."""
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
    """One field value at pos: {braced}, "quoted" or a bare token, '#' concatenations joined -> (value, pos)."""
    parts, n = [], len(body)
    while True:
        while pos < n and body[pos].isspace():
            pos += 1
        if pos >= n:
            break
        c = body[pos]
        if c in "{\"":
            depth, start = 0, pos + (c == '"')
            pos += c == '"'
            while pos < n:
                if body[pos] == "{":
                    depth += 1
                elif body[pos] == "}":
                    depth -= 1
                    if c == "{" and depth == 0:
                        break
                elif c == '"' and body[pos] == '"' and depth == 0:
                    break
                pos += 1
            parts.append(body[start + (c == "{"):pos])
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


def parse_bib(text):
    """A minimal BibTeX reader: (entry type, key, {field (lower-case): value, braces dropped}); @comment, @string and
    @preamble skipped. No LaTeX decoding: titles and identifiers only."""
    pos = 0
    while (at := text.find("@", pos)) >= 0:
        m = re.match(r"@\s*([A-Za-z]+)\s*([{(])", text[at:])
        if not m:
            pos = at + 1
            continue
        etype, body_start = m.group(1).lower(), at + m.end()
        end = bib_close(text, body_start, "}" if m.group(2) == "{" else ")")
        body, pos = text[body_start:end], end + 1
        if etype in ("comment", "string", "preamble"):
            continue
        key, _, rest = body.partition(",")
        fields, p = {}, 0
        while fm := re.match(r"\s*,?\s*([^\s=,]+)\s*=\s*", rest[p:]):
            value, p = bib_value(rest, p + fm.end())
            fields[fm.group(1).lower()] = re.sub(r"\s+", " ", value.replace("{", "").replace("}", "")).strip()
        yield etype, key.strip(), fields


def bib_identifier(fields):
    """An entry's DOI, else its arXiv id (eprint, or an arXiv url / mention in url, journal, howpublished, note), else None."""
    doi = paper.normalize_doi(fields.get("doi"))
    if doi:
        return doi
    eprint = (fields.get("eprint") or "").strip()
    prefix = (fields.get("archiveprefix") or fields.get("eprinttype") or "").strip().lower()
    m = re.fullmatch(rf"(?:arxiv:)?({paper.ARXIV_ID})(v\d+)?", eprint, flags=re.I)
    if eprint and (prefix == "arxiv" or m):
        return "arXiv:" + (m.group(1) + (m.group(2) or "") if m else eprint)
    for name in ("url", "journal", "howpublished", "note", "eprint"):
        m = re.search(rf"(?:arxiv\.org/(?:abs|pdf)/|arxiv:\s*)({paper.ARXIV_ID})(v\d+)?", fields.get(name) or "", flags=re.I)
        if m:
            return "arXiv:" + m.group(1) + (m.group(2) or "")
    return None


def lines_of(text):
    """The identify lines of a .bib text."""
    out = []
    for _, key, fields in parse_bib(text):
        ident = bib_identifier(fields) or "title:" + (fields.get("title") or "")
        out.append(ident + (f"\t{key}" if key else ""))
    return out


def main(argv=None):
    p = cli.parser(__doc__)
    p.add_argument("bibs", nargs="*", metavar="BIB", help=".bib files (default: the text on stdin)")
    args = p.parse_args(argv)
    code, lines = cli.OK, []
    for name, read in [(b, lambda b=b: Path(b).read_text(encoding="utf-8")) for b in args.bibs] or [("stdin", sys.stdin.read)]:
        try:
            got = lines_of(read())
        except (OSError, UnicodeDecodeError) as e:
            cli.log(f"{name}: cannot read: {e}")
            code = cli.ACT
            continue
        if not got:
            cli.log(f"{name}: no entry")
            code = cli.ACT
        lines += got
    for line in lines:
        print(line)
    pinned = sum(ln.startswith("title:") for ln in lines)
    cli.log(f"{len(lines)} entries" + (f", {pinned} without a DOI or arXiv id (title: lines)" if pinned else ""))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
