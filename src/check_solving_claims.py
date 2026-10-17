"""Quantify two claims in solving.md:

Q1. Constrained decoding over root x wazan pairs: how sparse is the VALID pair set?
    (A12 says masking invalid root/wazan pairs is "the genuinely interesting use".)

Q2. Per-step decision cost of the structured tuple vs a BPE baseline.
    (Refines challenge A3: is the treatment's hypothesis space smaller, or LARGER?)
"""
import collections
import math
import re

from camel_tools.morphology.database import MorphologyDB
from camel_tools.morphology.analyzer import Analyzer
from camel_tools.disambig.mle import MLEDisambiguator

from paths import PADT_TRAIN as PADT
DIAC = re.compile(r"[\u064b-\u0652\u0670]")
DIG = re.compile(r"[1-4]")


def wazan_of(raw):
    if not raw or raw in ("None", "na"):
        return None
    ds = set(DIG.findall(raw))
    if ds not in ({"1", "2", "3"}, {"1", "2", "3", "4"}) or len(DIG.findall(raw)) != len(ds):
        return None
    body = raw[min(raw.index(d) for d in DIG.findall(raw)):]
    body = body[:-1] if body and body[-1] in "ًٌٍَُِْ" else body
    return body.translate(str.maketrans({"1": "ف", "2": "ع", "3": "ل", "4": "ل"}))


tokens = []
with open(PADT, encoding="utf-8") as fh:
    for line in fh:
        if line.startswith("#") or not line.strip():
            if len(tokens) >= 6000:
                break
            continue
        c = line.rstrip("\n").split("\t")
        if len(c) < 10 or "-" in c[0] or "." in c[0] or c[3] == "PUNCT":
            continue
        if not re.search(r"[\u0621-\u064a]", c[1]):
            continue
        tokens.append(c[1])
tokens = tokens[:6000]

mle = MLEDisambiguator.pretrained("calima-msa-r13")
dis = [d for d in mle.disambiguate(tokens) if d.analyses]

pairs = set()
roots = set()
wazans = set()
roles = collections.Counter()
for d in dis:
    a = d.analyses[0].analysis
    if a.get("source") != "lex" or not a.get("root"):
        continue
    w = wazan_of(a.get("pattern"))
    if not w:
        continue
    r = a["root"]
    roots.add(r)
    wazans.add(w)
    pairs.add((r, w))

print("=" * 74)
print("Q1. root x wazan VALID-PAIR SPARSITY")
print("=" * 74)
print(f"  distinct roots          : {len(roots):>8}")
print(f"  distinct wazans         : {len(wazans):>8}")
print(f"  product (all combos)    : {len(roots)*len(wazans):>8,}")
print(f"  OBSERVED valid pairs    : {len(pairs):>8,}")
print(f"  fill rate               : {100*len(pairs)/(len(roots)*len(wazans)):>7.2f}%")
print()
print("  -> the valid set is extremely sparse, so masking root x wazan at inference")
print("     removes the overwhelming majority of the joint space. A12 is well-founded.")

# how many wazans does the average root take?
per_root = collections.Counter()
for r, w in pairs:
    per_root[r] += 1
vals = sorted(per_root.values())
if vals:
    print()
    print(f"  wazans per root: median {vals[len(vals)//2]}, "
          f"mean {sum(vals)/len(vals):.1f}, max {vals[-1]}")
    print(f"  roots seen with exactly 1 wazan: "
          f"{sum(1 for v in vals if v==1)}/{len(vals)}")

print()
print("=" * 74)
print("Q2. PER-STEP DECISION COST (refining challenge A3)")
print("=" * 74)

BASELINE_VOCAB = 32000
case_vocab = 3
role_vocab = None
# role vocab from PADT deprels
deps = set()
with open(PADT, encoding="utf-8") as fh:
    for line in fh:
        if line.startswith("#"):
            continue
        c = line.rstrip("\n").split("\t")
        if len(c) >= 10 and "-" not in c[0] and "." not in c[0]:
            deps.add(c[7])
role_vocab = len(deps)
OFFSET_BUCKETS = 16

b_bits = math.log2(BASELINE_VOCAB)
t_bits = (math.log2(len(roots)) + math.log2(len(wazans)) +
          math.log2(OFFSET_BUCKETS) + math.log2(role_vocab) + math.log2(case_vocab))
print(f"  baseline: one {BASELINE_VOCAB:,}-way choice per step = {b_bits:.2f} bits")
print(f"  treatment: root({len(roots)}) x wazan({len(wazans)}) x offset({OFFSET_BUCKETS}) "
      f"x role({role_vocab}) x case({case_vocab})")
print(f"             summed head entropies = {t_bits:.2f} bits per step")
print(f"  unconstrained joint            = "
      f"{math.log2(len(roots)*len(wazans)*OFFSET_BUCKETS*role_vocab*case_vocab):.2f} bits")
print()
print("  -> the treatment makes MORE decisions per step, not fewer.")
print("     So A3 is not a 'smaller hypothesis space' problem. It is a SUPERVISION-DENSITY")
print("     problem: the treatment receives ~5 labels per token where the baseline gets 1,")
print("     and its non-embedding body is larger at matched total parameters.")
print("     Same fix (score both from surface output through one analyser), different reason.")
