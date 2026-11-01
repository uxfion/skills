#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Answer a handoff: the one way a judge's or the user's conclusion reaches a record.

  p2z.py answer HANDOFF ANSWER [--key K ...] [--reason R] [--by WHO]

HANDOFF is the handoff's file (<scratch>/paper-to-zotero/handoffs/<id>.json, as prepare, find_in_library and
create_item print it). A same_paper handoff asks whether library items (its `candidates`, each with its evidence)
are the paper its record describes (`paper`):
  same --key K          K is this paper: the record's same_as (the import goes on with that item)
  distinct [--key K]    other papers: added to the record's distinct_from; without --key, every candidate of the
                        handoff still open
  pair --key K          K and this paper are a preprint and its published version, or the same paper in two items
                        of different kinds: the user's call
  unknown --key K       cannot tell from the evidence: the user's call
pair and unknown leave the candidate open, kept in the handoff's `answered`; prepare then lists the record as
waiting on the user, and the user's word is recorded the same way (same or distinct, --by user). Every answer goes
into `answered` ({key, answer, reason, by, at}). Then run p2z.py prepare again.

stdout: one line {id, code: ok, answer, keys, record, open: [keys still open]}, or a refusal {id, code, hint}:
bad_answer, no_such_handoff, not_open (nothing in it is open any more), no_such_key (not one of its candidates),
one_key (same names exactly one item), no_key (pair and unknown name the items). Exit 0 = recorded; 1 = refused.

Examples:
  uv run scripts/answer.py <scratch>/paper-to-zotero/handoffs/he2020mask.1.json distinct --reason "other papers: another task and venue" --by judge
  uv run scripts/answer.py <scratch>/paper-to-zotero/handoffs/liu2022jbhi.1.json same --key ABCD1234 --reason "same title, authors and year; the library item lacks the DOI" --by judge
"""
import json
from pathlib import Path

from p2zlib import cli, run

BY = ("agent", "judge", "user")


def answer(path, word, keys, reason, by):
    try:
        handoff = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise cli.Stop("no_such_handoff", hint="Give the handoff's file as prepare printed it.") from None
    hid, kind = handoff.get("id"), handoff.get("kind")
    if word not in run.ANSWERS.get(kind, ()):
        raise cli.Stop("bad_answer", id=hid, hint=f"A {kind} handoff takes one of: {', '.join(run.ANSWERS.get(kind, ()))}.")
    rec = run.read(handoff["record"])
    candidates = [c.get("key") for c in handoff.get("candidates") or []]
    still = [k for k in run.unsettled(rec) if k in candidates]
    if not still:
        raise cli.Stop("not_open", id=hid, hint="Nothing in this handoff is open any more: run p2z.py prepare, which "
                                                "prints the open ones.")
    unknown = [k for k in keys if k not in candidates]
    if unknown:
        raise cli.Stop("no_such_key", id=hid, keys=unknown, hint=f"Name candidates of this handoff: {', '.join(candidates)}.")
    if word == "same" and len(keys) != 1:
        raise cli.Stop("one_key", id=hid, hint="same names exactly one item: --key K.")
    if word in ("pair", "unknown") and not keys:
        raise cli.Stop("no_key", id=hid, hint=f"{word} names the items it is about: --key K.")
    keys = keys or still
    if word == "same":
        rec["same_as"] = keys[0]
        rec["distinct_from"] = [k for k in rec.keys_of("distinct_from") if k != keys[0]]
    elif word == "distinct":
        rec["distinct_from"] = list(dict.fromkeys(rec.keys_of("distinct_from") + keys))
    rec.save()
    handoff["answered"] = list(handoff.get("answered") or []) + [
        {"key": k, "answer": word, "reason": reason, "by": by, "at": run.now_iso()} for k in keys]
    run.atomic_write(path, json.dumps(handoff, ensure_ascii=False, indent=2) + "\n")
    return {"id": hid, "code": "ok", "answer": word, "keys": keys, "record": str(rec.path),
            "open": [k for k in run.unsettled(rec) if k in candidates]}


def main(argv=None):
    p = cli.parser(__doc__)
    p.add_argument("handoff", metavar="HANDOFF", help="the handoff's file")
    p.add_argument("answer", metavar="ANSWER", help="same | distinct | pair | unknown")
    p.add_argument("--key", action="append", default=[], metavar="K", help="a candidate's item key (repeatable, or comma-separated)")
    p.add_argument("--reason", help="what the answer rests on")
    p.add_argument("--by", choices=BY, default="agent", help="who answers (default agent)")
    args = p.parse_args(argv)
    keys = [k.strip() for v in args.key for k in v.split(",") if k.strip()]

    def go():
        cli.emit(answer(Path(args.handoff), args.answer, keys, args.reason, args.by))
        return cli.OK

    return cli.run(go)


if __name__ == "__main__":
    raise SystemExit(main())
