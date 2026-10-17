"""Weak-radical RE-REALIZATION: (root, wazān pattern) -> surface, with the weak radical
resolved by CONTEXT instead of being dropped.

WHY v2 IS THROWN AWAY (measured, on the 300-row gold)
    v2's hollow rule deleted a weak r2 unconditionally. That is wrong, and the gold says
    so loudly:
        قَوْل  (1َ2ْ3)   ->  قَلُ   ✗        غَيْرِ (1َ2ْ3)  ->  غَرِ  ✗
        لَيْسَ (1َ2ْ3َ)   ->  لَسَ   ✗        كَوْنِ (1َ2ْ3)  ->  كَنِ  ✗
    The template `1َ2ْ3` carries no mater lectionis, so the radical MUST be written. v2
    also lost the shadda's position in الْعَامّ and mis-indexed the madda. v3 keeps v2's
    correct cases (قَالَ, مُحْتَاجٌ, احْتَاطَ, قُلْتُ) and fixes the rest.

THE TWO PASSES THE PLAN ASKED FOR
    PASS A (slot mapping): walk the template. A SOUND radical is written in place. A WEAK
    radical is NOT committed here — it is left as a decision to Pass B.
    PASS B (context reduction): resolve each weak slot from the template's own material:
      · a mater lectionis supplied by the template adjacent to the slot  -> the radical is
        ABSORBED (not written):    1َا2َ3 -> قَالَ   ·  مُ1ْتَا2َ3 -> مُحْتَاجٌ
      · a closed syllable (the next slot carries sukun)                  -> DELETED:
        1ُ2ْ3ْتُ -> قُلْتُ
      · a suffix follows the slot (ـُونَ / ـِينَ / ـُوا)                  -> DELETED
      · otherwise                                                       -> WRITTEN:
        1َ2ْ3 -> قَوْل   ·  1ِ2َا3 -> قِيَاس   ·  1َ2ْ3َيْن -> زَوْجَيْن
    Plus two grounded extras:
      · FINAL HAMZA: a final weak radical absorbed by a word-final alif leaves ء:
        1َ2َا3 -> عَلَاء   ·  1ِ2َا3 -> نِسَاء   ·  إ1ْ2َا3 -> إمْلَاء
      · MADDA: alif onto alif is written آ, replacing the last LETTER (not the last
        character — v2 overwrote the preceding fatha instead, giving قُرْاآنِ).

SCOPE — what this deliberately does NOT do, so the gap is not overstated
    · True ASSIMILATED (r1 = و) deletion — يَعِدُ / اتَّصَلَ — is NOT implemented; only
      ~5 gold rows are genuinely and not hamza-classed, so it is not worth the risk yet.
    · The annotator writes a bare alif for a hamza radical (اله, امر, احد), which
      `root_class` reads as assimilated. Those rows are REALLY hamza-seat cases, and the
      divine name (اللَّه) is its own special form.
    · Nunation is `apply_case`'s business and is untouched here.
"""
from __future__ import annotations

import json
import sys

from final_surface import (candidates, classify_defect, strip_diac as skel, nfc as NFC,
                           apply_clitic_plane)
from paths import GOLD_JSONL
from renderer import render_rule, apply_case, DIAC

WEAK = set("\u0648\u064a")                                  # و ي
MATER = set("\u0627\u0648\u064a\u0649")                     # ا و ي ى
HARAKAT = set("\u064b\u064c\u064d\u064e\u064f\u0650\u0651\u0652\u0670")
SUKUN = "\u0652"
SHADDA = "\u0651"
MADDA, ALIF, HAMZA_ALIF, HAMZA = "\u0622", "\u0627", "\u0623", "\u0621"
SUFFIX_START = ("\u0648\u0646", "\u064a\u0646", "\u0648\u0627")   # ون ين وا


# ----------------------------------------------------------------- helpers
def _last_letter(out: list[str]) -> str:
    for c in reversed(out):
        if c not in HARAKAT:
            return c
    return ""


def _last_letter_idx(out: list[str]) -> int:
    for i in range(len(out) - 1, -1, -1):
        if out[i] not in HARAKAT:
            return i
    return -1


def _nearest_left(pattern: str, i: int) -> str:
    """Nearest non-haraka char to the LEFT of index i (skips harakat). '' if none."""
    j = i - 1
    while j >= 0:
        if pattern[j] not in HARAKAT:
            return pattern[j]
        j -= 1
    return ""


def _nearest_right(pattern: str, i: int) -> str:
    j = i + 1
    while j < len(pattern):
        if pattern[j] not in HARAKAT:
            return pattern[j]
        j += 1
    return ""


