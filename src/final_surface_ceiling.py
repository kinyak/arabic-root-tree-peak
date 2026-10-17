"""The renderer's CEILING on the shared final-surface metric, and the CALIMA proxy.

WHY THIS IS THE NUMBER THE PAPER NEEDS FIRST
    The treatment arm's pipeline is  model -> (root, wazān, case) -> renderer -> surface.
    Its end-to-end score is therefore bounded from above by what the renderer can do
    when the triple is CORRECT. This script measures that bound, on the 300 human gold
    rows, two ways:

      HUMAN triple  = an ORACLE for the model: the annotator's own (root, wazān, case).
                      Whatever this scores is the renderer's ceiling, and NO model can
                      exceed it — not because models are weak, but because the renderer
                      sits after them.
      CALIMA triple = what the distillation SOURCE supplies, so it is the realistic
                      pipeline proxy (this is the object the treatment is trained to
                      imitate, so it is also the honest target).

    Both go through `final_surface.score_final_surface` — the SAME function
    `eval_harness.score_human_gold` now calls for both arms — so a ceiling measured
    here and an arm measured there are the same quantity.

COVERAGE IS REPORTED SEPARATELY FROM ACCURACY
    `stem_accuracy_of_covered` is conditional on a render; `stem_yield` counts an
    abstention as a miss. They are different claims and neither replaces the other.
"""
from __future__ import annotations

import collections
import re
import sys

import eval_harness as EH
from final_surface import render_triple, score_final_surface

BATCH = 500
CALIMA_CASE = {"n": 0, "a": 1, "g": 2}
WEAK_OK = re.compile(r"[\u0621-\u063a\u0641-\u064a]")


def norm_root(r):
    if not r:
        return None
    r = "".join(c for c in r if c not in ". ")
    return None if (not r or "#" in r) else r


def main() -> int:
    from camel_tools.disambig.mle import MLEDisambiguator

    gold = EH.load_human_gold()
    forms = [g.get("form") or "" for g in gold]
    print(f"human gold rows: {len(gold)}")

    mle = MLEDisambiguator.pretrained("calima-msa-r13")
    ana = []
    for i in range(0, len(forms), BATCH):
        for d in mle.disambiguate(forms[i:i + BATCH]):
            ana.append(d.analyses[0].analysis if (d and d.analyses) else None)

    triples = {"human": [], "calima": []}
    n_human = n_calima = 0
    for g, a in zip(gold, ana):
        form = g.get("form")
        if g.get("t_root_arabic") and g.get("t_wazan_pattern"):
            triples["human"].append((form, (g["t_root_arabic"], g["t_wazan_pattern"],
                                            g.get("t_case"))))
            n_human += 1
        if a and a.get("pattern"):
            triples["calima"].append((form, (norm_root(a.get("root")), a.get("pattern"),
                                             CALIMA_CASE.get(a.get("cas")))))
            n_calima += 1
        else:
            triples["calima"].append((form, None))

    print(f"rows with a human triple : {n_human}")
    print(f"rows with a CALIMA triple: {n_calima}")
    print()
    print("=" * 92)
    print("SHARED FINAL-SURFACE METRIC — coverage and accuracy SEPARATE")
    print("=" * 92)
    print(f"{'triple':<8} {'engine':<7} {'n':>4} {'cover':>7} {'abstain':>8} "
          f"{'acc|covered':>12} {'yield':>7} {'token':>7} {'skel':>7}")
    out = {}
    for src in ("human", "calima"):
        for e in ("v1", "v3"):
            pairs = [(f, render_triple(*(t or (None, None, None)), engine=e, token=f)[0])
                     for f, t in triples[src]]
            s = score_final_surface(pairs)
            out[f"{src}:{e}"] = s
            print(f"{src:<8} {e:<7} {s['n']:>4} {s['coverage']*100:6.1f}% "
                  f"{s['abstain']:>8} {s['stem_accuracy_of_covered']*100:11.1f}% "
                  f"{s['stem_yield']*100:6.1f}% {s['token_exact_yield']*100:6.1f}% "
                  f"{s['skeleton_yield']*100:6.1f}%")

    print()
    print("  READ IT THIS WAY:")
    print("    · 'human' is the renderer's CEILING for a perfect model. If it is low, the")
    print("      treatment's end-to-end number is bounded by the RENDERER, not the model.")
    print("    · 'calima' is the distillation source, so it is the realistic target.")
    print("    · coverage is the abstention rate; it is NOT folded into the accuracy column.")
    print()
    print("  defect buckets (human triple, engine v3) — the work list:")
    for k, v in out["human:v3"]["defect_buckets"].items():
        print(f"    {k:<26} {v:>4}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
