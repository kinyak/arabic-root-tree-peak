import argparse
import json
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, "src")
import torch
from model_arms import Arm, Vocabs, load_config, load_for_eval
import eval_harness as EH
from paths import GOLD_JSONL

DEFAULT_CHECKPOINTS = [
    "dist/kaggle-output/checkpoints/gold-treatment-s20261009.pt",
    "dist/kaggle-output/checkpoints/gold-treatment-s20261010.pt",
    "dist/kaggle-output/checkpoints/gold-treatment-s20261011.pt",
]

# Fallbacks if dist/kaggle-output not populated
FALLBACK_CHECKPOINTS = [
    "checkpoints/gold-treatment-s20261009.pt",
    "checkpoints/gold-treatment-s20261010.pt",
    "checkpoints/gold-treatment-s20261011.pt",
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Score new checkpoints against gold evaluation")
    ap.add_argument("--ckpts", nargs="*", default=None, help="Paths to checkpoints to score")
    ap.add_argument("--out", default="dist/new_checkpoints_scores.json", help="Path to output JSON")
    args = ap.parse_args()

    checkpoints = args.ckpts
    if not checkpoints:
        if any(Path(p).exists() for p in DEFAULT_CHECKPOINTS):
            checkpoints = DEFAULT_CHECKPOINTS
        else:
            checkpoints = FALLBACK_CHECKPOINTS

    gold = EH.load_human_gold(GOLD_JSONL)
    results = {}

    for ck_path in checkpoints:
        p = Path(ck_path)
        if not p.exists():
            print(f"Skipping {p}: file not found")
            continue
        tag = p.stem
        print(f"\n{'='*70}\nScoring: {tag}\n{'='*70}")
        t0 = time.time()
        ck = torch.load(p, map_location="cpu", weights_only=False)
        V = Vocabs.from_dict(ck["vocab"])
        sizes = {**ck.get("sizes", {}), **V.sizes()}
        cfg = ck.get("cfg") or load_config()

        model = Arm(cfg, sizes, ck["arm"])
        load_for_eval(model, ck["model"])
        model.eval()

        res = EH.score_human_gold(model, V, gold, device=torch.device("cpu"))
        elapsed = time.time() - t0
        print(f"Time taken: {elapsed:.2f}s")
        print(f"Wazan raw        : {res['wazan']['accuracy']*100:.2f}% ({res['wazan']['correct']}/{res['wazan']['n']})")
        print(f"Wazan canon      : {res['wazan_canonical']['accuracy']*100:.2f}% ({res['wazan_canonical']['correct']}/{res['wazan_canonical']['n']})")
        beamed = res.get('root_whole_beamed')
        if beamed:
            print(f"Root beamed      : {beamed['accuracy']*100:.2f}% ({beamed['correct']}/{beamed['n']})")
        print(f"Case macro-F1    : {res.get('case', {}).get('macro_f1', 0.0):.4f}")
        if "final_surface" in res:
            for engine, s_res in res["final_surface"].items():
                tok_yield = (s_res.get('token_exact_yield') or 0.0) * 100
                stem_yield = (s_res.get('stem_yield') or 0.0) * 100
                print(f"Final surface ({engine}): token_exact={tok_yield:.2f}% ({s_res.get('token_exact_matches')}/{s_res.get('n')}), stem_yield={stem_yield:.2f}% ({s_res.get('stem_matches')}/{s_res.get('n')})")

        results[tag] = {
            "wazan": res["wazan"],
            "wazan_canonical": res.get("wazan_canonical"),
            "root": res["root"],
            "root_whole_beamed": beamed,
            "case": res.get("case"),
            "final_surface": res.get("final_surface"),
            "elapsed": elapsed
        }

    out_file = Path(args.out)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved all results to {out_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
