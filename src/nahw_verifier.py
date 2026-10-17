#!/usr/bin/env python3
"""src/nahw_verifier.py — Deterministic Syntactic & Morphological Constraint Verifier.

Implements the 8 core pedagogical counterfactual checks for the Arabic Sentence Sandbox:
  1. CHECK_AL_TANWIN_CLASH: Definiteness prefix 'الـ' and tanwīn are mutually exclusive.
  2. CHECK_PREP_GENITIVE: Prepositions ('حروف الجر') force genitive case (Majrūr).
  3. CHECK_VERB_VALENCY_AND_FAIL: Active verb requires identifiable Fāʿil (flags MISSING_FAIL, DOUBLE_FAIL_COLLISION).
  4. CHECK_PASSIVE_NAIB_FAIL: Passive verb requires Nominative deputy subject (Nāʾib al-Fāʿil).
  5. CHECK_SVO_VSO_AGREEMENT: VSO singular verb agreement vs SVO number/gender matched agreement.
  6. CHECK_IDAFAH_CHAIN: Muḍāf drops tanwīn and 'الـ', Muḍāf ilayhi must be Majrūr (GEN).
  7. CHECK_SOUND_PLURAL_INFLECTION: Sound masc. plural (ـُونَ / ـِينَ) and sound fem. plural (ـَاتِ in ACC/GEN).
  8. CHECK_INNA_KANA_GOVERNMENT: Inna assigns ACC to Ism and NOM to Khabar; Kāna assigns NOM to Ism and ACC to Khabar.

Zero-ML, deterministic, Linus Torvalds standard: Clean, readable, bullet-proof.
"""
from __future__ import annotations

import io
import re
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

# Ensure UTF-8 output on Windows consoles
if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8")

HARAKAT = "\u064b\u064c\u064d\u064e\u064f\u0650\u0651\u0652\u0670"
TANWIN = "\u064b\u064c\u064d"  # ً ٌ ٍ


def strip_tashkeel(s: str | None) -> str:
    """Strip all Arabic short vowels, sukun, tanwīn, and shadda."""
    if not s:
        return ""
    return re.sub(r"[\u064b-\u0652\u0670]", "", s)


# ---------------------------------------------------------------------------
# CONSTANTS & LEXICAL INVENTORIES
# ---------------------------------------------------------------------------

PREPOSITIONS: set[str] = {
    "في", "فِي",
    "إلى", "إِلَى",
    "على", "عَلَى",
    "من", "مِنْ", "مِنَ",
    "عن", "عَنْ", "عَنِ",
    "حتى", "حَتَّى",
    "منذ", "مُنْذُ",
    "مذ", "مُذْ",
    "رب", "رُبَّ",
}

PREP_PROCLITICS: set[str] = {"بِ", "بِـ", "لِ", "لِـ", "كَ", "كَـ"}

INNA_SISTERS: set[str] = {
    "إن", "إِنَّ",
    "أن", "أَنَّ",
    "كأن", "كَأَنَّ",
    "لكن", "لَكِنَّ",
    "ليت", "لَيْتَ",
    "لعل", "لَعَلَّ",
}

KANA_SISTERS: set[str] = {
    "كان", "كَانَ", "كَانَتْ", "كَانُوا",
    "أصبح", "أَصْبَحَ", "أَصْبَحَتْ",
    "أمسى", "أَمْسَى", "أَمْسَتْ",
    "ظل", "ظَلَّ", "ظَلَّتْ",
    "بات", "بَاتَ", "بَاتَتْ",
    "صار", "صَارَ", "صَارَتْ",
    "ليس", "لَيْسَ", "لَيْسَتْ",
    "ما زال", "مَا زَالَ",
}

CONJUNCTIONS: set[str] = {"و", "وَ", "ف", "فَ", "ثم", "ثُمَّ", "أو", "أَوْ"}

COMMON_KNOWN_VERBS: set[str] = {
    "نصر", "نَصَرَ", "نُصِرَ", "يَنْصُرُ", "يُنْصَرُ",
    "ضرب", "ضَرَبَ", "ضُرِبَ", "يَضْرِبُ", "يُضْرَبُ",
    "علم", "عَلِمَ", "عُلِمَ", "يَعْلَمُ", "يُعْلَمُ",
    "كتب", "كَتَبَ", "كُتِبَ", "يَكْتُبُ", "يُكْتَبُ",
    "قرا", "قرأ", "قَرَأَ", "قُرِئَ", "يَقْرَأُ", "يُقْرَأُ",
    "ذهب", "ذَهَبَ", "يَذْهَبُ",
    "قال", "قَالَ", "قِيلَ", "يَقُولُ", "يُقَالُ", "قُلْتُ",
    "رقد", "رَقَدَ", "يَرْقُدُ",
    "حمد", "حَمِدَ", "حُمِدَ", "يَحْمَدُ", "يُحْمَدُ",
    "أكل", "أَكَلَ", "أُكِلَ", "يَأْكُلُ", "يُؤْكَلُ",
    "شرب", "شَرِبَ", "شُرِبَ", "يَشْرَبُ", "يُشْرَبُ",
    "فتح", "فَتَحَ", "فُتِحَ", "يَفْتَحُ", "يُفْتَحُ",
    "خلق", "خَلَقَ", "خُلِقَ", "يَخْلُقُ", "يُخْلَقُ",
    "عرف", "عَرَفَ", "عُرِفَ", "يَعْرِفُ", "يُعْرَفُ",
    "سمع", "سَمِعَ", "سُمِعَ", "يَسْمَعُ", "يُسْمَعُ",
    "وجد", "وَجَدَ", "وُجِدَ", "يَجِدُ", "يُوجَدُ",
    "طهر", "طَهَّرَ", "طُهِّرَ", "يُطَهِّرُ",
    "قلد", "قَلَّدَ", "قُلِّدَ", "يُقَلِّدُ",
    "فرق", "فَرَّقَ", "فُرِّقَ", "يُفَرِّقُ",
    "طاف", "طَافَ", "يَطُوفُ",
}


# ---------------------------------------------------------------------------
# DATA STRUCTURES
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Violation:
    code: str
    tile_indices: list[int]
    rule_name_ar: str
    rule_name_en: str
    message_ar: str
    message_en: str
    broken_meaning_preview: str
    severity: str = "ERROR"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GovernorArrow:
    from_idx: int
    to_idx: int
    relation: str
    description_ar: str
    description_en: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ClauseAnalysis:
    clause_type: str
    verb_idx: int | None = None
    subject_idx: int | None = None
    subject_source: str | None = None
    object_indices: list[int] = field(default_factory=list)
    predicate_idx: int | None = None
    prep_phrase_indices: list[tuple[int, int]] = field(default_factory=list)
    idafah_pairs: list[tuple[int, int]] = field(default_factory=list)


