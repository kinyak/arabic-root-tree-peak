"""measure_constrained_root_decoding.py — is the root head's error ILLEGALITY or CONFUSION?

THE QUESTION (v12 Phase 3, `CHALLENGES.md` 2z)
    A trie constraint on the root decoder can only fix ONE class of error:
      ILLEGALITY : the emitted trio is not a root in the inventory (structural hallucination)
      CONFUSION  : the emitted trio IS a legal root, but the wrong one for this word
    If confusion dominates, the constraint buys nothing and that is the honest answer.
    This script measures the RATIO, then measures what the constraint actually moves on
    whole-root accuracy, split by in-vocab / OOV because that is where the head is capped.

WHY BEAM AND NOT A SLOT MASK
    Masking slot 3 after greedily committing slots 1-2 cannot recover a mistake made in
    slot 1 — it just forces a wrong branch or an abstention. `decode_root_slots_beamed`
    searches the joint objective with trie pruning at every step, and falls back to the
    SHARED decoder (reported, never silent) when no legal root is reachable.

TWO INVENTORIES, because they answer different questions
    train   : the roots present in the model's own training targets (its LABEL SPACE).
              "can the constraint keep the head inside the space it was trained on?"
    lexicon : PADT `Root=` + arramooz roots (LICENSED Arabic roots).
              "is the emitted trio a real root in Arabic?"

USAGE
    ART_ROOT=<bundle> python src/measure_constrained_root_decoding.py \
        --ckpt dist/kaggle-output/checkpoints/silver-treatment-s20261009.pt
    python src/measure_constrained_root_decoding.py --selftest
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import torch  # noqa: E402

import eval_harness as EH  # noqa: E402
from final_surface import (RootTrie, decode_root_slots,  # noqa: E402
                           decode_root_slots_beamed)
from model_arms import Arm, Vocabs, load_config, read_records, resolve_device  # noqa: E402


# --------------------------------------------------------------- inventories
def roots_from_records(paths, cap=None) -> set:
    """The roots that actually appear as TARGETS in these records = the model's label space."""
    out = set()
    for p in paths:
        p = Path(p)
        if not p.exists():
            continue
        with open(p, encoding="utf-8") as fh:
            for i, line in enumerate(fh):
                if cap and i >= cap:
                    break
                r = json.loads(line)
                if r.get("m_root"):
                    s = "".join(c for c in r["t_root"] if c)
                    if s:
                        out.add(s)
    return out


def roots_from_lexicon(padt_dict: Path) -> tuple[set, dict]:
    """PADT `Root=` + arramooz roots, via the repo's own builder (no held-out corpora read)."""
    import build_training_jsonl as BTJ
    mapping, prov = BTJ.build_silver_root_dict(str(padt_dict))
    return {v for v in mapping.values() if v and len(v) in (3, 4)}, prov


# ------------------------------------------------------------------- scoring
def score_arm(model, V, gold, device, trie, beam):
    """Per-row unconstrained vs constrained decode, with the illegality/confusion split."""
    inv_r = {i: c for c, i in V.radical.items()}
    c = collections.Counter()
    model.eval()
    with torch.no_grad():
        for g in gold:
            toks, idx = EH.parse_gold_context(g.get("context") or "")
            if not toks:
                continue
            if not (g.get("root_valid") and g.get("t_root_arabic")):
                continue
            in_vocab = V.encode(toks[idx]) != 1
            bucket = "in_vocab" if in_vocab else "oov"

            x = torch.tensor([[V.encode(t) for t in toks]], device=device)
            max_char_len = 20
            xc = []
            for t in toks:
                row = [V.char.get(ch, 0) for ch in t[:max_char_len]]
                row += [0] * (max_char_len - len(row))
                xc.append(row)
            x_char = torch.tensor([xc], device=device)

            o = model(x, x_char)
            if o["root"] is None or o["wazan"] is None:
                continue
            pw = {i: w for w, i in V.wazan.items()}.get(int(o["wazan"][0, idx].argmax()))
            slots = o["root"][0, idx].argmax(-1).tolist()
            logits = o["root"][0, idx].cpu().tolist()          # (4, V)

            # ---- unconstrained (the shared ONE decoder: what every other path reports) ----
            uncon = EH.to_bare_root_str(decode_root_slots(slots, pw, inv_r))
            # ---- constrained (nothing is scored from the argmax slots above the shared call) ----
            r = decode_root_slots_beamed(logits, pw, inv_r, trie, beam=beam)
            con = EH.to_bare_root_str(r["root"])

            want = EH.to_bare_root_str(g["t_root_arabic"])

            c["n"] += 1
            c[bucket + "_n"] += 1
            c["uncon_ok" if uncon == want else "uncon_bad"] += 1
            c["con_ok" if con == want else "con_bad"] += 1
            c[bucket + "_uncon_ok" if uncon == want else bucket + "_uncon_bad"] += 1
            c[bucket + "_con_ok" if con == want else bucket + "_con_bad"] += 1
            if uncon == want:
                c["both_ok"] += 1
            # the constraint can only act on a row it is allowed to change
            if r["illegal_before"]:
                c["illegal"] += 1
                c[bucket + "_illegal"] += 1
            elif uncon != want:
                c["confusion"] += 1
                c[bucket + "_confusion"] += 1
            if r["fell_back"]:
                c["fell_back"] += 1
            if r["changed"]:
                c["changed"] += 1
                if r["illegal_before"] and con == want:
                    c["fixed_by_constraint"] += 1
                elif r["illegal_before"] and con != want:
                    c["illegal_but_still_wrong"] += 1
                elif not r["illegal_before"] and uncon == want:
                    c["broke_a_correct_row"] += 1
    model.train()
    return c


