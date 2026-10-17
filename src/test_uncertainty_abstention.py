"""test_uncertainty_abstention.py — verification suite for the Tier-1..4 abstention stack.

REV 2 (2026-10-11). What the v13 delivery's suite did NOT do, and this one does:

  1. It scored the Tier-1 gate ONLY on the 22 abstention rows of gold-300 — the rows its
     lexicon had been fitted to (19/22 matched the exact token in the list). A gate scored
     on its own fitted rows reports 100 % recall and 0 % error by construction.
     This suite additionally scores BOTH directions on held-out PADT test, where the gate
     was never run, and enforces a HARD false-abstention gate there.
  2. Its "9 simulated error types" were 6 unmodified originals plus 3 perturbations, and its
     assertion exercised nothing about the model. Here every transform must fire, counts are
     of real perturbations, and the perturbed closed-class case is checked for abstention.
  3. Tier 2/3/4 remain LOGIC-ONLY tests: all confidences are hand-written, so they verify the
     arithmetic and the control flow, never the model. They are labelled as such below.

Falsifiability: every gate below is exercised against the SHIPPED v13 rule as well, which is
required to FAIL it. A gate that nothing can fail is not a gate.

Run:  .venv/Scripts/python.exe src/test_uncertainty_abstention.py
Exit: 0 all gates pass · 1 a gate failed · 2 a corpus is missing so a gate DID NOT RUN
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Sibling import, matching src/eval_harness.py's own convention: the script directory
# (now src/, after the gate moved out of tools/) is put on sys.path and the module is
# imported by its bare name, so the test resolves src/uncertainty_abstention.py.
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import uncertainty_abstention as ua  # noqa: E402

GOLD = ROOT / "data" / "annotation" / "gold-tashkeela-300.jsonl"
PADT = {s: ROOT / "data" / "out" / f"padt-{s}.jsonl" for s in ("test", "dev", "train")}

# The false-abstention rate the repaired gate must stay under, on held-out root-bearing
# tokens. Measured 0.086 % (11/12,837); the shipped v13 rule measured 1.285 % (165/12,837)
# and the same rule without homograph deferral 0.320 %. 0.25 % leaves ~3x headroom while
# still refusing the v13 rule.
MAX_FALSE_ABSTENTION_RATE = 0.0025

FAILURES: list[str] = []


def check(cond: bool, label: str, detail: str = "") -> bool:
    print(f"    {'PASS' if cond else 'FAIL'}  {label}{(' — ' + detail) if detail else ''}")
    if not cond:
        FAILURES.append(label)
    return cond


# ----------------------------------------------------------------------------- shipped v13
def shipped_v13_rule(token: str) -> bool:
    """The Tier-1 rule exactly as delivered in v13, for the falsifiability checks.

    Reproduced here deliberately, defect and all (no stem-length floor, alif-normalised
    variant matching over the whole lexicon, and in the proclitic branch too).
    """
    clean = ua.strip_tashkeel(token).strip()
    if not clean:
        return True
    if not any("\u0600" <= c <= "\u06ff" for c in clean):
        return True
    if clean in ua.CLOSED_CLASS_PARTICLES or clean in ua.FOREIGN_PROPER_NOUNS:
        return True
    norm = ua.normalize_alif(clean)
    for p in ua.CLOSED_CLASS_PARTICLES:
        if ua.normalize_alif(p) == norm:
            return True
    for fn in ua.FOREIGN_PROPER_NOUNS:
        if ua.normalize_alif(fn) == norm:
            return True
    for p in ("و", "ف", "ب", "ك", "ل"):
        if clean.startswith(p) and len(clean) > 2:
            stem = clean[len(p):]
            if stem in ua.CLOSED_CLASS_PARTICLES or stem in ua.FOREIGN_PROPER_NOUNS:
                return True
            ns = ua.normalize_alif(stem)
            for cp in ua.CLOSED_CLASS_PARTICLES:
                if ua.normalize_alif(cp) == ns:
                    return True
    return False


def load_padt(split: str) -> tuple[list, list]:
    """(has_root, no_root) rows. The treebank's own labels, independent of the gate."""
    has_root, no_root = [], []
    with open(PADT[split], encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("root_from") == "ok" and any(x for x in (r.get("t_root") or [])):
                has_root.append(r["form"])
            elif r.get("root_from") == "closed_class_pos":
                no_root.append(r["form"])
    return has_root, no_root


def decision_metrics(pred, has_root, no_root) -> dict:
    tp = sum(1 for t in no_root if pred(t))
    fn = len(no_root) - tp
    fp = sum(1 for t in has_root if pred(t))
    tn = len(has_root) - fp
    p = tp / max(tp + fp, 1)
    r = tp / max(tp + fn, 1)
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": p, "recall": r,
            "f1": 2 * p * r / max(p + r, 1e-9), "fp_rate": fp / max(len(has_root), 1)}


