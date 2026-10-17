"""tools/rescore_cpu.py — CPU re-scoring for checkpoints, WITHOUT the two defects that invalidated
the first version of this tool.

WHAT WENT WRONG BEFORE (§2ci). The first version had two failures that made its table meaningless:
  1. It called `model.load_state_dict(ck["model"], strict=False)` against a model built from the
     CURRENT config. Every checkpoint here is missing `case_gov_q/k/v`, the four newer heads, and
     `char_encoder.char_pos` / `pool_gate.*` — and the latter two are in the INPUT PATHWAY, so they
     were left at random init and injected noise into the whole network. Root accuracy came out far
     below the checkpoint's trained value. Now: `load_for_eval`, which DISABLES any module whose
     weights are absent, and says which heads are untrained.
  2. It never set `ARABIC_SPELLING_RESOURCE`, so the "neural compiler" figures silently included the
     8 MB corpus dictionary. The two modes answer DIFFERENT questions and are now run and LABELLED
     separately:
        resource_off  — pure neural planner + rule compiler.  THE THESIS NUMBER.
        resource_on   — the hybrid production system (rule compiler + corpus lexicon).

Usage:
    python tools/rescore_cpu.py                     # all default checkpoints
    python tools/rescore_cpu.py --ckpts a.pt b.pt
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import torch                                                     # noqa: E402
import eval_harness as EH                                        # noqa: E402
from model_arms import Arm, Vocabs, load_config, load_for_eval    # noqa: E402

CHECKPOINT_ROOT = "checkpoints"
ARMS = ("silver", "gold")
KINDS = ("treatment", "baseline")
SEEDS = ("s20261009", "s20261010", "s20261011")
DEFAULT_CHECKPOINTS = [f"{CHECKPOINT_ROOT}/{a}-{k}-{s}.pt"
                       for a in ARMS for k in KINDS for s in SEEDS]

# A head is only reported if its weights are actually in the checkpoint.
OPTIONAL_HEADS = ("wazan_canonical",)


def _get(d, *path, default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def score_checkpoint(ckpt_path: Path | str, gold: list[dict], device: torch.device):
    ckpt_path = Path(ckpt_path)
    if not ckpt_path.exists():
        return None

    t0 = time.time()
    ck = torch.load(ckpt_path, map_location=device, weights_only=False)
    V = Vocabs.from_dict(ck["vocab"])
    sizes = {**ck.get("sizes", {}), **V.sizes()}
    cfg = ck.get("cfg") or load_config()
    arm = ck["arm"]

    model = Arm(cfg, sizes, arm).to(device)
    missing, disabled = load_for_eval(model, ck["model"], verbose=False)
    model.eval()

    untrained = [h for h in OPTIONAL_HEADS
                 if any(k.startswith(f"h_{h}.") for k in missing)]

    rec = {
        "checkpoint": ckpt_path.name,
        "arm": arm,
        "source": ck.get("source"),
        "seed": ck.get("seed"),
        "n_missing_tensors": len(missing),
        "disabled_modules": disabled,
        "untrained_heads": untrained,
        "elapsed_sec": None,
        "modes": {},
    }

    for mode, env in (("resource_off", "0"), ("resource_on", "1")):
        os.environ["ARABIC_SPELLING_RESOURCE"] = env
        res = EH.score_human_gold(model, V, gold, device=device)
        fs_map = res.get("final_surface", {})
        rec["modes"][mode] = {
            "wazan_raw": _get(res, "wazan", "accuracy"),
            "wazan_hamza_norm": _get(res, "wazan_hamza_normalised", "accuracy"),
            "wazan_canonical": (None if "wazan_canonical" in untrained
                                else _get(res, "wazan_canonical", "accuracy")),
            "wazan_slots": _get(res, "wazan_radical_slots", "accuracy"),
            "root": _get(res, "root", "accuracy"),
            "case_macro_f1": _get(res, "case", "macro_f1"),
            "surface_v3_stem": _get(fs_map, "v3", "stem_yield") if _get(fs_map, "v3", "stem_yield") is not None else (_get(fs_map, "v3_resource_off_argmax" if mode == "resource_off" else "v3_resource_on", "stem_yield")),
            "surface_v3_rasm_stem": _get(fs_map, "v3_rasm", "stem_yield"),
            "surface_v3_rasm_token": _get(fs_map, "v3_rasm", "token_exact_yield"),
            "v3_res_off_argmax": _get(fs_map, "v3_resource_off_argmax", "stem_yield"),
            "v3_res_off_joint": _get(fs_map, "v3_resource_off_joint", "stem_yield"),
            "v3_res_on": _get(fs_map, "v3_resource_on", "stem_yield"),
            "v3_res_on_joint": _get(fs_map, "v3_resource_on_joint", "stem_yield"),
        }
    os.environ["ARABIC_SPELLING_RESOURCE"] = "1"
    rec["elapsed_sec"] = round(time.time() - t0, 2)
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description="CPU re-scoring (leak-free, both resource modes)")
    ap.add_argument("--ckpts", nargs="*", default=DEFAULT_CHECKPOINTS)
    ap.add_argument("--gold", default=str(ROOT / "data/annotation/gold-tashkeela-300.jsonl"))
    ap.add_argument("--out", default=str(ROOT / "results/rescore_cpu_results.json"))
    args = ap.parse_args()

    gold = EH.load_human_gold(args.gold)
    device = torch.device("cpu")

    print("=" * 118)
    print("CPU RE-SCORING — leak-free decoder, safe checkpoint load, BOTH resource modes")
    print("=" * 118)
    print(f"gold: {len(gold)} rows ({args.gold})")
    print()
    print("  resource_off = pure neural planner + rule compiler   <- THE THESIS NUMBER")
    print("  resource_on  = hybrid (rule compiler + 8 MB corpus lexicon)")
    print()
    hdr = (f"{'checkpoint':<30} {'mode':<13} {'wz_raw':>7} {'root':>7} {'caseF1':>7} "
           f"{'surf_stem':>10} {'rasm_tok':>9} {'miss':>5} {'t(s)':>6}")
    print(hdr)
    print("-" * 118)

    results = []
    for ckpt in args.ckpts:
        p = Path(ckpt) if Path(ckpt).is_absolute() else (ROOT / ckpt)
        rec = score_checkpoint(p, gold, device)
        if rec is None:
            continue
        results.append(rec)
        for mode in ("resource_off", "resource_on"):
            m = rec["modes"][mode]
            f = lambda v, s=100: ("     n/a" if v is None else f"{v*s:>6.1f}%".rjust(7))
            print(f"{rec['checkpoint']:<30} {mode:<13} {f(m['wazan_raw'])} {f(m['root'])} "
                  f"{(m['case_macro_f1'] or 0):>7.3f} {f(m['surface_v3_stem'])} "
                  f"{f(m['surface_v3_rasm_token'])} {rec['n_missing_tensors']:>5} "
                  f"{rec['elapsed_sec']:>5.1f}")
        if rec["disabled_modules"] or rec["untrained_heads"]:
            print(f"    ^ {rec['checkpoint']}: disabled={rec['disabled_modules']} "
                  f"untrained={rec['untrained_heads']}")
    print("-" * 118)

    # Print requested 3-column comparison table: gold_v3_res_off_joint, gold_v3_res_off_argmax, gold_v3_res_on
    print("\n" + "=" * 110)
    print("FINAL EVALUATION TABLE (Gold-300 Benchmark)")
    print("=" * 110)
    cmp_hdr = (f"{'Checkpoint':<32} {'Root':>8} {'Wazan':>8} "
               f"{'res_off_joint':>16} {'res_off_argmax':>16} {'res_on (arg)':>14} {'res_on (joint)':>16}")
    print(cmp_hdr)
    print("-" * 110)
    for r in results:
        moff = r["modes"]["resource_off"]
        mon = r["modes"]["resource_on"]
        ck_name = r["checkpoint"]
        rt = f"{moff['root']*100:.1f}%" if moff.get("root") is not None else "n/a"
        wz = f"{moff['wazan_raw']*100:.1f}%" if moff.get("wazan_raw") is not None else "n/a"
        off_joint = f"{moff['surface_v3_rasm_stem']*100:.1f}%" if moff.get("surface_v3_rasm_stem") is not None else "n/a"
        off_arg = f"{moff['surface_v3_stem']*100:.1f}%" if moff.get("surface_v3_stem") is not None else "n/a"
        on_arg = f"{mon['surface_v3_stem']*100:.1f}%" if mon.get("surface_v3_stem") is not None else "n/a"
        on_joint = f"{mon['surface_v3_rasm_stem']*100:.1f}%" if mon.get("surface_v3_rasm_stem") is not None else "n/a"
        print(f"{ck_name:<32} {rt:>8} {wz:>8} {off_joint:>16} {off_arg:>16} {on_arg:>14} {on_joint:>16}")
    print("=" * 110)

    os.makedirs(Path(args.out).parent, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump({"note": "leak-free decoder; both resource modes; safe checkpoint load",
                   "results": results}, fh, indent=2)
    print(f"\nSaved {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
