#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["markdown-it-py==3.0.0", "mdit-py-plugins==0.6.1", "mdit-py-cjk-friendly==0.3.0"]
# ///
"""Convert Zotero notes between their HTML and Markdown, both ways, losing nothing: a filter, no Zotero needed.

  -t md     note HTML -> Markdown. The front matter carries the note's wrapper (schema, citation-items); everything
            the subset cannot say stays HTML inside the Markdown.
  -t note   Markdown -> note HTML, wrapper rebuilt from the front matter; the front matter's other keys are dropped
            (note.py put is what reads them).

Input: the paths given, or stdin (no path, or -). Output: stdout (one input); -o FILE (one input); -o DIR/ (an
existing directory, or a path ending in /, made if absent): each input with its last extension changed, x.html ->
DIR/x.md, x.md -> DIR/x.html. Writing over an existing file, stdin into a directory, or two inputs onto one name
are usage errors. UTF-8, \\n line ends.

The subset written as Markdown, and what the check means, are in p2zlib/note_md.py. stderr: nothing, except one line
per block the check kept as HTML ("FILE: block N: <tag> kept as HTML"), and errors.
Exit 0 = every input converted; 1 = an input could not be read or converted (the others are); 2 = usage error.

Examples:
  uv run scripts/note_md.py -t md note.html
  uv run scripts/note_md.py -t md note.html -o note.md
  cat note.html | uv run scripts/note_md.py -t md > note.md
  uv run scripts/note_md.py -t note notes/*.md -o out/
"""
import sys
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
    p.add_argument("inputs", nargs="*", metavar="INPUT", help="files to convert (none, or -: stdin)")
    p.add_argument("-t", "--to", required=True, choices=("md", "note"), help="md: note HTML -> Markdown; note: back")
    p.add_argument("-o", "--out", metavar="OUT", help="a file (one input) or a directory/ (default: stdout)")
    args = p.parse_args(argv)
    inputs = args.inputs or ["-"]
    out, into_dir = cli.output(p, args.out, len(inputs))
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
    code = cli.OK
    for name, target in zip(inputs, targets):
        try:
            text = sys.stdin.read() if name == "-" else Path(name).read_text(encoding="utf-8")
            result, kept = convert(text, args.to)
        except (OSError, UnicodeDecodeError, ValueError) as e:
            cli.log(f"{name}: {e}")
            code = cli.ACT
            continue
        for n, tag in kept:
            cli.log(f"{'stdin' if name == '-' else name}: block {n}: <{tag}> kept as HTML")
        if target is None:
            sys.stdout.write(result)
        else:
            target.write_text(result, encoding="utf-8", newline="\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
