"""wazan_normalizer.py — corrected §6 pipeline.

Fixes vs SPEC-REV5:
  1. strip_case_from_wazan no longer eats a RADICAL alif (defective roots).
     Rule: if the radical-digit set is COMPLETE, the trailing alif is orthographic
     (tanwin-alif) -> strip it. If a slot digit is MISSING, a trailing weak literal
     IS the missing radical -> map it to that digit instead of deleting it.
  2. The call ORDER is fixed and documented: expand_geminate -> map weak literal -> strip case.
     (Was unspecified; the two orders gave different labels.)
  3. extract_clean_lemma rejects non-Arabic garbage, not just empty strings.

Added 2026-10-09 (Task 2 + the two defects it exposed):
  4. PROCLITIC STRIPPING. The label used to carry the article ('المستشار' ->
     'المُسْتَ123'), entangling Head 3 with the clitic plane. The clitic surface is
     read from CALIMA's `d3tok` — NOT from prc0-prc3, which are LABELS
     ('Al_det','wa_conj','bi_prep') carrying no letters and ordered innermost-first.
  5. ENCLITIC STRIPPING from the right edge, same mechanism, separator '_+' in d3tok.
  6. GEMINATE EXPANSION IS NOW ROOT-GATED. It used to fire on ANY shadda, which
     corrupted فُعّال-class templates on SOUND roots ('الطُّلّاب' -> '1ُ23ا3',
     duplicating digit 3). It now fires only when C2 == C3.

Both strips run BEFORE _map_missing_slot_literal, which rewrites the LAST weak
literal — otherwise a clitic containing و/ا/ي can be mistaken for a missing radical,
or shield the stem's own weak radical from recovery.

Every strip carries the SAME hard guard: the radical-digit set must be IDENTICAL
before and after, so a mis-aligned cut is refused rather than silently accepted.
This project's catalogued failure mode is code that runs, reports success, and does
nothing; here a refused strip is an explicit False in the returned record.
"""
import re

DIACRITICS = re.compile(r"[\u064b-\u0652\u0670]")
CASE_MARKS = re.compile(r"[\u064b-\u0652\u0670]")   # fatha..sukun + dagger alef
ARABIC_ONLY = re.compile(r"^[\u0621-\u064a]+$")
DIG = re.compile(r"[1-4]")
WEAK_LITERAL = {"\u0627": "3", "\u0649": "3", "\u064a": "3", "\u0648": "3"}  # ا ى ي و


def tail_strip(label: str) -> str:
    """The Head-3 class of a `t_wazan` label: everything through the LAST radical digit.

    THE ONE IMPLEMENTATION — used by the data build, the vocabulary and the target builder, so the three can
    never disagree about what a class is. The literal run AFTER the last digit is inflection, not wazan
    (`123َة`, `1ا2َ3ْت`, `12ئِ3َت`: §2bs measured 63.5% of labels carrying one, and it is what inflated the old
    target space to 6,633 classes of which 46% were never supervised). Leading literals are KEPT: مُسْتَ-, مُ-,
    أَ-, تَ- are mazid/participial TEMPLATE matter and are exactly what a wazan is for.

    Returns "" for a label with no radical digit at all — the malformed labels the mask already rejects.
    """
    spans = list(DIG.finditer(label or ""))
    return label[:spans[-1].end()] if spans else ""


def trailing_run(label: str) -> str:
    """The literal run after the last radical digit — the inflectional tail `tail_strip` removes."""
    spans = list(DIG.finditer(label or ""))
    return label[spans[-1].end():] if spans else ""


STEM_TAIL_CLASSES = [
    "", "ة", "ات", "ان", "ين", "ون", "ت", "وا", "نا", "ي", "ى", "ية"
]


def extract_stem_tail(label: str | None) -> str:
    """Extract inflectional tail stripped by tail_strip, normalized without diacritics.

    NOTE (§2cl): the DIACRITIC-FREE form is not renderable. Kept for backward compatibility; use
    `vocalized_stem_tail` for anything that has to produce a surface.
    """
    tail = trailing_run(label or "")
    return DIACRITICS.sub("", tail) if tail else ""


def vocalized_stem_tail(label: str | None) -> str:
    """The VOCALIZED inflectional tail of a wazān label — `trailing_run`, verbatim (§2cl).

    MEASURED, NOT ASSUMED. `trailing_run(t_wazan_pattern)` over the 278 usable gold rows yields
    **23 distinct vocalized runs**: 20 carry letters (َة ى َان ْتُ َتْ …) and **3 are pure diacritics
    (َ ُ ْ)** — the terminal case vowel the gold pattern spells out.

    AN EARLIER DRAFT FILTERED THE PURE-DIACRITIC ONES OUT as "not really tails", on the reasoning that
    the case vowel is `case`'s job. **That was measured and is WRONG: it cost 29 rows** (57.6% ->
    47.1%). On rows whose gold `case` is None/ABSTAIN the pattern's terminal diacritic is the ONLY
    carrier of the final vowel, so filtering it produced وَقَال for وَقَالَ. All 23 runs are kept.

    WHY THE VOCALIZATION IS THE WHOLE POINT. `STEM_TAIL_CLASSES` (12 diacritic-free classes) collapses
    those 23 endings into 15 and loses 8 distinct surfaces. In a pedagogical Arabic app the collapsed
    cases ARE the lesson: diacritic-free "ت" is ْتُ (1cs) / ْتَ (2ms) / ْتِ (2fs) / َتْ (3fs) at once.
    The vowel BEFORE the tail is part of the class too — it is fixed by the paradigm (ْ before
    تُ/تَ/تِ/نَا/تُمْ, َ before تْ, ُ before وا/ون, ِ before ين) and cannot be recovered from a skeleton.
    """
    return trailing_run(label or "")


def strip_diac_tail(t: str) -> str:
    """Letters of a tail (used to decide whether a 'tail' is real)."""
    return DIACRITICS.sub("", t or "")


# THE 20 VOCALIZED TAILS ATTESTED IN gold-tashkeela-300 (measured, with counts in §2cl).
STEM_TAIL_VOCALIZED_MEASURED = [
    "\u064e\u0629", "\u0649", "\u064e\u0627\u0646", "\u0652\u062a\u064f", "\u064e\u062a\u0652",
    "\u064e\u0627\u0621", "\u064e\u0627\u062a", "\u0652\u062a\u064e", "\u0650\u064a\u0646",
    "\u064f\u0648\u0646\u064e", "\u064a", "\u064e\u0627\u0646\u0650", "\u0646\u064e",
    "\u0651\u0650\u064a\u0651", "\u0650\u064a\u0651", "\u0652\u0646\u064e\u0627",
    "\u064e\u062a\u064e\u0627\u0646", "\u0627", "\u064f\u0648\u0627", "\u064e\u064a\u0652\u0646",
]

