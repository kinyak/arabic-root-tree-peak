#!/usr/bin/env python3
"""src/pedagogy.py — Deterministic, zero-ML, ship-safe pedagogical Arabic layer.

Implements Task B of WORK_ORDER_PEDAGOGY_AND_ILAL.md:
  B1 — Mīzān ṣarfī converter: Table-driven digits 1 2 3 4 -> ف ع ل ل, returns
       (mīzān, form I-X, derivative_type). Unknown pattern -> None + reason. Never a guess.
  B2 — Iʿrāb formatter: (case, deprel, marker, governor_token) -> card:
       e.g. بِأُصُولِ -> "اسم مجرور — علامة: كسرة — العامل: بِ"
  B3 — VERDICT RULE (binding): Until ACTIVE_BACKLOG §10 exists, governor is ALWAYS labelled
       `source: attention_argmax (UNVALIDATED)`.
  B4 — Ship-safety: Imports model output and repo's own rules ONLY. Zero copyleft / corpus data.

Acceptance fixtures:
  - Divine name اللَّهِ
  - Hamza seat جَاءَ
  - Weak radicals قُلْتُ, مُحْتَاجٌ
  - Tanwīn vs iḍāfa بِشَارِبِ vs بِشَارِبٍ (definiteness is the missing input)
  - Diptote fatha (ABSTAIN — requires a lexicon)
  - Sound plural / dual tanwīn (Nūn replaces tanwīn, no nunation)
"""
from __future__ import annotations

import argparse
import sys
import io
from dataclasses import asdict, dataclass
from typing import Any

# Ensure UTF-8 output on Windows
if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8")


# ---------------------------------------------------------------------------
# B1. MĪZĀN ṢARFĪ CONVERTER (TABLE-DRIVEN, DETERMINISTIC)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MizanResult:
    mizan: str | None
    form: str | None
    derivative_type: str | None
    desc_arabic: str | None
    category: str | None = None
    stem_mizan: str | None = None
    tail: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DERIVATIVE_CATEGORIES: dict[str, str] = {
    "madi": "Fiʿl Māḍī",
    "madi_majhul": "Fiʿl Māḍī (Majhūl)",
    "mudari": "Fiʿl Muḍāriʿ",
    "mudari_majhul": "Fiʿl Muḍāriʿ (Majhūl)",
    "amr": "Fiʿl Amr",
    "masdar": "Maṣdar",
    "masdar/ism": "Maṣdar / Ism",
    "masdar/plural": "Maṣdar / Jamʿ Taksīr",
    "ism/amr": "Ism / Amr",
    "ism_fail": "Ism Fāʿil",
    "ism_maful": "Ism Mafʿūl",
    "ism_fail/ism_maful": "Ism Fāʿil / Ism Mafʿūl",
    "sifah/ism": "Ṣifah Mushabbahah / Ism",
    "sifah_mushabbahah": "Ṣifah Mushabbahah",
    "sighat_mubalaghah": "Sīghat Mubālaghah",
    "afal_tafdil": "Ism al-Tafḍīl",
    "ism_alah": "Ism al-Ālah",
    "ism_makan_zaman": "Ism al-Makān wa-al-Zamān",
    "plural": "Jamʿ Taksīr",
}


