"""Inventory every artifact in the project by PARSING it, not grepping.
Prints the numbers that go into HANDOFF.md.
"""
import collections
import hashlib
import os
import re

from paths import ROOT
RAW = os.path.join(ROOT, "data", "raw")


def sha256(path, limit=None):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


print("=" * 78)
print("FILE INVENTORY")
print("=" * 78)
total = 0
for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if d not in {"__pycache__", ".git"}]
    for fn in sorted(filenames):
        p = os.path.join(dirpath, fn)
        sz = os.path.getsize(p)
        total += sz
        rel = os.path.relpath(p, ROOT)
        print(f"{sz:>12,}  {rel}")
print(f"{total:>12,}  TOTAL")

print()
print("=" * 78)
print("PADT  (parsed from .conllu)")
print("=" * 78)
pad = collections.Counter()
per_file = {}
total_sent = total_tok = total_root = total_case = total_head = total_vform = 0
for split in ("train", "dev", "test"):
    p = os.path.join(RAW, f"ar_padt-ud-{split}.conllu")
    if not os.path.exists(p):
        print(f"{split}: MISSING")
        continue
    sents = toks = roots = cases = heads = vforms = 0
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            if line.startswith("#"):
                if line.startswith("# sent_id"):
                    sents += 1
                continue
            cols = line.split("\t")
            if len(cols) < 10 or "-" in cols[0] or "." in cols[0]:
                continue
            toks += 1
            misc = cols[9]
            feats = cols[5]
            if re.search(r"(?:^|\|)Root=", misc):
                roots += 1
            if re.search(r"(?:^|\|)Vform=", misc):
                vforms += 1
            if re.search(r"(?:^|\|)Case=", feats):
                cases += 1
            if cols[7] != "root":
                heads += 1
            for k, v in (m.split("=", 1) for m in feats.split("|") if "=" in m):
                pad[f"{k}={v}"] += 1
    per_file[split] = (sents, toks, roots, cases, vforms)
    total_sent += sents
    total_tok += toks
    total_root += roots
    total_case += cases
    total_head += heads
    total_vform += vforms
    print(f"{split:>5}: {sents:>6,} sentences  {toks:>7,} tokens  "
          f"root={roots:>7,} ({roots/toks*100:5.1f}%)  "
          f"case={cases:>7,} ({cases/toks*100:5.1f}%)  "
          f"vform={vforms:>7,} ({vforms/toks*100:5.1f}%)")
print(f"TOTAL: {total_sent:>6,} sentences  {total_tok:>7,} tokens  "
      f"root={total_root:,}  case={total_case:,}  vform={total_vform:,}")

print()
print("=== top 20 UD morphological features ===")
for k, v in pad.most_common(20):
    print(f"{v:>8,}  {k}")

print()
print("=== Case distribution (the I'rab target) ===")
for k in sorted(k for k in pad if k.startswith("Case=")):
    print(f"{pad[k]:>8,}  {k}")

print()
print("=" * 78)
print("QAC morphology 0.4  (parsed)")
print("=" * 78)
roots = collections.Counter()
feat = collections.Counter()
segs = stems = 0
qpath = os.path.join(RAW, "qac-morphology-0.4.txt")
with open(qpath, encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("LOCATION"):
            continue
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        segs += 1
        toks = [t for t in parts[3].split("|") if t]
        for t in toks:
            feat[t] += 1
            if t.startswith("ROOT:"):
                roots[t[5:]] += 1
        if "STEM" in toks:
            stems += 1
print(f"segments:        {segs:>9,}")
print(f"STEM segments:   {stems:>9,}")
print(f"distinct roots:  {len(roots):>9,}")
print(f"hapax roots:     {sum(1 for v in roots.values() if v == 1):>9,}")
print(f"roots >= 5:      {sum(1 for v in roots.values() if v >= 5):>9,}")
print(f"3-letter roots:  {sum(1 for r in roots if len(r) == 3):>9,}")
print(f"4-letter roots:  {sum(1 for r in roots if len(r) == 4):>9,}")
print(f"other lengths:   {sum(1 for r in roots if len(r) not in (3, 4)):>9,}")

print()
print("=" * 78)
print("SHA256 of the three primary corpora")
print("=" * 78)
for f in ("qac-morphology-0.4.txt", "ar_padt-ud-train.conllu",
          "ar_padt-ud-dev.conllu", "ar_padt-ud-test.conllu"):
    p = os.path.join(RAW, f)
    print(f"{sha256(p)}  {f}")
