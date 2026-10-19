"""score.py FRESH: the fresh batch's grades against the implemented figure check."""
import csv, glob, json, sys
from collections import Counter
S = sys.argv[1]
items = {r[0]: r for r in (l.rstrip("\n").split("\t") for l in open(f"{S}/grade/items.tsv"))}
ctl = {r[0]: r for r in (l.rstrip("\n").split("\t") for l in open(f"{S}/grade/controls.tsv"))}
grades = {}
for f in sorted(glob.glob(f"{S}/grade/out/*.tsv")):
    for r in csv.DictReader(open(f), delimiter="\t"):
        grades[r["id"]] = r
ov = {}
try:
    for l in open(f"{S}/grade/overrides.tsv"):
        if l.strip() and not l.startswith("#"):
            i, t, why = l.rstrip("\n").split("\t", 2); ov[i] = int(t)
except FileNotFoundError:
    pass
print("controls:", [(c, ctl[c][2], grades[c]["verdict"], grades[c]["size"]) for c in ctl if c in grades])
flags = {}
for jp in glob.glob(f"{S}/out/*/*.json"):
    k = jp.split("/")[-1][:-5]
    for w in json.load(open(jp))["warnings"]:
        if w["code"] == "figure_check":
            flags[(k, str(w["page"]), str(w["block"]))] = w["reasons"]
def tier(g):
    if g["verdict"] in ("ok", "nofig", "unsure", "unread"): return 0
    return 1 if g["verdict"] in ("none", "split") or g["size"] == "large" else 2
rows = []
for i, (iid, k, p, c, two, text) in items.items():
    if iid not in grades: continue
    g = grades[iid]
    t = ov.get(iid, tier(g))
    fl = flags.get((k, p, c), [])
    rows.append((iid, k, p, c, g["verdict"], g["size"], tier(g), t, ";".join(r.split(":")[0] for r in fl), g["note"]))
for scope, keep in (("all", lambda r: True), ("PDFs", lambda r: not r[1].endswith("_scan")), ("page images", lambda r: r[1].endswith("_scan"))):
    rs = [r for r in rows if keep(r)]
    n = {t: [r for r in rs if r[7] == t] for t in (0, 1, 2)}
    print(f"{scope:<12} captions {len(rs)}  severe {sum(bool(r[8]) for r in n[1])}/{len(n[1])}  minor {sum(bool(r[8]) for r in n[2])}/{len(n[2])}  "
          f"good passed {sum(not r[8] for r in n[0])}/{len(n[0])}  to agent {sum(bool(r[8]) for r in rs)}")
print("\nsevere or minor not reported:")
for r in rows:
    if r[7] in (1, 2) and not r[8]: print(" ", r[0], r[1][:28], "p" + r[2], r[4], r[5], "tier", r[7], "|", r[9][:80])
print("\ngraded severe/minor (all), with flags:")
for r in rows:
    if r[6] or r[7]: print(" ", r[0], r[1][:28], "p" + r[2], f"{r[4]}/{r[5]}", "grader", r[6], "defined", r[7], "|", r[8], "|", r[9][:60])
print("\nwhich checks fired:", Counter(f for r in rows for f in r[8].split(";") if f))
with open(f"{S}/graded.tsv", "w") as o:
    o.write("id\tkey\tpage\tcaption\tverdict\tsize\tgrader_tier\tdefined_tier\tflags\tnote\n")
    for r in rows: o.write("\t".join(map(str, r)) + "\n")