def _rest_after(pattern: str, i: int) -> str:
    """Everything after index i with harakat stripped (for suffix detection)."""
    return "".join(c for c in pattern[i + 1:] if c not in HARAKAT)


def _closed_syllable(pattern: str, i: int) -> bool:
    """True when this slot is followed by a haraka and the NEXT slot carries sukun.

    1ُ2ْ3ْتُ -> قُلْتُ : slot 2 is followed by sukun and slot 3 by sukun -> closed.
    1َ2ْ3   -> قَوْل  : slot 2 is followed by sukun but slot 3 is terminal -> NOT closed.
    """
    j = i + 1
    if j >= len(pattern) or pattern[j] not in HARAKAT:
        return False
    k = j
    while k < len(pattern) and pattern[k] not in "1234":
        k += 1
    if k >= len(pattern):
        return False
    return k + 1 < len(pattern) and pattern[k + 1] == SUKUN


def _consume(pattern: str, i: int) -> int:
    """Index after skipping position i, taking its haraka with it — EXCEPT a shadda.

    The radical's OWN vowel belongs to it, so it goes too: leaving it behind turned
    قَالَ into قَاَل and مُحْتَاجٌ into مُحْتَاَجُ (both real, both caught here).

    A shadda is different — in these templates it is written after the weak slot but
    applies to the FOLLOWING consonant (الْعَامّ writes it after the deleted و but it sits
    on م), so it is left in place for the next letter.
    """
    j = i + 1
    while j < len(pattern) and pattern[j] in HARAKAT and pattern[j] != SHADDA:
        j += 1
    return j


# ----------------------------------------------------------------- the renderer
def render_v2(root: str | None, pattern: str | None):
    """ARCHIVED — KNOWN WRONG ON HOLLOW ROOTS. Kept ONLY so the regression stays visible.

    It deletes a weak r2 UNCONDITIONALLY, so قَوْل -> قَلُ and غَيْر -> غَرِ, and it
    mis-indexes the madda onto the preceding fatha (قُرْاآنِ). Superseded by render_v3;
    never use it as an engine. Its one virtue is that it is the honest record of what the
    "evaluate the pattern context" step looks like when the context is NOT evaluated.
    """
    rads = [c for c in (root or "") if c not in ". "]
    if not pattern or not rads:
        return None, "no_pattern" if pattern is None else "no_root"
    if "#" in rads:
        return None, "no_root"
    digits = [c for c in pattern if c in "1234"]
    ds = set(digits)
    if ds not in ({"1", "2", "3"}, {"1", "2", "3", "4"}):
        return None, "digit_set_incomplete"
    if len(digits) != len(ds):
        return None, "repeated_digit"
    if len(rads) != len(ds):
        return None, "root_len_mismatch"
    slot = {int(k): r for k, r in zip(sorted(ds), rads)}
    hollow = len(rads) >= 3 and rads[1] in WEAK
    chars, out, i, n = list(pattern), [], 0, len(pattern)
    while i < n:
        ch = chars[i]
        if ch in "1234":
            k, r = int(ch), slot[int(ch)]
            nxt = next((c for c in chars[i + 1:] if c not in HARAKAT), "")
            if k == 2 and hollow:
                i += 1
                if i < n and chars[i] in HARAKAT:
                    i += 1
                continue
            if r in WEAK and nxt in MATER and _last_letter(out) != nxt:
                i += 1
                continue
            if _last_letter(out) == r:
                i += 1
                continue
            if _last_letter(out) == ALIF and r == ALIF:
                out[-1] = MADDA
                i += 1
                continue
            if k == 1 and r == ALIF and not _last_letter(out):
                r = HAMZA_ALIF
            out.append(r)
            i += 1
            continue
        if ch == ALIF and _last_letter(out) == ALIF:
            out[-1] = MADDA
        else:
            out.append(ch)
        i += 1
    return "".join(out), "ok"


