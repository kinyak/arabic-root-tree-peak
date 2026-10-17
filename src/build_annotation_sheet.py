"""build_annotation_sheet.py — the BLIND pilot annotation sheet (SPEC-REV6 §5.3).

WHY BLIND, AND WHY IT CANNOT BE RETROFITTED
    The treatment trains on CALIMA-derived silver. If the labels that score it were also
    produced while looking at CALIMA, the evaluation is a closed loop: the model is
    scored on agreement with the very system it was trained to imitate. Anchoring is
    permanent — once an annotator has seen the analyser's answer, that label is
    contaminated and cannot be un-seen. So the protocol is frozen BEFORE annotation.

    This sheet therefore contains NO CALIMA output, NO root, NO pattern and NO case.
    It contains only the token and its context.

THE SOURCE, AND WHY
    Tokens are sampled from **EQTB** — an independent human treebank, not CALIMA
    (satisfies §5.3 item 1). EQTB also carries its OWN gold `root_ar` and `nominal_case`,
    which are WITHHELD from the sheet and kept in a private key: that gives a free
    validity check on the annotator's labels without ever showing them an answer.

    A deliberate fraction of rows have NO EQTB root/case gold, so the "genuinely
    ambiguous -> ABSTAIN" rule is exercised rather than assumed.

HONEST CAVEAT ABOUT THIS PILOT
    The text is Quranic, and many annotators know it well. That makes this pilot easier
    than the real target (Tashkeela prose, where no gold exists at all). That is
    acceptable for a PILOT whose only job is to prove the instructions are unambiguous —
    but the full sheet must sample Tashkeela.

WHAT IS FROZEN
    The sheet is written with a sha256 recorded in the protocol doc. Re-generating it
    with a different seed produces a different hash, which is how a reader can tell that
    the sheet was fixed before annotation began.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import sys
from pathlib import Path

from paths import EQTB_CSV, ROOT, require

ARABIC = re.compile(r"[\u0621-\u063a\u0641-\u064a]")
TATWEEL = "\u0640"
CASE_VOWEL = {0: "\u064f", 1: "\u064e", 2: "\u0650"}
CASE_NAME = {0: "NOM", 1: "ACC", 2: "GEN"}
EQTB_CASE = {"NOM": 0, "ACC": 1, "GEN": 2}

OUT_DIR = ROOT / "data" / "annotation"
PRIVATE_DIR = OUT_DIR / "private"


def fold_orth(s: str) -> str:
    """Uthmani -> standard (imlaa'i) orthography, so the annotator sees the same
    convention the analysis pipeline uses. Alef-wasla and the superscript alef are
    presentation differences, not annotation decisions."""
    if not s:
        return s
    out = s.replace("\u0671", "\u0627").replace("\u0670", "").replace(TATWEEL, "")
    return "".join(c for c in out if not ("\u06d6" <= c <= "\u06ed"))


def load_rows(path, limit=None):
    """One WORD per EQTB word, with its verse context assembled.

    EQTB segments clitics as SEPARATE tokens (`عِبَادِ` + `هِ`), so joining tokens with
    spaces produced context like `عِبَادِ هِ` — unusable for a human annotator and a good
    way to collect garbage labels. Segments are therefore joined by `word_id` into
    orthographic words, which is the unit an annotator actually reasons about.
    """
    import collections
    by_verse = collections.defaultdict(lambda: collections.defaultdict(list))
    n = 0
    with open(path, encoding="utf-16", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            surf = (row.get("uthmani_token") or "").strip()
            if not surf or not ARABIC.search(surf):
                continue
            by_verse[(row.get("chapter_id"), row.get("verse_id"))][
                row.get("word_id")].append(row)
            n += 1
            if limit and n >= limit:
                break
    out = []
    for key, words in by_verse.items():
        ordered = sorted(words.items(), key=lambda kv: int(kv[0] or 0))
        toks = []
        for _, segs in ordered:
            segs.sort(key=lambda r: int(r.get("tok_id") or 0))
            surface = fold_orth("".join((s.get("uthmani_token") or "").strip()
                                        for s in segs))
            if not ARABIC.search(surface):
                continue
            # the STEM segment carries the root/case in EQTB
            stem = None
            for s in segs:
                if (s.get("segment") or "").upper().startswith("STEM"):
                    stem = s
                    break
            stem = stem or segs[0]
            root = (stem.get("root_ar") or "").strip()
            if root in ("", TATWEEL, "_", "-"):
                root = None
            case_raw = (stem.get("nominal_case") or "").strip().upper()
            toks.append({"surface": surface, "gold_root": root,
                         "gold_case": EQTB_CASE.get(case_raw)})
        if len(toks) >= 4:
            out.append((key, toks))
    return out


def load_tashkeela(books=8, per_book_chars=40000, seed=0):
    """Fetch a few Tashkeela books via the HF rows API and split into sentences.

    Tashkeela is the corpus where **no gold exists at all**, so annotation here CREATES
    the gold rather than checking against one — which also means the full sheet has no
    withheld-gold validity check. That is expected; the pilot supplied the validity check.

    Deliberate STRATIFICATION, documented rather than hidden: the sheet oversamples words
    whose SURFACE contains a weak letter (و/ي) or a shadda, because those are the classes
    where CALIMA silver collapses and where new human gold is most valuable. Sampling
    only from surface features means no analyser is consulted, so the blindness holds.
    """
    import time
    import requests
    url = "https://datasets-server.huggingface.co/rows"
    print(f"  fetching {books} Tashkeela book(s) via the rows API")
    texts = []
    for off in range(books):
        for attempt in range(4):
            try:
                r = requests.get(url, timeout=180, params={
                    "dataset": "community-datasets/tashkeela", "config": "plain_text",
                    "split": "train", "offset": off, "length": 1})
                if r.status_code == 429:
                    time.sleep(5 * (attempt + 1))
                    continue
                r.raise_for_status()
                t = (r.json()["rows"][0]["row"].get("text") or "")[:per_book_chars]
                if t:
                    texts.append(t)
                break
            except Exception as ex:
                if attempt == 3:
                    print(f"    FAIL offset {off}: {type(ex).__name__}")
                else:
                    time.sleep(3 * (attempt + 1))
        print(f"    book {off+1}/{books}", flush=True)

    sents = []
    for t in texts:
        for chunk in re.split(r"[\n\.\?!\u061f\u06d4]+", t):
            words = chunk.split()
            if len(words) >= 8:
                sents.append(words)
    return sents


PUNCT = "،؛؟٬٭۔,;:!?.\"'()[]{}*_—–-\u00ab\u00bb\u2018\u2019\u201c\u201d"


def strip_punct(w: str) -> str:
    """Tashkeela attaches punctuation to words without a space (`مَالِكٍ،`), so a target
    taken verbatim carries a comma the annotator would have to ignore — and which would
    silently poison the wazān pattern. Strip it at build time."""
    return w.strip(PUNCT)


def candidates_from_sentences(sents, rng):
    """(with_weak_or_geminate, plain) candidate pools — surface cues only, no analyser."""
    weak = re.compile(r"[\u0648\u064a]")
    shadda = "\u0651"
    strong, strati = [], []
    for s in sents:
        clean = [strip_punct(w) for w in s]
        for i, w in enumerate(clean):
            letters = [c for c in w if "\u0621" <= c <= "\u064a"]
            if len(letters) < 4 or not ARABIC.search(w):
                continue
            if not any("\u064b" <= c <= "\u0652" for c in w):
                continue                      # must be vocalized to judge the wazān
            bare = "".join(c for c in w if not ("\u064b" <= c <= "\u0652"))
            lo, hi = max(0, i - 5), min(len(clean), i + 6)
            ctx = list(clean[lo:hi])
            rec = {"token": w, "i": i - lo, "context": ctx,
                   "gold_root": None, "gold_case": None}
            (strati if (weak.search(bare) or shadda in w) else strong).append(rec)
    return strong, strati


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50, help="tokens in the sheet")
    ap.add_argument("--no-gold", type=int, default=10,
                    help="how many rows deliberately have NO withheld gold")
    ap.add_argument("--seed", type=int, default=20261009)
    ap.add_argument("--prefix", default="pilot",
                    help="filename prefix; use another for the full sheet")
    ap.add_argument("--limit", type=int, default=60000)
    ap.add_argument("--source", default="eqtb", choices=("eqtb", "tashkeela"))
    ap.add_argument("--strati-frac", type=float, default=0.4,
                    help="fraction drawn from weak/doubled-surface words (tashkeela)")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    picked, n_gold = [], 0

    if args.source == "tashkeela":
        sents = load_tashkeela(seed=args.seed)
        print(f"  sentences        : {len(sents):,}")
        strong, strati = candidates_from_sentences(sents, rng)
        print(f"  candidates       : {len(strong):,} plain, {len(strati):,} weak/shadda")
        n_strati = min(int(args.n * args.strati_frac), len(strati))
        picked = rng.sample(strati, n_strati) + rng.sample(
            strong, min(args.n - n_strati, len(strong)))
        rng.shuffle(picked)
        n_gold = 0                            # Tashkeela has NO gold by definition
    else:
        verses = load_rows(require(EQTB_CSV), args.limit)
        print(f"verses assembled : {len(verses):,}")
        with_gold, without_gold = [], []
        for key, toks in verses:
            for i, t in enumerate(toks):
                if len(t["surface"]) < 3 or not ARABIC.search(t["surface"]):
                    continue
                lo, hi = max(0, i - 4), min(len(toks), i + 5)
                rec = {"key": key, "i": i, "token": t["surface"],
                       "context": [x["surface"] for x in toks[lo:hi]],
                       "gold_root": t["gold_root"], "gold_case": t["gold_case"]}
                (with_gold if (t["gold_root"] and t["gold_case"] is not None)
                 else without_gold).append(rec)
        print(f"candidates       : {len(with_gold):,} with root+case gold, "
              f"{len(without_gold):,} without")
        n_no = min(args.no_gold, args.n - 5)
        picked = rng.sample(with_gold, min(args.n - n_no, len(with_gold)))
        if n_no > 0 and without_gold:
            picked += rng.sample(without_gold, min(n_no, len(without_gold)))
        rng.shuffle(picked)
        n_gold = sum(1 for r in picked if r["gold_root"] and r["gold_case"] is not None)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PRIVATE_DIR.mkdir(parents=True, exist_ok=True)
    sheet = OUT_DIR / f"{args.prefix}-annotation-sheet.csv"
    keyf = PRIVATE_DIR / f"{args.prefix}-annotation-KEY.csv"

    with open(sheet, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "sentence_with_target_in_double_brackets", "target_token",
                    "root", "wazn_pattern", "case", "confidence", "notes"])
        for n, rec in enumerate(picked, 1):
            ctx = list(rec["context"])
            idx = rec.get("i", 0)
            if 0 <= idx < len(ctx):
                ctx[idx] = f"[[{rec['token']}]]"
            w.writerow([f"B{n:03d}", " ".join(ctx), rec["token"], "", "", "", "", ""])

    with open(keyf, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "target_token", "EQTB_root_arabic", "EQTB_case", "has_gold"])
        for n, rec in enumerate(picked, 1):
            gc = rec.get("gold_case")
            w.writerow([f"B{n:03d}", rec["token"], rec.get("gold_root") or "",
                        CASE_NAME.get(gc, "") if gc is not None else "",
                        "yes" if (rec.get("gold_root") and gc is not None) else "no"])

    h = hashlib.sha256(sheet.read_bytes()).hexdigest()
    meta = {"sheet": sheet.name, "rows": len(picked), "seed": args.seed,
            "source": args.source, "rows_with_withheld_gold": n_gold,
            "rows_without_gold": len(picked) - n_gold, "sha256": h,
            "strati_frac": args.strati_frac if args.source == "tashkeela" else None}
    (OUT_DIR / f"{args.prefix}-annotation-meta.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8")

    print(f"\nsheet  -> {sheet}")
    print(f"key    -> {keyf}   (answer key; empty for Tashkeela — no gold exists)")
    print(f"rows   : {len(picked)}  (withheld gold: {n_gold})")
    print(f"sha256 : {h}")
    print("\nFREEZE THIS HASH in docs/ANNOTATION-PROTOCOL.md before annotating.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
