#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Create a Zotero collection, once: `p2z.py mkcol PARENT/NAME` (or a NAME alone, at the top level); a rerun finds the one already there.

What follows the options is the new collection's path: its last part is the new name, what comes before it is the
parent, found as everywhere else (a key, a path from p2z.py collections, or a name one collection has). The live
collection tree is read (a collection in the trash, and every collection under one, left out) and the name looked
for under that parent. None there: POST {name, parentCollection}, then read the new collection back. Run again, it
finds that collection, so it never makes a second copy. A name with "/" in it cannot be made here.

stdout: one line {key, code, name, parent, path, ...}; `path` joins the names from the root with "/".
  ok                    created and read back (`version`); -n: would be created, key null
  skipped               reason exists: the collection is already there, `key` is it
  ambiguous             several collections of this name under that parent (`keys`): the user decides which stays;
                        or the parent named answers to several collections (`candidates`)
  collection_not_found  no live collection is the parent named (it may be in the trash)
  invalid_name          the new name is blank
  write_denied          the library is not editable
  write_failed          Zotero did not create it; see status and detail
  readback_mismatch     created, but it reads back with another name or parent; look at it in Zotero
Exit 0 = ok or skipped; 1 = any other code; 2 = cannot check (zotero_unreachable, local_api_disabled, no_key,
key_rejected, server_mismatch), then stderr's last line is {code, hint}.

Examples:
  p2z.py mkcol -n "自然图像/Mean Flow"
  p2z.py mkcol 投稿文献
"""
from p2zlib import cli, zotero


def make(args):
    parent_name, _, name = args.path.strip().rpartition("/")
    name = name.strip()
    if not name:
        raise cli.Stop("invalid_name", hint="Name the new collection: PARENT/NAME or NAME.", path=args.path)
    zot = zotero.Zotero(args.base_url)
    if not args.dry_run:
        zot.write_headers()
    tree = zot.collections()
    parent = zot.collection(parent_name.strip(), tree) if parent_name.strip() else None
    path = f"{tree[parent]['path']}/{name}" if parent else name
    same = sorted(k for k, c in tree.items() if c["name"] == name and c["parent"] == parent)
    if len(same) > 1:
        raise cli.Stop("ambiguous", hint="Several collections of this name sit under that parent; the user decides which stays.",
                       keys=same, name=name, parent=parent, path=path)
    line = {"name": name, "parent": parent, "path": path}
    if same:
        return {"key": same[0], **cli.skipped("exists", **line)}
    if args.dry_run:
        return {"key": None, **cli.ok(**line, dry_run=True)}
    key = zot.create_collection(name, parent)
    back = zot.get(f"{zotero.LIB}/collections/{key}", allow_404=True)
    d = zotero.data(back)
    if back is None or d.get("name") != name or (d.get("parentCollection") or None) != parent:
        raise cli.Stop("readback_mismatch", hint="The collection was created, but it reads back differently; look at it in Zotero.",
                       key=key, name=name, parent=parent, read_back={f: d.get(f) for f in ("name", "parentCollection")})
    return {"key": key, **cli.ok(**line, version=back.get("version"))}


def main(argv=None):
    p = cli.parser(__doc__)
    p.add_argument("path", metavar="[PARENT/]NAME", help="the new collection: its parent's key, path or name, then its name")
    cli.add_dry_run(p, help="look for it and check the parent; create nothing")
    cli.add_base_url(p)
    args = cli.parse(p, argv)

    def run():
        cli.emit(make(args))
        return cli.OK

    return cli.run(run)


if __name__ == "__main__":
    raise SystemExit(main())