def show(name, c, trie):
    n = max(c["n"], 1)
    print(f"\n--- {name} ---   (inventory: {len(trie):,} roots, beam search)")
    print(f"  rows scored            : {c['n']}")
    print(f"  UNCONSTRAINED illegal  : {c['illegal']:3d}/{n} = {c['illegal']/n:.3f}"
          f"   <- the constraint's only reachable error class")
    print(f"  UNCONSTRAINED confusion: {c['confusion']:3d}/{n} = {c['confusion']/n:.3f}"
          f"   <- legal root, wrong word: constraint CANNOT fix")
    print(f"  fell back (no legal path): {c['fell_back']}")
    print(f"  rows the constraint changed: {c['changed']}"
          f"   (fixed {c['fixed_by_constraint']}, still wrong {c['illegal_but_still_wrong']},"
          f" broke a correct row {c['broke_a_correct_row']})")
    print(f"  WHOLE-ROOT  unconstrained {c['uncon_ok']/n:.4f}  ->  constrained "
          f"{c['con_ok']/n:.4f}   delta {(c['con_ok']-c['uncon_ok'])/n:+.4f}")
    for b in ("in_vocab", "oov"):
        bn = max(c[b + "_n"], 1)
        print(f"    {b:<8} n={c[b+'_n']:3d}  uncon {c[b+'_uncon_ok']/bn:.4f}"
              f"  ->  con {c[b+'_con_ok']/bn:.4f}"
              f"   delta {(c[b+'_con_ok']-c[b+'_uncon_ok'])/bn:+.4f}"
              f"   | illegal {c[b+'_illegal']}/{c[b+'_n']}"
              f"  confusion {c[b+'_confusion']}/{c[b+'_n']}")


# ------------------------------------------------------------------ selftest
def selftest() -> int:
    """Prove the trie + beam behave: reject illegal, find legal, fall back loudly."""
    roots = {"كتب", "قول", "علم", "ضرب", "فعل", "استع"}
    trie = RootTrie(roots)
    assert len(trie) == 6
    assert trie.is_legal("كتب") and not trie.is_legal("كxx")
    assert trie.has_prefix("كت") and not trie.has_prefix("كط")
    inv_r = {1: "ك", 2: "ت", 3: "ب", 4: "ق", 5: "و", 6: "ل",
             7: "ع", 8: "م", 9: "ض", 10: "ر", 11: "ف", 12: "s"}

    def mk(letter_ids, V=13):
        """One-hot-ish logits: chosen ids get +8, everything else 0 (one row per slot)."""
        rows = []
        for lid in letter_ids:
            r = [0.0] * V
            r[lid] = 8.0
            rows.append(r)
        return rows

    # (a) argmax is already legal -> constraint must NOT change it
    r = decode_root_slots_beamed(mk([1, 2, 3]), "1َ2َ3", inv_r, trie)
    assert r["root"] == "كتب" and r["legal_path"] and not r["changed"], r
    assert not r["illegal_before"], r

    # (b) argmax is ILLEGAL at slot 3 (ك ت م) -> beam must find a legal branch (ك ت ب)
    logits = mk([1, 2, 8])
    r = decode_root_slots_beamed(logits, "1َ2َ3", inv_r, trie)
    assert r["argmax_root"] == "كتم", r
    assert r["illegal_before"], r
    assert r["legal_path"] and r["root"] == "كتب" and r["changed"], r

    # (c) a mistake in slot 1 must be recoverable (the naive slot-3 mask could not do this)
    logits = mk([12, 2, 3])          # "sتب" illegal at slot 1
    r = decode_root_slots_beamed(logits, "1َ2َ3", inv_r, trie)
    assert r["illegal_before"] and r["root"] == "كتب", r

    # (d) no legal path at all (all letters unrecognised) -> LOUD fallback to the shared decoder
    inv_bad = {1: "ز", 2: "ط"}       # no root starts with زط
    r = decode_root_slots_beamed(mk([1, 2, 1], V=3), "1َ2َ3", inv_bad, trie)
    assert r["fell_back"] and not r["legal_path"], r
    assert r["root"] == r["argmax_root"], r

    print("  [OK] trie rejects illegal prefixes and admits legal roots")
    print("  [OK] argmax already legal -> unchanged")
    print("  [OK] illegal slot-3 -> beam recovers a legal root (confusion avoided)")
    print("  [OK] illegal slot-1 -> beam recovers (impossible for a naive slot-3 mask)")
    print("  [OK] no legal path -> loud fallback to the shared decode_root_slots")
    print("  SELFTEST PASSED")
    return 0


