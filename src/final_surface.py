"""final_surface.py — THE shared final-surface metric, defined on the STEM.

WHY THE METRIC HAD TO MOVE OFF THE TOKEN (measured, `CHALLENGES.md` §2s)
    `eval_harness.surface_exact_match` compares raw token strings. Run against the 300
    human gold triples the renderer scores 9.4% — but 29.5% of the mismatch is the
    CLITIC PLANE: the renderer emits a correct STEM ('فَوْقِ') while the gold token
    carries a proclitic ('كَفَوْقِ'). Charging the renderer for affix material it was
    never given is a metric bug that looks exactly like a morphology failure.

    Tested before changing anything (`src/check_nunation_derivability.py`): of the 215
    gold rows with a full (root, wazān, case) triple, 193 triples are distinct and 11
    carry more than one surface — and ZERO of those 11 disagree about nunation. Every
    one disagrees about CLITICS (اللَّهِ|بِاَللَّهِ, الْعَقْلِ|عَقْلِهِ,
    أَعْلَمَ|أَعْلَمَهُمْ, الْقَلْبِ|قَلْبِهِ). So (root, wazān, case) determines the
    STEM, and the token adds a separate plane. That is the whole justification.

THE DEFINITION (symmetric, so it cannot favour either arm)
    A prediction MATCHES iff it equals the gold token after SOME legal affix
    decomposition of that token — where the zero-strip decomposition is always
    available. So:
      · an arm that emits the full token     (clitics included) matches unmodified;
      · an arm that emits the stem           matches once its own clitic plane is set aside;
      · an arm that emits the wrong consonants matches neither.
    Neither arm is penalised for a plane it was not asked to produce, and neither is
    credited for one.

COVERAGE IS NEVER FOLDED IN
    An abstention (the renderer refuses) is a COVERAGE loss, reported separately. A
    renderer that applies to 14% of tokens at 90% and one that applies to 90% at 14%
    are different claims, and SPEC-REV6 §5.1 item 1 requires the pair, never one alone.

THE DECOMPOSITION IS VERIFICATION-DRIVEN, NOT GREEDY
    An earlier run stripped greedily from a list containing ف ب ك ل س — which are ALSO
    root radicals — cutting the ف off فَضْلَ and inventing a failure. Every legal
    decomposition (0-2 proclitics + optional enclitic) is generated instead, and a
    combining mark left dangling at the cut seam is removed (it belonged to the clitic).

LEAKAGE / NO-TRAINING NOTE
    Nothing here is learned and nothing is trained. This module only measures.
"""
from __future__ import annotations

import collections
import math
import os
import re
import sys
import unicodedata as uni

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DIAC = re.compile(r"[\u064b-\u0652\u0670\u0640]")
PRO = ("وال", "فال", "بال", "كال", "ال", "و", "ف", "ب", "ك", "ل", "س")
ENC = ("هما", "كما", "هم", "هن", "كم", "ها", "نا", "ه", "ي")
# LEGAL TWO-PROCLITIC CHAINS (§2cm). `candidates()` strips ANY two PRO prefixes, but the compiler must
# not guess a chain the language does not form: in `فَلْيُدْمِنْ` the `ف` is the conjunction and the `ل`
# is the jussive lām, and splicing `فَلِ` there BROKE a ruler row. Only the measured, unambiguous chains
# are listed; anything else is refused and the token falls back to the bare stem, which the metric
# already credits. Proclitic+article pairs (وال فال بال كال) are single PRO entries above, and the
# article's own لِ + الْ form is the `(ل, ل)` chain below.
PRO2 = (("و", "س"), ("ف", "س"), ("ل", "ل"))

# THE AFFIX PLANE'S VOCALISATION TABLES (`EVIDENCE_LOG` §2cd). A proclitic's vowel is a property of
# the PROCLITIC, not of the token — لِ is always لِ, بِ is always بِ — so it is SUPPLIED BY RULE.
# This is what makes the layer independent of whether the input text carries diacritics: measured
# before this table existed, **94.3% of the raw "copy the affix characters" gain on gold-300
# (86.4% on the ruler) sat on an affix that carries a diacritic**, i.e. a copy-the-affix
# implementation would have been an ORACLE for the affix vowels. The tables remove that: the
# function now reads only the affix LETTERS from the token and never its affix diacritics.
PRO_V = {"وال": "وَالْ", "فال": "فَالْ", "بال": "بِالْ", "كال": "كَالْ", "ال": "الْ",
         "لل": "لِلْ",                    # لِ + الْ: the article's alif elides after لِ (§2cm)
         "و": "وَ", "ف": "فَ", "ب": "بِ", "ك": "كَ", "ل": "لِ", "س": "سَ"}
ENC_V = {"هما": "هُمَا", "كما": "كُمَا", "هم": "هُمْ", "هن": "هُنَّ", "كم": "كُمْ",
         "ها": "هَا", "نا": "نَا", "ه": "هُ", "ي": "ي"}
# ENCLITIC VOWEL HARMONY. A pronoun enclitic's vowel follows the STEM's final vowel — هِ after a
# kasra (كِتَابِهِ), هُ otherwise (كِتَابُهُ) — so the kasra forms are supplied as a rule rather than
# copied. It reads the vowel the RENDERER just produced, so it is not an oracle either. Measured on
# gold-300: the plain damma forms alone left 8.9 points on the table vs copying the gold affix
# vowel; the kasra forms reclaim most of it. Only the h-/k-initial enclitics harmonise.
ENC_V_KASRA = {"هما": "هِمَا", "كما": "كِمَا", "هم": "هِمْ", "كم": "كِمْ", "ه": "هِ"}
TANWIN_ALIF = "\u064b\u0627"                     # ًا — the accusative nunation written as an alif
HAMZA = set("\u0623\u0625\u0622\u0671\u0621\u0626\u0624")   # أ إ آ ٱ ء ئ ؤ
ALIF = {"\u0627"} | HAMZA
# THE SEAT SETS (§2co). A SEAT is a written hamza chair — the consonant a folded root radical cannot
# express. SEATISH adds the maters such a radical masquerades as. آ is deliberately NOT a seat here: it
# is a madda (ا + hamza) and is handled by its own rule at the stem/tail seam.
SEATS = frozenset("\u0623\u0625\u0624\u0626\u0621")          # أ إ ؤ ئ ء
SEATISH = SEATS | frozenset("\u0627\u0648\u064a")            # + ا و ي
WEAK = {"\u0648", "\u064a"}                                 # و ي
TAN = set("\u064b\u064c\u064d")                             # ً ٌ ٍ nunation
SEAM = re.compile(r"^[\u064b-\u0652\u0670]+")


VERBAL_STEM_TAILS = {
    "\u0652\u062a\u064f",      # ْتُ (1s past)
    "\u064e\u062a\u0652",      # َتْ (3fs past)
    "\u0652\u062a\u064e",      # ْتَ (2ms past)
    "\u0652\u062a\u0650",      # ْتِ (2fs past)
    "\u064f\u0648\u0627",      # ُوا (3mp past)
    "\u0652\u0646\u064e\u0627",  # ْنَا (1p past)
    "\u0652\u0646\u064e",      # ْنَ (3fp past)
    "\u0646\u064e",            # نَ
    "\u064e\u062a\u064e\u0627",  # َتَا (3fd past)
    "\u0652\u062a\u064f\u0645\u0652", # ْتُمْ (2mp past)
    "\u0652\u062a\u064f\u0646\u0651", # ْتُنَّ (2fp past)
    "\u064e\u0627",            # َا (3md past)
}


def is_verbal_tail(t: str | None) -> bool:
    if not t:
        return False
    return t in VERBAL_STEM_TAILS or any(t.endswith(s) for s in VERBAL_STEM_TAILS)


def is_verb_template(w: str | None) -> bool:
    if not w:
        return False
    w_clean = w.replace("\u0671", "\u0627")
    if any(w_clean.startswith(p) for p in (
        "يَ", "يُ", "يِ", "ي1", "ي2", "نَ", "نُ", "ن1", "أُ1", "أُ2",
        "تَ1َا", "تَ1َ2ّ", "تَتَ", "يَتَ", "نَتَ", "يَسْت", "تَسْت", "نَسْت",
        "يَ1", "يُ1", "تُ1", "تَ1ْت", "يَ1ْت", "نَ1ْت"
    )):
        return True
    if any(w_clean.startswith(p) for p in (
        "ا1ْتَ", "ٱ1ْتَ", "1ْتَ", "اِسْت", "ٱِسْت", "اسْت", "ٱسْت", "1سْت", "ا1ْن", "ان1"
    )):
        return True
    if any(w_clean.endswith(s) for s in (
        "ْتُ", "َتْ", "ْتَ", "ْتِ", "ُوا", "ْنَا", "ْنَ", "نَ", "َتَا", "ْتُمْ", "ْتُنَّ"
    )):
        return True
    if w_clean.endswith("3\u064e") or w_clean.endswith("3َ"):
        return True
    return False


def strip_diac(s: str | None) -> str:
    return DIAC.sub("", s or "")


def nfc(s: str | None) -> str | None:
    return None if s is None else uni.normalize("NFC", s)


def rasm(s: str | None) -> str:
    """Consonantal skeleton representation of an Arabic string.

    1. Strips all diacritics and tatweel.
    2. Folds hamza family (أ, إ, آ, ٱ, ء, ئ, ؤ) into bare alif 'ا'.
    3. Normalizes alif maqsura 'ى' to 'ي'.
    4. Normalizes ta marbuta 'ة' to 'ه'.
    """
    if not s:
        return ""
    s = DIAC.sub("", s)
    s = "".join("\u0627" if c in "أإآٱءئؤ" else c for c in s)
    return s.replace("\u0649", "\u064a").replace("\u0629", "\u0647")


def _cut_at_letter(s: str, keep_letters: int) -> str:
    """Prefix of `s` holding the first `keep_letters` LETTERS (diacritics ride along)."""
    cnt = 0
    for i, ch in enumerate(s):
        if not DIAC.match(ch):
            if cnt == keep_letters:
                return s[:i]
            cnt += 1
    return s


def candidates(token: str) -> list[str]:
    """Every legal reading of a token: 0-2 proclitics, then an optional enclitic.

    The zero-strip reading (the token itself) is always included, which is what makes
    the metric symmetric — see the module docstring.

    THE ENCLITIC EDGE IS CUT BY LETTER, NOT BY CHARACTER. `أَخْبَرَهُ` ends with a
    DAMMA, so `s.endswith("ه")` is False and an earlier version therefore failed every
    enclitic case — silently understating clitic-plane coverage.
    """
    seen, frontier = {token}, [token]
    for _ in range(2):
        nxt = []
        for s in frontier:
            for p in PRO:
                if s.startswith(p) and len(strip_diac(s)) > len(strip_diac(p)) + 1:
                    t = SEAM.sub("", s[len(p):])
                    if t not in seen:
                        seen.add(t)
                        nxt.append(t)
        frontier = nxt
    out = set(seen)
    for s in seen:
        sk = strip_diac(s)
        for e in ENC:
            if sk.endswith(e) and len(sk) > len(e) + 1:
                out.add(_cut_at_letter(s, len(sk) - len(e)))
                break
    return sorted(out, key=len, reverse=True)


