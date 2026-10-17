"""Why does the surface route abstain on the human gold? Bucket the renderer's OWN reasons.

`eval_harness.py:299` builds its pairs as `render_triple(r, p, c, engine=e)[0]` — it keeps the
surface and DISCARDS the reason, so `score_final_surface` can only report one lumped `abstain`
bucket. That is why 296/300 came back as a single number with no diagnosis attached.

This runs the renderer on the HUMAN GOLD triples (the annotator's own root+pattern+case), which
separates the two very different failures:
  · the renderer abstains on the GOLD triple too  -> a renderer/convention problem, independent of
    the model, and it caps the metric for everyone;
  · it renders the gold triple but abstained on the model's -> a MODEL problem.
Zero GPU: the renderer is pure rules.

Run: .venv/Scripts/python.exe src/diagnose_gold_abstention.py
"""
from __future__ import annotations

import collections
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.chdir(Path(__file__).resolve().parent.parent)

from final_surface import render_triple          # the SAME dispatch the metric uses

GOLD = Path("data/annotation/gold-tashkeela-300.jsonl")


def main() -> int:
    rows = [json.loads(l) for l in open(GOLD, encoding="utf-8") if l.strip()]
    print("=" * 96)
    print(f"HUMAN-GOLD ABSTENTION DIAGNOSIS — {len(rows)} rows, rendering the ANNOTATOR'S OWN triples")
    print("=" * 96)

    for engine in ("v1", "v3"):
        ok = 0
        why = collections.Counter()
        examples = collections.defaultdict(list)
        for r in rows:
            surf, reason = render_triple(r.get("t_root_arabic"), r.get("t_wazan_pattern"),
                                         r.get("t_case"), engine=engine)
            if surf is None:
                why[reason] += 1
                if len(examples[reason]) < 4:
                    examples[reason].append(
                        f"{r.get('form')}  root={r.get('t_root_arabic')!r} "
                        f"pat={r.get('t_wazan_pattern')!r} case={r.get('t_case')!r} "
                        f"pat_valid={r.get('pattern_valid')} why={r.get('pattern_reason')}")
            else:
                ok += 1
        n = len(rows)
        print(f"\n--- engine {engine} — rendered {ok}/{n} = {100*ok/n:.1f}%, "
              f"abstained {n-ok} = {100*(n-ok)/n:.1f}% ---")
        for k, v in why.most_common():
            print(f"    {v:>4}  {k}")
            for ex in examples[k]:
                print(f"          eg {ex}")

    # Do the annotated patterns even PARSE as the renderer's digit convention? Rule 6 says a
    # complete slot pattern looks like 1َ2ّ3 / 1ُ2َ3ى. If the renderer's expectation differs, the
    # mismatch shows up here rather than as a rendering error.
    print("\n=== annotated pattern shapes (the convention question) ===")
    shapes = collections.Counter()
    for r in rows:
        p = r.get("t_wazan_pattern") or ""
        digits = [ch for ch in p if ch in "1234"]
        shapes[("digits=" + "".join(sorted(set(digits))), f"len={len(digits)}",
                "rootlen=" + str(len(r.get("t_root_arabic") or "")))] += 1
    for k, v in shapes.most_common(12):
        print(f"    {v:>4}  {k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