def render_v3(root: str | None, pattern: str | None, trace: list[dict] | None = None):
    """Weak-radical re-realization. Same abstention contract as render_rule."""
    from wazan_normalizer import canonicalize_mater_vowels
    pat_raw = pattern
    pattern = canonicalize_mater_vowels(pattern)
    if trace is not None and pat_raw is not None:
        trace.append({
            "stage": "wazan_canonicalization",
            "rule_id": "canonicalize_mater_vowels",
            "before": pat_raw,
            "after": pattern,
            "changed": pat_raw != pattern,
        })
    rads = [c for c in (root or "") if c not in ". "]
    if not pattern or not rads:
        return None, "no_pattern" if pattern is None else "no_root"
    if "#" in rads:
        return None, "no_root"
    digits = [c for c in pattern if c in "1234"]
    ds = set(digits)
    if ds not in ({"1", "2", "3"}, {"1", "2", "3", "4"}):
        return None, "digit_set_incomplete"
    if len(digits) != len(ds):
        return None, "repeated_digit"
    if len(rads) != len(ds):
        return None, "root_len_mismatch"
    slot = {int(k): r for k, r in zip(sorted(ds), rads)}
    last_slot = max(slot)
    pos_of = {int(ch): idx for idx, ch in enumerate(pattern) if ch in "1234"}

    def _absorbed_geminate(k: int) -> bool:
        """True when slot `k` must NOT write its letter because the template already
        geminated the PREVIOUS slot's identical radical.

        THE REGRESSION THIS FIXES (measured 2026-10-12, commit 6746f13):
            ح.ص.ص + 1ِ2ّ3َة -> حِصّصَةُ   (want حِصَّة)      الْبَزِّ -> بَزّزِ
            السُّرَّةِ -> سُرّرَةِ        تَمَسُّوهُنَّ -> تَمَسّسُوا
        Pass A copies the shadda it walks past, then the sound branch wrote the second
        radical as well, so the consonant appeared twice. v2 had this dedup; v3 dropped it
        and lost 10.1 pp on doubled roots (36.2% -> 26.1%).

        THREE conditions, all required, so the rule cannot over-fire:
          1. the previous slot exists and holds the SAME letter (a geminate ROOT, not a
             letter coincidence — e.g. تَتَبُّع, root ت.ب.ع + تَ1َ2ُّ3, writes BOTH ت's and
             must keep doing so);
          2. a SHADDA lies between the two slots in the template — that mark IS the
             doubling, so the second letter is already represented;
          3. the shadda has already been copied into `out` — guaranteed, since Pass A
             walks left to right and pos_of[k-1] < pos_of[k].
        """
        if k <= 1 or slot.get(k) != slot.get(k - 1):
            return False
        lo, hi = pos_of.get(k - 1), pos_of.get(k)
        if lo is None or hi is None:
            return False
        return SHADDA in pattern[lo:hi]

    out: list[str] = []
    # ---------- PASS A: slot mapping (weak slots deferred) ----------
    i, n = 0, len(pattern)
    while i < n:
        ch = pattern[i]
        if ch not in "1234":
            if ch == ALIF and _last_letter(out) == ALIF:      # MADDA, on the last LETTER
                out[_last_letter_idx(out)] = MADDA
            else:
                out.append(ch)
            i += 1
            continue

        k, r = int(ch), slot[int(ch)]

        # ---------- PASS B: reduce this slot ----------
        if r in WEAK:
            tleft = _nearest_left(pattern, i)
            tright = _nearest_right(pattern, i)

            # (1) hollow: the template already carries the mater
            if k == 2 and tleft in MATER:
                if trace is not None:
                    trace.append({"stage": "renderer", "rule_id": "hollow_mater_absorption",
                                  "before": "".join(out) + r, "after": "".join(out), "changed": True})
                i = _consume(pattern, i)
                continue
            # (2) hollow: closed syllable -> the glide cannot stand
            if k == 2 and _closed_syllable(pattern, i):
                if trace is not None:
                    trace.append({"stage": "renderer", "rule_id": "hollow_closed_syllable",
                                  "before": "".join(out) + r, "after": "".join(out), "changed": True})
                i = _consume(pattern, i)
                continue
            # (3) defective r3: suffix (ـُونَ/ـِينَ/ـُوا) -> elided
            if k == last_slot and _rest_after(pattern, i).startswith(SUFFIX_START):
                if trace is not None:
                    trace.append({"stage": "renderer", "rule_id": "defective_r3_suffix_elision",
                                  "before": "".join(out) + r, "after": "".join(out), "changed": True})
                i = _consume(pattern, i)
                continue
            # (4) defective r3: absorbed by a mater the template supplies
            if k == last_slot and (tleft in MATER or tright in MATER):
                if trace is not None:
                    trace.append({"stage": "renderer", "rule_id": "defective_r3_mater_absorption",
                                  "before": "".join(out) + r,
                                  "after": "".join(out) + (HAMZA if (not _rest_after(pattern, i) and _last_letter(out) == ALIF) else ""),
                                  "changed": True})
                i = _consume(pattern, i)
                # FINAL HAMZA: an absorbed final radical leaves a word-final alif as اء
                if not _rest_after(pattern, i) and _last_letter(out) == ALIF:
                    out.append(HAMZA)
                continue
            # (5) defective r3, terminal, nothing to carry it -> ا (و) / ى (ي)
            if k == last_slot and not _rest_after(pattern, i):
                term_c = ALIF if r == "\u0648" else "\u0649"
                if trace is not None:
                    trace.append({"stage": "renderer", "rule_id": "defective_r3_terminal",
                                  "before": "".join(out) + r, "after": "".join(out) + term_c, "changed": r != term_c})
                out.append(term_c)
                i += 1
                continue
            # (6) otherwise WRITE the radical
            out.append(r)
            i += 1
            continue

        # sound / hamza / alif radical: written in place — UNLESS the template already
        # geminated it (see _absorbed_geminate above; this is the v3 doubled-root regression)
        if _absorbed_geminate(k):
            if trace is not None:
                trace.append({"stage": "renderer", "rule_id": "geminate_absorption",
                              "before": "".join(out) + r, "after": "".join(out), "changed": True})
            i += 1
            continue
        if r == ALIF and _last_letter(out) == ALIF:
            out[_last_letter_idx(out)] = MADDA
        elif r == ALIF and k == 1 and not _last_letter(out):
            out.append(HAMZA_ALIF)                  # bare-alif first radical, word-initial
        else:
            out.append(r)
        i += 1
    res = "".join(out)
    if trace is not None:
        trace.append({
            "stage": "renderer",
            "rule_id": "render_v3",
            "before": pattern,
            "after": res,
            "changed": pattern != res,
        })
    return res, "ok"


