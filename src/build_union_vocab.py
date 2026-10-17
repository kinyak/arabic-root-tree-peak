"""Rebuild the ablation's ONE shared vocabulary and check it against the checkpoint.

WHY THIS IS SAFE TO REBUILD (and the check that makes it safe)
    `train.py` does not save the vocab with the checkpoint, but `Vocabs` is a pure
    function of the sentence list and the config: radical = sorted(set), wazān =
    sorted(set), form = most_common with min_freq. The notebook builds it as

        V = Vocabs(GOLD_TR + SILV_TR, cfg['data']['min_freq'], cfg['data']['max_vocab'])

    so rebuilding it from the same records must reproduce it — and the checkpoint
    carries `sizes`, so the rebuild is VERIFIED rather than assumed. If the sizes do
    not match, every head index is misaligned and the model would silently produce
    garbage; that is why this prints the comparison and refuses to continue on a
    mismatch instead of trusting it.
"""
from __future__ import annotations

import pickle
import sys

import torch

from model_arms import Vocabs, read_records
from model_arms import load_config
from paths import resolve

CKPT = "dist/kaggle-output/checkpoints/gold-treatment-s20261009.pt"
OUT = "dist/union_vocab_full.pkl"


def main() -> int:
    cfg = load_config()
    print(f"limit_train = {cfg['data']['limit_train']} · min_freq = {cfg['data']['min_freq']}"
          f" · max_vocab = {cfg['data']['max_vocab']}")
    # resolve() so this works from src/ as well as the repo root: the config declares
    # root-relative paths, and passing them straight to open() from src/ raised a
    # FileNotFoundError that looked like missing data.
    gold = read_records(resolve(cfg["paths"]["train"]), cfg["data"]["limit_train"])
    silv = read_records(resolve(cfg["paths"]["silver_train"]), None)
    print(f"gold sentences {len(gold):,} · silver sentences {len(silv):,}")

    V = Vocabs(gold + silv, cfg["data"]["min_freq"], cfg["data"]["max_vocab"])
    sizes = V.sizes()
    print(f"rebuilt sizes: {sizes}")

    ck = torch.load(resolve(CKPT), map_location="cpu", weights_only=False)
    want = ck["sizes"]
    print(f"checkpoint   : {want}")
    ok = sizes == want
    print(f"\nSIZES MATCH: {ok}")
    if not ok:
        print("  MISMATCH -> the head indices are NOT aligned; refusing to write the vocab.")
        for k in sorted(set(sizes) | set(want)):
            if sizes.get(k) != want.get(k):
                print(f"    {k}: rebuilt {sizes.get(k)} vs ckpt {want.get(k)}")
        return 1
    with open(resolve(OUT), "wb") as fh:
        pickle.dump(V, fh)
    print(f"  wrote {OUT}")
    print(f"  radical vocab ({len(V.radical)}): {sorted(V.radical)[:12]} ...")
    print(f"  wazān has {len(V.wazan)} templates; sample: "
          f"{[w for w in sorted(V.wazan)[:6]]}")
    print(f"  checkpoint arm={ck.get('arm')} source={ck.get('source')} seed={ck.get('seed')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
