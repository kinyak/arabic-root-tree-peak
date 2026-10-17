"""Tashkeela X proxy — replace the speculative "<2% X" with a measured number.

WHY
    `docs/CLOSED-CLASS-INVENTORY.md` §4.6 states that the `X` share "in Tashkeela /
    Durus al-Lughah" is *expected* to be under 2%. That was never measured, and it is a
    load-bearing claim: it is what justifies saying the 11.1% X figure is a property of
    PADT news rather than of Arabic. This probe replaces it.

WHAT IS MEASURED, AND WHAT IT IS NOT
    Tashkeela has no POS tags, so PADT's `X` label cannot be counted there directly.
    What CAN be counted is the share of tokens CAMeL cannot give a TEMPLATIC analysis to:
    no analysis at all, `NTWS` (non-templatic word structure), or `backoff`. That is a
    PROXY for X-like material (foreign names, transliterations, unknown strings) and it is
    an UPPER-ish bound — it also catches dialectal/odd forms and CAMeL gaps that are not
    foreign. It is never to be quoted as "X share".

    The PADT `X` share is printed on the SAME basis (share of ALL tokens) so the two are
    comparable; the 11.1% figure that appears in the spec is X as a share of the
    *closed-class floor*, which is a different denominator and is labelled as such.

Run:  .venv/Scripts/python.exe src/measure_tashkeela_x_proxy.py [--tokens 30000]
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

from reconcile import ARABIC
from paths import OUT

BOOKS = Path("data/raw/tashkeela-books.jsonl")
ART = Path("data/tashkeela_x_proxy.json")


def first_calima_analysis(a):
    """The pattern CAMeL offers, or a marker saying it offered nothing."""
    if not a:
        return None
    return a.get("pattern")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tokens", type=int, default=30_000)
    ap.add_argument("--books", type=int, default=10)
    args = ap.parse_args()

    # ---- deterministic slice: the first N Arabic tokens of the first M books
    toks = []
    with open(BOOKS, encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if i >= args.books or len(toks) >= args.tokens:
                break
            text = (json.loads(line) or {}).get("text") or ""
            for t in text.split():
                if ARABIC.search(t):
                    toks.append(t)
                    if len(toks) >= args.tokens:
                        break

    print("=" * 96)
    print(f"TASHKEELA X PROXY — {len(toks):,} Arabic tokens from {args.books} books")
    print("=" * 96)

    from camel_tools.disambig.mle import MLEDisambiguator
    mle = MLEDisambiguator.pretrained("calima-msa-r13")
    B = 500
    ana = []
    for i in range(0, len(toks), B):
        for d in mle.disambiguate(toks[i:i + B]):
            ana.append(d.analyses[0].analysis if (d and d.analyses) else None)

    cls = collections.Counter()
    usable_root = 0
    for a in ana:
        if not a:
            cls["no_analysis"] += 1
            continue
        pat = a.get("pattern")
        root = a.get("root") or ""
        if root and "#" not in root and root != "NTWS":
            usable_root += 1
        if not pat:
            cls["no_pattern"] += 1
        elif "NTWS" in pat:
            cls["ntws_pattern"] += 1
        elif "backoff" in pat:
            cls["backoff_pattern"] += 1
        else:
            cls["templatic"] += 1

    n = len(ana)
    print(f"\n  {'class':<20}{'tokens':>9}{'share':>9}")
    for k, v in cls.most_common():
        print(f"  {k:<20}{v:>9,}{100*v/n:>8.1f}%")
    untemplatic = n - cls["templatic"]
    print(f"\n  UNTEMPLATIC (no analysis / NTWS / backoff / no pattern) = "
          f"{untemplatic:,} = {100*untemplatic/n:.2f}% of tokens")
    print(f"  CALIMA gives a usable root for {usable_root:,} = {100*usable_root/n:.1f}%")

    # ---- PADT's X on the SAME basis
    tags = {i: t for t, i in json.loads((OUT / "vocab.json").read_text(encoding="utf-8"))["upos"].items()}
    padt = {}
    for split in ("train", "test"):
        tot = 0
        x = 0
        with open(OUT / f"padt-{split}.jsonl", encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                tot += 1
                if tags.get(r.get("upos")) == "X":
                    x += 1
        padt[split] = {"tokens": tot, "x": x, "share": x / tot}
        print(f"\n  PADT {split:<5} X = {x:,}/{tot:,} = {100*x/tot:.2f}% OF ALL TOKENS "
              f"(the 11.1% in the spec is X / closed-class floor, a different denominator)")

    print("\n" + "=" * 96)
    print("READING")
    print("=" * 96)
    print(f"  Tashkeela untemplatic proxy : {100*untemplatic/n:.2f}% of tokens")
    print(f"  PADT X (same basis)         : {100*padt['train']['share']:.2f}% train · "
          f"{100*padt['test']['share']:.2f}% test")
    ratio = (padt["train"]["share"] / (untemplatic / n)) if untemplatic else float("nan")
    print(f"  ratio PADT:classical        : {ratio:.1f}x")
    print("  REMINDER: the Tashkeela figure is an UNTEMPLATIC proxy (an upper-ish bound),")
    print("  not the X tag. The direction of the claim is what matters — that the 11.1% is")
    print("  a property of news-wire text, not of Arabic.")

    ART.write_text(json.dumps({
        "what": "Tashkeela untemplatic-analysis proxy for the X share",
        "caveat": "NOT the X tag; CAMeL untemplatic analysis. Upper-ish bound.",
        "tokens": n, "books": args.books, "classes": dict(cls),
        "untemplatic": untemplatic, "untemplatic_share": untemplatic / n,
        "usable_root_share": usable_root / n, "padt_x_same_basis": padt,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n  artifact -> {ART}")


if __name__ == "__main__":
    main()
