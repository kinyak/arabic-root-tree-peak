"""uncertainty_abstention.py — Selective classification, uncertainty quantification, and
multi-tier abstention for the Native Arabic Root-Tree Model.

    REV 2 — 2026-10-11 — audit repairs. See CHALLENGES.md §2al for the full record.

THEORETICAL FOUNDATION (unchanged from the v13 delivery)
  1. Chow's Rule (Chow 1957, 1970) & Selective Classification (Geifman & El-Yaniv 2017, 2019).
  2. Multi-tier semantic abstention: TIER 1 structural, TIER 2 confidence, TIER 3 hierarchical.
  3. Inductive Conformal Prediction (Vovk et al. 2005, Angelopoulos & Bates 2021).

WHAT WAS WRONG IN THE v13 DELIVERY, AND WHAT REPLACED IT
--------------------------------------------------------------------------------------------
1. **The Tier-1 gate was scored on the rows it was fitted to.** The delivery reported
   "0/278 (0.00%) false positives on valid templatic words". 278 rows is the templatic half
   of gold-300, and 19 of the 22 abstention rows the gate is scored against match the exact
   token IN the shipped lexicon (17 of them verbatim). Re-measured on held-out, root-bearing
   PADT tokens (the gate was never run on them), the shipped rule produced:

       PADT test  165 / 12,837 = 1.285 %   ·  dev 224 / 12,930 = 1.732 %
       PADT train 1,289 / 99,869 = 1.291 %

   Two rule defects caused it, and both are repaired here:

   (a) the proclitic branch accepted an ALIF-NORMALISED variant of the stripped stem, so
       كَانَ → strip ك → "ان" → normalised match against أَن. Every surface starting with
       و/ف/ب/ك/ل whose remainder collapses onto a hamzated particle was abstained on.
       Now the branch requires EXACT stem membership.

   (b) whole-token alif-insensitive matching ran over the entire lexicon, which conflated
       كَأَنَّ with كَانَ (ك-و-ن) — the single largest false-positive class. Word-initial
       hamza seating is the genuinely learner-ambiguous case (إن/ان، إلى/الى، أو/او), so
       variant matching is now restricted to entries whose hamza is WORD-INITIAL.

2. **Homographs now defer instead of hard-abstaining.** A surface attested BOTH root-bearing
   and closed-class in PADT TRAIN (قَدْ particle vs قَدَّ verb; أَي which vs أي) has no
   context-free word class. Hard abstaining on it is a false abstention by construction, so
   such surfaces return False with reason "context_dependent_homograph" and fall through to
   the Tier-2/3 confidence policy. The table is built from the TRAIN split only
   (tools/build_abstention_homographs.py); the test split is never read.

3. **The lexicon contained a malformed entry** — the literal "وأreading" (mixed script), plus
   three duplicated strings. validate_lexicon() now refuses at import, so an unvalidated
   lexicon cannot ship again.

4. **The multiplicative joint score is not a bound.** P(root)·P(wazān)·P(case) equals the
   joint only under independence; it is neither an upper nor a lower bound of it (the valid
   bound is min over the heads). compute_joint_scores() now also exposes joint_upper_bound
   and documents the difference.

MEASURED TRADE OF THE REPAIRED TIER-1 GATE (both directions, held-out PADT test)
--------------------------------------------------------------------------------------------
Reference labels are the treebank's own and independent of the gate:
  NO-ROOT  root_from == "closed_class_pos"   (8,212 tokens) — the gate SHOULD abstain
  HAS-ROOT root_from == "ok"                (12,837 tokens) — the gate must NOT abstain

    rule                                 precision   recall     F1     false abstentions
    shipped v13 (alif-variants)            95.98 %  47.92 %  63.92 %   1.285 % (165)
    repaired, deferral OFF                 98.13 %  47.89 %  64.37 %   0.584 % ( 75)
    repaired, deferral ON (this file)      99.64 %  37.09 %  54.06 %   0.086 % ( 11)

Precision is what an abstention gate is FOR: a false abstention blocks a learner on a word
that is perfectly analysable, and on this corpus it was the commonest way the v13 gate was
wrong. Deferral removes 64 of the 75 remaining false abstentions (85 %; 165 -> 11 overall, so
93 % of the v13 gate's false abstentions are gone) and costs recall: 889 PADT-test tokens move
from Tier 1 (hard abstention) to Tier 2/3 (confidence-scored), which is the correct home for a
context-dependent decision. F1 is NOT the right summary here — it scores a deferral as a miss,
and a deferral is not a miss.
StructuralGate(defer_homographs=False) gives the coverage-first posture: 0.584 % false
abstentions, i.e. it fails this module's own gate, which is why deferral is the default.

   Lexicons are NOT interchangeable with the PADT closed-class inventory: building the set
   from data/closed_class_inventory.json (TRAIN-derived lemmas, train_freq >= 5) gives 637
   entries and 3.513 % false abstentions on test — a COVERAGE instrument, not a precision
   instrument. inventory_lexicon() is exposed for coverage work and is off by default. The
   inventory is used here as the held-out EVALUATION reference it was built to be, not as
   the lexicon.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
HOMOGRAPH_TABLE = _REPO_ROOT / "data" / "abstention_homographs.json"

# -----------------------------------------------------------------------------
# Tier 1: Structural abstention gate (closed class & non-templatic words)
# -----------------------------------------------------------------------------
# Curated function words. THIS IS A PRECISION INSTRUMENT: recall against a corpus is
# deliberately traded away (see module docstring), so do not grow it by pasting in rows
# from an evaluation set — that is precisely how the v13 delivery produced a 100 % recall
# that meant nothing.
CLOSED_CLASS_PARTICLES: Set[str] = {
    # Harf Jarr, 'Atf, Istifham, Nida, Nafy, Shart
    "من", "إلى", "عن", "على", "في", "رب", "حتى", "كأن", "لعل", "ليت", "لكن", "إن", "أن",
    "لا", "ما", "لم", "لن", "لو", "كي", "إذ", "إذا", "ثم", "أو", "أم", "بل", "قد", "سوف",
    "هل", "يا", "أيا", "هيا", "أي", "إذن", "غير", "سوى", "خلا", "عدا", "حاشا", "مذ", "منذ",
    # Compound / Kaf & Makfuf (كافة ومكفوفة)
    "إنما", "أنما", "كأنما", "لكنما", "ربما", "طالما", "قلما", "حيثما", "إذما", "كلما",
    # Pronouns (Dama'ir Munfasilah)
    "هو", "هي", "هما", "هم", "هن", "أنت", "أنتما", "أنتم", "أنتن", "أنا", "نحن",
    "إياه", "إياها", "إياهما", "إياهم", "إياهن", "إياك", "إياكما", "إياكم", "إياكن", "إياي", "إيانا",
    "كلا", "كلتا", "كلاهما", "كلتاهما",
    # Demonstratives (Asma' Isharah)
    "هذا", "هذه", "هذان", "هاتان", "هؤلاء", "ذلك", "تلك", "ذانك", "تانك", "أولئك", "هنا", "هناك", "هنالك",
    # Relatives (Asma' Mawsulah)
    "الذي", "التي", "اللذان", "اللتان", "الذين", "اللاتي", "اللواتي", "اللائي",
    # Fused particle+pronoun clusters seen in running text
    "وإذا", "فإذا", "والذي", "فالذي", "بذلك", "لذلك", "كذلك", "فعلى", "وعلى", "وفي", "ففي",
    "ومنه", "فمنه", "وعنه", "فعنه", "وإليه", "فإليه", "وعليه", "فعليه", "وبما", "فبما",
    "وإن", "فإن", "وأن", "فأن", "ولكن", "فلكن", "ولم", "فلم", "ولن", "فلن", "وقد", "فقد",
    "عنه", "عنها", "عنهم", "عنهن", "منه", "منها", "منهم", "منهن", "إليه", "إليها", "إليهم", "إليهن",
    "عليه", "عليها", "عليهم", "عليهن", "فيه", "فيها", "فيهم", "فيهن", "به", "بها", "بهم", "بهن",
    "له", "لها", "لهم", "لهن", "معه", "معها", "معهم", "معهن", "وأنه", "فأنه", "وأنها", "فأنها",
    "وأنهما", "وأنهن", "وأنهم", "فأنهم",
}

# Non-Arabic Semitic / Biblical / foreign proper nouns (a'lam a'jamiyyah — non-templatic).
FOREIGN_PROPER_NOUNS: Set[str] = {
    "إبراهيم", "إسماعيل", "إسحاق", "يعقوب", "يوسف", "عيسى", "موسى", "هارون", "داود",
    "سليمان", "أيوب", "يونس", "زكريا", "يحيى", "إلياس", "اليسع", "لوط", "آدم", "نوح",
    "إدريس", "طالوت", "جالوت", "فرعون", "قارون", "هامان", "آزر",
}

_ARABIC_RANGE = ("\u0600", "\u06ff")
_DIACRITICS_RE = re.compile(r"[\u064b-\u0652\u0670\u0651]")
# Word-initial hamza seats. Only these are treated as orthographic VARIANT material: the
# learner-error case is a bare alif written where a hamza belongs at the START of a word
# (ان for إن). Medial hamza seating is not a variant — conflating it is what made the v13
# gate abstain on كَانَ by normalising it onto كَأَنَّ.
_HAMZA_SEATS = ("أ", "إ", "آ")
_PROCLITICS = ("و", "ف", "ب", "ك", "ل")


def strip_tashkeel(text: str) -> str:
    """Removes Arabic short vowels, tanwin, sukun and shadda."""
    return _DIACRITICS_RE.sub("", text)


def normalize_alif(text: str) -> str:
    """Normalises hamzated alif seats for lookup (أ/إ/آ -> ا)."""
    return text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")


def validate_lexicon(closed: Set[str], foreign: Set[str]) -> Dict[str, int]:
    """Refuses a malformed lexicon. Raises ValueError rather than warning.

    The v13 delivery shipped the literal "وأreading" (mixed script) inside the closed-class
    set; it could never match a real token, so nothing failed and nothing was noticed.
    """
    bad = sorted(x for x in list(closed) + list(foreign)
                 if not x or not all(_ARABIC_RANGE[0] <= c <= _ARABIC_RANGE[1] for c in x))
    if bad:
        raise ValueError(f"lexicon contains non-Arabic / malformed entries: {bad}")
    if not closed or not foreign:
        raise ValueError("lexicon halves must both be non-empty")
    return {"closed_class": len(closed), "foreign_proper_nouns": len(foreign)}


LEXICON_AUDIT = validate_lexicon(CLOSED_CLASS_PARTICLES, FOREIGN_PROPER_NOUNS)

_INITIAL_HAMZA_ENTRIES = {p for p in CLOSED_CLASS_PARTICLES if p[:1] in _HAMZA_SEATS}


def load_homograph_table(path: Optional[Path] = None) -> Set[str]:
    """Surfaces attested BOTH root-bearing and closed-class, built from PADT TRAIN only.

    Absent table -> empty set -> the gate behaves exactly as without the deferral. The table
    is a data artifact; regenerate with tools/build_abstention_homographs.py.
    """
    p = Path(path) if path else HOMOGRAPH_TABLE
    if not p.exists():
        return set()
    d = json.loads(p.read_text(encoding="utf-8"))
    splits = d.get("splits_read")
    if splits is None:
        raise ValueError(f"refusing a homograph table with no recorded provenance: {p}")
    if list(splits) != ["train"]:
        raise ValueError(f"refusing a homograph table derived from an evaluation split: {splits}")
    return {strip_tashkeel(x) for x in d.get("surfaces", [])}


def inventory_lexicon(path: Optional[Path] = None, min_train_freq: int = 5) -> Set[str]:
    """Closed-class lemma set from data/closed_class_inventory.json (PADT TRAIN-derived).

    A COVERAGE instrument, not a precision one: at min_train_freq=5 it yields 637 entries and
    a 3.513 % false-abstention rate on PADT test, versus 0.086 % for the curated gate here.
    Off by default for that reason.
    """
    p = Path(path) if path else (_REPO_ROOT / "data" / "closed_class_inventory.json")
    if not p.exists():
        return set()
    d = json.loads(p.read_text(encoding="utf-8"))
    return {strip_tashkeel(e["lemma"]) for e in d.get("lemmas", [])
            if e.get("train_freq", 0) >= min_train_freq and strip_tashkeel(e["lemma"])}


class StructuralGate:
    """Tier-1 structural abstention, with the repaired rule ordering."""

    def __init__(self, closed: Optional[Set[str]] = None,
                 foreign: Optional[Set[str]] = None,
                 homographs: Optional[Set[str]] = None,
                 defer_homographs: bool = True):
        self.closed = set(CLOSED_CLASS_PARTICLES if closed is None else closed)
        self.foreign = set(FOREIGN_PROPER_NOUNS if foreign is None else foreign)
        self.homographs = load_homograph_table() if homographs is None else set(homographs)
        self.defer_homographs = defer_homographs

    def evaluate(self, token: str) -> Tuple[bool, Optional[str]]:
        clean = strip_tashkeel(token).strip()
        if not clean:
            return True, "empty_token"
        if not any(_ARABIC_RANGE[0] <= c <= _ARABIC_RANGE[1] for c in clean):
            return True, "non_arabic_or_punctuation"

        # Context-free word class is not available for a homograph: hand it to Tier 2/3.
        if self.defer_homographs and clean in self.homographs:
            return False, "context_dependent_homograph"

        if clean in self.closed:
            return True, f"closed_class_particle:{clean}"
        if clean in self.foreign:
            return True, f"foreign_proper_noun:{clean}"

        # Alif-insensitive matching, word-INITIAL hamza only (see module docstring, 1b).
        norm = normalize_alif(clean)
        for p in _INITIAL_HAMZA_ENTRIES & self.closed:
            if normalize_alif(p) == norm:
                return True, f"closed_class_particle_variant:{clean}"
        for fn in self.foreign:
            if normalize_alif(fn) == norm:
                return True, f"foreign_proper_noun_variant:{clean}"

        # Proclitic stripping. EXACT membership only: an alif-normalised variant of the
        # remainder is what abstained on كَانَ (v13 defect 1a). Minimum stem length 2 —
        # a one-letter remainder is a radical, not a stripped particle.
        for p in _PROCLITICS:
            if clean.startswith(p) and len(clean) > 2:
                stem = clean[len(p):]
                if len(stem) < 2:
                    continue
                if stem in self.closed:
                    return True, f"closed_class_with_proclitic:{clean}"
                if stem in self.foreign:
                    return True, f"foreign_proper_noun_with_proclitic:{clean}"
        return False, None


_DEFAULT_GATE = StructuralGate()


def is_structural_abstention_candidate(token: str) -> Tuple[bool, Optional[str]]:
    """Public entry point (API unchanged; semantics repaired). See StructuralGate.evaluate."""
    return _DEFAULT_GATE.evaluate(token)


# -----------------------------------------------------------------------------
# Tier 2: uncertainty quantifiers
# -----------------------------------------------------------------------------
def softmax(logits: List[float], temperature: float = 1.0) -> List[float]:
    """Numerically stable softmax with temperature scaling."""
    if not logits:
        return []
    t = max(temperature, 1e-4)
    m = max(logits)
    exp_vals = [math.exp((x - m) / t) for x in logits]
    total = sum(exp_vals)
    return [e / total for e in exp_vals]


def predictive_entropy(probs: List[float]) -> float:
    """Shannon entropy H(P) = -sum p log p, in nats."""
    return -sum(p * math.log(p) for p in probs if p > 1e-12)


def normalized_entropy(probs: List[float]) -> float:
    """Entropy in [0, 1]."""
    k = len(probs)
    return 0.0 if k <= 1 else predictive_entropy(probs) / math.log(k)


def margin_confidence(probs: List[float]) -> float:
    """Top-1 minus top-2 probability."""
    if len(probs) < 2:
        return 1.0 if probs else 0.0
    s = sorted(probs, reverse=True)
    return s[0] - s[1]


@dataclass
class HeadPrediction:
    label: Any
    confidence: float
    entropy: float
    margin: float
    probs: List[float] = field(default_factory=list)


@dataclass
class JointMorphologicalPrediction:
    root: Optional[HeadPrediction] = None
    wazan: Optional[HeadPrediction] = None
    case: Optional[HeadPrediction] = None
    clitics: Optional[HeadPrediction] = None

    joint_multiplicative_score: float = 0.0
    joint_upper_bound: float = 0.0
    bottleneck_score: float = 0.0
    harmonic_mean_score: float = 0.0

    def compute_joint_scores(self) -> None:
        """Per-head aggregates.

        NOTE ON joint_multiplicative_score: it is P(root)·P(wazān)·P(case) under an
        INDEPENDENCE assumption over three heads the architecture predicts without mutual
        conditioning. It is NOT an upper bound of the joint: P(A∩B∩C) <= min(P(A),P(B),P(C)),
        which is joint_upper_bound. The v13 write-up used the product as a "ceiling" on
        exact-surface yield and mixed aggregation levels besides (two single-seed accuracies
        and one 3-seed macro-F1), so the "1.6 % ceiling" does not follow.
        """
        confs = [h.confidence for h in (self.root, self.wazan, self.case) if h is not None]
        if not confs:
            self.joint_multiplicative_score = 0.0
            self.joint_upper_bound = 0.0
            self.bottleneck_score = 0.0
            self.harmonic_mean_score = 0.0
            return
        prod = 1.0
        for c in confs:
            prod *= max(c, 1e-8)
        self.joint_multiplicative_score = prod
        self.joint_upper_bound = min(confs)
        self.bottleneck_score = min(confs)
        self.harmonic_mean_score = len(confs) / sum(1.0 / max(c, 1e-8) for c in confs)


# -----------------------------------------------------------------------------
# Tier 3: selective classification decision & hierarchical abstention
# -----------------------------------------------------------------------------
@dataclass
class AbstentionVerdict:
    abstain_entire: bool = False
    abstain_root: bool = False
    abstain_wazan: bool = False
    abstain_case: bool = False
    decision_tier: str = "accepted"  # structural | confidence | hierarchical | accepted
    primary_reason: str = "ok"
    confidence_score: float = 1.0
    retained_subcomponents: Dict[str, Any] = field(default_factory=dict)


class SelectiveAbstentionPolicy:
    """Chow's optimal rule (tau* = lambda/(1+lambda)) plus component-wise abstention."""

    def __init__(self, tau_bottleneck: float = 0.45, tau_joint_prod: float = 0.20,
                 tau_root: float = 0.50, tau_wazan: float = 0.35, tau_case: float = 0.40,
                 enable_structural_gate: bool = True,
                 enable_hierarchical_fallback: bool = True,
                 structural_gate: Optional[StructuralGate] = None):
        self.tau_bottleneck = tau_bottleneck
        self.tau_joint_prod = tau_joint_prod
        self.tau_root = tau_root
        self.tau_wazan = tau_wazan
        self.tau_case = tau_case
        self.enable_structural_gate = enable_structural_gate
        self.enable_hierarchical_fallback = enable_hierarchical_fallback
        self.structural_gate = structural_gate or _DEFAULT_GATE

    def evaluate(self, surface_token: str, joint_pred: JointMorphologicalPrediction,
                 is_trie_legal: bool = True) -> AbstentionVerdict:
        verdict = AbstentionVerdict()
        joint_pred.compute_joint_scores()

        if self.enable_structural_gate:
            is_struct, reason = self.structural_gate.evaluate(surface_token)
            if is_struct:
                verdict.abstain_entire = verdict.abstain_root = True
                verdict.abstain_wazan = verdict.abstain_case = True
                verdict.decision_tier = "structural"
                verdict.primary_reason = reason or "structural_closed_class"
                verdict.confidence_score = 1.0
                return verdict

        if not is_trie_legal:
            verdict.abstain_root = True
            if not self.enable_hierarchical_fallback:
                verdict.abstain_entire = True
                verdict.decision_tier = "confidence"
                verdict.primary_reason = "illegal_root_combination"
                verdict.confidence_score = joint_pred.root.confidence if joint_pred.root else 0.0
                return verdict

        if joint_pred.root and joint_pred.root.confidence < self.tau_root:
            verdict.abstain_root = True
        if joint_pred.wazan and joint_pred.wazan.confidence < self.tau_wazan:
            verdict.abstain_wazan = True
        if joint_pred.case and joint_pred.case.confidence < self.tau_case:
            verdict.abstain_case = True

        score = joint_pred.bottleneck_score
        verdict.confidence_score = score

        if score < self.tau_bottleneck or joint_pred.joint_multiplicative_score < self.tau_joint_prod:
            if not self.enable_hierarchical_fallback:
                verdict.abstain_entire = True
                verdict.decision_tier = "confidence"
                verdict.primary_reason = f"low_joint_confidence:{score:.3f}"
                return verdict
            verdict.decision_tier = "hierarchical"
            reasons = []
            for name, head, flag in (("root", joint_pred.root, verdict.abstain_root),
                                     ("wazan", joint_pred.wazan, verdict.abstain_wazan),
                                     ("case", joint_pred.case, verdict.abstain_case)):
                if flag:
                    reasons.append(f"uncertain_{name}")
                elif head is not None:
                    verdict.retained_subcomponents[name] = head.label
            if verdict.abstain_root and verdict.abstain_wazan:
                verdict.abstain_entire = True
                verdict.primary_reason = "uncertain_root_and_wazan"
            else:
                verdict.abstain_entire = False
                verdict.primary_reason = "+".join(reasons) if reasons else "partial_retention"
            return verdict

        verdict.abstain_entire = False
        verdict.decision_tier = "accepted"
        verdict.primary_reason = "ok"
        for name, head in (("root", joint_pred.root), ("wazan", joint_pred.wazan),
                           ("case", joint_pred.case)):
            if head is not None:
                verdict.retained_subcomponents[name] = head.label
        return verdict


