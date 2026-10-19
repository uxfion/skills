# /// script
# dependencies = []
# ///
"""pool.py FULLTEXT USED OUT_TSV: every parsed paper in the fulltext folder not used yet, with its source PDF,
page count, first-page venue guess and whether the INDEX marks it no_text_layer."""
import json, re, subprocess, sys
from pathlib import Path

ft, used, out = Path(sys.argv[1]), set(Path(sys.argv[2]).read_text().split()), sys.argv[3]
index = {}
for line in (ft / "INDEX.md").read_text().splitlines():
    cells = [c.strip() for c in line.split("|")]
    if len(cells) > 6 and cells[1] and not cells[1].startswith(("citation", "---")):
        index[cells[1]] = cells
VENUES = [("nature medicine", "NatMed"), ("npj", "npj"), ("nature communications", "NatComm"), ("nature", "Nature"),
          ("science", "Science"), ("lancet", "Lancet"), ("jama", "JAMA"), ("bmj", "BMJ"), ("ieee", "IEEE"),
          ("neurips", "NeurIPS"), ("neural information processing", "NeurIPS"), ("iclr", "ICLR"),
          ("international conference on learning representations", "ICLR"), ("icml", "ICML"),
          ("association for computational linguistics", "ACL"), ("acl", "ACL"), ("emnlp", "EMNLP"),
          ("naacl", "NAACL"), ("proceedings of machine learning research", "PMLR"), ("aaai", "AAAI"),
          ("cell", "Cell"), ("plos", "PLOS"), ("arxiv", "arXiv"), ("medrxiv", "medRxiv"), ("elsevier", "Elsevier"),
          ("springer", "Springer"), ("oxford", "OUP"), ("acm", "ACM")]
rows = []
for d in sorted(ft.iterdir()):
    j = d / f"{d.name}.json"
    if not j.exists() or d.name in used:
        continue
    try:
        src = json.load(open(j))["source"]["path"]
    except Exception:
        continue
    if not src or not Path(src).exists() or not src.lower().endswith(".pdf"):
        continue
    txt = subprocess.run(["pdftotext", "-l", "2", src, "-"], capture_output=True, text=True).stdout.lower()
    venue = next((v for k, v in VENUES if re.search(r"\b" + re.escape(k) + r"\b", txt)), "?")
    cells = index.get(d.name, [])
    pages = cells[4] if cells else "?"
    nolayer = "no_text_layer" in (cells[6] if cells else "") or len(txt.strip()) < 200
    rows.append((d.name, venue, pages, "nolayer" if nolayer else "", src))
with open(out, "w") as f:
    for r in rows:
        f.write("\t".join(r) + "\n")
print(len(rows), "unused papers")