# ============================ THE SHIPPED TARGET SPACE (§2cz, 2026-10-14) ====================
# THE GOLD-300 VOCABULARY, kept under an explicit legacy name. This is the 30-class space every
# §2cs/§2cu number was measured against, and `tools/stem_tail_audit.py --space 30` still gates it.
STEM_TAIL_VOCALIZED_GOLD300 = ["", *STEM_TAIL_VOCALIZED_MEASURED,
                              "\u064e", "\u064f", "\u0652",        # terminal vowels (measured)
                              "\u0652\u062a\u064f\u0645\u0652",    # \u0645 2mp (completion)
                              "\u0652\u062a\u064f\u0646\u0651",    # 2fp (completion)
                              "\u064e\u062a\u064e\u0627",          # 3fd (completion)
                              "\u064e\u064a\u0652\u0646\u0650",    # dual ACC/GEN (completion)
                              "\u0650\u064a\u0646\u064e",          # sound masc pl ACC/GEN (completion)
                              "\u0650\u064a\u0651\u064e\u0629"]    # nisbah fem (completion)

# THE CORPUS VOCABULARY: every real-unseen tail the TRAINING corpora actually supervise, with no
# candidate class to bridge to. 125 classes / 40387 supervised tokens. Previously these rows carried
# class 0 = "bare stem" WITH a live gradient — a confidently wrong label, not a masked row.
STEM_TAIL_VOCALIZED_CORPUS = [
    "\u0621",   #   11325 tok
    "\u064f\u0648",   #    6433 tok
    "\u0652\u0646",   #    4932 tok
    "\u064e\u0649",   #    4822 tok
    "\u064e\u064a",   #    1547 tok
    "\u064e\u062a\u064e\u064a\u0652\u0646",   #    1141 tok
    "\u0648",   #    1081 tok
    "\u0621\u064e\u0629",   #     941 tok
    "\u0626",   #     867 tok
    "\u0670\u0646",   #     757 tok
    "\u064f\u0645",   #     609 tok
    "\u064e\u0626\u0650\u0630",   #     592 tok
    "\u0624",   #     455 tok
    "\u0643",   #     413 tok
    "\u064e\u0623",   #     411 tok
    "\u0650\u0626",   #     402 tok
    "\u0650\u064a\u0651\u0627\u062a",   #     313 tok
    "\u0627\u0626\u064e\u0629",   #     303 tok
    "\u0650\u064a\u0651\u0650\u064a\u0646",   #     272 tok
    "\u064e\u0645",   #     255 tok
    "\u0650\u064a\u0651\u0627",   #     250 tok
    "\u0650\u064a\u0651\u064e\u062a",   #     222 tok
    "\u0651\u0650\u0626",   #     148 tok
    "\u0651\u064e\u0623",   #     145 tok
    "\u0627\u062a\u0647",   #     129 tok
    "\u0627\u0646\u0650\u064a",   #     120 tok
    "\u0627\u0626",   #     112 tok
    "\u062a\u0647",   #     112 tok
    "\u0626\u064e\u0629",   #     102 tok
    "\u0650\u064a\u0651\u064e\u064a\u0652\u0646",   #     102 tok
    "\u0621\u064e\u062a",   #      84 tok
    "\u0650\u064a\u0651\u064f\u0648\u0646",   #      81 tok
    "\u064e\u062a\u064e\u064a",   #      68 tok
    "\u062f",   #      66 tok
    "\u0627\u0646\u0650\u064a\u0651\u064e\u0629",   #      54 tok
    "\u0627\u0624",   #      48 tok
    "\u062a\u0647\u0645",   #      41 tok
    "\u0652\u062a\u064f\u0645\u064f\u0648",   #      36 tok
    "\u0627\u062a\u0647\u0645",   #      34 tok
    "\u064e\u0622",   #      34 tok
    "\u0644\u0650\u0643",   #      31 tok
    "\u0650\u0626\u064e\u0629",   #      28 tok
    "\u0650\u064a\u0646\u0627\u062a",   #      28 tok
    "\u062a\u0643",   #      25 tok
    "\u0627\u0648\u0650\u064a",   #      21 tok
    "\u0631\u064e\u062a",   #      21 tok
    "\u0627\u0637",   #      20 tok
    "\u064e\u0623\u064e\u0629",   #      19 tok
    "\u0650\u064a\u0651\u064e\u062a\u064e\u064a\u0652\u0646",   #      18 tok
    "\u0644\u064e\u0629",   #      16 tok
    "\u0646\u064e\u0629",   #      15 tok
    "\u0627\u0626\u0650\u064a\u0651\u064e\u0629",   #      14 tok
    "\u0627\u062a\u0643",   #      14 tok
    "\u0650\u064a\u0651\u0627\u0646",   #      13 tok
    "\u0631\u064e\u0629",   #      12 tok
    "\u064f\u0624",   #      11 tok
    "\u062a\u0643\u064f\u0645",   #      10 tok
    "\u064e\u0648\u0652\u062a",   #       9 tok
    "\u064f\u0648\u064e\u0629",   #       9 tok
    "\u0626\u064e\u062a",   #       8 tok
    "\u0627\u062a\u0646",   #       8 tok
    "\u0644",   #       8 tok
    "\u064f\u0648\u062a",   #       8 tok
    "\u0650\u064a\u0627\u0621",   #       8 tok
    "\u0650\u064a\u0651\u0627\u062a\u0647",   #       7 tok
    "\u0650\u064a\u0651\u064e\u062a\u0627\u0646",   #       7 tok
    "\u0627\u0626\u0650\u064a",   #       6 tok
    "\u0627\u0628",   #       6 tok
    "\u0627\u0631",   #       6 tok
    "\u062e\u064e\u0629",   #       6 tok
    "\u064e\u062a\u064e\u0626\u0650\u0630",   #       6 tok
    "\u0627\u0646\u0627",   #       5 tok
    "\u062f\u064e\u062a",   #       5 tok
    "\u0647",   #       4 tok
    "\u064e\u0648",   #       4 tok
    "\u064e\u0648\u0627\u062a",   #       4 tok
    "\u064e\u064a\u0627\u0646",   #       4 tok
    "\u064e\u064a\u064e\u064a\u0652\u0646",   #       4 tok
    "\u0650\u064a\u0643",   #       4 tok
    "\u0651\u064e\u0622",   #       4 tok
    "\u0627\u062a\u0650\u064a\u0651\u064e\u0629",   #       3 tok
    "\u0627\u0646\u0650\u064a\u0651\u064e\u062a",   #       3 tok
    "\u064e\u064a\u0652\u062a",   #       3 tok
    "\u0650\u064a\u0627\u0626",   #       3 tok
    "\u0650\u064a\u062f",   #       3 tok
    "\u0650\u064a\u0646\u0650\u064a\u0651\u0627\u062a",   #       3 tok
    "\u0651\u064f\u0645",   #       3 tok
    "\u0627\u0626\u0650\u064a\u0651\u064e\u064a\u0652\u0646",   #       2 tok
    "\u0627\u0637\u064e\u064a",   #       2 tok
    "\u0627\u0644",   #       2 tok
    "\u0627\u0648\u0650\u064a\u0651\u064e\u0629",   #       2 tok
    "\u062c",   #       2 tok
    "\u064e\u0623\u0652\u0646",   #       2 tok
    "\u064e\u062c",   #       2 tok
    "\u064e\u0647",   #       2 tok
    "\u064e\u064a\u0627\u062a",   #       2 tok
    "\u0650\u064a\u0631",   #       2 tok
    "\u0650\u064a\u0644",   #       2 tok
    "\u0650\u064a\u0651\u0650\u064a",   #       2 tok
    "\u0651\u064f\u0646",   #       2 tok
    "\u0627\u0626\u0650\u064a\u0651\u0627",   #       1 tok
    "\u0627\u0646\u0650\u064a\u0651\u0627",   #       1 tok
    "\u0627\u0646\u0650\u064a\u0651\u064e\u064a\u0652\u0646",   #       1 tok
    "\u0627\u0646\u0650\u064a\u0651\u064f\u0648\u0646",   #       1 tok
    "\u0627\u064e\u0629",   #       1 tok
    "\u0636",   #       1 tok
    "\u0645\u064e\u0629",   #       1 tok
    "\u064e\u0622\u062a",   #       1 tok
    "\u064e\u0622\u062a\u0647",   #       1 tok
    "\u064e\u062f",   #       1 tok
    "\u064e\u0631\u0652\u062a",   #       1 tok
    "\u064e\u0631\u0652\u0646",   #       1 tok
    "\u064e\u0636\u0652\u062a",   #       1 tok
    "\u064e\u0648\u0650\u064a",   #       1 tok
    "\u064f\u0648\u0646\u0650\u064a",   #       1 tok
    "\u0650\u0626\u0652\u062a",   #       1 tok
    "\u0650\u0626\u0652\u0646",   #       1 tok
    "\u0650\u0633",   #       1 tok
    "\u0650\u064a\u0627\u0624",   #       1 tok
    "\u0650\u064a\u0637",   #       1 tok
    "\u0650\u064a\u0651\u0627\u062a\u0647\u0645",   #       1 tok
    "\u0650\u064a\u0651\u064e\u064a",   #       1 tok
    "\u0650\u064a\u0651\u064f\u0648",   #       1 tok
    "\u0651\u0627\u062a\u0647",   #       1 tok
    "\u0651\u0627\u062a\u0647\u0645",   #       1 tok
]

