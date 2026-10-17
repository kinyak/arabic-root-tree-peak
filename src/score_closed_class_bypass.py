"""Stage (ii) — score the closed-class bypass's vocalised half on HELD-OUT vocalised gold.

THE PROBLEM WITH THE RECORDED NUMBER
    `data/closed_class_ambiguity.json` reports 91.09% micro / 99.57% for the >=0.95 head. But the
    majority-vote map and the evidence it was scored against came from the SAME books, so part of
    that is memorisation, not accuracy. The policy cannot be signed off on an in-sample figure.

WHAT THIS DOES
    · MAP    — built from a TRAIN slice of Tashkeela (books 0-INPUT_BOOKS), i.e. what the bypass
               would actually ship: per closed-class surface, the majority vocalisation and its
               confidence (majority share).
    · EVAL   — a DISJOINT slice (books EVAL_START..EVAL_STOP). Every matched token is scored
               against the map. In-domain but genuinely held out.
    · CROSS  — EQTB (Qur'anic), best-effort: a different corpus in a different orthography, so it
               measures transfer rather than fit.
    · The point of the exercise: does Tier 1 (confidence >= 0.95) actually hold ~99.5% precision
      once the tokens are unseen, and what fraction of running text does the policy safely deliver
      versus abstain?

TRUTH CONVENTION
    A hit is EXACT STRING EQUALITY between the map's emitted vocalisation and the token as it
    appears in the held-out text. No normalisation is applied to the comparison — normalisation is
    used only to MATCH a surface, never to award a hit (matching must never rewrite the evidence).

Run:  .venv/Scripts/python.exe src/score_closed_class_bypass.py [--train-books 10] [--cap 300000]
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.chdir(Path(__file__).resolve().parent.parent)

from reconcile import ARABIC, strip_diacritics, qac_form_to_arabic
from measure_closed_class_ambiguity import (   # one source of truth for matching behaviour
    closed_class_surfaces, match_key, stream_eqtb, BOOKS)
from normalize_uthmani import fold               # the Uthmani transliteration layer
from paths import QAC_TXT, require

ART = Path("data/closed_class_bypass_heldout.json")
GOLD = Path("data/annotation/gold-tashkeela-300.jsonl")
IN_SAMPLE = Path("data/closed_class_ambiguity.json")
TIER1 = 0.95


def stream_books(surf: set, start: int, stop: int, cap: int, transform=None):
    """Yield (match_key, vocalized token) over books [start, stop).

    `transform` (the Uthmani fold) is applied before the surface filter, matching stream_eqtb.
    """
    scanned = 0
    with open(BOOKS, encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if i < start:
                continue
            if i >= stop:
                break
            text = (json.loads(line) or {}).get("text") or ""
            for tok in text.split():
                if not ARABIC.search(tok):
                    continue
                if transform is not None:
                    tok = transform(tok)
                scanned += 1
                k = match_key(tok)
                if k in surf:
                    yield k, tok
                if scanned >= cap:
                    return


def stream_qac(surf: set, cap: int, transform=None, surat=None):
    """Qur'anic gold from QAC 0.4 — the RIGHT reference for a vocalisation metric.

    QAC's layout is `LOCATION  FORM  TAG  FEATURES`, and **column 2 is the fully-vocalised
    Buckwalter FORM** (no `FORM:` label — an earlier grep for that string returned zero and
    nearly hid this). It decodes to standard-orthography vocalised Arabic via
    `reconcile.qac_form_to_arabic`, so unlike EQTB's uthmani_token it does NOT leave ~46% of
    its tokens bare. That is the whole reason this stream exists: EQTB answers "is the text
    written in Uthmani orthography?", QAC answers "what is the vocalisation?".

    `surat=(lo, hi)` restricts to surahs in range — used for the IN-REGISTER split, which is what
    separates "the mechanism is broken" from "the map does not transfer across registers".
    """
    n = 0
    with open(require(QAC_TXT), encoding="utf-8") as fh:
        for line in fh:
            if not line.startswith("("):
                continue
            if surat is not None:
                try:
                    s = int(line[1:].split(":", 1)[0])
                except ValueError:
                    continue
                if not (surat[0] <= s <= surat[1]):
                    continue
            c = line.rstrip("\n").split("\t")
            if len(c) < 3:
                continue
            ar = qac_form_to_arabic(c[1].strip())
            if not ar:
                continue                      # undecodable Buckwalter is dropped, never guessed
            if transform is not None:
                ar = transform(ar)
            if not ARABIC.search(ar):
                continue
            n += 1
            k = match_key(ar)
            if k in surf:
                yield k, ar
            if n >= cap:
                return


def build_map(pairs):
    """surface -> (majority vocalisation, confidence). This IS the shipping artifact."""
    variants = collections.defaultdict(collections.Counter)
    for k, tok in pairs:
        variants[k][tok] += 1
    return {k: (c.most_common(1)[0][0], max(c.values()) / sum(c.values()))
            for k, c in variants.items()}, variants


def score(name, pairs, amap, scanned, show=12):
    variants = collections.defaultdict(collections.Counter)
    total = 0
    for k, tok in pairs:
        variants[k][tok] += 1
        total += 1
    print(f"\n--- {name} ---")
    if not total or not scanned:
        print("  no matched tokens — nothing to score")
        return None

    hits = seen = 0
    t1 = {"n": 0, "hit": 0, "surfaces": set()}
    t2 = {"n": 0, "hit": 0, "surfaces": set()}
    missing = 0
    for k, c in variants.items():
        n = sum(c.values())
        seen += 1
        if k not in amap:
            missing += n
            continue
        pred, conf = amap[k]
        h = c.get(pred, 0)
        hits += h
        bucket = t1 if conf >= TIER1 else t2
        bucket["n"] += n
        bucket["hit"] += h
        bucket["surfaces"].add(k)

    print(f"  closed-class tokens in text     : {total:,} "
          f"({100*total/scanned:.1f}% of {scanned:,} tokens scanned)")
    print(f"  surfaces seen                   : {seen:,}  "
          f"(not in the TRAIN map: {missing:,} tokens)")
    print(f"  HELD-OUT micro precision        : {100*hits/total:.2f}%  ({hits:,}/{total:,})"
          f"   <- compare with the in-sample figure")

    # ---- CONVENTION SPLIT — the same treatment EQTB needed in §2x.5. A corpus that leaves
    # tokens UNVOCALISED (Uthmani orthography does, heavily) farms exact-match failures that
    # are ORTHOGRAPHY, not ambiguity. Split them out before the number is read as an accuracy,
    # and report precision over the vocalised tokens only: that is the cross-corpus figure.
    bare = sum(n for c in variants.values() for t, n in c.items() if strip_diacritics(t) == t)
    vtot = vhit = v1t = v1h = 0
    for k, c in variants.items():
        if k not in amap:
            continue
        pred, conf = amap[k]
        is1 = conf >= TIER1
        for t, n in c.items():
            if strip_diacritics(t) == t:
                continue                 # unvocalised token: a corpus convention, not an error
            vtot += n
            if is1:
                v1t += n
            if t == pred:
                vhit += n
                if is1:
                    v1h += n
    print(f"  unvocalised share of matched    : {100*bare/total:.1f}%  "
          f"(a corpus orthography — not ambiguity)")
    if vtot:
        print(f"  precision over VOCALISED only   : {100*vhit/vtot:.2f}%  ({vhit:,}/{vtot:,})"
              f"   <- comparable across corpora")
        if v1t:
            print(f"    Tier 1 over vocalised only    : {100*v1h/v1t:.2f}%  ({v1h:,}/{v1t:,})")
    for label, b in (("Tier 1 (conf >= 0.95)", t1), ("Tier 2 (conf <  0.95)", t2)):
        if b["n"]:
            print(f"    {label}: {len(b['surfaces']):>3} surfaces, {b['n']:>8,} tokens "
                  f"({100*b['n']/total:5.1f}% of matched), precision "
                  f"{100*b['hit']/b['n']:.2f}%")
    print(f"  POLICY (Tier 1 emits, Tier 2 abstains):")
    if t1["n"]:
        print(f"    delivered : {t1['n']:,} tokens = {100*t1['n']/scanned:.1f}% of RUNNING TEXT, "
              f"precision {100*t1['hit']/t1['n']:.2f}%")
    print(f"    abstained : {t2['n']:,} tokens = {100*t2['n']/scanned:.1f}% of running text "
          f"(falls back to bare surface / upstream head)")

    # where does the 99.5% gate actually sit? the gate is a THRESHOLD choice, so sweep it.
    print(f"  threshold sweep (delivered = tokens at or above the threshold):")
    sweep = []
    for thr in (0.999, 0.99, 0.98, 0.95, 0.90, 0.80, 0.0):
        n = h = s = 0
        for k, c in variants.items():
            if k not in amap:
                continue
            pred, conf = amap[k]
            if conf >= thr:
                n += sum(c.values())
                h += c.get(pred, 0)
                s += 1
        prec = h / n if n else 0.0
        sweep.append({"threshold": thr, "surfaces": s, "tokens": n,
                      "share_of_running_text": n / scanned, "precision": prec})
        print(f"    >= {thr:<6} {s:>3} surfaces  {n:>8,} tokens  "
              f"{100*n/scanned:5.1f}% of text  precision {100*prec:6.2f}%")
    # The gate is a THRESHOLD CHOICE, so answer the question a policy-maker asks: how low can
    # the threshold go before precision drops under 99.5%? (Lowest = most coverage delivered.)
    meet = [x for x in sweep if x["precision"] >= 0.995 and x["tokens"]]
    if meet:
        best = max(meet, key=lambda x: x["tokens"])
        print(f"    SMALLEST threshold still meeting 99.5%: >= {best['threshold']} "
              f"-> {100*best['share_of_running_text']:.1f}% of text at "
              f"{100*best['precision']:.2f}%")
    else:
        print("    no threshold in the sweep meets 99.5% on this corpus")

    worst = sorted(variants.items(), key=lambda kv: -(sum(kv[1].values()) - (
        kv[1].get(amap[kv[0]][0], 0) if kv[0] in amap else 0)))
    print(f"  worst held-out surfaces (surface, tokens, majority-in-TRAIN, HELD-OUT distribution):")
    for k, c in worst[:show]:
        if k not in amap:
            continue
        err = sum(c.values()) - c.get(amap[k][0], 0)
        if not err:
            break
        dist = " · ".join(f"{v}×{n}" for v, n in c.most_common(4))
        print(f"    {k:<10} {sum(c.values()):>7,} tok  TRAIN maj {amap[k][1]*100:5.1f}%  "
              f"held-out: {dist}")

    return {"name": name, "scanned": scanned, "matched": total, "surfaces_seen": seen,
            "not_in_train_map": missing, "precision": hits / total,
            "unvocalised_share": bare / total,
            "vocalised_only": {"tokens": vtot,
                               "precision": (vhit / vtot) if vtot else None,
                               "tier1_tokens": v1t,
                               "tier1_precision": (v1h / v1t) if v1t else None},
            "tier1": {"surfaces": len(t1["surfaces"]), "tokens": t1["n"],
                      "precision": t1["hit"] / t1["n"] if t1["n"] else None,
                      "share_of_running_text": t1["n"] / scanned},
            "tier2": {"surfaces": len(t2["surfaces"]), "tokens": t2["n"],
                      "precision": t2["hit"] / t2["n"] if t2["n"] else None,
                      "share_of_running_text": t2["n"] / scanned},
            "sweep": sweep,
            "worst_surfaces": {k: dict(c.most_common(6)) for k, c in worst[:show] if k in amap}}


def gold_overlap(surf) -> dict:
    """How much of the human gold sheet is closed-class at all? (It is content-word focused, so
    this is reported for completeness and is expected to be small — a 0 is a fact, not a bug.)"""
    if not GOLD.exists():
        return {"present": False}
    n = hit = 0
    forms = []
    with open(GOLD, encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            n += 1
            if match_key(r.get("form", "")) in surf:
                hit += 1
                forms.append(r["form"])
    return {"present": True, "rows": n, "closed_class_rows": hit, "forms": forms}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train-books", type=int, default=10,
                    help="Tashkeela books used to BUILD the map (0..N)")
    ap.add_argument("--eval-start", type=int, default=60)
    ap.add_argument("--eval-stop", type=int, default=97)
    ap.add_argument("--cap", type=int, default=300_000, help="scanned-token cap per slice")
    ap.add_argument("--fold-uthmani", action="store_true",
                    help="apply src/normalize_uthmani.fold to the MAP and to both corpora "
                         "(the both-sides contract), and report EQTB raw vs folded")
    ap.add_argument("--qac-gold", action="store_true",
                    help="also score QAC 0.4's VOCALISED FORM — the proper Qur'anic gold")
    ap.add_argument("--qac-split", action="store_true",
                    help="in-register QAC test: build the map from surahs 1-57 and score 58-114, "
                         "which separates a broken mechanism from a cross-register map")
    args = ap.parse_args()
    if not (args.train_books <= args.eval_start):
        sys.exit(f"refusing to run: train books 0..{args.train_books} overlap the eval slice "
                 f"{args.eval_start}..{args.eval_stop}")

    surf, prov = closed_class_surfaces()
    print("=" * 96)
    print("STAGE (ii) — the closed-class VOCALISED bypass, scored on HELD-OUT vocalised gold")
    print("=" * 96)
    print(f"surface set : {prov['surfaces']:,} closed-class surfaces from {prov['source']}")

    print(f"\nbuilding the map from Tashkeela books 0..{args.train_books} (cap {args.cap:,} tokens)…")
    amap, train_variants = build_map(stream_books(surf, 0, args.train_books, args.cap))
    t_tok = sum(sum(c.values()) for c in train_variants.values())
    print(f"  map: {len(amap):,} surfaces from {t_tok:,} matched TRAIN tokens")
    t1s = sum(1 for _, cf in amap.values() if cf >= TIER1)
    print(f"  Tier 1 (conf >= {TIER1}): {t1s:,} surfaces · Tier 2: {len(amap)-t1s:,} surfaces")
    in_sample_t1 = t1s

    if args.fold_uthmani:
        # BOTH SIDES. The map values are folded exactly like the corpora — folding one side only
        # would break canonically-equivalent strings (shadda/fatha ordering) and the metric would
        # fall for a reason unrelated to the language. See normalize_uthmani's CONTRACT note.
        amap_f = {k: (fold(v), c) for k, (v, c) in amap.items()}
        moved = sum(1 for k, (v, c) in amap.items() if fold(v) != v)
        print(f"\n--fold-uthmani: map folded too — {moved:,} of {len(amap):,} values changed "
              f"({100*moved/max(len(amap),1):.1f}%)")
        res = [score(f"HELD-OUT Tashkeela books {args.eval_start}..{args.eval_stop-1} — FOLDED "
                     f"both sides: REGRESSION GUARD (must match the unfolded run)",
                     stream_books(surf, args.eval_start, args.eval_stop, args.cap, transform=fold),
                     amap_f, args.cap),
               score("QAC 0.4 FORM (Qur'anic, FULLY VOCALISED — the right Qur'anic gold)",
                     stream_qac(surf, args.cap), amap, args.cap),
               score("EQTB uthmani RAW (control)",
                     stream_eqtb(surf, args.cap), amap, args.cap),
               score("EQTB uthmani FOLDED (normalize_uthmani layer, both sides)",
                     stream_eqtb(surf, args.cap, transform=fold), amap_f, args.cap)]
    else:
        res = [score(f"HELD-OUT Tashkeela books {args.eval_start}..{args.eval_stop-1} (in-domain)",
                     stream_books(surf, args.eval_start, args.eval_stop, args.cap),
                     amap, args.cap),
               score("EQTB uthmani (CROSS-corpus, different orthography)",
                     stream_eqtb(surf, args.cap), amap, args.cap)]
    if args.qac_gold:
        res.append(score("QAC 0.4 FORM (Qur'anic, FULLY VOCALISED — the right Qur'anic gold)",
                         stream_qac(surf, args.cap), amap, args.cap))
    if args.qac_split:
        # IN-REGISTER. Same corpus, disjoint surahs. If Tier 1 springs back to ~99%, the mechanism
        # is sound and the cross-register collapse is a MAP problem (train one map per register),
        # not an architecture problem. If it does not, the mechanism itself is at fault.
        amap_q, _ = build_map(stream_qac(surf, args.cap, surat=(1, 57)))
        moved_q = sum(1 for k, (v, c) in amap.items() if k in amap_q and amap_q[k][0] != v)
        print(f"\n--qac-split: in-register map = {len(amap_q):,} surfaces from surahs 1-57; "
              f"{moved_q:,} of them differ from the Tashkeela-register map's choice")
        res.append(score("QAC FORM — IN-REGISTER (map surahs 1-57, eval surahs 58-114)",
                         stream_qac(surf, args.cap, surat=(58, 114)), amap_q, args.cap))
    res = [r for r in res if r]

    print("\n" + "=" * 96)
    print("VERDICT — does Tier 1 hold its >= 99.5% precision OUT OF SAMPLE?")
    print("=" * 96)
    for r in res:
        p = r["tier1"]["precision"]
        if p is None:
            continue
        ok = "HOLDS" if p >= 0.995 else "DOES NOT HOLD"
        print(f"  {r['name'][:46]:<48} Tier 1 {100*p:6.2f}%  -> {ok} "
              f"(delivers {100*r['tier1']['share_of_running_text']:.1f}% of text)")
    if IN_SAMPLE.exists():
        d = json.loads(IN_SAMPLE.read_text(encoding="utf-8"))
        r0 = next((x for x in d["results"] if "Tashkeela" in x["name"]), None)
        if r0:
            print(f"\n  recorded IN-SAMPLE Tashkeela micro was {100*r0['micro_accuracy']:.2f}%; the"
                  f" held-out figure above is the honest one.")
    g = gold_overlap(surf)
    print(f"\n  human gold sheet: {g.get('rows')} rows, {g.get('closed_class_rows')} closed-class"
          f" — it is content-word focused by design, so it cannot validate the bypass."
          if g.get("present") else "\n  human gold sheet: absent")

    ART.write_text(json.dumps({
        "map_train": {"books": [0, args.train_books], "surfaces": len(amap),
                      "matched_tokens": t_tok, "tier1_surfaces": in_sample_t1,
                      "tier1_threshold": TIER1},
        "eval": res, "human_gold": g, "token_cap": args.cap,
        "note": "map built from books 0..N; eval slice is DISJOINT. Held-out precision is the "
                "number to sign the policy off with, not the in-sample figure.",
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nartifact -> {ART}")


if __name__ == "__main__":
    main()
