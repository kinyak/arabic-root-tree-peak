"""Measure what the arity/projectivity decoder design depends on.

Q1. How non-projective are these treebanks?  -> does 'distance only for non-projective' work?
Q2. What is the left/right dependent-arity distribution? -> what count classes / is '>4' rare?
Q3. How often is a sentence fully projective (no distance head needed at all)?
"""
import collections
import os

from paths import RAW
FILES = {
    "PADT  (news, CATiB-UD)": ["ar_padt-ud-train.conllu", "ar_padt-ud-dev.conllu", "ar_padt-ud-test.conllu"],
    "NYUAD (PATB, no roots)": ["ar_nyuad-ud-train.conllu", "ar_nyuad-ud-dev.conllu", "ar_nyuad-ud-test.conllu"],
}


def read_sents(files):
    for fn in files:
        p = os.path.join(RAW, fn)
        if not os.path.exists(p):
            continue
        sent = []
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if not line:
                    if sent:
                        yield sent
                        sent = []
                    continue
                if line.startswith("#"):
                    continue
                c = line.split("\t")
                if len(c) < 10 or "-" in c[0] or "." in c[0]:
                    continue
                try:
                    sid = int(c[0]); head = int(c[6])
                except ValueError:
                    continue
                sent.append((sid, head, c[7]))
        if sent:
            yield sent


def nonprojective_arcs(sent):
    """An arc is non-projective if it crosses another arc."""
    arcs = [(min(d, h), max(d, h)) for d, h, _ in sent if h != 0]
    bad = set()
    for i, (a1, b1) in enumerate(arcs):
        for j, (a2, b2) in enumerate(arcs):
            if i == j:
                continue
            if a1 < a2 < b1 < b2:
                bad.add(i)
    return bad, len(arcs)


for label, files in FILES.items():
    sents = list(read_sents(files))
    tot_arcs = nonproj = 0
    fully_proj = 0
    left = collections.Counter()
    right = collections.Counter()
    maxl = maxr = 0
    for s in sents:
        bad, n = nonprojective_arcs(s)
        tot_arcs += n
        nonproj += len(bad)
        if not bad:
            fully_proj += 1
        # arity
        kids = collections.defaultdict(list)
        for d, h, _ in s:
            if h != 0:
                kids[h].append(d)
        for d, h, _ in s:
            ld = sum(1 for k in kids.get(d, []) if k < d)
            rd = sum(1 for k in kids.get(d, []) if k > d)
            left[min(ld, 9)] += 1
            right[min(rd, 9)] += 1
            maxl = max(maxl, ld); maxr = max(maxr, rd)

    print("=" * 78)
    print(f"{label}   ({len(sents):,} sentences, {tot_arcs:,} arcs)")
    print("=" * 78)
    print(f"  non-projective arcs      : {nonproj:,}  ({100*nonproj/max(tot_arcs,1):.2f}%)")
    print(f"  fully projective sentences: {fully_proj:,}  ({100*fully_proj/max(len(sents),1):.2f}%)")
    print(f"  max left deps / right deps: {maxl} / {maxr}")
    print()
    print("  LEFT-dependents per token :", {k: left[k] for k in sorted(left)})
    print("  RIGHT-dependents per token:", {k: right[k] for k in sorted(right)})
    over4l = sum(v for k, v in left.items() if k >= 5)
    over4r = sum(v for k, v in right.items() if k >= 5)
    tk = sum(left.values())
    print()
    print(f"  tokens with >4 left deps  : {over4l} ({100*over4l/max(tk,1):.3f}%)")
    print(f"  tokens with >4 right deps : {over4r} ({100*over4r/max(tk,1):.3f}%)")
    print()