# AMBIGUOUS BY MARK ORDER: two classes sit at the same distance, differing only in the order of
# their marks (\u064e\u062a\u0652 vs \u0652\u062a\u064e). The bridge must NOT pick one — that would invent an order the corpus did
# not write. So the observed tail becomes its own class. 4 classes / 34455 supervised tokens.
# (§2cs had re-registered this bucket as "needs an input the notation lacks"; that premise is wrong:
#  no input is missing, the ambiguity was between two REWRITES of the tail, and the honest answer
#  to two wrong rewrites is to not rewrite.)
STEM_TAIL_VOCALIZED_AMBIGUOUS = [
    "\u064e\u062a",   #   28525 tok
    "\u062a",   #    3515 tok
    "\u0652\u062a",   #    2194 tok
    "\u0651\u064e\u062a",   #     221 tok
]

# BRIDGEABLE-BUT-OBSERVED: tails that have a nearest candidate class AND are attested in training.
# These are their OWN classes, not bridged, and the measurement is why: with `\u0652\u0646` added above, the
# observed tail `\u0646` acquired a SECOND candidate at the same distance and fell out of the bridge
# entirely — 6,919 rows (1,010 PADT / 5,909 silver) silently moved from a repair to IGNORE.
# A tail the training data witnesses describes a surface the model must be able to emit; it does not
# need bridging. 17 classes / 37570 supervised tokens.
STEM_TAIL_VOCALIZED_BRIDGEABLE = [
    "\u0650\u064a",   #    9725 tok
    "\u0646",   #    6919 tok
    "\u0627\u062a",   #    5533 tok
    "\u0627\u0646",   #    4362 tok
    "\u0651\u064e\u0629",   #    4201 tok
    "\u064f\u0648\u0646",   #    3579 tok
    "\u0627\u0621",   #    2425 tok
    "\u0652\u062a\u064f\u0645",   #     321 tok
    "\u0650\u064a\u064e\u0629",   #     254 tok
    "\u064e\u062a\u0627\u0646",   #     229 tok
    "\u0651\u0627\u062a",   #      14 tok
    "\u0651\u0627\u0646",   #       2 tok
    "\u0652\u062a\u064f\u0646",   #       2 tok
    "\u064e\u0646",   #       1 tok
    "\u0651\u0627",   #       1 tok
    "\u0651\u064f\u0648\u0646",   #       1 tok
    "\u0651\u0650\u064a\u0646",   #       1 tok
]

# THE SHIPPED CLASS SPACE = every tail the TRAINING corpora supervise, except non-Arabic junk.
# `STEM_TAIL_VOCALIZED` keeps its name so that every consumer (the model arms' head, the eval
# harness) inherits the completed space WITHOUT editing them — the defect was that a lookup
# defaulted to class 0, and the repair belongs in one module, not in each consumer.
#
# The BRIDGE's job is what is left: a tail the space does NOT contain, i.e. one never seen in
# training. That is measured on the frozen ruler (9 rows), not on the corpora.
STEM_TAIL_VOCALIZED = [*STEM_TAIL_VOCALIZED_GOLD300, *STEM_TAIL_VOCALIZED_CORPUS,
                       *STEM_TAIL_VOCALIZED_AMBIGUOUS, *STEM_TAIL_VOCALIZED_BRIDGEABLE]
assert len(STEM_TAIL_VOCALIZED) == len(set(STEM_TAIL_VOCALIZED)), "duplicate class in the space"
assert len(STEM_TAIL_VOCALIZED) == 176, "space size drifted from the measured 176"

# THE ONLY MASK. `IGNORE` is the training ignore index; a class that is a REAL but never-observed
# tail resolves to its own class (above), so IGNORE is reached only by a tail this notation cannot
# spell: one carrying a literal pattern digit (the extractor's `DIG = [1-4]` is narrower than the
# corpus's slot digits 5-6 — measured 436 tokens / 13 patterns, reported in §2cz, not fixed here).
STEM_TAIL_IGNORE = -100


