#!/usr/bin/env python3
"""src/semantic_binder.py — Diacritic-Driven Semantic Role Binder & Live Translator.

Binds semantic roles (AGENT, PATIENT, RECIPIENT, LOCATION, POSSESSOR, TOPIC, PREDICATE)
strictly from verified morphological voice, case diacritics, and governor links.
Never assumes naive English SVO word order.

Minimal Pair Invariant (Gate G8):
  ضَرَبَ زَيْدٌ عَمْرًا  -> AGENT=Zayd, PATIENT='Amr (V-S-O: "Zayd struck 'Amr")
  ضَرَبَ زَيْدًا عَمْرٌ  -> AGENT='Amr, PATIENT=Zayd (V-O-S: "It was Zayd whom 'Amr struck")
  ضُرِبَ زَيْدٌ        -> PATIENT=Zayd (Passive: "Zayd was struck")
"""
from __future__ import annotations

import io
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

from nahw_verifier import VerificationResult, parse_tile, strip_tashkeel, verify_sentence

# Ensure UTF-8 output on Windows consoles
if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8")


# ---------------------------------------------------------------------------
# LEXICAL GLOSSES & DICTIONARIES
# ---------------------------------------------------------------------------

VERB_GLOSSES: dict[str, dict[str, str]] = {
    "نصر": {"active_past": "helped", "passive_past": "was helped", "active_id": "menolong", "passive_id": "ditolong"},
    "ضرب": {"active_past": "struck", "passive_past": "was struck", "active_id": "memukul", "passive_id": "dipukul"},
    "علم": {"active_past": "knew", "passive_past": "was known", "active_id": "mengetahui", "passive_id": "diketahui"},
    "كتب": {"active_past": "wrote", "passive_past": "was written", "active_id": "menulis", "passive_id": "ditulis"},
    "قرا": {"active_past": "read", "passive_past": "was read", "active_id": "membaca", "passive_id": "dibaca"},
    "ذهب": {"active_past": "went", "passive_past": "was gone", "active_id": "pergi", "passive_id": "dipergi"},
    "قال": {"active_past": "said", "passive_past": "was said", "active_id": "berkata / mengatakan", "passive_id": "dikatakan"},
    "رقد": {"active_past": "slept", "passive_past": "was slept", "active_id": "tidur", "passive_id": "ditiduri"},
    "حمد": {"active_past": "praised", "passive_past": "was praised", "active_id": "memuji", "passive_id": "dipuji"},
    "طهر": {"active_past": "purified", "passive_past": "was purified", "active_id": "menyucikan", "passive_id": "disucikan"},
    "قلد": {"active_past": "imitated", "passive_past": "was imitated", "active_id": "meniru", "passive_id": "ditiru"},
    "فرق": {"active_past": "separated", "passive_past": "was separated", "active_id": "memisahkan", "passive_id": "dipisahkan"},
    "طاف": {"active_past": "circumambulated", "passive_past": "was circumambulated", "active_id": "mengelilingi", "passive_id": "dikelilingi"},
    "راي": {"active_past": "saw", "passive_past": "was seen", "active_id": "melihat", "passive_id": "dilihat"},
    "سمع": {"active_past": "heard", "passive_past": "was heard", "active_id": "mendengar", "passive_id": "didengar"},
    "اكل": {"active_past": "ate", "passive_past": "was eaten", "active_id": "memakan", "passive_id": "dimakan"},
    "شرب": {"active_past": "drank", "passive_past": "was drunk", "active_id": "meminum", "passive_id": "diminum"},
    "فتح": {"active_past": "opened", "passive_past": "was opened", "active_id": "membuka", "passive_id": "dibuka"},
    "خلق": {"active_past": "created", "passive_past": "was created", "active_id": "menciptakan", "passive_id": "diciptakan"},
}

