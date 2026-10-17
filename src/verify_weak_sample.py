"""Verify the weak-radical sample size and the R1 error buckets, from the DATA.

WHY: before writing phonological rules, check the two numbers the plan rests on — "93
stratified weak rows" and a "5.7% R1 error bucket". The project's rule is that a number
is run before it is repeated, and these two decide the acceptance test.
"""
from __future__ import annotations

import collections
import json
import sys

from paths import GOLD_JSONL, ROOT
from eval_harness import root_class
from final_surface import candidates, classify_defect
from renderer import render_rule, apply_case


def main() -> int:
    gold = [json.loads(l) for l in open(GOLD_JSONL, encoding="utf-8") if l.strip()]
    usable = [r for r in gold if r.get("t_root_arabic") and r.get("t_wazan_pattern")]
    n = len(usable)
    print(f"gold rows {len(gold)} · with root+pattern {n}")

    print("\nroot_class distribution over the gold (eval_harness.root_class):")
    dist = collections.Counter(root_class(r["t_root_arabic"]) for r in usable)
    for k, v in dist.most_common():
        print(f"  {k:<16} {v:>4}  {100*v/n:5.1f}%")
    weak = {"hollow", "defective", "assimilated", "hamza"}
    w = sum(dist[k] for k in weak)
    print(f"  {'WEAK TOTAL':<16} {w:>4}  {100*w/n:5.1f}%   "
          f"(hollow+defective+assimilated+hamza)")

    print("\nany row whose root contains a weak letter و/ي/ا at all:")
    contains = sum(1 for r in usable if any(c in "ويا" for c in r["t_root_arabic"]))
    print(f"  {contains} of {n}  ({100*contains/n:.1f}%)")

    print(f"\nR1 defect buckets on the CURRENT renderer (engine v1), first reconciling rule:")
    b = collections.Counter()
    cross = collections.defaultdict(collections.Counter)
    examples = collections.defaultdict(list)
    for r in usable:
        cls = root_class(r["t_root_arabic"])
        got, why = render_rule(r["t_root_arabic"], r["t_wazan_pattern"])
        if got is None:
            b["abstain"] += 1
            cross[cls]["abstain"] += 1
            continue
        got_c = apply_case(got, r.get("t_case"))
        k = classify_defect(r["form"], got_c)
        b[k] += 1
        cross[cls][k] += 1
        if cls in ("hollow", "defective", "assimilated") and k != "clitic" \
                and len(examples[cls]) < 4:
            examples[cls].append((r["id"], r["form"], got_c, r["t_root_arabic"],
                                  r["t_wazan_pattern"]))
    for k, v in b.most_common():
        print(f"  {k:<26} {v:>4}  {100*v/n:5.1f}%")
    plan = sum(b[k] for k in ("weak_radical_written", "weak_radical_missing",
                              "weak_or_hamza"))
    print(f"  {'-> the three WEAK buckets':<26} {plan:>4}  {100*plan/n:5.1f}%")

    print("\nCROSS-TAB root class x defect bucket (where the weak rules must aim):")
    order = [k for k, _ in b.most_common()]
    print(f"  {'class':<14} {'n':>4}  " + " ".join(f"{k[:9]:>9}" for k in order[:7]))
    for cls, c in sorted(cross.items(), key=lambda x: -sum(x[1].values())):
        tot = sum(c.values())
        row = " ".join(f"{c.get(k,0):>9}" for k in order[:7])
        print(f"  {cls:<14} {tot:>4}  {row}")

    print("\nweak-class failures that are NOT the clitic plane (v1):")
    for cls, ex in examples.items():
        print(f"  [{cls}]")
        for i, form, gotc, rt, pat in ex:
            print(f"    {i:<5} gold {form:<14} got {gotc:<14} root={rt:<7} {pat}")

    print(f"\nstrata metadata available: {(ROOT / 'data/annotation/full-annotation-meta.json')}")
    try:
        meta = json.loads((ROOT / "data/annotation/full-annotation-meta.json").read_text())
        print(json.dumps(meta, indent=2)[:800])
    except Exception as e:
        print("  (unreadable:", e, ")")
    return 0


if __name__ == "__main__":
    sys.exit(main())