FATHA = "\u064e"
ALIF = "\u0627"
SUKUN = "\u0652"
SHADDA = "\u0651"
HAMZA_ABOVE = "\u0623"
CONSONANT_CHARS = r"[1-4\u0621-\u0626\u0628-\u063a\u0641-\u064a]"


def canonicalize_mater_vowels(pattern: str | None) -> str | None:
    """Canonicalize mater vowels to eliminate CALIMA vs human gold convention splits.

    1. Whenever a radical digit (1, 2, 3, 4) or template consonant is immediately
       followed by bare alif ا (with no intervening diacritic), insert fatha َ before ا.
       (1ا2ِ3 -> 1َا2ِ3, 1َ2ا3 -> 1َ2َا3, مَ1ْ2ا3 -> مَ1ْ2َا3)
    2. Ensure word-initial أ before a vowelless slot carries its hamza vowel
       (أ1ْ2َ3 -> أَ1ْ2َ3).
    """
    if not pattern:
        return pattern
    # NO NFC PASS HERE (§2cv). It is applied on the other paths (`canonicalize_vocalized_wazan`,
    # `eval_harness`, `final_surface`), so composition is not lost; applying it HERE reorders the marks of
    # `...ِي3َّ ة`, which drops the yāʾ's shadda — measured on 2 frozen-ruler rows (الْقَضِيَّةَ, بَقِيَّةِ).
    w = pattern
    # ANCHORED TO A RADICAL DIGIT — the only context the docstring above documents (1ا2ِ3 / 1َ2ا3 / مَ1ْ2ا3).
    # Accepting any consonant instead made the sound masculine plural ending `ُوا` become `ُوَا`, which broke
    # 4 more frozen-ruler rows (يَهْتِكُوا, فَخَلُّوا, وَارْكَبُوا, فَأَقْشَعُوا). Measured: §2cv.
    w = re.sub(r"([1-4])" + ALIF, r"\g<1>" + FATHA + ALIF, w)
    w = re.sub(r"([1-4]" + SHADDA + r")" + ALIF, r"\g<1>" + FATHA + ALIF, w)
    w = re.sub(r"^" + HAMZA_ABOVE + r"(?=[1-4\u0621-\u064a]" + SUKUN + ")", HAMZA_ABOVE + FATHA, w)
    w = re.sub(r"^" + HAMZA_ABOVE + r"(?=[1-4])", HAMZA_ABOVE + FATHA, w)
    w = re.sub(FATHA + "+", FATHA, w)
    return w


_VALID_WAZAN_CHARS = re.compile(r"^[1234\u0621-\u063a\u0641-\u064a\u064b-\u0652\u0670\u0671]+$")
_RADICAL_DIGITS = re.compile(r"[1234]")


def split_wazan_stem_and_tail(raw_wazan: str) -> tuple[str, str] | None:
    if not raw_wazan or not _VALID_WAZAN_CHARS.match(raw_wazan):
        return None  # Rejects 'َ5', page markers, and non-Arabic junk -> IGNORE (-100)
    matches = list(_RADICAL_DIGITS.finditer(raw_wazan))
    if not matches:
        return None
    last_digit_end = matches[-1].end()
    # Keep shadda (and any vowel between the last digit and shadda) on the last radical slot!
    # Only strip the vowel that immediately precedes the suffix (or ends the word).
    rest = raw_wazan[last_digit_end:]
    shadda_match = re.match(r"^([\u064e\u064f\u0650]*\u0651)", rest)
    if shadda_match:
        last_digit_end += shadda_match.end()
        rest = raw_wazan[last_digit_end:]

    # Strip the connecting stem vowel into the tail so the tail is self-contained for splicing
    stem_raw = raw_wazan[:last_digit_end]
    tail_raw = rest

    # If there are no Arabic letters in tail_raw, it is a BARE stem (trailing vowels are case/mood)
    if not re.search(r"[\u0621-\u063a\u0641-\u064a]", tail_raw):
        stem_canon = canonicalize_mater_vowels(stem_raw)
        return (stem_canon, "")

    # Canonicalize leading mater vowels on the tail so CALIMA 'ات'/'ان'/'اء'/'ى' match Gold 'َات'/'َان'/'َاء'/'َى'
    if tail_raw.startswith("\u0627") or tail_raw.startswith("\u0649"):  # bare 'ا' or 'ى'
        tail_canon = "\u064e" + tail_raw  # prepend fatha 'َ'
    elif tail_raw.startswith("\u0648") and not re.match(r"^\u0648[\u064e\u064f\u0650\u0652\u0651]", tail_raw):
        tail_canon = "\u064f" + tail_raw  # prepend damma 'ُ' before bare waw mater 'ون'/'وا'
    elif tail_raw.startswith("\u064a") and not re.match(r"^\u064a[\u064e\u064f\u0650\u0652\u0651]", tail_raw):
        tail_canon = "\u0650" + tail_raw  # prepend kasra 'ِ' before bare ya mater 'ين'/'ي'
    else:
        tail_canon = tail_raw

    tail_canon = canonicalize_mater_vowels(tail_canon)
    stem_canon = canonicalize_mater_vowels(stem_raw)
    return (stem_canon, tail_canon)


def canonicalize_vocalized_wazan(w: str | None) -> str:
    """Canonicalize vocalized wazān template to eliminate convention/orthographic splits.

    Normalizes:
      1. Unicode NFC composition
      2. Tatweel removal
      3. Shadda-first ordering (shadda \u0651 preceding vowels/tanwins)
      4. Deduplication of adjacent identical diacritics
      5. Mater vowel canonicalization (1ا2ِ3 -> 1َا2ِ3, أ1ْ2َ3 -> أَ1ْ2َ3)
      6. Initial alif wasla prefix normalization
      7. Trailing case vowels/tanwin stripped
    """
    if not w:
        return ""
    import unicodedata as _uni
    w = _uni.normalize("NFC", w)
    w = w.replace("\u0640", "")  # tatweel
    # Shadda-first ordering
    w = re.sub(r"([\u064b-\u0650\u0652])\u0651", "\u0651" + r"\1", w)
    # Deduplicate diacritics
    w = re.sub(r"([\u064b-\u0652])\1+", r"\1", w)
    # Mater vowel canonicalization
    w = canonicalize_mater_vowels(w)
    # Initial alif wasla prefix normalization
    w = re.sub(r"^\u0627\u0650(?=1|\u0633|\u062a)", "\u0627", w)
    # Strip trailing case mark / tanwin
    w = re.sub(r"[\u064b-\u0652\u0670]+$", "", w)
    return w