def stem_match(gold_token: str, pred: str | None) -> bool:
    """THE DEFINITION. True iff `pred` equals the gold token modulo a legal affix split."""
    if pred is None or not gold_token:
        return False
    p = nfc(pred)
    return any(nfc(c) == p for c in candidates(gold_token))


def fold_hamza(s: str) -> str:
    return "".join("\u0627" if c in HAMZA else c for c in s)


def _diff(a: str, b: str):
    ca, cb = collections.Counter(a), collections.Counter(b)
    return ca - cb, cb - ca


def classify_defect(gold_token: str, pred: str) -> str:
    """First repair rule that reconciles `pred` with SOME reading of the gold token.

    Buckets are named ORTHOGRAPHIC rules so the counts are an implementation order.
    `clitic` and `canonical_order` are HARNESS/pipeline (a legal split already
    reconciles them); the rest are renderer defects.
    """
    cands = candidates(gold_token)
    if pred in cands:
        return "clitic"
    if any(nfc(c) == nfc(pred) for c in cands):
        return "canonical_order"
    same = [c for c in cands if strip_diac(c) == strip_diac(pred)]
    if same:
        return ("tanwin_missing" if (TAN & set(same[0])) and not (TAN & set(pred))
                else "diacritic_only")

    def cost(c):
        dg, dr = _diff(strip_diac(c), strip_diac(pred))
        return sum(dg.values()) + sum(dr.values())

    stem = min(cands, key=cost)
    a, b = strip_diac(stem), strip_diac(pred)
    if TAN & set(stem) and not _diff(a, b)[1] and _diff(a, b)[0] == collections.Counter({"\u0627": 1}):
        return "tanwin_alif_acc"          # ACC nunation is WRITTEN WITH AN ALIF
    if "\u0627\u0644\u0644\u0647" in a:
        return "divine_name"              # اللَّه
    if fold_hamza(a) == fold_hamza(b):
        return "hamza_seat"
    dg, dr = _diff(a, b)
    ch = set(dg) | set(dr)
    if ch and ch <= (ALIF | WEAK):
        if (set(dr) & WEAK) and not (set(dg) & WEAK):
            return "weak_radical_written"
        if (set(dg) & WEAK) and not (set(dr) & WEAK):
            return "weak_radical_missing"
        return "weak_or_hamza"
    if ch and ch <= ALIF:
        return "hamza_seat"
    if ch and ch <= {"\u062a", "\u0629"}:
        return "ta_marbuta"
    return "other"


def pattern_arity(pattern) -> int:
    """How many radical slots a wazān pattern asks for = its distinct digit count.

    The pattern head is the reliable one: measured 272/278 = 97.8% agreement on the radical-slot SET
    against the human gold, i.e. it essentially never confuses a 3-slot pattern with a 4-slot one.
    """
    return len({ch for ch in (pattern or "") if ch in "1234"})


def decode_root_slots(slots, pattern, inv_r) -> str:
    """Root head slots -> bare root string, SLICED TO THE PATTERN'S ARITY.

    PRONG 1 of CHALLENGES.md 2x.14. The root head's 4th slot is trained as IGNORE (-100) and never as
    <pad> (0) — measured, 97,294 of the 99,869 lettered PADT roots (97.4%) never supervise it — so
    ignore_index zeroes its gradient and its argmax is unconstrained noise that does not land on 0.
    Decoding all four slots therefore gave every triliteral root a length-4 string, which no 3-slot
    pattern accepts: 296/296 abstentions, all reasoned `root_len_mismatch`, and root accuracy 0/278.

    The arity comes from the PATTERN, not from the slots, because the pattern head is reliable and the
    4th slot is not. An unsupervised slot must never be read as content.

    ONE decoder: every path that turns root slots into a string must call THIS, not re-implement it —
    the dev and gold paths disagreeing (0.7458 vs 0.0000 on the SAME weights) is exactly how this defect
    stayed hidden.
    """
    arity = pattern_arity(pattern)
    n = arity if arity else len(slots)          # no pattern -> no arity to condition on
    return "".join(inv_r.get(s, "") for s in list(slots)[:n] if s)


class RootTrie:
    """A prefix trie over a root inventory, for CONSTRAINED root decoding (v12 Phase 3).

    WHY THIS EXISTS — and what it can and cannot buy (`CHALLENGES.md` §2z)
        An unconstrained per-slot argmax can emit a radical trio that is not a root at all.
        A trie makes that unreachable AT DECODE TIME. But the thing worth measuring is
        *which kind of error the head actually makes*, because the constraint only helps one:

          ILLEGALITY (structural hallucination): the emitted trio is not in the inventory.
              The constraint recovers these — it can only replace them with a real root.
          CONFUSION (lexical error): the emitted trio IS a real root, just not this word's.
              The constraint buys nothing here; it shuffles one wrong legal root into another.

        If the error budget is dominated by confusion the honest result is "no gain", and that
        is a result. This class exists so the question is decidable rather than assumed.
    """

    __slots__ = ("kids", "terms")

    def __init__(self, roots):
        self.kids: dict = {}
        self.terms: set = set()
        for r in roots:
            r = "".join(r)
            if not r:
                continue
            node = self.kids
            for ch in r:
                node = node.setdefault(ch, {})
            self.terms.add(r)

    def has_prefix(self, p: str) -> bool:
        node = self.kids
        for ch in p:
            node = node.get(ch)
            if node is None:
                return False
        return True

    def is_legal(self, s: str) -> bool:
        return s in self.terms

    def __len__(self) -> int:
        return len(self.terms)


def _log_softmax(row):
    m = max(row)
    e = [math.exp(x - m) for x in row]
    z = math.fsum(e)
    lz = math.log(z)
    return [x - m - lz for x in row]


def decode_root_slots_beamed(slot_logits, pattern, inv_r, trie, beam=5):
    """Root slots -> bare root, by BEAM SEARCH over the JOINT slot log-probs, TRIE-PRUNED.

    NOT a per-slot mask. Masking only the last slot after greedily taking the first two is the
    trap: if slot 1 is the mistake (a weak prefix letter read as a radical) then fixing slots 1-2
    forces slot 3 down a wrong branch, or forces an abstention. The joint objective

        log P(r1,r2,r3 | h) = sum_i log P(r_i | h)

    with pruning at every step explores the alternatives that the greedy path never reaches. With
    a 3- or 4-slot root and <=34 radical types the search is trivially cheap (<=5x34 paths/step).

    Fallback is NEVER silent: if no complete legal root is reachable the SHARED `decode_root_slots`
    is used (so coverage is never lost to the constraint) and the row is reported `fell_back=True`.
    A silent fallback would hide exactly the rows the constraint failed on.

    Returns a dict:
      root           final decoded root string
      argmax_root    the unconstrained decode of the same row (the comparison baseline)
      legal_path     True iff a complete legal root was reachable
      fell_back      True iff no legal path existed and argmax_root was used instead
      illegal_before True iff argmax_root is NOT in the inventory  <- the illegality indicator
      changed        True iff the constrained decode differs from argmax_root
      beam_score     joint log-prob of the chosen path (None when fell back)
      arity          number of slots the pattern asked for
    """
    arity = pattern_arity(pattern)
    n = arity if arity else len(slot_logits)
    rows = [_log_softmax(list(r)) for r in slot_logits[:n]]

    arg_slots = [max(range(len(r)), key=lambda j: r[j]) for r in rows]
    arg_root = decode_root_slots(arg_slots, pattern, inv_r)     # the ONE shared decoder

    # beam over prefixes, pruned against the trie at EVERY step
    beams = [(0.0, "")]
    for i in range(n):
        row = rows[i]
        cand: dict = {}
        for sc, pre in beams:
            for j in range(1, len(row)):          # id 0 is <pad>, never a radical letter
                ch = inv_r.get(j)
                if not ch:
                    continue
                nxt = pre + ch
                if not trie.has_prefix(nxt):
                    continue
                v = sc + row[j]
                if v > cand.get(nxt, float("-inf")):
                    cand[nxt] = v
        if not cand:
            beams = []
            break
        beams = [(v, p) for p, v in
                 sorted(cand.items(), key=lambda kv: kv[1], reverse=True)[:beam]]

    best = None
    for sc, pre in beams:
        if len(pre) == n and trie.is_legal(pre):
            best = (sc, pre)
            break

    out = {"argmax_root": arg_root, "illegal_before": not trie.is_legal(arg_root),
           "arity": n, "beam": beam}
    if best is None:
        out.update(root=arg_root, legal_path=False, fell_back=True, changed=False,
                   beam_score=None)
    else:
        out.update(root=best[1], legal_path=True, fell_back=False,
                   changed=(best[1] != arg_root), beam_score=best[0])
    return out


LAST_TRACE: list[dict] = []


