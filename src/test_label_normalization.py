"""Verification for the Head-3 label pipeline: proclitic strip (Task 2), enclitic
strip, and the root-gated geminate expansion.

Runs against LIVE calima-msa-r13, not recorded fixtures — so it is a measurement,
not a restatement.  No corpus is needed, which is why it can run before the corpora
land.

WHAT IS ASSERTED
 1. The doc's worked example: المُسْتَشار -> 'مُسْتَ123' — 'ال' gone AND the missing
    slot 2 recovered from the root's '#'.
 2. Proclitic removal, incl. sun letters, and PRESERVATION of templatic material
    (مُسْتَ / أَسْتَ of Form X, the mīm of مَـ).
 3. Enclitic removal from the right edge, and that it happens BEFORE
    _map_missing_slot_literal (عليهم needs its tail weak radical recovered).
 4. The geminate gate: expansion happens for a confirmed geminate root (م.د.د) and
    NOT for a templatic shadda on a sound root (ط.ل.ب, فُعّال).
 5. The digit-set invariant, and that every emitted label is STRICT-well-formed
    (each radical digit exactly once) — which the per-shadda expansion used to break.

FINDINGS STILL RECORDED, DELIBERATELY NOT FIXED
 C. prc0-prc3 are LABELS not surfaces and prc0 is the INNERMOST clitic, so the
    docs' "strip via prc0-prc3 alignment" is not implementable from those fields.
    d3tok carries the surfaces.
 D. The MLE disambiguator never surfaces quadriliteral readings. For وَسْوَسَ the
    RAW analyser emits root '#.س.#.س' pattern 'وَ2ْوَ4َ' — exactly HANDOFF §3.4's
    example — but it is 1 of 43 candidates and the MLE returns 'وَ1َوِ3َ' (wa + سِس).
    Four-digit Head-3 labels are therefore ~never produced from CALIMA silver, and
    quadrilateral supervision must come from gold PADT + arramooz (72 awzān).
    Undiacritized 'ووس' has 0 raw candidates -> 'backoff' fallback.

NOTHING HERE IS AN ACCURACY FIGURE.  No public gold wazān exists (SPEC-REV6 §8.1
item 2); well-formedness is all that is measurable.  Say "coverage of well-formed
labels".  The corpus-scale figure is measure_normalizer_gain.py (needs PADT).
"""
from __future__ import annotations

import sys

from camel_tools.disambig.mle import MLEDisambiguator
from camel_tools.morphology.analyzer import Analyzer
from camel_tools.morphology.database import MorphologyDB

from wazan_normalizer import (DIG, expand_geminate, has_enclitic, is_geminate_root,
                              normalize_from_analysis, normalize_wazan,
                              proclitic_surface, strip_proclitic)

MLE = MLEDisambiguator.pretrained("calima-msa-r13")
RAW = Analyzer(MorphologyDB.builtin_db("calima-msa-r13"))

# word, expected proclitic, must_NOT_contain, must_contain, note
PROCLITIC_CASES = [
    ("المستشار", "ال", "ال", "", "the doc's worked example (CHALLENGES §2g)"),
    ("والكتاب", "وَال", "ال", "", "conj + article"),
    ("فبالمدرسة", "فَبِال", "ال", "مَ", "conj + prep + article"),
    ("الطلاب", "ال", "ال", "1ُ2ّا3", "article only; templatic shadda PRESERVED"),
    ("الشمس", "ال", "ال", "", "sun letter: pattern writes the article unassimilated"),
    ("بالبيت", "بِال", "ال", "", "prep + article"),
    ("مدرسة", "", "", "مَ1ْ2َ3َة", "no clitic: templatic mīm AND feminine ة survive"),
    ("استغفر", "", "", "أَسْتَ", "Form X: أَسْتَ is TEMPLATIC, not a clitic"),
]

# word, expected enclitic surface, expected label (None = just report)
ENCLITIC_CASES = [
    ("كتابه", "هُ", "1ِ2ا3"),
    ("مدرستهم", "هُم", None),
    ("وبكتابه", "هُ", "1ِ2ا3"),
    ("عليهم", "هُم", "1َ2َ3"),
]