# -----------------------------------------------------------------------------
# Tier 4: split conformal prediction
# -----------------------------------------------------------------------------
class SplitConformalPredictor:
    """Split conformal prediction for set-valued predictions.

    The 1-alpha guarantee is conditional on exchangeability between the calibration and test
    distributions. Calibrating on a hand-written vector does not carry that guarantee, so any
    number produced that way is a smoke test of the arithmetic, not a coverage result.
    """

    def __init__(self, alpha: float = 0.10):
        self.alpha = alpha
        self.q_hat: float = 1.0
        self.calibrated: bool = False
        self.n_calibration: int = 0

    def calibrate(self, nonconformity_scores: List[float]) -> None:
        if not nonconformity_scores:
            self.q_hat, self.calibrated, self.n_calibration = 1.0, True, 0
            return
        n = len(nonconformity_scores)
        self.n_calibration = n
        rank = math.ceil((n + 1) * (1 - self.alpha))     # Angelopoulos & Bates Alg. 1
        idx = min(max(rank, 1) - 1, n - 1)
        self.q_hat = sorted(nonconformity_scores)[idx]
        self.calibrated = True

    def predict_set(self, labels: List[Any], probs: List[float],
                    max_k: int = 5) -> Tuple[List[Any], bool]:
        if not self.calibrated:
            top = max(range(len(probs)), key=lambda i: probs[i])
            return [labels[top]], False
        pset = [lbl for lbl, pr in zip(labels, probs) if (1.0 - pr) <= self.q_hat]
        if not pset:
            top = max(range(len(probs)), key=lambda i: probs[i])
            pset = [labels[top]]
        return pset, len(pset) > max_k


