"""dry_run_ablation.py — exercise the notebook's NEW code paths locally, at smoke scale.

NOT a substitute for the Kaggle run. It exists because the notebook's grid calls
train()/evaluate()/score_human_gold() in ways the previous round never did (a train
path override, a shared vocabulary object, a human-gold scorer), and a signature error
found here costs two minutes instead of a 45-minute GPU run.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import eval_harness as EH
from model_arms import load_config, read_records, Vocabs, resolve_device
from train import train, evaluate

cfg = load_config(smoke=True)
cfg["data"]["limit_train"] = 200
cfg["data"]["limit_dev"] = 40
cfg["paths"]["silver_train"] = "data/out/tashkeela-train.jsonl"
cfg["paths"]["silver_dev"] = "data/out/tashkeela-dev.jsonl"
device = resolve_device(cfg)

GOLD_TR = read_records(cfg["paths"]["train"], cfg["data"]["limit_train"])
SILV_TR = read_records(cfg["paths"]["silver_train"], cfg["data"]["limit_train"])
V = Vocabs(GOLD_TR + SILV_TR, cfg["data"]["min_freq"], cfg["data"]["max_vocab"])
sizes = V.sizes()
print("union sizes:", sizes)
assert sizes["radical"] > 5 and sizes["wazan"] > 5

ABL = {"gold": (cfg["paths"]["train"], cfg["paths"]["dev"]),
       "silver": (cfg["paths"]["silver_train"], cfg["paths"]["silver_dev"])}
DEVS = {"gold": read_records(cfg["paths"]["dev"], cfg["data"]["limit_dev"]),
        "silver": read_records(cfg["paths"]["silver_dev"], cfg["data"]["limit_dev"])}
GOLD = EH.load_human_gold(cfg["paths"]["human_gold"])

for src in ("gold", "silver"):
    for arm in ("treatment", "baseline"):
        t0 = time.time()
        model, hist, _, _ = train(cfg, arm, 7, device, quiet=True,
                                  train_path=ABL[src][0], dev_path=ABL[src][1],
                                  vocab_sents=V)
        res = evaluate(model, DEVS[src], V, cfg, sizes, device)
        if src == "silver":
            res["padt_dev"] = evaluate(model, DEVS["gold"], V, cfg, sizes, device)
        g = EH.score_human_gold(model, V, GOLD, device, cfg["data"]["max_len"])
        print("%-8s %-10s %.0fs  in-domain case macroF1 %s  root %s | gold wz_raw %.3f "
              "slots %.3f root %.3f oov %.2f"
              % (src, arm, time.time() - t0,
                 round((res.get("case") or {}).get("macro_f1", float("nan")), 3),
                 round((res.get("root") or {}).get("accuracy", float("nan")), 3),
                 g["wazan"]["accuracy"], g["wazan_radical_slots"]["accuracy"],
                 g["root"]["accuracy"], g["oov_rate"]))
        assert set(g) >= {"wazan", "wazan_radical_slots", "root", "case_majority_macro_f1"}
print("\nDRY RUN OK — every notebook path exercised at smoke scale")