def render_triple(root: str | None, pattern: str | None,
                  case: int | None = None, engine: str = "v3",
                  token: str | None = None, repairs: bool = True,
                  affix_plane: bool = True, tanwin: bool = False,
                  definiteness: int | None = None, stem_tail: str | None = None,
                  resource: bool = True, trace: list[dict] | None = None):
    """(root, wazān, case) -> (surface | None, reason). The renderer IS the pipeline.

    `engine` picks the digit rule:
      'v1' digit in place (renderer.render_rule)
      'v2' Steps 1-2 with early commitment (render_rules.render_v2)
      'v3' Pass A/Pass B weak-radical re-realization (render_rules.render_v3)  <- default
    Imported lazily so this module is importable without pulling either in (they import
    THIS module for the taxonomy, and a top-level import would be a cycle).

    `token` — THE CLITIC PLANE AS AN INPUT (added 2026-10-12, `EVIDENCE_LOG.md` §2bc).
    When the surrounding token is supplied, the stem is passed through the token's own
    affix plane before it is returned, because some orthography is conditioned by what
    surrounds the stem and cannot be derived from `(root, wazān, case)`:

        خِدْمَة + هُ  ->  خِدْمَتِهُ    (a stem-final ة is written ت before a pronominal enclitic)

    WHY THIS IS AN INPUT AND NOT A LEAK. The token is what the model READS; its affix split
    is derivable at inference exactly as it is here. Nothing about the LABEL (root, wazān,
    case, pattern) is read. The tempting alternative — teaching `render_v3` a ta-marbuta
    rule — is impossible in principle: `render_v3` receives `(root, pattern)` and never sees
    the enclitic (measured: 11 rows of the benchmark turn on exactly this, and 70 of 521
    failures carry an enclitic at all).

    `repairs` — THE DIACRITIC REPAIR LAYER (added 2026-10-12, §2be/§2bg). Four rules that
    were each measured on the frozen ruler before they were written here (+62, +51, +3, +2
    rows, and the two candidates that LOSE rows are deliberately absent). They run after the
    clitic plane because every one of them is a statement about the final orthography, not
    about a radical. **The switch exists for ATTRIBUTION, not for production**: a measuring
    tool must be able to ask what the pipeline looked like before this layer, or the layer's
    own effect becomes unmeasurable the moment it ships — `tools/diacritic_split.py` depends
    on exactly that, and asserts both the before and after numbers.

    Passing `token=None` (the default) reproduces the pre-2026-10-12 behaviour bit for bit —
    which is what makes this a *declared* change rather than a silent one: every caller that
    has the token must pass it, and the callers that do not are unchanged.

    `affix_plane` — THE AFFIX PLANE (added 2026-10-13, §2cd). Splices the token's own proclitic
    and enclitic around the rendered stem, accepted only when the skeletons line up exactly.
    Measured BEFORE shipping: with the resource OFF and a 100% gold triple, this compiler was
    **15.8% token-exact but 60.8% stem-level**, and the entire gap was this plane — **146 of 278
    rows (52.5%)** carry an affix that `(root, wazān, case)` does not encode. It runs LAST, so
    every layer above it still receives the bare stem.

    `tanwin` / `definiteness` — AUTOSEGMENTAL NUNATION (added 2026-10-13). Encodes the missing
    definiteness state (1 = INDEFINITE_TANWIN), lifting the ceiling by over 13 percentage points
    by emitting nunation vowels (ٌ ً ٍ) rather than bare short vowels.
    """
    global LAST_TRACE
    if trace is None and os.environ.get("ARABIC_TRACE", "0") == "1":
        trace = []
        LAST_TRACE = trace
    elif trace is not None:
        LAST_TRACE = trace

    if engine == "v1":
        from renderer import render_rule
        surface, why = render_rule(root, pattern)
        if trace is not None and surface is not None:
            trace.append({"stage": "renderer", "rule_id": "render_rule",
                          "before": pattern, "after": surface, "changed": pattern != surface})
    else:
        from render_rules import ENGINES
        if engine not in ENGINES:
            raise ValueError(f"unknown engine {engine!r}; have {sorted(ENGINES)}")
        fn = ENGINES[engine]
        try:
            surface, why = fn(root, pattern, trace=trace)
        except TypeError:
            surface, why = fn(root, pattern)
    if surface is None:
        # A FALLBACK MUST BE A TRUE FALLBACK (§2bt). The corpus resource is keyed on the TOKEN's skeleton and
        # does not depend on the renderer at all, so trapping it behind the digit engine's success made it
        # unreachable exactly when the engine had nothing to say. Measured before shipping: **+3 rows on the
        # 300-row contextual gold (52.0% -> 53.0%)**, and a **measured no-op on the frozen ruler** (827 -> 827,
        # whose coverage is 100% by construction) — so this fix has zero counterexamples on either instrument.
        # With the resource OFF (`ARABIC_SPELLING_RESOURCE=0`) this branch returns exactly what it returned
        # before, which is what keeps every pre-existing probe reading the surface pipeline unchanged.
        # [comment restored 2026-10-13 — an agent rewrite dropped it; the decision it records is still live]
        if resource and token:
            form = apply_spelling_resource(None, token, case, resource=resource)
            if form:
                if trace is not None:
                    trace.append({"stage": "spelling_resource", "rule_id": "apply_spelling_resource",
                                  "before": None, "after": form, "changed": True})
                return form, "resource_only"
        return None, why
    from renderer import apply_case
    # THE STEM TAIL IS AN INPUT (§2ck). `tail_strip` removes the inflectional run after the last
    # radical digit to build Head-3's class, and that run is WRITTEN ORTHOGRAPHY — ة / ات / ون / ين /
    # ان / ت. On the 42.4% of gold rows carrying one, the stripped render cannot reach the token, and
    # in the rasm-constrained decoder it cannot satisfy a filter written against the FULL word (§2cj),
    # which is the mechanism behind resource-off 0.0%. The tail belongs to the STEM, so it is appended
    # BEFORE the case vowel — the case mark then lands on the tail's last letter
    # (مُقَدِّم + َات + GEN -> مُقَدِّمَاتٍ). `None` (the default) is a strict no-op.
    #
    # TWO GUARDS, both measured on gold-300 (§2cl) — neither is a row-id hack:
    #  (a) REJECTED, AND THE MEASUREMENT IS WHY. I first skipped tails with no consonants ("a bare case
    #      vowel is `case`'s job, not the tail's"). It cost **29 rows** (57.6% -> 47.1%): on rows whose
    #      gold `case` is None/ABSTAIN, the pattern's terminal diacritic is the ONLY carrier of the
    #      final vowel, so dropping it produced وَقَال for وَقَالَ. The terminal diacritic is a real
    #      signal and the tail keeps it. **Do not re-add that guard without re-measuring.**
    #  (b) A TAIL ALREADY REALISED IS NOT RE-APPENDED. On defective R3 the last radical IS written as
    #      the tail: يُوحَى has pattern يُ1ْ2َ3ى, so the stripped core already renders يُوحَى and
    #      appending ى gave يُوحَىى. This was the ONLY cause of the two rows that regressed when the
    #      tail was first wired, and the guard is a phonological statement — "the tail's letters are
    #      already on the page" — not a list of exceptions. A tail with no letters has nothing to
    #      duplicate, so it is always appended.
    if stem_tail:
        t_sk = strip_diac(stem_tail)
        if not t_sk or not strip_diac(surface or "").endswith(t_sk):
            #  (c) HOLLOW CONTRACTION AT THE SEAM (§2cm, 2026-10-14). A hollow stem's long vowel is
            #      ELIDED before a tail that begins with a sukūn — قُول + ْتُ -> قُلْتُ, the classical
            #      ḥadhf (compare لَمْ يَقُلْ, قُلْ). EVERY ELEMENT OF THE TRIGGER IS ON THE PAGE: the
            #      tail's first mark is a sukūn (ْ), and the stem's final letter is preceded by a mater
            #      (ا و ي) carrying its own short vowel. Nothing is read from the gold. Measured on
            #      gold-300: this is the `weak_radical_written` bucket of the §2cl residual census
            #      (6 rows — فَقُلْتُ was rendering قُولْتُ). §2cg's verdict says the remaining deficit
            #      is rule coverage on the WEAK classes, and this is the first rule taken from that
            #      census; its fixed/broken pair is measured in §2cm, not assumed.
            #      AN OPTIONAL SUKŪN SITS BETWEEN THE MATER AND THE FINAL LETTER, because the pattern
            #      writes it literally: `1ُ2ْ3` renders قُوْل, and قُوْل/قُول are the same stem. The
            #      guard accepts both spellings, which is why it tests the character AFTER skipping
            #      the sukun rather than a fixed offset.
            s = surface or ""
            done = False
            if stem_tail[:1] == SUKUN and len(s) >= 4 and not DIAC.match(s[-1]):
                k = 3 if s[-2] == SUKUN else 2
                if s[-k] in MATER and s[-k - 1] in SHORT_VOWEL:
                    surface = s[:-k] + s[-1:] + stem_tail
                    done = True
                    if trace is not None:
                        trace.append({"stage": "stem_tail", "rule_id": "iltiqāʾ al-sākinayn",
                                      "before": s + stem_tail, "after": surface, "changed": True})
            #  (d) THE TAIL'S WEAK LETTER WINS AT THE SEAM (§2cn). The surface's final ا is the
            #      renderer's realization of a weak R3, and the tail spells that SAME letter again —
            #      as ى/ي, or as a long alif. Appending duplicates it (تَعَالَا + ى -> تَعَالَاى,
            #      أُصَلِّا + ي -> أُصَلِّاي, قُرْا + َان -> قُرْاَان). REPLACE instead: the tail's own
            #      letter is the correct realization, and two adjacent alifs merge into the madda آ,
            #      which is what the human wrote in قُرْآن. Both are orthography, not morphology.
            if not done and s.endswith("\u0627") and t_sk[:1] in "\u0649\u064a":
                surface = s[:-1] + stem_tail
                done = True
                if trace is not None:
                    trace.append({"stage": "stem_tail", "rule_id": "stem_tail:weak_letter_seam",
                                  "before": s + stem_tail, "after": surface, "changed": True})
            if not done and s.endswith("\u0627") and t_sk[:1] == "\u0627":
                # the tail's own alif may carry the pattern's fatha BEFORE it (`َان`), so strip the
                # leading mark first and the alif second — the reverse order leaves a double alif.
                rest = stem_tail
                if rest[:1] == FATHA:
                    rest = rest[1:]                      # ... its fatha, which the madda carries ...
                if rest[:1] == "\u0627":
                    rest = rest[1:]                      # ... and its own alif
                surface = s[:-1] + "\u0622" + rest       # آ — ا + ا, written as the human wrote it
                done = True
                if trace is not None:
                    trace.append({"stage": "stem_tail", "rule_id": "stem_tail:madda_merge",
                                  "before": s + stem_tail, "after": surface, "changed": True})
            if not done:
                prev_s = surface
                surface = s + stem_tail
                if trace is not None:
                    trace.append({"stage": "stem_tail", "rule_id": "stem_tail:append",
                                  "before": prev_s, "after": surface, "changed": prev_s != surface})
    # A FINAL WEAK R3 IS WRITTEN AS THE PATTERN WRITES IT (§2cn) — see `align_weak_r3`. It runs here,
    # after the tail is in place and before the case vowel, so the case mark still lands last.
    prev_w3 = surface
    surface = align_weak_r3(surface, pattern)
    if trace is not None:
        trace.append({"stage": "weak_r3", "rule_id": "align_weak_r3",
                      "before": prev_w3, "after": surface, "changed": prev_w3 != surface})
    # THEN RE-SEAT THE HAMZA RADICAL FROM THE TOKEN (§2co). This runs BEFORE the affix plane on purpose:
    # the plane matches `skel(token) == pro + skel(stem) + enc`, so a stem still carrying the root's
    # folded bare ا cannot be framed at all (الْمَرْءِ), and re-seating first is what lets the proclitic
    # attach without loosening the frame's own guard.
    prev_hz = surface
    surface = project_hamza_from_input(surface, token)
    if trace is not None:
        trace.append({"stage": "hamza_seat", "rule_id": "project_hamza_from_input",
                      "before": prev_hz, "after": surface, "changed": prev_hz != surface})
    # NUNATION IS AN INPUT, NOT A DERIVATION (2026-10-13). `definiteness` is supplied by the new
    # definiteness head because indefiniteness is encoded NOWHERE in (root, wazān, case) — it is
    # exactly the 25 rows / 9.0% of gold-300 that no compiler could reach (§2ce). WHEN IT IS
    # SUPPLIED FROM GOLD THE RESULT IS AN ORACLE CEILING, NOT A PIPELINE NUMBER: the
    # `tools/bench_autosegmental_eval.py` figure of 72.02% (+13.83 pp) reads the GOLD token for
    # definiteness (`extract_gold_definiteness`), so it BOUNDS this architecture and does not
    # predict what a trained head will score. The predicted-definiteness number is the one that
    # counts, and it has not been measured. Compare §2ce's method: the affix plane was audited the
    # same way and its headline was an oracle until it was made invariant.
    is_tw = bool(tanwin or (definiteness == 1))
    out = apply_case(surface, case, tanwin=is_tw, definiteness=definiteness, stem_tail=stem_tail, trace=trace)
    # THE MANQŪṢ INDEFINITE READS THE CASE MARK apply_case JUST PLACED (§2co) — it has to run after it,
    # because what it changes is the case ending itself.
    prev_mq = out
    out = repair_manqus_indefinite(out, pattern, case, definiteness)
    if trace is not None:
        trace.append({"stage": "manqus", "rule_id": "repair_manqus_indefinite",
                      "before": prev_mq, "after": out, "changed": prev_mq != out})
    if token:
        prev_cp = out
        out = apply_clitic_plane(out, token)
        if trace is not None:
            trace.append({"stage": "clitic_plane", "rule_id": "apply_clitic_plane",
                          "before": prev_cp, "after": out, "changed": prev_cp != out})
        if repairs:
            out = apply_diacritic_repairs(out, token, case, trace=trace)
        # THE AFFIX PLANE, LAST (§2cd): the layers above still see the BARE STEM, which is what
        # keeps this additive. `ARABIC_AFFIX_PLANE=0` disables it for attribution, the same reason
        # `repairs` and `ARABIC_SPELLING_RESOURCE` exist.
        # [comment restored 2026-10-13 — an agent rewrite dropped it]
        if affix_plane and os.environ.get("ARABIC_AFFIX_PLANE", "1") != "0":
            prev_ap = out
            out = attach_affix_plane(out, token, case, tanwin=is_tw)
            if trace is not None:
                trace.append({"stage": "affix_plane", "rule_id": "attach_affix_plane",
                              "before": prev_ap, "after": out, "changed": prev_ap != out})
        if resource:
            prev_sp = out
            out = apply_spelling_resource(out, token, case, resource=resource)
            if trace is not None:
                trace.append({"stage": "spelling_resource", "rule_id": "apply_spelling_resource",
                              "before": prev_sp, "after": out, "changed": prev_sp != out})
    return out, "ok"


