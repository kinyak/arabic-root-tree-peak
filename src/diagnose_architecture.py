"""diagnose_architecture.py — WHICH PART IS WRONG.

The question this answers, in one CPU-only pass: among the pipeline's parts, which one is
BINDING the conjunctive end-to-end number, and what would each part have to become for the
target to be reachable?

WHY COMPONENT ACCURACIES ALONE CANNOT ANSWER IT
    root 57.2% / wazan 17.6% / case 44.3% is three numbers, not a diagnosis. The pipeline's
    output is their CONJUNCTION, so the part that costs the most is the part with the most
    headroom *relative to its own ceiling*, weighted by the others. So every component is
    reported beside (i) its own prior floor (a constant predictor), (ii) its oracle ceiling
    (the gold answer supplied), and (iii) the CONJUNCTIVE delta from lifting it to that ceiling.
    The sort of that last column is the answer.

AND WHY A LINEAR PROBE IS PART OF IT
    A head can be weak because the HEAD is wrong, because the REPRESENTATION feeding it lacks
    the information, or because the information is not in the input at all. Those need three
    different fixes (retrain the head / change the architecture / change the input). A probe
    fitted on the FROZEN trunk states separates them: probe >> head means the head is the
    defect; probe ~ head means the representation is; probe ~ prior means the input is.

LOADING IS PART OF THE MEASUREMENT (EVIDENCE_LOG §2cq)
    Every v20 checkpoint must be read by `src/legacy_arch.py` (0 missing / 0 unexpected) or the
    numbers describe a fabricated model. This module REFUSES to score a checkpoint it cannot
    load exactly, and records which reader it used.

USAGE
    python src/diagnose_architecture.py --ckpt <pt> [--ckpt <pt> ...] [--probe] [--json out.json]
    python src/diagnose_architecture.py --verify-legacy      # the §2cq reproduction check
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import eval_harness as EH                      # noqa: E402
import legacy_arch as LA                       # noqa: E402
import model_arms as MA                        # noqa: E402
from final_surface import decode_root_slots, render_triple  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
GOLD = REPO / "data" / "annotation" / "gold-tashkeela-300.jsonl"
CKPT_DIR = REPO / "dist" / "kaggle-output" / "checkpoints"

# The 2026-10-13 recorded figures, re-derived by §2cq with the faithful reader. Any change to
# these means the reader, the gold file, or the metric moved -- all three are supposed to be frozen.
PINNED = {
    "gold-baseline": {"root": (89, 278), "triple": 8, "e2e_off_stem": 9, "e2e_on_stem": 199},
    "gold-treatment": {"root": (67, 278), "triple": 5, "e2e_off_stem": 5, "e2e_on_stem": 205},
    "silver-baseline": {"root": (136, 278), "triple": 18, "e2e_off_stem": 14, "e2e_on_stem": 192},
    "silver-treatment": {"root": (159, 278), "triple": 16, "e2e_off_stem": 11, "e2e_on_stem": 191},
}
# §2cg / §2co ceilings, for the target-feasibility audit. Named with the section that paid for them.
CEILINGS = {
    "compiler_gold_plan_resource_OFF": (0.788, "§2co gold-300, gold MorphPlan, resource OFF"),
    "compiler_gold_plan_resource_ON": (0.862, "frozen ruler 862/1000, the shipped dictionary path"),
    "case_from_deprel_oracle_macroF1": (0.7331, "item 10, gold upos+deprel on PADT"),
    "case_human_agreement_macroF1": (0.459, "CALIMA-vs-human ceiling, §2au"),
}
TARGET = 0.98


# ------------------------------------------------------------------ loading
def build_faithful(path: Path, seed: int = 0):
    """Return (model, ck, reader_name). REFUSES a checkpoint no reader can load exactly."""
    ck = torch.load(path, map_location="cpu", weights_only=False)
    sizes = dict(ck.get("sizes") or {})
    for name, mod in (("legacy_arch", LA), ("model_arms", MA)):
        torch.manual_seed(seed)
        try:
            model = mod.Arm(ck["cfg"], dict(sizes), ck.get("arm", "treatment"))
        except Exception:                                    # noqa: BLE001  (KeyError: not this arch)
            continue
        inc = model.load_state_dict(ck["model"], strict=False)
        if not inc.missing_keys and not inc.unexpected_keys:
            model.eval()
            return model, ck, name
    raise SystemExit(
        f"REFUSED: no faithful reader for {path.name}. A checkpoint loaded with absent tensors "
        f"describes a fabricated model (§2cq) -- its numbers are not measurements. Readers tried: "
        f"legacy_arch (vendored 2026-10-13), model_arms (current).")


def vocabs_from(ck):
    for mod in (MA, LA):
        try:
            return mod.Vocabs.from_dict(ck["vocab"])
        except Exception:                                    # noqa: BLE001
            continue
    raise SystemExit("cannot rebuild the vocabulary from the checkpoint")


# ------------------------------------------------------------------ one forward pass
def predict(model, V, gold, max_len, want_hidden=False):
    """Every row's prediction + everything the census needs. One pass, no second decode."""
    inv_w = {i: w for w, i in V.wazan.items()}
    inv_r = {i: c for c, i in V.radical.items()}
    n_slots = getattr(model, "n_root_slots", 4)
    rows, H = [], []
    with torch.no_grad():
        for g in gold:
            toks, idx = EH.parse_gold_context(g.get("context") or "")
            if not toks:
                continue
            if len(toks) > max_len:
                lo = max(0, min(idx - max_len // 2, len(toks) - max_len))
                toks, idx = toks[lo:lo + max_len], idx - lo
            x = torch.tensor([[V.encode(t) for t in toks]])
            xc = []
            for t in toks:
                ch = [V.char.get(c, 0) for c in t[:20]]
                xc.append(ch + [0] * (20 - len(ch)))
            x_char = torch.tensor([xc])
            h = model.encode(x, x_char)
            o = model(x, x_char)
            if want_hidden:
                H.append(h[0, idx].cpu().numpy().copy())

            pred_waz = inv_w.get(int(o["wazan"][0, idx].argmax())) if o.get("wazan") is not None else None
            slots = o["root"][0, idx].argmax(-1).tolist() if o.get("root") is not None else None
            gw = g.get("t_wazan_pattern")
            pred = {
                "id": g.get("id"),
                # THE TOKEN THE MODEL ACTUALLY READS. The gold `form` is the LABEL; feeding it to a
                # renderer whose resource keys the token's SKELETON turns the resource into an oracle
                # (measured: this is what produced a 207/300 "resource-OFF" leg for the WORST arm).
                "ctx": toks[idx],
                "oov": V.encode(toks[idx]) == 1,
                "gold_root": EH.to_bare_root_str(g["t_root_arabic"]) if g.get("t_root_arabic") else None,
                "gold_waz": EH.nfc(gw) if gw else None,
                "gold_case": int(g["t_case"]) if g.get("t_case") is not None else None,
                "pred_waz": pred_waz,
                # arity from the PREDICTED pattern == the shipped path
                "pred_root": EH.to_bare_root_str(decode_root_slots(slots, pred_waz, inv_r)) if slots else None,
                # arity from the GOLD pattern == the decode's oracle (isolates head from conditioning)
                "pred_root_gold_arity": (EH.to_bare_root_str(decode_root_slots(slots, gw, inv_r))
                                         if slots and gw else None),
                "slot_ids": slots[:n_slots] if slots else None,
                "pred_case": int(o["case"][0, idx].argmax()) if o.get("case") is not None else None,
            }
            rows.append(pred)
    return rows, (H if want_hidden else None)


def _nfc_eq(a, b):
    return a is not None and b is not None and EH.nfc(a) == EH.nfc(b)


def _slot_set(a, b):
    import re
    if a is None or b is None:
        return False
    return sorted(re.findall(r"[1-4]", a)) == sorted(re.findall(r"[1-4]", b))


def _diac_free(lab):
    return EH.nfc(EH.strip_diac(lab)) if lab else None


# ------------------------------------------------------------------ census
def census(rows, gold_waz_classes=None):
    c = collections.Counter()
    per_slot = collections.Counter()
    case_g, case_p = [], []
    for r in rows:
        is_root = r["gold_root"] is not None
        is_waz = r["gold_waz"] is not None
        is_case = r["gold_case"] is not None
        if is_root:
            ok = r["pred_root"] == r["gold_root"]
            c["root_n"] += 1
            c["root_ok"] += ok
            c["root_iv_n" if not r["oov"] else "root_oov_n"] += 1
            c["root_iv_ok" if not r["oov"] else "root_oov_ok"] += ok
            # per-slot
            want = r["gold_root"]
            for i, ch in enumerate(r["pred_root"] or ""):
                c["rslot_n"] += 1
                c["rslot_ok"] += (i < len(want) and ch == want[i])
            r["root_ok"] = ok
        if is_waz:
            c["waz_n"] += 1
            c["waz_raw_ok"] += _nfc_eq(r["pred_waz"], r["gold_waz"])
            c["waz_hamza_ok"] += (EH.lead_hamza_variant(r["pred_waz"]) == EH.lead_hamza_variant(r["gold_waz"]))
            c["waz_diacfree_ok"] += (_diac_free(r["pred_waz"]) == _diac_free(r["gold_waz"]))
            c["waz_slot_ok"] += _slot_set(r["pred_waz"], r["gold_waz"])
            r["waz_raw_ok"] = _nfc_eq(r["pred_waz"], r["gold_waz"])
            r["waz_slot_ok"] = _slot_set(r["pred_waz"], r["gold_waz"])
            per_slot[r["gold_waz"]] += 1
        if is_case and r["pred_case"] is not None:
            case_g.append(r["gold_case"]), case_p.append(r["pred_case"])
            r["case_ok"] = r["gold_case"] == r["pred_case"]
    maj = collections.Counter(case_g).most_common(1)[0] if case_g else (None, 0)
    macro = EH.prf_per_class(case_g, case_p, labels=(0, 1, 2)) if case_g else {}
    c["case_n"] = len(case_g)
    c["case_ok"] = sum(a == b for a, b in zip(case_g, case_p))
    c["case_majority_ok"] = sum(1 for a in case_g if a == maj[0])
    return c, {"macro_f1": macro.get("macro_f1"), "majority_class": maj[0],
               "majority_acc": maj[1] / max(len(case_g), 1)}, per_slot


# ------------------------------------------------------------------ the answer: sensitivity
def eligible(rows):
    return [r for r in rows
            if r["gold_root"] is not None and r["gold_waz"] is not None and r["gold_case"] is not None
            and r["pred_case"] is not None]


def sensitivity(rows):
    """Conjunctive triple on the SAME rows, then each component lifted to its own ceiling."""
    R = eligible(rows)
    n = len(R)
    if not n:
        return {}
    root_ok = sum(r["root_ok"] for r in R)
    wraw_ok = sum(r["waz_raw_ok"] for r in R)
    wslo_ok = sum(r["waz_slot_ok"] for r in R)
    case_ok = sum(r["case_ok"] for r in R)
    triple = sum(r["root_ok"] and r["waz_raw_ok"] and r["case_ok"] for r in R)
    variants = {
        "TRIPLE_raw__shipped": triple / n,
        "TRIPLE_slotset_wazan": sum(r["root_ok"] and r["waz_slot_ok"] and r["case_ok"] for r in R) / n,
        "TRIPLE_raw__no_case": sum(r["root_ok"] and r["waz_raw_ok"] for r in R) / n,
    }
    lifts = {
        "root head -> oracle (gold root)":
            sum(r["waz_raw_ok"] and r["case_ok"] for r in R) / n - triple / n,
        "wazan head -> oracle (gold pattern, raw)":
            sum(r["root_ok"] and r["case_ok"] for r in R) / n - triple / n,
        "case head -> oracle (gold case)":
            sum(r["root_ok"] and r["waz_raw_ok"] for r in R) / n - triple / n,
        "root ARITY -> gold pattern (decode conditioning only)":
            sum(r["pred_root_gold_arity"] == r["gold_root"] for r in R) / n - root_ok / n,
        # NOT a gold-oracle: the SAME head, the SAME weights, scored in the other space. Supplying the
        # gold pattern instead would make slot-set trivially true and duplicate the oracle row above.
        "NOTATION ONLY: score the same wazan output as a radical slot-SET":
            variants["TRIPLE_slotset_wazan"] - variants["TRIPLE_raw__shipped"],
    }
    return {"n_eligible": n, "components": {"root": root_ok / n, "wazan_raw": wraw_ok / n,
                                            "wazan_slots": wslo_ok / n, "case": case_ok / n},
            "triple_variants": variants,
            "marginal_pp_if_lifted_to_ceiling": {k: v * 100 for k, v in
                                                 sorted(lifts.items(), key=lambda kv: -kv[1])}}


# ------------------------------------------------------------------ compiler
def compiler(rows, gold):
    """End-to-end through render_triple: the MODEL's plan vs the GOLD plan (the ceiling).

    TWO DEFECTS ARE PINNED HERE, both found by a structurally suspicious number: `gold-baseline`
    (the WORST arm) read 207/300 on the "resource-OFF" leg while `silver-treatment` (the BEST) read
    15/300. A worse planner cannot score better; that inversion is a bug report, not a result.

      1. ORDER. The first version built `triples` ONCE, outside the resource loop, so the
         "resource OFF" and "resource ON" rows were the SAME render — the resource axis was never
         measured, and the number labelled OFF was in fact a resource-ON render. Both settings are
         rendered inside the loop now, and `changed` is printed because a policy that fires nowhere
         is otherwise indistinguishable from one that fires everywhere.
      2. THE ORACLE TOKEN. The plan is rendered with the token the MODEL READS (`ctx`). Passing the
         gold `form` instead hands the spelling resource the LABEL's skeleton; the resource then
         answers from the corpus without consulting the plan at all, which is exactly why a bad
         planner scored 207/300. The gold-token variant is kept, labelled ORACLE, and is a ceiling —
         never a pipeline number.
    """
    by_id = {r["id"]: r for r in rows}
    plans = {}
    for plan in ("model", "gold"):
        plans[plan] = []
        for g in gold:
            r = by_id.get(g.get("id"))
            if r is None:
                continue
            if plan == "model":
                rt, w, cs = r["pred_root"], r["pred_waz"], r["pred_case"]
            else:
                rt, w, cs = (EH.to_bare_root_str(g["t_root_arabic"]) if g.get("t_root_arabic") else None,
                             EH.nfc(g["t_wazan_pattern"]) if g.get("t_wazan_pattern") else None,
                             int(g["t_case"]) if g.get("t_case") is not None else None)
            plans[plan].append((g, r, rt, w, cs))

    out = {}
    for plan, items in plans.items():
        for tok_src in ("ctx", "gold_ORACLE"):
            for res_on in (False, True):
                os.environ["ARABIC_SPELLING_RESOURCE"] = "1" if res_on else "0"
                triples = []
                for g, r, rt, w, cs in items:
                    token = r["ctx"] if tok_src == "ctx" else g.get("form")
                    triples.append((g.get("form"),) + tuple(render_triple(rt, w, cs, token=token)))
                sc = EH.score_final_surface(triples)
                key = f"{plan}_plan__token_{tok_src}__resource_{'ON' if res_on else 'OFF'}"
                out[key] = {k: sc[k] for k in ("n", "coverage", "abstain", "stem_correct", "stem_yield",
                                               "stem_accuracy_of_covered", "token_exact",
                                               "token_exact_yield", "skeleton_yield") if k in sc}
                if tok_src == "ctx":
                    out[key]["_renders"] = [t[1] for t in triples]
        # how many rows does the resource actually change? 0 on a population expected to move = a bug
        off = out.get(f"{plan}_plan__token_ctx__resource_OFF")
        on = out.get(f"{plan}_plan__token_ctx__resource_ON")
        if off and on:
            ro, rn = off.pop("_renders"), on.pop("_renders")
            out[f"{plan}_plan__resource_CHANGED_rows"] = sum(a != b for a, b in zip(ro, rn))
    os.environ["ARABIC_SPELLING_RESOURCE"] = "0"
    return out


# ------------------------------------------------------------------ linear probe
def probe(H, rows, tag=""):
    """Frozen-trunk probes: does the REPRESENTATION carry the target the head is failing?"""
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import cross_val_score
    from sklearn.preprocessing import StandardScaler

    X = np.asarray(H)
    res = {}
    # per-slot radical (same target the root head predicts)
    for s in range(4):
        y, keep = [], []
        for i, r in enumerate(rows):
            if r["gold_root"] is not None and len(r["gold_root"]) > s:
                y.append(r["gold_root"][s]), keep.append(i)
        if len(set(y)) < 2:
            res[f"slot{s + 1}"] = {"n": len(y), "note": "single class"}
            continue
        Xs = StandardScaler().fit_transform(X[keep])
        classes = {ch: j for j, ch in enumerate(sorted(set(y)))}
        yv = np.array([classes[ch] for ch in y])
        res[f"slot{s + 1}"] = _fit_probe(LogisticRegression, cross_val_score, Xs, yv, len(y),
                                        {"classes": len(classes)})
    # wazan skeleton (slot-set), the notation-free target
    import re
    yw, kw = [], []
    for i, r in enumerate(rows):
        if r["gold_waz"]:
            # the ORDERED digit sequence, not the sorted set: the sorted set has 2 classes in this
            # gold and one of them holds 98.9% of the rows, so a probe scoring 0.9892 on all four
            # ARMS ALIKE was reporting the base rate and nothing else. Ordered keeps 3- vs 4-slot
            # templates apart.
            yw.append("".join(re.findall(r"[1-4]", r["gold_waz"]))), kw.append(i)
    if len(set(yw)) > 1:
        Xs = StandardScaler().fit_transform(X[kw])
        classes = {c: j for j, c in enumerate(sorted(set(yw)))}
        yv = np.array([classes[c] for c in yw])
        res["wazan_slotseq"] = _fit_probe(LogisticRegression, cross_val_score, Xs, yv, len(yw),
                                         {"classes": len(classes)})
    # case (3 classes)
    yc, kc = [], []
    for i, r in enumerate(rows):
        if r["gold_case"] is not None:
            yc.append(r["gold_case"]), kc.append(i)
    if len(set(yc)) > 1:
        Xs = StandardScaler().fit_transform(X[kc])
        yv = np.array(yc)
        res["case"] = _fit_probe(LogisticRegression, cross_val_score, Xs, yv, len(yc),
                                 {"classes": 3,
                                  "majority_acc": max(yc.count(k) for k in set(yc)) / len(yc)})
    return res


def _fit_probe(LogisticRegression, cross_val_score, Xs, yv, n, extra):
    """A probe that cannot fit is a FINDING, not a crash -- and EVERY probe reports the trivial
    predictor's score beside its own, because a probe that only reproduces the base rate is
    indistinguishable from a representation that carries the information."""
    import numpy as np
    counts = np.bincount(yv)
    present = counts[counts > 0]
    majority = float(present.max()) / float(present.sum())
    out = dict(extra)
    out["n"] = int(n)
    out["majority_acc"] = majority
    folds = int(min(5, present.min()))
    if folds < 2:
        out["probe"] = f"not fittable (smallest class has {int(present.min())} rows)"
        out["informative"] = "n/a"
        return out
    try:
        clf = LogisticRegression(max_iter=2000)
        cv = float(np.mean(cross_val_score(clf, Xs, yv, cv=folds)))
        clf.fit(Xs, yv)
        out["probe_cv_acc"] = cv
        out["probe_train_acc"] = float(clf.score(Xs, yv))
        out["vs_majority"] = cv - majority
        out["informative"] = bool(cv - majority > 0.02)
    except Exception as e:                                   # noqa: BLE001
        out["probe"] = f"{type(e).__name__}: {e}"
        out["informative"] = "n/a"
    return out


# ------------------------------------------------------------------ reporting
def show(title, payload, indent="  "):
    print(f"\n{'-' * 92}\n{title}\n{'-' * 92}")
    for k, v in payload.items():
        if isinstance(v, dict):
            print(f"{indent}{k}:")
            for kk, vv in v.items():
                print(f"{indent}  {kk:52s} {vv if not isinstance(vv, float) else f'{vv:.4f}'}")
        else:
            print(f"{indent}{k:54s} {v if not isinstance(v, float) else f'{v:.4f}'}")


def verdict(sens, comp, cstats):
    n = sens["n_eligible"]
    base = sens["triple_variants"]["TRIPLE_raw__shipped"]
    lifts = sens["marginal_pp_if_lifted_to_ceiling"]
    print(f"\n{'=' * 92}\nWHERE THE MASS IS (n={n} rows with all three gold labels)\n{'=' * 92}")
    print(f"  the shipped conjunction            {base * 100:5.1f}%   "
          f"(root {comp['root'] * 100:.1f} x wazan {comp['wazan_raw'] * 100:.1f} x case {comp['case'] * 100:.1f}"
          f"  = {comp['root'] * comp['wazan_raw'] * comp['case'] * 100:.1f}%)")
    print("\n  marginal gain from lifting ONE component to its own ceiling (pp of the conjunction):")
    for k, v in lifts.items():
        print(f"    {v:+6.1f}   {k}")
    print(f"\n  notation alone is worth "
          f"{lifts['NOTATION ONLY: score the same wazan output as a radical slot-SET']:+.1f} pp "
          f"to the conjunction; the wazan raw->slots gap on that head is "
          f"{(comp['wazan_slots'] - comp['wazan_raw']) * 100:+.1f} pp")
    print(f"\n  TARGET FEASIBILITY ({TARGET * 100:.0f}%):")
    for k, (val, src) in CEILINGS.items():
        flag = "REACHABLE" if val >= TARGET else f"CAPS ANY MODEL AT {val * 100:.1f}%"
        print(f"    {k:38s} {val * 100:5.1f}%   {flag}   ({src})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", action="append", default=[])
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--json")
    ap.add_argument("--verify-legacy", action="store_true")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    if args.verify_legacy:
        return verify_legacy()

    ckpts = [Path(p) for p in args.ckpt] or sorted(CKPT_DIR.glob("*-s20261009.pt"))
    gold = EH.load_human_gold(str(GOLD))
    if args.limit:
        gold = gold[:args.limit]
    print(f"gold   : {len(gold)} rows  ({GOLD})")
    OUT = {}

    for path in ckpts:
        model, ck, reader = build_faithful(path)
        V = vocabs_from(ck)
        max_len = (ck["cfg"].get("data") or {}).get("max_len", 96)
        print(f"\n{'=' * 92}\n{path.stem}   reader={reader}  arm={ck.get('arm')}  seed={ck.get('seed')}\n{'=' * 92}")
        print(f"  tensors: model {len(model.state_dict())} == checkpoint {len(ck['model'])}  (0 missing / 0 unexpected)")
        print(f"  vocab  : { {k: (len(v) if hasattr(v, '__len__') else v) for k, v in ck['vocab'].items() if k in ('form','char','radical','wazan')} }")
        print(f"  new modules in this checkpoint: "
              f"{sorted({k.split('.')[0] for k in ck['model']})}")

        rows, H = predict(model, V, gold, max_len, want_hidden=args.probe)
        c, cstats, wclasses = census(rows)
        n_oov = sum(r["oov"] for r in rows)
        show("INPUTS", {"rows_with_context": len(rows), "oov_tokens": n_oov,
                        "oov_rate": n_oov / max(len(rows), 1),
                        "surface_vocab": len(V.form), "char_vocab": len(V.char),
                        "wazan_classes": len(V.wazan)})
        show("HEADS", {
            "root whole-exact": f"{c['root_ok']}/{c['root_n']} = {c['root_ok'] / max(c['root_n'], 1):.3f}",
            "root in-vocab": f"{c['root_iv_ok']}/{c['root_iv_n']} = {c['root_iv_ok'] / max(c['root_iv_n'], 1):.3f}",
            "root OOV": f"{c['root_oov_ok']}/{c['root_oov_n']} = {c['root_oov_ok'] / max(c['root_oov_n'], 1):.3f}",
            "root per-slot": f"{c['rslot_ok']}/{c['rslot_n']} = {c['rslot_ok'] / max(c['rslot_n'], 1):.3f}",
            "wazan raw string": f"{c['waz_raw_ok']}/{c['waz_n']} = {c['waz_raw_ok'] / max(c['waz_n'], 1):.3f}",
            "wazan hamza-normalised": f"{c['waz_hamza_ok']}/{c['waz_n']}",
            "wazan diacritic-free": f"{c['waz_diacfree_ok']}/{c['waz_n']}",
            "wazan radical SLOT-SET": f"{c['waz_slot_ok']}/{c['waz_n']} = {c['waz_slot_ok'] / max(c['waz_n'], 1):.3f}",
            "case exact": f"{c['case_ok']}/{c['case_n']} = {c['case_ok'] / max(c['case_n'], 1):.3f}",
            "case majority floor": f"{c['case_majority_ok']}/{c['case_n']} = {cstats['majority_acc']:.3f}",
            "case macro-F1": f"{cstats['macro_f1']:.4f}  (majority macro-F1 is the worthless baseline)",
        })
        sens = sensitivity(rows)
        show("CONJUNCTION & SENSITIVITY", sens)
        comp = compiler(rows, gold)
        show("COMPILER (render_triple through the shipped metric)", comp)
        pr = probe(H, rows) if args.probe else {}
        if pr:
            show("FROZEN-TRUNK LINEAR PROBE (is the info in the REPRESENTATION?)", pr)
        if sens.get("n_eligible"):
            verdict(sens, sens["components"], cstats)
        else:
            print("\n  !! no row carries all three gold labels in this slice — "
                  "the conjunction is undefined (pass more rows)")
        OUT[path.stem] = {"reader": reader, "heads": dict(c), "case_stats": cstats,
                          "sensitivity": sens, "compiler": comp, "probe": pr,
                          "rows": [{k: v for k, v in r.items() if k != "slot_ids"} for r in rows]}

    if args.json:
        Path(args.json).write_text(json.dumps(OUT, indent=2, ensure_ascii=False, default=str) + "\n",
                                   encoding="utf-8", newline="\n")
        print(f"\nwrote {args.json}")
    return 0


def verify_legacy() -> int:
    """§2cq reproduction: the vendored reader must land on the RECORDED numbers, to the row."""
    print("VERIFY-LEGACY — the vendored reader vs the 2026-10-13 recording (EVIDENCE_LOG §2cq)")
    gold = EH.load_human_gold(str(GOLD))
    bad = 0
    for arm, pin in PINNED.items():
        path = CKPT_DIR / f"{arm}-s20261009.pt"
        model, ck, reader = build_faithful(path)
        V = vocabs_from(ck)
        rows, _ = predict(model, V, gold, (ck["cfg"].get("data") or {}).get("max_len", 96))
        c, _, _ = census(rows)
        R = eligible(rows)
        triple = sum(r["root_ok"] and r["waz_raw_ok"] and r["case_ok"] for r in R)
        ok = (reader == "legacy_arch" and (c["root_ok"], c["root_n"]) == pin["root"] and triple == pin["triple"])
        bad += not ok
        print(f"  {arm:18s} reader={reader:12s} root {c['root_ok']}/{c['root_n']} "
              f"(pinned {pin['root'][0]}/{pin['root'][1]})  TRIPLE {triple} (pinned {pin['triple']})  "
              f"{'OK' if ok else 'MISMATCH'}")
    print(f"\n  {'ALL OK — the vendored reader reproduces the recording' if not bad else f'{bad} MISMATCH(ES)'}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
