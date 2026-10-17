import collections

from paths import QAC_TXT as path
roots = collections.Counter()
with open(path, encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("LOCATION"):
            continue
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        for t in parts[3].split("|"):
            if t.startswith("ROOT:"):
                roots[t[5:]] += 1

quad = {r: c for r, c in roots.items() if len(r) == 4}
print(f"QUADRILATERAL ROOTS: {len(quad)} of {len(roots)} ({len(quad)/len(roots)*100:.1f}%)")
print(f"total stem occurrences they cover: {sum(quad.values()):,}")
print()
for r, c in sorted(quad.items(), key=lambda x: -x[1]):
    print(f"{c:>5}  {r}")