# ------------------------------------------------------------------- registry
# `final_surface.render_triple` dispatches through THIS dict. Adding a rule version means
# adding it here and nowhere else.
#
# NOTE: this registry was added to reconcile a CONCURRENT EDIT — `final_surface.py` was
# changed (outside this session) to dispatch `ENGINES[engine]` with "v3" as the default
# while no ENGINES existed, which raised ImportError on every render. The registry satisfies
# that dispatch without discarding it. `render_v2` stays registered on purpose: it is the
# documented WRONG version, and leaving it reachable is what keeps the regression visible.
ENGINES = {"v2": render_v2, "v3": render_v3}


def main() -> int:
    rows = [json.loads(l) for l in open(GOLD_JSONL, encoding="utf-8") if l.strip()]
    usable = [r for r in rows if r.get("t_root_arabic") and r.get("t_wazan_pattern")]

    import eval_harness as EH
    WEAK_CLASSES = {"hollow", "defective", "assimilated"}
    TRUE_WEAK = lambda rt: any(c in "\u0648\u064a" for c in rt)   # a real و/ي radical

    def weak(r):
        return EH.root_class(r["t_root_arabic"]) in WEAK_CLASSES

    weak_rows = [r for r in usable if weak(r)]
    true_weak = [r for r in usable if TRUE_WEAK(r["t_root_arabic"])]

    print("=" * 88)
    print("WEAK-RADICAL RE-REALIZATION — v1 vs v2 (unconditional deletion) vs v3 (context)")
    print("=" * 88)
    print(f"gold rows {len(rows)} · usable {len(usable)}")
    print(f"weak by root_class (hollow+defective+assimilated): {len(weak_rows)}")
    print(f"  of which hollow {sum(1 for r in weak_rows if EH.root_class(r['t_root_arabic'])=='hollow')}"
          f" · defective {sum(1 for r in weak_rows if EH.root_class(r['t_root_arabic'])=='defective')}"
          f" · assimilated {sum(1 for r in weak_rows if EH.root_class(r['t_root_arabic'])=='assimilated')}")
    print(f"roots that ACTUALLY contain و/ي anywhere      : {len(true_weak)}")
    print()

    engines = {"v1": render_rule, "v2": render_v2, "v3": render_v3}

    def score(fn, rows_):
        ok = 0
        for r in rows_:
            got, _ = fn(r["t_root_arabic"], r["t_wazan_pattern"])
            if got is None:
                continue
            if candidates(r["form"]) and any(
                    NFC(c) == NFC(apply_clitic_plane(apply_case(got, r.get("t_case")), r["form"]))
                    for c in candidates(r["form"])):
                ok += 1
        return ok

    hdr = f"{'subset':<28} {'n':>4} " + " ".join(f"{e:>8}" for e in engines)
    print(hdr)
    for name, subset in (("ALL usable", usable), ("weak (root_class)", weak_rows),
                         ("true weak (has و/ي)", true_weak)):
        cells = " ".join(f"{score(fn, subset):>8}" for fn in engines.values())
        print(f"{name:<28} {len(subset):>4} {cells}")
    print()
    print("  v2's unconditional deletion is the regression: it clears the rows whose template")
    print("  supplies a mater and BREAKS every row where the radical must be written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
