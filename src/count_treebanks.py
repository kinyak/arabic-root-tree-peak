"""Count the newly proposed treebanks and check what supervision they actually carry."""
import collections
import os
import re

from paths import RAW

FILES = {
    "PADT (already had)": ["ar_padt-ud-train.conllu", "ar_padt-ud-dev.conllu", "ar_padt-ud-test.conllu"],
    "NYUAD (proposed)":   ["ar_nyuad-ud-train.conllu", "ar_nyuad-ud-dev.conllu", "ar_nyuad-ud-test.conllu"],
    "PUD (proposed)":     ["ar_pud-ud-test.conllu"],
}

grand = collections.OrderedDict()

for label, files in FILES.items():
    sents = toks = roots = cases = vforms = 0
    upos = collections.Counter()
    deps = collections.Counter()
    for fn in files:
        p = os.path.join(RAW, fn)
        if not os.path.exists(p):
            print(f"  MISSING {fn}")
            continue
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if not line:
                    continue
                if line.startswith("#"):
                    if line.startswith("# sent_id"):
                        sents += 1
                    continue
                c = line.split("\t")
                if len(c) < 10 or "-" in c[0] or "." in c[0]:
                    continue
                toks += 1
                feats, misc = c[5], c[9]
                if re.search(r"(?:^|\|)Root=", misc):
                    roots += 1
                if re.search(r"(?:^|\|)Vform=", misc):
                    vforms += 1
                if re.search(r"(?:^|\|)Case=", feats):
                    cases += 1
                upos[c[3]] += 1
                deps[c[7]] += 1
    grand[label] = (sents, toks, roots, cases, vforms)
    print("=" * 78)
    print(f"{label}")
    print("=" * 78)
    print(f"  sentences                 : {sents:>9,}")
    print(f"  tokens                    : {toks:>9,}")
    print(f"  with Root= in misc        : {roots:>9,}  ({100*roots/max(toks,1):5.1f}%)")
    print(f"  with Vform= (vocalized)   : {vforms:>9,}  ({100*vforms/max(toks,1):5.1f}%)")
    print(f"  with Case=                : {cases:>9,}  ({100*cases/max(toks,1):5.1f}%)")
    print(f"  top 8 deprels             : {[d for d, _ in deps.most_common(8)]}")
    print()

print("=" * 78)
print("COMBINED GOLD DEPENDENCY SUPERVISION")
print("=" * 78)
tot_s = sum(v[0] for v in grand.values())
tot_t = sum(v[1] for v in grand.values())
tot_r = sum(v[2] for v in grand.values())
tot_c = sum(v[3] for v in grand.values())
for k, v in grand.items():
    print(f"  {k:<22} {v[0]:>8,} sents  {v[1]:>9,} tokens  root {100*v[2]/max(v[1],1):5.1f}%")
print(f"  {'TOTAL':<22} {tot_s:>8,} sents  {tot_t:>9,} tokens  root {100*tot_r/max(tot_t,1):5.1f}%")
print()
print(f"  D1,000-claim check: user said 34,638 sentences.")
print(f"  Actual (PADT+NYUAD+PUD, no QADT yet): {tot_s:,}")
print(f"  Difference = {34638 - tot_s:,}  <-- should equal the QADT verse count if the claim is right")