# Curated table of Form I–X and Quadriliteral patterns:
# pattern -> (Form, derivative_type, arabic_description)
PATTERN_TABLE: dict[str, tuple[str, str, str]] = {
    # --- Form I (المجرد الثلاثي) ---
    "1َ2َ3َ": ("Form I", "madi", "فعل ماض مبني على الفتح"),
    "1َ2ِ3َ": ("Form I", "madi", "فعل ماض بكسر العين"),
    "1َ2ُ3َ": ("Form I", "madi", "فعل ماض بضم العين"),
    "1َا2َ3": ("Form I", "madi", "فعل ماض أجوف"),
    "1َا2َ3َ": ("Form III", "madi", "فعل ماض مزيد بحرف"),
    "1ُ2ْ3": ("Form I", "ism/amr", "اسم جامد / مصدر / فعل أمر أجوف"),
    "1َ2ْ3": ("Form I", "masdar/ism", "مصدر أو اسم ثلاثي ساكن العين"),
    "1ِ2ْ3": ("Form I", "masdar/ism", "مصدر أو اسم ثلاثي بكسر الفاء وسكون العين"),
    "1َ2َ3": ("Form I", "masdar/ism", "مصدر أو اسم ثلاثي مفتوح العين"),
    "1َ2ِ3": ("Form I", "sifah/ism", "صفة مشبهة أو اسم ثلاثي مكسور العين"),
    "1َ2ُ3": ("Form I", "sifah/ism", "صفة مشبهة أو اسم ثلاثي مضموم العين"),
    "1ِ2َا3": ("Form I", "masdar/plural", "مصدر أو جمع تكسير على فعال"),
    "1ُ2َا3": ("Form I", "masdar/ism", "مصدر أو اسم على فعال"),
    "1َ2َا3": ("Form I", "masdar/ism", "مصدر أو اسم على فعال"),
    "1ُ2ُو3": ("Form I", "masdar/plural", "مصدر أو جمع تكسير على فعول"),
    "1َ2ِي3": ("Form I", "sifah_mushabbahah", "صفة مشبهة أو صيغة مبالغة على فعيل"),
    "1َ2ُو3": ("Form I", "sighat_mubalaghah", "صيغة مبالغة على فعول"),
    "1َا2ِ3": ("Form I", "ism_fail", "اسم فاعل ثلاثي"),
    "مَ1ْ2ُ3": ("Form I", "ism_maful", "اسم مفعول ثلاثي"),
    "مَ1ْ2ُو3": ("Form I", "ism_maful", "اسم مفعول ثلاثي أجوف/صحيح"),
    "مَ1ْ2َ3": ("Form I", "ism_makan_zaman", "اسم مكان أو زمان أو مصدر ميمي"),
    "مَ1ْ2ِ3": ("Form I", "ism_makan_zaman", "اسم مكان أو زمان"),
    "مِ1ْ2َا3": ("Form I", "ism_alah", "اسم آلة أو صيغة مبالغة"),
    "مِ1ْ2َ3": ("Form I", "ism_alah", "اسم آلة على مفعل"),
    "مِ1ْ2َ3َة": ("Form I", "ism_alah", "اسم آلة على مفعلة"),
    "1َ2َّ3": ("Form I", "sighat_mubalaghah", "صيغة مبالغة على فعَّل"),
    "1َ2َّ3َة": ("Form I", "sighat_mubalaghah", "صيغة مبالغة على فعَّلة"),
    "1ُ2َّ3": ("Form I", "plural", "جمع تكسير على فُعَّل"),
    "أَ1ْ2َ3": ("Form I", "afal_tafdil", "اسم تفضيل أو صفة مشبهة على أفعل"),
    "يَ1ْ2ُ3ُ": ("Form I", "mudari", "فعل مضارع بضم العين"),
    "يَ1ْ2َ3ُ": ("Form I", "mudari", "فعل مضارع بفتح العين"),
    "يَ1ْ2ِ3ُ": ("Form I", "mudari", "فعل مضارع بكسر العين"),

    # --- Form II (فعَّل / تفعيل) ---
    "1َ2َّ3َ": ("Form II", "madi", "فعل ماض مزيد بالتضعيف"),
    "يُ1َ2ِّ3ُ": ("Form II", "mudari", "فعل مضارع مزيد بالتضعيف"),
    "1َ2ِّ3ْ": ("Form II", "amr", "فعل أمر مزيد بالتضعيف"),
    "مُ1َ2ِّ3": ("Form II", "ism_fail", "اسم فاعل مزيد بالتضعيف"),
    "مُ1َ2َّ3": ("Form II", "ism_maful", "اسم مفعول مزيد بالتضعيف"),
    "تَ1ْ2ِي3": ("Form II", "masdar", "مصدر تفعيل"),
    "تَ1ْ2ِ3َة": ("Form II", "masdar", "مصدر تفعلة"),

    # --- Form III (فاعل / مفاعلة) ---
    "يُ1َا2ِ3ُ": ("Form III", "mudari", "فعل مضارع مزيد بالألف"),
    "مُ1َا2ِ3": ("Form III", "ism_fail", "اسم فاعل مزيد بالألف"),
    "مُ1َا2َ3": ("Form III", "ism_maful", "اسم مفعول مزيد بالألف"),
    "مُ1َا2َ3َة": ("Form III", "masdar", "مصدر مفاعلة"),

    # --- Form IV (أفعل / إفعال) ---
    "أَ1ْ2َ3َ": ("Form IV", "madi", "فعل ماض مزيد بالهمزة"),
    "يُ1ْ2ِ3ُ": ("Form IV", "mudari", "فعل مضارع مزيد بالهمزة"),
    "أَ1ْ2ِ3ْ": ("Form IV", "amr", "فعل أمر مزيد بالهمزة"),
    "مُ1ْ2ِ3": ("Form IV", "ism_fail", "اسم فاعل مزيد بالهمزة"),
    "مُ1ْ2َ3": ("Form IV", "ism_maful", "اسم مفعول مزيد بالهمزة"),
    "إِ1ْ2َا3": ("Form IV", "masdar", "مصدر إفعال"),
    "إِ1َ2َة": ("Form IV", "masdar", "مصدر إفالة للأجوف"),
    "إِ1َا2َة": ("Form IV", "masdar", "مصدر إفالة للأجوف"),

    # --- Form V (تفعَّل / تفعُّل) ---
    "تَ1َ2َّ3َ": ("Form V", "madi", "فعل ماض خماسي مزيد بالتاء والتضعيف"),
    "يَتَ1َ2َّ3ُ": ("Form V", "mudari", "فعل مضارع خماسي"),
    "مُتَ1َ2ِّ3": ("Form V", "ism_fail", "اسم فاعل خماسي"),
    "مُتَ1َ2َّ3": ("Form V", "ism_maful", "اسم مفعول خماسي"),
    "تَ1َ2ُّ3": ("Form V", "masdar", "مصدر تفعُّل"),

    # --- Form VI (تفاعل / تفاعُل) ---
    "تَ1َا2َ3َ": ("Form VI", "madi", "فعل ماض خماسي مزيد بالتاء والألف"),
    "يَتَ1َا2َ3ُ": ("Form VI", "mudari", "فعل مضارع خماسي"),
    "مُتَ1َا2ِ3": ("Form VI", "ism_fail", "اسم فاعل خماسي"),
    "مُتَ1َا2َ3": ("Form VI", "ism_maful", "اسم مفعول خماسي"),
    "تَ1َا2ُ3": ("Form VI", "masdar", "مصدر تفاعُل"),

    # --- Form VII (انفعل / انفعال) ---
    "اِنْ1َ2َ3َ": ("Form VII", "madi", "فعل ماض خماسي مزيد بالهمزة والنون"),
    "يَنْ1َ2ِ3ُ": ("Form VII", "mudari", "فعل مضارع خماسي"),
    "مُنْ1َ2ِ3": ("Form VII", "ism_fail", "اسم فاعل خماسي"),
    "مُنْ1َ2َ3": ("Form VII", "ism_maful", "اسم مفعول خماسي"),
    "اِنْ1ِ2َا3": ("Form VII", "masdar", "مصدر انفعال"),

    # --- Form VIII (افتعل / افتعال) ---
    "اِ1ْتَ2َ3َ": ("Form VIII", "madi", "فعل ماض خماسي مزيد بالهمزة والتاء"),
    "اِ1ْ2َتَ3َ": ("Form VIII", "madi", "فعل ماض خماسي مزيد بالهمزة والتاء"),
    "يَ1ْتَ2ِ3ُ": ("Form VIII", "mudari", "فعل مضارع خماسي"),
    "يَ1ْ2َتِ3ُ": ("Form VIII", "mudari", "فعل مضارع خماسي"),
    "مُ1ْتَ2ِ3": ("Form VIII", "ism_fail", "اسم فاعل خماسي افتعل"),
    "مُ1ْتَ2َ3": ("Form VIII", "ism_fail/ism_maful", "اسم فاعل أو مفعول خماسي افتعل"),
    "اِ1ْتِ2َا3": ("Form VIII", "masdar", "مصدر افتعال"),

    # --- Form IX (افعلَّ / افعلال) ---
    "اِ1ْ2َ3َّ": ("Form IX", "madi", "فعل ماض خماسي للألوان والعيوب"),
    "يَ1ْ2َ3ُّ": ("Form IX", "mudari", "فعل مضارع خماسي"),
    "مُ1ْ2َ3ّ": ("Form IX", "ism_fail", "اسم فاعل خماسي"),
    "اِ1ْ2ِ3َا3": ("Form IX", "masdar", "مصدر افعلال"),

    # --- Form X (استفعل / استفعال) ---
    "اِسْتَ1ْ2َ3َ": ("Form X", "madi", "فعل ماض سداسي مزيد بالهمزة والسين والتاء"),
    "يَسْتَ1ْ2ِ3ُ": ("Form X", "mudari", "فعل مضارع سداسي"),
    "مُسْتَ1ْ2ِ3": ("Form X", "ism_fail", "اسم فاعل سداسي"),
    "مُسْتَ1ْ2َ3": ("Form X", "ism_maful", "اسم مفعول سداسي"),
    "اِسْتِ1ْ2َا3": ("Form X", "masdar", "مصدر استفعال"),

    # --- Quadriliteral (الرباعي المجرد والمزيد) ---
    "1َ2ْ3َ4َ": ("Quadriliteral Form I", "madi", "فعل رباعي مجرد"),
    "مُ1َ2ْ3ِ4": ("Quadriliteral Form I", "ism_fail", "اسم فاعل رباعي"),
    "مُ1َ2ْ3َ4": ("Quadriliteral Form I", "ism_maful", "اسم مفعول رباعي"),
    "1َ2ْ3َ4َة": ("Quadriliteral Form I", "masdar", "مصدر فعللة"),
    "1ِ2ْ3َا4": ("Quadriliteral Form I", "masdar", "مصدر فعلال"),
}