# -----------------------------------------------------------------------------
# L2 learner error simulation
# -----------------------------------------------------------------------------
class LearnerErrorSimulator:
    """Orthographic / phonetic error transforms from the QALB, ALC and ARETA taxonomies.

    transform_errors() applies every transform that CHANGES the token. (The v13 delivery
    defined apply_tanwin_alif_omission and never called it, then reported "9 simulated error
    types" that were 6 unmodified originals plus 3 perturbations.)
    """

    TRANSFORMS = {
        "hamza_confusion": "apply_hamza_confusion",
        "ta_marbuta_confusion": "apply_ta_marbuta_confusion",
        "alif_maqsura_confusion": "apply_alif_maqsura_confusion",
        "solar_assimilation_spelling": "apply_phonetic_solar_spelling",
        "tanwin_alif_omission": "apply_tanwin_alif_omission",
    }

    @staticmethod
    def apply_hamza_confusion(word: str) -> str:
        return word.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")

    @staticmethod
    def apply_ta_marbuta_confusion(word: str) -> str:
        if word.endswith("ة"):
            return word[:-1] + "ه"
        if word.endswith("ه"):
            return word[:-1] + "ة"
        return word

    @staticmethod
    def apply_alif_maqsura_confusion(word: str) -> str:
        if word.endswith("ى"):
            return word[:-1] + "ي"
        if word.endswith("ي"):
            return word[:-1] + "ى"
        return word

    @staticmethod
    def apply_phonetic_solar_spelling(word: str) -> str:
        solar = set("تثدذرزسشصضطظلن")
        if word.startswith("ال") and len(word) > 2 and word[2] in solar:
            return "ا" + word[2] + word[2:]
        return word

    @staticmethod
    def apply_tanwin_alif_omission(word: str) -> str:
        """كِتَابًا -> كِتَابً — a learner drops the alif that follows fathatan.

        Compared by CODE POINT, not by a visual literal: the logical order is fathatan
        (U+064B) then alif (U+0627), which is the opposite of how the pair is usually
        typed, and an order-sensitive literal silently matched nothing (measured: this
        transform produced 0 perturbations before the fix, which is how the v13 delivery
        shipped a transform that never ran at all).
        """
        if len(word) >= 2 and word[-1] == "\u0627" and word[-2] == "\u064b":
            return word[:-1]
        return word

    @classmethod
    def transform_errors(cls, word: str) -> List[Dict[str, str]]:
        out = []
        for name, method in cls.TRANSFORMS.items():
            p = getattr(cls, method)(word)
            if p != word:
                out.append({"error_type": name, "perturbed": p})
        return out

    @classmethod
    def generate_learner_corrupted_dataset(cls, clean_words: List[str]) -> List[Dict[str, Any]]:
        """Original first, then every transform that actually fires. Nothing is padded with
        identity rows: a count of "variants" must be a count of perturbations."""
        dataset = []
        for w in clean_words:
            dataset.append({"original": w, "perturbed": w, "error_type": "none"})
            for err in cls.transform_errors(w):
                dataset.append({"original": w, **err})
        return dataset
