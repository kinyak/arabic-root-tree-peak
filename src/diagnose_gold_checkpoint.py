"""diagnose_gold_checkpoint.py — why is a head's gold score what it is?

WHY THIS EXISTS
    A score against the human gold is not interpretable on its own. The ablation reported
    `root = 0.000` on the 278 gold rows while the SAME head scores 0.75 per-slot in-domain,
    and a trivial "always predict the most common pattern" baseline beats the model on raw
    wazan. Both facts have to be separated from the plumbing before either can be believed,
    so this script takes a checkpoint and reports the things that decide the reading:

      · per-slot vs whole-root accuracy (0.75 per slot and 0/163 whole roots are not the
        same claim, and only one of them is a distributional finding)
      · the TARGET-word OOV rate, because a word the vocabulary cannot encode is a word the
        model cannot be asked about — this is what separates "the head failed" from
        "the item was unanswerable"
      · per-slot accuracy split by IN-VOCAB vs OOV target, which is the actual test
      · the constant-prediction baselines, so "98% slot agreement" can be checked against a
        predictor that always says {1,2,3} (which scores 0.989)
      · an UNTRAINED model as a control, since random weights are also a predictor

USAGE
    python src/diagnose_gold_checkpoint.py --ckpt dist/kaggle-output/checkpoints/gold-treatment-s20261009.pt
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import torch  # noqa: E402

import eval_harness as EH  # noqa: E402
from final_surface import decode_root_slots  # noqa: E402  (the ONE shared root decoder)
from model_arms import Arm, Vocabs, load_config, read_records, resolve_device  # noqa: E402
from paths import ROOT  # noqa: E402


def union_vocab(cfg) -> Vocabs:
    lim = cfg["data"]["limit_train"]
    g = read_records(cfg["paths"]["train"], lim)
    s = read_records(cfg["paths"]["silver_train"], lim)
    return Vocabs(g + s, cfg["data"]["min_freq"], cfg["data"]["max_vocab"])


def score(model, V, gold, device, max_len):
    """Per-slot and whole-root accuracy, split by whether the target word is in vocab."""
    inv_r = {i: c for c, i in V.radical.items()}
    inv_w = {i: w for w, i in V.wazan.items()}
    out = {"root": collections.Counter(), "wazan": collections.Counter(),
           "root_preds": collections.Counter(), "wazan_preds": collections.Counter(),
           "case_gold": [], "case_pred": []}
    model.eval()
    with torch.no_grad():
        for g in gold:
            toks, idx = EH.parse_gold_context(g.get("context") or "")
            if not toks:
                continue
            in_vocab = V.encode(toks[idx]) != 1
            x = torch.tensor([[V.encode(t) for t in toks]], device=device)
            # v12: build character tensor for the input
            max_char_len = 20
            x_char_list = []
            for t in toks:
                chars = [V.char.get(c, 0) for c in t[:max_char_len]]
                chars += [0] * (max_char_len - len(chars))
                x_char_list.append(chars)
            x_char = torch.tensor([x_char_list], device=device)
            o = model(x, x_char)
            if o["root"] is not None and g.get("root_valid") and g.get("t_root_arabic"):
                slots = o["root"][0, idx].argmax(-1).tolist()
                # Use the SHARED decoder, not a re-implementation — the 1-row defect in §2y.2
                pw = inv_w.get(int(o["wazan"][0, idx].argmax())) if o["wazan"] is not None else None
                got = EH.to_bare_root_str(decode_root_slots(slots, pw, inv_r))
                want = EH.to_bare_root_str(g["t_root_arabic"])
                out["root_preds"][got] += 1
                bucket = "in_vocab" if in_vocab else "oov"
                out["root"]["n"] += 1
                out["root"][bucket + "_n"] += 1
                out["root"]["whole_ok"] += 1 if got == want else 0
                out["root"][bucket + "_whole_ok"] += 1 if got == want else 0
                # per-slot, against the gold root's own letters
                wl = list(want)
                got_chars = list(got)
                for i, ch in enumerate(got_chars):
                    if i < len(wl) and ch == wl[i]:
                        out["root"]["slot_ok"] += 1
                        out["root"][bucket + "_slot_ok"] += 1
                    out["root"]["slot_n"] += 1
                    out["root"][bucket + "_slot_n"] += 1
            if o["wazan"] is not None and g.get("pattern_valid") and g.get("t_wazan_pattern"):
                pw = inv_w.get(int(o["wazan"][0, idx].argmax()))
                gp = EH.nfc(g["t_wazan_pattern"])
                out["wazan_preds"][pw] += 1
                out["wazan"]["n"] += 1
                out["wazan"]["raw_ok"] += 1 if EH.nfc(pw) == gp else 0
                out["wazan"]["norm_ok"] += 1 if EH.lead_hamza_variant(pw) == EH.lead_hamza_variant(gp) else 0
                out["wazan"]["slot_ok"] += 1 if (sorted(re.findall(r"[1-4]", pw or ""))
                                                 == sorted(re.findall(r"[1-4]", gp or ""))) else 0
            if o["case"] is not None and g.get("t_case") is not None:
                out["case_gold"].append(int(g["t_case"]))
                out["case_pred"].append(int(o["case"][0, idx].argmax()))
    model.train()
    return out


def show(name, r):
    n = max(r["root"]["n"], 1)
    sn = max(r["root"]["slot_n"], 1)
    wn = max(r["wazan"]["n"], 1)
    print("\n--- %s ---" % name)
    print("  ROOT   whole-root exact : %3d/%3d = %.3f" % (r["root"]["whole_ok"], n, r["root"]["whole_ok"] / n))
    print("         per-slot exact   : %3d/%3d = %.3f" % (r["root"]["slot_ok"], sn, r["root"]["slot_ok"] / sn))
    for b in ("in_vocab", "oov"):
        bn = max(r["root"][b + "_n"], 1)
        bsn = max(r["root"][b + "_slot_n"], 1)
        print("         %-8s n=%3d  whole %.3f   per-slot %.3f" % (
            b, r["root"][b + "_n"], r["root"][b + "_whole_ok"] / bn,
            r["root"][b + "_slot_ok"] / bsn))
    print("  WAZAN  raw %.3f   hamza-normalised %.3f   slot-set %.3f   (n=%d)" % (
        r["wazan"]["raw_ok"] / wn, r["wazan"]["norm_ok"] / wn,
        r["wazan"]["slot_ok"] / wn, r["wazan"]["n"]))
    print("         top predictions: %s" % r["wazan_preds"].most_common(4))
    print("         top roots      : %s" % r["root_preds"].most_common(4))
    if r["case_gold"]:
        p = EH.prf_per_class(r["case_gold"], r["case_pred"], names=EH.CASE_NAMES)
        print("  CASE   macro-F1 %.3f (majority %.3f)  pred dist %s" % (
            p["macro_f1"], p["majority_macro_f1"],
            dict(collections.Counter(r["case_pred"]).most_common())))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--untrained-control", action="store_true", default=True)
    args = ap.parse_args()

    cfg = load_config()
    device = resolve_device(cfg)
    V = union_vocab(cfg)
    sizes = V.sizes()
    gold = EH.load_human_gold(cfg["paths"]["human_gold"])
    torch.manual_seed(0)

    if args.untrained_control:
        show("CONTROL: untrained weights", score(Arm(cfg, sizes, "treatment"), V, gold,
                                                device, cfg["data"]["max_len"]))

    ck = torch.load(args.ckpt, map_location=device, weights_only=False)
    # Build the arm from the config the model was TRAINED with (a checkpoint carries it), not
    # from the current file: an architecture flag flipped after the run would otherwise make a
    # perfectly good checkpoint fail to load. Falls back to the current config for old files.
    ck_cfg = ck.get("cfg") or cfg
    model = Arm(ck_cfg, sizes, ck.get("arm", "treatment"))
    model.load_state_dict(ck["model"])
    show(Path(args.ckpt).stem, score(model, V, gold, device, cfg["data"]["max_len"]))

    print("\nBASELINES that a claim has to beat (computed on the 278 gold patterns):")
    pats = [EH.nfc(g["t_wazan_pattern"]) for g in gold
            if g.get("pattern_valid") and g.get("t_wazan_pattern")]
    top, cnt = collections.Counter(pats).most_common(1)[0]
    print("  constant raw wazan %r : %.3f" % (top, cnt / len(pats)))
    dss = collections.Counter(tuple(sorted(set(re.findall(r"[1-4]", p)))) for p in pats)
    td, dc = dss.most_common(1)[0]
    print("  constant slot-set %s : %.3f" % (list(td), dc / len(pats)))
    roots = [EH.to_bare_root_str(g["t_root_arabic"]) for g in gold
             if g.get("root_valid") and g.get("t_root_arabic")]
    tr, rc = collections.Counter(roots).most_common(1)[0]
    print("  constant root %r : %.3f of %d" % (tr, rc / len(roots), len(roots)))
    oov = sum(1 for g in gold if (lambda t: t and V.encode(t[0][t[1]]) == 1)
              (EH.parse_gold_context(g.get("context") or "")))
    print("  TARGET-word OOV among all %d gold rows: %.3f" % (len(gold), oov / len(gold)))
    print("\nREAD IT THIS WAY: a metric a CONSTANT predictor nearly saturates (the slot set)"
          " carries almost no information; a metric the model loses to a constant predictor"
          " (raw wazan) is evidence AGAINST the head, not merely a low score; and a metric"
          " measured on items the vocabulary cannot encode (OOV) is uninterpretable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
