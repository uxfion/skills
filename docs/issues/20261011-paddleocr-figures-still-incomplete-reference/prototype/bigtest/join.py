# /// script
# dependencies = []
# ///
"""join.py MODE: one row per graded caption: item id, set, key, page, caption, grader verdict, size, note, and the
detector's raw signals (MODE = layer | nolayer). Controls are left out."""
import csv, glob, sys
mode = sys.argv[1]
items = {}
for l in open("grade/items.tsv"):
    iid, s, k, p, c, t = l.rstrip("\n").split("\t")
    items[iid] = dict(id=iid, set=s, key=k, page=int(p), caption=int(c), text=t)
ctl = {l.split("\t")[0] for l in open("grade/controls.tsv")}
grades = {}
for f in sorted(glob.glob("grade/out/*.tsv")):
    for r in csv.DictReader(open(f), delimiter="\t"):
        if r["id"] in ctl or r["id"] not in items:
            continue
        grades[r["id"]] = r
det = {}
for f in glob.glob(f"det_*_{mode}.tsv"):
    for r in csv.DictReader(open(f), delimiter="\t"):
        det[(r["set"], r["key"], int(r["page"]), int(r["caption"]))] = r
w = csv.writer(open(f"joined_{mode}.tsv", "w"), delimiter="\t")
cols = ["warn_uncropped", "ncrops", "second_has_box", "d_top", "d_bottom", "d_left", "d_right"]
w.writerow(["id", "set", "key", "page", "caption", "verdict", "size", "note", *cols, "text"])
n = 0
for iid, it in items.items():
    g = grades.get(iid)
    if not g:
        continue
    d = det[(it["set"], it["key"], it["page"], it["caption"])]
    w.writerow([iid, it["set"], it["key"], it["page"], it["caption"], g["verdict"], g["size"], g["note"], *[d[c] for c in cols], it["text"][:60]])
    n += 1
print(n, "graded captions joined")