# The 118 Canonical Wazān Skeletons (derived from the gold benchmark data/annotation/bench-gold.jsonl)
CANONICAL_WAZAN_118 = [
    "123", "1234", "1234ان", "1234ة", "1234ي", "123ا4", "123اء", "123ات", "123ان", "123ة",
    "123ت", "123تين", "123نا", "123وا", "123ى", "123ي", "123ية", "12ا3", "12ا34ة", "12ا3ات",
    "12ا3ان", "12ا3ة", "12ا3ى", "12ا3ي", "12ا3ين", "12ائ3", "12و3", "12ي3", "12ي3ة", "1ا23",
    "1ا23ة", "1ا23ت", "1ا2ا3", "1ا2و3", "1ي23", "1يا23", "أ123", "أ123ا", "أ123اء", "أ123ة",
    "أ123ت", "أ123وا", "أ123ى", "أ123ي", "أ12ا3", "أ12ا3ة", "أ1ا23", "أ1ا23ة", "أ1ا23ت", "أ1ي23",
    "إ12ا3", "إ12ا3ان", "إ12ا3ة", "ا123ت", "ا123وا", "ا1ت23", "ا1ت23ا", "ا1ت23ت", "ا1ت2ا3", "ا1ت2ا3ات",
    "است123", "است123ت", "است12ا3", "است12ا3ة", "است1ا23", "ان123", "ان12ا3", "ت123", "ت123ة", "ت123وا",
    "ت123ى", "ت12ا3", "ت12ي3", "ت1ا23", "ت1ا23ت", "ت1ا23ى", "ت1ت23", "ت1تا23", "تت123", "تت1ا23",
    "تست123", "م123", "م123ات", "م123ان", "م123ة", "م123ى", "م123ين", "م12ا3", "م12ا3ة", "م12و3",
    "م12و3ان", "م1ا23", "م1ا23ة", "م1ا2ا3ة", "م1ا2ي3", "م1ت23", "م1ت23ة", "م1تا23", "م1ي23", "مت123",
    "مت1234ة", "مت123ة", "مت1ا23ة", "مست123", "مست123ان", "مست123ة", "من123", "نن123", "ي123", "ي123وا",
    "ي123ون", "ي12ا3", "ي1ا23", "ي1ت23", "يت123", "يت1ا23ا", "يست123", "ين12ا3"
]

# Closed-class proclitic and enclitic categories in MSA
PROCLITIC_CLASSES = [
    "ال", "ب", "بال", "س", "ف", "فس", "فك", "فل", "ك", "كال", "ل", "لال",
    "و", "وال", "وب", "وبال", "وك", "ول", "ولال", "أ", "لا", "وس"
]

ENCLITIC_CLASSES = [
    "ه", "ها", "هم", "هما", "هن", "ك", "كم", "كما", "كن", "نا", "ي", "ني", "ما", "من", "لا"
]


def canonical_wazan_skeleton(label: str) -> str:
    """Extract canonical skeleton from pattern or wazan label (tail-stripped, diacritics removed, alif wasla mapped)."""
    s = DIACRITICS.sub("", tail_strip(label) if label else "")
    return s.replace("ٱ", "ا")


def extract_clean_lemma(raw_lex: str) -> str:
    """CALIMA `lex` -> a usable dictionary key. (Field is `lex`, NOT `lemma`.)

    NOTE ON LIMITS: the assertions below catch EMPTY and NON-ARABIC values. They do
    NOT catch semantic garbage -- CALIMA returns lex='راوَنْد' for رَأَى, which is
    valid Arabic script of plausible length and passes every check here. The only
    reliable guard for that is to cross-check the key against the gold lexicon at
    use time and record the miss rate. Do not describe this function as validating
    the lemma; it validates the *shape* of the lemma.
    """
    assert raw_lex and isinstance(raw_lex, str), "CALIMA lex is empty/missing"
    s = DIACRITICS.sub("", raw_lex).replace("\u0640", "").strip()   # drop tatweel
    assert s, f"empty after stripping diacritics: {raw_lex!r}"
    assert ARABIC_ONLY.match(s), f"lex is not Arabic: {raw_lex!r} -> {s!r}"
    assert 2 <= len(s) <= 12, f"implausible lemma length: {s!r}"
    return s


def expand_geminate_ungated_rev8(pat: str) -> str:
    """RETAINED FOR PROVENANCE ONLY — do not use in the pipeline.

    This is the rev-8 behaviour verbatim (fire on any shadda). It is kept so the
    published 53.6% well-formed-coverage figure stays reproducible and the effect of
    the gate can be stated as a measured delta instead of an assertion
    (measure_normalizer_gain.py reports both rows).
    """
    def repl(m):
        v = m.group(2) or m.group(4) or ""
        return f"{m.group(1)}{v}3{v}"
    return re.sub(r"(2)([\u064b-\u0652]*)(\u0651)([\u064b-\u0652]*)", repl, pat)


def _radicals(root: str) -> list:
    """Radicals of a root in any of the project's four encodings.

    CALIMA emits dot-separated Arabic ('م.د.د'); some sources omit separators
    ('مدد'); PADT uses SPACE-separated Latin translit ('m d d' — spaces are radical
    separators, MANIFEST/§2h). Returns [] for an empty root so callers fail closed.
    """
    if not root:
        return []
    if "." in root:
        return [r for r in root.split(".") if r]
    if " " in root:
        return [r for r in root.split() if r]
    return list(root)


def is_geminate_root(root: str) -> bool:
    """True only when the root itself confirms doubling (C2 == C3), i.e. مُضاعَف."""
    rads = _radicals(root)
    return len(rads) == 3 and rads[1] == rads[2] and rads[1] not in ("#", "")


def expand_geminate(pat: str, root: str = "") -> str:
    """Geminate compressed pattern -> 3-slot form.  '1َ2َّ' -> '1َ2َ3َ'

    FIXED 2026-10-09 — this used to fire on ANY shadda, and a shadda in a pattern is
    NOT proof of a doubled root.  فُعَّال (الطُّلّاب, root ط-ل-ب, a SOUND root) and
    فَعَّلَ carry a TEMPLATIC shadda with slot 3 already present natively, so the old
    code produced '1ُ23ا3' — a duplicated digit 3 and an invalid wazān (caught by
    test_proclitic_strip.py; the loose digit-SET gate accepted it).

    It now fires ONLY when the root confirms gemination:
        root 'م.د.د'  -> geminate -> '1َ2ُّ'   becomes '1َ2ُ3ُ'      (correct)
        root 'ط.ل.ب'  -> sound    -> '1ُ2ّا3' returned UNCHANGED     (correct)

    With NO root we cannot confirm, so we do NOT expand. Deliberate: an unexpanded
    2-slot label FAILS the well-formedness gate, which is honest, whereas a wrongly
    expanded one silently corrupts the label — and this project has repeatedly been
    burned by that second failure mode.
    """
    if not is_geminate_root(root):
        return pat

    def repl(m):
        v = m.group(2) or m.group(4) or ""
        return f"{m.group(1)}{v}3{v}"
    return re.sub(r"(2)([\u064b-\u0652]*)(\u0651)([\u064b-\u0652]*)", repl, pat)


