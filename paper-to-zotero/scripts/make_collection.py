#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Create a Zotero collection by name under an optional parent, once: a rerun finds the one already there.

Reads the live collection tree (a collection in the trash, and every collection under one, left out) and looks for
the same name under the same parent (the top level without --parent). None there: POST {name, parentCollection},
then read the new collection back. Run again, it finds that collection, so it never makes a second copy.

stdout: one line {key, code, name, parent, path, ...}; `path` joins the names from the root with "/".
  ok                 created and read back (`version`); --dry-run: would be created, key null
  skipped            reason exists: the collection is already there, `key` is it
  ambiguous          several collections of this name under that parent (`keys`); the user decides which stays
  parent_not_found   no live collection has the --parent key (it may be in the trash); take it from ready.py's tree
  invalid_name       --name is blank
  write_denied       the library is not editable
  write_failed       Zotero did not create it; see status and detail
  readback_mismatch  created, but it reads back with another name or parent; look at it in Zotero
Exit 0 = ok or skipped, 1 = any other code, 2 = cannot check (zotero_unreachable, local_api_disabled, no_key,
key_rejected, server_mismatch).

Examples:
  uv run scripts/make_collection.py --name "Mean Flow" --parent SV9NEBPJ --dry-run
  uv run scripts/make_collection.py --name "投稿文献"
"""
from p2zlib import cli, zotero


def make(args):
    name, parent = args.name.strip(), args.parent
    if not name:
        raise cli.Stop("invalid_name", hint="--name must not be blank.")
    zot = zotero.Zotero(args.base_url)
    if not args.dry_run:
        zot.write_headers()
    tree = zot.collections()
    if parent and parent not in tree:
        raise cli.Stop("parent_not_found", hint="No live collection has this key (it may be in the trash); take the key "
                       "from ready.py's tree.", name=name, parent=parent)
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
    p.add_argument("--name", required=True, help="the collection's name (an exact match counts as already there)")
    p.add_argument("--parent", metavar="KEY", help="the parent collection's key; without it, the top level")
    p.add_argument("--dry-run", action="store_true", help="look for it and check the parent; create nothing")
    cli.add_base_url(p)
    args = p.parse_args(argv)
    if args.parent is not None and not cli.KEY_RE.match(args.parent):
        p.error("--parent takes an 8-character collection key")

    def run():
        cli.emit(make(args))
        return cli.OK

    return cli.run(run)


if __name__ == "__main__":
    raise SystemExit(main())