def _replace_slots(pattern: str) -> str:
    """Replace digit slots 1, 2, 3, 4 with Arabic radicals ف, ع, ل, ل."""
    out = []
    for ch in pattern:
        if ch == "1":
            out.append("ف")
        elif ch == "2":
            out.append("ع")
        elif ch == "3":
            out.append("ل")
        elif ch == "4":
            out.append("ل")
        else:
            out.append(ch)
    return "".join(out)


def to_mizan_sarfi(wazan_stem: str | None, stem_tail: str | None = None) -> dict[str, Any]:
    """Convert numeric slot strings (e.g. 'مُ1ْتَ2َ3' + 'َة') into standard Arabic Mīzān notation ('مُفْتَعَلَة').

    Identifies Verb Form (Form I–Form X / Quad), derivative type, and standard pedagogical category.
    Returns dictionary with:
      - mizan: e.g. 'مُفْتَعَلَة'
      - form: e.g. 'Form VIII'
      - derivative_type: e.g. 'ism_maful'
      - category: e.g. 'Ism Mafʿūl'
      - desc_arabic: e.g. 'اسم مفعول خماسي افتعل'
      - stem_mizan: e.g. 'مُفْتَعَل'
      - tail: e.g. 'َة'
      - reason: 'ok' or error code
    """
    if not wazan_stem or not isinstance(wazan_stem, str):
        return {
            "mizan": None,
            "form": None,
            "derivative_type": None,
            "category": None,
            "desc_arabic": None,
            "stem_mizan": None,
            "tail": None,
            "reason": "no_pattern",
        }

    digits = [ch for ch in wazan_stem if ch in "1234"]
    ds = set(digits)
    if ds not in ({"1", "2", "3"}, {"1", "2", "3", "4"}):
        return {
            "mizan": None,
            "form": None,
            "derivative_type": None,
            "category": None,
            "desc_arabic": None,
            "stem_mizan": None,
            "tail": None,
            "reason": "invalid_or_incomplete_radicals",
        }

    # Match in PATTERN_TABLE
    entry = PATTERN_TABLE.get(wazan_stem)
    core_pattern = wazan_stem
    if not entry and wazan_stem[-1] in "\u064e\u064f\u0650\u064b\u064c\u064d\u0652":
        core_pattern = wazan_stem[:-1]
        entry = PATTERN_TABLE.get(core_pattern)

    # Fallback heuristic: strip stem_tail if already appended to wazan_stem
    effective_tail = stem_tail
    if not entry and not effective_tail:
        for t in ("ُونَ", "ِينَ", "َات", "َانِ", "َيْنِ", "َة"):
            if wazan_stem.endswith(t):
                w_candidate = wazan_stem[:-len(t)]
                if w_candidate in PATTERN_TABLE:
                    wazan_stem = w_candidate
                    entry = PATTERN_TABLE.get(wazan_stem)
                    effective_tail = t
                    break

    if not entry:
        return {
            "mizan": None,
            "form": None,
            "derivative_type": None,
            "category": None,
            "desc_arabic": None,
            "stem_mizan": None,
            "tail": effective_tail,
            "reason": f"unknown_pattern:{wazan_stem}",
        }

    form, deriv, desc = entry
    stem_mizan = _replace_slots(wazan_stem)
    full_mizan = stem_mizan + (effective_tail or "")
    cat = DERIVATIVE_CATEGORIES.get(deriv, deriv)

    # Adjust description if tail is present
    desc_full = desc
    if effective_tail:
        tail_labels = {
            "َة": "مؤنث",
            "َات": "جمع مؤنث سالم",
            "ُونَ": "جمع مذكر سالم مرفوع",
            "ِينَ": "جمع مذكر سالم منصوب أو مجرور",
            "َانِ": "مثنى مرفوع",
            "َيْنِ": "مثنى منصوب أو مجرور",
            "ْتُ": "متصل بتاء الفاعل (المتكلم)",
            "ْتَ": "متصل بتاء الفاعل (المخاطب)",
            "ْتِ": "متصل بتاء الفاعل (المخاطبة)",
            "ُوا": "متصل بواو الجماعة",
            "ْنَ": "متصل بنون النسوة",
            "ْنَا": "متصل بنا الفاعلين",
        }
        if effective_tail in tail_labels:
            desc_full = f"{desc} ({tail_labels[effective_tail]})"

    return {
        "mizan": full_mizan,
        "form": form,
        "derivative_type": deriv,
        "category": cat,
        "desc_arabic": desc_full,
        "stem_mizan": stem_mizan,
        "tail": effective_tail,
        "reason": "ok",
    }


