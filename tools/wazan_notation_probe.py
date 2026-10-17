"""wazan_notation_probe.py — is the wazan accuracy gap a MODEL problem or a NOTATION problem?

THE CLAIM UNDER TEST
    A proposal wants to lift wazan accuracy from "22.1%" to 95-97% by pruning a "70-class"
    label space to <=3 surface-compatible templates. Two things about that are checkable offline:

    1. the label space is not 70 classes. The project's own vocabulary records wazan types per run
       (3,248 in v13, 6,633 in v26) -- two orders of magnitude larger.
    2. if the SAME template can legitimately be written several ways, then raw string match
       understates what the model knows. The project already measures a `*_wazan_slots` key that
       sits at ~0.99 while `*_wazan_raw` sits at ~0.11-0.22. If that gap is notation, the fix is a
       canonical label space (and the item-1 adjudicated benchmark), not a search-space prune.

WHAT THIS MEASURES
    On the 300-row human gold (the only human wazan annotation that exists in this project):
      * how many DISTINCT patterns annotators wrote
      * how many distinct patterns remain after canonicalisation, at increasing strictness
        (case-vowel strip -> diacritic strip -> keep only digit skeleton + template letters)
      * the ceiling a canonical-metric evaluation would give

CPU only. Reads data/annotation/full-FILLED-by-Rendi.csv.
"""
from __future__ import annotations

import argparse
import collections
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_root import resolve_root  # noqa: E402

DIAC = re.compile(r"[\u064b-\u0652\u0670]")
TRAILING_CASE = re.compile(r"[\u064b-\u0652\u0670]*\u0627?$")


def canon_case_strip(p: str) -> str:
    """drop the trailing case vowel / tanwin (the packet already excludes it in principle)"""
    return TRAILING_CASE.sub("", p.strip())


def canon_diacritic_strip(p: str) -> str:
    return DIAC.sub("", p.strip())


def canon_skeleton(p: str) -> str:
    """digits + template letters only: pure structural signature of the pattern"""
    return re.sub(r"[^0-9\u0621-\u064a]", "", DIAC.sub("", p.strip()))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None)
    args = ap.parse_args()
    ROOT = resolve_root(args.root)

    src = ROOT / "data/annotation/full-FILLED-by-Rendi.csv"
    rows = list(csv.DictReader(src.open(encoding="utf-8-sig", newline="")))
    pats = [r["wazn_pattern"].strip() for r in rows if (r.get("wazn_pattern") or "").strip()]
    pats = [p for p in pats if p.upper() != "ABSTAIN"]

    print("=" * 84)
    print("WAZAN: label space and notation collapse  (human gold, %d patterns)" % len(pats))
    print("=" * 84)
    for label, fn in (("raw (as written)", lambda p: p),
                      ("trailing case vowel stripped", canon_case_strip),
                      ("all diacritics stripped", canon_diacritic_strip),
                      ("digit+letter skeleton", canon_skeleton)):
        vals = [fn(p) for p in pats]
        n = len(set(vals))
        print("  %-30s distinct types = %4d   (%.1f%% of the raw space)"
              % (label, n, 100.0 * n / len(set(pats))))

    print("\n--- the collapse, concretely: raw types that share one structural skeleton ---")
    groups = collections.defaultdict(set)
    for p in pats:
        groups[canon_skeleton(p)].add(p)
    multi = sorted(((len(v), k, v) for k, v in groups.items() if len(v) > 1), reverse=True)[:8]
    print("  %d structural skeletons carry >1 distinct written form" % len(
        [1 for k, v in groups.items() if len(v) > 1]))
    for n, k, v in multi:
        print("    skeleton %-12s %d ways: %s" % (k, n, " | ".join(sorted(v)[:5])))

    print("\n--- what a SLOT-LEVEL metric would score, versus a raw-string metric ---")
    # slot-level: compare the multiset of digits present (the project's *_wazan_slots idea)
    n_raw = len(set(pats))
    n_slot = len(set(tuple(sorted(set(re.findall(r"[0-9]", p)))) for p in pats))
    print("  raw distinct forms        : %4d" % n_raw)
    print("  distinct digit-set signatures: %4d  -> a raw-string metric conflates these"
          % n_slot)
    print("\n  NOTE: this bounds the NOTATION share of the gap. It is not an accuracy claim --")
    print("  the honest fix is an adjudicated canonical label space (ACTIVE_BACKLOG item 1).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
