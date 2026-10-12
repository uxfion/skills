# /// script
# dependencies = []
# ///
"""final.py SETS MODE: per set group, the triage numbers.
Severity two ways: 'grader' = the blind grader's own words (none, split or size large = severe; small = minor);
'defined' = SEVERE.md applied by me (overrides.tsv). Detectors:
  G1 / G3 = existing uncropped warning + split + second opinion differs by > 1 / > 3 text rows on a side;
  +T = also the table-pairing check; +C = also the edge-cut check (>= 3 ink components across one side)."""
import csv, glob, sys
sets, mode = sys.argv[1].split(","), sys.argv[2]
items = {}
for l in open("grade/items.tsv"):
    iid, s, k, p, c, t = l.rstrip("\n").split("\t")
    items[iid] = (s, k, p, c, t)
ctl = {l.split("\t")[0] for l in open("grade/controls.tsv")}
grades = {}
for f in glob.glob("grade/out/*.tsv"):
    for r in csv.DictReader(open(f), delimiter="\t"):
        if r["id"] in items and r["id"] not in ctl:
            grades[r["id"]] = r
det, sig = {}, {}
for f in glob.glob(f"det_*_{mode}.tsv"):
    for r in csv.DictReader(open(f), delimiter="\t"):
        det[(r["set"], r["key"], r["page"], r["caption"])] = r
for f in glob.glob("sig_*.tsv"):
    for r in csv.DictReader(open(f), delimiter="\t"):
        sig[(r["set"], r["key"], r["page"], r["caption"])] = r
ov = {}
for l in open("overrides.tsv"):
    if l.startswith("#") or not l.strip(): continue
    i, t, w = l.rstrip("\n").split("\t", 2); ov[i] = int(t)
def grader_tier(g):
    if g["verdict"] in ("ok", "nofig", "unsure", "unread"): return 0
    return 1 if g["verdict"] in ("none", "split") or g["size"] == "large" else 2
rows = []
for iid, (s, k, p, c, t) in items.items():
    if s not in sets or iid not in grades: continue
    g = grades[iid]; d = det[(s, k, p, c)]; x = sig[(s, k, p, c)]
    rows.append(dict(id=iid, set=s, key=k, page=p, text=t, verdict=g["verdict"], size=g["size"], note=g["note"],
                     gt=grader_tier(g), dt=ov.get(iid, grader_tier(g)), d=d, x=x))
def flags(r, thr, T=False, C=False):
    d, x, out = r["d"], r["x"], []
    if d["warn_uncropped"] == "1": out.append("uncropped")
    if int(d["ncrops"]) >= 2: out.append("split")
    if d["d_top"] != "" and max(abs(float(d[k])) for k in ("d_top", "d_bottom", "d_left", "d_right")) > thr: out.append("edge")
    if T and x["table"] == "1": out.append("table")
    if C and max(int(x[k]) for k in ("cut_top", "cut_bottom", "cut_left", "cut_right")) >= 3: out.append("cut")
    return out
n = len(rows)
print(f"== sets {sets}, second opinion {mode}: {n} captions graded")
for name, key in (("grader's own severity", "gt"), ("defined severity", "dt")):
    t1 = [r for r in rows if r[key] == 1]; t2 = [r for r in rows if r[key] == 2]; t0 = [r for r in rows if r[key] == 0]
    print(f"-- {name}: severe {len(t1)}, minor {len(t2)}, fine {len(t0)}")
    for label, thr, T, C in (("existing check only", 1e9, False, False), ("G1", 1, False, False), ("G3", 3, False, False),
                             ("G3+T", 3, True, False), ("G1+T", 1, True, False), ("G3+T+C", 3, True, True), ("G1+T+C", 1, True, True)):
        if label == "existing check only":
            fl = lambda r: ["uncropped"] if r["d"]["warn_uncropped"] == "1" else []
        else:
            fl = lambda r, thr=thr, T=T, C=C: flags(r, thr, T, C)
        f = [r for r in rows if fl(r)]
        print(f"  {label:<20} to agent {len(f):>4} ({100*len(f)/n:4.1f}%)  severe caught {sum(1 for r in t1 if fl(r))}/{len(t1)}"
              f"  minor caught {sum(1 for r in t2 if fl(r))}/{len(t2)}  fine sent {sum(1 for r in t0 if fl(r))}")
        if label in ("G3+T", "G1+T+C"):
            for r in t1:
                if not fl(r):
                    print(f"      severe missed: {r['id']} {r['key'][:28]} p{r['page']} {r['verdict']}/{r['size']}: {r['note'][:80]}")
csv.writer(open(f"final_{'_'.join(sets)}_{mode}.tsv", "w"), delimiter="\t").writerows(
    [["id", "set", "key", "page", "verdict", "size", "grader_tier", "defined_tier", "flags_G1+T+C", "note", "text"]] +
    [[r["id"], r["set"], r["key"], r["page"], r["verdict"], r["size"], r["gt"], r["dt"], ",".join(flags(r, 1, True, True)), r["note"], r["text"]] for r in rows])
