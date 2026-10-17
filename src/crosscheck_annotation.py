"""crosscheck_annotation.py — independent checks on a filled annotation sheet.

Tashkeela has no gold, so `score_annotation.py` cannot validate it. But a large share of
Tashkeela prose QUOTES the Quran, so a subset of the sheet's targets can be matched
against **EQTB** and **QAC** — two human treebanks that ARE independent of the annotator
and of CALIMA. That gives a real external validity check on part of the sheet.

Two checks, deliberately separated by what they can and cannot prove:

  CHECK A — against human gold (EQTB / QAC).  This is evidence. A disagreement is either
            an annotator slip or a gold quibble, and every disagreement is printed for
            adjudication rather than silently counted.

  CHECK B — against CALIMA.  NOT evidence, and never used to "correct" the gold. It
            measures the human-vs-analyser gap, and it flags rows where the annotator and
            the analyser disagree so a human can re-read them. Recording CALIMA's answer
            as truth would re-create exactly the closed loop the blind protocol exists to
            prevent.
"""
from __future__ import annotations

import argparse
import collections
import csv
import re
import sys

from paths import EQTB_CSV, QAC_TXT, require

ARABIC = re.compile(r"[\u0621-\u063a\u0641-\u064a]")
DIAC = re.compile(r"[\u064b-\u0652\u0670\u0640]")
DIG = re.compile(r"[1-4]")


def skel(s: str) -> str:
    """Match key: diacritics, tatweel and hamza variety removed."""
    if not s:
        return ""
    s = DIAC.sub("", s)
    return (s.replace("\u0623", "\u0627").replace("\u0625", "\u0627")
             .replace("\u0622", "\u0627").replace("\u0621", "\u0627"))


def nroot(r: str | None) -> str | None:
    if not r:
        return None
    t = "".join(c for c in r if ARABIC.match(c))
    if not t:
        return None
    return (t.replace("\u0623", "\u0627").replace("\u0625", "\u0627")
             .replace("\u0622", "\u0627").replace("\u0621", "\u0627"))


def eqtb_map(limit=140000):
    words = collections.defaultdict(list)
    with open(require(EQTB_CSV), encoding="utf-16", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            words[(row.get("chapter_id"), row.get("verse_id"), row.get("word_id"))].append(row)
    out = {}
    for _, segs in words.items():
        segs.sort(key=lambda r: int(r.get("tok_id") or 0))
        surf = skel("".join((s.get("uthmani_token") or "").strip() for s in segs))
        if not surf:
            continue
        stem = next((s for s in segs
                     if (s.get("segment") or "").upper().startswith("STEM")), segs[0])
        r = nroot(stem.get("root_ar"))
        if r:
            out.setdefault(surf, r)
    return out


def qac_map(limit=80000):
    from reconcile import qac_form_to_arabic, qac_to_arabic
    out = {}
    n = 0
    with open(require(QAC_TXT), encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#") or not line.strip():
                continue
            c = line.split("\t")
            if len(c) < 4 or not c[3].startswith("STEM"):
                continue
            m = re.search(r"ROOT:([^|]+)", c[3])
            if not m:
                continue
            surf = skel(qac_form_to_arabic(c[1].strip()))
            r = nroot(qac_to_arabic(m.group(1).strip()))
            if surf and r:
                out.setdefault(surf, r)
            n += 1
            if n >= limit:
                break
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", required=True)
    ap.add_argument("--calima", action="store_true", help="also run CHECK B")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.sheet, encoding="utf-8-sig")))
    print("=" * 84)
    print("ANNOTATION CROSS-CHECK")
    print("=" * 84)
    print(f"sheet: {args.sheet}   rows: {len(rows)}")

    gold = {}
    e = eqtb_map()
    print(f"\nEQTB human roots indexed : {len(e):,} distinct surfaces")
    gold.update(e)
    q = qac_map()
    print(f"QAC  human roots indexed : {len(q):,} distinct surfaces")
    for k, v in q.items():
        gold.setdefault(k, v)
    print(f"combined gold lookup     : {len(gold):,}")

    print("\n--- CHECK A: against human gold (EQTB + QAC), independent of the annotator ---")
    agree = disagree = 0
    misses = []
    for r in rows:
        key = skel(r["target_token"])
        mine = nroot(r["root"])
        g = gold.get(key)
        if not g or not mine:
            continue
        if mine == g:
            agree += 1
        else:
            disagree += 1
            misses.append((r["id"], r["target_token"], mine, g))
    tot = agree + disagree
    if tot:
        print(f"  matched {tot} rows · agree {agree} ({100*agree/tot:.1f}%) · "
              f"disagree {disagree}")
        for i, t, mine, g in misses:
            print(f"    {i} {t:16} sheet={mine:8} gold={g:8}")
        print("  -> each disagreement is either an annotator slip or a gold quibble;")
        print("     printed for adjudication, NOT auto-corrected.")
    else:
        print("  no rows matched the gold surface index")

    # ---- Rule 6 compliance, measured directly
    print("\n--- Rule 6 compliance: does every pattern have a complete digit set? ---")
    bad = [(r["id"], r["target_token"], r["wazn_pattern"]) for r in rows
           if r["wazn_pattern"].strip()
           and not r["wazn_pattern"].strip().upper().startswith("ABSTAIN")
           and not (lambda d: set(d) in ({"1", "2", "3"}, {"1", "2", "3", "4"})
                    and len(d) == len(set(d)))(DIG.findall(r["wazn_pattern"]))]
    print(f"  patterns failing the digit gate: {len(bad)}")
    for i, t, p in bad[:10]:
        print(f"    {i} {t:16} {p!r}")
    if not bad:
        print("  -> ZERO. The pilot's 7 failures are gone; the Rule 6 examples worked.")

    if args.calima:
        print("\n--- CHECK B: annotator vs CALIMA (NOT gold — diagnostic only) ---")
        from camel_tools.disambig.mle import MLEDisambiguator
        mle = MLEDisambiguator.pretrained("calima-msa-r13")
        surv = [r["target_token"] for r in rows]
        ana = []
        B = 400
        for i in range(0, len(surv), B):
            for d in mle.disambiguate(surv[i:i + B]):
                ana.append(d.analyses[0].analysis if (d and d.analyses) else None)
        rc = cr = cc = ct = 0
        flags = []
        for r, a in zip(rows, ana):
            mine_raw = r["root"].strip()
            if mine_raw.upper().startswith("ABSTAIN") or not a:
                continue
            mine = nroot(mine_raw)
            theirs = nroot(a.get("root"))
            if mine and theirs:
                ct += 1
                rc += 1 if mine == theirs else 0
                if mine != theirs and len(flags) < 10:
                    flags.append((r["id"], r["target_token"], mine, theirs))
        if ct:
            print(f"  root: annotator and CALIMA agree on {rc}/{ct} = "
                  f"{100*rc/ct:.1f}% of rows both attempted")
            print("  -> a LOW figure is expected and is the point: the sheet exists")
            print("     because CALIMA is wrong on exactly these classes. It is NOT")
            print("     evidence the annotator is wrong.")
            for i, t, mine, th in flags:
                print(f"    {i} {t:16} sheet={mine:8} CALIMA={th:8}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
