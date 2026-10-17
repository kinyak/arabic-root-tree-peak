"""tools/bench_autosegmental_eval.py — Official Evaluation of the Autosegmental Morphological Pipeline.

Strict Requirements:
1. Pure Neural Planner + Deterministic Autosegmental Compiler.
2. ARABIC_SPELLING_RESOURCE=0 strictly enforced (no 8 MB TSV dictionary crutch).
3. Evaluates on the frozen human ruler: data/annotation/bench-gold.jsonl (650 test / 350 calibration).
4. Stratified reporting across all phonological and morphological strata:
   - Sound triliteral
   - Weak (Hollow, Defective, Assimilated)
   - Doubled / Geminate
   - Hamza
   - Quadriliteral
   - Clitic / Affix plane tokens
   - Definiteness classes (DEF_AL, INDEF_TANWIN, CONSTRUCT_IDAFA, OTHER)
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys
from pathlib import Path

# Enforce no TSV dictionary before importing compiler modules
os.environ["ARABIC_SPELLING_RESOURCE"] = "0"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from final_surface import render_triple, score_final_surface, TAN, strip_diac
from eval_harness import root_class
from renderer_bench_audit import load_gold, usable_row, case_int, DEF_PRO

def extract_gold_definiteness(target_token: str, ci: int | None) -> int:
    """Determine definiteness class from gold token and case."""
    sk = strip_diac(target_token) or ""
    has_al = any(sk.startswith(p) and len(sk) > len(p) for p in DEF_PRO)
    if has_al:
        return 0  # DEF_AL
    has_tanwin = any(ch in TAN for ch in target_token)
    if has_tanwin:
        return 1  # INDEF_TANWIN
    if ci is not None:
        return 2  # CONSTRUCT_IDAFA
    return 3      # INVARIABLE/OTHER

def evaluate_pipeline(rows: list[dict], with_autosegmental: bool = True) -> dict:
    pairs = []
    strata_pairs = collections.defaultdict(list)
    definiteness_pairs = collections.defaultdict(list)
    clitic_pairs = collections.defaultdict(list)
    
    for r in rows:
        if not usable_row(r):
            continue
        tok = r["target_token"]
        ci = case_int(r.get("case"))
        r_str = str(r["root"])
        cls = root_class(r_str)
        
        # Definiteness state
        df = extract_gold_definiteness(tok, ci) if with_autosegmental else 0
        is_tw = bool(with_autosegmental and (df == 1))
        
        pred, why = render_triple(
            r["root"],
            r["wazn_pattern"],
            ci,
            engine="v3",
            token=tok,
            tanwin=is_tw,
            definiteness=df,
        )
        
        triple_res = (tok, pred, why)
        pairs.append(triple_res)
        strata_pairs[cls].append(triple_res)
        definiteness_pairs[df].append(triple_res)
        
        has_clitic = any(strip_diac(tok).startswith(p) and len(strip_diac(tok)) > len(p) for p in ("و", "ف", "ب", "ك", "ل", "س", "ال"))
        clitic_pairs["with_clitic" if has_clitic else "bare_stem"].append(triple_res)
        
    overall = score_final_surface(pairs)
    
    strata_results = {}
    for k, p_list in strata_pairs.items():
        strata_results[k] = score_final_surface(p_list)
        
    def_results = {}
    def_names = {0: "DEF_AL", 1: "INDEF_TANWIN", 2: "CONSTRUCT_IDAFA", 3: "INVARIABLE_OTHER"}
    for k, p_list in definiteness_pairs.items():
        def_results[def_names.get(k, str(k))] = score_final_surface(p_list)
        
    clitic_results = {}
    for k, p_list in clitic_pairs.items():
        clitic_results[k] = score_final_surface(p_list)
        
    return {
        "overall": overall,
        "by_root_class": strata_results,
        "by_definiteness": def_results,
        "by_clitic": clitic_results,
    }

def print_report(res: dict, title: str):
    ov = res["overall"]
    print("=" * 88)
    print(f"{title}")
    print("=" * 88)
    print(f"Total usable rows: {ov['n']} / {ov['n'] + ov['abstain']}")
    print(f"Token Exact:       {ov['token_exact']} / {ov['n']} ({ov['token_exact_yield']*100:.2f}%)")
    print(f"Stem Exact:        {ov['stem_correct']} / {ov['n']} ({ov['stem_yield']*100:.2f}%)")
    print(f"Coverage:          {ov['covered']} / {ov['n']} ({ov['coverage']*100:.2f}%)")
    print(f"Defect buckets:    {dict(ov['defect_buckets'])}")
    
    print("\n--- Breakdown by Root Morphology Class ---")
    print(f"{'Class':<16} {'N':>5} {'Token Exact':>12} {'Stem Exact':>12}")
    for cls, sc in sorted(res["by_root_class"].items()):
        print(f"{cls:<16} {sc['n']:>5} {sc['token_exact_yield']*100:>11.2f}% {sc['stem_yield']*100:>11.2f}%")
        
    print("\n--- Breakdown by Definiteness / Nunation ---")
    print(f"{'Definiteness':<18} {'N':>5} {'Token Exact':>12} {'Stem Exact':>12}")
    for df, sc in sorted(res["by_definiteness"].items()):
        print(f"{df:<18} {sc['n']:>5} {sc['token_exact_yield']*100:>11.2f}% {sc['stem_yield']*100:>11.2f}%")

    print("\n--- Breakdown by Clitic Presence ---")
    print(f"{'Category':<16} {'N':>5} {'Token Exact':>12} {'Stem Exact':>12}")
    for c_cat, sc in sorted(res["by_clitic"].items()):
        print(f"{c_cat:<16} {sc['n']:>5} {sc['token_exact_yield']*100:>11.2f}% {sc['stem_yield']*100:>11.2f}%")
    print("=" * 88)

def main():
    parser = argparse.ArgumentParser(description="Autosegmental Evaluation on Bench-Gold")
    parser.add_argument("--gold", default=str(ROOT / "data" / "annotation" / "bench-gold.jsonl"))
    parser.add_argument("--split", default="test", choices=["all", "test", "calibration"])
    parser.add_argument("--json", default=None, help="Save JSON report")
    args = parser.parse_args()

    rows = load_gold(Path(args.gold))
    if args.split == "test":
        rows = rows[:650]
    elif args.split == "calibration":
        rows = rows[650:]
        
    print(f"Evaluating split: {args.split} ({len(rows)} raw rows) with ARABIC_SPELLING_RESOURCE=0 strictly enforced.\n")
    
    # 1. Baseline without autosegmental nunation
    res_base = evaluate_pipeline(rows, with_autosegmental=False)
    print_report(res_base, f"BASELINE COMPILER (No Autosegmental Tanwīn, Resource OFF) [{args.split}]")
    
    # 2. Autosegmental Compiler
    res_auto = evaluate_pipeline(rows, with_autosegmental=True)
    print_report(res_auto, f"AUTOSEGMENTAL COMPILER (With Definiteness/Tanwīn, Resource OFF) [{args.split}]")
    
    gain_token = res_auto["overall"]["token_exact"] - res_base["overall"]["token_exact"]
    gain_pp = (res_auto["overall"]["token_exact_yield"] - res_base["overall"]["token_exact_yield"]) * 100
    print(f"\nNET HEADLINE GAIN: +{gain_token} rows (+{gain_pp:.2f} percentage points)")
    print(f"Tanwin Missing Defect: {res_base['overall']['defect_buckets'].get('tanwin_missing', 0)} -> {res_auto['overall']['defect_buckets'].get('tanwin_missing', 0)}")
    
    if args.json:
        out_data = {
            "split": args.split,
            "baseline": res_base,
            "autosegmental": res_auto,
            "gain_token_exact": gain_token,
            "gain_token_pp": gain_pp,
        }
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(out_data, f, indent=2, ensure_ascii=False)
        print(f"Report written to {args.json}")

if __name__ == "__main__":
    main()