# ---------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", default=None)
    ap.add_argument("--inventory", default="train", choices=("train", "lexicon"))
    ap.add_argument("--beam", type=int, default=5)
    ap.add_argument("--all", action="store_true",
                    help="score every checkpoint in dist/kaggle-output/checkpoints")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        print("=" * 78)
        print("SELFTEST — the trie and the beam, before any checkpoint is loaded")
        print("=" * 78)
        return selftest()

    cfg = load_config()
    device = resolve_device(cfg)
    root = Path(cfg["paths"]["train"]).parent
    train_paths = [cfg["paths"]["train"], cfg["paths"]["silver_train"]]

    if args.inventory == "train":
        roots = roots_from_records(train_paths)
        src = f"train label space ({', '.join(Path(p).name for p in train_paths)})"
    else:
        # the dict lives beside `out/` (data/silver_root_dict_padt.json), not inside it
        cands = [Path(cfg["paths"]["train"]).parent.parent / "silver_root_dict_padt.json",
                 Path(cfg["paths"]["train"]).parent / "silver_root_dict_padt.json",
                 Path("dist/silver_root_dict_padt.json")]
        padt = next((p for p in cands if p.exists()), None)
        if padt is None:
            raise SystemExit("silver_root_dict_padt.json not found; tried: "
                             + ", ".join(str(p) for p in cands))
        roots, prov = roots_from_lexicon(padt)
        src = f"PADT+arramooz lexicon ({padt.name}; {prov.get('arramooz_added')} arramooz forms)"
    trie = RootTrie(roots)

    V = Vocabs(read_records(cfg["paths"]["train"], cfg["data"]["limit_train"]) +
               read_records(cfg["paths"]["silver_train"], cfg["data"]["limit_train"]),
               cfg["data"]["min_freq"], cfg["data"]["max_vocab"])
    sizes = V.sizes()
    gold = EH.load_human_gold(cfg["paths"]["human_gold"])

    print("=" * 78)
    print("CONSTRAINED ROOT DECODING — illegality vs confusion on the human gold")
    print("=" * 78)
    print(f"  inventory      : {src}")
    print(f"  distinct roots : {len(trie):,}")
    print(f"  gold rows      : {len(gold)}   (278 have a usable gold root)")
    print(f"  radical types  : {sizes['radical']}   wazan types: {sizes['wazan']:,}")
    print(f"  beam width     : {args.beam}")

    ckpts = ([p for p in sorted((Path("dist/kaggle-output/checkpoints")).glob("*.pt"))]
             if args.all else [Path(args.ckpt)])
    for p in ckpts:
        ck = torch.load(p, map_location=device, weights_only=False)
        m = Arm(ck.get("cfg") or cfg, sizes, ck.get("arm", "treatment"))
        m.load_state_dict(ck["model"])
        show(p.stem, score_arm(m, V, gold, device, trie, args.beam), trie)

    print("\nREAD IT THIS WAY: only the `illegal` rows are reachable by a trie constraint. If")
    print("`confusion` dominates, the constraint cannot move whole-root accuracy and the honest")
    print("result is 'no gain' — the head's problem is lexical, not structural.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