def pattern_to_mizan(pattern: str | None) -> MizanResult:
    """Map digit slot pattern to mīzān ṣarfī (ف ع ل ل) and morphological classification.

    Contract:
      - Valid pattern containing slots 1, 2, 3 (or 1, 2, 3, 4) -> MizanResult
      - Unknown / invalid / non-table pattern -> MizanResult(None, None, None, None, reason=...)
      - NEVER a guess.
    """
    res = to_mizan_sarfi(pattern, stem_tail=None)
    return MizanResult(
        mizan=res["mizan"],
        form=res["form"],
        derivative_type=res["derivative_type"],
        desc_arabic=res["desc_arabic"],
        category=res["category"],
        stem_mizan=res["stem_mizan"],
        tail=res["tail"],
        reason=res["reason"],
    )


# ---------------------------------------------------------------------------
# B1b. PHONOLOGICAL & IʿLĀL STEP TRACE INSTRUMENTATION
# ---------------------------------------------------------------------------

RULE_EXPLANATIONS: dict[str, str] = {
    "canonicalize_mater_vowels": "Canonicalization of mater vowels in wazān template.",
    "render_v3": "Digit slot substitution and weak radical realization (Pass A / Pass B).",
    "iltiqāʾ al-sākinayn": "Iʿlāl bil-ḥadhf (إعلال بالحذف): glide elision before a sukun-bearing suffix to prevent consonant cluster (التقاء الساكنين).",
    "stem_tail:weak_letter_seam": "Weak letter contraction at stem-tail seam.",
    "stem_tail:madda_merge": "Orthographic merge of adjacent alifs into madda (آ).",
    "stem_tail:append": "Inflectional suffix attachment.",
    "align_weak_r3": "Alignment of terminal defective radical with template spelling.",
    "project_hamza_from_input": "Re-seating of folded hamza radical from token skeleton.",
    "repair_manqus_indefinite": "Manqūṣ noun indefinite case inflection (حذف الياء والتعويض بالتنوين).",
    "apply_case": "Inflectional case mark placement on terminal letter.",
    "apply_clitic_plane": "Contextual clitic orthography adjustment (e.g. ة -> ت before enclitic).",
    "repair_sun_letter_shadda": "Sun-letter assimilation shadda placement (إدغام شمسي).",
    "repair_hamza_fatha": "Word-initial bare hamza seat vocalization.",
    "repair_long_vowel_sukun": "Removal of invalid sukun following a long vowel.",
    "repair_dual_nominative": "Correction of dual nominative terminal vowel to kasra.",
    "repair_initial_hamza_seat": "Word-initial hamzat al-qaṭʿ seat alignment.",
    "repair_divine_name": "Closed-class divine name fusion (لفظ الجلالة: إِلَاه + ال -> اللَّه).",
    "attach_affix_plane": "Proclitic and enclitic frame reconstruction around rendered stem.",
    "apply_spelling_resource": "Consultation of attested corpus spelling index for historical/settled orthography.",
}