# pattern, root, expect_expansion?
GEMINATE_CASES = [
    ("1َ2ُّ", "م.د.د", True, "true geminate (مُضاعَف) -> expand"),
    ("1ُ2ّا3", "ط.ل.ب", False, "فُعّال on a SOUND root -> templatic shadda, keep"),
    ("1َ2َّ", "خ.ب.ب", True, "geminate -> expand"),
    ("1ُ2ّا3", "ك.ت.ب", False, "كُتّاب -> keep"),
    ("1َ2َّ", "", False, "no root: cannot confirm -> do NOT expand (fail closed)"),
]


def main() -> int:
    failures: list[str] = []

    print("=" * 94)
    print("HEAD-3 LABEL PIPELINE — proclitic + enclitic strip, root-gated geminate")
    print("=" * 94)

    print(f"\n[1] PROCLITIC STRIP\n{'word':13} {'proclitic':10} {'pattern':21} "
          f"{'label':15} {'strict':7} note")
    print("-" * 94)
    for word, exp_prc, forbidden, required, note in PROCLITIC_CASES:
        a = MLE.disambiguate([word])[0].analyses[0].analysis
        rec = normalize_from_analysis(a)
        prc, label = proclitic_surface(a.get("d3tok") or ""), rec["label"] or ""
        if prc != exp_prc:
            failures.append(f"{word}: proclitic {prc!r} != {exp_prc!r}")
        if forbidden and forbidden in label:
            failures.append(f"{word}: label still has {forbidden!r} -> {label!r}")
        if required and required not in label:
            failures.append(f"{word}: lost templatic {required!r} -> {label!r}")
        if prc:
            after, stripped = strip_proclitic(a["pattern"], prc)
            if stripped and set(DIG.findall(after)) != set(DIG.findall(a["pattern"])):
                failures.append(f"{word}: strip changed the digit set")
        if rec["label"] and not rec["wellformed_strict"]:
            failures.append(f"{word}: label not STRICT well-formed -> {label!r}")
        print(f"{word:13} {prc or '-':10} {a.get('pattern','')!r:21} {label!r:15} "
              f"{'OK' if rec['wellformed_strict'] else 'BAD':7} {note}")

    print("\n--- the doc's target, asserted exactly ---")
    rec = normalize_from_analysis(MLE.disambiguate(["المستشار"])[0].analyses[0].analysis)
    print(f"  المستشار -> {rec['label']!r}   (target 'مُسْتَ123')")
    if rec["label"] != "مُسْتَ123":
        failures.append(f"worked example: got {rec['label']!r}")

    print("\n--- clitic-free words: the pattern must come back byte-identical ---")
    for w in ("مدرسة", "استغفر"):
        a = MLE.disambiguate([w])[0].analyses[0].analysis
        prc = proclitic_surface(a.get("d3tok") or "")
        out, stripped = strip_proclitic(a["pattern"], prc)
        same = out == a["pattern"]
        print(f"  {w:9} d3tok proclitic={prc!r:4} stripped={stripped!s:5} unchanged={same}")
        if stripped or not same:
            failures.append(f"{w}: templatic material was stripped")

    print(f"\n[2] ENCLITIC STRIP (right edge, from d3tok; separator '_+')\n"
          f"{'word':11} {'d3tok':22} {'enclitic':9} {'pattern':15} {'label':12} note")
    print("-" * 94)
    for word, exp_enc, exp_label in ENCLITIC_CASES:
        a = MLE.disambiguate([word])[0].analyses[0].analysis
        rec = normalize_from_analysis(a)
        got = rec["enclitic_surface"]
        if got != exp_enc:
            failures.append(f"{word}: enclitic {got!r} != {exp_enc!r}")
        if not rec["enclitic_stripped"]:
            failures.append(f"{word}: enclitic was NOT stripped -> {rec['label']!r}")
        if exp_label is not None and rec["label"] != exp_label:
            failures.append(f"{word}: label {rec['label']!r} != {exp_label!r}")
        note = ""
        if exp_label is not None and rec["label"] == exp_label:
            note = "enclitic gone; stem template recovered"
        print(f"{word:11} {a.get('d3tok',''):22} {got:9} {a.get('pattern','')!r:15} "
              f"{str(rec['label'])!r:12} {note}")
    print("  NOTE عليهم: the strip must precede _map_missing_slot_literal, or the")
    print("  enclitic shields the stem's weak radical and slot 3 is never recovered.")

    print(f"\n[3] GEMINATE GATE (root must confirm C2 == C3)\n"
          f"{'pattern':11} {'root':9} {'expand?':8} {'result':12} {'digits':8} note")
    print("-" * 94)
    for pat, root, expect, note in GEMINATE_CASES:
        out = expand_geminate(pat, root)
        did = out != pat
        if did != expect:
            failures.append(f"geminate {pat!r}/{root!r}: expanded={did}, want {expect}")
        digits = "".join(sorted(DIG.findall(out)))
        if root == "ط.ل.ب" and did:
            failures.append("templatic shadda was expanded on a sound root")
        print(f"{pat:11} {root or '-':9} {str(did):8} {out!r:12} {digits:8} {note}")
    print(f"  is_geminate_root('م.د.د')={is_geminate_root('م.د.د')}  "
          f"is_geminate_root('ط.ل.ب')={is_geminate_root('ط.ل.ب')}  "
          f"is_geminate_root('')={is_geminate_root('')}")

    print("\n--- real analyser output for a true geminate ---")
    a = MLE.disambiguate(["مدّ"])[0].analyses[0].analysis
    rec = normalize_from_analysis(a)
    print(f"  مدّ  root={a.get('root')} pattern={a.get('pattern')!r} "
          f"-> label={rec['label']!r} strict={rec['wellformed_strict']}")

    print("\n--- finding C: why the clitic string must come FROM d3tok ---")
    a = MLE.disambiguate(["فبالمدرسة"])[0].analyses[0].analysis
    print(f"  prc0..prc3 = {[a.get(f'prc{i}') for i in range(4)]}")
    print("  ^ labels ('Al_det','bi_prep','fa_conj'), no letters, prc0 INNERMOST.")

    print("\n--- finding D: the MLE never surfaces the quadriliteral ---")
    w = "وَسْوَسَ"
    raw = RAW.analyze(w)
    quads = [x for x in raw if "4" in (x.get("pattern") or "")]
    d = MLE.disambiguate([w])[0]
    best = d.analyses[0].analysis
    print(f"  raw candidates {len(raw)}; with digit 4: {len(quads)}")
    for x in quads:
        print(f"    {x.get('root')} {x.get('pattern')!r} {x.get('pos')}")
    print(f"  MLE returns {len(d.analyses)} reading(s): {best.get('root')} "
          f"{best.get('pattern')!r} prc2={best.get('prc2')}")
    if not quads:
        failures.append("finding D: raw analyser gave no digit-4 candidate")
    if quads and "4" in (best.get("pattern") or ""):
        failures.append("finding D: MLE unexpectedly selected the quadriliteral")
    print(f"  undiacritized 'ووس': {len(RAW.analyze('ووس'))} raw candidates -> backoff")

    print("\n--- backward compatibility: the 2-arg call still works ---")
    print(f"  normalize_wazan('1َ2َّ','م.د.د') -> {normalize_wazan('1َ2َّ', 'م.د.د')}")
    print(f"  normalize_wazan('1َ2َّ')         -> {normalize_wazan('1َ2َّ')}   "
          f"(no root: gate declines to expand, by design)")

    print("\n--- coverage BY WELL-FORMEDNESS (coverage, never accuracy) ---")
    recs = [normalize_from_analysis(MLE.disambiguate([w])[0].analyses[0].analysis)
            for w, *_ in PROCLITIC_CASES]
    loose = sum(1 for r in recs if r["wellformed"])
    strict = sum(1 for r in recs if r["wellformed_strict"])
    print(f"  loose (digit SET)        : {loose}/{len(recs)}")
    print(f"  strict (each digit once) : {strict}/{len(recs)}")
    print("  Before the geminate gate these two DISAGREED (الطلاب -> '1ُ23ا3' passed")
    print("  loose and failed strict). They now agree on this sample.")
    print("  A unit-test sample. NOT a corpus figure; do not quote it as one.")

    print("\n" + "=" * 94)
    if failures:
        print(f"FAILURES ({len(failures)}):")
        for f in failures:
            print("  -", f)
        return 1
    print(f"ALL PASS · worked example exact · loose={loose} strict={strict}")
    print("=" * 94)
    return 0


if __name__ == "__main__":
    sys.exit(main())