def _map_missing_slot_literal(pat: str, root: str) -> str:
    """If a radical slot is missing AND the root agrees that slot is the unassigned
    one (`#`), then a trailing weak literal RENDERS that missing radical -> map it
    to the digit.

    NEW GUARD (was missing in the first draft, which mapped affixes as radicals):
    the missing digit must match the `#` position in the root. Otherwise a suffix
    like the final ي of التي gets mistaken for radical 1.
    Also: replace the last WEAK LITERAL, not simply the last character.
    """
    if not root:
        return pat
    rads = root.split(".")
    hash_positions = {str(i + 1) for i, r in enumerate(rads) if r == "#"}
    present = set(DIG.findall(pat))
    missing = {"1", "2", "3"} - present
    if len(missing) != 1:
        return pat
    slot = missing.pop()
    if slot not in hash_positions:          # root disagrees -> do not guess
        return pat
    if slot == "1":
        hi = min((pat.find(d) for d in ("2", "3") if d in present), default=len(pat))
        cands = [i for i, c in enumerate(pat[:hi]) if c in WEAK_LITERAL]
        idx = cands[0] if cands else -1
    elif slot == "2":
        lo = pat.find("1") if "1" in present else -1
        hi = pat.find("3") if "3" in present else len(pat)
        sub = pat[lo + 1:hi] if lo != -1 else pat[:hi]
        cands = [lo + 1 + i for i, c in enumerate(sub) if c in WEAK_LITERAL]
        idx = cands[0] if cands else -1
    else:  # slot 3
        lo = max((pat.rfind(d) for d in ("1", "2") if d in present), default=-1)
        sub = pat[lo + 1:] if lo != -1 else pat
        cands = [lo + 1 + i for i, c in enumerate(sub) if c in WEAK_LITERAL]
        idx = cands[-1] if cands else -1
    if idx == -1:
        return pat
    return pat[:idx] + slot + pat[idx + 1:]


def strip_case(pat: str, root: str = "") -> str:
    """Remove the terminal case vowel / tanwin. Never eats a radical alif.

    Key rule: a terminal alif is only ORTHOGRAPHIC (tanwin-alif, removable) when
    the radical-digit set is already complete. When a slot is missing, that alif is
    the radical itself and `_map_missing_slot_literal` has already turned it into a
    digit -- so by the time we get here the alif is safe to drop.
    """
    present = set(DIG.findall(pat))
    complete = present in ({"1", "2", "3"}, {"1", "2", "3", "4"})
    if complete and pat.endswith("\u0627"):      # trailing orthographic alif
        pat = pat[:-1]
    return re.sub(r"[\u064b-\u0652\u0670]+$", "", pat)


# --------------------------------------------------------------------------
# Proclitic stripping (SPEC-REV6 §8.1 item 7 / START-HERE §8 Task 2)
#
# MEASURED on calima-msa-r13, 2026-10-09 — do not re-derive, and do not trust
# the earlier prose.  Three facts, each of which changes the implementation:
#
#   1. `prc0`-`prc3` ARE NOT SURFACES.  They are LABELS:
#          المستشار      prc0='Al_det'
#          والكتاب       prc0='Al_det', prc2='wa_conj'
#          فبالمدرسة     prc0='Al_det', prc1='bi_prep', prc2='fa_conj'
#      So the docs' "strip via prc0-prc3 alignment" cannot be done from those
#      fields alone -- they carry no letters.  `d3tok` is the field that does.
#
#   2. prc0 is the INNERMOST clitic, so index order is stem-outward, i.e. the
#      REVERSE of surface order.  `d3tok` already lists them outermost-first.
#
#   3. `d3tok` uses TWO different separators: '+_' AFTER a proclitic and '_+'
#      BEFORE an enclitic.  Splitting on '+_' therefore leaves any enclitic
#      attached to the stem, by construction (verified: 'كِتابِ_+هُ' has no
#      '+_' at all and yields no proclitic).
#
#      'ال+_مُسْتَشارُ'        -> proclitic 'ال'
#      'وَ+_ال+_كُتّابِ'       -> proclitics 'وَ','ال'  (surface order)
#      'فَ+_بِ+_ال+_مَدْرَسَة'  -> 'فَ','بِ','ال'
#      'كِتابِ_+هُ'            -> none (enclitic only)
#
#   Also verified: the pattern's proclitic is written UNASSIMILATED, so string
#   alignment works even for sun letters -- الشمس -> pattern 'ال1َ2ْ3ِ' matches
#   d3tok's 'ال'.  And the FEMININE ة is NOT a proclitic (مدرسة -> pattern
#   'مَ1ْ2َ3َةِ' keeps it, correctly).
#
# ORDER MATTERS: the proclitic strip must run BEFORE _map_missing_slot_literal.
# That function replaces the LAST weak literal in the pattern, so a proclitic
# containing و/ا/ي (وَ, فَ...ا) can be mistaken for a missing radical when the
# stem itself has no weak literal.  Stripping the prefix first removes the hazard.
PROCLITIC_SEP = "+_"
ENCLITIC_SEP = "_+"


def proclitic_surface(d3tok: str) -> str:
    """Proclitic surface from CALIMA `d3tok`, outermost-first, as a string."""
    if not d3tok:
        return ""
    segs = d3tok.split(PROCLITIC_SEP)
    return "".join(segs[:-1]) if len(segs) > 1 else ""


def enclitic_surface(d3tok: str) -> str:
    """Enclitic surface from CALIMA `d3tok` ('' when there is none)."""
    if not d3tok or ENCLITIC_SEP not in d3tok:
        return ""
    return d3tok.split(ENCLITIC_SEP, 1)[1]


def has_enclitic(analysis: dict) -> bool:
    enc = analysis.get("enc0")
    return bool(enc) and enc not in ("0", "na")