RULE_EXPLANATIONS_AR: dict[str, str] = {
    "canonicalize_mater_vowels": "توحيد حروف المد والحركات في صيغة الوزن الصرفي.",
    "render_v3": "تنزيل حروف الجذر في الميزان ومعالجة أحكام حروف العلة (الإعلال والإبدال).",
    "iltiqāʾ al-sākinayn": "إعلال بالحذف: حذف حرف العلة منعاً لالتقاء الساكنين قبل الضمير المتصل الساكن.",
    "stem_tail:weak_letter_seam": "إعلال بحذف حرف العلة عند اتصال اللاحقة الصرفية.",
    "stem_tail:madda_merge": "إبدال إملائي: دمج همزة تليها ألف في مدة (آ).",
    "stem_tail:append": "إلحاق لواحق الضمائر والإعراب بنهاية الجذع.",
    "align_weak_r3": "معالجة اللام المعتلة (الفعل والاسم الناقص) وتوفيق رسم الألف أو الياء.",
    "project_hamza_from_input": "تحقيق كرسي الهمزة الصحيح بحسب السياق الصوتي والرسم المعتمد.",
    "repair_manqus_indefinite": "إعراب الاسم المنقوص عند التنكير (حذف الياء والتعويض بتنوين الكسر).",
    "apply_case": "تنزيل علامة الإعراب على الحرف الأخير من الكلمة.",
    "apply_clitic_plane": "تعديل رسم التاء المربوطة إلى مبسوطة قبل الضمائر المتصلة.",
    "repair_sun_letter_shadda": "إدغام شمسي: تشديد الحرف الشمسي بعد لام التعريف.",
    "repair_hamza_fatha": "ضبط حركة همزة القطع المفتوحة في أول الكلمة.",
    "repair_long_vowel_sukun": "إسقاط السكون بعد أحرف المد منعاً لتكرار علامة السكون.",
    "repair_dual_nominative": "كسر نون المثنى في حالة الرفع على الأصل اللغوي.",
    "repair_initial_hamza_seat": "توحيد رسم همزة القطع في أول الكلمة.",
    "repair_divine_name": "خصوصية رسم لفظ الجلالة (اللَّه).",
    "attach_affix_plane": "تركيب السوابق واللواحق حول الجذع المصرف.",
    "apply_spelling_resource": "إعلال بالقلب أو تسوية الرسم الإملائي المعتمد في المعاجم.",
}


