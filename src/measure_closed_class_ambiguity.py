"""Measure the closed-class bypass's unigram majority-vote accuracy.

THE QUESTION (docs/CLOSED-CLASS-INVENTORY.md §4.5)
    The bypass is a bare-surface -> vocalized-form lookup. One bare surface can map to
    several vocalized forms (وَ/وِ, لِ/لَ, مِنْ/مَنْ). Before choosing a selection policy,
    measure how often the most frequent vocalization actually wins.

METHOD
    · The surface set comes from PADT TRAIN only, restricted to the FUNCTION-WORD tags
      (ADP/CCONJ/PRON/DET/SCONJ/PART) — the scope the spec gives the component. PUNCT/SYM
      are identity and X is not closed-class, so neither belongs here (§4.3).
    · The vocalized evidence comes from a fully vocalized corpus, streamed. Register
      matters and is reported separately, because مِنْ vs مَنْ is a register question:
        primary   Tashkeela books  (classical/expository, on disk)
        secondary EQTB uthmani     (Quranic) — best-effort, skipped loudly if absent
    · micro-accuracy = sum(count of each surface's majority variant) / sum(all matches).
      macro-accuracy = mean over surfaces of each surface's own majority share.

NOT A PADT MEASUREMENT
    PADT's FORM is 98.7% undiacritized (§2x.4), so PADT can say nothing about
    vocalization. This must come from a vocalized corpus or it is meaningless.

Run:  .venv/Scripts/python.exe src/measure_closed_class_ambiguity.py [--books 25] [--cap 1500000]
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.chdir(Path(__file__).resolve().parent.parent)

from reconcile import ARABIC, strip_diacritics
from paths import OUT, EQTB_CSV, require

FUNCTION_TAGS = {"ADP", "CCONJ", "PRON", "DET", "SCONJ", "PART"}
BOOKS = Path("data/raw/tashkeela-books.jsonl")
ART = Path("data/closed_class_ambiguity.json")

# for MATCHING only: Tashkeela and PADT differ in alef/ya spelling. The recorded variant
# stays the original vocalized token — normalisation must never rewrite the evidence.
MATCH_NORM = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ؤ": "و",
                            "ئ": "ي", "ة": "ه"})


def match_key(s: str) -> str:
    return strip_diacritics(s or "").translate(MATCH_NORM)


def closed_class_surfaces() -> tuple[set, dict]:
    """(surface set, provenance) from PADT TRAIN, function-word tags only."""
    tags = {i: t for t, i in json.loads((OUT / "vocab.json").read_text(encoding="utf-8"))["upos"].items()}
    surf, per_tag = set(), collections.Counter()
    with open(OUT / "padt-train.jsonl", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            tag = tags.get(r.get("upos"))
            if tag in FUNCTION_TAGS:
                k = match_key(r["form_bare"])
                if k:
                    surf.add(k)
                    per_tag[tag] += 1
    return surf, {"source": "PADT train (function-word tags only)", "surfaces": len(surf),
                  "train_tokens_by_tag": dict(per_tag)}


def stream_tashkeela(surf: set, n_books: int, cap: int):
    """Yield match_key -> original vocalized token, over the first n_books books."""
    seen = 0
    with open(BOOKS, encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if i >= n_books:
                break
            text = (json.loads(line) or {}).get("text") or ""
            for tok in text.split():
                if not ARABIC.search(tok):
                    continue
                seen += 1
                k = match_key(tok)
                if k in surf:
                    yield k, tok
                if seen >= cap:
                    return


def stream_eqtb(surf: set, cap: int, transform=None):
    """Best-effort: EQTB's vocalized uthmani token column, if the CSV is present.

    `transform` is applied to the RAW token BEFORE the surface filter, because the filter key must
    be computed from the transformed form — folding Uthmani ٱلْ to الْ only makes it match the
    surface الْ if the fold happens first. Default None keeps the original behaviour exactly.
    """
    try:
        path = require(EQTB_CSV)
    except SystemExit:
        print("  EQTB skipped: corpus not present on this host")
        return
    try:
        with open(path, encoding="utf-16", newline="") as fh:
            rd = csv.DictReader(fh, delimiter="\t")
            col = next((c for c in (rd.fieldnames or []) if c and "uthmani" in c.lower()
                        and "token" in c.lower()), None)
            if col is None:
                print(f"  EQTB skipped: no vocalized token column in {rd.fieldnames[:8]}…")
                return
            print(f"  EQTB column: {col}")
            n = 0
            for row in rd:
                tok = (row.get(col) or "").strip()
                if transform is not None:
                    tok = transform(tok)
                if not tok or not ARABIC.search(tok):
                    continue
                n += 1
                k = match_key(tok)
                if k in surf:
                    yield k, tok
                if n >= cap:
                    return
    except Exception as ex:                                   # pragma: no cover
        print(f"  EQTB skipped: {type(ex).__name__}: {ex}")


def score(name: str, pairs, surf: set, show: int = 14):
    variants = collections.defaultdict(collections.Counter)
    total = 0
    for k, tok in pairs:
        variants[k][tok] += 1
        total += 1
    if not total:
        print(f"\n--- {name}: no matches ---")
        return None
    hdr = sum(max(c.values()) for c in variants.values())
    macro = sum(max(c.values()) / sum(c.values()) for c in variants.values()) / len(variants)
    ambiguous = {k: c for k, c in variants.items() if len(c) > 1}
    print(f"\n--- {name} ---")
    print(f"  matched tokens            : {total:,}   (surface set {len(surf):,})")
    print(f"  surfaces actually seen    : {len(variants):,}")
    print(f"  surfaces with >1 variant  : {len(ambiguous):,} "
          f"({100*len(ambiguous)/max(len(variants),1):.1f}% of surfaces seen)")
    print(f"  MICRO majority accuracy   : {100*hdr/total:.2f}%   "
          f"({hdr:,}/{total:,} tokens)")
    print(f"  MACRO majority accuracy   : {100*macro:.2f}%   (mean over surfaces)")

    # ---- CONVENTION SPLIT. A corpus that leaves many particles unvocalised (Uthmani
    # orthography does) splits every surface between "vocalised" and "bare" variants, and
    # the bare one can win. That is orthography, not ambiguity, and it must be separated
    # before the number is read as an accuracy.
    bare = sum(n for c in variants.values() for t, n in c.items() if strip_diacritics(t) == t)
    voc = total - bare
    if bare:
        print(f"\n  CONVENTION SPLIT — tokens left unvocalised by this corpus: {bare:,} "
              f"({100*bare/total:.1f}%)")
        if voc:
            vh = 0
            for c in variants.values():
                vc = collections.Counter({t: n for t, n in c.items()
                                          if strip_diacritics(t) != t})
                if vc:
                    vh += max(vc.values())
            print(f"  MICRO over the VOCALISED tokens only : {100*vh/voc:.2f}%  "
                  f"({vh:,}/{voc:,})  <- comparable to the Tashkeela figure")
        print("  (the bare share is an ORTHOGRAPHIC convention of the corpus; a bypass that")
        print("   emits bare forms would score that share trivially — decided by policy, not")
        print("   by accuracy)")

    print(f"\n  most ambiguous surfaces (variant: count):")
    ranked = sorted(ambiguous.items(), key=lambda kv: -sum(kv[1].values()))
    for k, c in ranked[:show]:
        dist = " · ".join(f"{v}×{n}" for v, n in c.most_common(5))
        share = 100 * c.most_common(1)[0][1] / sum(c.values())
        print(f"    {k:<10} {sum(c.values()):>7,} tokens, {len(c)} variants, "
              f"majority {share:5.1f}%   {dist}")

    # ---- ERROR ATTRIBUTION. Which surfaces actually cost the accuracy? A 91% aggregate
    # hides whether the loss is spread thin (unfixable) or concentrated (conditionable).
    errors = {k: sum(c.values()) - max(c.values()) for k, c in variants.items()}
    tot_err = sum(errors.values())
    print(f"\n  ERROR ATTRIBUTION — {tot_err:,} wrong tokens; where do they come from?")
    ranked_err = sorted(errors.items(), key=lambda kv: -kv[1])
    cum = 0
    for k, e in ranked_err[:10]:
        if not e:
            break
        cum += e
        print(f"    {k:<10} {e:>7,} errors ({100*e/max(tot_err,1):4.1f}% of all)  "
              f"volume {sum(variants[k].values()):>7,}  majority "
              f"{100*max(variants[k].values())/sum(variants[k].values()):5.1f}%")
    print(f"    top-10 surfaces carry {100*cum/max(tot_err,1):.1f}% of ALL errors")
    # what would the accuracy be if the tail were conditioned instead of guessed?
    for thr in (0.99, 0.95, 0.90):
        safe = {k: c for k, c in variants.items()
                if max(c.values()) / sum(c.values()) >= thr}
        s_tok = sum(sum(c.values()) for c in safe.values())
        s_hit = sum(max(c.values()) for c in safe.values())
        print(f"    surfaces with majority >= {thr:.2f}: {len(safe):>3} surfaces, "
              f"{100*s_tok/total:5.1f}% of volume, accuracy {100*s_hit/max(s_tok,1):.2f}%")
    return {"name": name, "matched": total, "surfaces_seen": len(variants),
            "ambiguous_surfaces": len(ambiguous), "micro_accuracy": hdr / total,
            "macro_accuracy": macro, "unvocalised_share": (bare / total) if total else 0.0,
            "errors_total": tot_err,
            "errors_by_surface": dict(sorted(errors.items(), key=lambda kv: -kv[1])),
            "variants": {k: dict(c.most_common()) for k, c in variants.items()}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--books", type=int, default=25, help="Tashkeela books to stream")
    ap.add_argument("--cap", type=int, default=1_500_000, help="token cap per corpus")
    args = ap.parse_args()

    surf, prov = closed_class_surfaces()
    print("=" * 96)
    print("CLOSED-CLASS AMBIGUITY — how often does the most frequent vocalisation win?")
    print("=" * 96)
    print(f"surface set: {prov['surfaces']:,} closed-class surfaces from {prov['source']}")
    print(f"  train tokens by tag: {prov['train_tokens_by_tag']}")

    print(f"\nstreaming Tashkeela (first {args.books} books, cap {args.cap:,} tokens)…")
    res_t = score("Tashkeela books (classical/expository, vocalised)",
                  stream_tashkeela(surf, args.books, args.cap), surf)

    print(f"\nstreaming EQTB (cap {args.cap:,} tokens)…")
    res_e = score("EQTB uthmani (Quranic)", stream_eqtb(surf, args.cap), surf)

    print("\n" + "=" * 96)
    print("POLICY GATE (the spec's threshold is 95%)")
    print("=" * 96)
    for res in (res_t, res_e):
        if not res:
            continue
        acc = res["micro_accuracy"]
        verdict = ("STATIC MAP OK" if acc >= 0.95 else
                   "STATIC MAP INSUFFICIENT — condition on the tail, or accept the error")
        print(f"  {res['name']:<52} {100*acc:5.2f}%  -> {verdict}")

    ART.write_text(json.dumps({"surface_set": prov, "books_streamed": args.books,
                               "token_cap": args.cap,
                               "results": [r for r in (res_t, res_e) if r]},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nartifact -> {ART}")


if __name__ == "__main__":
    main()
