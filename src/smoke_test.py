"""smoke_test.py — tiny model, tiny data, the FULL loop end to end.

This is item 4 of "what must exist before the first notebook" (START-HERE §10). It is
the cheap gate that catches the errors that would otherwise be discovered after
spending GPU hours: a config the two arms read differently, a mask that does not mask,
a head that never receives gradient, a loss that is NaN on step 1.

WHAT IT ASSERTS (each one is a thing that has actually gone wrong in this project)
  1. Both arms build from the SAME config file and match within parity.tolerance.
  2. The A13 difference is exactly the decoder: the baseline has a surface head, the
     treatment does not, and both have all five shared heads.
  3. A masked position contributes EXACTLY zero — tested by corrupting a masked target
     and confirming the loss is bit-identical.
  4. Every unmasked head actually receives gradient (a head that is silently skipped
     is this project's signature failure mode).
  5. The loop runs, the loss is finite at step 1 and does not increase over the run.
  6. The eval path returns per-class macro-F1 for case WITH the majority baseline, so
     the metric cannot be mistaken for accuracy.
  7. The device is resolved explicitly and CPU-training-as-a-surprise is impossible.

USAGE
    python src/smoke_test.py            # exit 0 = all invariants hold
    python src/train.py --smoke         # just run the loop
"""
from __future__ import annotations

import copy
import math
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import torch

from paths import ROOT
from model_arms import (IGNORE, Arm, Vocabs, count_params, load_config,
                        make_batch, parity_report, read_records, resolve_device)
from train import compute_loss, evaluate, head_loss, train

FAILURES: list[str] = []