@dataclass
class VerificationResult:
    is_valid: bool
    violations: list[Violation]
    clauses: list[ClauseAnalysis]
    governor_arrows: list[dict[str, Any]]
    annotated_tiles: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "violations": [v.to_dict() for v in self.violations],
            "governor_arrows": self.governor_arrows,
            "clauses": [asdict(c) for c in self.clauses],
            "annotated_tiles": self.annotated_tiles,
        }


# ---------------------------------------------------------------------------
# TILE PARSING & NORMALIZATION
# ---------------------------------------------------------------------------

def parse_tile(tile_input: dict[str, Any] | str, index: int) -> dict[str, Any]:
    """Normalize and enrich user tile representation."""
    if isinstance(tile_input, str):
        t: dict[str, Any] = {"surface": tile_input}
    else:
        t = dict(tile_input)

    surface = str(t.get("surface", "")).strip()
    bare = strip_tashkeel(surface)

    # 1. Closed-class POS detection must run FIRST to avoid treating root letters as proclitics
    pos = t.get("pos")
    if pos is None:
        if surface in PREPOSITIONS or bare in PREPOSITIONS:
            pos = "PREP"
        elif surface in INNA_SISTERS or bare in INNA_SISTERS:
            pos = "INNA"
        elif surface in KANA_SISTERS or bare in KANA_SISTERS:
            pos = "KANA"
        elif surface in CONJUNCTIONS or bare in CONJUNCTIONS:
            pos = "CONJ"
        else:
            # If word starts with definite article 'الـ', it is unconditionally a NOUN
            if (
                surface.startswith("ال") or bare.startswith("ال") or
                bare.startswith("بال") or bare.startswith("كال") or
                bare.startswith("وال") or bare.startswith("فال") or bare.startswith("لل")
            ):
                pos = "NOUN"
            else:
                # Check verb endings/indicators
                has_verb_suffix = (
                    surface.endswith("ُوا") or bare.endswith("وا") or
                    surface.endswith("ْتُ") or surface.endswith("ْتَ") or
                    surface.endswith("ْتِ") or surface.endswith("ْنَا") or
                    surface.endswith("ْتُمْ") or surface.endswith("ْتُنَّ") or
                    surface.endswith("ْنَ")
                )
                wazan = str(t.get("wazan") or "")
                is_verb_wazan = (
                    wazan.startswith("1") or wazan.startswith("ي") or wazan.startswith("ت") or
                    wazan.startswith("أ") or wazan.startswith("اِ") or wazan.startswith("اُ")
                ) and any(w in wazan for w in ("َ", "ِ", "ُ", "ْ")) and not any(
                    wazan.startswith(nom) for nom in ("مَ1", "مِ1", "مُ1", "1ِ2َا3", "1ُ2ُو3", "1َ2ِي3", "1َا2ِ3")
                )
                vowels_in_surface = [ch for ch in surface if ch in "\u064b\u064c\u064d\u064e\u064f\u0650\u0652"]
                is_3letter_vocalized_verb = (
                    len(bare) == 3 and len(vowels_in_surface) >= 2 and
                    not surface.startswith("ال") and not any(ch in TANWIN for ch in surface) and
                    (
                        (vowels_in_surface[0] == "\u064e" and (surface.endswith("\u064e") or surface[-2:] == "\u064e\u0651")) or
                        (vowels_in_surface[0] == "\u064f" and vowels_in_surface[1] == "\u0650")
                    )
                )
                is_known_verb = (
                    bare in COMMON_KNOWN_VERBS or surface in COMMON_KNOWN_VERBS or
                    is_3letter_vocalized_verb or
                    any(bare.startswith(v) and len(bare) <= len(v) + 3 for v in (
                        "نصر", "ضرب", "علم", "كتب", "قرا", "قرأ", "ذهب", "قال", "رقد", "حمد",
                        "أكل", "شرب", "فتح", "خلق", "عرف", "سمع", "وجد", "طهر", "قلد", "فرق", "طاف", "راي", "رأي"
                    ))
                )
                if has_verb_suffix or is_verb_wazan or is_known_verb:
                    pos = "VERB"
                else:
                    pos = "NOUN"

    # 2. Proclitic detection (ONLY for non-closed-class words)
    proclitic = t.get("proclitic")
    if proclitic is None and pos not in ("PREP", "INNA", "KANA", "CONJ"):
        bare_stem_root = bare.rstrip("ا")
        if surface.startswith("الْ") or surface.startswith("ال"):
            proclitic = "الـ"
        elif (surface.startswith("بِال") or surface.startswith("بِالْ") or (any(surface.startswith(p) for p in ("بِـ", "بِ")) and len(bare) > 2 and bare_stem_root not in ("بيت", "باب", "بلد", "بنت", "بحر", "بين", "خبز"))):
            proclitic = "بِـ"
        elif (surface.startswith("لِل") or (any(surface.startswith(p) for p in ("لِـ", "لِ")) and len(bare) > 2 and bare_stem_root not in ("ليس", "ليل", "لحم", "لبن", "لسان"))):
            proclitic = "لِـ"
        elif (surface.startswith("كَال") or surface.startswith("كَالْ") or surface.startswith("كَـ")):
            proclitic = "كَـ"
        elif (surface.startswith("وَال") or surface.startswith("وَالْ") or (surface.startswith("وَ") and len(bare) > 2 and bare_stem_root not in ("ولد", "ورد", "وزير", "وحيد", "وقت", "وجه", "وطن"))):
            proclitic = "وَ"

    # 3. Definiteness detection
    definiteness = t.get("definiteness")
    if definiteness is None:
        if (
            proclitic == "الـ" or surface.startswith("ال") or
            bare.startswith("ال") or bare.startswith("بال") or bare.startswith("كال") or
            bare.startswith("وال") or bare.startswith("فال") or bare.startswith("لل")
        ):
            definiteness = "definite"
        elif any(ch in TANWIN for ch in surface):
            definiteness = "indefinite_tanwin"
        else:
            definiteness = "indefinite_bare"

    # 4. Case detection
    user_case = t.get("user_case")
    tail_chars = surface[-4:] if len(surface) >= 4 else surface
    has_tanwin_damm = "\u064c" in tail_chars
    has_tanwin_fath = "\u064b" in tail_chars
    has_tanwin_kasr = "\u064d" in tail_chars

    last_vowel = None
    for ch in reversed(tail_chars):
        if ch in ("\u064c", "\u064b", "\u064d"):
            break
        if ch in ("\u064f", "\u064e", "\u0650", "\u0652"):
            last_vowel = ch
            break

    has_damma = (last_vowel == "\u064f") or has_tanwin_damm
    has_fatha = (last_vowel == "\u064e") or has_tanwin_fath
    has_kasra = (last_vowel == "\u0650") or has_tanwin_kasr
    has_sukun = (last_vowel == "\u0652")

    is_sound_masc_plural = False
    is_sound_fem_plural = False
    is_dual = False
    tail = t.get("tail")

    if pos != "VERB":
        if bare.endswith("ون") or surface.endswith("ُونَ"):
            is_sound_masc_plural = True
            tail = tail or "ُونَ"
            user_case = user_case or "NOM"
        elif (bare.endswith("ين") or surface.endswith("ِينَ") or surface.endswith("َيْنِ")) and bare not in ("عين", "حين", "طين", "دين", "يمين"):
            if surface.endswith("َيْنِ") or (bare.endswith("ين") and t.get("is_dual")):
                is_dual = True
                tail = tail or "َيْنِ"
                user_case = user_case or "ACC_OR_GEN"
            else:
                is_sound_masc_plural = True
                tail = tail or "ِينَ"
                user_case = user_case or "ACC_OR_GEN"
        elif surface.endswith("َانِ") or (t.get("is_dual") and bare.endswith("ان")):
            is_dual = True
            tail = tail or "َانِ"
            user_case = user_case or "NOM"
        elif bare.endswith("ات") or "َات" in surface:
            is_sound_fem_plural = True
            tail = tail or "َات"
            if has_damma:
                user_case = user_case or "NOM"
            elif has_kasra:
                user_case = user_case or "ACC_OR_GEN"
            elif has_fatha:
                user_case = user_case or "ACC_INVALID_FATHA"

        if user_case is None:
            if has_damma:
                user_case = "NOM"
            elif has_fatha:
                user_case = "ACC"
            elif has_kasra:
                user_case = "GEN"
            elif has_sukun:
                user_case = "JUSS"

    # 5. Verb Voice and attached pronoun analysis
    is_passive_verb = False
    is_active_verb = False
    attached_subject_pronoun: str | None = None

    if pos == "VERB":
        wazan = str(t.get("wazan") or "")
        vowels_in_surface = [ch for ch in surface if ch in "\u064b\u064c\u064d\u064e\u064f\u0650\u0652"]
        is_past_passive = len(vowels_in_surface) >= 2 and vowels_in_surface[0] == "\u064f" and vowels_in_surface[1] == "\u0650"
        is_pres_passive = len(vowels_in_surface) >= 3 and vowels_in_surface[0] == "\u064f" and vowels_in_surface[1] == "\u0652" and vowels_in_surface[2] == "\u064e"
        is_hollow_passive = bare in ("قيل", "بيع") or "1ِي3" in wazan

        if (
            is_past_passive or is_pres_passive or is_hollow_passive or
            "1ُ2ِ3" in wazan or "يُ1ْ2َ3" in wazan or "1ُ2ِّ3" in wazan or
            "أُ1ْ2ِ3" in wazan or "اُ1ْتُ" in wazan or "اُسْتُ" in wazan or
            surface.startswith("نُصِ") or surface.startswith("ضُرِ") or
            surface.startswith("كُتِ") or surface.startswith("عُلِ") or
            surface.startswith("قُرِ") or surface.startswith("أُكِ") or
            surface.startswith("فُتِ") or surface.startswith("خُلِ") or
            surface.startswith("حُمِ") or surface.startswith("قِي")
        ):
            is_passive_verb = True
        else:
            is_active_verb = True

        # Check attached subject pronoun suffixes
        for sfx in ("ْتُ", "ْتَ", "ْتِ", "ْنَا", "ْتُمْ", "ْتُنَّ", "ُوا", "ْنَ", "َا"):
            if surface.endswith(sfx) or (tail and tail == sfx) or (sfx == "ُوا" and bare.endswith("وا")):
                attached_subject_pronoun = sfx
                tail = tail or sfx
                break


    return {
        "index": index,
        "surface": surface,
        "bare": bare,
        "root": t.get("root"),
        "wazan": t.get("wazan"),
        "tail": tail,
        "proclitic": proclitic,
        "definiteness": definiteness,
        "user_case": user_case,
        "pos": pos,
        "is_active_verb": is_active_verb,
        "is_passive_verb": is_passive_verb,
        "attached_subject_pronoun": attached_subject_pronoun,
        "is_sound_masc_plural": is_sound_masc_plural,
        "is_sound_fem_plural": is_sound_fem_plural,
        "is_dual": is_dual,
        "has_tanwin": any(ch in TANWIN for ch in surface) or definiteness == "indefinite_tanwin",
        "gloss": t.get("gloss"),
    }


