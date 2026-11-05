#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["markdown-it-py==3.0.0", "mdit-py-plugins==0.6.1", "mdit-py-cjk-friendly==0.3.0"]
# ///
"""Convert Zotero notes between their HTML and Markdown, both ways, losing nothing: a filter, no Zotero needed.

  -t md     note HTML -> Markdown. The front matter carries the note's wrapper (schema, citation-items); everything
            the subset cannot say stays HTML inside the Markdown.
  -t note   Markdown -> note HTML, wrapper rebuilt from the front matter; the front matter's other keys are dropped
            (p2z.py note put is what reads them).

Input: the files after the options (- reads one from stdin). Output: stdout (one input); -o FILE (one input); -o
DIR/ (an existing directory, or a path ending in /, made if absent): each input with its last extension changed,
x.html -> DIR/x.md, x.md -> DIR/x.html. Writing over an existing file, stdin into a directory, or two inputs onto one
name are usage errors. UTF-8, \\n line ends.

The subset written as Markdown, and what the check means, are in p2zlib's note_md module. stderr: nothing, except one
line per block the check kept as HTML ("FILE: block N: <tag> kept as HTML").
Exit 0 = every input converted; 1 = an input could not be read or converted (the others are): a JSON line on stderr
for each, {file, code: file_not_found | not_converted, detail?}, then {"summary": {total, failed}} last; 2 = usage
error, then stderr's last line is {code, hint}.

Examples:
  p2z.py convert -t md note.html
  p2z.py convert -t md note.html -o note.md
  cat note.html | p2z.py convert -t md - > note.md
  p2z.py convert -t note notes/*.md -o out/
"""
from pathlib import Path

from p2zlib import cli, note_md


def convert(text, to):
    """-> (output text, the blocks kept as HTML)."""
    if to == "md":
        kept = []
        return note_md.to_md(text, fallbacks=kept), kept
    return note_md.to_note(text)[0] + "\n", []


def main(argv=None):
    p = cli.parser(__doc__)
    p.add_argument("inputs", nargs="*", metavar="FILE", help="files to convert; - reads one from stdin")
    p.add_argument("-t", "--to", required=True, choices=("md", "note"), help="md: note HTML -> Markdown; note: back")
    p.add_argument("-o", "--output", metavar="FILE|DIR/", help="a file (one input) or a directory/ (default: stdout)")
    args = cli.parse(p, argv)
    inputs = args.inputs
    if not inputs:
        p.error("name the files to convert, or - to read one from stdin")
    out, into_dir = cli.output(p, args.output, len(inputs))
    stdin = "-" in inputs
    if into_dir and stdin:
        p.error("stdin has no name to write into a directory: give -o FILE, or no -o")
    ext = ".md" if args.to == "md" else ".html"
    targets = [out / Path(i).with_suffix(ext).name if into_dir else out for i in inputs]
    if into_dir and len(set(targets)) < len(targets):
        p.error("two inputs would write the same file: " + ", ".join(sorted({str(t) for t in targets if targets.count(t) > 1})))
    taken = [str(t) for t in targets if t is not None and t.exists()]
    if taken:
        p.error("will not write over existing files: " + ", ".join(taken))
    problems = []
    for name, target in zip(inputs, targets):
        try:
            result, kept = convert(cli.document(name), args.to)
        except cli.Stop as stop:
            problems.append(stop.line(file=name))
            continue
        except ValueError as e:
            problems.append({"file": name, "code": "not_converted", "detail": str(e)})
            continue
        for n, tag in kept:
            cli.log(f"{'stdin' if name == '-' else name}: block {n}: <{tag}> kept as HTML")
        if target is None:
            cli.write(result)
        else:
            target.write_text(result, encoding="utf-8", newline="\n")
    return cli.summarize(len(inputs), len(problems), problems=problems)


if __name__ == "__main__":
    raise SystemExit(main())
