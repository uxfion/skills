# /// script
# dependencies = []
# ///
"""eval_all.py BIG SLIMDIR: option G's recommended configuration (1 row + table + cut + two figures) with each version
of the second opinion, against the stage-4 grades. g699p is a grader error (two separate crops read as one box) and
counts as a good figure. Writes edge_flags.tsv: per caption, whether each version's edge check fires."""
import csv, glob, sys
B, S = sys.argv[1], sys.argv[2]
VERSIONS = [("frozen", "frozen (23 rules)"), ("slim", "core 6"), ("s7b", "core 6 + body lines"), ("s7h", "core 6 + heading"), ("slim8", "core 6 + both")]
GRADER_ERRORS = {"g699p"}
items = {l.split("\t")[0]: tuple(l.rstrip("\n").split("\t")[1:5]) for l in open(f"{B}/grade/items.tsv")}
graded = list(csv.DictReader(open(f"{B}/final_in_ho_new_layer.tsv"), delimiter="\t"))
tier = {r["id"]: 0 if r["id"] in GRADER_ERRORS else int(r["defined_tier"]) for r in graded}
def load(pat):
    out = {}
    for f in glob.glob(pat):
        for r in csv.DictReader(open(f), delimiter="\t"):
            out[(r["set"], r["key"], r["page"], r["caption"])] = r
    return out
sig, two = load(f"{B}/sig_*.tsv"), load(f"{B}/two_*.tsv")
def edge(d):
    return d["d_top"] != "" and max(abs(float(d[k])) for k in ("d_top", "d_bottom", "d_left", "d_right")) > 1
table = {i: {} for i in tier}
for mode in ("layer", "nolayer"):
    print(f"== second opinion with {'the text layer' if mode == 'layer' else 'geometry only'}")
    for v, name in VERSIONS:
        det = load(f"{S}/det_{v}_*_{mode}.tsv")
        sent = {}
        for i in tier:
            k = items[i]; d, x = det[k], sig[k]
            e = edge(d)
            table[i][f"{v}_{mode}"] = int(e)
            sent[i] = d["warn_uncropped"] == "1" or int(d["ncrops"]) >= 2 or e or x["table"] == "1" \
                or max(int(x[c]) for c in ("cut_top", "cut_bottom", "cut_left", "cut_right")) >= 3 or bool(two[k]["twofig"])
        n = {t: [i for i in tier if tier[i] == t] for t in (0, 1, 2)}
        sev = sum(sent[i] for i in n[1]); good = sum(not sent[i] for i in n[0])
        miss = [i for i in n[1] if not sent[i]]
        print(f"  {name:<22} severe {sev}/{len(n[1])}  minor {sum(sent[i] for i in n[2])}/{len(n[2])}  "
              f"good passed {good}/{len(n[0])} ({100 * good / len(n[0]):.1f}%)  missed: {' '.join(miss) or '-'}")
with open(f"{S}/edge_flags.tsv", "w") as out:
    cols = [f"{v}_{m}" for m in ("layer", "nolayer") for v, _ in VERSIONS]
    out.write("id\tset\tkey\tpage\tcaption\ttier\t" + "\t".join(cols) + "\n")
    for i in sorted(tier, key=lambda i: items[i]):
        out.write("\t".join([i, *items[i], str(tier[i])] + [str(table[i][c]) for c in cols]) + "\n")
