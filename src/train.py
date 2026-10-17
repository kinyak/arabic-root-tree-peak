"""train.py — the masked multi-task training loop. Reads config/shared.yaml.

NOTHING IS TRAINED BY DEFAULT. The real runs are for Kaggle (0 local compute units
here); this file exists so the loop is written, runnable and tested before anyone
spends GPU time. `--smoke` runs a tiny model on tiny data on CPU.

THE LOSS (§4)
    L = sum over heads of  w_h * CE_h / log(|V_h|)      (w and the normalisation are
                                                         config-driven, not hardcoded)
    Every head's cross-entropy is computed with ignore_index, and masked positions are
    written into the target as ignore_index at batch-construction time — so a masked
    position cannot leak into the loss even if a call site forgets a mask.
    Normalising by log|V| keeps a 26-way radical slot from being drowned by a
    13k-way next-lemma head; §4 names Kendall-style learned weights as the principled
    replacement and that is a config change, not a code change.

SURFACE OUTPUT IS ABSENT BY DESIGN FOR THE TREATMENT
    The renderer (R1) does not exist, so the treatment arm produces no surface. This
    loop does not fake one: for a treatment arm, the surface head is None and its
    weight is skipped, and the harness reports head metrics only. Both arms are scored
    head-to-head on those; the end-to-end surface metric waits for R1.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import torch
import torch.nn as nn

from paths import ROOT
from model_arms import (IGNORE, Arm, Vocabs, count_params, load_config,
                        make_batch, parity_report, read_records, resolve_device)

HEAD_LOSSES = ("root", "wazan", "wazan_canonical", "stem_tail", "proclitic", "enclitic",
               "case", "definiteness", "syntax", "ntp")

# (head name in config and in the model's output, target key in the batch,
#  vocabulary key). ONE place, so a weight can never silently fail to apply because
# two files spell the same head differently.
HEAD_SPEC = (("root", "root", "radical"),
             ("wazan", "wazan", "wazan"),
             ("wazan_canonical", "wazan_canonical", "wazan_canonical"),
             ("stem_tail", "stem_tail", "stem_tail"),
             ("proclitic", "proclitic", "proclitic"),
             ("enclitic", "enclitic", "enclitic"),
             ("case", "case", "case"),
             ("definiteness", "definiteness", "definiteness"),
             ("syntax", "deprel", "deprel"),
             ("ntp", "ntp", "ntp"))


def head_loss(logits, target, ignore=IGNORE, gamma=0.0):
    if logits is None:
        return None
    # root is (B, L, 4, V) against (B, L, 4); every other head is (B, L, V) vs (B, L)
    if logits.dim() == 4 and target.dim() == 3:
        V = logits.shape[-1]
        flat_logits = logits.reshape(-1, V)
        flat_target = target.reshape(-1)
    elif logits.dim() == 3 and target.dim() == 2:
        V = logits.shape[-1]
        flat_logits = logits.reshape(-1, V)
        flat_target = target.reshape(-1)
    else:
        raise ValueError(f"unexpected head shapes: logits {tuple(logits.shape)}, "
                         f"target {tuple(target.shape)}")

    if gamma <= 0.0:
        return nn.functional.cross_entropy(
            flat_logits, flat_target, ignore_index=ignore)

    # Focal loss for multi-class classification:
    # L_focal = - (1 - p_t)^gamma * log(p_t)
    ce = nn.functional.cross_entropy(flat_logits, flat_target, ignore_index=ignore, reduction="none")
    pt = torch.exp(-ce)
    focal_weight = (1.0 - pt) ** gamma
    loss = focal_weight * ce
    valid_mask = (flat_target != ignore)
    if not valid_mask.any():
        return flat_logits.sum() * 0.0
    return loss[valid_mask].mean()


def compute_loss(out, tgt, cfg, sizes):
    """Config-driven masked multi-task loss with explicit head weighting and focal loss. Returns (total, parts).

    A HEAD WITH NO SUPERVISION CONTRIBUTES NOTHING, NOT NaN. `cross_entropy` over an
    all-`ignore_index` target returns NaN (0 valid elements -> 0/0), and this function SUMS the
    heads, so a single unsupervised head poisons the whole total. That is precisely how every one
    of the six SILVER runs died on Kaggle v9 (2026-10-10): Tashkeela carries `m_syn = 0` and
    `m_ntp = 0` for every record — the run itself printed "syntax and NTP are 0% supervised on
    this corpus by design" — so those two heads were NaN in EVERY batch and the loss was NaN from
    step 1, while the six gold/PADT runs (syn 100%, ntp 97.4%) trained normally. The guard lives
    here, not in the config, so that any head absent from a corpus degrades to "unmeasured"
    instead of poisoning the sum. Verified locally: silvers lose 2 of 5 heads and total stays
    finite; golds are unchanged.
    """
    weights = cfg.get("heads", {})
    loss_weights = cfg.get("loss", {}).get("weights", {})
    focal_heads = set(cfg.get("loss", {}).get("focal_heads", ["wazan", "wazan_canonical"]))
    focal_gamma = float(cfg.get("loss", {}).get("focal_gamma", 2.0))
    norm_log_vocab = bool(cfg.get("loss", {}).get("normalise_by_log_vocab", False))

    V = {"radical": sizes["radical"], "wazan": sizes["wazan"],
         "wazan_canonical": sizes["wazan_canonical"],
         "stem_tail": sizes["stem_tail"],   # §2db: NO default -- the space is 176 classes since §2cz
         "proclitic": sizes["proclitic"], "enclitic": sizes["enclitic"],
         "case": sizes["case"],
         "definiteness": sizes.get("definiteness", 4),
         "deprel": sizes["deprel"], "ntp": sizes["lemma"], "surface": sizes["surface"]}
    parts, total = {}, torch.zeros((), device=tgt["case"].device)
    for head, target_key, vocab_key in HEAD_SPEC:
        t = tgt[target_key]
        if not bool((t != IGNORE).any()):
            parts[head] = None      # unsupervised on this corpus: contributes 0, reported as null
            continue
        gamma = focal_gamma if head in focal_heads else 0.0
        l = head_loss(out[head], t, gamma=gamma)
        if l is None:
            continue
        # Head weight: loss.weights overrides heads.<head>.weight if present
        if head in loss_weights:
            w = float(loss_weights[head])
        elif head in weights and "weight" in weights[head]:
            w = float(weights[head]["weight"])
        else:
            w = 1.0

        if norm_log_vocab:
            l = l / math.log(max(V[vocab_key], 2))
        parts[head] = float(l.detach())
        total = total + w * l

    if out.get("surface") is not None and bool((tgt["next_surface"] != IGNORE).any()):
        l = head_loss(out["surface"], tgt["next_surface"], gamma=0.0)   # baseline only; same all-masked guard
        if "surface" in loss_weights:
            w = float(loss_weights["surface"])
        elif "surface" in weights and "weight" in weights["surface"]:
            w = float(weights["surface"]["weight"])
        else:
            w = 1.0
        if norm_log_vocab:
            l = l / math.log(max(V["surface"], 2))
        parts["surface"] = float(l.detach())
        total = total + w * l

    parts["total"] = float(total.detach())
    return total, parts


@torch.no_grad()
def evaluate(model, sents, v, cfg, sizes, device, trie=None, beam=5):
    """Head metrics on a split. Case is reported as per-class macro-F1 (never raw
    accuracy) with the majority-class baseline, via the shared eval harness.

    `trie` (a final_surface.RootTrie) additionally reports `root_whole_beamed`: the SAME
    weights decoded twice, once by plain argmax and once by the trie-constrained beam
    search. The pair is the point — a decode-time change must be visible as a pair, never
    folded into one number (CHALLENGES §2aa).
    """
    import eval_harness as EH
    from final_surface import (decode_root_slots,          # the ONE shared root decoder
                               decode_root_slots_beamed)   # trie-constrained variant
    model.eval()
    if hasattr(torch.backends, "mha") and hasattr(torch.backends.mha, "set_fastpath_enabled"):
        torch.backends.mha.set_fastpath_enabled(False)
    # TWO root metrics, reported side by side and never conflated (CHALLENGES 2x.14):
    #   · per-slot radical accuracy (the loop below, mask per slot) = HEAD TRAINING PROGRESS
    #   · whole-root exact match (composed with the SHARED decode_root_slots) = END-TO-END FIDELITY
    # The gold path could only ever report the second, so the dev figure (per-slot) and the human-gold
    # figure (composed) were never comparable — 0.7458 vs ~0.10-0.24 is essentially 0.746**3 ~ 0.41 vs
    # 0.24 once attenuation is accounted for, i.e. the same phenomenon measured two ways.
    inv_r = {i: c for c, i in v.radical.items()}
    inv_w = {i: w for w, i in v.wazan.items()}
    gwhole, pwhole, pbwhole = [], [], []
    gold = {"case": [], "pred": [], "root": [[], []], "wazan": [[], []],
            "wazan_canonical": [[], []], "stem_tail": [[], []],
            "proclitic": [[], []], "enclitic": [[], []],
            "ntp": [[], []], "definiteness": [[], []]}
    for x, x_char, t in make_batch(sents, v, cfg["data"]["max_len"], cfg["training"]["batch_size"]):
        x = x.to(device)
        x_char = x_char.to(device)
        out = model(x, x_char)
        if out["case"] is not None:
            m = t["m_case"].bool()
            if m.any():
                gold["case"] += t["case"][m].tolist()
                gold["pred"] += out["case"].argmax(-1)[m].tolist()
        for name, key in (("root", "root"), ("wazan", "wazan"),
                          ("wazan_canonical", "wazan_canonical"),
                          ("stem_tail", "stem_tail"),
                          ("proclitic", "proclitic"), ("enclitic", "enclitic"),
                          ("ntp", "ntp"), ("definiteness", "definiteness")):
            if name == "root":
                tg, lg = t["root"], out["root"]
                m = (tg != IGNORE)
                if m.any():
                    gold["root"][0] += tg[m].tolist()
                    gold["root"][1] += lg.argmax(-1)[m].tolist()
                # ---- whole-root exact match, through the ONE shared decoder ----
                rids = lg.argmax(-1)                       # (B, L, 4)
                # move to CPU ONCE per batch: a per-token .tolist() on a (4, |V|) tensor is
                # ~13k float conversions x thousands of tokens and dominated the eval cost
                lg_cpu = lg.detach().cpu()
                wz_cpu = out["wazan"].detach().cpu() if out.get("wazan") is not None else None
                for b in range(rids.shape[0]):
                    for l in range(rids.shape[1]):
                        gslots = tg[b, l].tolist()
                        if all(x == IGNORE for x in gslots):
                            continue                       # unusable gold root: not scored
                        pw = (inv_w.get(int(wz_cpu[b, l].argmax()), None)
                              if wz_cpu is not None else None)
                        gwhole.append(EH.to_bare_root_str(
                            "".join(inv_r.get(x, "") for x in gslots if x != IGNORE)))
                        pwhole.append(EH.to_bare_root_str(
                            decode_root_slots(rids[b, l].tolist(), pw, inv_r)))
                        if trie is not None:
                            # the SAME weights, decoded a second way: beam search over the
                            # joint slot log-probs, pruned to the valid-root trie
                            pbwhole.append(EH.to_bare_root_str(
                                decode_root_slots_beamed(
                                    lg_cpu[b, l].tolist(), pw, inv_r, trie,
                                    beam=beam)["root"]))
            else:
                tg, lg = t[key], out.get(name)
                if lg is not None:
                    m = (tg != IGNORE)
                    if m.any():
                        gold[key][0] += tg[m].tolist()
                        gold[key][1] += lg.argmax(-1)[m].tolist()
    res = {}
    if gold["case"]:
        res["case"] = EH.prf_per_class(gold["case"], gold["pred"], names=EH.CASE_NAMES)
    for key in ("root", "wazan", "wazan_canonical", "stem_tail", "proclitic", "enclitic", "ntp", "definiteness"):
        g, p = gold.get(key, [[], []])
        if g:
            if key == "stem_tail":
                n_tot = len(g)
                n_suff = sum(1 for a in g if a != 0)
                suff_ok = sum(1 for a, b in zip(g, p) if a != 0 and a == b)
                bare_cnt = sum(1 for a in g if a == 0)
                acc = sum(1 for a, b in zip(g, p) if a == b) / n_tot
                res["stem_tail"] = {
                    "accuracy": acc,
                    "overall_accuracy": acc,
                    "suffixed_only_accuracy": (suff_ok / n_suff) if n_suff else 0.0,
                    "constant_bare_baseline": bare_cnt / n_tot if n_tot else 0.0,
                    "n": n_tot,
                    "n_suffixed": n_suff,
                    "metric": "stem_tail accuracy with suffixed breakdown",
                }
            else:
                # PER-SLOT radical accuracy: each element is ONE radical slot of one token, so a
                # 3-radical token contributes 3 scored items. This is head-training progress, NOT
                # end-to-end fidelity — do not quote it as "root accuracy" without saying so.
                res[key] = {"accuracy": sum(1 for a, b in zip(g, p) if a == b) / len(g),
                            "n": len(g),
                            "metric": "per-slot radical accuracy" if key == "root" else "per-slot"}
    # WHOLE-ROOT EXACT MATCH — the composed quantity, and the only one comparable with the human-gold
    # path (which can only ever compose). `accuracy` is a 3-radical token counted once, not three times.
    if gwhole:
        res["root_whole"] = {
            "accuracy": sum(1 for a, b in zip(gwhole, pwhole) if a == b) / len(gwhole),
            "n": len(gwhole), "metric": "whole-root exact match",
            "decoder": "final_surface.decode_root_slots (shared)"}
    if pbwhole:
        # the SAME rows, the SAME weights, a DIFFERENT decoder — reported beside, never blended
        res["root_whole_beamed"] = {
            "accuracy": sum(1 for a, b in zip(gwhole, pbwhole) if a == b) / len(pbwhole),
            "n": len(pbwhole), "metric": "whole-root exact match, trie-constrained beam",
            "decoder": "final_surface.decode_root_slots_beamed"}
    model.train()
    return res


def train(cfg, arm_kind, seed, device, quiet=False, train_path=None, dev_path=None,
          vocab_sents=None, train_limit="config"):
    """Train ONE arm.

    `train_path` / `dev_path` / `vocab_sents` exist for the SILVER-vs-GOLD ablation: the
    training TARGET source is the variable there, so the data can move while the
    vocabulary must NOT. If each run built its own vocabulary from its own corpus, the
    two runs would have different head sizes, the parameter counts would differ, and the
    matched-size claim would quietly die on the head the comparison is about. So the
    caller passes ONE vocabulary (built over both corpora) and both runs share it.

    `train_limit` is the PER-CALL budget: "config" (default) is `data.limit_train`, None
    is IN FULL. It must be per-call because round 26 raises the silver arm to 1.87M
    tokens while gold stays at 120k, and BOTH sources are read through this function --
    one config-wide limit would truncate the larger sample back to 120,000, the run would
    reproduce the old result, and it would read as evidence against the hypothesis it was
    built to test.
    """
    torch.manual_seed(seed)
    _lim = cfg["data"]["limit_train"] if train_limit == "config" else train_limit
    tr = read_records(Path(train_path) if train_path else (ROOT / cfg["paths"]["train"]),
                      _lim)
    dv = read_records(Path(dev_path) if dev_path else (ROOT / cfg["paths"]["dev"]),
                      cfg["data"]["limit_dev"])
    if not quiet:
        # THE VOLUME IS PRINTED BECAUSE THE VOLUME IS THE EXPERIMENT. If a limit silently
        # truncated this arm, every downstream number would look like a clean negative.
        print("  data: %d train tokens, limit=%r (%s)"
              % (sum(len(t) for _, t in tr), train_limit,
                 train_path or cfg["paths"]["train"]))
    v = (vocab_sents if isinstance(vocab_sents, Vocabs)
         else Vocabs(vocab_sents if vocab_sents is not None else tr,
                     cfg["data"]["min_freq"], cfg["data"]["max_vocab"]))
    sizes = v.sizes()
    model = Arm(cfg, sizes, arm_kind).to(device)
    bs = cfg["training"]["batch_size"]
    opt = torch.optim.AdamW(model.parameters(), lr=cfg["training"]["lr"],
                            weight_decay=cfg["training"]["weight_decay"])
    warmup_steps = cfg["training"].get("warmup_steps", 500)
    total_steps = cfg["training"]["steps"]
    effective_warmup = min(warmup_steps, max(1, total_steps // 5))

    def lr_lambda(s):
        if s < effective_warmup:
            return float(s + 1) / float(effective_warmup)
        progress = float(s - effective_warmup) / float(max(1, total_steps - effective_warmup))
        return 0.5 * (1.0 + math.cos(math.pi * progress))

    sched = torch.optim.lr_scheduler.LambdaLR(opt, lr_lambda)


    history, step = [], 0
    t0 = time.time()
    while step < cfg["training"]["steps"]:
        for x, x_char, t in make_batch(tr, v, cfg["data"]["max_len"], bs):
            if step >= cfg["training"]["steps"]:
                break
            x = x.to(device)
            x_char = x_char.to(device)
            t = {k: vv.to(device) for k, vv in t.items()}
            out = model(x, x_char)
            loss, parts = compute_loss(out, t, cfg, sizes)
            opt.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), cfg["training"]["grad_clip"])
            opt.step()
            sched.step()
            step += 1
            history.append(parts)
            if not quiet and step % cfg["training"]["log_every"] == 0:
                print(f"    step {step:>5} loss {parts['total']:.4f} "
                      f"({(time.time()-t0)/step*1000:.0f} ms/step)", flush=True)
            if step % cfg["training"]["eval_every"] == 0:
                res = evaluate(model, dv, v, cfg, sizes, device)
                history[-1]["eval"] = res
                if not quiet:
                    c = res.get("case", {})
                    print(f"      eval @{step}: case macro-F1 "
                          f"{c.get('macro_f1', float('nan')):.3f} "
                          f"(majority {c.get('majority_macro_f1', float('nan')):.3f}) "
                          f"root acc {res.get('root', {}).get('accuracy', float('nan')):.3f}")
    return model, history, sizes, v


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="treatment", choices=("baseline", "treatment"))
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--step", type=int, default=0)
    args = ap.parse_args()

    cfg = load_config(smoke=args.smoke)
    device = resolve_device(cfg)
    print("=" * 80)
    print(f"TRAIN — arm={args.arm}  device={device}  "
          f"{'SMOKE (tiny)' if args.smoke else 'FULL CONFIG'}")
    print("config: config/shared.yaml  (both arms read THE SAME FILE — §5.2)")
    print("=" * 80)
    if not args.smoke:
        print("\nWARNING: this is the full config. Real runs belong on Kaggle "
              "(0 local compute units). Use --smoke to exercise the loop.")
        return 2
    model, hist, sizes, v = train(cfg, args.arm, cfg["seeds"][0], device)
    print(f"\n  steps run : {len([h for h in hist if 'total' in h])}")
    print(f"  final loss: {hist[-1]['total']:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