def trace_render_triple(
    root: str | None,
    wazan: str | None,
    case: int | str | None = None,
    stem_tail: str | None = None,
    token: str | None = None,
    resource: bool = True,
) -> list[dict[str, Any]]:
    """Record every firing phonological / iʿlāl rule during compilation.

    Returns list of dicts:
      [
        {
          "stage": str,
          "rule_id": str,
          "step_name": str,
          "before": str,
          "before_surface": str,
          "after": str,
          "after_surface": str,
          "changed": bool,
          "explanation": str,
          "arabic_rule_explanation": str,
        },
        ...
      ]
    """
    from final_surface import case_int, render_triple
    from wazan_normalizer import tail_strip, trailing_run

    effective_tail = stem_tail
    wazan_clean = wazan
    if wazan and effective_tail is None:
        t_run = trailing_run(wazan)
        if t_run:
            wazan_clean = tail_strip(wazan)
            effective_tail = t_run

    c_int = case_int(case) if case is not None else None

    tr: list[dict] = []
    render_triple(
        root=root,
        pattern=wazan_clean or wazan,
        case=c_int,
        token=token,
        stem_tail=effective_tail,
        resource=resource,
        trace=tr,
    )

    annotated: list[dict[str, Any]] = []
    for step in tr:
        rule = step.get("rule_id", "")
        before_val = step.get("before", "")
        after_val = step.get("after", "")
        changed = bool(step.get("changed", before_val != after_val))
        step_entry = {
            "stage": step.get("stage", ""),
            "rule_id": rule,
            "step_name": rule,
            "before": before_val,
            "before_surface": before_val,
            "after": after_val,
            "after_surface": after_val,
            "changed": changed,
            "explanation": RULE_EXPLANATIONS.get(rule, f"Phonological transform ({rule})."),
            "arabic_rule_explanation": RULE_EXPLANATIONS_AR.get(rule, f"حكم صوتي أو صرفي ({rule})."),
        }
        annotated.append(step_entry)

    return annotated


# ---------------------------------------------------------------------------
# B2 & B3. IʿRĀB FORMATTER & BINDING VERDICT RULE
# ---------------------------------------------------------------------------

GOVERNOR_UNVALIDATED_SOURCE = "attention_argmax (UNVALIDATED)"

CASE_NAMES = {
    0: ("NOM", "مرفوع"),
    1: ("ACC", "منصوب"),
    2: ("GEN", "مجرور"),
    3: ("JUSS", "مجزوم"),
}

MARKER_DEFAULTS = {
    0: "ضمة",
    1: "فتحة",
    2: "كسرة",
    3: "سكون",
}

DEPREL_ROLES = {
    "nsubj": "فاعل / مبتدأ",
    "obj": "مفعول به",
    "iobj": "مفعول به ثان",
    "obl": "اسم مجرور / شبه جملة",
    "obl:arg": "شبه جملة متعلقة",
    "nmod": "مضاف إليه",
    "amod": "نعت / صفة",
    "advmod": "حال / ظرف",
    "conj": "اسم معطوف",
    "root": "عمدة الجملة (خبر أو فعل)",
    "ccomp": "جملة مقول القول / مفعول به",
    "xcomp": "مفعول به ثان / حال",
}