NOUN_GLOSSES: dict[str, dict[str, str]] = {
    "مسلم": {"def_en": "the Muslim", "indef_en": "a Muslim", "pl_def_en": "the Muslims", "pl_indef_en": "Muslims",
             "def_id": "orang Muslim itu", "indef_id": "seorang Muslim", "pl_def_id": "orang-orang Muslim itu", "pl_indef_id": "orang-orang Muslim"},
    "رجل": {"def_en": "the man", "indef_en": "a man", "pl_def_en": "the men", "pl_indef_en": "men",
            "def_id": "laki-laki itu", "indef_id": "seorang laki-laki", "pl_def_id": "laki-laki itu", "pl_indef_id": "orang-orang laki-laki"},
    "ولد": {"def_en": "the boy", "indef_en": "a boy", "pl_def_en": "the boys", "pl_indef_en": "boys",
            "def_id": "anak laki-laki itu", "indef_id": "seorang anak laki-laki", "pl_def_id": "anak-anak itu", "pl_indef_id": "anak-anak"},
    "معلم": {"def_en": "the teacher", "indef_en": "a teacher", "pl_def_en": "the teachers", "pl_indef_en": "teachers",
             "def_id": "guru itu", "indef_id": "seorang guru", "pl_def_id": "guru-guru itu", "pl_indef_id": "guru-guru"},
    "معلمة": {"def_en": "the female teacher", "indef_en": "a female teacher", "pl_def_en": "the female teachers", "pl_indef_en": "female teachers",
              "def_id": "guru perempuan itu", "indef_id": "seorang guru perempuan", "pl_def_id": "guru-guru perempuan itu", "pl_indef_id": "guru-guru perempuan"},
    "طالب": {"def_en": "the student", "indef_en": "a student", "pl_def_en": "the students", "pl_indef_en": "students",
             "def_id": "murid itu", "indef_id": "seorang murid", "pl_def_id": "murid-murid itu", "pl_indef_id": "murid-murid"},
    "زيد": {"def_en": "Zayd", "indef_en": "Zayd", "def_id": "Zaid", "indef_id": "Zaid"},
    "عمرو": {"def_en": "'Amr", "indef_en": "'Amr", "def_id": "'Amr", "indef_id": "'Amr"},
    "عمر": {"def_en": "'Umar", "indef_en": "'Umar", "def_id": "'Umar", "indef_id": "'Umar"},
    "محمد": {"def_en": "Muhammad", "indef_en": "Muhammad", "def_id": "Muhammad", "indef_id": "Muhammad"},
    "علي": {"def_en": "'Ali", "indef_en": "'Ali", "def_id": "'Ali", "indef_id": "'Ali"},
    "كتاب": {"def_en": "the book", "indef_en": "a book", "pl_def_en": "the books", "pl_indef_en": "books",
             "def_id": "buku itu", "indef_id": "sebuah buku", "pl_def_id": "buku-buku itu", "pl_indef_id": "buku-buku"},
    "بيت": {"def_en": "the house", "indef_en": "a house", "def_id": "rumah itu", "indef_id": "sebuah rumah"},
    "مسجد": {"def_en": "the mosque", "indef_en": "a mosque", "def_id": "masjid itu", "indef_id": "sebuah masjid"},
    "طعام": {"def_en": "the food", "indef_en": "food", "def_id": "makanan itu", "indef_id": "makanan"},
    "خبز": {"def_en": "the bread", "indef_en": "bread", "def_id": "roti itu", "indef_id": "roti"},
    "عالم": {"def_en": "the scholar", "indef_en": "a scholar", "def_id": "orang alim itu", "indef_id": "seorang alim"},
    "صادق": {"def_en": "the truthful one", "indef_en": "truthful", "def_id": "orang yang jujur itu", "indef_id": "jujur"},
    "جديد": {"def_en": "the new one", "indef_en": "new", "def_id": "yang baru itu", "indef_id": "baru"},
    "قديم": {"def_en": "the old one", "indef_en": "old", "def_id": "yang lama itu", "indef_id": "lama"},
    "كبير": {"def_en": "the big one", "indef_en": "big", "def_id": "yang besar itu", "indef_id": "besar"},
    "صغير": {"def_en": "the small one", "indef_en": "small", "def_id": "yang kecil itu", "indef_id": "kecil"},
    "الله": {"def_en": "Allah / God", "indef_en": "Allah / God", "def_id": "Allah", "indef_id": "Allah"},
}

PREP_GLOSSES: dict[str, dict[str, str]] = {
    "في": {"en": "in", "id": "di"},
    "إلى": {"en": "to", "id": "ke"},
    "من": {"en": "from", "id": "dari"},
    "على": {"en": "on", "id": "di atas"},
    "بِـ": {"en": "with", "id": "dengan"},
    "لِـ": {"en": "for", "id": "untuk"},
    "كَـ": {"en": "like", "id": "seperti"},
}

PRONOUN_SUFFIX_GLOSS: dict[str, dict[str, str]] = {
    "ْتُ": {"agent_en": "I", "agent_id": "aku"},
    "ْتَ": {"agent_en": "you (m)", "agent_id": "kamu"},
    "ْتِ": {"agent_en": "you (f)", "agent_id": "kamu (pr)"},
    "ْنَا": {"agent_en": "we", "agent_id": "kami / kita"},
    "ْتُمْ": {"agent_en": "you all", "agent_id": "kalian"},
    "ُوا": {"agent_en": "they", "agent_id": "mereka"},
    "ْنَ": {"agent_en": "they (f)", "agent_id": "mereka (pr)"},
    "ـهُ": {"patient_en": "him", "patient_id": "dia"},
    "ـهَا": {"patient_en": "her", "patient_id": "dia (pr)"},
    "ـهُمْ": {"patient_en": "them", "patient_id": "mereka"},
    "ـكَ": {"patient_en": "you", "patient_id": "kamu"},
    "ـنِي": {"patient_en": "me", "patient_id": "aku"},
}


# ---------------------------------------------------------------------------
# DATA STRUCTURES
# ---------------------------------------------------------------------------