def _align_prefix(pat: str, prefix: str):
    """Index in `pat` just past `prefix`, comparing skeletons (diacritics ignored
    on both sides).  None if it does not align.

    After consuming a letter we also consume ITS diacritics in the pattern: a
    diacritic belongs to the preceding letter, so stopping at the letter leaves an
    orphaned fatha at the head of the label.  (Caught by this module's own test:
    strip_proclitic('مَ1ْ2َ3َةِ', 'مَ') returned a label starting with a bare 'َ'.)
    """
    i = 0
    for ch in prefix:
        if DIACRITICS.match(ch):
            continue
        while i < len(pat) and DIACRITICS.match(pat[i]):
            i += 1
        if i < len(pat) and pat[i] == ch:
            i += 1
            while i < len(pat) and DIACRITICS.match(pat[i]):
                i += 1
        else:
            return None
    return i


def strip_proclitic(pat: str, proclitic: str) -> tuple:
    """Remove the clitic prefix from the pattern prefix.  Returns (pat, stripped?).

    Alignment, not positional slicing: the letters before digit 1 are ambiguous
    between proclitic and TEMPLATIC (Form X مُسْتَفْعِل), so only the exact clitic
    surface CALIMA reports is removed.

    HARD GUARD: the radical-digit set must be IDENTICAL before and after.  If
    stripping dropped a digit we over-stripped, so we refuse and return the input
    unchanged.  The project's catalogued failure mode is a silent no-op that
    reports success; here a failed strip is an explicit False in the return value.
    """
    if not pat or not proclitic:
        return pat, False
    i = _align_prefix(pat, proclitic)
    if i is None:
        return pat, False
    out = pat[i:]
    if set(DIG.findall(out)) != set(DIG.findall(pat)):
        return pat, False
    return out, True


def _align_suffix(pat: str, suffix: str):
    """Index in `pat` BEFORE `suffix`, matching skeletons RIGHT-to-LEFT.  None if it
    does not align.  Mirror of _align_prefix, for the enclitic side.

    Diacritics are ignored on both sides on purpose: the pattern and `d3tok` do not
    always agree on case vowels — كتابه has pattern '1ِ2ا3ِهِ' (kasra on the ه) while
    d3tok's enclitic is 'هُ' (damma).  The consonant skeleton is what aligns.
    """
    j = len(pat) - 1
    for ch in reversed(suffix):
        if DIACRITICS.match(ch):
            continue
        while j >= 0 and DIACRITICS.match(pat[j]):
            j -= 1
        if j >= 0 and pat[j] == ch:
            j -= 1
        else:
            return None
    return j + 1


def strip_enclitic(pat: str, enclitic: str) -> tuple:
    """Remove the enclitic (pronominal / object suffix) from the RIGHT edge of the
    pattern, so Head 3 predicts the uninflected lexical stem template.

    Grounded exactly like the proclitic strip: the suffix string comes from `d3tok`
    (measured separator '_+' — 'كِتابِ_+هُ', 'مَدْرَسَة_+هُم'), never guessed — the
    same discipline that replaced prc0-prc3 label guessing with surfaces.

    Same HARD GUARD as the proclitic strip: the radical-digit set must be IDENTICAL
    before and after, so a mis-aligned cut is REFUSED, not silently accepted.

    MUST run before _map_missing_slot_literal for the same reason as the proclitic:
    that function rewrites the LAST weak literal, and an enclitic sitting after the
    stem's weak radical would shield it.  Verified: عليهم -> pattern '1َ2َيهِم',
    root ع.ل.#; stripping the enclitic first leaves '1َ2َي', so slot 3 can be
    recovered correctly.
    """
    if not pat or not enclitic:
        return pat, False
    k = _align_suffix(pat, enclitic)
    if k is None or k <= 0:
        return pat, False
    out = pat[:k]
    if set(DIG.findall(out)) != set(DIG.findall(pat)):
        return pat, False
    return out, True


def normalize_from_analysis(a: dict) -> dict:
    """The full Head-3 pipeline over ONE CALIMA analysis dict.

    Composes: strip proclitic -> strip enclitic -> expand geminate (root-gated) ->
    map missing-slot literal -> strip case.  Returns a record rather than a bare
    label so the caller can report WHY a token was dropped instead of losing it.
    """
    pat = a.get("pattern")
    root = a.get("root") or ""
    d3tok = a.get("d3tok") or ""
    enc = has_enclitic(a)
    base = {"render": pat, "proclitic": proclitic_surface(d3tok),
            "proclitic_stripped": False, "enclitic": enc,
            "enclitic_surface": enclitic_surface(d3tok), "enclitic_stripped": False,
            "wellformed": False, "wellformed_strict": False}
    if not pat or pat in ("None", "na", "NTWS", "backoff"):
        return {**base, "label": None, "reason": "no_pattern"}

    prc = base["proclitic"]
    enc_s = base["enclitic_surface"]
    # "stripped" means THE LABEL IS NOW CLITIC-FREE — which is vacuously true when
    # no clitic was present. Reading a no-op as a failure was a real bug: every
    # clitic-free token reported reason='proclitic_not_aligned', which zeroed the
    # Head-3 mask in build_training_jsonl.py (caught by that script's smoke test:
    # wazan coverage came out 15.9% instead of ~54%).
    if prc:
        lab, ok = strip_proclitic(pat, prc)
    else:
        lab, ok = pat, True
    if enc_s:
        lab, enc_ok = strip_enclitic(lab, enc_s)
    else:
        enc_ok = True
    lab = expand_geminate(lab, root)
    lab = _map_missing_slot_literal(lab, root)
    lab = strip_case(lab, root)
    lab = canonicalize_mater_vowels(lab)

    digits = DIG.findall(lab or "")
    if not ok:
        reason = "proclitic_not_aligned"
    elif not enc_ok:
        reason = "enclitic_not_aligned"
    else:
        reason = "ok"
    return {**base, "label": lab, "proclitic_stripped": ok,
            "enclitic_stripped": enc_ok,
            # LOOSE (what the 53.6% figure in the docs used): the digit SET is
            # {1,2,3} or {1,2,3,4}.  Insufficient on its own -- it accepted labels
            # like '1ُ23ا3' produced by the old ungated geminate expansion.
            "wellformed": set(digits) in ({"1", "2", "3"}, {"1", "2", "3", "4"}),
            # STRICT: every radical digit appears EXACTLY ONCE and IN ORDER. Report both so the
            # published loose figure stays comparable; never silently swap a metric.
            "wellformed_strict": digits in (["1", "2", "3"], ["1", "2", "3", "4"]),
            "reason": reason}


def normalize_wazan(pat: str, root: str = "", proclitic: str = "",
                    enclitic: str = "") -> tuple:
    """ORDER: strip proclitic -> strip enclitic -> expand geminate (root-gated) ->
    map missing-slot -> strip case.  Returns (label, render_pattern).

    The clitic arguments are optional and backward compatible: omit them and the
    only behavioural change is the geminate gate (which now needs a confirming root).
    """
    if not pat or pat in ("None", "na"):
        return None, None
    render = pat
    lab, _ = strip_proclitic(pat, proclitic)
    lab, _ = strip_enclitic(lab, enclitic)
    lab = expand_geminate(lab, root)
    lab = _map_missing_slot_literal(lab, root)
    lab = strip_case(lab, root)
    lab = canonicalize_mater_vowels(lab)
    return lab, render


