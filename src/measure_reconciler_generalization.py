"""Held-out test of the weak-root RECONCILER that CHALLENGES.md §2d claims works.

CHALLENGES.md §2d reports:
    all unusable roots            3,825 / 3,966 = 96.4%
    open-class unusable roots     2,253 / 2,257 = 99.8%
citing "a `surface -> root` dictionary built from PADT's human `Root=` column
(193,012 tokens, 20,614 distinct surfaces) -- applied to every CALIMA token whose
root was unusable".

No src/*.py in the repo produces those numbers, and the measurement as described is
IN-SAMPLE: the dictionary is keyed on surfaces taken from the same file the unusable
tokens come from, so a surface that appears once clean and once '#'-marked is
"recovered" by looking itself up.

This script measures the thing the paper actually needs: does the reconciler
generalize to surfaces the dictionary has never seen?  Dictionary is built from
PADT **train** gold roots only; the unusable tokens are sampled from PADT **dev**
and **test**, which are disjoint documents.
"""
import collections
import re
import sys

from camel_tools.disambig.mle import MLEDisambiguator

from paths import RAW as PD
DIAC = re.compile(r"[\u064b-\u0652\u0670]")
ARABIC = re.compile(r"[\u0621-\u064a]")
UNUSABLE = ("#", "NTWS")


def read_conllu_tokens(path, want_gold_root):
    """Yield (surface, upos, gold_root|None) for real tokens."""
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            c = line.rstrip("\n").split("\t")
            if len(c) < 10 or "-" in c[0] or "." in c[0]:
                continue
            if not ARABIC.search(c[1]):
                continue
            root = None
            m = re.search(r"(?:^|\|)Root=([^|]+)", c[9])
            if m:
                root = m.group(1).strip()
            if want_gold_root and root is None:
                continue
            out.append((c[1], c[3], root))
    return out


def clean_surface(s):
    return DIAC.sub("", s)


# ---------------------------------------------------------------- dictionary
train = read_conllu_tokens(f"{PD}/ar_padt-ud-train.conllu", want_gold_root=True)
lut = collections.defaultdict(collections.Counter)
for surf, upos, root in train:
    lut[clean_surface(surf)][root] += 1
DICT = {k: c.most_common(1)[0][0] for k, c in lut.items()}

print("=" * 78)
print("RECONCILER GENERALIZATION — dictionary built from PADT train gold roots")
print("=" * 78)
print(f"  PADT train tokens with gold Root= : {len(train):,}")
print(f"  distinct surfaces in dictionary   : {len(DICT):,}")

# ---------------------------------------------------------------- probe set
probe = read_conllu_tokens(f"{PD}/ar_padt-ud-dev.conllu", want_gold_root=False)
probe += read_conllu_tokens(f"{PD}/ar_padt-ud-test.conllu", want_gold_root=False)
probe = probe[:6000]
print(f"  probe tokens (PADT dev+test)      : {len(probe):,}")

mle = MLEDisambiguator.pretrained("calima-msa-r13")
surfaces = [p[0] for p in probe]
dis = mle.disambiguate(surfaces)

rows = []
for (surf, upos, _), d in zip(probe, dis):
    if not d.analyses:
        continue
    a = d.analyses[0].analysis
    if a.get("source") != "lex":
        continue
    root = a.get("root") or ""
    rows.append({
        "surf": surf,
        "key": clean_surface(surf),
        "root": root,
        "upos": a.get("pos") or upos,
        "usable": bool(root) and len(root.split(".")) in (3, 4)
                  and not any(t in root for t in UNUSABLE),
    })

usable = [r for r in rows if r["usable"]]
unusable = [r for r in rows if not r["usable"]]
print(f"  lexicon-backed, CALIMA usable      : {len(usable):,} "
      f"({100*len(usable)/max(len(rows),1):.1f}% of {len(rows):,})")
print(f"  lexicon-backed, CALIMA UNUSABLE    : {len(unusable):,}")

OPEN = {"noun", "verb", "adj", "noun_prop", "noun_num", "adj_comp", "adj_num"}
occ = [r for r in unusable if r["upos"] in OPEN]

print()
print("  HELD-OUT recovery by the train-derived dictionary")
print(f"    all unusable          : {sum(r['key'] in DICT for r in unusable):,}"
      f" / {len(unusable):,}")
print(f"    open-class unusable   : {sum(r['key'] in DICT for r in occ):,}"
      f" / {len(occ):,}")

# distinct-surface view: a surface counts once
dis_un = {r["key"] for r in unusable}
dis_occ = {r["key"] for r in occ if r["key"] not in DICT}
print()
print(f"    distinct unusable surfaces : {len(dis_un):,}  "
      f"(in dict: {sum(s in DICT for s in dis_un):,})")
print(f"    distinct UNRESOLVED surfaces (still no root) : {len(dis_occ):,}")

print()
print("  20 unresolved open-class surfaces, sampled:")
for s in sorted(dis_occ)[:20]:
    ex = next(r for r in occ if r["key"] == s)
    print(f"    {ex['surf']:12} calima_root={ex['root']!r:14} pos={ex['upos']}")
print()
print("  NOTE: 'in dict' means the held-out surface appeared in PADT TRAIN. A surface")
print("  absent from the dictionary is a hard failure under this design -- which is the")
print("  case that matters for Tashkeela, whose vocabulary is largely not in PADT.")
