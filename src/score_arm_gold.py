"""Score ONE arm's checkpoint against the human gold through the SHARED metric.

WHY THIS EXISTS
    `eval_harness.score_human_gold` now renders the model's OWN (root, wazān, case) and
    scores it against the human gold at the STEM level. That is the metric both arms
    must be compared by (A3). This script is the local driver for it: it loads a
    checkpoint, rebuilds the exact vocabulary it was trained with, and prints the
    per-head blocks next to the final-surface block.

    A checkpoint is only meaningful together with ITS vocabulary — a mismatched vocab
    silently misaligns every head. `build_union_vocab.py` verifies the vocab against
    the sizes stored IN the checkpoint and refuses to write it on a mismatch.
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys

import torch

import eval_harness as EH
from model_arms import Arm, Vocabs, load_config
from paths import resolve


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--vocab", default="dist/union_vocab_full.pkl")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    ck = torch.load(resolve(args.ckpt), map_location="cpu", weights_only=False)
    # PREFER the vocabulary stored IN the checkpoint. A checkpoint is only meaningful
    # together with the exact vocabulary it was trained with — a mismatched vocab
    # silently misaligns every head. Rebinding from a separate file is a last resort
    # and is only safe when the sizes agree.
    if ck.get("vocab"):
        V = Vocabs.from_dict(ck["vocab"])
        print(f"vocabulary : EMBEDDED in the checkpoint (sizes {V.sizes()})")
    else:
        if not resolve(args.vocab).exists():
            print(f"  !! the checkpoint carries NO vocabulary and {args.vocab} does not exist.")
            print("     A checkpoint is only meaningful with the exact vocabulary it was")
            print("     trained with, so this one cannot be scored here. Checkpoints written")
            print("     from now on embed their vocab (model_arms.Vocabs.to_dict), so re-run")
            print("     the training to get a scoreable artifact rather than guessing one.")
            return 1
        with open(resolve(args.vocab), "rb") as fh:
            V = pickle.load(fh)
        print(f"vocabulary : rebound from {args.vocab} (NOT stored in the checkpoint)")
        if V.sizes() != ck.get("sizes"):
            print("  !! size mismatch — refusing to score a misaligned checkpoint")
            print(f"     vocab {V.sizes()}")
            print(f"     ckpt  {ck.get('sizes')}")
            return 1
    cfg = ck.get("cfg") or load_config()
    sizes = {**ck.get("sizes", {}), **V.sizes()}
    arm = ck["arm"]
    print("=" * 84)
    print(f"ARM '{arm}' · source {ck.get('source')} · seed {ck.get('seed')}")
    print(f"checkpoint {args.ckpt}")
    print("=" * 84)

    model = Arm(cfg, sizes, arm)
    missing, unexpected = model.load_state_dict(ck["model"], strict=False)
    if missing or unexpected:
        print(f"  !! state_dict mismatch: missing={list(missing)[:4]} "
              f"unexpected={list(unexpected)[:4]}")
    model.eval()
    n = sum(p.numel() for p in model.parameters())
    print(f"  parameters loaded: {n:,}")

    gold = EH.load_human_gold()
    res = EH.score_human_gold(model, V, gold, device=torch.device("cpu"))

    print(f"\n  gold rows {res['gold_rows']} · context tokens {res['contexts_scored']} "
          f"· OOV rate {res['oov_rate']}")
    print("\n  -- PER-HEAD (each on the rows that carry that human label) --")
    heads_to_show = [("wazan", "wazān raw"), ("wazan_hamza_normalised", "wazān hamza-norm")]
    if "wazan_canonical" in res:
        heads_to_show.append(("wazan_canonical", "wazān canonical-vocalized"))
    heads_to_show.extend([
        ("wazan_hamza_normalised_diacritic_free", "wazān diac-free"),
        ("wazan_radical_slots", "wazān radical-slots"),
        ("root", "root")
    ])
    for k, lab in heads_to_show:
        b = res.get(k)
        if b:
            print(f"    {lab:<26} {b['correct']:>4}/{b['n']:<4} = {b['accuracy']*100:5.1f}%")
    if "case" in res:
        c = res["case"]
        print(f"    {'case macro-F1':<26} {c['macro_f1']:.3f}   "
              f"(majority-class {c.get('majority_macro_f1', 0):.3f}, "
              f"n={c['n']})")

    print("\n  -- SHARED FINAL-SURFACE METRIC (A3): coverage and accuracy SEPARATE --")
    print(f"    {'engine':<8} {'cover':>7} {'abstain':>8} {'acc|covered':>12} "
          f"{'yield':>7} {'token':>7} {'skel':>7}")
    for e, s in res["final_surface"].items():
        print(f"    {e:<8} {s['coverage']*100:6.1f}% {s['abstain']:>8} "
              f"{s['stem_accuracy_of_covered']*100:11.1f}% {s['stem_yield']*100:6.1f}% "
              f"{s['token_exact_yield']*100:6.1f}% {s['skeleton_yield']*100:6.1f}%")
    print("\n    defect buckets (engine v2), first reconciling rule per miss:")
    for k, v in (res["final_surface"].get("v2") or {}).get("defect_buckets", {}).items():
        print(f"      {k:<26} {v:>4}")

    if args.json_out:
        with open(resolve(args.json_out), "w", encoding="utf-8") as fh:
            json.dump(res, fh, ensure_ascii=False, indent=2, default=str)
        print(f"\n  json -> {args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
