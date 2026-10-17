"""summarize_ablation.py — read the ablation's results.json and print the honest tables.

WHY A SCRIPT AND NOT A GLANCE AT THE NOTEBOOK
    The notebook prints a lot, and the numbers that matter are DIFFERENCES between a 2x2 grid of
    means with a seed spread attached. Doing that subtraction by eye across 12 runs is how a
    "result" gets quoted that the data does not support. This reads results.json, groups by
    (target source, arm), and prints every difference NEXT TO the spread it has to beat — and
    puts the label-level ceiling underneath, because a model cannot beat the labels it was taught.

USAGE
    python src/summarize_ablation.py                      # dist/kaggle-output/results/results.json
    python src/summarize_ablation.py --results PATH
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from paths import ROOT, OUT  # noqa: E402

# metric key in the flattened row -> (label, direction that would support the treatment)
METRICS = (
    ("in_domain_case_macro_f1", "case macro-F1 (own dev)"),
    ("in_domain_root_acc", "root acc (own dev)"),
    ("padt_dev_case_macro_f1", "case macro-F1 (PADT dev)"),
    ("padt_dev_root_acc", "root acc (PADT dev)"),
    ("gold_wazan_raw", "wazan vs gold (RAW)"),
    ("gold_wazan_norm", "wazan vs gold (hamza-normalised)"),
    ("gold_wazan_slots", "wazan vs gold (radical slots)"),
    ("gold_root", "root vs gold"),
    ("gold_case_macro_f1", "case macro-F1 vs gold"),
    ("gold_oov", "OOV rate of gold context (lower is better)"),
)
CEIL = {"case_macro_f1": 0.459, "root_accuracy": 0.451}


def flat(tag: str, results: dict, gold: dict, training: dict) -> dict:
    t = training.get(tag, {})
    r = results[tag]
    # two layouts exist: v5 stored the eval metrics at the top level, the round-17 notebook
    # nests them under 'in_domain_dev'. Accept both so this tool can read either file —
    # and so the v5 file can be used to CHECK the round-17 numbers with the same code.
    dom = r.get("in_domain_dev") or r
    padt = r.get("padt_dev") or dom
    g = gold.get(tag, {})
    return {"tag": tag, "source": t.get("source"), "arm": t.get("arm"),
            "seed": t.get("seed"), "seconds": t.get("seconds"),
            "in_domain_case_macro_f1": (dom.get("case") or {}).get("macro_f1"),
            "in_domain_root_acc": (dom.get("root") or {}).get("accuracy"),
            "padt_dev_case_macro_f1": (padt.get("case") or {}).get("macro_f1"),
            "padt_dev_root_acc": (padt.get("root") or {}).get("accuracy"),
            "gold_wazan_raw": (g.get("wazan") or {}).get("accuracy"),
            "gold_wazan_norm": (g.get("wazan_hamza_normalised") or {}).get("accuracy"),
            "gold_wazan_slots": (g.get("wazan_radical_slots") or {}).get("accuracy"),
            "gold_root": (g.get("root") or {}).get("accuracy"),
            "gold_case_macro_f1": (g.get("case") or {}).get("macro_f1"),
            "gold_oov": g.get("oov_rate")}


def spread(rows: list[dict], key: str):
    xs = [r[key] for r in rows if r.get(key) is not None]
    if not xs:
        return None
    return {"n": len(xs), "mean": st.fmean(xs),
            "sd": (st.stdev(xs) if len(xs) > 1 else 0.0),
            "min": min(xs), "max": max(xs), "vals": [round(x, 4) for x in xs]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=str(ROOT / "dist" / "kaggle-output" /
                                            "results" / "results.json"))
    ap.add_argument("--label-ceiling", default=str(OUT / "silver_vs_gold.json"))
    args = ap.parse_args()

    d = json.loads(Path(args.results).read_text(encoding="utf-8"))
    results = d["results"]
    gsc = d.get("gold_scored", {})
    training = d.get("training")
    if not training:
        # The round-16/v5 notebook wrote neither block. Recover the tags from the run
        # names rather than crashing on a file this script is supposed to be able to read.
        training = {}
        for tag in results:
            parts = tag.split("-s")[0].split("-")
            training[tag] = {"source": parts[0] if len(parts) > 1 else "?",
                             "arm": parts[-1], "seed": tag.split("-s")[-1]}
    rows = [flat(t, results, gsc, training) for t in results]

    print("=" * 100)
    print("ABLATION — every run, then every difference against the spread it must beat")
    print("=" * 100)
    print("%-26s %-8s %-9s %6s | %7s %7s | %7s %7s %7s %7s %7s %6s" % (
        "run", "source", "arm", "s", "inCase", "inRoot",
        "wz_raw", "wz_norm", "wz_slot", "gldRoot", "gldCase", "oov"))
    for r in sorted(rows, key=lambda r: (r["source"] or "", r["arm"] or "", r["seed"] or 0)):
        def f(k):
            v = r.get(k)
            return "%.3f" % v if isinstance(v, (int, float)) else "  -  "
        print("%-26s %-8s %-9s %6s | %7s %7s | %7s %7s %7s %7s %7s %6s" % (
            r["tag"], r["source"], r["arm"], r["seed"], f("in_domain_case_macro_f1"),
            f("in_domain_root_acc"), f("gold_wazan_raw"), f("gold_wazan_norm"),
            f("gold_wazan_slots"), f("gold_root"), f("gold_case_macro_f1"), f("gold_oov")))

    summary = {}
    # Adapt to whatever the file contains rather than assuming {gold, silver}: the v5 file
    # stores no source at all (a 1x2 grid), and hardcoding the two names silently produced
    # an EMPTY comparison the first time this ran against it.
    for source in sorted({r["source"] for r in rows}):
        print("\n" + "-" * 100)
        print("TARGET SOURCE = %s   (treatment vs baseline, %d seeds each)" % (
            source, len([r for r in rows if r["source"] == source and r["arm"] == "treatment"])))
        print("-" * 100)
        for key, label in METRICS:
            a = spread([r for r in rows if r["source"] == source and r["arm"] == "treatment"], key)
            b = spread([r for r in rows if r["source"] == source and r["arm"] == "baseline"], key)
            if not a or not b:
                continue
            diff = a["mean"] - b["mean"]
            ref = max(a["sd"], b["sd"])
            verdict = "SEPARATED" if abs(diff) > 2 * ref else "not separated"
            summary["%s/%s" % (source, key)] = {"treatment": a, "baseline": b,
                                                "diff": diff, "verdict": verdict}
            print("%-38s treat %.3f [%.3f]  base %.3f [%.3f]  d=%+.4f  -> %s"
                  % (label, a["mean"], a["sd"], b["mean"], b["sd"], diff, verdict))

    print("\n" + "=" * 100)
    print("WHAT THE MODEL COULD POSSIBLY SCORE — the labels it was taught set the ceiling")
    print("=" * 100)
    lc = Path(args.label_ceiling)
    if lc.exists():
        j = json.loads(lc.read_text(encoding="utf-8"))
        w, r = j.get("wazan", {}), j.get("root", {})
        print("  silver LABEL vs human gold (no model involved, n=%s gold rows with a label):"
              % w.get("n"))
        print("     raw exact %.3f | hamza-normalised %.3f | radical-slot set %.3f"
              % (w.get("raw_correct", 0) / max(w.get("n", 1), 1),
                 w.get("norm_correct", 0) / max(w.get("n", 1), 1),
                 w.get("slot_correct", 0) / max(w.get("n", 1), 1)))
        print("     root  %.3f (n=%s)" % (r.get("correct", 0) / max(r.get("n", 1), 1), r.get("n")))
    else:
        print("  (no %s — run src/compare_silver_vs_gold.py first)" % lc)
    print("  CALIMA-vs-human ceilings: case macro-F1 %.3f, root %.3f  (a GOLD-trained arm"
          % (CEIL["case_macro_f1"], CEIL["root_accuracy"]))
    print("  beating these proves nothing; only the SILVER rows are a ceiling comparison.)")

    out = ROOT / "dist" / "ablation_summary.json"
    out.write_text(json.dumps({"rows": rows, "summary": summary,
                              "ceilings": CEIL, "parity": d.get("parity"),
                              "vocab_sizes": d.get("vocab_sizes")},
                             indent=1, ensure_ascii=False), encoding="utf-8")
    print("\nwrote %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