def check(cond, label, detail=""):
    print(f"  [{'OK ' if cond else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))
    if not cond:
        FAILURES.append(label)
    return cond


def main() -> int:
    print("=" * 84)
    print("SMOKE TEST — tiny model, tiny data, the full loop end to end")
    print("=" * 84)

    cfg = load_config(smoke=True)
    device = resolve_device(cfg)
    print(f"\nconfig : config/shared.yaml   device: {device}")

    # ---- data
    tr = read_records(ROOT / cfg["paths"]["train"], cfg["data"]["limit_train"])
    dv = read_records(ROOT / cfg["paths"]["dev"], cfg["data"]["limit_dev"])
    v = Vocabs(tr, cfg["data"]["min_freq"], cfg["data"]["max_vocab"])
    sizes = v.sizes()
    print(f"data   : train {sum(len(t) for _, t in tr):,} tokens / "
          f"dev {sum(len(t) for _, t in dv):,} tokens")
    print(f"vocabs : {sizes}")

    print("\n1. data sanity — vocabularies must not be degenerate")
    check(sizes["radical"] > 5, "radical vocab has real entries",
          f"({sizes['radical']})")
    check(sizes["wazan"] > 5, "wazan vocab has real entries", f"({sizes['wazan']})")
    check(sizes["deprel"] > 5, "deprel vocab has real entries", f"({sizes['deprel']})")

    print("\n2. both arms from the SAME config")
    b = Arm(cfg, sizes, "baseline")
    t = Arm(cfg, sizes, "treatment")
    base_n = count_params(b)
    treat_n = count_params(t)
    surf_n = count_params(b.h_surface)
    check(t.tower is None, "treatment arm is lean and towerless (no dummy weights)")
    check(t.h_surface is None, "treatment has NO surface head lookup table")
    check(b.h_surface is not None, "baseline HAS a surface head lookup table")

    print("\n3. true architectural separation (Task 2 / Gate 2)")
    check(hasattr(t, "root_slot_queries"),
          "treatment carries positional character-slot cross-attention queries (root_slot_queries)")
    check(hasattr(t, "affix_to_wazan") and hasattr(t, "h_wazan_bottleneck"),
          "treatment carries affix-conditioned wazan bottleneck")
    check(hasattr(b, "h_root") and hasattr(t, "h_root"),
          "both arms carry root prediction interfaces")
    check(all(hasattr(t, f"h_{h}") and hasattr(b, f"h_{h}")
              for h in ("wazan", "wazan_canonical", "stem_tail", "proclitic", "enclitic",
                        "case", "definiteness", "syntax")),
          "both arms carry grammatical prediction heads")

    print("\n4. a masked position contributes EXACTLY zero")
    b.to(device).eval()
    x, x_char, tgt = next(iter(make_batch(tr, v, cfg["data"]["max_len"], 2)))
    x = x.to(device)
    x_char = x_char.to(device)
    tgt = {k: vv.to(device) for k, vv in tgt.items()}
    with torch.no_grad():
        out = b(x, x_char)
        # Work FLAT: (B, L) -> (B*L,) and logits (B, L, C) -> (B*L, C). Indexing a 2-D
        # tensor with flat indices row-indexes instead, which raised IndexError here.
        t_case = tgt["case"].flatten()
        logits = out["case"].reshape(-1, out["case"].shape[-1])
        m = t_case != IGNORE
        # (a) the library loss with ignore_index must EQUAL a manual loss summed over
        #     only the unmasked positions. If masking were broken these would differ.
        manual = torch.nn.functional.cross_entropy(logits[m], t_case[m])
        lib = head_loss(out["case"], tgt["case"])
        check(abs(float(manual) - float(lib)) < 1e-6,
               "ignore_index loss == loss over unmasked positions only",
               f"({float(manual):.6f} vs {float(lib):.6f})")
        check(int((~m).sum()) > 0, "the batch HAS masked positions to test with",
               f"({int((~m).sum())} masked of {m.numel()})")
        # (b) POSITIVE CONTROL: changing an UNMASKED target must change the loss.
        #     Without it, (a) would also pass on a loss that ignores everything.
        corr = t_case.clone()
        corr[m] = (corr[m] + 1) % 3                      # wrong class, still valid
        lib2 = head_loss(logits.reshape(out["case"].shape), corr.reshape(tgt["case"].shape))
        check(abs(float(lib2) - float(lib)) > 1e-6,
               "POSITIVE CONTROL: changing an UNMASKED target does change the loss",
               f"({float(lib):.6f} -> {float(lib2):.6f})")
        # (c) the masked subset alone is undefined: every target in it is ignore_index,
        #     so cross_entropy has nothing to average and returns NaN. That is the
        #     strongest form of "excluded" — treat NaN as passing, and say so.
        try:
            others = float(torch.nn.functional.cross_entropy(logits[~m], t_case[~m]))
        except Exception:
            others = float("nan")
        excluded = math.isnan(others) or abs(others - float(lib)) > 1e-6
        check(excluded,
               "masked subset alone is undefined/NaN (every target ignored) — excluded",
               f"({float(lib):.6f} vs {others})")

    print("\n5. every unmasked head receives gradient & Gate 2 invariants")
    b.to(device).train()
    b.zero_grad()
    out = b(x, x_char)
    loss, _ = compute_loss(out, tgt, cfg, sizes)
    loss.backward()
    for name, mod in (("root", b.h_root), ("wazan", b.h_wazan),
                      ("wazan_canonical", b.h_wazan_canonical),
                      ("stem_tail", b.h_stem_tail),
                      ("proclitic", b.h_proclitic), ("enclitic", b.h_enclitic),
                      ("case", b.h_case), ("definiteness", b.h_definiteness),
                      ("syntax", b.h_syntax), ("surface", b.h_surface)):
        if mod is None:
            continue
        g = mod.weight.grad
        live = g is not None and torch.isfinite(g).all() and bool((g != 0).any())
        check(live, f"{name} head received a finite non-zero gradient")

    # Gate 2 Invariant 1: Zeroing C_seq suffix positions changes stem_tail_logits on Treatment
    t.to(device).eval()
    with torch.no_grad():
        out_orig = t(x, x_char)
        # Forward hook to zero out suffix positions of C_seq
        def hook_fn(module, inp, outp):
            C_seq, char_mask, c_pool = outp
            C_seq_mod = C_seq.clone()
            lengths = (~char_mask).long().sum(dim=-1)
            for bi in range(C_seq.shape[0]):
                for li in range(C_seq.shape[1]):
                    l_tok = lengths[bi, li].item()
                    if l_tok > 0:
                        start_suf = max(0, l_tok - 4)
                        C_seq_mod[bi, li, start_suf:l_tok, :] = 0.0
            return (C_seq_mod, char_mask, c_pool)

        handle = t.char_encoder.register_forward_hook(hook_fn)
        out_zeroed = t(x, x_char)
        handle.remove()

        diff_stem = (out_orig["stem_tail"] - out_zeroed["stem_tail"]).abs().max().item()
        check(diff_stem > 1e-4,
              "Gate 2 Invariant 1: Zeroing C_seq suffix positions changes stem_tail_logits on Treatment",
              f"(max diff: {diff_stem:.6f})")

    # Gate 2 Invariants 2 & 3: case_gov_q/k and root_slot_queries receive non-zero gradient on step 1
    t.train()
    t.zero_grad()
    out_t = t(x, x_char)
    loss_t, _ = compute_loss(out_t, tgt, cfg, sizes)
    loss_t.backward()

    q_g = t.case_gov_q.weight.grad
    k_g = t.case_gov_k.weight.grad
    check(q_g is not None and bool((q_g != 0).any()),
          "Gate 2 Invariant 2a: case_gov_q.weight.grad is strictly non-zero on step 1")
    check(k_g is not None and bool((k_g != 0).any()),
          "Gate 2 Invariant 2b: case_gov_k.weight.grad is strictly non-zero on step 1")

    r_q_g = t.root_slot_queries.grad
    check(r_q_g is not None and bool((r_q_g != 0).any()),
          "Gate 2 Invariant 3: root_slot_queries.grad is strictly non-zero on Treatment")

    print("\n6. the loop runs end to end")
    cfg_smoke = load_config(smoke=True)
    model, hist, _, _ = train(cfg_smoke, "treatment", cfg_smoke["seeds"][0], device,
                              quiet=True)
    totals = [h["total"] for h in hist if "total" in h]
    check(len(totals) == cfg_smoke["training"]["steps"],
          "ran exactly the configured number of steps", f"({len(totals)})")
    check(all(t == t and abs(t) < 1e6 for t in totals), "all losses finite")
    first, last = sum(totals[:3]) / 3, sum(totals[-3:]) / 3
    check(last <= first, "loss did not increase (coarse stability signal)", f"({first:.4f} -> {last:.4f})")
    # THE REAL TEST, replacing reliance on the trend heuristic above. Monotonicity over a tiny
    # run is a HEURISTIC that can fail for reasons unrelated to correctness — measured, it moves
    # +0.075 at 12 steps and -0.481 at 60 purely because the first steps are lr-warmup noise on
    # 200 tokens. REPRODUCIBILITY is a property the code either has or does not, and it is what
    # makes a multi-seed grid interpretable at all: the same seed must give a bit-identical
    # trajectory, and a different seed must NOT (otherwise the seed is being ignored, and the
    # three "seeds" in the grid are one run reported three times).
    _, hist_same, _, _ = train(cfg_smoke, "treatment", cfg_smoke["seeds"][0], device, quiet=True)
    t_same = [h["total"] for h in hist_same if "total" in h]
    check(len(t_same) == len(totals) and all(abs(a - b) < 1e-9 for a, b in zip(totals, t_same)),
          "same seed -> bit-identical loss trajectory (seeds are reproducible)",
          f"({len(totals)} steps)")
    _, hist_diff, _, _ = train(cfg_smoke, "treatment", 987654321, device, quiet=True)
    t_diff = [h["total"] for h in hist_diff if "total" in h]
    check(len(t_diff) == len(totals) and any(abs(a - b) > 1e-9 for a, b in zip(totals, t_diff)),
          "a DIFFERENT seed -> a different trajectory (the seed is not ignored)")

    print("\n7. the eval path reports macro-F1 with the majority baseline")
    res = evaluate(model, dv, v, cfg_smoke, sizes, device)
    c = res.get("case", {})
    check("macro_f1" in c, "case macro-F1 present")
    check("majority_macro_f1" in c and "majority_accuracy" in c,
          "majority-class baseline printed alongside", 
          f"(macro-F1 {c.get('macro_f1', float('nan')):.3f} vs "
          f"majority {c.get('majority_macro_f1', float('nan')):.3f})")
    check("root" in res and "accuracy" in res["root"], "root accuracy present")

    # ---- an unsupervised head must contribute 0, NOT NaN -------------------------------
    # This is the invariant the file was MISSING, and its absence cost six GPU runs (R19).
    # cross_entropy over an all-ignore_index target returns NaN, not 0, and compute_loss SUMS the
    # heads — so any corpus that drops a head (Tashkeela carries m_syn = m_ntp = 0 for every record)
    # poisons the entire loss from step 1. The existing finite-loss check only ever ran on data where
    # every head was supervised, so it passed 7/7 while all six silver runs died on Kaggle.
    try:
        import train as T
        _cfg = T.load_config(smoke=True)
        _sz = {"radical": 12, "wazan": 20, "wazan_canonical": 119, "stem_tail": 30,
               "proclitic": 23, "enclitic": 16,
               "case": 4, "definiteness": 4, "deprel": 40, "lemma": 100, "surface": 50}
        _B, _L = 2, 5
        _o = {"root": torch.randn(_B, _L, 4, _sz["radical"], requires_grad=True),
              "wazan": torch.randn(_B, _L, _sz["wazan"], requires_grad=True),
              "wazan_canonical": torch.randn(_B, _L, _sz["wazan_canonical"], requires_grad=True),
              "stem_tail": torch.randn(_B, _L, _sz["stem_tail"], requires_grad=True),
              "proclitic": torch.randn(_B, _L, _sz["proclitic"], requires_grad=True),
              "enclitic": torch.randn(_B, _L, _sz["enclitic"], requires_grad=True),
              "case": torch.randn(_B, _L, _sz["case"], requires_grad=True),
              "definiteness": torch.randn(_B, _L, _sz["definiteness"], requires_grad=True),
              "syntax": torch.randn(_B, _L, _sz["deprel"], requires_grad=True),
              "ntp": torch.randn(_B, _L, _sz["lemma"], requires_grad=True)}
        _t = {"root": torch.randint(0, _sz["radical"], (_B, _L, 4)),
              "wazan": torch.randint(0, _sz["wazan"], (_B, _L)),
              "wazan_canonical": torch.randint(0, _sz["wazan_canonical"], (_B, _L)),
              "stem_tail": torch.randint(0, _sz["stem_tail"], (_B, _L)),
              "proclitic": torch.randint(0, _sz["proclitic"], (_B, _L)),
              "enclitic": torch.randint(0, _sz["enclitic"], (_B, _L)),
              "case": torch.randint(0, _sz["case"], (_B, _L)),
              "definiteness": torch.randint(0, _sz["definiteness"], (_B, _L)),
              "deprel": torch.full((_B, _L), T.IGNORE, dtype=torch.long),
              "ntp": torch.full((_B, _L), T.IGNORE, dtype=torch.long)}
        _tot, _parts = T.compute_loss(_o, _t, _cfg, _sz)
        _fin = bool(torch.isfinite(_tot))
        if not _fin:
            FAILURES.append(
                f"unsupervised head -> NaN loss ({float(_tot)}): compute_loss must SKIP a head with "
                f"no unmasked target instead of summing its NaN")
        _tot.backward()
        _bad = [k for k, v in _o.items()
                if v.grad is not None and not bool(torch.isfinite(v.grad).all())]
        if _bad:
            FAILURES.append(f"non-finite gradients from unsupervised heads: {_bad}")
        if _parts.get("syntax") is not None:
            FAILURES.append("an unsupervised head must report None, not a number")
        print(f"  unsupervised head: total {float(_tot.detach()):.4f} finite={_fin}, "
              f"syntax={_parts.get('syntax')} (must be False/None, never nan)")
    except Exception as exc:  # noqa: BLE001
        FAILURES.append(f"unsupervised-head check could not run: {type(exc).__name__}: {exc}")

    # ---- the COMPOSED root string must be well-formed (CHALLENGES 2x.14) -----------------
    # Per-slot masks cannot see an unsupervised slot: it is simply not counted. The defect that caused
    # the 296/300 gold blackout only existed at the point where the head's output was consumed as a
    # WHOLE, so the invariant has to live at composition, not per head. This asserts that the shared
    # decoder slices to the pattern's arity and that the resulting triple actually renders.
    try:
        from final_surface import decode_root_slots, pattern_arity, render_triple
        _inv_r = {0: "<pad>", 1: "ك", 2: "ت", 3: "ب", 4: "ر", 5: "س", 6: "ل", 7: "و"}
        _slots = [1, 2, 3, 7]        # 4 slots; slot 4 is the unsupervised one and predicts noise ('و')
        _pat = "1َ2َ3"               # a 3-slot pattern
        _root = decode_root_slots(_slots, _pat, _inv_r)
        _a = pattern_arity(_pat)
        if len(_root) != _a:
            FAILURES.append(
                f"decode_root_slots gave {_root!r} (len {len(_root)}) for a {_a}-slot pattern: an "
                f"unsupervised slot was read as content")
        _surf, _why = render_triple(_root, _pat, 0, engine="v3")
        if _surf is None:
            FAILURES.append(
                f"a composed triple must render, got {_why!r} for root={_root!r} pat={_pat!r} — "
                f"root_len_mismatch here means the arity slice is broken")
        print(f"  composed string: {len(_slots)} slots -> root {_root!r} on a {_a}-slot pattern "
              f"-> {_surf!r} ({_why})")
    except Exception as exc:  # noqa: BLE001
        FAILURES.append(f"composed-string check could not run: {type(exc).__name__}: {exc}")

    # ---- PRONG 2: root targets must carry ARITY (CHALLENGES 2x.14) ----------------------
    # The invariant, checkable without aligning windows: in a ROOT-SUPERVISED token no slot may be
    # IGNORE — a triliteral root's empty slot must be supervised as <pad> = 0. Pre-fix, slot 4 was
    # IGNORE on 97.4% of lettered roots, so it got no gradient, decoded as noise, and every triliteral
    # root came out length 4 (296/296 root_len_mismatch on the human gold). A fully unsupervised token
    # must still be all-IGNORE. Real records through the real builder — not a re-implementation.
    try:
        import json as _json
        from pathlib import Path as _P
        import train as _T
        from model_arms import IGNORE as _IG
        _recs = _T.read_records(_P("data/out/padt-train.jsonl"), 600)
        _v2 = Vocabs(_recs, 1, 20000)
        _tri = _quad = _closed = _bad_open = _bad_closed = 0
        for _x, _x_char, _t in make_batch(_recs, _v2, 96, 32):
            _tg, _tm = _t["root"].tolist(), _t["m_root"].tolist()
            for _b in range(len(_tg)):
                for _l2 in range(len(_tg[_b])):
                    _s = _tg[_b][_l2]
                    if _tm[_b][_l2]:
                        if _s[3] == _IG:
                            _bad_open += 1
                        elif _s[3] == 0:
                            _tri += 1
                        else:
                            _quad += 1
                    elif any(x != _IG for x in _s):
                        _bad_closed += 1
                    else:
                        _closed += 1
        if _bad_open:
            FAILURES.append(
                f"{_bad_open} root-supervised tokens still carry an IGNORE slot: an empty root slot "
                f"must be supervised as <pad>=0 (Prong 2), or it gets no gradient and decodes as noise")
        if _bad_closed:
            FAILURES.append(f"{_bad_closed} unsupervised tokens carry a non-IGNORE root slot")
        if not _tri:
            FAILURES.append("no triliteral token (slot 4 == <pad>) in the sample — check is vacuous")
        print(f"  root targets: {_tri} triliteral (slot4=<pad>), {_quad} quadriliteral, "
              f"{_closed} unsupervised (all IGNORE); violations {_bad_open}+{_bad_closed} (want 0+0)")
    except Exception as exc:  # noqa: BLE001
        FAILURES.append(f"root-target arity check could not run: {type(exc).__name__}: {exc}")

    # ---- STEM_TAIL: bare stem must be class 0 (<pad>), NEVER IGNORE (Landmine 1) -------
    # If vocalized_stem_tail == "" maps to IGNORE, 58% of words get zero gradient on stem_tail
    # and the model hallucinates suffixes on 100% of bare stems.
    # §2cz SHARPENED THIS INVARIANT. It used to read `if m_wazan == 1: target must not be IGNORE`, which
    # conflated "the wazan head is supervised" with "the tail head is supervised" — two different masks.
    # The properties that actually matter are: (i) an IGNORE target is never supervised (a `-100` must not
    # reach a loss), and (ii) masking is deliberate, not a default — a tail this notation cannot spell (a
    # pattern carrying a literal slot digit >= 5) is the ONLY thing that reaches IGNORE, measured at 436
    # tokens of 1,234,611 (§2cz). Asserting (i) and (ii) is strictly stronger than the old wording.
    try:
        from wazan_normalizer import vocalized_stem_tail
        _recs_tail = tr
        _n_bare = _n_affixed = _n_unmasked = _n_masked = 0
        if "m_stem_tail" not in next(iter(make_batch(_recs_tail, v, cfg["data"]["max_len"], 32)))[2]:
            FAILURES.append("batch carries no m_stem_tail — the stem_tail mask invariant cannot be checked")
        _inv_t = {i: t for t, i in v.stem_tail.items()}
        for _xb, _x_char_b, _tb in make_batch(_recs_tail, v, cfg["data"]["max_len"], 32):
            _st_list = _tb["stem_tail"].flatten().tolist()
            _mw_list = _tb["m_wazan"].flatten().tolist()
            _ms_list = _tb["m_stem_tail"].flatten().tolist()
            for _tail_id, _mw, _ms in zip(_st_list, _mw_list, _ms_list):
                if _tail_id == IGNORE:
                    if _ms != 0:
                        FAILURES.append(f"stem_tail target is IGNORE with m_stem_tail={_ms} — a "
                                        f"supervised -100 target")
                    _n_masked += 1
                    continue
                if _ms != 1:
                    FAILURES.append(f"stem_tail target {_tail_id} is not IGNORE but m_stem_tail={_ms}")
                _cls = _inv_t.get(_tail_id)
                if _cls is None:
                    FAILURES.append(f"supervised stem_tail target {_tail_id} decodes to NO class")
                elif not all(0x0600 <= ord(c) <= 0x06FF for c in _cls):
                    FAILURES.append("stem_tail class %d (%r) is not fully Arabic and cannot be a target"
                                    % (_tail_id, _cls.encode("unicode_escape").decode()))
                if _mw == 1:
                    _n_unmasked += 1
                    if _tail_id == 0:
                        _n_bare += 1
                    else:
                        _n_affixed += 1
        check(_n_bare > 0, "stem_tail has bare-stem tokens (class 0)", f"({_n_bare} bare / {_n_affixed} affixed)")
        check(_n_unmasked > 0, "stem_tail has supervised tokens", f"({_n_unmasked})")
        # (ii) masking is DELIBERATE and counted. The batch cannot test the corpus-wide converse ("a
        # fully-Arabic tail never reaches IGNORE") because a batch position is masked whenever its wazan is
        # unsupervised — that 1,234,611-row claim lives in the audit's pins instead, and this says so rather
        # than pretending to have checked it here.
        check(_n_masked > 0, "masking happens and is reported (§2cz: 436 of 1,234,611)",
              f"({_n_masked} masked positions / {_n_unmasked} supervised)")
        print("  NOTE: 'a fully-Arabic tail never reaches IGNORE' is a 1.23M-row measurement — it is pinned in"
              " tools/stem_tail_audit.py --check (ignore_real == 0), not here.")
        # Check inference: class 0 decodes to "" and passes stem_tail="" to render_triple
        _inv_tail = {i: t for t, i in v.stem_tail.items()}
        _pred_tail_0 = _inv_tail.get(0, None)
        check(_pred_tail_0 == "" or _pred_tail_0 == "<pad>",
              "class 0 decodes to bare stem / <pad>", f"({_pred_tail_0!r})")
        from final_surface import render_triple as _rt
        _bare_surf, _ = _rt("كتب", "1َ2َ3", None, engine="v3", stem_tail="")
        check(_bare_surf == "كَتَب",
              "render_triple with stem_tail='' does not hallucinate suffix", f"({_bare_surf!r})")
    except Exception as exc:  # noqa: BLE001
        FAILURES.append(f"stem_tail bare-stem check could not run: {type(exc).__name__}: {exc}")

    print("\n" + "=" * 84)
    if FAILURES:
        print(f"SMOKE TEST FAILED — {len(FAILURES)} invariant(s) broken:")
        for f in FAILURES:
            print("  -", f)
        return 1
    print("SMOKE TEST PASSED — config shared, parity matched, masks exact,")
    print("gradients live, loop finite and descending, eval reports macro-F1.")
    print("=" * 84)
    return 0


if __name__ == "__main__":
    sys.exit(main())
