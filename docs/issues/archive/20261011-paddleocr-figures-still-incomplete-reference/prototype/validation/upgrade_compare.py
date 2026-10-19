# compare.py BIG SLIM VAL: the implemented figure check against the stage-4 grades and the stage-5 prototype flags.
import csv, glob, json, sys
from collections import Counter
B, S, V = sys.argv[1:4]
items = {l.split("\t")[0]: tuple(l.rstrip("\n").split("\t")[1:5]) for l in open(f"{B}/grade/items.tsv")}
graded = {r["id"]: r for r in csv.DictReader(open(f"{B}/final_in_ho_new_layer.tsv"), delimiter="\t")}
tier = {i: 0 if i == "g699p" else int(r["defined_tier"]) for i, r in graded.items()}
def load(pat):
    out = {}
    for f in glob.glob(pat):
        for r in csv.DictReader(open(f), delimiter="\t"):
            out[(r["set"], r["key"], r["page"], r["caption"])] = r
    return out
sig, two = load(f"{B}/sig_*.tsv"), load(f"{B}/two_*.tsv")
edge = {r["id"]: r for r in csv.DictReader(open(f"{S}/edge_flags.tsv"), delimiter="\t")}
det = load(f"{B}/det_*_layer.tsv")
proto = {}
for i, k in items.items():
    if i not in tier: continue
    d, x = det[k], sig[k]
    f = set()
    if d["warn_uncropped"] == "1": f.add("no_crop")
    if int(d["ncrops"]) >= 2: f.add("split")
    if edge[i]["s8_layer"] == "1": f.add("second_opinion")
    if x["table"] == "1": f.add("table")
    if max(int(x[c]) for c in ("cut_top", "cut_bottom", "cut_left", "cut_right")) >= 3: f.add("edge_cut")
    if two[k]["twofig"]: f.add("two_figures")
    proto[i] = f
new, summaries = {}, {}
for s in ("in", "ho", "new"):
    for l in open(f"{V}/{s}.jsonl"):
        d = json.loads(l)
        key = d["input"].rsplit("/", 1)[-1][:-4]
        summaries[(s, key)] = d
        for w in d.get("warnings", []):
            if w["code"] == "figure_check":
                new[(s, key, str(w["page"]), str(w["block"]))] = {r.split(":")[0] for r in w["reasons"]}
impl = {i: new.get(items[i], set()) for i in proto}
for name, fl in (("prototype (stage 5)", proto), ("implementation", impl)):
    n = {t: [i for i in fl if tier[i] == t] for t in (0, 1, 2)}
    print(f"{name:<22} severe {sum(bool(fl[i]) for i in n[1])}/{len(n[1])}  minor {sum(bool(fl[i]) for i in n[2])}/{len(n[2])}  "
          f"good sent {sum(bool(fl[i]) for i in n[0])}/{len(n[0])}")
print("missed severe:", [i for i in impl if tier[i] == 1 and not impl[i]])
diff = Counter()
rows = []
for i in proto:
    for r in proto[i] ^ impl[i]:
        side = "proto only" if r in proto[i] else "impl only"
        diff[(r, side)] += 1
        rows.append((i, *items[i], tier[i], r, side))
for k, v in sorted(diff.items()): print(k, v)
with open(f"{V}/diff.tsv", "w") as o:
    o.write("id\tset\tkey\tpage\tcaption\ttier\treason\tside\n")
    for r in rows: o.write("\t".join(map(str, r)) + "\n")
extra = [(k, v) for k, v in new.items() if k not in {items[i] for i in proto}]
print("flags on captions outside the graded set:", len(extra), Counter(r for _, v in extra for r in v))
print("errors:", [(k, d.get("figures_check") or d.get("error")) for k, d in summaries.items() if d.get("figures_check") or d.get("error")])
print("figures_checked:", sum(1 for d in summaries.values() if d.get("figures_checked")), "of", len(summaries))
