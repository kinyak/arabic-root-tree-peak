"""Transliteration / folding layer: Uthmani (Qur'anic) orthography -> standard orthography.

WHY THIS EXISTS (docs/CLOSED-CLASS-INVENTORY.md §4.9)
    Held-out scoring showed the closed-class bypass is ORTHOGRAPHY-LOCKED: on EQTB uthmani the
    raw precision was 18.67%, 45.7% of matched tokens were left bare, and 12.4% of tokens were
    not in the surface map at all. The cause is not grammar and not ambiguity — it is that
    Uthmani orthography writes alef wasla (ٱ), dagger alef (ٰ), small high tajwid letters and
    end-of-ayah signs that an exact-string map trained on standard orthography cannot see.
    `reconcile.strip_diacritics` does NOT touch any of them (its class is [\\u064b-\\u0652\\u0670\\u0640]),
    so 'ٱلْحَمْدُ' strips to 'ٱلحمد' — with the wasla still in it.

WHAT THIS IS, AND WHAT IT IS NOT
    This is an INPUT transliteration layer, exactly like NFC: it is applied to the raw corpus
    BEFORE any lookup, so the metric that follows is still exact string equality against the
    folded text. It is NOT a scoring fudge — nothing is normalised at comparison time.

    CONTRACT — the layer is applied to BOTH SIDES. Because it includes NFC, the surface MAP must be
    folded the same way as the corpus (i.e. build the map from folded text). Folding only one side
    desynchronises canonically-equivalent strings — Tashkeela writes shadda+fatha where NFC orders
    fatha+shadda — and the metric would fall for a reason that has nothing to do with the language.
    `score_closed_class_bypass.py --fold-uthmani` folds the map and both corpora, and the in-domain
    Tashkeela score is reported as the regression guard that proves the two-sided form is neutral.

    Two rules it obeys deliberately:
      · HARAKAT ARE KEPT. Short vowels, tanwin, shadda and sukun are the vocalisation the bypass
        is being tested on. Removing them would make the metric meaningless.
      · TAJWID/ANNOTATION MARKS ARE REMOVED. Small high letters, pause/sajdah signs, end-of-ayah
        signs and the extended Arabic mark block carry recitation instructions, not phonemes.
      · DAGGER ALEF AND WASLA FOLD TO LETTERS, not to nothing: U+0670 (superscript alef) and
        U+0671 (alef wasla) both denote a long /aː/, so they fold to ا. Deleting them would
        shorten the word and manufacture matches.

Run:
    .venv/Scripts/python.exe src/normalize_uthmani.py --selftest
    .venv/Scripts/python.exe src/normalize_uthmani.py --check eqtb
    .venv/Scripts/python.exe src/normalize_uthmani.py --check tashkeela
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.chdir(Path(__file__).resolve().parent.parent)

from reconcile import ARABIC
from paths import EQTB_CSV, require

BOOKS = Path("data/raw/tashkeela-books.jsonl")

# --------------------------------------------------------------------- tajwid / annotation
# Codepoint ranges carrying recitation or annotation information rather than phonemes.
# Documented by range and name so a later reader can audit the choice.
TAJWID_RANGES = (
    (0x0610, 0x061A, "Arabic signs (honorifics, sanah, rahma...)"),
    (0x0640, 0x0640, "tatweel / kashida — a stretching glyph, no phoneme"),
    (0x0656, 0x065F, "Arabic subscript/annotation marks (subscript alef, inverted damma...)"),
    (0x06D6, 0x06DC, "Quranic annotation signs (small high letters, sajdah)"),
    (0x06DD, 0x06DD, "Arabic end-of-ayah sign"),
    (0x06DE, 0x06E4, "Quranic signs incl. small high meem/jeem/dotless head of khah (tajwid)"),
    (0x06E7, 0x06E8, "small high yeh / noon (tajwid)"),
    (0x06EA, 0x06ED, "empty centre / small high/low marks (tajwid)"),
    (0x08D3, 0x08E1, "Arabic extended-A marks (quranic open tanwin, small high signs...)"),
    (0x08E3, 0x08FF, "Arabic extended-A marks (tajwid, small high letters)"),
    (0x200C, 0x200F, "ZWNJ / ZWJ / direction marks"),
    (0xFE00, 0xFE0F, "variation selectors"),
)
_TAJWID = frozenset(
    cp for lo, hi, _ in TAJWID_RANGES for cp in range(lo, hi + 1)
)

# --------------------------------------------------------------------- letter folding
# Uthmani letter variants -> the letter standard orthography (and the surface map) uses.
# These are LETTER substitutions, so the length of the word is preserved.
FOLD_MAP = {
    0x0671: 0x0627,   # alef wasla            -> alef         (ٱ -> ا)
    0x0670: 0x0627,   # superscript/dagger alef -> alef       (ٰ -> ا)  long /aː/
    0x06CC: 0x064A,   # farsi yeh             -> yeh   (non-Arabic variant, defensive)
    0x06A9: 0x0643,   # keheh                 -> kaf
    0x06BE: 0x0647,   # heh doachashmee       -> heh
    0x06C1: 0x0647,   # heh goal              -> heh
}
_FOLD = str.maketrans({chr(k): chr(v) for k, v in FOLD_MAP.items()})

# WHAT THE AUDIT FORCED OUT OF THIS TABLE (both errors were caught by measurement, not by review):
#
#  · U+0622 (آ, alef with madda) — NOT folded. An earlier draft folded it to bare ا and the
#    self-test caught it at once: قُرْآن became قُرْان and آية became اية. U+0622 is STANDARD
#    orthography, not an Uthmani variant, and the surface map contains آ legitimately — folding it
#    pushed the text AWAY from the map and manufactured mismatches on common words.
#
#  · U+0649 (ى, alef maksura) — NOT folded either, and this one was worse: the corpus audit showed
#    ى→ي corrupting 28.97% of a Tashkeela sample (عَلَى -> عَلَي, حَتَّى -> حَتَّي, تَعَالَى ->
#    تَعَالَي). ى is correct standard spelling; folding it turns real words into wrong ones. The
#    existing `MATCH_NORM` in measure_closed_class_ambiguity.py DOES map ى→ي, but only to build a
#    LOOKUP KEY — a key may be lossy, the emitted/compared string may not. That distinction is the
#    whole reason this table is separate from that one.
#
# NFC, by contrast, is KEPT, on measurement: over 60,000 tokens the corpora break down as
#     Tashkeela 14,566 non-NFC tokens — 100% ordering-only (shadda/fatha), 0 compositions
#     EQTB       7,768 non-NFC tokens — 6,849 ordering-only + 919 COMPOSITIONS
#                (e.g. ضَّآلِّينَ -> ضَّآلِّينَ: decomposed ا+U+0653 becomes precomposed آ)
# The 919 compositions are genuine Uthmani-vs-standard differences that no amount of letter folding
# reaches; canonical ordering is canonical equivalence, so normalising it is correct rather than a
# convenience. The cost is the both-sides contract above — hence the regression guard.


def fold(text: str) -> str:
    """Fold Uthmani orthography to standard: NFC, drop tajwid marks, fold letter variants."""
    if not text:
        return text
    s = unicodedata.normalize("NFC", text)
    s = "".join(c for c in s if ord(c) not in _TAJWID)
    return s.translate(_FOLD)


def describe(text: str) -> dict:
    """What the layer would change about one token — for auditing, not for scoring."""
    f = fold(text)
    removed = [c for c in unicodedata.normalize("NFC", text or "") if ord(c) in _TAJWID]
    folded = [c for c in (text or "") if ord(c) in FOLD_MAP
              and unicodedata.normalize("NFC", text or "") != f]
    return {"raw": text, "folded": f, "changed": f != text,
            "n_removed": len(removed),
            "removed_cps": [f"U+{ord(c):04X}" for c in removed],
            "folded_cps": [f"U+{ord(c):04X}" for c in folded]}


# --------------------------------------------------------------------- corpora
def iter_eqtb(cap: int):
    path = require(EQTB_CSV)
    import csv
    with open(path, encoding="utf-16", newline="") as fh:
        rd = csv.DictReader(fh, delimiter="\t")
        col = next((c for c in (rd.fieldnames or []) if c and "uthmani" in c.lower()
                    and "token" in c.lower()), None)
        if col is None:
            sys.exit(f"no vocalized token column in {rd.fieldnames[:8]}")
        n = 0
        for row in rd:
            tok = (row.get(col) or "").strip()
            if not tok or not ARABIC.search(tok):
                continue
            yield tok
            n += 1
            if n >= cap:
                return


def iter_tashkeela(cap: int, n_books: int = 10):
    n = 0
    with open(BOOKS, encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if i >= n_books:
                break
            text = (json.loads(line) or {}).get("text") or ""
            for tok in text.split():
                if not ARABIC.search(tok):
                    continue
                yield tok
                n += 1
                if n >= cap:
                    return


def audit(name: str, tokens, show: int = 12) -> dict:
    n = changed = skel_changed = 0
    removed = collections.Counter()
    folded_letter = collections.Counter()
    examples = collections.Counter()
    for t in tokens:
        n += 1
        d = describe(t)
        if d["changed"]:
            changed += 1
            # Did the CONSONANTAL SKELETON move? Removing tajwid marks and re-ordering combining
            # marks are harmless; substituting a base letter is not — for standard orthography it
            # must be zero, and a non-zero count is the fingerprint of a folding bug.
            skel_changed += skeleton(t) != skeleton(d["folded"])
            removed.update(d["removed_cps"])
            folded_letter.update(d["folded_cps"])
            examples[f"{t}  ->  {d['folded']}"] += 1
    print(f"\n--- {name} ---")
    if not n:
        print("  no tokens")
        return {"name": name, "tokens": 0, "changed": 0}
    print(f"  tokens                 : {n:,}")
    print(f"  changed by the layer   : {changed:,} = {100*changed/n:.2f}%")
    print(f"  of which SKELETON-change: {skel_changed:,} "
          f"(base-letter substitution; must be 0 for standard orthography)")
    if removed:
        top = ", ".join(f"{c}×{v:,}" for c, v in removed.most_common(6))
        print(f"  marks removed (top)    : {top}")
    if folded_letter:
        top = ", ".join(f"{c}×{v:,}" for c, v in folded_letter.most_common(6))
        print(f"  letters folded (top)   : {top}")
    if examples:
        print(f"  most common changes    :")
        for ex, c in examples.most_common(show):
            print(f"    {ex}   ×{c:,}")
    return {"name": name, "tokens": n, "changed": changed,
            "skeleton_changed": skel_changed,
            "removed_cps": dict(removed), "folded_cps": dict(folded_letter),
            "examples": dict(examples.most_common(40))}


CASES = [
    ("ٱلْحَمْدُ", "الْحَمْدُ", "alef wasla (U+0671) folds to alef"),
    ("مَٰلِكِ", "مَالِكِ", "dagger alef (U+0670) folds to a long-a letter"),
    ("كِتَٰب", "كِتَاب", "fatha + dagger alef -> fatha + alef"),
    ("وَٱللَّهِ", "وَاللَّهِ", "wasla after a proclitic"),
    ("مِنْ", "مِنْ", "plain vocalised word: UNCHANGED"),
    ("رَسُولِ", "رَسُولِ", "Tashkeela-style word: UNCHANGED (regression guard)"),
    ("بِسْمِ\u06e1", "بِسْمِ", "small high dotless head of khah (tajwid) removed"),
    ("قُرْآن\u06dd", "قُرْآن", "end-of-ayah sign (U+06DD) removed"),
    ("هُدًى", "هُدًى", "alef maksura is STANDARD orthography: kept, not folded"),
    ("عَلَى", "عَلَى", "…so the preposition keeps its alef maksura (was a 28.97% corruption)"),
    ("\u0627\u0644\u0644\u0651\u064e\u0647\u064f", "\u0627\u0644\u0644\u064e\u0651\u0647\u064f",
     "NFC canonical ordering: shadda+fatha -> fatha+shadda (applied to the map as well)"),
    ("ٱلرَّحْمَٰنِ", "الرَّحْمَانِ", "the fully-marked Rahman form"),
    ("قُرْآن", "قُرْآن", "U+0622 (آ) is standard orthography: NOT folded (see NOTE)"),
    ("آيَة", "آيَة", "…so آية keeps its madda, matching the surface map"),
]


def skeleton(s: str) -> str:
    """The consonantal skeleton: base letters only, all combining marks gone."""
    return "".join(c for c in (s or "") if not unicodedata.combining(c))


def selftest() -> int:
    print("=" * 84)
    print("normalize_uthmani — known-answer self-test")
    print("=" * 84)
    bad = []
    for raw, want, why in CASES:
        got = fold(raw)
        ok = got == want
        print(f"  {'ok ' if ok else 'FAIL'} {raw!r:22} -> {got!r:22} (want {want!r})  {why}")
        if not ok:
            bad.append((raw, want, got))
    # the two invariants that keep the metric meaningful
    keep = "الْحَمْدُ لِلَّهِ"
    if fold(keep) != keep:
        bad.append((keep, keep, fold(keep)))
        print(f"  FAIL harakat must survive: {keep!r} -> {fold(keep)!r}")
    else:
        print(f"  ok  harakat survive (vocalisation is the metric, not noise)")
    print()
    if bad:
        print(f"SELFTEST FAILED — {len(bad)} case(s)")
        return 1
    print("SELFTEST PASSED — folding, removal and both invariants hold")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--check", choices=["eqtb", "tashkeela"], nargs="+")
    ap.add_argument("--cap", type=int, default=60_000)
    args = ap.parse_args()
    if args.selftest or not args.check:
        return selftest()
    out = []
    for target in args.check:
        if target == "eqtb":
            out.append(audit(f"EQTB uthmani (cap {args.cap:,})", iter_eqtb(args.cap)))
        else:
            out.append(audit(f"Tashkeela books 0-9 (cap {args.cap:,}, "
                             f"expect NFC ordering only — SKELETON-change must be 0)",
                             iter_tashkeela(args.cap)))
    p = Path("data/normalize_uthmani_audit.json")
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nartifact -> {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
