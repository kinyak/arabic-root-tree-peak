"""Print the raw root-head argmax vs the inv_r lookup for the first gold rows.

WHAT THIS IS FOR
    The human-gold score was root 0/278 with 296/296 abstentions bucketed `root_len_mismatch`.
    `eval_harness.py:264` builds the predicted root as
        "".join(inv_r.get(s, "") for s in out["root"][0, idx].argmax(-1).tolist() if s)
    — note the `if s`, which DELETES any slot whose predicted id is 0. And id 0 is `'<pad>'`
    (confirmed in the checkpoint's vocab: {'<pad>': 0, 'ء': 1, ...}). So a model that predicts PAD
    produces an EMPTY root, and the renderer then reports the misleading reason
    `root_len_mismatch` (length 0 vs a 3-slot pattern) rather than "no root was predicted".

Zero GPU. Run:
    .venv/Scripts/python.exe src/diagnose_gold_root_decode.py --ckpt <path.pt> [--rows 5]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.chdir(Path(__file__).resolve().parent.parent)

import torch

from model_arms import Arm, Vocabs
from eval_harness import parse_gold_context, to_bare_root_str, load_human_gold


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--rows", type=int, default=5)
    args = ap.parse_args()

    ck = torch.load(args.ckpt, map_location="cpu", weights_only=False)
    V = Vocabs.from_dict(ck["vocab"])
    cfg = ck.get("cfg")
    # the checkpoint carries the config it was TRAINED with — use it, so an architecture
    # flag flipped after the run cannot make a good checkpoint unloadable
    model = Arm(ck.get("cfg") or cfg, ck["sizes"], ck["arm"])
    model.load_state_dict(ck["model"], strict=False)
    model.eval()

    inv_r = {i: c for c, i in V.radical.items()}
    inv_w = {i: w for w, i in V.wazan.items()}
    gold = load_human_gold(cfg["paths"]["human_gold"])
    max_len = cfg["data"]["max_len"]

    print("=" * 118)
    print("ROOT DECODING: raw argmax vs inv_r lookup  (inv_r id 0 = %r)" % inv_r.get(0))
    print("=" * 118)
    print(f"checkpoint {args.ckpt}")
    print(f"inv_r: {len(inv_r)} ids, key type {type(list(inv_r.keys())[0]).__name__}, "
          f"id 0 -> {inv_r.get(0)!r}")

    for g in gold[:args.rows]:
        toks, idx = parse_gold_context(g.get("context") or "")
        if not toks:
            continue
        if len(toks) > max_len:
            lo = max(0, min(idx - max_len // 2, len(toks) - max_len))
            toks = toks[lo:lo + max_len]
            idx -= lo
        x = torch.tensor([[V.encode(t) for t in toks]])
        # v12: build character tensor
        max_char_len = 20
        x_char_list = []
        for t in toks:
            chars = [V.char.get(c, 0) for c in t[:max_char_len]]
            chars += [0] * (max_char_len - len(chars))
            x_char_list.append(chars)
        x_char = torch.tensor([x_char_list])
        with torch.no_grad():
            out = model(x, x_char)
        slots = out["root"][0, idx].argmax(-1).tolist()
        letters = [inv_r.get(s, "<MISS>") for s in slots]
        # the code path's join (filter `if s` ON) vs the unfiltered join
        joined_no_filter = "".join(letters)
        joined_filtered = "".join(inv_r.get(s, "") for s in slots if s)
        _r = to_bare_root_str(joined_filtered)
        pw = inv_w.get(int(out["wazan"][0, idx].argmax()), None) if out["wazan"] is not None else None
        n_digits = sum(ch in "1234" for ch in (pw or ""))
        print("\n" + "-" * 118)
        print(f"form {g.get('form')!r}   gold root={g.get('t_root_arabic')!r} "
              f"gold pattern={g.get('t_wazan_pattern')!r}")
        print(f"  raw argmax slots            : {slots}   (mask/pad is id 0 = {inv_r.get(0)!r})")
        print(f"  inv_r per slot              : {letters}")
        print(f"  join WITHOUT the `if s`     : {joined_no_filter!r}  (len {len(joined_no_filter)})")
        print(f"  join WITH the `if s` filter : {joined_filtered!r}  (len {len(joined_filtered)})"
              f"   <- what the code actually uses")
        print(f"  _r after to_bare_root_str   : {_r!r}  (len {len(_r)})")
        print(f"  predicted pattern pw        : {pw!r}  -> {n_digits} slots")
        verdict = ("ROOT IS EMPTY — all slots predicted PAD, so `if s` produced '' and the "
                   "renderer calls it root_len_mismatch"
                   if not _r else
                   f"len(root)={len(_r)} vs {n_digits} pattern slots -> "
                   f"{'MISMATCH' if len(_r) != n_digits else 'ok'}")
        print(f"  VERDICT                     : {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