@dataclass
class SemanticRole:
    role: str               # "AGENT" | "PATIENT" | "RECIPIENT" | "LOCATION" | "POSSESSOR" | "TOPIC" | "PREDICATE"
    tile_index: int | None
    surface: str
    gloss_en: str
    gloss_id: str
    case_assigned: str | None
    source: str             # "OVERT_NOUN" | "ATTACHED_PRONOUN" | "LATENT" | "PREPOSITIONAL_PHRASE"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SemanticBindingResult:
    is_valid: bool
    word_order: str         # "VSO" | "VOS" | "SVO" | "OVS" | "PASSIVE_V_NAIB" | "INNA_SENTENCE" | "KANA_SENTENCE" | "NOMINAL"
    voice: str              # "ACTIVE" | "PASSIVE" | "COPULAR" | "NON_VERBAL"
    roles: dict[str, SemanticRole]
    translation_en: str
    translation_id: str
    info_structure_note: str | None
    violations: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "word_order": self.word_order,
            "voice": self.voice,
            "roles": {k: v.to_dict() for k, v in self.roles.items()},
            "translation_en": self.translation_en,
            "translation_id": self.translation_id,
            "info_structure_note": self.info_structure_note,
            "violations": self.violations,
        }


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _lookup_noun_gloss(surface: str, bare: str, is_plural: bool, is_def: bool) -> tuple[str, str]:
    """Look up English and Indonesian gloss for a noun tile."""
    # Strip any attached prepositions (بِـ, لِـ, كَـ)
    clean_bare = bare
    for p in ("ب", "ل", "ك"):
        if clean_bare.startswith(p) and len(clean_bare) > 2 and clean_bare not in NOUN_GLOSSES:
            clean_bare = clean_bare[1:]

    # Strip definite article
    if clean_bare.startswith("ال") and len(clean_bare) > 2:
        clean_bare = clean_bare[2:]

    # Disambiguate 'Amr vs 'Umar and strip tanwīn alif (e.g. عَمْرًا -> عمرو, زَيْدًا -> زيد)
    if clean_bare == "عمرا":
        clean_bare = "عمرو"
    elif clean_bare == "عمر":
        # 'Umar is a diptote (عُمَرُ) that never takes tanwīn.
        # 'Amr (عَمْرٌ) carries sukun on mim and takes tanwīn.
        if any(ch in "\u064b\u064c\u064d" for ch in surface) or "عَمْر" in surface:
            clean_bare = "عمرو"
    elif clean_bare.endswith("ا") and len(clean_bare) > 2 and clean_bare not in NOUN_GLOSSES:
        stem_no_alif = clean_bare[:-1]
        if stem_no_alif in NOUN_GLOSSES:
            clean_bare = stem_no_alif

    # Remove sound plural / feminine suffixes to find root lemma
    stem = clean_bare
    if stem.endswith("ون") or stem.endswith("ين"):
        stem = stem[:-2]
    elif stem.endswith("ات"):
        stem = stem[:-2]

    entry = NOUN_GLOSSES.get(clean_bare) or NOUN_GLOSSES.get(stem)
    if entry:
        if is_plural and "pl_def_en" in entry:
            en = entry["pl_def_en"] if is_def else entry["pl_indef_en"]
            ind = entry["pl_def_id"] if is_def else entry["pl_indef_id"]
        else:
            en = entry["def_en"] if is_def else entry["indef_en"]
            ind = entry["def_id"] if is_def else entry["indef_id"]
        return en, ind

    # Fallback default
    fallback = clean_bare.capitalize()
    return fallback, fallback


def _lookup_verb_gloss(bare: str) -> dict[str, str]:
    """Look up verb translation templates."""
    # Find base 3-letter root or known verb
    for root, gl in VERB_GLOSSES.items():
        if bare.startswith(root) or (len(bare) >= 3 and bare[:3] == root):
            return gl
    return {
        "active_past": f"act-on ({bare})",
        "passive_past": f"was acted-on ({bare})",
        "active_id": f"melakukan ({bare})",
        "passive_id": f"dilakukan ({bare})",
    }


# ---------------------------------------------------------------------------
# CORE SEMANTIC ROLE BINDER
# ---------------------------------------------------------------------------