if __name__ == "__main__":
    print("=" * 74)
    print("A. the round-5/6 failure cases")
    print("=" * 74)
    for p, root, note in [
        ("1\u064e2\u064e3\u064f", "", "nominal, damma"),
        ("1\u064e2\u064e3\u064b", "", "tanwin fath"),
        ("1\u064e2\u064e3\u064b\u0627", "", "tanwin fath + alif (orthographic)"),
        ("1\u064e2\u064e\u0627", "\u062f.\u0639.#", "defective: alif IS radical 3"),
        ("1\u064e2\u0627", "\u062f.\u0639.#", "defective, bare alif"),
        ("1\u064e2\u064e\u0649", "\u0645.\u0634.#", "defective: alef maqsura"),
        ("1\u064e2\u064e\u0651", "\u0645.\u062f.\u062f", "geminate"),
        ("1\u064e2\u064f\u0651", "\u0645.\u062f.\u062f", "geminate w/ vowel"),
    ]:
        lab, _ = normalize_wazan(p, root)
        slots = "".join(sorted(set(DIG.findall(lab or ""))))
        print(f"  {p:12} -> {lab!r:14} slots={{{slots}}}  {note}")

    print()
    print("=" * 74)
    print("B. order + garbage guards")
    print("=" * 74)
    print("  lex 'راوَنْد' ->", end=" ")
    try:
        print(extract_clean_lemma("\u0631\u0627\u0648\u064e\u0646\u0652\u062f"))
    except AssertionError as e:
        print("REJECTED:", e)
    print("  lex 'كِتاب'  ->", extract_clean_lemma("\u0643\u0650\u062a\u0627\u0628"))


# ===================== THE BRIDGE — the ONE shared definition (§2cz) ==========================
# Every measurement imports THIS. A private copy in a tool is the bug: two copies disagree exactly
# where it matters, and the instrument then measures a different pipeline than the one that ships.
_TAIL_COMB = frozenset(list(range(0x064B, 0x0653)) + [0x0670])
_TAIL_SHADDA = "\u0651"


def _tail_marks(s):
    m = {}
    for c in s:
        if ord(c) in _TAIL_COMB:
            m[c] = m.get(c, 0) + 1
    return m


def _tail_minus(a, b):
    """Multiset difference a - b (non-positive counts dropped)."""
    r = {}
    for k, v in a.items():
        d = v - b.get(k, 0)
        if d > 0:
            r[k] = d
    return r


def _tail_base(s):
    return "".join(c for c in s if ord(c) not in _TAIL_COMB)


def _tail_stem_shadda(t):
    """A shadda sitting BEFORE the tail's first base letter belongs to the STEM (a doubled final
    radical), not to the tail. A tail with no base letter at all that is only a shadda carries no
    suffix: it collapses to the bare stem."""
    i = next((k for k, c in enumerate(t) if 0x0621 <= ord(c) <= 0x064A or 0x0671 <= ord(c) <= 0x06D3), None)
    if i is None:
        return t.replace(_TAIL_SHADDA, ""), True
    if any(ord(c) == 0x0651 for c in t[:i]):
        return t[:i].replace(_TAIL_SHADDA, "") + t[i:], True
    return t, False


def bridge_stem_tail(tail, inv=None):
    """Resolve an inflectional tail against the class space -> (kind, target, distance, shadda_moved).

    IDENTITY    the tail IS a class. Never moves — this is what makes `broken = 0` structural.
    DETERMINATE exactly ONE nearest candidate, reached by ADDING marks (never deleting one: adding a
                mark the convention spells out is a repair, deleting one is inventing information).
    TIE         two candidates equidistant (mark ORDER differs) -> NO target. The caller must not guess.
    NEW         no candidate at all -> a class of its own, if it is ever observed.
    JUNK        not fully Arabic -> IGNORE.
    BARE        empty tail -> class 0 (bare stem / <pad>).
    """
    inv = STEM_TAIL_VOCALIZED if inv is None else inv
    if not tail:
        return ("BARE", None, 0, False)
    if not all(0x0600 <= ord(c) <= 0x06FF for c in tail):
        return ("JUNK", None, 0, False)
    if tail in inv:                                     # IDENTITY, first and again after stripping
        return ("IDENTITY", tail, 0, False)
    t2, moved = _tail_stem_shadda(tail)
    if t2 == "":
        return ("DETERMINATE", "", 0, moved)
    if t2 in inv:
        return ("DETERMINATE", t2, 0, moved)
    t2m = _tail_marks(t2)
    t2b = _tail_base(t2)
    cands = []
    for i, c in enumerate(inv):
        if _tail_base(c) != t2b:
            continue
        if _tail_minus(t2m, _tail_marks(c)):            # t2's marks must be a SUB-MULTISET
            continue
        cands.append((sum(_tail_minus(_tail_marks(c), t2m).values()), i, c))
    if not cands:
        return ("NEW", None, 0, moved)
    cands.sort()
    tied = [c for c in cands if c[0] == cands[0][0]]
    if len(tied) > 1:
        return ("TIE", [c[2] for c in tied], cands[0][0], moved)
    return ("DETERMINATE", tied[0][2], cands[0][0], moved)


def stem_tail_class_index(tail, inv=None):
    """The class INDEX a tail resolves to in the shipped space, or `STEM_TAIL_IGNORE`.

    NO SILENT DEFAULT. The defect this repairs was `vocab.get(raw_tail, 0)`: class 0 is a MEANINGFUL
    class (the bare stem), so the default taught a confident wrong label with a live gradient.
    """
    inv = STEM_TAIL_VOCALIZED if inv is None else inv
    kind, tgt, _, _ = bridge_stem_tail(tail, inv)
    if kind == "BARE":
        return 0
    if isinstance(tgt, str) and tgt in inv:
        return inv.index(tgt)
    return STEM_TAIL_IGNORE


def stem_tail_target(tail, vocab):
    """Resolve a tail to the MODEL's class id through a {class: id} vocab, or `STEM_TAIL_IGNORE`.

    Use this instead of `vocab.get(tail, 0)` in every data builder. An empty tail is genuinely class 0.
    """
    kind, tgt, _, _ = bridge_stem_tail(tail)
    if kind == "BARE":
        return vocab.get("", 0)
    if isinstance(tgt, str) and tgt in vocab:
        return vocab[tgt]
    return STEM_TAIL_IGNORE
