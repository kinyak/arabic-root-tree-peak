"""compare_silver_vs_gold.py — how good is the SILVER label itself, against the 278
human wazān patterns?

WHY THIS EXISTS, SEPARATELY FROM ANY MODEL
    The ablation in the notebook answers "does a model trained on silver do as well as
    one trained on gold?" — but that number cannot be interpreted without knowing the
    QUALITY OF THE SILVER TARGET ITSELF. If CALIMA's label for a word disagrees with the
    human pattern, then a model that reproduces its target perfectly still scores below
    the human agreement ceiling, and that gap is a LABEL gap, not a model gap. This
    script measures exactly that gap, with no training involved and no model in the loop.

    It is also the only measurement here that can be run before a GPU is spent — which
    is the point: it says what the training run could possibly achieve.

WHAT IT JOINS ON
    The diacritic-stripped surface (`form_bare`), which is the same key the dictionary
    uses and the same key the gold's skeleton form gives. One gold form can occur many
    times in the corpus, so the comparison is per gold ROW: the silver label is taken
    from every matching record and the MODAL label wins; the number of distinct labels
    seen is reported, because a form with several silver labels is a form where the
    teacher itself is unstable and no model can be blamed for missing it.

CAVEAT THAT MUST TRAVEL WITH THE OUTPUT
    Single annotator, no inter-annotator agreement, and the sample is stratified toward
    weak/doubled surfaces. A disagreement is not proof that the human is right.

USAGE
    python src/compare_silver_vs_gold.py
    python src/compare_silver_vs_gold.py --silver data/out/tashkeela-dev.jsonl
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import eval_harness as EH                       # noqa: E402
from paths import OUT, ROOT                      # noqa: E402

DIG = re.compile(r"[1-4]")


def load_records(paths) -> dict[str, list[dict]]:
    """form_bare -> [record, ...]."""
    by_form: dict[str, list[dict]] = collections.defaultdict(list)
    for p in paths:
        p = Path(p)
        if not p.exists():
            print(f"  (missing, skipped: {p})")
            continue
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                by_form[r["form_bare"]].append(r)
    return by_form


def classify_mismatch(gold: str, pred: str | None) -> str:
    """Name the KIND of disagreement, so a count is interpretable rather than a number.

    The categories are the ones the gold's own convention makes possible, and the split
    between them is what decides whether a model-level gap is the MODEL's fault:
      match      identical (after NFC — same visual string, same string)
      hamza_lead differs only by the leading radical being a letter vs the digit
      diacritics identical once diacritics are removed (the annotator writes the full
                 template vocalization; CALIMA's pattern is sparser and drops the
                 trailing case vowel)
      slot_count the radical-SLOT SETS differ — the only class that is a genuine
                 structural disagreement, and MEASURED at 1 row of 196
      template   the slots agree and the spelling differs (a weak radical written as a
                 letter by the annotator and as its digit by the pipeline, an extra
                 orthographic alif, a hamza spelled إ vs أ)
      pred_none  a record existed but the strict gate refused to emit a label
    """
    if pred is None:
        return "pred_none"
    if EH.nfc(pred) == EH.nfc(gold):
        return "match"
    if EH.lead_hamza_variant(pred) == EH.lead_hamza_variant(gold):
        return "hamza_lead"
    if EH.strip_diac(EH.lead_hamza_variant(pred) or "") == \
            EH.strip_diac(EH.lead_hamza_variant(gold) or ""):
        return "diacritics"
    if sorted(DIG.findall(pred)) != sorted(DIG.findall(gold)):
        return "slot_count"
    return "template"

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--silver", nargs="*",
                    default=[str(OUT / "tashkeela-dev.jsonl"),
                             str(OUT / "tashkeela-train.jsonl")])
    ap.add_argument("--gold", default=str(ROOT / "data" / "annotation" /
                                          "gold-tashkeela-300.jsonl"))
    args = ap.parse_args()

    print("=" * 88)
    print("SILVER LABEL QUALITY vs THE 278 HUMAN WAZAN PATTERNS (no model involved)")
    print("=" * 88)
    gold = EH.load_human_gold(args.gold)
    silver = load_records(args.silver)
    print(f"  gold rows : {len(gold)}")
    print(f"  silver    : {sum(len(v) for v in silver.values()):,} records over"
          f" {len(silver):,} distinct bare forms")

    waz = collections.Counter()
    waz_kinds = collections.Counter()
    root_hit = root_n = 0
    root_kinds = collections.Counter()
    ambiguous = []
    no_silver = []
    examples = []

    for g in gold:
        key = EH.bare_form(g.get("form") or "")
        recs = silver.get(key, [])
        if not recs:
            no_silver.append(key)
            continue
        if g.get("pattern_valid") and g.get("t_wazan_pattern"):
            labs = collections.Counter(r["t_wazan"] for r in recs if r["m_wazan"])
            if not labs:
                waz["no_silver_label"] += 1
                waz_kinds["pred_none"] += 1
            else:
                if len(labs) > 1:
                    ambiguous.append((key, len(labs), labs.most_common(3)))
                pred, _ = labs.most_common(1)[0]
                kind = classify_mismatch(g["t_wazan_pattern"], pred)
                waz_kinds[kind] += 1
                waz["n"] += 1
                waz["raw_correct"] += 1 if EH.nfc(pred) == EH.nfc(g["t_wazan_pattern"]) else 0
                waz["norm_correct"] += 1 if kind in ("match", "hamza_lead",
                                                     "diacritics") else 0
                waz["slot_correct"] += 1 if (sorted(DIG.findall(pred or ""))
                                             == sorted(DIG.findall(g["t_wazan_pattern"]))) else 0
                if kind not in ("match",) and len(examples) < 10:
                    examples.append((key, g["t_wazan_pattern"], pred, kind))
        if g.get("root_valid") and g.get("t_root_arabic"):
            roots = collections.Counter(
                EH.to_bare_root_str("".join(x for x in r["t_root"] if x))
                for r in recs if r["m_root"])
            if roots:
                pred, _ = roots.most_common(1)[0]
                root_n += 1
                gl = EH.to_bare_root_str(g["t_root_arabic"])
                ok = pred == gl
                root_hit += ok
                if not ok and len(root_kinds) < 14 and root_kinds[pred] < 3:
                    root_kinds[pred] += 1

    print()
    print("WAZAN — silver label vs the human pattern, per gold row (modal silver label)")
    print(f"  rows with a silver label      : {waz['n']}")
    print(f"  1. RAW exact                  : {waz['raw_correct']}/{waz['n']} = "
          f"{100*waz['raw_correct']/max(waz['n'],1):5.1f}%")
    print(f"  2. hamza/diacritic-normalised : {waz['norm_correct']}/{waz['n']} = "
          f"{100*waz['norm_correct']/max(waz['n'],1):5.1f}%")
    print(f"  3. radical-slot set matches   : {waz['slot_correct']}/{waz['n']} = "
          f"{100*waz['slot_correct']/max(waz['n'],1):5.1f}%")
    print(f"  rows with NO silver label     : {waz['no_silver_label']}  (a GAP, not a zero)")
    print(f"  gold rows with no silver record for their form: {len(no_silver)}")
    # A MEASURED CLASS THE SILVER PIPELINE CANNOT SUPERVISE AT ALL. A hamzated FIRST
    # radical is written by the annotator as the digit 1 (أُصُول -> '1ُ2ُو3') but CALIMA
    # returns the letter with slot 1 missing ('أَ2ْ3' for الْأَرْض), which the strict
    # well-formedness gate then MASKs. So the silver arm is never shown this class while
    # the human gold asks about it. Counted here so the model-level gap has a cause.
    lead = [g for g in gold if g.get("pattern_valid") and g.get("t_wazan_pattern")
            and EH.lead_hamza_variant(g["t_wazan_pattern"]) != g["t_wazan_pattern"]]
    print(f"  gold patterns in the LEAD-HAMZA class (digit-1 spelling): {len(lead)}"
          f"  of {sum(1 for g in gold if g.get('pattern_valid'))} valid patterns")
    print(f"  DISAGREEMENT KIND: {dict(waz_kinds.most_common())}")
    print(f"  forms where the silver teacher is itself UNSTABLE (>1 label): "
          f"{len(ambiguous)}")
    for k, n, top in ambiguous[:5]:
        print(f"     {k}: {n} distinct -> {top}")
    print()
    print("  examples (kind = how the two differ):")
    for k, gp, pp, kind in examples[:10]:
        print(f"     {k:14} gold {gp!r:16} silver {pp!r:16} {kind}")

    print()
    print("ROOT — silver dictionary root vs the human root")
    print(f"  rows with a silver root       : {root_n}")
    print(f"  bare-alef agreement           : {root_hit}/{root_n} = "
          f"{100*root_hit/max(root_n,1):5.1f}%")
    print("  most frequent predicted roots on the misses (a cluster here is a convention,")
    print("  not a scattering of errors):")
    for r, n in root_kinds.most_common(10):
        print(f"     {r!r}: {n}")

    out = OUT / "silver_vs_gold.json"
    out.write_text(json.dumps({
        "gold_rows": len(gold), "wazan": dict(waz), "wazan_kinds": dict(waz_kinds),
        "root": {"n": root_n, "correct": root_hit},
        "gold_rows_without_a_silver_record": no_silver,
        "ambiguous_forms": [{"form": k, "distinct": n,
                             "top": [[l, c] for l, c in top]}
                            for k, n, top in ambiguous],
        "caveat": "single annotator, no IAA, sample stratified toward weak/doubled "
                  "surfaces: a disagreement is not proof the human is right",
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out}")
    print("REMEMBER: the denominators are gold rows that HAD a silver label. The gap is")
    print("reported separately because a missing label is not a wrong label.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
