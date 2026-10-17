"""Quantify CALIMA ambiguity and the pattern-vs-wazan entanglement.

Q1. How ambiguous is raw analyzer output? (=> is a disambiguator mandatory?)
Q2. Is `pattern` a WAZAN, or a WAZAN x CASE-ENDING x CLITIC product?
"""
import re
import collections

from camel_tools.morphology.database import MorphologyDB
from camel_tools.morphology.analyzer import Analyzer
from camel_tools.disambig.mle import MLEDisambiguator

DIAC = re.compile(r"[\u064b-\u0652\u0670]")
from paths import PADT_TRAIN as PADT

tokens = []
with open(PADT, encoding="utf-8") as fh:
    for line in fh:
        if line.startswith("#") or not line.strip():
            if len(tokens) >= 1500:
                break
            continue
        c = line.rstrip("\n").split("\t")
        if len(c) < 10 or "-" in c[0] or "." in c[0]:
            continue
        if c[3] == "PUNCT" or not re.search(r"[\u0621-\u064a]", c[1]):
            continue
        tokens.append(c[1])
tokens = tokens[:1200]

an = Analyzer(MorphologyDB.builtin_db())
mle = MLEDisambiguator.pretrained("calima-msa-r13")

print("=" * 78)
print(f"Q1. AMBIGUITY  (sample: {len(tokens)} PADT tokens)")
print("=" * 78)
counts = sorted(n for n in (len(an.analyze(t)) for t in tokens) if n)
print(f"raw analyzer : median {counts[len(counts)//2]}, "
      f"mean {sum(counts)/len(counts):.1f}, max {counts[-1]} analyses/word")
print(f"unambiguous words (exactly 1 analysis): {sum(1 for n in counts if n==1)}/{len(counts)}"
      f"  ({sum(1 for n in counts if n==1)/len(counts)*100:.1f}%)")

dis = mle.disambiguate(tokens)
resolved = [d for d in dis if d.analyses]
print(f"after MLE disambiguation: {len(resolved)}/{len(tokens)} tokens have an analysis; "
      f"best-ranked retained for each")

print()
print("=" * 78)
print("Q2. IS `pattern` A WAZAN, OR A WAZAN x CASE x CLITIC PRODUCT?")
print("=" * 78)
raw, nodiac, with_al = collections.Counter(), collections.Counter(), 0
roots, cases, states = set(), collections.Counter(), collections.Counter()
n = 0
for d in resolved:
    a = d.analyses[0].analysis
    p = a.get("pattern")
    if not p or p in ("None", "na"):
        continue
    n += 1
    raw[p] += 1
    nodiac[DIAC.sub("", p)] += 1
    if p.startswith("ال") or p.startswith("و") or p.startswith("ف"):
        with_al += 1
    r = a.get("root")
    if r and r != "None":
        roots.add(r)
    cases[a.get("cas", "?")] += 1
    states[a.get("stt", "?")] += 1

print(f"tokens with a usable pattern : {n}")
print(f"distinct patterns AS EMITTED  : {len(raw):>5}")
print(f"distinct patterns, diacritics stripped: {len(nodiac):>5}")
print(f"=> compression {len(raw)/max(len(nodiac),1):.1f}x  "
      f"(the inflation factor = case endings x clitics)")
print(f"patterns carrying a CLITIC prefix (ال/و/ف): {with_al} of {n} "
      f"({with_al/max(n,1)*100:.0f}%)")
print(f"distinct roots observed: {len(roots)}")
print()
print("case (`cas`) values:", dict(cases.most_common(8)))
print("state (`stt`) values:", dict(states.most_common(8)))
print()
print("--- one wazan, many surface patterns (proof of entanglement) ---")
grp = collections.defaultdict(list)
for p in raw:
    grp[DIAC.sub("", p)].append(p)
for stem, variants in sorted(grp.items(), key=lambda x: -sum(raw[v] for v in x[1]))[:6]:
    tot = sum(raw[v] for v in variants)
    print(f"  {stem:<10} {len(variants)} variants  ({tot} tokens)")
    print(f"      {sorted(variants)}")
print()
print("--- 10 most common AS-EMITTED patterns ---")
for p, c in raw.most_common(10):
    print(f"{c:>5}  {p!r}")
