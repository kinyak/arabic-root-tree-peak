#!/usr/bin/env python3
"""tests/test_sandbox_mutations.py — 100-Sentence Minimal-Pair Mutation Suite.

Verifies:
  - Gate G7: Counterfactual Naḥw Verifier Precision & Recall = 100.0% (100/100).
    50 valid sentences + 50 illegal sentences across the 8 constraint checks.
  - Gate G8: Diacritic-Sensitive Semantic Role Binding = 100.0% role-flip accuracy.
    Minimal pairs (VSO vs VOS, Active vs Passive).
  - Gate G1: Oracle Compiler Accuracy & Trace Verification.
    Verifies trace_render_triple and render_triple phonological step traces.

Zero-ML, CPU execution, strict exit 0 on pass.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

# Fix Windows console UTF-8 output
if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from nahw_verifier import verify_sentence
from semantic_binder import bind_semantics
from pedagogy import to_mizan_sarfi, trace_render_triple


# ---------------------------------------------------------------------------
# 50 VALID COUNTERFACTUAL SENTENCES
# ---------------------------------------------------------------------------
VALID_SENTENCES = [
    # 1-5: Basic VSO & Fronted Object VOS
    (["نَصَرَ", "المُسْلِمُ", "الرَّجُلَ"], "VSO Active standard order"),
    (["نَصَرَ", "المُسْلِمَ", "الرَّجُلُ"], "VOS Active fronted object"),
    (["المُسْلِمُ", "نَصَرَ", "الرَّجُلَ"], "SVO Active singular topic"),
    (["المُسْلِمُونَ", "نَصَرُوا", "الرَّجُلَ"], "SVO Active plural topic with plural verb agreement"),
    (["نَصَرَ", "المُسْلِمُونَ", "الرَّجُلَ"], "VSO Active plural subject with singular verb"),

    # 6-10: Passive Voice Mutations
    (["نُصِرَ", "المُسْلِمُ"], "Passive voice with singular deputy subject"),
    (["نُصِرَ", "المُسْلِمُونَ"], "Passive voice with plural deputy subject"),
    (["ضَرَبَ", "زَيْدٌ", "عَمْرًا"], "VSO Active striking"),
    (["ضَرَبَ", "زَيْدًا", "عَمْرٌ"], "VOS Active striking with fronted object"),
    (["ضُرِبَ", "زَيْدٌ"], "Passive voice striking"),

    # 11-15: Writing & Knowledge Roots
    (["كَتَبَ", "الوَلَدُ", "الدَّرْسَ"], "VSO Writing standard"),
    (["كَتَبَ", "الدَّرْسَ", "الوَلَدُ"], "VOS Writing fronted object"),
    (["كُتِبَ", "الدَّرْسُ"], "Passive writing"),
    (["عَلِمَ", "المُعَلِّمُ", "الحَقَّ"], "VSO Knowledge standard"),
    (["عَلِمَ", "الحَقَّ", "المُعَلِّمُ"], "VOS Knowledge fronted object"),

    # 16-20: Passive Knowledge & Reading Root
    (["عُلِمَ", "الحَقُّ"], "Passive knowledge"),
    (["قَرَأَ", "الطَّالِبُ", "الكِتَابَ"], "VSO Reading standard"),
    (["قَرَأَ", "الكِتَابَ", "الطَّالِبُ"], "VOS Reading fronted object"),
    (["قُرِئَ", "الكِتَابُ"], "Passive reading"),
    (["ذَهَبَ", "الرَّجُلُ", "إِلَى", "المَسْجِدِ"], "Intransitive motion with prepositional phrase"),

    # 21-25: Motion, Prepositional Predicates & Iḍāfah
    (["ذَهَبَ", "إِلَى", "المَسْجِدِ", "الرَّجُلُ"], "Fronted prepositional phrase"),
    (["جَلَسَ", "الوَلَدُ", "فِي", "البَيْتِ"], "Intransitive in house"),
    (["فِي", "البَيْتِ", "رَجُلٌ"], "Prepositional predicate with delayed indefinite subject"),
    (["سَمِعَ", "الرَّجُلُ", "كَلَامَ", "المُعَلِّمِ"], "Transitive verb governing an Iḍāfah chain"),
    (["كِتَابُ", "الرَّجُلِ", "جَدِيدٌ"], "Iḍāfah topic with nominative predicate"),

    # 26-30: Iḍāfah & Inna Sentences
    (["بَابُ", "المَسْجِدِ", "مَفْتُوحٌ"], "Iḍāfah mosque door is open"),
    (["طَعَامُ", "الوَلَدِ", "لَذِيذٌ"], "Iḍāfah boy food is delicious"),
    (["إِنَّ", "الرَّجُلَ", "عَالِمٌ"], "Inna sister: ACC Ism + NOM Khabar"),
    (["إِنَّ", "المُسْلِمِينَ", "صَادِقُونَ"], "Inna sister with sound plural: ACC Ism + NOM Khabar"),
    (["إِنَّ", "الحَقَّ", "وَاضِحٌ"], "Inna truth is clear"),

    # 31-35: Kāna Sentences
    (["كَانَ", "الرَّجُلُ", "عَالِمًا"], "Kāna sister: NOM Ism + ACC Khabar"),
    (["كَانَ", "المُسْلِمُونَ", "صَادِقِينَ"], "Kāna sister with sound plural: NOM Ism + ACC Khabar"),
    (["كَانَ", "البَيْتُ", "كَبِيرًا"], "Kāna house was big"),
    (["أَصْبَحَ", "الوَلَدُ", "نَشِيطًا"], "Aṣbaḥa sister: NOM Ism + ACC Khabar"),
    (["لَيْسَ", "الكِتَابُ", "صَعْبًا"], "Laysa sister: NOM Ism + ACC Khabar"),

    # 36-40: Inna Sisters & Attached Pronoun Subjects
    (["لَعَلَّ", "الفَرَجَ", "قَرِيبٌ"], "La'alla sister: ACC Ism + NOM Khabar"),
    (["لَيْتَ", "الشَّبَابَ", "عَائِدٌ"], "Layta sister: ACC Ism + NOM Khabar"),
    (["نَصَرْتُ", "المُسْلِمَ"], "Verb with attached 1sg subject pronoun + object"),
    (["نَصَرْتَ", "الرَّجُلَ"], "Verb with attached 2sg m subject pronoun + object"),
    (["نَصَرْنَا", "المُسْلِمِينَ"], "Verb with attached 1pl subject pronoun + sound plural object"),

    # 41-45: Food, Drink & Praise Roots
    (["شَرِبَ", "الرَّجُلُ", "المَاءَ"], "VSO Drinking water"),
    (["أَكَلَ", "الوَلَدُ", "الخُبْزَ"], "VSO Eating bread standard"),
    (["أَكَلَ", "الخُبْزَ", "الوَلَدُ"], "VOS Eating bread fronted object"),
    (["أُكِلَ", "الخُبْزُ"], "Passive eating bread"),
    (["حَمِدَ", "المُسْلِمُ", "اللهَ"], "VSO Praising Allah"),

    # 46-50: Creation, Opening & Purification Roots
    (["حُمِدَ", "اللهُ"], "Passive praising Allah"),
    (["فَتَحَ", "الرَّجُلُ", "البَابَ"], "VSO Opening the door"),
    (["فُتِحَ", "البَابُ"], "Passive opening the door"),
    (["خَلَقَ", "اللهُ", "العَالَمَ"], "VSO Creation of universe"),
    (["خُلِقَ", "العَالَمُ"], "Passive creation of universe"),
]


# ---------------------------------------------------------------------------
# 50 ILLEGAL COUNTERFACTUAL SENTENCES (TAGGED WITH EXPECTED VIOLATION CODES)
# ---------------------------------------------------------------------------
ILLEGAL_SENTENCES = [
    # 1-5: Check 1 (CHECK_AL_TANWIN_CLASH)
    (["الرَّجُلٌ"], "CHECK_AL_TANWIN_CLASH", "Definite article with tanwīn damma"),
    (["المُسْلِمًا"], "CHECK_AL_TANWIN_CLASH", "Definite article with tanwīn fatha"),
    (["الكِتَابٍ"], "CHECK_AL_TANWIN_CLASH", "Definite article with tanwīn kasra"),
    (["بِالْمَسْجِدٍ"], "CHECK_AL_TANWIN_CLASH", "Proclitic with definite article and tanwīn"),
    (["البَيْتٌ"], "CHECK_AL_TANWIN_CLASH", "Definite article with tanwīn"),

    # 6-10: Check 2 (CHECK_PREP_GENITIVE)
    (["إِلَى", "المَسْجِدُ"], "CHECK_PREP_GENITIVE", "Preposition followed by nominative noun"),
    (["فِي", "البَيْتَ"], "CHECK_PREP_GENITIVE", "Preposition followed by accusative noun"),
    (["مِنْ", "رَجُلٌ"], "CHECK_PREP_GENITIVE", "Preposition followed by tanwīn damma"),
    (["عَلَى", "الكِتَابُ"], "CHECK_PREP_GENITIVE", "Preposition followed by nominative noun"),
    (["بِالرَّجُلُ"], "CHECK_PREP_GENITIVE", "Attached preposition followed by nominative"),

    # 11-15: Check 3 (CHECK_VERB_VALENCY_AND_FAIL: Missing Fāʿil / Double ACC)
    (["نَصَرَ", "المُسْلِمَ", "الرَّجُلَ"], "CHECK_VERB_VALENCY_AND_FAIL", "Active verb with two accusative objects and no subject"),
    (["ضَرَبَ", "زَيْدًا", "عَمْرًا"], "CHECK_VERB_VALENCY_AND_FAIL", "Active verb with two accusative objects"),
    (["كَتَبَ", "الوَلَدَ", "الدَّرْسَ"], "CHECK_VERB_VALENCY_AND_FAIL", "Writing active verb with no nominative subject"),
    (["عَلِمَ", "المُعَلِّمَ", "الحَقَّ"], "CHECK_VERB_VALENCY_AND_FAIL", "Knowledge active verb with no nominative subject"),
    (["قَرَأَ", "الطَّالِبَ", "الكِتَابَ"], "CHECK_VERB_VALENCY_AND_FAIL", "Reading active verb with no nominative subject"),

    # 16-20: Check 3 (CHECK_VERB_VALENCY_AND_FAIL: Double Fāʿil Collision)
    (["نَصَرَ", "المُسْلِمُ", "الرَّجُلُ"], "CHECK_VERB_VALENCY_AND_FAIL", "Two separate nominative subjects without conjunction"),
    (["ضَرَبَ", "زَيْدٌ", "عَمْرٌ"], "CHECK_VERB_VALENCY_AND_FAIL", "Two nominative agents colliding"),
    (["كَتَبَ", "الوَلَدُ", "المُعَلِّمُ"], "CHECK_VERB_VALENCY_AND_FAIL", "Two nominative agents on writing verb"),
    (["قَرَأَ", "الطَّالِبُ", "الرَّجُلُ"], "CHECK_VERB_VALENCY_AND_FAIL", "Two nominative agents on reading verb"),
    (["أَكَلَ", "الوَلَدُ", "الرَّجُلُ"], "CHECK_VERB_VALENCY_AND_FAIL", "Two nominative agents on eating verb"),

    # 21-28: Check 4 (CHECK_PASSIVE_NAIB_FAIL: Passive with Accusative Patient)
    (["نُصِرَ", "المُسْلِمَ"], "CHECK_PASSIVE_NAIB_FAIL", "Passive verb with accusative receiver"),
    (["ضُرِبَ", "زَيْدًا"], "CHECK_PASSIVE_NAIB_FAIL", "Passive striking with accusative receiver"),
    (["كُتِبَ", "الدَّرْسَ"], "CHECK_PASSIVE_NAIB_FAIL", "Passive writing with accusative receiver"),
    (["عُلِمَ", "الحَقَّ"], "CHECK_PASSIVE_NAIB_FAIL", "Passive knowledge with accusative receiver"),
    (["قُرِئَ", "الكِتَابَ"], "CHECK_PASSIVE_NAIB_FAIL", "Passive reading with accusative receiver"),
    (["أُكِلَ", "الخُبْزَ"], "CHECK_PASSIVE_NAIB_FAIL", "Passive eating with accusative receiver"),
    (["فُتِحَ", "البَابَ"], "CHECK_PASSIVE_NAIB_FAIL", "Passive opening with accusative receiver"),
    (["خُلِقَ", "العَالَمَ"], "CHECK_PASSIVE_NAIB_FAIL", "Passive creation with accusative receiver"),

    # 29-32: Check 5 (CHECK_SVO_VSO_AGREEMENT: VSO Plural Verb Error)
    (["نَصَرُوا", "المُسْلِمُونَ", "الرَّجُلَ"], "CHECK_SVO_VSO_AGREEMENT", "VSO verb carrying plural waw before overt plural subject"),
    (["ضَرَبُوا", "المُسْلِمُونَ", "الرَّجُلَ"], "CHECK_SVO_VSO_AGREEMENT", "VSO striking with plural verb before overt subject"),
    (["كَتَبُوا", "الأَوْلَادُ", "الدَّرْسَ"], "CHECK_SVO_VSO_AGREEMENT", "VSO writing with plural verb before overt subject"),
    (["ذَهَبُوا", "الرِّجَالُ", "إِلَى", "المَسْجِدِ"], "CHECK_SVO_VSO_AGREEMENT", "VSO motion with plural verb before overt subject"),

    # 33-36: Check 5 (CHECK_SVO_VSO_AGREEMENT: SVO Singular Verb Agreement Error)
    (["المُسْلِمُونَ", "نَصَرَ", "الرَّجُلَ"], "CHECK_SVO_VSO_AGREEMENT", "SVO plural fronted topic with singular verb"),
    (["المُسْلِمُونَ", "ضَرَبَ", "الرَّجُلَ"], "CHECK_SVO_VSO_AGREEMENT", "SVO plural fronted topic with singular verb"),
    (["المُسْلِمُونَ", "كَتَبَ", "الدَّرْسَ"], "CHECK_SVO_VSO_AGREEMENT", "SVO plural fronted topic with singular verb"),
    (["المُسْلِمُونَ", "عَلِمَ", "الحَقَّ"], "CHECK_SVO_VSO_AGREEMENT", "SVO plural fronted topic with singular verb"),

    # 37-42: Check 6 (CHECK_IDAFAH_CHAIN)
    (["كِتَابٌ", "الرَّجُلِ"], "CHECK_IDAFAH_CHAIN", "Muḍāf carrying forbidden tanwīn"),
    (["بَابٌ", "المَسْجِدِ"], "CHECK_IDAFAH_CHAIN", "Muḍāf carrying forbidden tanwīn"),
    (["طَعَامٌ", "الوَلَدِ"], "CHECK_IDAFAH_CHAIN", "Muḍāf carrying forbidden tanwīn"),
    (["الْكِتَابُ", "الرَّجُلِ"], "CHECK_IDAFAH_CHAIN", "Muḍāf carrying forbidden definite article 'الـ'"),
    (["الْبَابُ", "المَسْجِدِ"], "CHECK_IDAFAH_CHAIN", "Muḍāf carrying forbidden definite article 'الـ'"),
    (["كِتَابُ", "الرَّجُلُ"], "CHECK_IDAFAH_CHAIN", "Muḍāf ilayhi not genitive (carrying nominative damma)"),

    # 43-46: Check 7 (CHECK_SOUND_PLURAL_INFLECTION)
    (["إِلَى", "المُسْلِمُونَ"], "CHECK_SOUND_PLURAL_INFLECTION", "Sound masculine plural '-ūna' used after preposition"),
    (["فِي", "المُعَلِّمُونَ"], "CHECK_SOUND_PLURAL_INFLECTION", "Sound masculine plural '-ūna' used after preposition"),
    ([{"surface": "رَأَيْتُ"}, {"surface": "المُعَلِّمَاتَ", "user_case": "ACC_INVALID_FATHA"}], "CHECK_SOUND_PLURAL_INFLECTION", "Sound feminine plural carrying forbidden fatḥah"),
    ([{"surface": "نَصَرَ"}, {"surface": "الرَّجُلُ"}, {"surface": "المُسْلِمَاتَ", "user_case": "ACC_INVALID_FATHA"}], "CHECK_SOUND_PLURAL_INFLECTION", "Sound feminine plural carrying forbidden fatḥah"),

    # 47-50: Check 8 (CHECK_INNA_KANA_GOVERNMENT)
    (["إِنَّ", "الرَّجُلُ", "عَالِمٌ"], "CHECK_INNA_KANA_GOVERNMENT", "Inna sister with nominative Ism"),
    (["إِنَّ", "الرَّجُلَ", "عَالِمًا"], "CHECK_INNA_KANA_GOVERNMENT", "Inna sister with accusative Khabar"),
    (["كَانَ", "الرَّجُلَ", "عَالِمٌ"], "CHECK_INNA_KANA_GOVERNMENT", "Kāna sister with accusative Ism"),
    (["كَانَ", "الرَّجُلُ", "عَالِمٌ"], "CHECK_INNA_KANA_GOVERNMENT", "Kāna sister with nominative Khabar"),
]


# ---------------------------------------------------------------------------
# MAIN EVALUATION RUNNER
# ---------------------------------------------------------------------------

def test_gate_g7_precision_and_recall() -> tuple[bool, int, int]:
    """Gate G7: 100/100 (100.0%) precision and recall on the mutation suite."""
    print("=" * 80)
    print("EVALUATING GATE G7: COUNTERFACTUAL NAḤW VERIFIER PRECISION & RECALL")
    print("=" * 80)
    correct = 0
    total = len(VALID_SENTENCES) + len(ILLEGAL_SENTENCES)

    # 1. Test 50 Valid Sentences
    for idx, (sent, desc) in enumerate(VALID_SENTENCES, 1):
        res = verify_sentence(sent)
        if res.is_valid:
            correct += 1
            print(f"  [VALID {idx:02d}/50 PASS] {desc}")
        else:
            v_codes = [v.code for v in res.violations]
            print(f"  [VALID {idx:02d}/50 FAIL] {desc} -> Spurious violation: {v_codes}")

    # 2. Test 50 Illegal Sentences
    for idx, (sent, exp_code, desc) in enumerate(ILLEGAL_SENTENCES, 1):
        res = verify_sentence(sent)
        if not res.is_valid and any(v.code == exp_code for v in res.violations):
            correct += 1
            print(f"  [ILLEGAL {idx:02d}/50 PASS] {desc} -> Caught {exp_code}")
        else:
            v_codes = [v.code for v in res.violations] if not res.is_valid else "VALID (MISSED)"
            print(f"  [ILLEGAL {idx:02d}/50 FAIL] {desc} -> Expected {exp_code}, Got: {v_codes}")

    rate = (correct / total) * 100.0
    passed = (correct == total)
    print(f"\nGATE G7 RESULT: {correct}/{total} ({rate:.1f}%) | Threshold: 100.0% (100/100) -> {'PASS' if passed else 'FAIL'}")
    return passed, correct, total


def test_gate_g8_semantic_role_flipping() -> tuple[bool, int, int]:
    """Gate G8: 100.0% role-flip accuracy on minimal pairs."""
    print("\n" + "=" * 80)
    print("EVALUATING GATE G8: DIACRITIC-SENSITIVE SEMANTIC ROLE FLIPPING")
    print("=" * 80)
    checks_passed = 0
    total_checks = 6

    # Minimal Pair A: ضَرَبَ زَيْدٌ عَمْرًا vs ضَرَبَ زَيْدًا عَمْرٌ
    r_a1 = bind_semantics(["ضَرَبَ", "زَيْدٌ", "عَمْرًا"])
    r_a2 = bind_semantics(["ضَرَبَ", "زَيْدًا", "عَمْرٌ"])

    if r_a1.is_valid and r_a1.roles["AGENT"].surface == "زَيْدٌ" and r_a1.roles["PATIENT"].surface == "عَمْرًا":
        checks_passed += 1
        print("  [G8 Check 1 PASS] 'ضَرَبَ زَيْدٌ عَمْرًا' -> AGENT=Zayd, PATIENT='Amr (VSO)")
    else:
        print("  [G8 Check 1 FAIL] VSO role binding mismatch")

    if r_a2.is_valid and r_a2.roles["AGENT"].surface == "عَمْرٌ" and r_a2.roles["PATIENT"].surface == "زَيْدًا":
        checks_passed += 1
        print("  [G8 Check 2 PASS] 'ضَرَبَ زَيْدًا عَمْرٌ' -> AGENT='Amr, PATIENT=Zayd (VOS Role-Flipped!)")
    else:
        print("  [G8 Check 2 FAIL] VOS role-flipping failed")

    # Minimal Pair B: نَصَرَ المُسْلِمُ الرَّجُلَ vs نَصَرَ المُسْلِمَ الرَّجُلُ
    r_b1 = bind_semantics(["نَصَرَ", "المُسْلِمُ", "الرَّجُلَ"])
    r_b2 = bind_semantics(["نَصَرَ", "المُسْلِمَ", "الرَّجُلُ"])

    if r_b1.is_valid and r_b1.roles["AGENT"].surface == "المُسْلِمُ" and r_b1.roles["PATIENT"].surface == "الرَّجُلَ":
        checks_passed += 1
        print("  [G8 Check 3 PASS] 'نَصَرَ المُسْلِمُ الرَّجُلَ' -> AGENT=Muslim, PATIENT=man (VSO)")
    else:
        print("  [G8 Check 3 FAIL] VSO role binding mismatch")

    if r_b2.is_valid and r_b2.roles["AGENT"].surface == "الرَّجُلُ" and r_b2.roles["PATIENT"].surface == "المُسْلِمَ":
        checks_passed += 1
        print("  [G8 Check 4 PASS] 'نَصَرَ المُسْلِمَ الرَّجُلُ' -> AGENT=man, PATIENT=Muslim (VOS Role-Flipped!)")
    else:
        print("  [G8 Check 4 FAIL] VOS role-flipping failed")

    # Minimal Pair C: Active vs Passive Voice
    r_c_act = bind_semantics(["نَصَرَ", "الرَّجُلُ", "المُسْلِمَ"])
    r_c_pas = bind_semantics(["نُصِرَ", "المُسْلِمُ"])

    if r_c_act.is_valid and r_c_act.roles["AGENT"].surface == "الرَّجُلُ" and r_c_act.roles["PATIENT"].surface == "المُسْلِمَ":
        checks_passed += 1
        print("  [G8 Check 5 PASS] Active 'نَصَرَ الرَّجُلُ المُسْلِمَ' -> AGENT=man, PATIENT=Muslim")
    else:
        print("  [G8 Check 5 FAIL] Active role binding failed")

    if r_c_pas.is_valid and r_c_pas.voice == "PASSIVE" and r_c_pas.roles["PATIENT"].surface == "المُسْلِمُ":
        checks_passed += 1
        print("  [G8 Check 6 PASS] Passive 'نُصِرَ المُسْلِمُ' -> PATIENT=Muslim (Nā'ib al-Fā'il)")
    else:
        print("  [G8 Check 6 FAIL] Passive role binding failed")

    passed = (checks_passed == total_checks)
    print(f"\nGATE G8 RESULT: {checks_passed}/{total_checks} ({checks_passed/total_checks*100.0:.1f}%) | Threshold: 100.0% -> {'PASS' if passed else 'FAIL'}")
    return passed, checks_passed, total_checks


def test_gate_g1_compiler_and_traces() -> tuple[bool, int, int]:
    """Gate G1: Oracle Compiler Accuracy & Phonological Step Traces."""
    print("\n" + "=" * 80)
    print("EVALUATING GATE G1: ORACLE COMPILER ACCURACY & IʿLĀL STEP TRACES")
    print("=" * 80)
    checks_passed = 0
    total_checks = 4

    # 1. Trace pin: قُلْتُ (root قول, wazan 1ُ2ْ3, tail ْتُ)
    tr_qultu = trace_render_triple(root="قول", wazan="1ُ2ْ3", case=None, stem_tail="ْتُ", token="قُلْتُ")
    has_iltiqa = any(s["rule_id"] == "iltiqāʾ al-sākinayn" and s["changed"] for s in tr_qultu)
    if has_iltiqa and len(tr_qultu) > 5:
        checks_passed += 1
        print("  [G1 Check 1 PASS] 'قُلْتُ' produces verified iltiqāʾ al-sākinayn iʿlāl trace")
    else:
        print("  [G1 Check 1 FAIL] 'قُلْتُ' missing iltiqāʾ al-sākinayn trace")

    # 2. Trace pin: مُحْتَاج (root حوج, wazan مُ1ْتَ2َ3)
    tr_muhtaj = trace_render_triple(root="حوج", wazan="مُ1ْتَ2َ3", case=None, token="مُحْتَاج")
    has_spelling = any(s["rule_id"] == "apply_spelling_resource" and s["changed"] for s in tr_muhtaj)
    if has_spelling:
        checks_passed += 1
        print("  [G1 Check 2 PASS] 'مُحْتَاج' produces verified Form VIII settled spelling trace")
    else:
        print("  [G1 Check 2 FAIL] 'مُحْتَاج' missing spelling resource trace")

    # 3. Mīzān ṣarfī converter: مُ1ْتَ2َ3 + َة -> مُفْتَعَلَة (Form VIII)
    mizan_res = to_mizan_sarfi("مُ1ْتَ2َ3", "َة")
    if mizan_res["mizan"] == "مُفْتَعَلَة" and mizan_res["form"] == "Form VIII":
        checks_passed += 1
        print("  [G1 Check 3 PASS] to_mizan_sarfi('مُ1ْتَ2َ3', 'َة') -> 'مُفْتَعَلَة' (Form VIII)")
    else:
        print(f"  [G1 Check 3 FAIL] to_mizan_sarfi failed: {mizan_res}")

    # 4. Mīzān ṣarfī converter: 1َا2ِ3 + ُونَ -> فَاعِلُونَ (Form I)
    mizan_fail = to_mizan_sarfi("1َا2ِ3", "ُونَ")
    if mizan_fail["mizan"] == "فَاعِلُونَ" and mizan_fail["form"] == "Form I":
        checks_passed += 1
        print("  [G1 Check 4 PASS] to_mizan_sarfi('1َا2ِ3', 'ُونَ') -> 'فَاعِلُونَ' (Form I)")
    else:
        print(f"  [G1 Check 4 FAIL] to_mizan_sarfi failed: {mizan_fail}")

    passed = (checks_passed == total_checks)
    print(f"\nGATE G1 RESULT: {checks_passed}/{total_checks} ({checks_passed/total_checks*100.0:.1f}%) | Threshold: >= 98.0% -> {'PASS' if passed else 'FAIL'}")
    return passed, checks_passed, total_checks


def main():
    print("=" * 80)
    print("RUNNING MILESTONE 1 VERIFICATION SUITE: GATES G1, G7, G8")
    print("=" * 80)

    g7_pass, g7_c, g7_tot = test_gate_g7_precision_and_recall()
    g8_pass, g8_c, g8_tot = test_gate_g8_semantic_role_flipping()
    g1_pass, g1_c, g1_tot = test_gate_g1_compiler_and_traces()

    print("\n" + "=" * 80)
    print("SUMMARY OF PRODUCTION GATES G1, G7, G8")
    print("=" * 80)
    print(f"  Gate G1 (Compiler & Trace Fidelity): {'PASS [100.0%]' if g1_pass else 'FAIL'}")
    print(f"  Gate G7 (Verifier Precision/Recall): {'PASS [100/100 = 100.0%]' if g7_pass else 'FAIL'}")
    print(f"  Gate G8 (Diacritic Role-Flipping)  : {'PASS [100.0%]' if g8_pass else 'FAIL'}")
    print("=" * 80)

    if g1_pass and g7_pass and g8_pass:
        print("SUCCESS: ALL MILESTONE 1 PRODUCTION GATES PASSED (exit 0)!")
        sys.exit(0)
    else:
        print("FAILURE: ONE OR MORE PRODUCTION GATES FAILED!")
        sys.exit(1)


if __name__ == "__main__":
    main()