# ---------------------------------------------------------------------------
# THE 8 NAḤW CONSTRAINT CHECKS
# ---------------------------------------------------------------------------

def verify_sentence(tiles_input: Sequence[dict[str, Any] | str]) -> VerificationResult:
    """Run all 8 deterministic syntactic and morphological constraint checks."""
    tiles = [parse_tile(t, idx) for idx, t in enumerate(tiles_input)]
    violations: list[Violation] = []
    arrows: list[dict[str, Any]] = []
    clauses: list[ClauseAnalysis] = []

    if not tiles:
        return VerificationResult(
            is_valid=True,
            violations=[],
            clauses=[],
            governor_arrows=[],
            annotated_tiles=[],
        )

    # -----------------------------------------------------------------------
    # CHECK 1: CHECK_AL_TANWIN_CLASH
    # -----------------------------------------------------------------------
    for t in tiles:
        has_al = (
            t["proclitic"] == "الـ" or
            t["surface"].startswith("ال") or
            t["bare"].startswith("ال") or
            t["bare"].startswith("بال") or
            t["bare"].startswith("كال") or
            t["bare"].startswith("وال") or
            t["bare"].startswith("فال") or
            t["bare"].startswith("لل") or
            t["definiteness"] == "definite"
        )
        has_tanwin = t["has_tanwin"] or any(ch in TANWIN for ch in t["surface"])
        if has_al and has_tanwin:
            violations.append(
                Violation(
                    code="CHECK_AL_TANWIN_CLASH",
                    tile_indices=[t["index"]],
                    rule_name_ar="تناقض التعريف والتنوين",
                    rule_name_en="Definiteness + Tanwīn Clash",
                    message_ar="لا يجتمع التنوين مع (أل) التعريف في كلمة واحدة مطلقاً؛ التنوين علامة التنكير وأل علامة التعريف.",
                    message_en=f"Definiteness clash on '{t['surface']}': The prefix 'الـ' ('the') and tanwīn ('a/an') are mutually exclusive.",
                    broken_meaning_preview=f"Cannot simultaneously be 'the {t['bare']}' and 'a {t['bare']}'.",
                )
            )

    # -----------------------------------------------------------------------
    # CHECK 2: CHECK_PREP_GENITIVE
    # -----------------------------------------------------------------------
    for i, t in enumerate(tiles):
        # Case A: Separate preposition token
        if t["pos"] == "PREP" and i + 1 < len(tiles):
            next_t = tiles[i + 1]
            if next_t["pos"] in ("NOUN", "VERB"):
                c = next_t["user_case"]
                is_gen = (c == "GEN" or c == "ACC_OR_GEN")
                if not is_gen:
                    violations.append(
                        Violation(
                            code="CHECK_PREP_GENITIVE",
                            tile_indices=[t["index"], next_t["index"]],
                            rule_name_ar="مخالفة عمل حرف الجر",
                            rule_name_en="Preposition Government Violation",
                            message_ar=f"حرف الجر '{t['surface']}' يوجب جرّ الاسم بعده بالكسرة أو الياء؛ وورد '{next_t['surface']}' غير مجرور.",
                            message_en=f"Preposition '{t['surface']}' governs '{next_t['surface']}' into the Genitive case (Majrūr with kasrah/yā'), but received {c or 'non-genitive'}.",
                            broken_meaning_preview=f"{t['surface']} [broken government: {next_t['surface']} is not genitive].",
                        )
                    )
                else:
                    arrows.append(
                        GovernorArrow(
                            from_idx=t["index"],
                            to_idx=next_t["index"],
                            relation="JAR_MAJRUR",
                            description_ar=f"حرف الجر '{t['surface']}' جرّ الاسم '{next_t['surface']}'",
                            description_en=f"Preposition '{t['surface']}' governs '{next_t['surface']}' into Genitive",
                        ).to_dict()
                    )

        # Case B: Prepositional proclitic attached to noun (e.g. بِـ, لِـ, كَـ)
        if t["proclitic"] in PREP_PROCLITICS:
            c = t["user_case"]
            is_gen = (c == "GEN" or c == "ACC_OR_GEN")
            if not is_gen:
                violations.append(
                    Violation(
                        code="CHECK_PREP_GENITIVE",
                        tile_indices=[t["index"]],
                        rule_name_ar="مخالفة عمل حرف الجر المتصل",
                        rule_name_en="Preposition Proclitic Government Violation",
                        message_ar=f"حرف الجر المتصل '{t['proclitic']}' يوجب جر الاسم بالكسرة أو الياء؛ وورد '{t['surface']}' غير مجرور.",
                        message_en=f"Attached preposition '{t['proclitic']}' requires Genitive case (Majrūr with kasrah/yā') on '{t['surface']}', but received {c or 'non-genitive'}.",
                        broken_meaning_preview=f"[broken preposition government on {t['surface']}].",
                    )
                )

    # -----------------------------------------------------------------------
    # CHECK 7: CHECK_SOUND_PLURAL_INFLECTION
    # -----------------------------------------------------------------------
    for i, t in enumerate(tiles):
        # 1. Sound masculine plural: ـُونَ (NOM) vs ـِينَ (ACC/GEN)
        if t["is_sound_masc_plural"]:
            is_after_prep = (i > 0 and tiles[i - 1]["pos"] == "PREP") or (t["proclitic"] in PREP_PROCLITICS)
            if is_after_prep and (t["surface"].endswith("ُونَ") or t["user_case"] == "NOM"):
                violations.append(
                    Violation(
                        code="CHECK_SOUND_PLURAL_INFLECTION",
                        tile_indices=[t["index"]],
                        rule_name_ar="خطأ إعراب جمع المذكر السالم",
                        rule_name_en="Sound Masculine Plural Inflection Error",
                        message_ar=f"جمع المذكر السالم '{t['surface']}' ورد بالواو والنون في موضع جر؛ وواجب جره بالياء والنون (ـِينَ).",
                        message_en=f"Sound masculine plural '{t['surface']}' uses Nominative '-ūna' in Genitive position; must be '-īna'.",
                        broken_meaning_preview=f"{t['surface']} [inflection error: nominative plural in genitive slot].",
                    )
                )

        # 2. Sound feminine plural: ـَات with fatḥah is strictly forbidden
        if t["is_sound_fem_plural"]:
            if t["user_case"] == "ACC_INVALID_FATHA" or t["surface"].endswith("َاتَ") or t["surface"].endswith("َاتًا"):
                violations.append(
                    Violation(
                        code="CHECK_SOUND_PLURAL_INFLECTION",
                        tile_indices=[t["index"]],
                        rule_name_ar="منع الفتحة على جمع المؤنث السالم",
                        rule_name_en="Forbidden Fatḥah on Sound Feminine Plural",
                        message_ar=f"جمع المؤنث السالم '{t['surface']}' ينصب بالكسرة نيابة عن الفتحة، وتمنع الفتحة عليه منعاً باتاً.",
                        message_en=f"Sound feminine plural '{t['surface']}' takes kasrah for both Accusative and Genitive; fatḥah is strictly prohibited on '-āt'.",
                        broken_meaning_preview=f"{t['surface']} [inflection error: fatḥah on feminine plural -āt].",
                    )
                )

    # -----------------------------------------------------------------------
    # CHECK 8: CHECK_INNA_KANA_GOVERNMENT
    # -----------------------------------------------------------------------
    for i, t in enumerate(tiles):
        # Inna Sister: Inna + Ism(ACC) + Khabar(NOM)
        if t["pos"] == "INNA":
            clause_nouns = [
                n for n in tiles[i + 1:]
                if n["pos"] in ("NOUN", "VERB") and not (n["index"] > 0 and tiles[n["index"] - 1]["pos"] == "PREP")
            ]
            if len(clause_nouns) >= 1:
                ism = clause_nouns[0]
                if ism["user_case"] not in ("ACC", "ACC_OR_GEN"):
                    violations.append(
                        Violation(
                            code="CHECK_INNA_KANA_GOVERNMENT",
                            tile_indices=[t["index"], ism["index"]],
                            rule_name_ar="مخالفة عمل إن وأخواتها في المبتدأ",
                            rule_name_en="Inna Sister Subject Government Error",
                            message_ar=f"'{t['surface']}' حرف ناسخ ينصب اسمه بالفتحة أو الياء، وورد '{ism['surface']}' غير منصوب.",
                            message_en=f"'{t['surface']}' assigns Accusative (Manṣūb with fatḥah/yā') to its subject (Ism Inna), but '{ism['surface']}' is {ism['user_case'] or 'not accusative'}.",
                            broken_meaning_preview=f"{t['surface']} [broken Inna government: subject is not accusative].",
                        )
                    )
                else:
                    arrows.append(
                        GovernorArrow(
                            from_idx=t["index"],
                            to_idx=ism["index"],
                            relation="INNA_ISM",
                            description_ar=f"'{t['surface']}' نصبت الاسم '{ism['surface']}'",
                            description_en=f"'{t['surface']}' assigns Accusative to '{ism['surface']}'",
                        ).to_dict()
                    )

            if len(clause_nouns) >= 2:
                khabar = clause_nouns[1]
                if khabar["user_case"] not in ("NOM", None) and khabar["pos"] == "NOUN":
                    violations.append(
                        Violation(
                            code="CHECK_INNA_KANA_GOVERNMENT",
                            tile_indices=[t["index"], khabar["index"]],
                            rule_name_ar="مخالفة عمل إن وأخواتها في الخبر",
                            rule_name_en="Inna Sister Predicate Government Error",
                            message_ar=f"'{t['surface']}' حرف ناسخ يرفع خبره بالضمة أو الواو، وورد '{khabar['surface']}' غير مرفوع.",
                            message_en=f"'{t['surface']}' assigns Nominative (Marfū' with ḍammah/wāw) to its predicate (Khabar Inna), but '{khabar['surface']}' is {khabar['user_case'] or 'not nominative'}.",
                            broken_meaning_preview=f"{t['surface']} [broken Inna government: predicate is not nominative].",
                        )
                    )
                elif khabar["pos"] == "NOUN":
                    arrows.append(
                        GovernorArrow(
                            from_idx=t["index"],
                            to_idx=khabar["index"],
                            relation="INNA_KHABAR",
                            description_ar=f"'{t['surface']}' رفعت الخبر '{khabar['surface']}'",
                            description_en=f"'{t['surface']}' assigns Nominative to predicate '{khabar['surface']}'",
                        ).to_dict()
                    )

        # Kāna Sister: Kāna + Ism(NOM) + Khabar(ACC)
        if t["pos"] == "KANA":
            clause_nouns = [
                n for n in tiles[i + 1:]
                if n["pos"] in ("NOUN", "VERB") and not (n["index"] > 0 and tiles[n["index"] - 1]["pos"] == "PREP")
            ]
            if len(clause_nouns) >= 1:
                ism = clause_nouns[0]
                if ism["user_case"] not in ("NOM", None):
                    violations.append(
                        Violation(
                            code="CHECK_INNA_KANA_GOVERNMENT",
                            tile_indices=[t["index"], ism["index"]],
                            rule_name_ar="مخالفة عمل كان وأخواتها في المبتدأ",
                            rule_name_en="Kāna Sister Subject Government Error",
                            message_ar=f"'{t['surface']}' فعل ناسخ يرفع اسمه بالضمة، وورد '{ism['surface']}' غير مرفوع.",
                            message_en=f"'{t['surface']}' assigns Nominative (Marfū' with ḍammah) to its subject (Ism Kāna), but '{ism['surface']}' is {ism['user_case'] or 'not nominative'}.",
                            broken_meaning_preview=f"{t['surface']} [broken Kāna government: subject is not nominative].",
                        )
                    )
                else:
                    arrows.append(
                        GovernorArrow(
                            from_idx=t["index"],
                            to_idx=ism["index"],
                            relation="KANA_ISM",
                            description_ar=f"'{t['surface']}' رفعت الاسم '{ism['surface']}'",
                            description_en=f"'{t['surface']}' assigns Nominative to '{ism['surface']}'",
                        ).to_dict()
                    )

            if len(clause_nouns) >= 2:
                khabar = clause_nouns[1]
                if khabar["user_case"] not in ("ACC", "ACC_OR_GEN") and khabar["pos"] == "NOUN":
                    violations.append(
                        Violation(
                            code="CHECK_INNA_KANA_GOVERNMENT",
                            tile_indices=[t["index"], khabar["index"]],
                            rule_name_ar="مخالفة عمل كان وأخواتها في الخبر",
                            rule_name_en="Kāna Sister Predicate Government Error",
                            message_ar=f"'{t['surface']}' فعل ناسخ ينصب خبره بالفتحة، وورد '{khabar['surface']}' غير منصوب.",
                            message_en=f"'{t['surface']}' assigns Accusative (Manṣūb with fatḥah) to its predicate (Khabar Kāna), but '{khabar['surface']}' is {khabar['user_case'] or 'not accusative'}.",
                            broken_meaning_preview=f"{t['surface']} [broken Kāna government: predicate is not accusative].",
                        )
                    )
                elif khabar["pos"] == "NOUN":
                    arrows.append(
                        GovernorArrow(
                            from_idx=t["index"],
                            to_idx=khabar["index"],
                            relation="KANA_KHABAR",
                            description_ar=f"'{t['surface']}' نصبت الخبر '{khabar['surface']}'",
                            description_en=f"'{t['surface']}' assigns Accusative to predicate '{khabar['surface']}'",
                        ).to_dict()
                    )

    # -----------------------------------------------------------------------
    # CHECK 6: CHECK_IDAFAH_CHAIN
    # -----------------------------------------------------------------------
    for i in range(len(tiles) - 1):
        n1 = tiles[i]
        n2 = tiles[i + 1]
        # Two consecutive nouns not separated by preposition or conjunction
        if n1["pos"] == "NOUN" and n2["pos"] == "NOUN" and not (n1["index"] > 0 and tiles[n1["index"] - 1]["pos"] == "PREP"):
            # If n1 is preceded by KANA or INNA, n1 and n2 are copular Ism and Khabar, not Idafah
            is_after_copula = (n1["index"] > 0 and tiles[n1["index"] - 1]["pos"] in ("KANA", "INNA"))
            if is_after_copula:
                continue
            # A sound masculine plural that retains -ūna or -īna cannot be a Muḍāf (nūn must be elided)
            if n1["is_sound_masc_plural"] or n1["surface"].endswith("ُونَ") or n1["surface"].endswith("ِينَ"):
                continue

            # Check if n1 has construct intent or n2 is GEN
            is_n2_gen = n2["user_case"] in ("GEN", "ACC_OR_GEN")
            is_n1_tanwin = n1["has_tanwin"]
            is_n1_def = n1["proclitic"] == "الـ" or n1["surface"].startswith("ال")

            # If n2 is Genitive, this is an attempted Iḍāfah
            if is_n2_gen:
                if is_n1_tanwin:
                    violations.append(
                        Violation(
                            code="CHECK_IDAFAH_CHAIN",
                            tile_indices=[n1["index"], n2["index"]],
                            rule_name_ar="تنوين المضاف الممنوع",
                            rule_name_en="Iḍāfah Muḍāf Tanwīn Violation",
                            message_ar=f"المضاف '{n1['surface']}' لا ينون مطلقاً عند الإضافة إلى '{n2['surface']}'.",
                            message_en=f"Iḍāfah violation: The first term (Muḍāf '{n1['surface']}') cannot have tanwīn when annexed to '{n2['surface']}'.",
                            broken_meaning_preview=f"[broken annexation: {n1['surface']} carries tanwīn].",
                        )
                    )
                if is_n1_def:
                    violations.append(
                        Violation(
                            code="CHECK_IDAFAH_CHAIN",
                            tile_indices=[n1["index"], n2["index"]],
                            rule_name_ar="تعريف المضاف بأل",
                            rule_name_en="Iḍāfah Muḍāf Definiteness Violation",
                            message_ar=f"المضاف '{n1['surface']}' لا يقترن بأل التعريف عند إضافته إلى '{n2['surface']}'.",
                            message_en=f"Iḍāfah violation: The first term (Muḍāf '{n1['surface']}') cannot take the definite article 'الـ'.",
                            broken_meaning_preview=f"[broken annexation: {n1['surface']} cannot have 'الـ'].",
                        )
                    )
                if not is_n1_tanwin and not is_n1_def:
                    arrows.append(
                        GovernorArrow(
                            from_idx=n1["index"],
                            to_idx=n2["index"],
                            relation="MUDHAF_MUDHAF_ILAYHI",
                            description_ar=f"المضاف '{n1['surface']}' جرّ المضاف إليه '{n2['surface']}'",
                            description_en=f"Muḍāf '{n1['surface']}' governs '{n2['surface']}' into Genitive",
                        ).to_dict()
                    )

            # If n1 is bare noun and n2 is noun with NOM or ACC while attempting iḍāfah
            elif not is_n1_def and not is_n1_tanwin and n2["user_case"] in ("NOM", "ACC"):
                has_verb = any(t["pos"] == "VERB" for t in tiles)
                if not has_verb:
                    violations.append(
                        Violation(
                            code="CHECK_IDAFAH_CHAIN",
                            tile_indices=[n1["index"], n2["index"]],
                            rule_name_ar="مخالفة جر المضاف إليه",
                            rule_name_en="Iḍāfah Muḍāf Ilayhi Non-Genitive Violation",
                            message_ar=f"المضاف إليه '{n2['surface']}' يجب أن يكون مجروراً بالكسرة دائماً، وورد {n2['user_case']}.",
                            message_en=f"Iḍāfah violation: The second term (Muḍāf ilayhi '{n2['surface']}') must be Genitive (Majrūr with kasrah), not {n2['user_case']}.",
                            broken_meaning_preview=f"[broken annexation: {n2['surface']} is not genitive].",
                        )
                    )

    # -----------------------------------------------------------------------
    # CHECK 3, 4, 5: VERBAL CLAUSE CHECKS
    # (VALENCY, PASSIVE NAIB FAIL, SVO/VSO AGREEMENT)
    # -----------------------------------------------------------------------
    verb_indices = [t["index"] for t in tiles if t["pos"] == "VERB"]

    for v_idx in verb_indices:
        v = tiles[v_idx]
        is_passive = v["is_passive_verb"]
        has_attached_subject = v["attached_subject_pronoun"] is not None

        # Collect candidate nouns belonging to this verb clause (excluding prepositional objects)
        free_nouns: list[dict[str, Any]] = []
        for i, t in enumerate(tiles):
            if t["pos"] == "NOUN":
                # Exclude nouns governed by preposition
                is_prep_obj = (i > 0 and tiles[i - 1]["pos"] == "PREP") or (t["proclitic"] in PREP_PROCLITICS)
                if not is_prep_obj:
                    free_nouns.append(t)

        preceding_nouns = [n for n in free_nouns if n["index"] < v_idx]
        following_nouns = [n for n in free_nouns if n["index"] > v_idx]

        # -------------------------------------------------------------------
        # CHECK 4: CHECK_PASSIVE_NAIB_FAIL
        # -------------------------------------------------------------------
        if is_passive:
            nom_nouns = [n for n in following_nouns if n["user_case"] == "NOM"]
            acc_nouns = [n for n in following_nouns if n["user_case"] in ("ACC", "ACC_INVALID_FATHA")]

            if acc_nouns and not nom_nouns and not has_attached_subject:
                # Receiver is marked with ACC instead of NOM!
                target_obj = acc_nouns[0]
                violations.append(
                    Violation(
                        code="CHECK_PASSIVE_NAIB_FAIL",
                        tile_indices=[v["index"], target_obj["index"]],
                        rule_name_ar="نصب نائب الفاعل في الفعل المبني للمجهول",
                        rule_name_en="Accusative Deputy Subject in Passive Sentence",
                        message_ar=f"الفعل المبني للمجهول '{v['surface']}' يرفع نائب الفاعل بالضمة؛ ولا يجوز نصبه بالفتحة كالمفعول به.",
                        message_en=f"In passive voice '{v['surface']}', the deputy subject (Nā'ib al-Fā'il '{target_obj['surface']}') must be Nominative (Marfū' with ḍammah), not Accusative (Manṣūb with fatḥah).",
                        broken_meaning_preview=f"Was helped [receiver '{target_obj['bare']}' is marked as an object instead of deputy subject].",
                    )
                )
            elif nom_nouns:
                # Valid Nāʾib al-Fāʿil
                naib = nom_nouns[0]
                arrows.append(
                    GovernorArrow(
                        from_idx=v["index"],
                        to_idx=naib["index"],
                        relation="FIL_NAIB_FAIL",
                        description_ar=f"الفعل المبني للمجهول '{v['surface']}' رفع نائب الفاعل '{naib['surface']}'",
                        description_en=f"Passive verb '{v['surface']}' assigns Nominative to Nā'ib al-Fā'il '{naib['surface']}'",
                    ).to_dict()
                )

        # -------------------------------------------------------------------
        # CHECK 3: CHECK_VERB_VALENCY_AND_FAIL (ACTIVE VERBS)
        # -------------------------------------------------------------------
        if not is_passive:
            # Separate NOM and ACC nouns in clause
            all_clause_nouns = preceding_nouns + following_nouns
            nom_nouns = [n for n in all_clause_nouns if n["user_case"] == "NOM"]
            acc_nouns = [n for n in all_clause_nouns if n["user_case"] in ("ACC", "ACC_OR_GEN")]

            # SUB-CHECK: MISSING_FAIL (Double ACC / All ACC without subject)
            if not has_attached_subject and len(acc_nouns) >= 2 and len(nom_nouns) == 0:
                violations.append(
                    Violation(
                        code="CHECK_VERB_VALENCY_AND_FAIL",
                        tile_indices=[v["index"]] + [n["index"] for n in acc_nouns],
                        rule_name_ar="غياب الفاعل وتعدد المنصوبات",
                        rule_name_en="Missing Subject (Fā'il) & Object Collision",
                        message_ar=f"الفعل المبني للمعلوم '{v['surface']}' يتطلب فاعلاً مرفوعاً بالضمة؛ وورد الاسمان منصوبين كلاهما مفعول به دون فاعل.",
                        message_en=f"Missing Subject on '{v['surface']}': Both '{acc_nouns[0]['surface']}' and '{acc_nouns[1]['surface']}' are marked with Accusative (fatḥah). An active verb requires a Nominative subject.",
                        broken_meaning_preview=f"{v['bare']} [??? — no doer/agent!] {acc_nouns[0]['bare']}, {acc_nouns[1]['bare']}.",
                    )
                )

            # SUB-CHECK: DOUBLE_FAIL_COLLISION (Two NOM nouns without coordinating conjunction)
            if len(nom_nouns) >= 2:
                # Check if there is a conjunction between them
                has_conj = any(
                    tiles[k]["pos"] == "CONJ"
                    for k in range(min(nom_nouns[0]["index"], nom_nouns[1]["index"]),
                                   max(nom_nouns[0]["index"], nom_nouns[1]["index"]))
                )
                if not has_conj:
                    violations.append(
                        Violation(
                            code="CHECK_VERB_VALENCY_AND_FAIL",
                            tile_indices=[v["index"], nom_nouns[0]["index"], nom_nouns[1]["index"]],
                            rule_name_ar="تنازع فاعلين مرفوعين دون عاطف",
                            rule_name_en="Subject (Fā'il) Collision",
                            message_ar=f"تنازع فاعلان مرفوعان ('{nom_nouns[0]['surface']}' و '{nom_nouns[1]['surface']}') على فعل واحد دون حرف عطف.",
                            message_en=f"Subject collision: Two separate nouns ('{nom_nouns[0]['surface']}' and '{nom_nouns[1]['surface']}') are both Nominative for active verb '{v['surface']}' without a conjunction ('wa').",
                            broken_meaning_preview=f"{v['bare']} both {nom_nouns[0]['bare']} and {nom_nouns[1]['bare']} [collision: who is the doer?].",
                        )
                    )

            # Record governor arrows for active verb
            if nom_nouns and not violations:
                subject_noun = nom_nouns[0]
                arrows.append(
                    GovernorArrow(
                        from_idx=v["index"],
                        to_idx=subject_noun["index"],
                        relation="FIL_FAIL",
                        description_ar=f"الفعل '{v['surface']}' رفع الفاعل '{subject_noun['surface']}'",
                        description_en=f"Verb '{v['surface']}' assigns Nominative to Fā'il '{subject_noun['surface']}'",
                    ).to_dict()
                )
            for acc in acc_nouns:
                arrows.append(
                    GovernorArrow(
                        from_idx=v["index"],
                        to_idx=acc["index"],
                        relation="FIL_MAFUL",
                        description_ar=f"الفعل '{v['surface']}' نصب المفعول به '{acc['surface']}'",
                        description_en=f"Verb '{v['surface']}' assigns Accusative to Maf'ūl '{acc['surface']}'",
                    ).to_dict()
                )

        # -------------------------------------------------------------------
        # CHECK 5: CHECK_SVO_VSO_AGREEMENT
        # -------------------------------------------------------------------
        # Case A: VSO (Verb precedes plural subject) -> Verb must remain SINGULAR
        following_subj = [n for n in following_nouns if n["user_case"] == "NOM"]
        if following_subj and v["attached_subject_pronoun"] in ("ُوا", "ْنَ", "َا"):
            # Verb carries plural marker before overt subject!
            violations.append(
                Violation(
                    code="CHECK_SVO_VSO_AGREEMENT",
                    tile_indices=[v["index"], following_subj[0]["index"]],
                    rule_name_ar="خطأ في مطابقة الفعل المتقدم (لزوم الإفراد)",
                    rule_name_en="VSO Word Order Number Agreement Error",
                    message_ar=f"الفعل إذا تقدم على فاعله الظاهر ('{following_subj[0]['surface']}') لزمه الإفراد دائماً في الفصحى؛ فلا تلحقه واو الجماعة.",
                    message_en=f"VSO Agreement Error: When the verb precedes an overt subject ('{following_subj[0]['surface']}'), the verb must remain singular (e.g. use singular verb, not '{v['surface']}').",
                    broken_meaning_preview=f"They-helped the Muslims [redundant subject marking in VSO].",
                )
            )

        # Case B: SVO (Fronted subject as Mubtada') -> Following verb must agree in NUMBER and GENDER
        if preceding_nouns and not following_subj:
            fronted_topic = preceding_nouns[-1]
            if fronted_topic["is_sound_masc_plural"] and fronted_topic["user_case"] == "NOM":
                # Fronted plural subject requires plural verb (ـُوا)
                if not (v["attached_subject_pronoun"] == "ُوا" or v["surface"].endswith("ُوا")):
                    violations.append(
                        Violation(
                            code="CHECK_SVO_VSO_AGREEMENT",
                            tile_indices=[fronted_topic["index"], v["index"]],
                            rule_name_ar="خطأ مطابقة المبتدأ والخبر الفعلي في الجمع",
                            rule_name_en="SVO Word Order Agreement Error",
                            message_ar=f"المبتدأ الجمع '{fronted_topic['surface']}' يوجب مطابقة الفعل في الخبر جمعاً باتصاله بواو الجماعة (ـُوا).",
                            message_en=f"SVO Agreement Error: Plural topic '{fronted_topic['surface']}' requires verb '{v['surface']}' to carry the matching plural suffix 'ـُوا' ('-ū').",
                            broken_meaning_preview=f"The Muslims [he] helped the man [subject-verb agreement mismatch in SVO].",
                        )
                    )

    # -----------------------------------------------------------------------
    # CLAUSE IDENTIFICATION & SUMMARY
    # -----------------------------------------------------------------------
    if verb_indices:
        v_idx = verb_indices[0]
        v = tiles[v_idx]
        is_pass = v["is_passive_verb"]
        clause_type = "VERBAL_PASSIVE" if is_pass else "VERBAL_ACTIVE"

        subj_idx = None
        subj_src = None
        if v["attached_subject_pronoun"]:
            subj_idx = v_idx
            subj_src = "ATTACHED_PRONOUN"
        else:
            noms = [t["index"] for t in tiles if t["pos"] == "NOUN" and t["user_case"] == "NOM"]
            if noms:
                subj_idx = noms[0]
                subj_src = "OVERT_NOUN"

        obj_indices = [t["index"] for t in tiles if t["pos"] == "NOUN" and t["user_case"] in ("ACC", "ACC_OR_GEN")]
        clauses.append(
            ClauseAnalysis(
                clause_type=clause_type,
                verb_idx=v_idx,
                subject_idx=subj_idx,
                subject_source=subj_src,
                object_indices=obj_indices,
            )
        )
    elif any(t["pos"] == "INNA" for t in tiles):
        clauses.append(ClauseAnalysis(clause_type="INNA_SENTENCE"))
    elif any(t["pos"] == "KANA" for t in tiles):
        clauses.append(ClauseAnalysis(clause_type="KANA_SENTENCE"))
    else:
        clauses.append(ClauseAnalysis(clause_type="NOMINAL"))

    is_valid = len(violations) == 0

    return VerificationResult(
        is_valid=is_valid,
        violations=violations,
        clauses=clauses,
        governor_arrows=arrows,
        annotated_tiles=tiles,
    )