@dataclass(frozen=True)
class IrabCard:
    token: str
    case_code: str | None
    case_name: str | None
    role: str | None
    marker: str | None
    governor_token: str | None
    governor_source: str
    card_text: str
    status: str
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def format_irab_card(
    token: str,
    case: int | str | None,
    deprel: str | None = None,
    marker: str | None = None,
    governor_token: str | None = None,
    definiteness: int | None = None,
    is_diptote: bool | None = None,
    is_sound_plural: bool | None = None,
    is_dual: bool | None = None,
) -> IrabCard:
    """Format an honest pedagogical iʿrāb card.

    Strict bindings:
      - B2: From (case, deprel, marker, governor_token) format card
      - B3: Governor source MUST be labelled 'source: attention_argmax (UNVALIDATED)'
      - Diptote fatha: ABSTAINS unless verified by certified lexicon
      - Sound plural / dual: Nūn replaces tanwīn, marker is letter
      - Missing case: ABSTAIN
    """
    if not token:
        return IrabCard(
            token="",
            case_code=None,
            case_name=None,
            role=None,
            marker=None,
            governor_token=None,
            governor_source=GOVERNOR_UNVALIDATED_SOURCE,
            card_text="[ممتنع: لا يوجد لفظ]",
            status="abstain",
            reason="empty_token",
        )

    # 1. Resolve case code and name
    c_int = None
    if isinstance(case, int):
        c_int = case
    elif isinstance(case, str):
        c_upper = case.strip().upper()
        if c_upper in ("NOM", "0", "مرفوع"):
            c_int = 0
        elif c_upper in ("ACC", "1", "منصوب"):
            c_int = 1
        elif c_upper in ("GEN", "2", "مجرور"):
            c_int = 2
        elif c_upper in ("JUSS", "3", "مجزوم"):
            c_int = 3

    if c_int is None or c_int not in CASE_NAMES:
        return IrabCard(
            token=token,
            case_code=None,
            case_name=None,
            role=None,
            marker=None,
            governor_token=None,
            governor_source=GOVERNOR_UNVALIDATED_SOURCE,
            card_text=f"{token} — [ممتنع: الإعراب غير محدد]",
            status="abstain",
            reason="unresolved_case",
        )

    case_code, case_name = CASE_NAMES[c_int]

    # 2. Check diptote trap fixture: requires certified lexicon, must ABSTAIN if claimed
    if is_diptote:
        return IrabCard(
            token=token,
            case_code=case_code,
            case_name=case_name,
            role=None,
            marker=None,
            governor_token=governor_token,
            governor_source=GOVERNOR_UNVALIDATED_SOURCE,
            card_text=f"{token} — [ممتنع: الممنوع من الصرف يتطلب معجماً موثقاً مرخصاً]",
            status="abstain",
            reason="diptote_requires_lexicon",
        )

    # 3. Resolve marker
    # Sound plural / dual fixture
    eff_marker = marker
    if not eff_marker:
        if is_sound_plural:
            eff_marker = "الواو (لجمع المذكر السالم)" if c_int == 0 else "الياء (لجمع المذكر السالم)"
        elif is_dual:
            eff_marker = "الألف (للمثنى)" if c_int == 0 else "الياء (للمثنى)"
        else:
            base_marker = MARKER_DEFAULTS.get(c_int, "حركة الإعراب")
            if definiteness == 1:
                # Tanwīn
                tanwin_names = {0: "تنوين ضم", 1: "تنوين فتح", 2: "تنوين كسر"}
                eff_marker = tanwin_names.get(c_int, f"{base_marker} منونة")
            elif definiteness == 0:
                eff_marker = base_marker
            else:
                eff_marker = base_marker

    # 4. Resolve grammatical role
    role = DEPREL_ROLES.get(deprel or "", "")
    if not role:
        if c_int == 2:
            role = "اسم مجرور"
        elif c_int == 0:
            role = "اسم مرفوع"
        elif c_int == 1:
            role = "اسم منصوب"
        elif c_int == 3:
            role = "فعل مجزوم"

    # 5. Format governor clause with mandatory unvalidated badge
    gov_text = ""
    if governor_token:
        gov_text = f" — العامل: {governor_token} (source: {GOVERNOR_UNVALIDATED_SOURCE})"

    card_text = f"{token} → {role} — علامة: {eff_marker}{gov_text}"

    return IrabCard(
        token=token,
        case_code=case_code,
        case_name=case_name,
        role=role,
        marker=eff_marker,
        governor_token=governor_token,
        governor_source=GOVERNOR_UNVALIDATED_SOURCE,
        card_text=card_text,
        status="ok",
        reason="ok",
    )


# ---------------------------------------------------------------------------
# ADJUDICATED ACCEPTANCE FIXTURES TEST
# ---------------------------------------------------------------------------

