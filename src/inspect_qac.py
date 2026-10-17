import collections, re

from paths import QAC_TXT as path
feat = collections.Counter()
roots = collections.Counter()
iv = collections.Counter()
stems = 0
segments = 0
mood = collections.Counter()

with open(path, encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("LOCATION"):
            continue
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        segments += 1
        tokens = [t for t in parts[3].split("|") if t]
        for t in tokens:
            feat[t] += 1
            if t.startswith("ROOT:"):
                roots[t[5:]] += 1
            if t.startswith("MOOD:"):
                mood[t[5:]] += 1
            if t == "(IV)":
                iv[t] += 1
        if "STEM" in tokens:
            stems += 1

print(f"segments (prefix+stem+suffix): {segments:,}")
print(f"STEM segments:                 {stems:,}")
print(f"distinct roots (QAC):          {len(roots):,}")
print(f"roots appearing once:          {sum(1 for v in roots.values() if v == 1):,}")
print(f"roots with >=5 occurrences:    {sum(1 for v in roots.values() if v >= 5):,}")
print()
print("=== 15 most frequent roots ===")
for r, c in roots.most_common(15):
    print(f"{c:>6,}  {r}")
print()
print("=== verb-form tag (IV) present? ===", dict(iv))
print("=== MOOD:* tags ===", dict(mood) or "none in v0.4")
print()
print("=== 45 most frequent feature tags ===")
for t, c in feat.most_common(45):
    print(f"{c:>7,}  {t}")