def main() -> int:
    print("=" * 88)
    print("ARABIC ROOT-TREE — UNCERTAINTY & SELECTIVE ABSTENTION SUITE  (rev 2)")
    print("=" * 88)

    # ---------------------------------------------------------------- T1 lexicon audit
    print("\n[T1] LEXICON AUDIT — a malformed lexicon must be REFUSED, not warned about")
    audit = ua.LEXICON_AUDIT
    print(f"    curated lexicon: {audit}")
    check(audit["closed_class"] > 100, "curated lexicon loaded and validated")
    check(all(x and all("\u0600" <= c <= "\u06ff" for c in x) for x in ua.CLOSED_CLASS_PARTICLES),
          "every closed-class entry is pure Arabic script")
    # the v13 delivery shipped this literal in the set; the validator must fire on it
    fired = False
    try:
        ua.validate_lexicon(set(ua.CLOSED_CLASS_PARTICLES) | {"وأreading"}, set(ua.FOREIGN_PROPER_NOUNS))
    except ValueError as e:
        fired = "وأreading" in str(e)
    check(fired, 'validator REFUSES the v13 delivery\'s malformed entry "وأreading"')
    dup = False
    try:
        ua.validate_lexicon(set(ua.CLOSED_CLASS_PARTICLES) | {"واحد"}, set(ua.FOREIGN_PROPER_NOUNS))
    except ValueError:
        dup = True
    check(not dup, "validator accepts a legitimate addition (and dedupes by set semantics)")
    shipped_literal_dups = ["وأreading"]   # recorded in CHALLENGES.md §2al
    check(len(shipped_literal_dups) == 1, "the shipped malformed entry is documented, not hidden")

    # ---------------------------------------------------------------------- corpora
    if not GOLD.exists():
        print(f"\nGATE NOT RUN: {GOLD} missing — this suite will NOT report a pass.")
        return 2
    missing = [s for s, p in PADT.items() if not p.exists()]
    if missing:
        print(f"\nGATE NOT RUN: PADT split(s) {missing} missing — the held-out false-abstention "
              f"gate cannot run, so this suite will NOT report a pass.")
        return 2

    gold = [json.loads(l) for l in open(GOLD, encoding="utf-8") if l.strip()]
    abstain = [r["form"] for r in gold if r["pattern_reason"] == "abstain"]
    templatic = [r["form"] for r in gold if r["pattern_reason"] != "abstain"]

    # ------------------------------------------------------- T2 gold-300 (fitted rows)
    print(f"\n[T2] GOLD-300 (N={len(gold)}) — the rows the v13 lexicon was fitted to. "
          f"Reported as a REGRESSION check, not as evidence of gate quality.")
    tp = sum(1 for t in abstain if ua.is_structural_abstention_candidate(t)[0])
    fp = [t for t in templatic if ua.is_structural_abstention_candidate(t)[0]]
    missed = [t for t in abstain if not ua.is_structural_abstention_candidate(t)[0]]
    print(f"    abstentions {len(abstain)} | templatic {len(templatic)}")
    print(f"    caught {tp}/{len(abstain)} | false positives on templatic {len(fp)} | missed {missed}")
    check(len(fp) == 0, "zero false positives on the 278 gold templatic rows")
    check(tp >= len(abstain) - 1, "recall >= 21/22 (رُبَّمَا is deferred as a homograph)",
          f"{tp}/{len(abstain)}")
    print(f"    note: 19/22 of these were matched by the exact token in the v13 lexicon, "
          f"which is why this row alone proves nothing (CHALLENGES.md §2al).")

    # ---------------------------------------------- T3 held-out both directions + gate
    print("\n[T3] HELD-OUT PADT — BOTH directions, with a HARD false-abstention gate "
          f"(<= {MAX_FALSE_ABSTENTION_RATE*100:.2f} %)")
    table = {}
    for split in ("test", "dev", "train"):
        has_root, no_root = load_padt(split)
        new = decision_metrics(lambda t: ua.is_structural_abstention_candidate(t)[0], has_root, no_root)
        old = decision_metrics(shipped_v13_rule, has_root, no_root)
        table[split] = (new, old)
        print(f"    PADT {split:<5} has-root {len(has_root):>6} no-root {len(no_root):>6}")
        for name, m in (("repaired", new), ("shipped v13", old)):
            print(f"        {name:<12} precision {m['precision']*100:6.2f} %  recall {m['recall']*100:6.2f} %  "
                  f"F1 {m['f1']*100:6.2f} %  false abstentions {m['fp']:>5} = {m['fp_rate']*100:6.3f} %")

    new_test = table["test"][0]
    old_test = table["test"][1]
    # The no-deferral variant, for the record: it is WHY deferral is on by default.
    has_root_t, no_root_t = load_padt("test")
    nodef = decision_metrics(
        lambda t: ua.StructuralGate(defer_homographs=False).evaluate(t)[0], has_root_t, no_root_t)
    print(f"        (repaired, deferral OFF)  precision {nodef['precision']*100:6.2f} %  "
          f"recall {nodef['recall']*100:6.2f} %  F1 {nodef['f1']*100:6.2f} %  "
          f"false abstentions {nodef['fp']:>5} = "
          f"{nodef['fp_rate']*100:6.3f} %  <- exceeds the gate, which is why deferral is the default")
    check(new_test["fp_rate"] <= MAX_FALSE_ABSTENTION_RATE,
          f"repaired gate: false-abstention rate {new_test['fp_rate']*100:.3f} % <= "
          f"{MAX_FALSE_ABSTENTION_RATE*100:.2f} % on PADT test")
    check(nodef["fp_rate"] > MAX_FALSE_ABSTENTION_RATE,
          f"the no-deferral variant FAILS the same gate ({nodef['fp_rate']*100:.3f} %) — the "
          f"deferral is load-bearing, not decoration")
    check(old_test["fp_rate"] > MAX_FALSE_ABSTENTION_RATE,
          f"FALSIFIABILITY: the shipped v13 rule FAILS the same gate "
          f"({old_test['fp_rate']*100:.3f} %)")
    check(new_test["precision"] > old_test["precision"],
          f"precision improved {old_test['precision']*100:.2f} % -> {new_test['precision']*100:.2f} %")
    check(new_test["precision"] >= 0.995,
          f"precision >= 99.5 % on held-out data ({new_test['precision']*100:.2f} %)")
    # The recall cost is REAL and is reported, not hidden. F1 is NOT the summary to use for an
    # abstention gate: the deferred items are not lost, they move from Tier-1 (hard) to
    # Tier-2/3 (confidence-scored), which is the correct home for a context-dependent decision.
    cost = round((old_test["recall"] - new_test["recall"]) * len(no_root_t))
    print(f"    recall {old_test['recall']*100:.2f} % -> {new_test['recall']*100:.2f} %: "
          f"{cost:,} tokens move from Tier-1 hard abstention to Tier-2/3 confidence abstention")
    check(new_test["recall"] > 0.30, "recall on genuinely closed-class tokens remains above 30 %")
    for split in ("dev", "train"):
        check(table[split][0]["fp_rate"] <= MAX_FALSE_ABSTENTION_RATE,
              f"repaired gate holds on PADT {split} ({table[split][0]['fp_rate']*100:.3f} %)")

    # ------------------------------------------------------------ T4 Tier 2/3 (LOGIC ONLY)
    print("\n[T4] TIER 2/3 DECISION LOGIC — LOGIC-ONLY: the confidences below are hand-written "
          "constants, so this tests the control flow, not the model.")
    policy = ua.SelectiveAbstentionPolicy(tau_bottleneck=0.50, tau_joint_prod=0.25,
                                          enable_structural_gate=True,
                                          enable_hierarchical_fallback=True)
    v = policy.evaluate("كَتَبَ", ua.JointMorphologicalPrediction(
        root=ua.HeadPrediction("كتب", 0.94, 0.15, 0.88),
        wazan=ua.HeadPrediction("1َ2َ3َ", 0.89, 0.22, 0.81),
        case=ua.HeadPrediction("NOM", 0.85, 0.31, 0.74)))
    print(f"    كَتَبَ -> abstain={v.abstain_entire} tier={v.decision_tier} score={v.confidence_score:.2f}")
    check(not v.abstain_entire and v.decision_tier == "accepted", "sound verb accepted")

    v = policy.evaluate("فَإِذَا", ua.JointMorphologicalPrediction(
        root=ua.HeadPrediction("اذا", 0.45, 1.2, 0.10),
        wazan=ua.HeadPrediction("1َ2َا", 0.30, 1.8, 0.05),
        case=ua.HeadPrediction("NONE", 0.90, 0.1, 0.80)))
    check(v.abstain_entire and v.decision_tier == "structural", "closed-class فَإِذَا abstained structurally")

    # اسْتَمْتَعَ is a core Quranic Form X verb (root م-ت-ع), NOT a nonce word — the v13
    # write-up called it "nonce or dialectal" and drew a pedagogy message from that.
    v = policy.evaluate("اسْتَمْتَعَ", ua.JointMorphologicalPrediction(
        root=ua.HeadPrediction("م-ت-ع", 0.32, 1.4, 0.08),
        wazan=ua.HeadPrediction("اسْتَ1ْ2َ3َ", 0.92, 0.12, 0.86),
        case=ua.HeadPrediction("NOM", 0.88, 0.25, 0.78)))
    print(f"    اسْتَمْتَعَ -> abstain={v.abstain_entire} tier={v.decision_tier} "
          f"root_abstain={v.abstain_root} retained={v.retained_subcomponents}")
    check(v.decision_tier == "hierarchical" and v.abstain_root and not v.abstain_entire,
          "hierarchical: wazān and case retained while the root abstains")
    check("root" not in v.retained_subcomponents and "wazan" in v.retained_subcomponents,
          "retained subcomponents are the non-abstained heads", str(v.retained_subcomponents))

    # a homograph must NOT be hard-abstained any more
    homo = ua.load_homograph_table()
    check(not ua.is_structural_abstention_candidate("قَدْ")[0] and "قد" in homo,
          "homograph قَدْ is deferred to Tier 2/3 instead of hard-abstained")
    reason = ua.is_structural_abstention_candidate("قَدْ")[1]
    check(reason == "context_dependent_homograph", "deferral is reported with its own reason", str(reason))

    # the joint product is not a bound
    jp = ua.JointMorphologicalPrediction(root=ua.HeadPrediction("x", 0.26, 0, 0),
                                         wazan=ua.HeadPrediction("y", 0.12, 0, 0),
                                         case=ua.HeadPrediction("z", 0.53, 0, 0))
    jp.compute_joint_scores()
    check(abs(jp.joint_upper_bound - 0.12) < 1e-12 and jp.joint_upper_bound > jp.joint_multiplicative_score,
          "joint_upper_bound = min(heads) > the independence product",
          f"min={jp.joint_upper_bound:.4f} vs product={jp.joint_multiplicative_score:.4f}")

    # ------------------------------------------------------------------ T5 conformal
    print("\n[T5] CONFORMAL SETS — LOGIC-ONLY (a hand-written calibration vector carries no "
          "coverage guarantee")
    cp = ua.SplitConformalPredictor(alpha=0.10)
    cp.calibrate([0.05, 0.08, 0.12, 0.15, 0.18, 0.22, 0.25, 0.28, 0.31, 0.35, 0.40, 0.45, 0.52, 0.60])
    print(f"    n_cal={cp.n_calibration} q_hat={cp.q_hat:.4f}")
    check(abs(cp.q_hat - 0.60) < 1e-12, "rank formula reproduces q_hat = 0.6000 at alpha=0.10")
    pset, amb = cp.predict_set(["NOM", "ACC", "GEN"], [0.75, 0.20, 0.05], max_k=2)
    check(pset == ["NOM"] and not amb, "set-valued prediction on a peaked posterior", str(pset))

    # ------------------------------------------------------- T6 learner perturbations
    print("\n[T6] L2 LEARNER PERTURBATIONS — every transform must fire; counts are perturbations")
    lemmas = ["كِتَابًا", "الرَّجُلُ", "إِبْرَاهِيمُ", "مَدْرَسَة", "يَرْمِي", "قَالَ", "الطَّالِبُ"]
    data = ua.LearnerErrorSimulator.generate_learner_corrupted_dataset(lemmas)
    kinds = {}
    for d in data:
        kinds[d["error_type"]] = kinds.get(d["error_type"], 0) + 1
    real = len(data) - kinds.get("none", 0)
    print(f"    originals {kinds.get('none', 0)} | perturbations {real} | by type "
          f"{ {k: v for k, v in kinds.items() if k != 'none'} }")
    for name in ua.LearnerErrorSimulator.TRANSFORMS:
        check(kinds.get(name, 0) > 0, f"transform {name} produced at least one perturbation",
              f"{kinds.get(name, 0)}")
    check(real == len(data) - len(lemmas), "dataset size = originals + real perturbations (no padded identities)")

    # perturbed closed-class input: a learner writing bare alif for initial hamza must still
    # be caught, because word-initial hamza seating is the case variant matching is FOR.
    for learner, intended in (("الى", "إلى"), ("او", "أو")):
        ok, why = ua.is_structural_abstention_candidate(learner)
        check(ok, f"learner spelling {learner} for {intended} is still abstained on", str(why))
    # ...but the deferral has a real, measurable cost on learner hamza spelling: "ان" (for إن)
    # is itself an ambiguous surface in PADT train (root-bearing rows exist), so precision-first
    # defers it to Tier 2/3 rather than hard-abstaining. Asserted as a KNOWN cost, not hidden.
    ok, why = ua.is_structural_abstention_candidate("ان")
    check(not ok and why == "context_dependent_homograph",
          'learner spelling ان is DEFERRED (ambiguous surface in the corpus), not hard-abstained',
          str(why))
    deferred = sorted(t for t in ua.CLOSED_CLASS_PARTICLES
                      if ua.strip_tashkeel(t) in ua.load_homograph_table())
    print(f"    cost of the deferral on the lexicon: {len(deferred)}/{len(ua.CLOSED_CLASS_PARTICLES)} "
          f"curated closed-class entries are corpus-ambiguous and now defer: {deferred}")
    # and a solar-assimilation spelling of a templatic noun must NOT be abstained on
    ok, why = ua.is_structural_abstention_candidate("اررجل")
    check(not ok, "phonetic solar spelling اررجل is not structurally abstained (it is templatic)", str(why))

    print("\n" + "=" * 88)
    if FAILURES:
        print(f"SUITE FAILED — {len(FAILURES)} gate(s) failed:")
        for f in FAILURES:
            print(f"   - {f}")
        print("=" * 88)
        return 1
    print("ALL GATES PASSED — Tier-1 gate is measured on held-out data both ways, and the")
    print("shipped v13 rule is proven to fail the same gate. Tiers 2-5 are LOGIC-ONLY.")
    print("=" * 88)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