# ---------------------------------------------------------------------------
# CLI & SELF TEST
# ---------------------------------------------------------------------------

def selftest() -> int:
    """Run verification self-test covering all 8 checks."""
    print("=" * 80)
    print("RUNNING NAḤW VERIFIER SELF-TEST (8 DETERMINISTIC CONSTRAINT CHECKS)")
    print("=" * 80)
    failures = []

    def check(cond: bool, msg: str):
        status = "OK " if cond else "FAIL"
        print(f"  [{status}] {msg}")
        if not cond:
            failures.append(msg)

    # Check 1: Definiteness + Tanwīn clash
    r1_bad = verify_sentence(["الرَّجُلٌ"])
    r1_good = verify_sentence(["الرَّجُلُ"])
    check(not r1_bad.is_valid and r1_bad.violations[0].code == "CHECK_AL_TANWIN_CLASH", "Check 1: Rejects 'الـ' with tanwīn (الرَّجُلٌ)")
    check(r1_good.is_valid, "Check 1: Accepts 'الـ' with bare damma (الرَّجُلُ)")

    # Check 2: Preposition Genitive
    r2_bad = verify_sentence(["إِلَى", "المَسْجِدُ"])
    r2_good = verify_sentence(["إِلَى", "المَسْجِدِ"])
    check(not r2_bad.is_valid and r2_bad.violations[0].code == "CHECK_PREP_GENITIVE", "Check 2: Rejects NOM after preposition (إِلَى المَسْجِدُ)")
    check(r2_good.is_valid, "Check 2: Accepts GEN after preposition (إِلَى المَسْجِدِ)")

    # Check 3: Missing Fāʿil (Double ACC)
    r3_bad = verify_sentence(["نَصَرَ", "المُسْلِمَ", "الرَّجُلَ"])
    r3_good = verify_sentence(["نَصَرَ", "المُسْلِمُ", "الرَّجُلَ"])
    check(not r3_bad.is_valid and r3_bad.violations[0].code == "CHECK_VERB_VALENCY_AND_FAIL", "Check 3: Rejects double ACC without subject (نَصَرَ المُسْلِمَ الرَّجُلَ)")
    check(r3_good.is_valid, "Check 3: Accepts VSO verbal clause (نَصَرَ المُسْلِمُ الرَّجُلَ)")

    # Check 4: Passive Deputy Subject (Nāʾib al-Fāʿil)
    r4_bad = verify_sentence(["نُصِرَ", "المُسْلِمَ"])
    r4_good = verify_sentence(["نُصِرَ", "المُسْلِمُ"])
    check(not r4_bad.is_valid and r4_bad.violations[0].code == "CHECK_PASSIVE_NAIB_FAIL", "Check 4: Rejects ACC receiver in passive voice (نُصِرَ المُسْلِمَ)")
    check(r4_good.is_valid, "Check 4: Accepts NOM Nā'ib al-Fā'il in passive voice (نُصِرَ المُسْلِمُ)")

    # Check 5: Agreement (VSO vs SVO)
    r5_vso_bad = verify_sentence(["نَصَرُوا", "المُسْلِمُونَ", "الرَّجُلَ"])
    r5_vso_good = verify_sentence(["نَصَرَ", "المُسْلِمُونَ", "الرَّجُلَ"])
    r5_svo_bad = verify_sentence(["المُسْلِمُونَ", "نَصَرَ", "الرَّجُلَ"])
    r5_svo_good = verify_sentence(["المُسْلِمُونَ", "نَصَرُوا", "الرَّجُلَ"])
    check(not r5_vso_bad.is_valid and r5_vso_bad.violations[0].code == "CHECK_SVO_VSO_AGREEMENT", "Check 5: Rejects plural verb in VSO order (نَصَرُوا المُسْلِمُونَ)")
    check(r5_vso_good.is_valid, "Check 5: Accepts singular verb in VSO order (نَصَرَ المُسْلِمُونَ)")
    check(not r5_svo_bad.is_valid and r5_svo_bad.violations[0].code == "CHECK_SVO_VSO_AGREEMENT", "Check 5: Rejects singular verb in SVO plural topic (المُسْلِمُونَ نَصَرَ)")
    check(r5_svo_good.is_valid, "Check 5: Accepts plural verb in SVO plural topic (المُسْلِمُونَ نَصَرُوا)")

    # Check 6: Iḍāfah
    r6_bad_tanwin = verify_sentence(["كِتَابٌ", "الرَّجُلِ"])
    r6_bad_al = verify_sentence(["الْكِتَابُ", "الرَّجُلِ"])
    r6_good = verify_sentence(["كِتَابُ", "الرَّجُلِ"])
    check(not r6_bad_tanwin.is_valid and r6_bad_tanwin.violations[0].code == "CHECK_IDAFAH_CHAIN", "Check 6: Rejects tanwīn on Muḍāf (كِتَابٌ الرَّجُلِ)")
    check(not r6_bad_al.is_valid and r6_bad_al.violations[0].code == "CHECK_IDAFAH_CHAIN", "Check 6: Rejects 'الـ' on Muḍāf (الْكِتَابُ الرَّجُلِ)")
    check(r6_good.is_valid, "Check 6: Accepts valid Iḍāfah (كِتَابُ الرَّجُلِ)")

    # Check 7: Sound Plural Inflection
    r7_masc_bad = verify_sentence(["إِلَى", "المُسْلِمُونَ"])
    r7_fem_bad = verify_sentence([{"surface": "رَأَيْتُ"}, {"surface": "المُعَلِّمَاتَ", "user_case": "ACC_INVALID_FATHA"}])
    r7_fem_good = verify_sentence([{"surface": "رَأَيْتُ"}, {"surface": "المُعَلِّمَاتِ", "user_case": "ACC"}])
    check(not r7_masc_bad.is_valid and any(v.code == "CHECK_SOUND_PLURAL_INFLECTION" for v in r7_masc_bad.violations), "Check 7: Rejects '-ūna' after preposition (إِلَى المُسْلِمُونَ)")
    check(not r7_fem_bad.is_valid and r7_fem_bad.violations[0].code == "CHECK_SOUND_PLURAL_INFLECTION", "Check 7: Rejects fatḥah on sound feminine plural (المُعَلِّمَاتَ)")
    check(r7_fem_good.is_valid, "Check 7: Accepts kasrah in ACC sound fem plural (المُعَلِّمَاتِ)")

    # Check 8: Inna and Kāna
    r8_inna_bad = verify_sentence(["إِنَّ", "الرَّجُلُ", "عَالِمٌ"])
    r8_inna_good = verify_sentence(["إِنَّ", "الرَّجُلَ", "عَالِمٌ"])
    r8_kana_bad = verify_sentence(["كَانَ", "الرَّجُلَ", "عَالِمٌ"])
    r8_kana_good = verify_sentence(["كَانَ", "الرَّجُلُ", "عَالِمًا"])
    check(not r8_inna_bad.is_valid and r8_inna_bad.violations[0].code == "CHECK_INNA_KANA_GOVERNMENT", "Check 8: Rejects NOM Ism Inna (إِنَّ الرَّجُلُ عَالِمٌ)")
    check(r8_inna_good.is_valid, "Check 8: Accepts ACC Ism Inna (إِنَّ الرَّجُلَ عَالِمٌ)")
    check(not r8_kana_bad.is_valid and r8_kana_bad.violations[0].code == "CHECK_INNA_KANA_GOVERNMENT", "Check 8: Rejects ACC Ism Kāna (كَانَ الرَّجُلَ عَالِمٌ)")
    check(r8_kana_good.is_valid, "Check 8: Accepts NOM Ism Kāna + ACC Khabar (كَانَ الرَّجُلُ عَالِمًا)")

    print("=" * 80)
    if failures:
        print(f"FAILED: {len(failures)} checks failed!")
        return 1
    print("ALL NAḤW VERIFIER CHECKS PASSED (exit 0)!")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] != "--selftest":
        res = verify_sentence(sys.argv[1:])
        import json
        print(json.dumps(res.to_dict(), ensure_ascii=False, indent=2))
    else:
        sys.exit(selftest())