def decode_rasm_constrained(
    root_logits,
    wazan_logits,
    case_logits=None,
    stem_tail_logits=None,
    def_logits=None,
    inv_r: dict | None = None,
    inv_w: dict | None = None,
    inv_tail: dict | None = None,
    token: str | None = None,
    engine: str = "v3",
    trie=None,
    top_k_w: int = 5,
    top_k_r: int = 5,
    top_k_t: int = 3,
    top_k_c: int = 3,
    top_k_d: int = 2,
    resource: bool = False,
):
    """Lattice decoding constrained by the token's UNVOCALIZED rasm (Task 4 / Gate 4).

    LEAK-FREE BY CONSTRUCTION (§2ci).
      1. `bare_token = strip_diac(token)` upfront — zero gold diacritics can ever be read.
      2. Top-5 beamed roots from decode_root_slots_beamed (enforces membership in RootTrie),
         top-5 wazan stems, top-3 stem_tail suffixes, top-3 case, top-2 definiteness.
      3. Fast Pre-Render Pruning (CPU latency < 15s per checkpoint):
         - Skip any (root, wazan) pair where pattern_arity(wazan) != len(root).
         - Enforce geminate consistency: if len(root) == 3 and root[1] == root[2] (mudaʿʿaf),
           penalize patterns lacking shadda or missing slot 3; if root[1] != root[2], reject
           2-slot geminate-only patterns.
         - Pre-check base render rasm(base_surf) against token_rasms before looping over case/def.
      4. Render with rules only (resource=False, token=bare_token, stem_tail=tail, definiteness=defn).
      5. Keep candidates whose rendered consonant skeleton matches rasm(bare_token) (or a legal
         affix split of bare_token), and pick candidate maximizing:
         S(y) = log P(root) + log P(wazan) + log P(stem_tail) + log P(case) + log P(definiteness).
         If no candidate matches, fallback to top arity-matched beamed (root, wazan, stem_tail, case, def)
         and log rasm_fallback: True.

    Returns:
      (best_root, best_wazan, best_case, best_surface, match_found)
    """
    bare_token = strip_diac(token) if token else ""
    token_rasms = {rasm(c) for c in candidates(bare_token)} if bare_token else set()
    if bare_token:
        token_rasms.add(rasm(bare_token))

    import torch

    # Normalize log probabilities
    if isinstance(wazan_logits, torch.Tensor):
        wazan_lsm = torch.log_softmax(wazan_logits.float(), dim=-1)
        root_lsm = torch.log_softmax(root_logits.float(), dim=-1)
        case_lsm = torch.log_softmax(case_logits.float(), dim=-1) if case_logits is not None else None
        tail_lsm = torch.log_softmax(stem_tail_logits.float(), dim=-1) if stem_tail_logits is not None else None
        def_lsm = torch.log_softmax(def_logits.float(), dim=-1) if def_logits is not None else None

        top_w_idx = torch.topk(wazan_lsm, min(top_k_w, wazan_lsm.shape[-1])).indices.tolist()
        w_scores = [float(wazan_lsm[j]) for j in top_w_idx]
    else:
        wazan_lsm = _log_softmax(list(wazan_logits))
        root_lsm = [_log_softmax(list(r)) for r in root_logits]
        case_lsm = _log_softmax(list(case_logits)) if case_logits is not None else None
        tail_lsm = _log_softmax(list(stem_tail_logits)) if stem_tail_logits is not None else None
        def_lsm = _log_softmax(list(def_logits)) if def_logits is not None else None

        top_w_idx = sorted(range(len(wazan_lsm)), key=lambda j: wazan_lsm[j], reverse=True)[:top_k_w]
        w_scores = [float(wazan_lsm[j]) for j in top_w_idx]

    w_cands = [(inv_w.get(j), w_scores[k]) for k, j in enumerate(top_w_idx) if inv_w and inv_w.get(j)]

    # Stem tail candidates
    if tail_lsm is not None:
        if isinstance(tail_lsm, torch.Tensor):
            t_idx = torch.topk(tail_lsm, min(top_k_t, tail_lsm.shape[-1])).indices.tolist()
            t_cands = [(inv_tail.get(j, "") if inv_tail else "", float(tail_lsm[j])) for j in t_idx]
        else:
            t_idx = sorted(range(len(tail_lsm)), key=lambda j: tail_lsm[j], reverse=True)[:top_k_t]
            t_cands = [(inv_tail.get(j, "") if inv_tail else "", float(tail_lsm[j])) for j in t_idx]
    else:
        t_cands = [("", 0.0)]

    # Case candidates
    if case_lsm is not None:
        if isinstance(case_lsm, torch.Tensor):
            c_indices = torch.topk(case_lsm, min(top_k_c, case_lsm.shape[-1])).indices.tolist()
            c_cands = [(int(c), float(case_lsm[c])) for c in c_indices] + [(None, 0.0)]
        else:
            c_indices = sorted(range(len(case_lsm)), key=lambda j: case_lsm[j], reverse=True)[:top_k_c]
            c_cands = [(int(c), float(case_lsm[c])) for c in c_indices] + [(None, 0.0)]
    else:
        c_cands = [(None, 0.0)]

    # Definiteness candidates
    if def_lsm is not None:
        if isinstance(def_lsm, torch.Tensor):
            d_indices = torch.topk(def_lsm, min(top_k_d, def_lsm.shape[-1])).indices.tolist()
            d_cands = [(int(d), float(def_lsm[d])) for d in d_indices]
        else:
            d_indices = sorted(range(len(def_lsm)), key=lambda j: def_lsm[j], reverse=True)[:top_k_d]
            d_cands = [(int(d), float(def_lsm[d])) for d in d_indices]
    else:
        d_cands = [(None, 0.0)]

    # Pre-extract beamed root candidates by arity (3 and 4, or 2)
    root_rows = root_lsm.tolist() if isinstance(root_lsm, torch.Tensor) else root_lsm

    def get_beamed_roots_for_arity(n_slots):
        if n_slots > len(root_rows):
            return []
        rows = root_rows[:n_slots]
        if trie is not None:
            beams = [(0.0, "")]
            for i in range(n_slots):
                row = rows[i]
                cand = {}
                for sc, pre in beams:
                    for j in range(1, len(row)):  # id 0 is pad
                        ch = inv_r.get(j)
                        if not ch:
                            continue
                        nxt = pre + ch
                        if not trie.has_prefix(nxt):
                            continue
                        v = sc + row[j]
                        if v > cand.get(nxt, float("-inf")):
                            cand[nxt] = v
                if not cand:
                    beams = []
                    break
                beams = [(v, p) for p, v in sorted(cand.items(), key=lambda kv: kv[1], reverse=True)[:top_k_r]]
            legal = [(p, v) for v, p in beams if len(p) == n_slots and trie.is_legal(p)]
            if legal:
                return legal
            # If no legal path found, fallback to argmax decoded root
            slots = [max(range(len(r)), key=lambda j: r[j]) for r in rows]
            return [(decode_root_slots(slots, "1" * n_slots, inv_r), 0.0)]
        else:
            top_slots = [sorted(range(1, len(r)), key=lambda j: r[j], reverse=True)[:top_k_r] for r in rows]
            beams = [(0.0, "")]
            for i in range(n_slots):
                nxt_beams = []
                for sc, pre in beams:
                    for j in top_slots[i]:
                        ch = inv_r.get(j, "")
                        nxt_beams.append((sc + rows[i][j], pre + ch))
                nxt_beams.sort(key=lambda x: x[0], reverse=True)
                beams = nxt_beams[:top_k_r]
            return [(p, v) for v, p in beams]

    beamed_roots_by_arity = {}
    for pw, _ in w_cands:
        ar = pattern_arity(pw) or 3
        if ar not in beamed_roots_by_arity:
            beamed_roots_by_arity[ar] = get_beamed_roots_for_arity(ar)

    if 3 not in beamed_roots_by_arity:
        beamed_roots_by_arity[3] = get_beamed_roots_for_arity(3)

    best_candidate = None
    best_score = float("-inf")

    for pw, w_score in w_cands:
        arity = pattern_arity(pw) or 3
        # If arity is 2, it can match geminate 3-slot roots
        lookup_arity = 3 if arity == 2 else arity
        r_cands = beamed_roots_by_arity.get(lookup_arity, [])

        for _r, r_score in r_cands:
            # Geminate consistency
            is_geminate = (len(_r) == 3 and _r[1] == _r[2])
            if arity == 2:
                if not is_geminate:
                    continue  # reject 2-slot geminate-only patterns for non-geminates
            elif arity != len(_r):
                continue

            geminate_penalty = 0.0
            if is_geminate:
                if "3" not in pw and "\u0651" not in pw:
                    continue  # missing slot 3 and lacking shadda completely
                elif "\u0651" not in pw:
                    geminate_penalty = 2.0

            for tail_str, tail_score in t_cands:
                base_score = w_score + r_score + tail_score - geminate_penalty
                if base_score <= best_score - 20.0:
                    continue

                # Fast pre-render pruning:
                base_surf, _ = render_triple(_r, pw, None, token=bare_token,
                                             engine=engine, stem_tail=tail_str,
                                             definiteness=None, resource=False)
                if not base_surf:
                    continue
                bs_rasm = rasm(base_surf)
                if bs_rasm not in token_rasms and (bs_rasm + "\u0627") not in token_rasms:
                    continue

                for c_val, c_score in c_cands:
                    for d_val, d_score in d_cands:
                        tot_score = base_score + c_score + d_score
                        if tot_score <= best_score:
                            continue
                        surf, why = render_triple(_r, pw, c_val, token=bare_token,
                                                  engine=engine, stem_tail=tail_str,
                                                  definiteness=d_val, resource=False)
                        if surf and rasm(surf) in token_rasms:
                            if tot_score > best_score:
                                best_score = tot_score
                                best_candidate = (_r, pw, c_val, surf, True)

    if best_candidate is not None:
        return best_candidate

    # Fallback to top arity-matched beamed candidate
    pw_top = w_cands[0][0] if w_cands else (inv_w.get(0) if inv_w else None)
    ar_top = pattern_arity(pw_top) or 3
    lookup_ar = 3 if ar_top == 2 else ar_top
    r_top_cands = beamed_roots_by_arity.get(lookup_ar) or beamed_roots_by_arity.get(3, [("", 0.0)])
    r_top = r_top_cands[0][0] if r_top_cands else ""
    tail_top = t_cands[0][0] if t_cands else ""
    c_top = c_cands[0][0] if c_cands else None
    d_top = d_cands[0][0] if d_cands else None

    surf_fb, _ = render_triple(r_top, pw_top, c_top, token=bare_token, engine=engine,
                               stem_tail=tail_top, definiteness=d_top, resource=False)
    return r_top, pw_top, c_top, surf_fb, False




