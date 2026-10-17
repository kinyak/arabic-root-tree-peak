"""The renderer against the 300 human gold triples — closed test + DEFECT TAXONOMY.

This is a THIN harness over `final_surface.py`. The metric, the clitic-plane
decomposition and the defect taxonomy live THERE and only there, because a metric that
exists in two places is a metric that can silently diverge — which is exactly what
happened here: this file's first version carried its own copy of the decomposition and
inherited a real bug (the enclitic edge was matched on the raw last CHARACTER, so
`أَخْبَرَهُ` — which ends in a damma — failed every enclitic case and understated the
clitic plane). Importing the shared implementation fixes it and keeps it fixed.

WHY THIS TEST, AND NOT PADT
    PADT's FORM column is UNDIACRITIZED, so "fully vocalized match" against PADT is
    0.0% BY CONSTRUCTION (renderer.py --measure prints that flat 0.0% and says why).
    The 300 annotated rows are the only corpus that carries BOTH a human
    (root, wazān, case) triple AND the human's own vocalized surface. Coverage here is
    100% by construction, so rendering ACCURACY is the only open question — which is
    exactly what the plan's Steps 1-2 claim to fix.

THE LADDER (never merged — each rung is a different claim)
    1 raw            byte-equal to the human's token
    2 NFC            equal after canonical normalisation
    3 clitic-aware   equal after SOME legal affix decomposition  <- final_surface.stem_match
    4 + hamza folded alif/hamza family folded (this rung HIDES the Step-2 defect)
    5 skeleton       consonants equal, diacritics off
"""
from __future__ import annotations

import collections
import json
import sys

from final_surface import (candidates, classify_defect, strip_diac as skel, nfc as NFC,
                           fold_hamza, apply_clitic_plane, TAN)
from paths import GOLD_JSONL
from renderer import render_rule, apply_case, DIAC

GOLD = str(GOLD_JSONL)


def run(render, rows_filter=None, label: str = "ALL") -> tuple[dict, collections.Counter, dict]:
    rows = [json.loads(l) for l in open(GOLD, encoding="utf-8") if l.strip()]
    usable = [r for r in rows if r.get("t_root_arabic") and r.get("t_wazan_pattern")]
    if rows_filter is not None:
        usable = [r for r in usable if rows_filter(r)]
    lad, buckets, examples = collections.Counter(), collections.Counter(), \
        collections.defaultdict(list)
    n = len(usable)
    for r in usable:
        form = r["form"]
        got, why = render(r["t_root_arabic"], r["t_wazan_pattern"])
        if got is None:
            lad["abstain"] += 1
            buckets["abstain"] += 1
            continue
        got_c = apply_clitic_plane(apply_case(got, r.get("t_case")), form)
        cands = candidates(form)
        lad["raw"] += (got_c == form)
        lad["nfc"] += (NFC(got_c) == NFC(form))
        lad["clitic"] += any(NFC(c) == NFC(got_c) for c in cands)
        lad["hamza"] += any(fold_hamza(NFC(c)) == fold_hamza(NFC(got_c)) for c in cands)
        lad["skel"] += (skel(got_c) == skel(form))
        b = classify_defect(form, got_c)
        buckets[b] += 1
        if len(examples[b]) < 4 and b != "clitic":
            examples[b].append((r["id"], form, got_c, r["t_root_arabic"],
                                r["t_wazan_pattern"]))
    return {"n": n, "lad": lad, "buckets": buckets, "examples": examples,
            "rows": rows, "usable": usable}


HARNESS = {"clitic", "canonical_order"}
PLAN = {"hamza_seat", "weak_radical_written", "weak_radical_missing", "weak_or_hamza"}


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default="v1", choices=("v1", "v2", "v3"),
                    help="v1 = digit in place (default, the documented baseline); "
                         "v3 = weak-radical re-realization")
    ap.add_argument("--weak-only", action="store_true",
                    help="restrict to rows whose root class is hollow/defective/"
                         "assimilated — the acceptance test the plan asked for. NOTE it "
                         "is 98 rows, not 93, and ~30 of those are hamza roots the "
                         "annotator wrote with a bare alif (see CHALLENGES §2s.10).")
    args = ap.parse_args()

    if args.engine == "v1":
        from renderer import render_rule as render
    else:
        from render_rules import ENGINES
        render = ENGINES[args.engine]

    def weak_filter(r):
        import eval_harness as EH
        return EH.root_class(r["t_root_arabic"]) in {"hollow", "defective", "assimilated"}

    res = run(render, rows_filter=weak_filter if args.weak_only else None)
    n, lad, buckets, examples, rows = (res["n"], res["lad"], res["buckets"],
                                      res["examples"], res["rows"])
    usable = res["usable"]
    print("=" * 84)
    print(f"RENDERER (engine {args.engine}) vs the 300 HUMAN GOLD TRIPLES"
          f"{' — WEAK-ONLY SUBSET' if args.weak_only else ''}")
    print("=" * 84)
    print(f"rows {len(rows)} · with root+pattern {n} · "
          f"with case {sum(1 for r in usable if r.get('t_case') is not None)} · "
          f"vocalized forms {sum(1 for r in rows if DIAC.search(r.get('form') or ''))}")
    print()
    print(f"{'rung':<46} {'count':>6} {'rate':>8}")
    for label, k in (("1 raw  render+case == human token", "raw"),
                     ("2 NFC-normalised equality", "nfc"),
                     ("3 clitic-aware (some legal affix split)", "clitic"),
                     ("4 + hamza/alif family folded", "hamza"),
                     ("5 skeleton (consonants, diacritics off)", "skel"),
                     ("abstentions", "abstain")):
        print(f"{label:<46} {lad[k]:>6} {100*lad[k]/n:>7.1f}%")

    print()
    print("-" * 84)
    print("DEFECT TAXONOMY — first repair rule reconciling each row")
    print("(count = UPPER BOUND on what that rule could win; nothing is fixed here)")
    print("-" * 84)
    for b, c in buckets.most_common():
        tag = ("  [harness/pipeline]" if b in HARNESS else
               "  [plan Steps 1+2]" if b in PLAN else "")
        print(f"  {b:<26} {c:>4}  {100*c/n:>5.1f}%{tag}")
    print()
    for b, ex in sorted(examples.items(), key=lambda x: -buckets[x[0]]):
        if not ex:
            continue
        print(f"  [{b}]")
        for i, form, gotc, rt, pat in ex:
            print(f"    {i:<5} gold {form:<14} rendered {gotc:<14} {rt:<7} {pat}")

    plan = sum(buckets[k] for k in PLAN)
    harness = sum(buckets[k] for k in HARNESS)
    print()
    print("=" * 84)
    print(f"ADDRESSABLE BY THE PLAN'S STEPS 1+2 : {plan} of {n} ({100*plan/n:.1f}%)")
    print(f"NUNATION (apply_case cannot emit it): "
          f"{buckets['tanwin_missing'] + buckets['tanwin_alif_acc']} "
          f"({100*(buckets['tanwin_missing']+buckets['tanwin_alif_acc'])/n:.1f}%)")
    print(f"HARNESS/PIPELINE, NOT MORPHOLOGY     : {harness} ({100*harness/n:.1f}%)"
          "  <- already render correctly")
    print(f"UNEXPLAINED (no named rule)          : {buckets['other']} "
          f"({100*buckets['other']/n:.1f}%)")
    print("=" * 84)
    return 0


if __name__ == "__main__":
    sys.exit(main())
