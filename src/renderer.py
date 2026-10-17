"""renderer.py — R1: (root, wazān pattern, case) -> vocalized surface.

THE CONTRACT
    Step 3 of the architecture: the model emits grammar, and a DETERMINISTIC renderer
    turns it into the written form. Nothing here is learned except the optional
    memorised table.

WHY IT SUBSTITUTES IN PLACE
    `fix_renderer.py` diagnosed the defect: round-tripping the pattern through ف/ع/ل
    and substituting those three ARABIC LETTERS back to radicals destroys any affix
    that contains them — most obviously the definite article. `ال1ا2ِ3ِ` became
    `ارصادِرِ` because the `ل` of `ال` was overwritten by c3. ف/ع/ل are a HUMAN display
    convention; as internal slot markers they are unsafe. So the digits are replaced
    in the raw pattern and every other character is kept verbatim.

    `ال1ا2ِ3ِ` + ص.د.ر  ->  الصادِرِ     (exact)

COVERAGE IS NOT ACCURACY (SPEC §5.1 item 1)
    Two independent gates, and both are reported:
      · COVERAGE   — how often a route applies at all
      · ACCURACY   — exact-match rate, conditional on a route applying
    A renderer that applies to 6% of tokens at 99% accuracy is not better than one
    that applies to 60% at 90%; the paper needs the pair, never one alone.

THE THREE ROUTES, measured separately so the residual is visible (R1g)
    1. rule with CALIMA's root
    2. rule with the RECONCILED root   <- this is the pair §8.1 item 4 says was never
                                          re-measured after the root fix
    3. hybrid: memorised (root, pattern) table first, rule fallback
    The RESIDUAL (no route renders) is not a footnote — it is the oracle-renderer
    upper bound the paper needs.

LEAKAGE DISCIPLINE
    The table is built from the **train** split only and evaluated on **test**. The
    overlap between the two key sets is printed, because a large overlap is what makes
    a table look good and it has to be visible rather than assumed.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

from paths import EQTB_CSV, PADT_TEST, PADT_TRAIN, RAW, require

DIAC = re.compile(r"[\u064b-\u0652\u0670\u0640]")
DIG = re.compile(r"[1-4]")
# ARABIC LETTERS ONLY. The naive range [\u0621-\u064a] also contains U+0640 (tatweel,
# the placeholder EQTB/PADT use for "no value"), which let 'ـ' pass a "has Arabic"
# test, reach reconcile._key(), and raise on an empty key. U+063B-U+063F are
# unassigned, so the real letter ranges are 0621-063A and 0641-064A.
ARABIC = re.compile(r"[\u0621-\u063a\u0641-\u064a]")
SLOT = {"1": 0, "2": 1, "3": 2, "4": 3}
CASE_VOWEL = {0: "\u064f", 1: "\u064e", 2: "\u0650"}   # NOM damma, ACC fatha, GEN kasra
CASE_TANWIN = {0: "\u064c", 1: "\u064b", 2: "\u064d"}  # NOM dammatan, ACC fathatan, GEN kasratan
EQTB_CASE = {"NOM": 0, "ACC": 1, "GEN": 2}             # EQTB `nominal_case` values


def norm_root(root: str | None) -> str | None:
    """Radical sequence, dots/space removed. '#' means CALIMA did not assign a weak
    radical — that is NOT a root, so it is rejected here and reported as a reason."""
    if not root:
        return None
    r = "".join(c for c in root if c not in ". ")
    if not r or "#" in r or not ARABIC.match(r[0]):
        return None
    return r


def _map_digits(ds: set, rads: str) -> dict | None:
    """digit -> radical for a NON-CANONICAL digit set. None when it cannot be completed.

    TWO REGIMES, and the difference is measured rather than stylistic:

    · `#unique digits == #radicals` -> **RANK ORDER**. CAMeL numbers TEMPLATE SLOTS, not
      radicals. In أُسقُف the pattern أُ2ْ3ُ4ُ has digits {2,3,4} and the root سقف has three
      radicals: they fill slots 2,3,4 in order, and slot 1 is the template's own أ. Mapping
      by digit VALUE asks for a 4th radical that does not exist and abstains — that single
      row was the entire RULE GAP class (`CHALLENGES.md` §2x.9).

    · `#unique digits < #radicals` -> **VALUE ORDER**, because then a radical genuinely has
      no slot and is carried literally by the pattern. لِلأَوْ2ا3 with root وقف maps 2→ق,
      3→ف, and the و is already written in the pattern. Rank order here would assign 2→و
      and emit لِلأَوْوَاق. **Rank-order-everywhere is a regression, so it is not applied
      everywhere.**
    """
    uniq = sorted(ds, key=int)
    if len(uniq) == len(rads):
        return {d: rads[i] for i, d in enumerate(uniq)}
    m = {d: rads[int(d) - 1] for d in uniq if 0 <= int(d) - 1 < len(rads)}
    return m if len(m) == len(uniq) else None


def render_rule(root: str | None, pattern: str | None,
                case: int | None = None) -> tuple[str | None, str]:
    """Digit-in-place. Returns (surface, reason); surface is None when it abstains.
    
    Handles incomplete digit sets for weak radicals by mapping available digits
    to the correct radical positions based on the root structure.
    """
    if not pattern or pattern in ("None", "na", "_"):
        return None, "no_pattern"
    
    # Parse root to identify weak radicals
    if not root:
        return None, "no_root"
    root_parts = [c for c in root if c not in ". "]
    if not root_parts or "#" in root_parts:
        # Weak radical - need special handling
        return _render_weak_radical(root, pattern, case)
    
    rads = "".join(root_parts)
    if not ARABIC.match(rads[0]):
        return None, "no_root"
    
    # Fix: if root has no dots but has 2-7 Arabic characters, split into individual chars
    # This handles roots like 'سور' (should be 3 radicals) and 'ءامريك' (6 radicals) stored without separators
    if '.' not in root and 2 <= len(rads) <= 7:
        root_parts = list(rads)
        rads = "".join(root_parts)  # Update rads to reflect the split
    
    digits = DIG.findall(pattern)
    ds = set(digits)
    
    if ds not in ({"1", "2", "3"}, {"1", "2", "3", "4"}):
        # NON-CANONICAL digit set — one helper decides the mapping for all of these
        # (rank order when every radical has a slot, value order when one does not).
        if not (1 <= len(rads) <= 7):
            return None, "digit_set_incomplete"
        digit_map = _map_digits(ds, rads)
        if digit_map is None:
            return None, "digit_set_incomplete"
        out = "".join(digit_map.get(c, c) for c in pattern)
        if not ARABIC.search(out):
            return None, "no_arabic_output"
        return out, "ok"
    if len(digits) != len(ds):
        return None, "repeated_digit"
    if len(rads) != len(ds):
        return None, "root_len_mismatch"
    
    out = "".join(rads[SLOT[c]] if c in SLOT else c for c in pattern)
    if not ARABIC.search(out):
        return None, "no_arabic_output"
    return out, "ok"


def _render_weak_radical(root: str, pattern: str, case: int | None = None) -> tuple[str | None, str]:
    """Render a weak radical with incomplete or complete digit set.
    
    CALIMA returns roots with '#' for weak radicals (e.g. '#.ز.ر') but patterns
    may have all digit slots (e.g. '1َ2ا3ِيٌّ'). We need to:
    1. Identify which position is weak (the '#' slot)
    2. Infer the actual weak radical from context
    3. Map all digits, substituting the inferred radical for the weak position
    """
    # Parse root to identify weak radical positions
    root_parts = [c for c in root.split(".") if c]
    if not root_parts:
        return None, "no_root"
    
    # Identify which positions are weak (#)
    weak_positions = [i for i, r in enumerate(root_parts) if r == "#"]
    if not weak_positions:
        return None, "no_root"
    
    # Get available digits from pattern
    digits = DIG.findall(pattern)
    ds = set(digits)
    
    # Determine expected number of radicals
    num_radicals = len(root_parts)
    expected_digits = {"1", "2", "3"} if num_radicals == 3 else {"1", "2", "3", "4"}
    
    # Infer the weak radical from pattern context
    weak_radical = _infer_weak_radical(pattern, weak_positions, root_parts)
    
    # Create mapping: digit -> radical
    # For weak radicals, we need to figure out which digit corresponds to the weak position
    # Strategy: sort digits and root positions, map them in order
    sorted_digits = sorted(ds)
    
    # Build the full radical list with inferred weak radicals
    full_radicals = []
    weak_idx = 0
    for i, r in enumerate(root_parts):
        if r == "#":
            full_radicals.append(weak_radical)
        else:
            if not ARABIC.match(r):
                return None, "no_root"
            full_radicals.append(r)
    
    # Map digits to radicals
    # Each digit N corresponds to position N-1 in full_radicals
    digit_to_radical = {}
    for digit in sorted_digits:
        pos = int(digit) - 1  # '1' -> 0, '2' -> 1, '3' -> 2, '4' -> 3
        if pos < len(full_radicals):
            digit_to_radical[digit] = full_radicals[pos]
    
    # If we have fewer digits than radicals, we're missing some
    # This can happen when the weak radical position doesn't get a digit slot
    if len(sorted_digits) < len(full_radicals):
        # Try to fill in missing positions
        missing_digits = expected_digits - ds
        for missing_digit in missing_digits:
            # Find which position this digit should map to
            digit_num = int(missing_digit) - 1  # '1' -> 0, '2' -> 1, etc.
            if digit_num < len(full_radicals):
                digit_to_radical[missing_digit] = full_radicals[digit_num]
    
    # Render the pattern
    out = []
    for c in pattern:
        if c in digit_to_radical:
            out.append(digit_to_radical[c])
        else:
            out.append(c)
    
    result = "".join(out)
    if not ARABIC.search(result):
        return None, "no_arabic_output"
    
    return result, "ok"


def _infer_weak_radical(pattern: str, weak_positions: list[int], root_parts: list[str]) -> str:
    """Infer the weak radical from pattern context.
    
    Common patterns:
    - و (waw): often appears as و in pattern or causes vowel changes
    - ي (ya): often appears as ي in pattern or causes kasra
    - ا (alif): often appears as ا in pattern (madda)
    - ء (hamza): often appears as ء or causes hamzat al-wasl
    """
    # Check if pattern contains weak radical letters
    if "و" in pattern:
        return "و"
    if "ي" in pattern:
        return "ي"
    if "ا" in pattern or "آ" in pattern:
        return "ا"
    if "ء" in pattern or "أ" in pattern or "إ" in pattern:
        return "ء"
    
    # Default to و (most common weak radical)
    return "و"


INDECLINABLE_STEM_TAILS = {
    "\u0652\u062a\u064f",      # ْتُ
    "\u064e\u062a\u0652",      # َتْ
    "\u064f\u0648\u0627",      # ُوا
    "\u0652\u0646\u064e\u0627",  # ْنَا
    "\u0652\u062a\u064e",      # ْتَ
    "\u0652\u062a\u064f\u0645\u0652", # ْتُمْ
    "\u0652\u062a\u064f\u0646\u0651", # ْتُنَّ
    "\u064e\u062a\u064e\u0627",       # َتَا
}


def apply_case(surface: str, case: int | None, tanwin: bool = False,
               definiteness: int | str | None = None, stem_tail: str | None = None,
               trace: list[dict] | None = None) -> str:
    """Append the case vowel (or nunation tanwin) when the rendered form has no final short vowel.

    Kept SEPARATE from render_rule and measured separately, because the case vowel is
    Head 5's business and folding it in would re-entangle Head 3 with Head 5 — the
    exact defect REV6 fixed in the label (SPEC §3.2).

    `tanwin` — NUNATION, CONDITIONED ON THE DEFINITENESS INPUT. When true this emits ٌ/ً/ٍ instead
    of the bare short vowel. It is NOT derivable from (root, wazān, case) — indefiniteness is
    absent from the triple, which is why the caller must supply it (the `definiteness` head).

    Gated against overwriting endings when:
    - `definiteness` is 3 (INVARIABLE / OTHER)
    - `stem_tail` already carries a fixed indeclinable/verbal suffix (e.g. ْتُ, َتْ, ُوا, ْنَا)
    """
    if case is None or not surface:
        return surface
    if definiteness in (3, "OTHER", "INVARIABLE"):
        return surface
    if stem_tail and (stem_tail in INDECLINABLE_STEM_TAILS or any(stem_tail.endswith(s) for s in INDECLINABLE_STEM_TAILS)):
        return surface
    if surface[-1] in "ًٌٍَُِْ":          # already carries a final short vowel
        return surface
    if surface[-1] in "\u0627\u0648\u064a\u0649":   # alif/waw/ya: no short vowel written
        return surface
    res = surface + (CASE_TANWIN.get(case, "") if tanwin else CASE_VOWEL.get(case, ""))
    if trace is not None:
        trace.append({
            "stage": "case",
            "rule_id": "apply_case",
            "before": surface,
            "after": res,
            "changed": surface != res,
        })
    return res



# --------------------------------------------------------------- the table route
def build_table(paths, limit: int | None = None) -> tuple[dict, collections.Counter]:
    """(root, pattern) -> surface, from GOLD PADT. TRAIN SPLIT ONLY.

    Uses CALIMA's pattern (the thing the model will actually predict) but the GOLD
    root and GOLD surface, so the table memorises rendering decisions, not analysis.
    """
    from camel_tools.disambig.mle import MLEDisambiguator
    mle = MLEDisambiguator.pretrained("calima-msa-r13")
    rows, stats = [], collections.Counter()
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("#") or not line.strip():
                    continue
                c = line.rstrip("\n").split("\t")
                if len(c) < 10 or "-" in c[0] or "." in c[0]:
                    continue
                m = re.search(r"(?:^|\|)Root=([^|]+)", c[9])
                if not m or not ARABIC.search(c[1]):
                    continue
                rows.append((c[1], m.group(1).strip()))
                if limit and len(rows) >= limit:
                    break
            if limit and len(rows) >= limit:
                break
    surfaces = [s for s, _ in rows]
    ana = []
    B = 500
    for i in range(0, len(surfaces), B):
        for d in mle.disambiguate(surfaces[i:i + B]):
            ana.append(d.analyses[0].analysis if (d and d.analyses) else None)
    table = {}
    for (surf, gold_root), a in zip(rows, ana):
        if not a:
            continue
        pat = a.get("pattern")
        root = norm_root(gold_root if ARABIC.search(gold_root)
                         else __import__("reconcile").padt_to_arabic(gold_root))
        if not pat or not root:
            continue
        table.setdefault((root, pat), collections.Counter())[surf] += 1
    final = {k: v.most_common(1)[0][0] for k, v in table.items()}
    stats["keys"] = len(final)
    stats["rows"] = len(rows)
    return final, stats


FUNCTION_TAGS = {"ADP", "CCONJ", "PRON", "DET", "SCONJ", "PART"}
IDENTITY_TAGS = {"PUNCT", "SYM"}


def read_padt_tokens(path, limit: int | None = None, include_punct: bool = False):
    """Read PADT tokens. ONE reader — earlier duplicate readers drifted (see §2x.6).

    `limit` counts **non-punctuation** tokens only, and `include_punct=False` is the shipped
    default: the 4,000-Arabic-token denominator is FROZEN. Every recorded table, log and
    commit (0e53880, ae31cf4, 150374c) depends on it, so punctuation is opt-in and a
    punct-inclusive run writes to its OWN report file rather than overwriting the baseline.
    """
    out = []
    kept = 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#") or not line.strip():
                continue
            c = line.rstrip("\n").split("\t")
            if len(c) < 10 or "-" in c[0] or "." in c[0]:
                continue
            if not ARABIC.search(c[1]):
                if not (include_punct and c[3] in IDENTITY_TAGS):
                    continue
            m = re.search(r"(?:^|\|)Root=([^|]+)", c[9])
            cm = re.search(r"(?:^|\|)Case=([^|]+)", c[5])
            out.append({"form": c[1], "lemma": c[2], "upos": c[3],
                        "gold_root": m.group(1).strip() if m else None,
                        "case": {"nom": 0, "acc": 1, "gen": 2}.get(
                            (cm.group(1).strip().lower() if cm else ""))})
            if c[3] not in IDENTITY_TAGS:
                kept += 1
                if limit and kept >= limit:
                    break
    return out


def build_closed_class_surfaces(path) -> tuple[set, collections.Counter]:
    """Bare surfaces of closed-class TRAIN tokens, for the bypass route (route 4).

    Keyed on the SURFACE, never the lemma: PADT lemmatises every pronoun to هُوَ, so a
    lemma-keyed table would render هِيَ/هُمْ as هُوَ (`docs/CLOSED-CLASS-INVENTORY.md` §4.2).
    Built from TRAIN only — the §2x.1 discipline, not re-broken for a new component.
    """
    surf, per = set(), collections.Counter()
    for t in read_padt_tokens(path):
        if t["upos"] in FUNCTION_TAGS:
            surf.add(t["form"])
            per[t["upos"]] += 1
    return surf, per


def hybrid_render(root, pat, case, table) -> tuple[str | None, str, str]:
    """THE hybrid decision, in ONE place. Returns (surface_or_None, branch, why).

    Both the measurement (`measure`) and the failure audit (`src/audit_arity_failures.py`)
    call this. They used to each carry their own copy of the same table-then-rule logic,
    and the copies drifted: the same question ("content words that have a usable gold root
    and still do not render") came out as 13 and as 18. A duplicated decision procedure is
    a duplicated metric, and this repo has already been burned once by a metric living in
    two places.

    branch is '3a_hybrid_table' when the memorised (root, pattern) -> surface table fired
    and '3b_hybrid_rule' when the rule did. The table branch returns PADT's FORM, which is
    98.7% undiacritized, so a CALIMA-`diac` comparison is NOT valid for it — that is why
    the branches are counted apart rather than merged into one `3_hybrid` row.
    """
    if pat:
        key = (norm_root(root) or "", pat)
        if key in table:
            return table[key], "3a_hybrid_table", "table"
    got, why = render_rule(root, pat, case)
    if got is not None:
        return got, "3b_hybrid_rule", why
    return None, "3_hybrid", why


def measure(limit: int = 4000, table_limit: int = 14000,
            include_punct: bool = False) -> int:
    import eval_harness as EH
    from camel_tools.disambig.mle import MLEDisambiguator
    from reconcile import RootDictionary, reconcile
    from build_training_jsonl import build_silver_root_dict

    print("=" * 84)
    print("R1 — the renderer, measured with the SHARED final-surface metric (A3)")
    print("=" * 84)
    print("coverage and accuracy are reported separately and never merged (§5.1 item 1)\n")

    test = read_padt_tokens(require(PADT_TEST), limit, include_punct=include_punct)
    n_punct = sum(1 for t in test if t["upos"] in IDENTITY_TAGS)
    print(f"test tokens            : {len(test):,}  (PADT test"
          + (f" + {n_punct:,} PUNCT/SYM)" if n_punct else ")"))
    if include_punct:
        print(f"                          --include-punct: `limit` still counted ARABIC tokens")
        print(f"                          ({len(test)-n_punct:,}), so the 4,000 baseline is NOT")
        print(f"                          perturbed; this run writes renderer_report_punct.json")
    print("                          the table AND the reconciler dictionary are built from")
    print("                          TRAIN + the arramooz lexicon only — nothing derived from")
    print("                          PADT test is read (SPEC-REV6 §3.1).")

    table, tstats = build_table([require(PADT_TRAIN)], table_limit)
    print(f"table built from TRAIN  : {tstats['keys']:,} (root,pattern) keys "
          f"from {tstats['rows']:,} gold rows")

    mle = MLEDisambiguator.pretrained("calima-msa-r13")
    surfaces = [t["form"] for t in test]
    ana = []
    B = 500
    for i in range(0, len(surfaces), B):
        for d in mle.disambiguate(surfaces[i:i + B]):
            ana.append(d.analyses[0].analysis if (d and d.analyses) else None)

    # Silver root dictionary: PADT TRAIN `Root=` + arramooz. NOTHING from PADT test.
    silver_dict, prov = build_silver_root_dict()
    assert "recoverable_added" not in prov, (
        "refusing to measure with an evaluation-split-derived dictionary (SPEC-REV6 §3.1)")
    print(f"silver root dict       : {len(silver_dict):,} entries "
          f"(PADT-train {prov.get('padt_kept', 0):,} + arramooz "
          f"{prov.get('arramooz_added', 0):,})")
    
    dic = RootDictionary.build_from_padt([require(PADT_TRAIN)])
    # Augment with silver dictionary entries
    for surface, root in silver_dict.items():
        if surface not in dic.mapping:
            dic.mapping[surface] = root

    # leakage visibility: how much do the table's keys coincide with the test set?
    test_keys = set()
    for t, a in zip(test, ana):
        if a and a.get("pattern") and t["gold_root"]:
            r = norm_root(t["gold_root"] if ARABIC.search(t["gold_root"])
                          else __import__("reconcile").padt_to_arabic(t["gold_root"]))
            if r:
                test_keys.add((r, a["pattern"]))
    ov = len(test_keys & set(table)) / max(len(test_keys), 1)
    print(f"table/test key overlap  : {ov*100:.1f}% of test keys are IN the table")
    print("                          (high overlap is what makes a table look good —"
          " reported, not assumed)\n")

    routes = collections.defaultdict(lambda: collections.Counter())
    reasons = collections.Counter()
    per_class = collections.defaultdict(lambda: [0, 0])
    cls_bias = collections.defaultdict(lambda: [0, 0])
    recon_gain = 0
    examples = []

    def gold_arabic_root(t):
        """PADT `Root=` is LATIN TRANSLIT ('Hq.b'); classify the Arabic radicals, or
        every root lands in the wrong class bucket — which is what an earlier version
        of this table did, reporting almost everything as 'quadriliteral'."""
        from reconcile import padt_to_arabic
        g = t["gold_root"]
        if not g:
            return None
        return norm_root(g if ARABIC.search(g) else (padt_to_arabic(g) or ""))

    # per-token hybrid success, so coverage can be split by token class below
    hyb = [False] * len(test)
    info = [None] * len(test)          # (pattern, calima root, reconciled root) per token
    for idx, (t, a) in enumerate(zip(test, ana)):
        gold = t["form"]
        pat = a.get("pattern") if a else None
        croot = a.get("root") if a else None
        calima_diac = a.get("diac") if a else None
        try:
            rroot, rroute = reconcile(gold, croot, dic)
        except ValueError:
            # reconcile refuses a surface with no letters left after stripping (its
            # _key guard). Count it as a fail rather than crashing the measurement —
            # silently returning None here would understate coverage.
            rroot, rroute = None, "fail"
        if rroute in ("exact", "prefix"):
            recon_gain += 1
        info[idx] = (pat, croot, rroot)

        for label, root, use_table in (("1_rule_calima", croot, False),
                                       ("2_rule_reconciled", rroot, False),
                                       ("3_hybrid", rroot, True)):
            if use_table:
                # ONE implementation of the hybrid decision, shared with
                # src/audit_arity_failures.py — the two hand-rolled copies drifted and
                # counted the same set as 13 and as 18.
                got, branch, why = hybrid_render(root, pat, t["case"], table)
            else:
                branch = label
                got, why = render_rule(root, pat, t["case"])
            if got is None:
                if label == "3_hybrid":
                    reasons[why] += 1
                continue
            R = routes[branch]
            R["cov"] += 1
            if label == "3_hybrid":
                hyb[idx] = True              # the hybrid route fired for this token
            # THREE comparisons, because "accuracy" is meaningless without saying
            # against WHAT. PADT's FORM is undiacritized, so a vocalized render can
            # never string-match it — measuring only that reported a flat 0.0%.
            if got == gold:
                R["eq_gold"] += 1
            if DIAC.sub("", got) == DIAC.sub("", gold or ""):
                R["eq_skeleton"] += 1          # consonants+alif, diacritics ignored
            if calima_diac and got == calima_diac:
                R["eq_calima"] += 1            # the basis of the documented 94.3%
            if label == "3_hybrid":
                cls = EH.root_class(gold_arabic_root(t) or "")
                per_class[cls][0] += 1
                if got == gold:
                    per_class[cls][1] += 1
                elif len(examples) < 6 and got != gold:
                    examples.append((gold, got, root, pat))

    # the class bias on the CALIMA-root route, which is the one M1 is about
    for t, a in zip(test, ana):
        croot = a.get("root") if a else None
        pat = a.get("pattern") if a else None
        got, why = render_rule(croot, pat)
        cls = EH.root_class(gold_arabic_root(t) or "")
        cls_bias[cls][0] += 1
        if got is not None and DIAC.sub("", got) == DIAC.sub("", t["form"]):
            cls_bias[cls][1] += 1

    N = len(test)
    print(f"{'route':<19} {'rendered':>8} {'cover':>7} | "
          f"{'= gold':>7} {'= skel':>7} {'= calima':>9}")
    for label in ("1_rule_calima", "2_rule_reconciled",
                  "3b_hybrid_rule", "3a_hybrid_table"):
        r = routes[label]
        cov = r["cov"] / max(N, 1)
        # the table branch emits PADT's undiacritized FORM, so a CALIMA-`diac`
        # comparison is not applicable to it — print n/a rather than a number that
        # would be read as a fidelity result
        cal = (f"{100*r['eq_calima']/max(r['cov'],1):>8.1f}%"
               if label != "3a_hybrid_table" else f"{'n/a':>9}")
        print(f"{label:<19} {r['cov']:>8,} {cov*100:>6.1f}% | "
              f"{100*r['eq_gold']/max(r['cov'],1):>6.1f}% "
              f"{100*r['eq_skeleton']/max(r['cov'],1):>6.1f}% {cal}")
    print("    (3a_hybrid_table: '= gold' is its meaningful column — it returns the")
    print("     memorised PADT FORM verbatim; '= calima' is n/a by construction.)")
    print("\n  READ THE THREE COLUMNS SEPARATELY:")
    print("    '= gold'   exact match against PADT FORM — which is UNDIACRITIZED, so a")
    print("               vocalized render cannot match it. ~0% is expected, not a bug.")
    print("    '= skel'   diacritic-stripped equality: did we get the consonants right?")
    print("    '= calima' equality with the ANALYSER's own `diac` — this is the basis of")
    print("               the documented 94.3%, and it is a CONSISTENCY check (can we")
    print("               rebuild the analyser's vocalization from root+pattern?), NOT a")
    print("               gold-surface result.")
    print("\n  => PADT cannot carry the shared final-surface metric. It must be measured")
    print("     on a VOCALIZED gold corpus (EQTB `uthmani_token`) — see --eqtb.")
    print(f"\n  reconciled roots supplied where CALIMA abstained: {recon_gain:,} "
          f"({100*recon_gain/max(N,1):.1f}% of test tokens)")
    print("  -> §8.1 item 4 asked for this post-reconciliation figure: the 30.0% was")
    print("     measured BEFORE the root fix; the coverage column above re-measures it.")

    print(f"\n  hybrid accuracy by root class (gold radicals, not translit):")
    for cls, (n, e) in sorted(per_class.items(), key=lambda x: -x[1][0]):
        print(f"    {cls:<14} {n:>6,} rendered  {e:>6,} exact  {100*e/max(n,1):5.1f}%")
    print("\n  rule-with-CALIMA-root, SKELETON match by gold root class (the M1 bias):")
    for cls, (n, e) in sorted(cls_bias.items(), key=lambda x: -x[1][0]):
        print(f"    {cls:<14} {n:>6,} tokens {e:>6,} skel-ok  {100*e/max(n,1):5.1f}%")

    print(f"\n  RESIDUAL — no route renders ({sum(reasons.values()):,} tokens, "
          f"{100*sum(reasons.values())/max(N,1):.1f}%): the oracle-renderer upper bound")
    for k, v in reasons.most_common():
        print(f"    {v:>6,}  {k}")

    # ---- WHICH TOKENS ARE IN THE RESIDUAL. A rate without a denominator is not a
    # finding: "26.9% residual" hides that most of it is function words, which have no
    # root by construction and are not a rendering defect. Two predicates matter here:
    #   · class — closed-class (ADP/CCONJ/PRON/DET/PART) words have no root to plan from
    #   · usable gold root — use reconcile.is_gold_root, NOT `bool(Root=)`. PADT carries
    #     `Root=` values for particles (و، ب، ل) that are not roots; counting those as
    #     "has a gold root" inflated this cell by 791 of 4,000 tokens on first
    #     measurement. (The first version of this diagnostic made exactly that mistake.)
    from reconcile import is_gold_root as _is_gold
    CONTENT_POS = {"NOUN", "VERB", "ADJ", "ADV", "PROPN", "NUM", "AUX"}
    cls_stats = {"content": 0, "content_rend": 0, "floor": 0, "arity": 0, "nosupply": 0}
    arity_rows = []
    for k, (r, ok) in enumerate(zip(test, hyb)):
        content = r["upos"] in CONTENT_POS
        usable = bool(r["gold_root"]) and _is_gold(r["gold_root"], r["upos"])
        if content:
            cls_stats["content"] += 1
            if ok:
                cls_stats["content_rend"] += 1
            elif usable:
                cls_stats["arity"] += 1      # has a usable root and still fails = rendering
                pat_k, croot_k, rroot_k = info[k] or (None, None, None)
                arity_rows.append({"form": r["form"], "upos": r["upos"],
                                   "gold_root": r["gold_root"], "calima_root": croot_k,
                                   "pattern": pat_k, "reconciled_root": rroot_k,
                                   "why": render_rule(rroot_k, pat_k, r["case"])[1]})
            else:
                cls_stats["nosupply"] += 1   # no usable root was available = root supply
        elif not ok:
            cls_stats["floor"] += 1          # closed-class: no root exists to use
    print(f"\n  BY TOKEN CLASS (the residual needs a denominator; §2x.8):")
    print(f"    content words       : {cls_stats['content']:,} tokens, "
          f"{cls_stats['content_rend']:,} rendered = "
          f"{100*cls_stats['content_rend']/max(cls_stats['content'],1):.1f}% "
          f"CONTENT-WORD COVERAGE")
    print(f"      failing with a usable gold root : {cls_stats['arity']:,}"
          f"   (a rendering defect)")
    print(f"      failing with no usable root     : {cls_stats['nosupply']:,}"
          f"   (root supply, not rendering)")
    print(f"    closed-class words  : {cls_stats['floor']:,} unrendered = "
          f"{100*cls_stats['floor']/max(N,1):.1f}% of all tokens — a STRUCTURAL floor; "
          f"function words have no root by design")

    # ---- ROUTE 4: the closed-class bypass (`docs/CLOSED-CLASS-INVENTORY.md`).
    # It is NOT part of the root-tree claim and is counted separately so it cannot inflate
    # content-word coverage. What runs here is the SKELETON half only: it emits the surface
    # for function words that have a TRAIN surface, and identity for punctuation. The
    # VOCALISED half of the bypass (108 static vocalised surfaces + an abstaining tail) is
    # NOT measurable on PADT — PADT's FORM is 98.7% undiacritized (§2x.4), the same
    # convention wall the hybrid table hit. It must be scored on a vocalised corpus.
    cc_surf, cc_per = build_closed_class_surfaces(PADT_TRAIN)
    print(f"\n  ROUTE 4 — closed-class bypass (SKELETON half; separate from the claim)")
    print(f"    TRAIN surfaces : {len(cc_surf):,}  ("
          + ", ".join(f"{k} {v:,}" for k, v in cc_per.most_common()) + ")")
    cc = {"covered": 0, "func": 0, "ident": 0, "x": 0, "unseen": 0}
    all_tok = 0
    for r, ok in zip(test, hyb):
        tag, bypassed = r["upos"], False
        if tag in IDENTITY_TAGS:
            bypassed, cc["ident"] = True, cc["ident"] + 1
        elif tag in FUNCTION_TAGS:
            if r["form"] in cc_surf:
                bypassed, cc["func"] = True, cc["func"] + 1
            else:
                cc["unseen"] += 1
        elif tag == "X":
            cc["x"] += 1                       # out of scope for both mechanisms (§4.6)
        if bypassed:
            cc["covered"] += 1
        if ok or bypassed:
            all_tok += 1
    print(f"    function words reached : {cc['func']:,}")
    print(f"    punctuation/symbols    : {cc['ident']:,} (identity)")
    print(f"    function words UNSEEN  : {cc['unseen']:,} (no TRAIN surface -> abstain)")
    print(f"    X, out of scope        : {cc['x']:,}")
    print(f"    bypass coverage        : {cc['covered']:,} = "
          f"{100*cc['covered']/max(N,1):.1f}% of all tokens")
    print(f"    '= gold' for the bypass: n/a BY CONSTRUCTION — it emits the reference "
          f"surface itself,")
    print(f"                             so any accuracy printed here would be a copy, "
          f"not a result.")
    # TWO denominators, reported side by side and never mixed: `limit` counts Arabic
    # tokens, so the punct-inclusive run adds PUNCT/SYM on top of the same 4,000.
    arabic_cov, n_arabic = all_tok - cc["ident"], N - cc["ident"]
    print(f"\n  ALL-TOKEN COVERAGE (Tier 1 root-tree + Tier 2 bypass, Tier 3 excluded)")
    print(f"    two denominators, never mixed:")
    print(f"    1. Arabic tokens only       : {arabic_cov:,} / {n_arabic:,} = "
          f"{100*arabic_cov/max(n_arabic,1):.1f}%   <- the FROZEN baseline")
    print(f"    2. Running text +PUNCT/SYM  : {all_tok:,} / {N:,} = "
          f"{100*all_tok/max(N,1):.1f}%   (identity adds {cc['ident']:,})")
    print(f"    X (Tier 3, pass-through, NOT counted above): {cc['x']:,} = "
          f"{100*cc['x']/max(N,1):.1f}%")
    if arity_rows:
        print(f"\n    every content-word failure that HAS a usable gold root "
              f"({len(arity_rows)}), with its tuple:")
        for row in arity_rows:
            print(f"      {row['form']:<12} {row['upos']:<6} gold={row['gold_root']:<9} "
                  f"calima={str(row['calima_root']):<11} pat={str(row['pattern']):<15} "
                  f"recon={str(row['reconciled_root']):<10} {row['why']}")
    if examples:
        print("\n  hybrid mismatches vs PADT FORM (the gold is undiacritized — note the")
        print("  rendered consonants are largely right):")
        for g, gt, r, p in examples:
            print(f"    want {g!r:20} got {gt!r:20} root={r} pat={p!r}")

    # A punct-inclusive run writes its OWN file: overwriting the baseline report with an
    # altered denominator is exactly the silent invalidation this flag exists to prevent.
    out = Path(RAW).parent / "out" / (
        "renderer_report_punct.json" if include_punct else "renderer_report.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "test_tokens": N, "table_keys": tstats["keys"],
        "table_test_key_overlap": ov,
        "routes": {k: {"coverage": v["cov"] / max(N, 1),
                       "exact_vs_gold_padt": v["eq_gold"] / max(v["cov"], 1),
                       "exact_vs_skeleton": v["eq_skeleton"] / max(v["cov"], 1),
                       "exact_vs_calima_diac": v["eq_calima"] / max(v["cov"], 1)}
                   for k, v in routes.items()},
        "conventions": {
            "1_rule_calima": "rule render w/ CALIMA root; '= calima' is the consistency check",
            "2_rule_reconciled": "rule render w/ reconciled root",
            "3b_hybrid_rule": "hybrid rule branch (no table key) — '= calima' is valid",
            "3a_hybrid_table": "hybrid table branch — returns PADT's UNDIACRITIZED FORM "
                               "verbatim; '= calima' is n/a, '= gold' is its column",
        },
        "dictionary_sources": "PADT-train Root= + arramooz only; nothing from PADT test "
                              "(SPEC-REV6 §3.1)",
        "reconciled_roots_supplied": recon_gain,
        "residual": dict(reasons),
        "by_token_class": {
            "content_tokens": cls_stats["content"],
            "content_rendered": cls_stats["content_rend"],
            "content_word_coverage": cls_stats["content_rend"] / max(cls_stats["content"], 1),
            "failing_with_usable_gold_root": cls_stats["arity"],
            "failing_without_any_root": cls_stats["nosupply"],
            "closed_class_unrendered_structural_floor": cls_stats["floor"],
            "arity_failure_tuples": arity_rows,
            "note": "content-word coverage is the number to quote for the root-tree claim; "
                    "closed-class words have no root by design",
        },
        "closed_class_bypass": {
            "scope": "Tier 2 — grammatical glue, NOT part of the root-tree claim",
            "train_surfaces": len(cc_surf),
            "function_words_reached": cc["func"],
            "punctuation_identity": cc["ident"],
            "function_words_unseen": cc["unseen"],
            "coverage": cc["covered"] / max(N, 1),
            "accuracy": "n/a by construction — it emits the reference surface itself",
            "vocalised_half": "not measurable on PADT (FORM is 98.7% undiacritized, §2x.4) — "
                              "score it on a vocalised corpus",
        },
        "all_token_coverage": {
            "arabic_only": {
                "value": (all_tok - cc["ident"]) / max(N - cc["ident"], 1),
                "n": all_tok - cc["ident"], "denominator": N - cc["ident"],
                "note": "the FROZEN baseline — quote this denominator with the rate",
            },
            "running_text": {
                "value": all_tok / max(N, 1),
                "n": all_tok, "denominator": N,
                "note": "includes the PUNCT/SYM identity pass-through",
            },
            "tiers": "Tier 1 root-tree + Tier 2 bypass; Tier 3 (X) NOT counted",
            "x_excluded": cc["x"],
            "include_punct": include_punct,
            "note": "an all-token figure must always be labelled as including a non-root-tree "
                    "component, AND with its denominator",
        },
    }, indent=2), encoding="utf-8")
    print(f"\nreport -> {out}")
    return 0


def fold_orth(s: str) -> str:
    """Fold Uthmani orthography onto the standard (imlaa'i) convention CALIMA emits.

    EQTB's `uthmani_token` is the vocalized gold, but it writes alef-wasla ٱ, the
    superscript alef ٰ and Uthmani-only marks where CALIMA writes plain ا. Comparing
    raw would charge the renderer for an ORTHOGRAPHIC CONVENTION difference it did not
    cause. Both raw and folded numbers are reported so the penalty stays visible
    instead of being silently absorbed.
    """
    if not s:
        return s
    out = s.replace("\u0671", "\u0627")      # ٱ alef wasla -> ا
    out = out.replace("\u0670", "")          # superscript alef
    out = out.replace("\u0640", "")          # tatweel
    out = "".join(c for c in out if not ("\u06d6" <= c <= "\u06ed"))   # Uthmani marks
    return out


def measure_eqtb(limit: int = 3000) -> int:
    """The renderer against GOLD VOCALIZED surface — the shared final-surface metric.

    PADT cannot carry this metric (§2m, Finding H): its FORM is undiacritized, so a
    vocalized render can never match it. EQTB's `uthmani_token` is 90.9% diacritized,
    so it is the only available corpus that can.

    Two configurations, so root error and rendering error are SEPARATED:
      A: GOLD root + oracle pattern  -> pure rendering quality (an upper bound)
      B: CALIMA root + oracle pattern -> adds the analyser's root errors
    The gap between A and B is what the root pipeline costs, and it is the number to
    quote when someone asks whether the renderer or the analysis is the problem.
    """
    import csv
    import eval_harness as EH
    from camel_tools.disambig.mle import MLEDisambiguator

    print("=" * 84)
    print("R1 — the renderer against GOLD VOCALIZED surface (EQTB uthmani_token)")
    print("=" * 84)
    print("This is the shared final-surface metric on the only corpus that can carry it.")
    print("The pattern comes from CALIMA analysing the token: an ORACLE pattern, so the")
    print("result is a rendering UPPER BOUND, not an end-to-end model number.\n")

    rows = []
    with open(require(EQTB_CSV), encoding="utf-16", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            gold = (row.get("uthmani_token") or "").strip()
            root = (row.get("root_ar") or "").strip()
            if not gold or not ARABIC.search(gold):
                continue
            if root in ("", "\u0640", "_", "-"):
                root = None
            case = EQTB_CASE.get((row.get("nominal_case") or "").strip().upper())
            rows.append((gold, norm_root(root) if root else None, case))
            if len(rows) >= limit:
                break
    print(f"EQTB rows read        : {len(rows):,}")
    n_root = sum(1 for _, r, _ in rows if r)
    n_case = sum(1 for _, _, c in rows if c is not None)
    print(f"with a REAL gold root : {n_root:,} ({100*n_root/max(len(rows),1):.1f}%)")
    print(f"with a gold CASE      : {n_case:,} ({100*n_case/max(len(rows),1):.1f}%)")

    mle = MLEDisambiguator.pretrained("calima-msa-r13")
    surf = [fold_orth(g) for g, _, _ in rows]
    ana = []
    B = 500
    for i in range(0, len(surf), B):
        for d in mle.disambiguate(surf[i:i + B]):
            ana.append(d.analyses[0].analysis if (d and d.analyses) else None)

    stats = {k: collections.Counter() for k in ("A", "Ap", "B", "Bp")}
    per_class = collections.defaultdict(lambda: [0, 0])
    reasons = collections.Counter()
    examples = []

    for (gold, gold_root, gold_case), a in zip(rows, ana):
        pat = a.get("pattern") if a else None
        croot = norm_root(a.get("root")) if a else None
        for cfg_name, root, case in (("A", gold_root, None),
                                     ("Ap", gold_root, gold_case),
                                     ("B", croot, None),
                                     ("Bp", croot, gold_case)):
            got, why = render_rule(root, pat)
            if got is not None and case is not None:
                got = apply_case(got, case)      # Head 5's contribution, applied here
            if got is None:
                if cfg_name == "A":
                    reasons[why] += 1
                continue
            S = stats[cfg_name]
            S["cov"] += 1
            if got == gold:
                S["eq_raw"] += 1
            if fold_orth(got) == fold_orth(gold):
                S["eq_fold"] += 1
            if DIAC.sub("", got) == DIAC.sub("", gold):
                S["eq_skel"] += 1
            if cfg_name == "Ap":
                cls = EH.root_class(gold_root or "")
                per_class[cls][0] += 1
                if fold_orth(got) == fold_orth(gold):
                    per_class[cls][1] += 1
                elif len(examples) < 10:
                    examples.append((gold, got, gold_root, pat))

    N = len(rows)
    labels = {"A": "A gold root, no case vowel",
              "Ap": "A + gold CASE VOWEL applied",
              "B": "B CALIMA root, no case vowel",
              "Bp": "B + gold CASE VOWEL applied"}
    print(f"\n{'config':<34} {'render':>7} {'cover':>7} {'=raw':>7} {'=fold':>7} {'=skel':>7}")
    for k in ("A", "Ap", "B", "Bp"):
        S = stats[k]
        c = max(S["cov"], 1)
        print(f"{labels[k]:<34} {S['cov']:>7,} {100*S['cov']/max(N,1):>6.1f}% "
              f"{100*S['eq_raw']/c:>6.1f}% {100*S['eq_fold']/c:>6.1f}% "
              f"{100*S['eq_skel']/c:>6.1f}%")
    a_, ap = stats["A"], stats["Ap"]
    print(f"\n  THE 'Ap' ROW IS THE POINT: applying the case vowel takes exact-vocalized")
    print(f"  from {100*a_['eq_fold']/max(a_['cov'],1):.1f}% -> {100*ap['eq_fold']/max(ap['cov'],1):.1f}%. "
          f"That is a DESIGN fact, not a bug: SPEC §3.2 strips the")
    print("  case vowel out of the Head-3 label precisely to disentangle it from Head 5, so")
    print("  the renderer CANNOT emit it alone. The gap measures Head 5's contribution.")
    print("  '=raw' vs '=fold' isolates the ORTHOGRAPHIC CONVENTION penalty (ٱ/ٰ/assimilation),")
    print("  which is not the renderer's fault and must not be silently absorbed.")

    print("\n  exact-vocalized (folded) by gold root class, config Ap:")
    for cls, (n, e) in sorted(per_class.items(), key=lambda x: -x[1][0]):
        print(f"    {cls:<14} {n:>6,} rendered {e:>6,} exact {100*e/max(n,1):5.1f}%")

    print(f"\n  abstentions (config A): {sum(reasons.values()):,}")
    for k, v in reasons.most_common():
        print(f"    {v:>6,}  {k}")
    if examples:
        print("\n  mismatches (want vs got), config Ap:")
        for g, gt, r, p in examples:
            print(f"    want {g!r:20} got {gt!r:20} root={r} pat={p!r}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--measure", action="store_true")
    ap.add_argument("--eqtb", action="store_true",
                    help="gold-VOCALIZED surface metric (EQTB uthmani_token)")
    ap.add_argument("--limit", type=int, default=4000)
    ap.add_argument("--include-punct", action="store_true",
                    help="also keep PUNCT/SYM tokens (identity pass-through); `--limit` still "
                         "counts ARABIC tokens so the 4,000 baseline is unperturbed, and the "
                         "report goes to renderer_report_punct.json")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if args.eqtb:
        return measure_eqtb(limit=args.limit)
    if args.measure:
        return measure(limit=args.limit, include_punct=args.include_punct)
    ap.print_help()
    return 0


def selftest() -> int:
    """Known answers, including the defect this file exists to avoid."""
    print("=" * 84)
    print("RENDERER — known-answer self-test")
    print("=" * 84)
    bad = []
    cases = [
        ("ص.د.ر", "ال1ا2ِ3ِ", "الصادِرِ", "the documented fix case (ال survives)"),
        ("ك.ت.ب", "1ا2ِ3", "كاتِب", "triliteral, alif in the template"),
        ("ع.ل.م", "مُ1َ2ِّ3", "مُعَلِّم", "doubled middle radical (shadda)"),
        ("د.ر.س", "1َ2ْ3َ", "دَرْسَ", "sound"),
    ]
    for root, pat, want, why in cases:
        got, reason = render_rule(root, pat)
        ok = got == want
        if not ok:
            bad.append(f"render_rule({root},{pat}) = {got!r}, want {want!r}")
        print(f"  [{'OK ' if ok else 'FAIL'}] {root:9} {pat:12} -> {got!r:14} "
              f"{'' if ok else f'(want {want!r}) '}{why}")

    print("\n  the defect that must never come back: ف/ع/ل round-trip")
    got, _ = render_rule("ص.د.ر", "ال1ا2ِ3ِ")
    print(f"  [{'OK ' if got == 'الصادِرِ' else 'FAIL'}] 'ال' is preserved verbatim "
          f"-> {got!r}")
    if got != "الصادِرِ":
        bad.append("ال was destroyed — the ف/ع/ل round-trip is back")

    print("\n  abstentions must be reported, never silently rendered")
    for root, pat, want_reason in (("ص.#.ر", "1ا2ِ3", "no_root"),
                                   ("ص.د.ر", "1ا2", "digit_set_incomplete"),
                                   ("ص.د.ر", "1123", "repeated_digit"),
                                   ("ص.د", "1ا2ِ3", "root_len_mismatch"),
                                   ("ص.د.ر", None, "no_pattern")):
        got, reason = render_rule(root, pat)
        ok = got is None and reason == want_reason
        if not ok:
            bad.append(f"abstention {root}/{pat}: got {got!r}/{reason}, want None/{want_reason}")
        print(f"  [{'OK ' if ok else 'FAIL'}] {str(root):9} {str(pat):12} -> abstains "
              f"({reason})")

    print("\n  case is applied SEPARATELY so Head 3 stays disentangled from Head 5")
    ok = apply_case("دَرْس", 0) == "دَرْسُ" and apply_case("دَرْسَ", 1) == "دَرْسَ"
    if not ok:
        bad.append("apply_case wrong")
    print(f"  [{'OK ' if ok else 'FAIL'}] apply_case adds a vowel only when absent")

    print("\n" + "=" * 84)
    if bad:
        print(f"FAILED ({len(bad)}):")
        for b in bad:
            print("  -", b)
        return 1
    print("ALL PASS — in-place substitution, ال preserved, abstentions named, case separate")
    print("=" * 84)
    return 0


if __name__ == "__main__":
    sys.exit(main())