# ------------------------------------------------------- the clitic plane's effects
TA, TE = "\u0629", "\u062a"          # ة ت


def pronominal_enclitic(token: str) -> str | None:
    """The pronominal enclitic this token carries, using THE SAME test `candidates()` uses.

    Deliberately not a second implementation: the metric decides what counts as an enclitic,
    so the assembly layer must agree with it or the two will disagree exactly where it
    matters. Same guards: `endswith(e)` on the diacritic-stripped skeleton, and enough stem
    left to be a real stem (`len(sk) > len(e) + 1`).
    """
    sk = strip_diac(token) or ""
    for e in ENC:
        if sk.endswith(e) and len(sk) > len(e) + 1:
            return e
    return None


def apply_clitic_plane(surface: str | None, token: str) -> str | None:
    """Apply the token's affix plane to a stem. Currently one rule, measured: ة -> ت.

    `خِدْمَةِ` + enclitic `هم` -> `خِدْمَتِ`  (the citation form is خِدْمَة; in context the
    ta-marbuta is written ta). The rule is conditioned on the ENCLITIC, so it cannot fire on
    a token without one — a stem-final ة in a bare noun (مَرْأَة) is untouched, which is what
    keeps it from being a blanket rewrite.
    """
    if not surface or pronominal_enclitic(token) is None:
        return surface
    i = surface.rfind(TA)
    if i < 0:
        return surface
    return surface[:i] + TE + surface[i + 1:]


# ------------------------------------------------------- the diacritic repair layer
# Four rules, each MEASURED on the frozen ruler before it was written here
# (`tools/diacritic_split.py --check` asserts every one of these numbers; EVIDENCE_LOG §2be/§2bg):
#
#     repair_sun_letter_shadda   +62 rows, 0 broken
#     repair_hamza_fatha         +51 rows, 0 broken
#     repair_long_vowel_sukun     +3 rows, 0 broken
#     repair_dual_nominative      +2 rows, 2 broken
#     ------------------------------------------------------------------
#     jointly                   583/973 = 59.9%   (from 463/973 = 47.6%)
#
# They repair the ASSEMBLED surface rather than a radical, because each is a fact about final
# orthography: whether a sun letter carries its assimilation shadda, whether a bare seat carries its
# vowel, whether a long vowel was wrongly closed, and which vowel a dual nominative ends in. Two
# further candidates were measured and are deliberately ABSENT — they lose rows overall
# (`drop_redundant_hamza_kasra` −5, `apply_diptote_fatha` −34, the latter because a suffix test is
# not a diptote test) — and the numbers, not a preference, are why.

SUN_LETTERS = frozenset("\u062a\u062b\u062f\u0630\u0631\u0632\u0633\u0634\u0635\u0636\u0637\u0638\u0644\u0646")
SHADDA = "\u0651"
SUKUN = "\u0652"
# The seam rules' alphabets (§2cm). A MATER is a long-vowel letter standing in for ا/و/ي; a SHORT_VOWEL is
# the ḥaraka it carries. Used only by the hollow-contraction guard at the stem/tail seam.
MATER = "\u0627\u0648\u064a"                     # ا و ي
SHORT_VOWEL = "\u064e\u064f\u0650"               # َ ُ ِ
FATHA = "\u064e"
KASRA = "\u0650"
DAMMA = "\u064f"
_DEFINITE_PRO = ("وال", "فال", "بال", "كال", "ال", "لل")


CASE_STR = {"NOM": 0, "ACC": 1, "GEN": 2}


def case_int(raw) -> int | None:
    """`NOM`/`ACC`/`GEN`, the case's own vowel mark, or an int -> the renderer's case index (or None).

    One implementation for the pipeline and for every measuring tool. The tools had each grown a private
    copy, which is how two instruments end up disagreeing about what case a row asks for — the same reason
    `is_definite` lives here rather than in each caller.
    """
    if isinstance(raw, int):
        return raw
    if not isinstance(raw, str):
        return None
    raw = raw.strip()
    if raw in CASE_STR:
        return CASE_STR[raw]
    from renderer import CASE_VOWEL          # 0 damma, 1 fatha, 2 kasra
    return {v: k for k, v in CASE_VOWEL.items()}.get(raw)


def is_definite(token: str) -> bool:
    """Does the token carry a definite-article proclitic (`الـ`, `والـ`, `للـ`, …)?

    A LEGAL INPUT, and the reason the sun-letter and tanwīn rules are allowed to look at the token at
    all: the model reads the token, so its proclitic is available at inference exactly as it is here.
    Nothing about the label is read. Deliberately one implementation, shared with the measuring tools —
    a second copy would disagree with this one exactly where it matters.
    """
    return (strip_diac(token) or "").startswith(_DEFINITE_PRO)


def repair_sun_letter_shadda(surface: str, token: str) -> str:
    """`الشْمس` -> `الشَّمس`: write the shadda a sun-letter assimilation requires.

    The rule cannot be blind: a shadda is written after a sun letter ONLY because a definite
    article is assimilating into it, so it is gated on the token being definite. It fires on the
    stem's first written letter and only there (+62 rows, 0 broken — the largest single rule in the
    bucket, and the one no hand-eyeball decomposition of the examples had found).
    """
    if not is_definite(token):
        return surface
    for i, ch in enumerate(surface):
        if DIAC.match(ch):
            continue
        if ch in SUN_LETTERS and SHADDA not in surface[i + 1:i + 3]:
            return surface[:i + 1] + SHADDA + surface[i + 1:]
        return surface
    return surface


def repair_hamza_fatha(surface: str) -> str:
    """`أنْصَارِ` -> `أَنْصَارِ`: a bare seat at a word's start carries its vowel.

    Gated three ways so it cannot become a blanket insert: the seat must be the word-initial `أ`, the
    next character must not already be a mark, and it must not be the long-vowel letters ا/و (where a
    bare seat is correct: `أُولَئِكَ`, `أَوْلَاد`). Surface-only — it reads no row data at all.
    """
    if surface.startswith("\u0623") and len(surface) > 1 and not DIAC.match(surface[1]) \
            and surface[1] not in "\u0627\u0648":
        return "\u0623" + FATHA + surface[1:]
    return surface


def repair_long_vowel_sukun(surface: str) -> str:
    """A long vowel is never closed: drop the sukun the pattern does not licence (`صُوْرَةِ`)."""
    return surface.replace("\u064f\u0648" + SUKUN, "\u064f\u0648").replace("\u0650\u064a" + SUKUN, "\u0650\u064a")


def repair_dual_nominative(surface: str, case: int | None) -> str:
    """A dual nominative ends in kasra (`مَخْبِزَانِ`), not damma.

    Conditional on the CASE, which is a model head and not a label — it is the renderer's own input in
    exactly the way the wazān is. This is the one rule of the four that costs anything (+4 rows, 2
    broken) and it was kept because +2 net with the two losses visible is still the best trade on the
    ruler; the trade is recorded rather than hidden.
    """
    if case != 0:
        return surface
    if surface.endswith("\u0627\u0646" + DAMMA):
        return surface[:-1] + KASRA
    if surface.endswith("\u0627\u0646"):
        return surface + KASRA
    return surface


def repair_initial_hamza_seat(surface: str, token: str) -> str:
    """`إقْلَالِ` -> a bare seat — but ONLY when the seat begins the token.

    **The gate IS the rule.** Ungated (strip the kasra from any word-initial `إِ`) this measures **−4**: it
    wins 9 rows and breaks 13, and every one of the 13 carries a proclitic in front of the seat
    (لِإِظْهَارِ, بِإِنْشَارِ, الْإِفْرَاطَ …), where the human *does* write the kasra. Gated on the seat being
    token-initial: **+9 rows, 0 broken**. The input is the token's own proclitic — the same legal signal the
    sun-letter and definiteness gates use, not a row list and not a label.

    Found by dumping the residual: the 9 wanted rows and the 13 the ungated rule broke separate perfectly on
    this one feature, which is the difference between "lexical, needs a lexicon" and "decidable at the surface".
    """
    if not surface.startswith("\u0625\u0650"):
        return surface
    if not (strip_diac(token) or "").startswith(("\u0625", "\u0623")):
        return surface                       # a proclitic precedes the seat: keep the kasra
    return "\u0625" + surface[2:]


DIVINE_NAME = "\u0627\u0644\u0644\u0651\u064e\u0647"        # اللَّه — ا ل ل ّ َ ه
CASE_VOWEL = {0: "\u064f", 1: "\u064e", 2: "\u0650"}          # ُ َ ِ   NOM / ACC / GEN


def repair_divine_name(surface: str | None, token: str | None, case: int | None) -> str | None:
    """اللَّه — the divine name: the DEFINITE ARTICLE FUSED with إِلَاه (a closed-class form).

    إِلَاه + الْ → الْإِلَاه → (hamzat al-qaṭʿ elided, the two lāms assimilated) → اللَّه. The
    renderer does the right thing on the LEXICAL STEM — root اله + `1ِ2َا3` gives أِلَاه — and what
    it cannot know is that this lexical item FUSES with the article, because the fusion is a property
    of the WORD, not of (root, wazān, case).

    THIS IS NEITHER A LOOKUP NOR A LEAK. The trigger is in the INPUT: the fused `...الله` is VISIBLE
    in the token's skeleton, which is what the model reads. The vowel on the shadda (always fatha)
    and the final vowel (the case) are supplied BY RULE — nothing is copied from the token's own
    diacritics — so the rule is INVARIANT to whether the text is vocalised, exactly like PRO_V/ENC_V,
    and any proclitic in front of it is re-vocalised from the same table (`وَاللَّهِ`, `بِاللَّهِ`
    come out right from unvocalised input).

    It fires ONLY when the stem the renderer produced IS the إِلَاه skeleton (four letters: alif or
    hamza, then ل ا ه), so a wrong render cannot be rewritten into a right answer. Measured on
    gold-300 (gold MorphPlan, resource OFF): 9 misses in this class, **8 fixed, 0 broken**. The
    ninth (`بِاَللَّهِ`) is the corpus's own anomalous spelling — a fatha after the article's alif,
    which no rule may invent — and it is REPORTED, not engineered away.
    """
    if not surface or not token or case not in CASE_VOWEL:
        return surface
    sk_tok = strip_diac(token)
    if not sk_tok.endswith("\u0627\u0644\u0644\u0647"):           # ...الله
        return surface
    sk_sur = strip_diac(surface)
    if not (len(sk_sur) == 4 and sk_sur[0] in ALIF and sk_sur[1:] == "\u0644\u0627\u0647"):
        return surface                                            # the stem is not إِلَاه
    n_pre = len(sk_tok) - 4
    pre = ""
    if n_pre:
        pre = PRO_V.get(strip_diac(_cut_at_letter(token, n_pre)))
        if pre is None:
            return surface                                        # unknown proclitic: refuse
    return pre + DIVINE_NAME + CASE_VOWEL[case]