def bind_semantics(tiles_input: Sequence[dict[str, Any] | str]) -> SemanticBindingResult:
    """Bind semantic roles and synthesize live translation from verified diacritics and voice."""
    # 1. Run the deterministic Naḥw verifier first
    v_res: VerificationResult = verify_sentence(tiles_input)
    tiles = v_res.annotated_tiles

    if not v_res.is_valid:
        # Generate broken preview translation
        broken_notes = [v.broken_meaning_preview for v in v_res.violations]
        broken_en = " | ".join(broken_notes)
        return SemanticBindingResult(
            is_valid=False,
            word_order="INVALID",
            voice="INVALID",
            roles={},
            translation_en=f"[Grammar Violation: {broken_en}]",
            translation_id=f"[Pelanggaran Tata Bahasa: {getattr(v_res.violations[0], 'message_id', v_res.violations[0].message_ar)}]",
            info_structure_note=v_res.violations[0].message_en,
            violations=[v.to_dict() for v in v_res.violations],
        )

    roles: dict[str, SemanticRole] = {}
    word_order = "NOMINAL"
    voice = "NON_VERBAL"
    info_note = None

    verb_tiles = [t for t in tiles if t["pos"] == "VERB"]
    noun_tiles = [t for t in tiles if t["pos"] == "NOUN"]
    inna_tiles = [t for t in tiles if t["pos"] == "INNA"]
    kana_tiles = [t for t in tiles if t["pos"] == "KANA"]
    prep_tiles = [t for t in tiles if t["pos"] == "PREP"]

    # -----------------------------------------------------------------------
    # SCENARIO 1: VERBAL SENTENCE (ACTIVE OR PASSIVE)
    # -----------------------------------------------------------------------
    if verb_tiles:
        v = verb_tiles[0]
        v_idx = v["index"]
        is_passive = v["is_passive_verb"]
        voice = "PASSIVE" if is_passive else "ACTIVE"
        v_gl = _lookup_verb_gloss(v["bare"])

        # Identify prepositional phrases (Location/Circumstance)
        prep_phrase_noun_indices: set[int] = set()
        prep_phrases: list[dict[str, Any]] = []
        for i, t in enumerate(tiles):
            if t["pos"] == "PREP" and i + 1 < len(tiles):
                p_noun = tiles[i + 1]
                prep_phrase_noun_indices.add(p_noun["index"])
                p_gl = PREP_GLOSSES.get(t["bare"], {"en": t["bare"], "id": t["bare"]})
                n_is_def = p_noun["definiteness"] == "definite"
                n_en, n_id = _lookup_noun_gloss(p_noun["surface"], p_noun["bare"], p_noun["is_sound_masc_plural"], n_is_def)
                prep_phrases.append({
                    "prep": t["surface"],
                    "noun_idx": p_noun["index"],
                    "en": f"{p_gl['en']} {n_en}",
                    "id": f"{p_gl['id']} {n_id}",
                })
            elif t["proclitic"] in PREP_GLOSSES:
                prep_phrase_noun_indices.add(t["index"])
                p_gl = PREP_GLOSSES[t["proclitic"]]
                n_is_def = t["definiteness"] == "definite"
                n_en, n_id = _lookup_noun_gloss(t["surface"], t["bare"], t["is_sound_masc_plural"], n_is_def)
                prep_phrases.append({
                    "prep": t["proclitic"],
                    "noun_idx": t["index"],
                    "en": f"{p_gl['en']} {n_en}",
                    "id": f"{p_gl['id']} {n_id}",
                })

        # Free clause nouns available for core arguments (Fāʿil / Mafʿūl / Nāʾib)
        clause_nouns = [n for n in noun_tiles if n["index"] not in prep_phrase_noun_indices]

        # Partition into NOM (Subject candidates) and ACC (Object candidates)
        nom_nouns = [n for n in clause_nouns if n["user_case"] == "NOM"]
        acc_nouns = [n for n in clause_nouns if n["user_case"] in ("ACC", "ACC_OR_GEN")]

        # -------------------------------------------------------------------
        # PASSIVE SENTENCE
        # -------------------------------------------------------------------
        if is_passive:
            word_order = "PASSIVE_V_NAIB"
            if nom_nouns:
                naib = nom_nouns[0]
                n_is_def = naib["definiteness"] == "definite"
                n_en, n_id = _lookup_noun_gloss(naib["surface"], naib["bare"], naib["is_sound_masc_plural"], n_is_def)
                roles["PATIENT"] = SemanticRole(
                    role="PATIENT",
                    tile_index=naib["index"],
                    surface=naib["surface"],
                    gloss_en=n_en,
                    gloss_id=n_id,
                    case_assigned="NOM",
                    source="OVERT_NOUN",
                )
                translation_en = f"{n_en.capitalize()} {v_gl['passive_past']}."
                translation_id = f"{n_id.capitalize()} {v_gl['passive_id']}."
            else:
                translation_en = f"Was {v_gl['passive_past']}."
                translation_id = f"{v_gl['passive_id'].capitalize()}."

            if prep_phrases:
                pp = prep_phrases[0]
                translation_en = translation_en.rstrip(".") + f" {pp['en']}."
                translation_id = translation_id.rstrip(".") + f" {pp['id']}."
                roles["LOCATION"] = SemanticRole(
                    role="LOCATION",
                    tile_index=pp["noun_idx"],
                    surface=pp["prep"],
                    gloss_en=pp["en"],
                    gloss_id=pp["id"],
                    case_assigned="GEN",
                    source="PREPOSITIONAL_PHRASE",
                )

            info_note = "Passive Voice (Mabnī lil-Majhūl): The doer/agent is unmentioned, and the receiver takes Nominative case as Deputy Subject (Nāʾib al-Fāʿil)."
            return SemanticBindingResult(
                is_valid=True,
                word_order=word_order,
                voice=voice,
                roles=roles,
                translation_en=translation_en,
                translation_id=translation_id,
                info_structure_note=info_note,
            )

        # -------------------------------------------------------------------
        # ACTIVE SENTENCE
        # -------------------------------------------------------------------
        agent_role: SemanticRole | None = None
        patient_role: SemanticRole | None = None

        # Case A: Attached subject pronoun on verb (e.g. نَصَرْتُ, نَصَرُوا)
        if v["attached_subject_pronoun"]:
            sfx = v["attached_subject_pronoun"]
            pr_info = PRONOUN_SUFFIX_GLOSS.get(sfx, {"agent_en": "they", "agent_id": "mereka"})

            preceding_subj = [n for n in clause_nouns if n["index"] < v_idx and n["user_case"] == "NOM"]
            if preceding_subj:
                # SVO / Jumlah Ismiyyah with fronted topic
                topic = preceding_subj[-1]
                t_is_def = topic["definiteness"] == "definite"
                t_en, t_id = _lookup_noun_gloss(topic["surface"], topic["bare"], topic["is_sound_masc_plural"], t_is_def)
                agent_role = SemanticRole(
                    role="AGENT",
                    tile_index=topic["index"],
                    surface=topic["surface"],
                    gloss_en=t_en,
                    gloss_id=t_id,
                    case_assigned="NOM",
                    source="OVERT_NOUN",
                )
                roles["AGENT"] = agent_role
                roles["TOPIC"] = agent_role
                word_order = "SVO"
                info_note = "Nominal Order (SVO): The subject is fronted as Topic (Mubtadaʾ), followed by a verbal predicate agreeing in number and gender."
            else:
                agent_role = SemanticRole(
                    role="AGENT",
                    tile_index=v["index"],
                    surface=v["surface"],
                    gloss_en=pr_info["agent_en"],
                    gloss_id=pr_info["agent_id"],
                    case_assigned=None,
                    source="ATTACHED_PRONOUN",
                )
                roles["AGENT"] = agent_role
                word_order = "VSO"
                info_note = None

            if acc_nouns:
                obj = acc_nouns[0]
                n_is_def = obj["definiteness"] == "definite"
                n_en, n_id = _lookup_noun_gloss(obj["surface"], obj["bare"], obj["is_sound_masc_plural"], n_is_def)
                patient_role = SemanticRole(
                    role="PATIENT",
                    tile_index=obj["index"],
                    surface=obj["surface"],
                    gloss_en=n_en,
                    gloss_id=n_id,
                    case_assigned="ACC",
                    source="OVERT_NOUN",
                )
                roles["PATIENT"] = patient_role

            trans_en = f"{agent_role.gloss_en.capitalize()} {v_gl['active_past']}"
            trans_id = f"{agent_role.gloss_id.capitalize()} {v_gl['active_id']}"
            if patient_role:
                trans_en += f" {patient_role.gloss_en}"
                trans_id += f" {patient_role.gloss_id}"
            if prep_phrases:
                trans_en += f" {prep_phrases[0]['en']}"
                trans_id += f" {prep_phrases[0]['id']}"
            return SemanticBindingResult(
                is_valid=True,
                word_order=word_order,
                voice=voice,
                roles=roles,
                translation_en=trans_en + ".",
                translation_id=trans_id + ".",
                info_structure_note=info_note,
            )

        # Case B: Overt Nouns (VSO vs VOS vs SVO)
        # Determine roles strictly from CASE:
        #   NOM -> AGENT (Fāʿil)
        #   ACC -> PATIENT (Mafʿūl bihi)
        if nom_nouns:
            subj_noun = nom_nouns[0]
            n_is_def = subj_noun["definiteness"] == "definite"
            n_en, n_id = _lookup_noun_gloss(subj_noun["surface"], subj_noun["bare"], subj_noun["is_sound_masc_plural"], n_is_def)
            agent_role = SemanticRole(
                role="AGENT",
                tile_index=subj_noun["index"],
                surface=subj_noun["surface"],
                gloss_en=n_en,
                gloss_id=n_id,
                case_assigned="NOM",
                source="OVERT_NOUN",
            )
            roles["AGENT"] = agent_role

        if acc_nouns:
            obj_noun = acc_nouns[0]
            n_is_def = obj_noun["definiteness"] == "definite"
            n_en, n_id = _lookup_noun_gloss(obj_noun["surface"], obj_noun["bare"], obj_noun["is_sound_masc_plural"], n_is_def)
            patient_role = SemanticRole(
                role="PATIENT",
                tile_index=obj_noun["index"],
                surface=obj_noun["surface"],
                gloss_en=n_en,
                gloss_id=n_id,
                case_assigned="ACC",
                source="OVERT_NOUN",
            )
            roles["PATIENT"] = patient_role

        if prep_phrases:
            pp = prep_phrases[0]
            roles["LOCATION"] = SemanticRole(
                role="LOCATION",
                tile_index=pp["noun_idx"],
                surface=pp["prep"],
                gloss_en=pp["en"],
                gloss_id=pp["id"],
                case_assigned="GEN",
                source="PREPOSITIONAL_PHRASE",
            )

        # Determine exact word order and rhetorical packaging
        if agent_role and patient_role:
            agent_idx = agent_role.tile_index or 0
            patient_idx = patient_role.tile_index or 0

            # V-S-O: Verb < Agent < Patient (Standard unmarked word order)
            if v_idx < agent_idx < patient_idx:
                word_order = "VSO"
                translation_en = f"{agent_role.gloss_en.capitalize()} {v_gl['active_past']} {patient_role.gloss_en}."
                translation_id = f"{agent_role.gloss_id.capitalize()} {v_gl['active_id']} {patient_role.gloss_id}."
                info_note = "Standard Verbal Order (VSO): The verb is followed by the Doer (Fāʿil), then the Receiver (Mafʿūl bihi)."

            # V-O-S: Verb < Patient < Agent (Fronted Object for topicalization/focus)
            elif v_idx < patient_idx < agent_idx:
                word_order = "VOS"
                translation_en = f"It was {patient_role.gloss_en} whom {agent_role.gloss_en} {v_gl['active_past']}."
                translation_id = f"{patient_role.gloss_id.capitalize()}-lah yang {v_gl['active_id']} {agent_role.gloss_id}."
                info_note = (
                    f"Fronted Object (Mafʿūl bihi muqaddam): '{patient_role.surface}' carries fatḥah (ACC) "
                    f"and is placed before the doer '{agent_role.surface}' (NOM with ḍammah) for focus or topicalization."
                )

            # S-V-O: Agent < Verb < Patient (Nominal Topicalization / Jumlah Ismiyyah)
            elif agent_idx < v_idx < patient_idx:
                word_order = "SVO"
                translation_en = f"{agent_role.gloss_en.capitalize()} {v_gl['active_past']} {patient_role.gloss_en}."
                translation_id = f"{agent_role.gloss_id.capitalize()} {v_gl['active_id']} {patient_role.gloss_id}."
                info_note = "Nominal Order (SVO): The subject is fronted as Topic (Mubtadaʾ), followed by a verbal predicate clause."

            # O-V-S: Patient < Verb < Agent
            elif patient_idx < v_idx < agent_idx:
                word_order = "OVS"
                translation_en = f"{patient_role.gloss_en.capitalize()}, {agent_role.gloss_en} {v_gl['active_past']}."
                translation_id = f"{patient_role.gloss_id.capitalize()}, {agent_role.gloss_id} {v_gl['active_id']}."
                info_note = "Preposed Object (Mafʿūl bihi muqaddam wujūban/jawāzan): Object fronted before the entire sentence."
            else:
                word_order = "VSO"
                translation_en = f"{agent_role.gloss_en.capitalize()} {v_gl['active_past']} {patient_role.gloss_en}."
                translation_id = f"{agent_role.gloss_id.capitalize()} {v_gl['active_id']} {patient_role.gloss_id}."

        elif agent_role and not patient_role:
            # Intransitive verb or omitted object (e.g. ذَهَبَ الرَّجُلُ)
            word_order = "VSO" if v_idx < (agent_role.tile_index or 0) else "SVO"
            translation_en = f"{agent_role.gloss_en.capitalize()} {v_gl['active_past']}."
            translation_id = f"{agent_role.gloss_id.capitalize()} {v_gl['active_id']}."

        else:
            # Latent 3rd person singular subject (e.g. نَصَرَ الرَّجُلَ -> He helped the man)
            word_order = "VSO"
            trans_en = f"He {v_gl['active_past']}"
            trans_id = f"Dia {v_gl['active_id']}"
            if patient_role:
                trans_en += f" {patient_role.gloss_en}"
                trans_id += f" {patient_role.gloss_id}"
            translation_en = trans_en + "."
            translation_id = trans_id + "."

        if prep_phrases and "LOCATION" in roles:
            pp = prep_phrases[0]
            translation_en = translation_en.rstrip(".") + f" {pp['en']}."
            translation_id = translation_id.rstrip(".") + f" {pp['id']}."

        return SemanticBindingResult(
            is_valid=True,
            word_order=word_order,
            voice=voice,
            roles=roles,
            translation_en=translation_en,
            translation_id=translation_id,
            info_structure_note=info_note,
        )

    # -----------------------------------------------------------------------
    # SCENARIO 2: INNA CLAUSE
    # -----------------------------------------------------------------------
    if inna_tiles:
        inna = inna_tiles[0]
        word_order = "INNA_SENTENCE"
        voice = "COPULAR"
        acc_nouns = [n for n in noun_tiles if n["user_case"] in ("ACC", "ACC_OR_GEN") and n["index"] > inna["index"]]
        nom_nouns = [n for n in noun_tiles if n["user_case"] == "NOM" and n["index"] > inna["index"]]

        ism_en, ism_id = ("the entity", "sesuatu")
        if acc_nouns:
            ism = acc_nouns[0]
            n_is_def = ism["definiteness"] == "definite"
            ism_en, ism_id = _lookup_noun_gloss(ism["surface"], ism["bare"], ism["is_sound_masc_plural"], n_is_def)
            roles["TOPIC"] = SemanticRole(
                role="TOPIC",
                tile_index=ism["index"],
                surface=ism["surface"],
                gloss_en=ism_en,
                gloss_id=ism_id,
                case_assigned="ACC",
                source="OVERT_NOUN",
            )

        khab_en, khab_id = ("is true", "adalah benar")
        if nom_nouns:
            khab = nom_nouns[0]
            n_is_def = khab["definiteness"] == "definite"
            khab_en, khab_id = _lookup_noun_gloss(khab["surface"], khab["bare"], khab["is_sound_masc_plural"], n_is_def)
            roles["PREDICATE"] = SemanticRole(
                role="PREDICATE",
                tile_index=khab["index"],
                surface=khab["surface"],
                gloss_en=khab_en,
                gloss_id=khab_id,
                case_assigned="NOM",
                source="OVERT_NOUN",
            )

        translation_en = f"Indeed, {ism_en} is {khab_en}."
        translation_id = f"Sesungguhnya {ism_id} adalah {khab_id}."
        info_note = f"Inna Sentence (Jumlah Nāsikhah): '{inna['surface']}' establishes certainty and emphasis, assigning Accusative to its noun (Ism) and Nominative to its predicate (Khabar)."

        return SemanticBindingResult(
            is_valid=True,
            word_order=word_order,
            voice=voice,
            roles=roles,
            translation_en=translation_en,
            translation_id=translation_id,
            info_structure_note=info_note,
        )

    # -----------------------------------------------------------------------
    # SCENARIO 3: KĀNA CLAUSE
    # -----------------------------------------------------------------------
    if kana_tiles:
        kana = kana_tiles[0]
        word_order = "KANA_SENTENCE"
        voice = "COPULAR"
        nom_nouns = [n for n in noun_tiles if n["user_case"] == "NOM" and n["index"] > kana["index"]]
        acc_nouns = [n for n in noun_tiles if n["user_case"] in ("ACC", "ACC_OR_GEN") and n["index"] > kana["index"]]

        ism_en, ism_id = ("the entity", "sesuatu")
        if nom_nouns:
            ism = nom_nouns[0]
            n_is_def = ism["definiteness"] == "definite"
            ism_en, ism_id = _lookup_noun_gloss(ism["surface"], ism["bare"], ism["is_sound_masc_plural"], n_is_def)
            roles["TOPIC"] = SemanticRole(
                role="TOPIC",
                tile_index=ism["index"],
                surface=ism["surface"],
                gloss_en=ism_en,
                gloss_id=ism_id,
                case_assigned="NOM",
                source="OVERT_NOUN",
            )

        khab_en, khab_id = ("known", "diketahui")
        if acc_nouns:
            khab = acc_nouns[0]
            n_is_def = khab["definiteness"] == "definite"
            khab_en, khab_id = _lookup_noun_gloss(khab["surface"], khab["bare"], khab["is_sound_masc_plural"], n_is_def)
            roles["PREDICATE"] = SemanticRole(
                role="PREDICATE",
                tile_index=khab["index"],
                surface=khab["surface"],
                gloss_en=khab_en,
                gloss_id=khab_id,
                case_assigned="ACC",
                source="OVERT_NOUN",
            )

        translation_en = f"{ism_en.capitalize()} was {khab_en}."
        translation_id = f"{ism_id.capitalize()} dulunya adalah {khab_id}."
        info_note = f"Kāna Sentence (Jumlah Nāsikhah): '{kana['surface']}' indicates past state, assigning Nominative to its subject (Ism Kāna) and Accusative to its predicate (Khabar Kāna)."

        return SemanticBindingResult(
            is_valid=True,
            word_order=word_order,
            voice=voice,
            roles=roles,
            translation_en=translation_en,
            translation_id=translation_id,
            info_structure_note=info_note,
        )

    # -----------------------------------------------------------------------
    # SCENARIO 4: EQUATIONAL / IDĀFAH / PREPOSITIONAL NOMINAL SENTENCE
    # -----------------------------------------------------------------------
    # Case A: Two nouns forming Iḍāfah (e.g. كِتَابُ الرَّجُلِ)
    if len(noun_tiles) >= 2 and noun_tiles[1]["user_case"] in ("GEN", "ACC_OR_GEN"):
        n1 = noun_tiles[0]
        n2 = noun_tiles[1]
        n1_en, n1_id = _lookup_noun_gloss(n1["surface"], n1["bare"], n1["is_sound_masc_plural"], is_def=False)
        n2_en, n2_id = _lookup_noun_gloss(n2["surface"], n2["bare"], n2["is_sound_masc_plural"], is_def=True)

        roles["POSSESSOR"] = SemanticRole(
            role="POSSESSOR",
            tile_index=n2["index"],
            surface=n2["surface"],
            gloss_en=n2_en,
            gloss_id=n2_id,
            case_assigned="GEN",
            source="OVERT_NOUN",
        )
        roles["TOPIC"] = SemanticRole(
            role="TOPIC",
            tile_index=n1["index"],
            surface=n1["surface"],
            gloss_en=n1_en,
            gloss_id=n1_id,
            case_assigned="NOM",
            source="OVERT_NOUN",
        )

        if len(noun_tiles) >= 3:
            pred = noun_tiles[2]
            pred_en, pred_id = _lookup_noun_gloss(pred["surface"], pred["bare"], False, is_def=False)
            roles["PREDICATE"] = SemanticRole(
                role="PREDICATE",
                tile_index=pred["index"],
                surface=pred["surface"],
                gloss_en=pred_en,
                gloss_id=pred_id,
                case_assigned="NOM",
                source="OVERT_NOUN",
            )
            translation_en = f"{n2_en}'s {n1_en} is {pred_en}."
            translation_id = f"{n1_id} milik {n2_id} adalah {pred_id}."
        else:
            translation_en = f"{n2_en}'s {n1_en}"
            translation_id = f"{n1_id} milik {n2_id}"

        return SemanticBindingResult(
            is_valid=True,
            word_order="IDĀFAH",
            voice="NON_VERBAL",
            roles=roles,
            translation_en=translation_en,
            translation_id=translation_id,
            info_structure_note="Annexation Construct (Iḍāfah): The first noun (Muḍāf) is possessed by the second noun (Muḍāf ilayhi).",
        )

    # Case B: Standard Equational Sentence (Mubtada' + Khabar, e.g. الرَّجُلُ عَالِمٌ)
    if len(noun_tiles) >= 2:
        mubt = noun_tiles[0]
        khab = noun_tiles[1]
        m_en, m_id = _lookup_noun_gloss(mubt["surface"], mubt["bare"], mubt["is_sound_masc_plural"], is_def=True)
        k_en, k_id = _lookup_noun_gloss(khab["surface"], khab["bare"], khab["is_sound_masc_plural"], is_def=False)

        roles["TOPIC"] = SemanticRole(
            role="TOPIC",
            tile_index=mubt["index"],
            surface=mubt["surface"],
            gloss_en=m_en,
            gloss_id=m_id,
            case_assigned="NOM",
            source="OVERT_NOUN",
        )
        roles["PREDICATE"] = SemanticRole(
            role="PREDICATE",
            tile_index=khab["index"],
            surface=khab["surface"],
            gloss_en=k_en,
            gloss_id=k_id,
            case_assigned="NOM",
            source="OVERT_NOUN",
        )
        return SemanticBindingResult(
            is_valid=True,
            word_order="NOMINAL",
            voice="NON_VERBAL",
            roles=roles,
            translation_en=f"{m_en.capitalize()} is {k_en}.",
            translation_id=f"{m_id.capitalize()} adalah {k_id}.",
            info_structure_note="Equational Nominal Sentence (Jumlah Ismiyyah): Both Subject (Mubtadaʾ) and Predicate (Khabar) are in the Nominative case.",
        )

    # Fallback for single noun or fragment
    if noun_tiles:
        n = noun_tiles[0]
        n_is_def = n["definiteness"] == "definite"
        n_en, n_id = _lookup_noun_gloss(n["surface"], n["bare"], n["is_sound_masc_plural"], n_is_def)
        return SemanticBindingResult(
            is_valid=True,
            word_order="FRAGMENT",
            voice="NON_VERBAL",
            roles={"TOPIC": SemanticRole(role="TOPIC", tile_index=n["index"], surface=n["surface"], gloss_en=n_en, gloss_id=n_id, case_assigned=n["user_case"], source="OVERT_NOUN")},
            translation_en=n_en.capitalize() + ".",
            translation_id=n_id.capitalize() + ".",
            info_structure_note=None,
        )

    return SemanticBindingResult(
        is_valid=True,
        word_order="UNKNOWN",
        voice="NON_VERBAL",
        roles={},
        translation_en="[Empty or unparsed phrase]",
        translation_id="[Frasa kosong]",
        info_structure_note=None,
    )


