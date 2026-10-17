"""Run the (now unified) dev evaluation locally from a retrieved checkpoint — zero GPU.

Reports BOTH root numbers, which is the point of the exercise:
  · per-slot radical accuracy  — head-training progress (a 3-radical token counts 3x)
  · whole-root exact match     — end-to-end fidelity, via the SHARED decode_root_slots
Only the second is comparable with the human-gold path.

Run: .venv/Scripts/python.exe src/score_dev_local.py --ckpt <path.pt>
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.chdir(Path(__file__).resolve().parent.parent)

import torch

import train as T
from model_arms import Arm, Vocabs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--split", default="dev", choices=("dev", "train"))
    args = ap.parse_args()

    ck = torch.load(args.ckpt, map_location="cpu", weights_only=False)
    cfg = ck.get("cfg") or T.load_config()
    V = Vocabs.from_dict(ck["vocab"])
    # prefer the config the checkpoint was trained with (see diagnose_gold_checkpoint)
    model = Arm(ck.get("cfg") or cfg, ck["sizes"], ck["arm"])
    model.load_state_dict(ck["model"], strict=False)
    model.eval()

    path = cfg["paths"][args.split]
    lim = cfg["data"]["limit_dev"] if args.split == "dev" else cfg["data"]["limit_train"]
    recs = T.read_records(Path(path), lim)
    print(f"{ck['arm']:>9} · source {ck.get('source')} · seed {ck.get('seed')} · "
          f"{args.split} units {len(recs):,}")

    res = T.evaluate(model, recs, V, cfg, ck["sizes"], "cpu")
    # evaluate() names its target source from the DATA it was given, not from training, so label it here
    print(f"  root  (PER-SLOT radical accuracy) : {res['root']['accuracy']*100:6.2f}%  n={res['root']['n']:,}")
    rw = res.get("root_whole")
    if rw:
        print(f"  root  (WHOLE-ROOT exact match)    : {rw['accuracy']*100:6.2f}%  n={rw['n']:,}"
              f"   <- comparable with the human-gold path")
    c = res.get("case") or {}
    if c:
        print(f"  case macro-F1 : {c.get('macro_f1', float('nan')):.4f}  "
              f"(majority {c.get('majority_macro_f1', float('nan')):.3f})")
    for k in ("wazan", "ntp"):
        if res.get(k):
            print(f"  {k:<13} (per-slot) : {res[k]['accuracy']*100:6.2f}%  n={res[k]['n']:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