def _letter_index(s: str, skel_pos: int) -> int:
    """Character index of the `skel_pos`-th base LETTER in `s` (its diacritics ride along)."""
    n = 0
    for i, ch in enumerate(s):
        if not DIAC.match(ch):
            if n == skel_pos:
                return i
            n += 1
    return -1


def _seat_script(a: str, b: str):
    """The ALL-SEAT edit script turning skeleton `a` into skeleton `b`, or None.

      SUB   a[i] ∈ {ا,و,ي} ∪ seats  ->  b[j] ∈ seats      (the folded radical re-seated)
      DEL   a[i] == bare ا sitting immediately beside a seat   (`إا` -> `إ`: the renderer emitted
            the seat AND the root's folded alif, doubling the radical)

    EVERY edit must be a hamza-seat repair; one edit touching a non-seat consonant makes the whole
    script illegal and the rule refuses. Returns [(index_in_a, new_letter_or_None)] or None.
    """
    if len(a) == len(b):
        diffs = [i for i in range(len(a)) if a[i] != b[i]]
        if diffs and all(a[i] in SEATISH and b[i] in SEATS for i in diffs):
            return [(i, b[i]) for i in diffs]
        return None
    if len(a) == len(b) + 1:
        for k in range(len(a)):
            if a[k] != "\u0627":                                  # the extra letter must be bare alif
                continue
            if not ((k and a[k - 1] in SEATS) or (k + 1 < len(a) and a[k + 1] in SEATS)):
                continue                                          # ... and must sit beside a seat
            rest = a[:k] + a[k + 1:]
            subs = []
            for j in range(len(b)):
                if rest[j] == b[j]:
                    continue
                if rest[j] in SEATISH and b[j] in SEATS:
                    subs.append((j if j < k else j + 1, b[j]))
                else:
                    subs = None
                    break
            if subs is not None:
                return [(k, None)] + subs
        return None
    return None


def project_hamza_from_input(surface: str | None, token: str | None) -> str | None:
    """Re-seat the hamza radical from the INPUT TOKEN — the root's folded ا cannot carry it (`§2co`).

    THE PREMISE. Root extraction normalizes hamza to bare alif (START-HERE §6: **93.9%** of gold/silver
    roots are bare-alef), so `ش.ي.ا` is really `ش.ي.ء` and `م.ر.ا` is `م.ر.ء`. A numeral template then
    substitutes a bare ا where a SEAT belongs, and `(root, wazān, case)` cannot recover it — the
    information was destroyed before the renderer ever saw the row.

    WHY THE SEAT IS STILL RECOVERABLE. In unvocalized running text a seat is a CONSONANT, not a
    diacritic: `بِشَيءٍ`, `الْمَرْءِ`, `مَسْأَلَة`, `يَأْتِي`, `لِلمُؤمِنِينَ` all WRITE their seat. So this
    reads the seat off `strip_diac(token)` — the same legal input the affix plane reads its letters from —
    and is therefore INVARIANT to input diacritics, with no oracle.

    THE GUARD. Candidates come from the metric's own `candidates()` (a legal affix split is the metric's
    definition, not this module's), and the script is accepted only when EVERY difference is seat-related.
    Marks are never touched: the seat's vowel is whatever the renderer already placed, which is what makes
    this a re-seating and not a re-rendering.
    """
    if not surface or not token:
        return surface
    a = strip_diac(surface)
    if not a:
        return surface
    for cand in candidates(token):
        ops = _seat_script(a, strip_diac(cand))
        if ops is None:
            continue
        out = surface
        for idx, new in sorted(ops, key=lambda t: -t[0]):        # right-to-left: indices stay valid
            j = _letter_index(out, idx)
            if j < 0:
                return surface
            out = out[:j] + (new or "") + out[j + 1:]
        return out
    return surface


def repair_manqus_indefinite(surface: str | None, pattern: str | None,
                            case: int | None, definiteness: int | None) -> str | None:
    """قَاضٍ / قَاضِيًا — the INDEFINITE manqūṣ noun (ناقص, R3 = و/ي after the pattern's kasra).

    In the definite and construct states the final ي simply stays (الْقَاضِي, قَاضِي الْمَدِينَةِ). In the
    INDEFINITE it behaves by case: **NOM and GEN drop the ي entirely** and the tanwīn kasr compensates
    (قَاضِي -> قَاضٍ, دَاعٍ), while **ACC keeps the ي and writes the tanwīn WITH ITS ALIF** (قَاضِيًا,
    مُقْتَضِيًا) — the accusative alif IS written here, because this ي is a radical, not a mater
    (`_tanwin_alif`'s exclusion list exists for maters and is right to refuse those).

    THIS RULE CONSUMES BOTH THE CASE AND THE DEFINITENESS INPUT. As shipped it wins **+1** on gold-300
    (`B129`, مُقْتَضِيًا, whose `t_case` is ACC); its CEILING with a perfect case head adds **+9** more,
    and those nine are NOT manqūṣ at all — they are the case-vowel family (طَلْحَةَ, سَلَمَةَ, عُبَادَةَ,
    ثَلَاثَةَ, وَقَالَ, تَخَافُ) where the row's own case produces the wrong vowel. So the honest reading is
    inverted from the obvious one: the manqūṣ rule pays +1, and the *case head* is the lever that pays — 
    see `G:/aide-harness/ceiling_manqus_case.py`.

    Note `apply_case` already elides a vowel after a final weak letter (istiṯqāl), so this rule keys on the
    `ـِي` SHAPE rather than on a mark the case layer may never have placed.
    """
    if not surface or not pattern or definiteness != 1:
        return surface
    i = pattern.rfind("3")
    if i <= 0 or pattern[i - 1] != KASRA:
        return surface
    s = surface
    while s and (s[-1] in TAN or s[-1] in (FATHA, DAMMA, KASRA)):
        s = s[:-1]                             # `apply_case` may already have elided the ending
    if len(s) < 3 or not s.endswith("\u0650\u064a"):           # …ـِي (the ending is already stripped)
        return surface
    if case in (0, 2):
        return s[:-2] + "\u064d"                  # ٍ — the ي AND its kasra drop; the tanwīn compensates
    if case == 1:
        return s + TANWIN_ALIF                    # ًا — ACC keeps the ي and writes the alif
    return surface


def align_weak_r3(surface: str | None, pattern: str | None) -> str | None:
    """A final weak R3 is written as the PATTERN writes it: `…ِ3` → ي, `…َ3` → ى.

    THE RENDERER'S BLANKET RULE IS WRONG ON THE fāʿil FAMILY. It writes a final weak radical as an
    alif maqṣūra in every case, but the human writes **ي** whenever the vowel the pattern carries
    immediately before its R3 digit is a KASRA — قَاضِي, الثَّانِي, يَنْفِي, وَرُوِيَ, مُقْتَضِي — and
    **ى** when it is a FATHA — مُسْتَثْنَى, تَعَالَى, أَبْزَى. That the deciding mark is the PATTERN's
    own (a wazān is an input, the model predicts it) is what makes this a rule rather than a lookup:
    the measured correlation on gold-300's nāqiṣ population is exact, both directions, 0 exceptions.
    """
    if not surface or not pattern:
        return surface
    i = pattern.rfind("3")
    if i <= 0:
        return surface
    v = pattern[i - 1]
    if v == KASRA and surface.endswith("\u0649"):
        return surface[:-1] + "\u064a"           # ى -> ي  (الثَّانِي, يَنْفِي)
    if v == FATHA and surface.endswith("\u064a"):
        return surface[:-1] + "\u0649"           # ي -> ى  (مُسْتَثْنَى, تَعَالَى)
    return surface


def apply_diacritic_repairs(surface: str | None, token: str, case: int | None,
                            trace: list[dict] | None = None) -> str | None:
    """The measured repair rules, **in the order they were measured**.

    The order is part of the measurement, not an implementation detail: the joint figure for the first four
    (583) was obtained applying them in exactly this sequence, so changing the sequence invalidates the number
    that justified the layer and `tools/diacritic_split.py --check` will say so. `repair_initial_hamza_seat`
    was added last (2026-10-12, §2bj) on a disjoint row set — it takes the shipped pipeline 583 → 592 — and it
    is measured and pinned separately, so the four-rule figure stays comparable to what §2be predicted.

    It rewrites no letters and abstains on an empty surface; every rule is a function of the assembled
    string plus (at most) the token's proclitic and the case head.

    `repair_divine_name` was added LAST (§2cm, 2026-10-14). It is a CLOSED-CLASS form, so it is
    disjoint from the rules above by construction — it fires only where the renderer produced the
    إِلَاه skeleton — and the four-rule figure stays comparable to what §2be predicted.
    """
    if not surface:
        return surface

    def _step(rule_id, fn, *args):
        nonlocal out
        prev = out
        out = fn(out, *args)
        if trace is not None:
            trace.append({
                "stage": "diacritic_repairs",
                "rule_id": rule_id,
                "before": prev,
                "after": out,
                "changed": prev != out,
            })

    out = surface
    _step("repair_sun_letter_shadda", repair_sun_letter_shadda, token)
    _step("repair_hamza_fatha", repair_hamza_fatha)
    _step("repair_long_vowel_sukun", repair_long_vowel_sukun)
    _step("repair_dual_nominative", repair_dual_nominative, case)
    _step("repair_initial_hamza_seat", repair_initial_hamza_seat, token)
    _step("repair_divine_name", repair_divine_name, token, case)
    return out


def _affix_frame(token: str, sk_stem: str):
    """(prefix_parts, stem, suffix) CHARACTER slices of `token` whose stem skeleton is `sk_stem`.

    WHY A SPLICE AND NOT AN APPEND. The affix characters are read OFF THE TOKEN — the model's own
    input — so this layer cannot invent an affix the text does not carry. It re-uses the token's
    orthography for the proclitic/enclitic and puts the RENDERER's stem between them; the stem is
    the only thing it contributes. The frame is accepted only when the skeletons line up exactly.

    LONGEST PROCLITIC FIRST, so `وال` beats `و` and `بال` beats `ب` — the same preference the
    metric's own `candidates()` takes, because the metric decides what counts as an affix and the
    compiler must not disagree with it. `None` means "not an affix case", and the caller then
    returns the stem UNCHANGED.

    TWO PROCLITICS, SINCE 2026-10-14 (§2cm). `candidates()` strips up to TWO proclitics, so a
    compiler that strips one can fail to read a token the metric can (`وَسَتَعْرِفُ`). The depth-2
    search is consulted ONLY WHEN THE SINGLE-PROCLITIC SEARCH FINDS NOTHING — that ordering is the
    entire safety argument, so every row the earlier layer already handled is returned bit for bit
    identically — AND ONLY FOR THE CHAINS IN `PRO2`. The whitelist is not decoration: the first
    version accepted any pair and spliced `فَلِ` into `فَلْيُدْمِنْ`, where the `ل` is the jussive lām,
    not a proclitic — measured on the ruler as 4 broken rows against 0 fixed. Gate the chain, not the
    guess.
    """
    pros = sorted([*PRO, ""], key=len, reverse=True)
    encs = [*sorted(ENC, key=len, reverse=True), ""]

    def match(parts, rest):
        """Accept a proclitic chain's `parts` iff the remainder is `sk_stem` + a legal enclitic."""
        sk = strip_diac(rest)
        if len(sk) < len(sk_stem):
            return None
        for enc in encs:
            if enc and not sk.endswith(enc):
                continue
            core = sk[:len(sk) - len(enc)] if enc else sk
            if core != sk_stem:
                continue
            j = len(_cut_at_letter(rest, len(core)))
            return parts, rest[:j], rest[j:]
        return None

    sk_tok = strip_diac(token)
    for pre in pros:                       # depth 1 — the shipped search, unchanged
        pre_sk = strip_diac(pre)
        if pre_sk and not sk_tok.startswith(pre_sk):
            continue
        i = len(_cut_at_letter(token, len(pre_sk)))
        got = match([pre] if pre else [], token[i:])
        if got is not None:
            return got
    for p1, p2 in PRO2:                    # depth 2 — only when depth 1 found nothing
        k1, k2 = strip_diac(p1), strip_diac(p2)
        if not sk_tok.startswith(k1) or len(sk_tok) <= len(k1) + 1:
            continue
        r1 = token[len(_cut_at_letter(token, len(k1))):]
        sk1 = strip_diac(r1)
        if not sk1.startswith(k2) or len(sk1) <= len(k2) + 1:
            continue
        got = match([p1, p2], r1[len(_cut_at_letter(r1, len(k2))):])
        if got is not None:
            return got
    return None