# ---------------------------------------------------------------------------
# CLI & SELF TEST
# ---------------------------------------------------------------------------

def selftest() -> int:
    """Run minimal pair role-flipping verification (Gate G8)."""
    print("=" * 80)
    print("RUNNING SEMANTIC BINDER SELF-TEST (GATE G8: DIACRITIC ROLE-FLIPPING)")
    print("=" * 80)
    failures = []

    def check(cond: bool, msg: str):
        status = "OK " if cond else "FAIL"
        print(f"  [{status}] {msg}")
        if not cond:
            failures.append(msg)

    # Minimal Pair 1: ضَرَبَ زَيْدٌ عَمْرًا vs ضَرَبَ زَيْدًا عَمْرٌ
    p1_vso = bind_semantics(["ضَرَبَ", "زَيْدٌ", "عَمْرًا"])
    p1_vos = bind_semantics(["ضَرَبَ", "زَيْدًا", "عَمْرٌ"])

    check(p1_vso.is_valid and p1_vso.roles["AGENT"].surface == "زَيْدٌ" and p1_vso.roles["PATIENT"].surface == "عَمْرًا",
          "Minimal Pair 1 (VSO): 'ضَرَبَ زَيْدٌ عَمْرًا' -> AGENT=Zayd, PATIENT='Amr")
    check(p1_vos.is_valid and p1_vos.roles["AGENT"].surface == "عَمْرٌ" and p1_vos.roles["PATIENT"].surface == "زَيْدًا",
          "Minimal Pair 1 (VOS): 'ضَرَبَ زَيْدًا عَمْرٌ' -> AGENT='Amr, PATIENT=Zayd (FLIPPED VIA DIACRITIC!)")
    check("Zayd struck 'Amr" in p1_vso.translation_en, "VSO Translation reflects Zayd as doer")
    check("whom Zayd" not in p1_vos.translation_en and ("whom 'Amr struck" in p1_vos.translation_en or "Zayd whom 'Amr" in p1_vos.translation_en),
          "VOS Translation reflects 'Amr as doer and Zayd as fronted object")

    # Minimal Pair 2: نَصَرَ المُسْلِمُ الرَّجُلَ vs نَصَرَ المُسْلِمَ الرَّجُلُ
    p2_vso = bind_semantics(["نَصَرَ", "المُسْلِمُ", "الرَّجُلَ"])
    p2_vos = bind_semantics(["نَصَرَ", "المُسْلِمَ", "الرَّجُلُ"])

    check(p2_vso.is_valid and p2_vso.roles["AGENT"].surface == "المُسْلِمُ" and p2_vso.roles["PATIENT"].surface == "الرَّجُلَ",
          "Minimal Pair 2 (VSO): 'نَصَرَ المُسْلِمُ الرَّجُلَ' -> AGENT=Muslim, PATIENT=man")
    check(p2_vos.is_valid and p2_vos.roles["AGENT"].surface == "الرَّجُلُ" and p2_vos.roles["PATIENT"].surface == "المُسْلِمَ",
          "Minimal Pair 2 (VOS): 'نَصَرَ المُسْلِمَ الرَّجُلُ' -> AGENT=man, PATIENT=Muslim (FLIPPED VIA DIACRITIC!)")
    check(p2_vos.info_structure_note is not None and "Fronted Object" in p2_vos.info_structure_note,
          "VOS triggers rhetorical fronted object note")

    # Minimal Pair 3: Active vs Passive
    # Active: نَصَرَ الرَّجُلُ المُسْلِمَ
    # Passive: نُصِرَ المُسْلِمُ
    p3_active = bind_semantics(["نَصَرَ", "الرَّجُلُ", "المُسْلِمَ"])
    p3_passive = bind_semantics(["نُصِرَ", "المُسْلِمُ"])

    check(p3_active.voice == "ACTIVE" and p3_active.roles["AGENT"].surface == "الرَّجُلُ",
          "Active voice: Agent is 'الرَّجُلُ'")
    check(p3_passive.voice == "PASSIVE" and p3_passive.roles["PATIENT"].surface == "المُسْلِمُ",
          "Passive voice: 'المُسْلِمُ' is elevated to PATIENT (Nā'ib al-Fā'il)")
    check("was helped" in p3_passive.translation_en.lower(),
          "Passive translation: 'The Muslim was helped'")
    check("ditolong" in p3_passive.translation_id.lower(),
          "Indonesian passive translation: 'Orang Muslim itu ditolong'")

    # SVO Order: المُسْلِمُونَ نَصَرُوا الرَّجُلَ
    p4_svo = bind_semantics(["المُسْلِمُونَ", "نَصَرُوا", "الرَّجُلَ"])
    check(p4_svo.is_valid and p4_svo.word_order == "SVO", "SVO Order recognized: 'المُسْلِمُونَ نَصَرُوا الرَّجُلَ'")

    # Inna Sentence: إِنَّ الرَّجُلَ عَالِمٌ
    p5_inna = bind_semantics(["إِنَّ", "الرَّجُلَ", "عَالِمٌ"])
    check(p5_inna.is_valid and p5_inna.roles["TOPIC"].surface == "الرَّجُلَ" and p5_inna.roles["PREDICATE"].surface == "عَالِمٌ",
          "Inna Sentence: TOPIC='الرَّجُلَ' (ACC), PREDICATE='عَالِمٌ' (NOM)")

    # Kāna Sentence: كَانَ الرَّجُلُ عَالِمًا
    p6_kana = bind_semantics(["كَانَ", "الرَّجُلُ", "عَالِمًا"])
    check(p6_kana.is_valid and p6_kana.roles["TOPIC"].surface == "الرَّجُلُ" and p6_kana.roles["PREDICATE"].surface == "عَالِمًا",
          "Kāna Sentence: TOPIC='الرَّجُلُ' (NOM), PREDICATE='عَالِمًا' (ACC)")

    print("=" * 80)
    if failures:
        print(f"FAILED: {len(failures)} checks failed!")
        return 1
    print("ALL SEMANTIC BINDER CHECKS PASSED (exit 0)!")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] != "--selftest":
        res = bind_semantics(sys.argv[1:])
        import json
        print(json.dumps(res.to_dict(), ensure_ascii=False, indent=2))
    else:
        sys.exit(selftest())