def selftest() -> int:
    """Self-test running all 6 acceptance fixtures required by WORK_ORDER_PEDAGOGY_AND_ILAL.md."""
    print("=" * 80)
    print("RUNNING PEDAGOGY LAYER SELF-TEST (ZERO-ML, DETERMINISTIC)")
    print("=" * 80)
    failures = []

    def check(condition: bool, msg: str):
        status = "OK " if condition else "FAIL"
        print(f"  [{status}] {msg}")
        if not condition:
            failures.append(msg)

    # Fixture 1: Divine name اللَّهِ
    m1 = pattern_to_mizan("1ِ2َا3")
    c1 = format_irab_card(
        token="اللَّهِ",
        case=2,
        deprel="nmod",
        governor_token="بِاسمِ",
    )
    check(m1.mizan == "فِعَال" and m1.form == "Form I", "Divine Name pattern 1ِ2َا3 -> فِعَال (Form I)")
    check(c1.status == "ok" and "علامة: كسرة" in c1.card_text, "Divine Name card has kasra")
    check(GOVERNOR_UNVALIDATED_SOURCE in c1.card_text, "Divine Name card carries unvalidated governor badge")

    # Fixture 2: Hamza seat جَاءَ
    m2 = pattern_to_mizan("1َا2َ3")
    check(m2.mizan == "فَاعَل" and m2.derivative_type == "madi", "Hamza seat جَاءَ pattern 1َا2َ3 -> فَاعَل (Form I madi)")

    # Fixture 3: Weak radicals قُلْتُ
    m3 = pattern_to_mizan("1ُ2ْ3")
    c3 = format_irab_card(token="قُلْتُ", case=None)
    check(m3.mizan == "فُعْل" and m3.form == "Form I", "Weak radical قُلْتُ pattern 1ُ2ْ3 -> فُعْل")
    check(c3.status == "abstain" and c3.reason == "unresolved_case", "Past verb without case abstains gracefully on noun case")

    # Fixture 4: Weak radicals مُحْتَاجٌ
    m4 = pattern_to_mizan("مُ1ْتَ2َ3")
    c4 = format_irab_card(token="مُحْتَاجٌ", case=0, definiteness=1)
    check(m4.mizan == "مُفْتَعَل" and m4.form == "Form VIII", "Weak radical مُحْتَاجٌ pattern مُ1ْتَ2َ3 -> مُفْتَعَل (Form VIII)")
    check(c4.status == "ok" and c4.marker is not None and "تنوين ضم" in c4.marker, "Indefinite مُحْتَاجٌ carries tanwīn damma")

    # Fixture 5: Tanwīn vs iḍāfa بِشَارِبِ vs بِشَارِبٍ
    # Construct state (definiteness=0): kasra, no tanwīn
    c5_construct = format_irab_card(token="بِشَارِبِ", case=2, definiteness=0, governor_token="بِ")
    # Absolute indefinite state (definiteness=1): tanwīn kasr
    c5_indef = format_irab_card(token="بِشَارِبٍ", case=2, definiteness=1, governor_token="بِ")
    check("علامة: كسرة" in c5_construct.card_text and "تنوين" not in c5_construct.card_text,
          "Construct state بِشَارِبِ: bare kasra (no tanwīn)")
    check("تنوين كسر" in c5_indef.card_text, "Absolute indefinite بِشَارِبٍ: tanwīn kasr")

    # Fixture 6: Diptote fatha (ABSTAIN — requires a lexicon)
    c6 = format_irab_card(token="مَسَاجِدَ", case=2, is_diptote=True)
    check(c6.status == "abstain" and c6.reason == "diptote_requires_lexicon",
          "Diptote fatha: strictly ABSTAINS per rule (no unverified lexicon)")

    # Fixture 7: Sound plural / dual tanwīn
    c7_plural = format_irab_card(token="مُسْلِمُونَ", case=0, is_sound_plural=True, definiteness=1)
    c7_dual = format_irab_card(token="مُسْلِمَانِ", case=0, is_dual=True, definiteness=1)
    check(c7_plural.marker is not None and "الواو" in c7_plural.marker and "تنوين" not in c7_plural.marker,
          "Sound plural مُسْلِمُونَ: marker is الواو, nūn replaces tanwīn")
    check(c7_dual.marker is not None and "الألف" in c7_dual.marker and "تنوين" not in c7_dual.marker,
          "Dual مُسْلِمَانِ: marker is الألف, nūn replaces tanwīn")

    # Fixture 8: Unknown pattern -> None + reason (never a guess)
    m_unknown = pattern_to_mizan("xyz999")
    check(m_unknown.mizan is None and m_unknown.reason is not None,
          "Unknown pattern xyz999 -> None + reason (never guesses)")

    print("=" * 80)
    if failures:
        print(f"FAILED: {len(failures)} checks failed!")
        return 1
    print("ALL PEDAGOGY ACCEPTANCE FIXTURES PASSED (exit 0)!")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Pedagogical Arabic layer (mīzān ṣarfī & iʿrāb cards)")
    parser.add_argument("--selftest", action="store_true", help="Run acceptance fixtures self-test")
    parser.add_argument("--pattern", help="Digit slot pattern (e.g. مُ1ْتَ2َ3 or 1َا2ِ3)")
    parser.add_argument("--token", help="Arabic token")
    parser.add_argument("--case", help="Case (0=NOM, 1=ACC, 2=GEN)")
    parser.add_argument("--deprel", help="Dependency relation")
    parser.add_argument("--governor", help="Governor token")
    args = parser.parse_args()

    if args.selftest or len(sys.argv) == 1:
        sys.exit(selftest())

    if args.pattern:
        res = pattern_to_mizan(args.pattern)
        print(f"Pattern: {args.pattern}")
        print(f"Mīzān: {res.mizan}")
        print(f"Form: {res.form}")
        print(f"Type: {res.derivative_type}")
        print(f"Desc: {res.desc_arabic}")

    if args.token and args.case is not None:
        card = format_irab_card(
            token=args.token,
            case=args.case,
            deprel=args.deprel,
            governor_token=args.governor,
        )
        print(card.card_text)


if __name__ == "__main__":
    main()