def _tanwin_alif(out: str, token: str) -> bool:
    """True when the token carries an ACCUSATIVE TANWĪN ALIF beyond the composed surface.

    `جَمِيعًا` : the ة-less accusative indefinite writes the nunation as a final alif, and that alif
    is VISIBLE in the skeleton (`جميعا` = `جميع` + `ا`) — so unlike the bare tanwīn marks it is
    derivable from the input, with no oracle and no morphology. Guarded on the letters after which
    the accusative alif is NOT written, so the rule cannot fire on a defective ending.
    """
    sk_out, sk_tok = strip_diac(out), strip_diac(token)
    if not sk_tok.endswith("\u0627") or len(sk_tok) != len(sk_out) + 1:
        return False
    if sk_tok[:-1] != sk_out:
        return False
    return sk_out[-1:] not in ("\u0627", "\u0648", "\u064a", "\u0649", "\u0629", "\u0621")


def attach_affix_plane(surface: str | None, token: str | None,
                       case: int | None = None, tanwin: bool = False) -> str | None:
    """Splice the token's affix frame around a rendered stem — THE AFFIX PLANE (`EVIDENCE_LOG` §2cd).

    MEASURED BEFORE SHIPPING (resource OFF, 100% gold triple, `G:/aide-harness/rule_only_compiler_probe.py`):
    the resource-free compiler was **15.8% token-exact but 60.8% stem-level** on the 300 human gold,
    and the entire gap was the affix plane — **146 of 278 rows (52.5%)** failed because the gold token
    carries a proclitic (و ف ب ك ل ال بِال …) or an enclitic (ه ها هم كم نا …) that `(root, wazān, case)`
    does NOT encode. `(root, wazān, case)` is therefore not a complete generative spec of the TOKEN,
    and no compiler — rule or neural — could exceed ~60% stem / ~16% token without this layer.

    WHY THIS IS NOT A LEAK. The token is an INPUT (§2bc): the model READS it, and its affix split is
    derivable at inference exactly as it is here. Only the affix CHARACTERS come from it; the stem
    comes from the renderer, and the frame is accepted only when
    `skel(token) == pro + skel(stem) + enc` exactly. So it cannot fabricate an affix, and a token
    with no such frame is returned UNCHANGED.

    WHERE IT SITS — LAST, deliberately. It runs after the clitic plane (ة -> ت) and after the
    repairs, both of which therefore still receive the BARE STEM they received before this layer
    existed. That is what makes the change additive: no measured layer changes its input.
    """
    if not surface or not token:
        return surface
    sk_stem = strip_diac(surface)
    if not sk_stem:
        return surface
    frame = _affix_frame(token, sk_stem)
    if frame is None:
        out = surface
    else:
        pre_parts, _stem, suf = frame
        # THE AFFIXES ARE RE-VOCALISED BY RULE, NOT COPIED. Only the affix LETTERS are read from
        # the token, so this layer is INVARIANT to whether the input text is diacritized — which is
        # the real task condition (the model reads undiacritized text). See PRO_V / ENC_V.
        suf_l = strip_diac(suf)
        suf_v = ENC_V.get(suf_l, suf_l)
        if surface.endswith(KASRA) and suf_l in ENC_V_KASRA:
            suf_v = ENC_V_KASRA[suf_l]               # هِ after a kasra, هُ otherwise
        # THE PREFIX IS VOCALISED AS A WHOLE FIRST (§2cm). A two-clitic prefix can be a FUSED form
        # whose vowel is not the concatenation of its parts — لِ + الْ → `لل` — so the joined
        # skeleton is looked up before falling back to per-part vocalisation.
        pre_sk = "".join(strip_diac(p) for p in pre_parts)
        pre = PRO_V.get(pre_sk) or "".join(PRO_V.get(strip_diac(p), strip_diac(p))
                                           for p in pre_parts)
        # LĀM ASSIMILATION (§2cn). Every article-bearing proclitic is stored with a sukūn on its lām
        # (الْ والْ بِالْ كَالْ لِلْ), but that lām ASSIMILATES before a SUN letter — the human writes
        # الشَّمْسِ and الثَّانِي, never *الْشَّمْسِ. The deciding letter is the STEM's first, which the
        # renderer produced a few lines up, so this is a rule and not a copy of the token. Measuring
        # this found the defect: `الْ` was emitted unconditionally, so the al- family was wrong on
        # EVERY sun-initial noun. It also subsumes لِ + الْ (`لِلْ` -> `لِل` before a sun letter).
        if pre.endswith("\u0644\u0652") and strip_diac(surface)[:1] in SUN_LETTERS:
            pre = pre[:-1]          # drop the SUKŪN only, never the lam: الْ -> ال, and لِلْ -> لِل
        out = pre + surface + suf_v
    if case == 1 and _tanwin_alif(out, token):       # جَمِيعًا — visible in the skeleton
        if out.endswith(FATHA) or out.endswith("\u064b"):  # the tanwīn REPLACES the case fatha,
            out = out[:-1]                           # it does not stack on top of it
        out += TANWIN_ALIF
    elif tanwin and case == 1 and not out.endswith(TANWIN_ALIF):
        sk_tok = strip_diac(token)
        if sk_tok.endswith("\u0627") and not out.endswith("\u0627") and not out.endswith("\u0629"):
            if out.endswith("\u064b"):
                out = out[:-1] + TANWIN_ALIF
    return out


def apply_spelling_resource(surface: str | None, token: str | None,
                            case: int | None = None, resource: bool = True) -> str | None:
    """Consult the corpus spelling resource — the missing INPUT, measured before it was written.

    ON by default at the zero-loss setting (`SPELLING_MIN_SHARE=0.95`); set `ARABIC_SPELLING_RESOURCE=0` or
    pass `resource=False` to switch it off. Every instrument that measures the SURFACE pipeline (the repair layer,
    the diacritic split, the tanwin probe) sets that variable explicitly, so their numbers keep their old meaning —
    the switch exists for ATTRIBUTION, the same reason `repairs` exists above.

    WHAT IT DOES. `spelling_resource.consult(token)` keys the token's SKELETON — a legal input — into an
    index of spellings attested in 66.2M tokens of tashkeela book text, and returns the corpus's spelling
    only when its share of the attestations clears `SPELLING_MIN_SHARE` (default 0.95: the measured
    ZERO-LOSS setting). The skeleton is erased of diacritics by construction, so this function cannot see
    the gold token's marks even in principle.

    MEASURED (frozen ruler, 973 rows, shipped baseline 592; harness `sweep_selector.py`):
        SPELLING_MIN_SHARE=0.95, confidence rule only   695/973 = 71.4%   fixed 103  broken  0   net +103
        SPELLING_MIN_SHARE=0.55, confidence rule only   756/973 = 77.7%   fixed 224  broken 60   net +164
        CASE-AWARE selector (consult_case, §2bo)        827/973 = 85.0%   fixed 213  broken 81   net +132
    The shipped default is the case-aware selector with the confidence rule behind it. Its counterexamples
    are named: `case=ABSTAIN` rows (no constraint, so it degrades to frequency), the enclitic plane (the
    case sits on the enclitic), and tanwīn-versus-construct — the definiteness input §7 still lacks.
    `0.95` is the strictly dominant setting (zero counterexamples anywhere on the ruler). `/sweep_selector.py`
    records the whole threshold curve, and `/diagnose_zero_loss.py` shows the 103 fixed rows sit on skeletons
    attested a median of 114 times — settled orthography, not retrieval.
    """
    if not resource or not token or os.environ.get("ARABIC_SPELLING_RESOURCE", "1") == "0":
        return surface
    try:
        from spelling_resource import consult, consult_case
        # CASE-AWARE FIRST (§2bo, measured 827/973 = 85.0%): the most frequent attested spelling whose
        # ending carries the case head. Then the confidence rule, then the shipped surface.
        form, _share, _total = consult_case(token, case)
        if not form:
            form, _share, _total = consult(token)
    except Exception:                                            # noqa: BLE001
        return surface                                           # never break the pipeline over an optional input
    return form or surface


def score_final_surface(pairs) -> dict:
    """THE SHARED METRIC. `pairs` = iterable of (gold_token, predicted_surface|None).

    Both arms are scored by THIS function on the SAME rows, which is the A3 fix: one
    metric, one object, both arms. Returns coverage and accuracy as SEPARATE numbers.

    A pair MAY carry a third element: the renderer's abstention reason. It exists because the
    reason was being thrown away — `eval_harness` built its pairs as `render_triple(...)[0]`, so
    the 296/300 abstentions on the human gold arrived as ONE undifferentiated bucket with no
    diagnosis attached. A rate without a reason is not a finding, so the reason is bucketed and
    also returned as `abstain_reasons`.
    """
    n = abstain = stem_ok = tok_ex = skel_ok = 0
    buckets = collections.Counter()
    abstain_reasons = collections.Counter()
    for row in pairs:
        gold, pred = row[0], row[1]
        if not gold:
            continue
        n += 1
        if pred is None:
            abstain += 1
            why = row[2] if len(row) > 2 else None
            if why:
                abstain_reasons[why] += 1
                buckets[f"abstain:{why}"] += 1
            else:
                buckets["abstain"] += 1
            continue
        if stem_match(gold, pred):
            stem_ok += 1
        else:
            buckets[classify_defect(gold, pred)] += 1
        if nfc(pred) == nfc(gold):
            tok_ex += 1
        if strip_diac(pred) == strip_diac(gold):
            skel_ok += 1
    nz = max(n, 1)
    cov = n - abstain
    return {
        "n": n,
        "covered": cov,
        "coverage": cov / nz,
        "abstain": abstain,
        "stem_correct": stem_ok,
        # CONDITIONAL accuracy: of the rows the renderer actually rendered.
        "stem_accuracy_of_covered": stem_ok / max(cov, 1),
        # YIELD: over ALL rows, so an abstention COUNTS AS A MISS. Named separately so
        # the two can never be quoted as each other — SPEC-REV6 §5.1 item 1.
        "stem_yield": stem_ok / nz,
        "token_exact": tok_ex,
        "token_exact_yield": tok_ex / nz,
        "skeleton": skel_ok,
        "skeleton_yield": skel_ok / nz,
        "defect_buckets": dict(buckets.most_common()),
        # WHY it abstained, so "abstain" is never again a deadline-grade number with no cause.
        "abstain_reasons": dict(abstain_reasons.most_common()),
    }


def selftest() -> int:
    """Known answers for the metric's OWN semantics — including the two bugs this
    module exists to avoid."""
    bad = []

    def chk(cond, msg):
        if not cond:
            bad.append(msg)
        print(f"  [{'OK ' if cond else 'FAIL'}] {msg}")

    print("=" * 84)
    print("FINAL-SURFACE METRIC (STEM-LEVEL) — known-answer self-test")
    print("=" * 84)
    print("\n  the metric is SYMMETRIC: it must not favour either arm")
    chk(stem_match("كَفَوْقِ", "فَوْقِ"), "stem arm matches a token with a proclitic")
    chk(stem_match("كَفَوْقِ", "كَفَوْقِ"), "token arm matches the token unchanged")
    chk(stem_match("أَخْبَرَهُ", "أَخْبَرَ"),
        "enclitic set aside — cut by LETTER (the token ends in a damma)")
    chk(not stem_match("مَعْرِفَتِهَا", "مَعْرِفَه"), "wrong consonant still fails")
    chk(not stem_match("رَسُولِ", "قَوْلِ"), "unrelated stem fails")
    chk(classify_defect("مَعْرِفَتِهَا", "مَعْرِفَةِ") == "ta_marbuta",
        "ta-marbuta under a pronoun is its OWN rule, not a clitic-plane match")

    print("\n  the greedy-strip bug must NOT come back (ف is also a root radical)")
    chk(stem_match("الْفَضْلَ", "فَضْلَ"), "ال stripped, the ف of the STEM kept")
    chk(stem_match("فَوْقِ", "فَوْقِ"), "a stem-initial ف is not eaten")
    chk(classify_defect("الْعَقْلِ", "عَقْلِ") == "clitic",
        "clitic plane classified as harness, not morphology")

    print("\n  coverage is separate from accuracy — an abstention is NOT a wrong answer")
    s = score_final_surface([("دَرْسَ", None), ("دَرْسَ", "دَرْسَ")])
    chk(s["coverage"] == 0.5 and s["stem_correct"] == 1 and s["abstain"] == 1,
        "abstention counted as coverage loss, not as a miss")

    print("\n  THE AFFIX PLANE (§2cd) — splices the token's affixes, and refuses to invent one")
    chk(attach_affix_plane("أَبُو", "وَأَبُو") == "وَأَبُو", "proclitic و attached")
    chk(attach_affix_plane("كَسْبِ", "لِكَسْبِ") == "لِكَسْبِ", "proclitic لِ attached")
    chk(attach_affix_plane("قَرَائِنِ", "بِالْقَرَائِنِ") == "بِالْقَرَائِنِ",
        "LONGEST proclitic wins — بِال, not بِ + الْ…")
    chk(attach_affix_plane("أَخْبَرَ", "أَخْبَرَهُ") == "أَخْبَرَهُ", "enclitic هُ attached")
    chk(attach_affix_plane("خِدْمَتِ", "خِدْمَتِهُ") == "خِدْمَتِهِ",
        "clitic plane (ة -> ت) runs BEFORE the splice, and the enclitic HARMONISES to the "
        "stem's kasra (هِ, not هُ) — the expectation changed when harmony shipped")
    chk(attach_affix_plane("كِتَابُ", "كِتَابُهُ") == "كِتَابُهُ",
        "harmony goes the other way after a damma: هُ, not هِ")
    chk(attach_affix_plane("جَمِيعَ", "جَمِيعًا", 1) == "جَمِيعًا",
        "ACCUSATIVE TANWĪN ALIF — visible in the skeleton, so derivable with no oracle")
    chk(attach_affix_plane("رَجُل", "رَجُلًا", 0) == "رَجُل",
        "the accusative alif is NOT attached when the case is not accusative")
    chk(attach_affix_plane("دَرْس", "مَدْرَسَة") == "دَرْس",
        "no legal frame -> UNCHANGED (a token whose skeleton is not pro+stem+enc)")
    chk(attach_affix_plane("عِلْم", "الْجَاهِلِيَّة") == "عِلْم",
        "cannot fabricate: ال matches but the stem does not, so nothing is attached")
    chk(attach_affix_plane("دَرْس", None) == "دَرْس" and attach_affix_plane(None, "دَرْس") is None,
        "missing either side is a no-op")

    # --- §2cm: three measured rules, each checked WITH its refusal case ------------------------------
    # (#1) hollow contraction at the stem/tail seam: the long vowel elides before a sukūn tail.
    chk(render_triple("قول", "1ُ2ْ3", None, engine="v3", stem_tail="ْتُ")[0] == "قُلْتُ",
        "hollow seam: قُوْل + ْتُ -> قُلْتُ (ḥadhf)")
    chk(render_triple("نصر", "1َ2َ3", None, engine="v3", stem_tail="ْتُ")[0] == "نَصَرْتُ",
        "a SOUND stem is not elided: نَصَر + ْتُ -> نَصَرْتُ")
    # (#2) the divine name: the article fused with إِلَاه. The trigger is the token's SKELETON and the
    # vowels are supplied by rule, so an UNVOCALISED token must give the same fully-vocalised answer.
    # NOTE THE EXPECTED STRINGS ARE \u-ESCAPED ON PURPOSE: `اللَّه` as typed by hand comes out
    # FATHA-THEN-SHADDA (0x64e,0x651), while the corpus and this module write SHADDA-THEN-FATHA
    # (0x651,0x64e). NFC never reorders marks, so the two are different strings — the mark-ordering
    # trap. Writing the escapes removes the ambiguity from the test itself.
    _LN = "\u0627\u0644\u0644\u0651\u064e\u0647"          # اللَّه (shadda, then fatha)
    chk(repair_divine_name("\u0623\u0650\u0644\u064e\u0627\u0647\u0650", _LN + "\u0650", 2) == _LN + "\u0650",
        "divine name: أِلَاهِ -> اللَّهِ")
    chk(repair_divine_name("\u0623\u0650\u0644\u064e\u0627\u0647\u0650", "\u0627\u0644\u0644\u0647\u064f", 0)
        == _LN + "\u064f",
        "divine name is INVARIANT: an unvocalised token yields the same vocalised form")
    chk(repair_divine_name("كِتَابِ", "اللَّهِ", 2) == "كِتَابِ",
        "a stem that is not إِلَاه is left alone")
    # (#3) two proclitics, and the fused لِ + الْ once more — with the stem's sun/moon letter deciding
    # whether the article's lām assimilates.
    chk(attach_affix_plane("تَعْرِفُ", "وَسَتَعْرِفُ") == "وَسَتَعْرِفُ",
        "TWO proclitics spliced: وَ + سَ")
    chk(attach_affix_plane("كَرَاهَةِ", "لِلْكَرَاهَةِ") == "لِلْكَرَاهَةِ",
        "لِ + الْ keeps its sukūn before a MOON letter")
    chk(attach_affix_plane("تَّاجِرِ", "لِلتَّاجِرِ") == "لِلتَّاجِرِ",
        "لِ + الْ assimilates before a SUN letter")
    chk(attach_affix_plane("يُدْمِنْ", "فَلْيُدْمِنْ") == "يُدْمِنْ",
        "ف + ل is NOT a legal chain (that ل is the jussive lām): refuse, attach nothing")

    # --- §2cn: the nāqiṣ families, each with its refusal case ---------------------------------------
    chk(attach_affix_plane("طَّحْنِ", "الطَّحْنِ") == "الطَّحْنِ",
        "lām ASSIMILATES before a sun letter: الطَّحْنِ, never *الْطَّحْنِ")
    chk(attach_affix_plane("قَلَمِ", "الْقَلَمِ") == "الْقَلَمِ",
        "lām KEEPS its sukūn before a moon letter")
    chk(align_weak_r3("يَنْفِى", "يَ1ْ2ِ3") == "يَنْفِي",
        "a final weak R3 is a ي when the PATTERN's vowel before slot 3 is a kasra")
    chk(align_weak_r3("مُسْتَثْنَي", "مُسْتَ1ْ2َ3") == "مُسْتَثْنَى",
        "... and an ى when it is a fatha")
    chk(align_weak_r3("كَتَبَ", "1َ2َ3") == "كَتَبَ", "a sound stem is untouched")
    chk(render_triple("علو", "تَ1َا2َ3", None, engine="v3", stem_tail="ى")[0] == "تَعَالَى",
        "the TAIL's weak letter replaces the stem's at the seam — never تَعَالَاى")
    chk(render_triple("قرا", "1ُ2ْ3", 2, engine="v3", token="الْقُرْآنِ",
                      stem_tail="َان")[0] == "الْقُرْآنِ",
        "two alifs at the seam merge into the madda: قُرْآن")

    # --- §2co: the hamza seat is a CONSONANT in the input, so it is readable there ---------------------
    chk(project_hamza_from_input("مَرْا", "الْمَرْءِ") == "مَرْء",
        "the root's folded ا is RE-SEATED from the token: الْمَرْءِ")
    chk(project_hamza_from_input("شَيْا", "بِشَيءٍ") == "شَيْء",
        "… and after a proclitic: بِشَيءٍ")
    chk(project_hamza_from_input("إاِمَام", "إمَامُ") == "إِمَام",
        "the doubled radical collapses: the renderer wrote the seat AND the folded alif (إا -> إ)")
    chk(project_hamza_from_input("كَتَبَ", "ذَهَبَ") == "كَتَبَ",
        "REFUSES when a difference touches a non-seat consonant — a wrong render is never rewritten")
    chk(project_hamza_from_input("مَرْا", None) == "مَرْا" and project_hamza_from_input(None, "x") is None,
        "missing either side is a no-op")

    # --- §2co: the manqūṣ indefinite, which keys on the SHAPE `…ـِي` (apply_case elides the vowel) ------
    chk(repair_manqus_indefinite("قَاضِي", "1َا2ِ3", 0, 1) == "قَاضٍ",
        "manqūṣ NOM indefinite: the ي drops and the tanwīn kasr compensates (قَاضٍ)")
    chk(repair_manqus_indefinite("مُقْتَضِي", "مُ1ْتَ2ِ3", 1, 1) == "مُقْتَضِيًا",
        "manqūṣ ACC indefinite KEEPS the ي and writes the alif (مُقْتَضِيًا)")
    chk(repair_manqus_indefinite("مُقْتَضِي", "مُ1ْتَ2ِ3", 1, None) == "مُقْتَضِي",
        "REFUSES without the definiteness input — this rule is oracle-bounded, not free")
    chk(repair_manqus_indefinite("مُقْتَضِي", "1َ2َ3", 1, 1) == "مُقْتَضِي",
        "REFUSES outside the fāʿil family: the pattern's own vowel before slot 3 must be a kasra")

    print("\n" + "=" * 84)
    if bad:
        print(f"FAILED ({len(bad)}):")
        for b in bad:
            print("  -", b)
        return 1
    print("ALL PASS — symmetric, verification-driven decomposition, coverage separate")
    print("=" * 84)
    return 0


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    print(__doc__)
