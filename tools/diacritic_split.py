"""diacritic_split.py — split the renderer's `diacritic_only` bucket into NAMED sub-rules and SIZE each
rule on the frozen ruler BEFORE one line of it is implemented.

WHY THIS EXISTS
    `diacritic_only` is the largest defect bucket in `score_final_surface` — rows where the renderer emits
    the right skeleton with the wrong diacritics, so the human's token and the renderer's surface differ by
    marks alone. It was described in the roadmap as three sub-rules (over-diacritization, a missing hamza-seat
    vowel, dual/diptote case). That description came from looking at a handful of examples, and it was wrong
    in the most expensive way: the single largest sub-rule — a MISSING SHADDA on a sun letter, 64 rows, 40% of
    the bucket — was not in the list at all. A bucket's size is not a lever's size, and a bucket's *name* is
    not a decomposition. This tool produces the decomposition, and for every sub-rule it measures what
    implementing that rule would actually be worth on the frozen ruler.

WHAT IT DOES
    For every usable row of `data/annotation/bench-gold.jsonl` it renders with engine v3 (passing the token,
    whose clitic plane is a legal renderer INPUT since round-28d) and scores through the SHARED metric
    `final_surface.score_final_surface`. It then (1) classifies each `diacritic_only` failure into a named
    sub-rule by the STRUCTURE of the diff between the gold token and the rendered surface — never by the row's
    label — and (2) applies each candidate repair rule to the rendered string and measures rows fixed, rows
    broken, and net. Output: a table on stdout and `dist/diacritic-split.json`.

WHAT IT DOES NOT DO
    It does not change the renderer, the metric, or any pipeline code, and it implements no rule. Every
    candidate rule lives in this file as a pure function of (surface, row, case) that is applied AFTER the
    fact, in the measurement only. Sizing is not shipping: a rule that measures +62 here still has to be
    implemented without regressing a single class, and the implementation bar is pre-registered in
    `ACTIVE_BACKLOG.md` item 9, not in this file.

    It also does not decide whether a sub-rule is worth having. It reports the number and the verdict
    (`propose` / `dropped`) that the number forces, and a sub-rule with net <= 0 is recorded as dropped with
    its number, never quietly omitted.

THE PITFALL IT AVOIDS
    Force-fitting. Every row that does not fit a named rule is left in an explicit `unexplained` bucket; if
    that bucket grows, the decomposition is wrong, not the rows. Rows are never reassigned to make the
    taxonomy look complete, and no rule is allowed to compare against the gold token to decide its output —
    the only gold-derived input any rule may read is the token's definiteness (a proclitic `al-`), which the
    model itself reads.

USAGE
    python tools/diacritic_split.py                  # measure, print the table, write the JSON
    python tools/diacritic_split.py --check          # assert the pre-registered numbers; non-zero on drift
    python tools/diacritic_split.py --json PATH      # write the artifact elsewhere
"""
from __future__ import annotations

# ATTRIBUTION SWITCH — this file measures the SURFACE pipeline, so it pins the corpus spelling resource OFF.
# The resource shipped ON at the zero-loss setting (EVIDENCE_LOG §2bn: shipped fidelity 592 -> 695 = 71.4%).
# Every number below is about the repair layer / the diff structure measured WITHOUT that input. Without this
# line the pins drift the moment the resource ships — measured, in this order: diacritic_split --check exit 1,
# tanwin_probe --check -189 -> -266, hollow_probe --check "seat_for_fail net +1 != pinned +0".
import os
os.environ["ARABIC_SPELLING_RESOURCE"] = "0"
# AND THE AFFIX PLANE, FOR EXACTLY THE SAME REASON (§2cn). The plane shipped at §2ce, AFTER these pins
# were written, and it is a post-hoc layer like the resource: without this line the pins drift and
# `--check` exits 1 with 10 problems that all look like regressions. They are not. Measured
# (`G:/aide-harness/attribute_2cn.py`): with the plane switched off, the SAME code reproduces the pinned
# `shipped 592` EXACTLY. The plane had been emitting `الْ` unconditionally, which is not a member of
# `candidates(gold)` for a sun-initial definite noun (`الطَّحْنِ`), so it converted 24 rows the bare stem
# was passing by the metric's affix-split leniency into hard misses — that is the whole of the
# 592 -> 568 movement this gate had been reporting. The plane is still measured, in §2ce and §2cn.
os.environ["ARABIC_AFFIX_PLANE"] = "0"


import argparse
import collections
import hashlib
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

_TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(_TOOLS))
sys.path.insert(0, str(_TOOLS.parent / "src"))

from repo_root import resolve_root                       # noqa: E402
from final_surface import (                              # noqa: E402
    DIAC, candidates, classify_defect, nfc, render_triple, score_final_surface, stem_match, strip_diac,
)
from renderer import CASE_VOWEL                          # noqa: E402

ENGINE = "v3"
RULER = Path("data") / "annotation" / "bench-gold.jsonl"
ARTIFACT = Path("dist") / "diacritic-split.json"

# --- the pre-registered numbers (EVIDENCE_LOG §2be; asserted by --check, never tuned to pass) ----------
# RE-PINNED 2026-10-14 (§2cv) after `render_v3` began canonicalising the pattern with
# `canonicalize_mater_vowels`. THIS RE-PIN CARRIES A VERDICT CHANGE, named here because a rule that stops
# earning rows is a change of verdict, not drift:
#   * `add_hamza_fatha` falls from +51 to **+0** and its own verdict line now reads `dropped`. The rule still
#     SHIPS and its work still happens — the canonicaliser now performs it UPSTREAM, inside the pattern, on
#     the pre-layer path. So the +52 move in this baseline (480 -> 532) is a RELOCATION, not new capability:
#     the shipped total moves only +1 with it (613 -> 614). The four shipped rules remain worth +82 rows
#     independently (614 - 532) and the >= 55% bar is still cleared.
#   * every other rule's verdict is unchanged; `apply_diptote_fatha` drifts one row on the broken side
#     (46 -> 47, still dropped), and the `hamza_seat_vowel_missing` sub-rule collapses 58 -> 2 because those
#     rows now leave through the canonicaliser instead.
# History, kept so the movement stays checkable: baseline 463 (§2be) -> 466 (§2cn) -> 480 (§2co) -> 532
# (§2cv); shipped 592 -> 595 -> 613 -> 614; four together 583 -> 586 -> 601 -> 602.
P_BASELINE = 532                 # stem_correct / 973, measured with the resource AND the affix plane off
P_BUCKET = 112                   # size of the diacritic_only bucket (was 164)
P_FOUR_TOGETHER = 602            # the four proposed rules applied jointly = 61.9% (delta over baseline +70)
P_SHIPPED = 614                  # the SHIPPED pipeline. SUPERSEDED VALUES, each with what it measured:
                                 #   592  §2bj .. §2cd — repairs only, no affix plane.
                                 #   568  §2ce .. §2cm — the affix plane as shipped, emitting `الْ`
                                 #        unconditionally: 24 sun-initial rows the bare stem was passing
                                 #        by the metric's leniency became hard misses. Fixed in §2cn.
                                 #   595  §2cn — that fix, with the renderer-level rules of §2cn/§2co
                                 #        still to come.
                                 #   613  §2co .. §2cu — before §2cv's canonicaliser move.
P_RULE_FIXED_BROKEN = {
    "add_sun_letter_shadda": (63, 0),
    "add_hamza_fatha": (0, 0),
    "drop_long_vowel_sukun": (3, 0),
    "dual_nominative_kasra": (4, 2),
    "drop_redundant_hamza_kasra": (11, 15),
    "apply_diptote_fatha": (10, 47),
}
PROPOSED = ("add_sun_letter_shadda", "add_hamza_fatha", "drop_long_vowel_sukun", "dual_nominative_kasra")

# The sub-rule counts recorded in EVIDENCE_LOG §2be. A row carrying MORE THAN ONE simultaneous defect has no
# single true bucket — whichever rule is tested first claims it — so the taxonomy is asserted with a small
# tolerance and its drift is printed, while every RULE number above is asserted exactly (those reproduce to
# the row, because each rule is applied to the whole ruler independently of any grouping).
# Four entries moved in the §2co re-pin (sun_letter_shadda_missing 64->65, hamza_seat_vowel_missing 56->58,
# diptote_case_vowel 11->12, redundant_hamza_kasra 9->12, other_case_vowel 5->3): the same cause, seen from
# the other side — rows whose base letters are now correct can only fail on marks.
P_SUBRULES = {
    "sun_letter_shadda_missing": 65,
    "hamza_seat_vowel_missing": 2,      # was 58 — §2cv: the canonicaliser now repairs these UPSTREAM, so the
                                        # pre-layer bucket no longer contains them (2 remain, unexplained by it)
    "diptote_case_vowel": 13,
    "redundant_hamza_kasra": 12,
    "other_extra_mark": 8,
    "other_case_vowel": 3,
    "dual_case_vowel": 4,
    "extra_long_vowel_sukun": 3,
    "unexplained": 2,
}
P_SUBRULE_TOLERANCE = 2

# --- classifier vocabulary ----------------------------------------------------------------------------
MARKS = set("\u064b\u064c\u064d\u064e\u064f\u0650\u0651\u0652")     # tanwin x3, fatha, damma, kasra, shadda, sukun
SHADDA, SUKUN = "\u0651", "\u0652"
CASE_VOWELS = {"\u064e", "\u064f", "\u0650"}                        # fatha, damma, kasra
SUN = set("تثدذرزسشصضطظلن")
HAMZA_SEAT = set("أإئؤءآٱ")
LONG_VOWEL = set("اوي")
CASE_STR = {"NOM": 0, "ACC": 1, "GEN": 2}
CASE_INT = {v: k for k, v in CASE_VOWEL.items()}
UNUSABLE = {"", "ABSTAIN", "NONE", "NA", "#", None}
DEF_PRO = ("وال", "فال", "بال", "كال", "ال", "لل")


def case_int(raw):
    """NOM/ACC/GEN, or the mark itself, or an int, -> the renderer's case index (or None)."""
    if isinstance(raw, int):
        return raw
    if not isinstance(raw, str):
        return None
    raw = raw.strip()
    if raw in CASE_STR:
        return CASE_STR[raw]
    return CASE_INT.get(raw)


def usable(row) -> bool:
    """Same filter as the audit instrument, so the two can never disagree about the denominator."""
    if row.get("root") in UNUSABLE or row.get("wazn_pattern") in UNUSABLE:
        return False
    return 2 <= len([c for c in str(row["root"]) if c != "."]) <= 5


def letter_marks(s: str) -> list[tuple[str, frozenset]]:
    """[(letter, marks attached to it)] — marks bind to the letter they follow."""
    out: list[list] = []
    for ch in nfc(s) or "":
        if ch in MARKS or DIAC.match(ch):
            if out:
                out[-1][1].add(ch)
        else:
            out.append([ch, set()])
    return [(l, frozenset(m)) for l, m in out]


def diff_positions(gold: str, pred: str) -> set:
    """Letter indices whose marks differ, against the gold's matching legal affix split.

    Empty when the two disagree in their LETTERS (not a diacritic-only defect at all). Used to report how many
    bucket rows carry more than one simultaneous defect — those are the rows whose bucket is decided by rule
    order rather than by the data.
    """
    same = [c for c in candidates(gold) if strip_diac(c) == strip_diac(pred)]
    g, p = letter_marks(same[0] if same else gold), letter_marks(pred)
    if [l for l, _ in g] != [l for l, _ in p]:
        return set()
    return {i for i, ((_, gm), (_, pm)) in enumerate(zip(g, p)) if gm != pm}


def taxonomy(gold: str, pred: str) -> str:
    """Name the diacritic sub-rule explaining `pred` against the gold token, or `unexplained`.

    The decision uses ONLY the structure of the mark diff: which marks the human wrote that the renderer
    dropped (missing), which the renderer invented (extra), and on which letter. It never looks at the row's
    label, and it never guesses a bucket to keep the taxonomy tidy — a row that fits no named rule is
    `unexplained`, and a growing `unexplained` bucket means this function is wrong, not the data.

    The comparison is against the LEGAL AFFIX SPLIT of the gold that `classify_defect` itself matched, not
    against the raw token: the bucket holds rows whose gold candidate differs from the surface by marks alone,
    and a proclitic (`al-`, `wa-`, …) that the renderer folded into the stem is not a diacritic defect at all.
    Comparing against the raw token instead misreads every such row as a skeleton mismatch.
    """
    same = [c for c in candidates(gold) if strip_diac(c) == strip_diac(pred)]
    g, p = letter_marks(same[0] if same else gold), letter_marks(pred)
    if [l for l, _ in g] != [l for l, _ in p]:
        return "unexplained"                      # not a diacritic-only difference; out of scope here

    missing, extra = [], []
    for i, ((gl, gm), (pl, pm)) in enumerate(zip(g, p)):
        if gm - pm:
            missing.append((i, gl, gm - pm))
        if pm - gm:
            extra.append((i, pl, pm - gm))

    # 1. a shadda the human wrote and the renderer did not, on a sun letter (assimilation: ash-shams).
    if any(SHADDA in m and l in SUN for _, l, m in missing):
        return "sun_letter_shadda_missing"
    # 2. a vowel missing on a hamza seat.
    if any((m & CASE_VOWELS) and l in HAMZA_SEAT for _, l, m in missing):
        return "hamza_seat_vowel_missing"
    # 3. an extra kasra the renderer wrote on a hamza seat (i-kalla: the seat carries no vowel).
    if any((m & {"\u0650"}) and l in HAMZA_SEAT for _, l, m in extra):
        return "redundant_hamza_kasra"
    # 4. an extra sukun sitting ON a long-vowel letter: the pattern licences no closed syllable there.
    if any(SUKUN in m and l in LONG_VOWEL for _, l, m in extra):
        return "extra_long_vowel_sukun"

    # 5-7. the diff is a case-vowel swap on the final letter: which rule that is depends on the ending.
    if missing or extra:
        positions = {i for i, _, _ in missing} | {i for i, _, _ in extra}
        only_final = positions == {len(g) - 1}
        # the marks themselves, not the per-letter frozensets that carry them
        swapped = {c for _, _, m in missing + extra for c in m}
        if only_final and swapped and swapped <= CASE_VOWELS:
            gave = {c for _, _, m in missing for c in m}          # what the human wrote
            got = {c for _, _, m in extra for c in m}             # what the renderer wrote instead
            if gave == {"\u064e"} and got == {"\u0650"}:
                return "diptote_case_vowel"        # human fatha (ACC), renderer kasra (GEN)
            if gave == {"\u0650"} and got == {"\u064f"}:
                return "dual_case_vowel"           # human kasra (dual NOM), renderer damma
            if gave and got:
                # a genuine swap — a diptote's fatha is what this word should carry, whatever it ends in
                return "diptote_case_vowel" if g[-1][0] in "\u0629\u0621" else "other_case_vowel"
            if got and not gave:
                # nothing missing: the renderer INVENTED a mark here. That is an extra mark, not a case choice.
                return "other_extra_mark"
            return "other_case_vowel"              # a dropped case vowel is still a case defect
        # 8. some other invented mark.
        if extra:
            return "other_extra_mark"
        return "other_case_vowel"
    return "unexplained"


# --- candidate repair rules ---------------------------------------------------------------------------
# Ported VERBATIM from the round-1 sizing instrument so the numbers in §2be reproduce exactly. They take
# (surface, row, case_index) and are pure: they never read the gold token except for its definiteness.

def is_definite(token: str) -> bool:
    return (strip_diac(token) or "").startswith(DEF_PRO)


def rule_sun_shadda(s, row, ci):
    """Write the shadda of a sun-letter assimilation — `ash-shams` not `ash-shams` (undoubled)."""
    if not s or not is_definite(row["target_token"]):
        return s
    for i, ch in enumerate(s):
        if DIAC.match(ch):
            continue
        if ch in SUN and SHADDA not in s[i + 1:i + 3]:
            return s[:i + 1] + SHADDA + s[i + 1:]
        return s
    return s


def rule_hamza_fatha(s, row, ci):
    """A bare seat at word start takes the fatha the pattern asks for (`al-ansar`)."""
    if s and s.startswith("\u0623") and len(s) > 1 and not DIAC.match(s[1]) and s[1] not in "\u0627\u0648":
        return "\u0623\u064e" + s[1:]
    return s


def rule_long_vowel_sukun(s, row, ci):
    """A long vowel is not closed: drop the sukun the pattern does not licence."""
    return s.replace("\u064f\u0648\u0652", "\u064f\u0648").replace("\u0650\u064a\u0652", "\u0650\u064a")


def rule_dual_nom(s, row, ci):
    """The dual nominative ends in kasra, not damma."""
    if ci == 0 and s.endswith("\u064e\u0627\u0646\u064f"):
        return s[:-1] + "\u0650"
    if ci == 0 and s.endswith("\u064e\u0627\u0646"):
        return s + "\u0650"
    return s


def rule_over_hamza_kasra(s, row, ci):
    """DROPPED: stripping the kasra under a word-initial seat costs more rows than it fixes."""
    return "\u0625" + s[2:] if s.startswith("\u0625\u0650") else s


def rule_diptote_fatha(s, row, ci):
    """DROPPED: a suffix test is not a diptote test — `apply_diptote_fatha` costs 44 rows to win 10."""
    if ci == 2 and s.endswith("\u064e\u0629\u0650"):
        return s[:-1] + "\u064e"
    if ci == 2 and s.endswith("\u064e\u0627\u0621\u0650"):
        return s[:-1] + "\u064e"
    if ci == 2 and s.endswith("\u0650\u062f\u0650"):
        return s[:-1] + "\u064e"
    return s


RULES = {
    "add_sun_letter_shadda": rule_sun_shadda,
    "add_hamza_fatha": rule_hamza_fatha,
    "drop_long_vowel_sukun": rule_long_vowel_sukun,
    "dual_nominative_kasra": rule_dual_nom,
    "drop_redundant_hamza_kasra": rule_over_hamza_kasra,
    "apply_diptote_fatha": rule_diptote_fatha,
}


def load_ruler(root: Path):
    """The frozen ruler and its digest — the digest is in the artifact so a report can name its bytes."""
    path = root / RULER
    raw = path.read_bytes()
    rows = [json.loads(l) for l in raw.decode("utf-8").splitlines() if l.strip()]
    return rows, hashlib.sha256(raw).hexdigest()


def measure(base, rule_names):
    """Apply `rule_names` in order to every rendered row; return fixed / broken / net / new correct."""
    fixed = broken = 0
    pairs = []
    for row, ci, pred in base:
        out = pred
        if out is not None:
            for name in rule_names:
                out = RULES[name](out, row, ci)
        pairs.append((row["target_token"], out))
        was = stem_match(row["target_token"], pred) if pred is not None else False
        now = stem_match(row["target_token"], out) if out is not None else False
        if now and not was:
            fixed += 1
        if was and not now:
            broken += 1
    return {"fixed": fixed, "broken": broken, "net": fixed - broken, "correct": score_final_surface(pairs)["stem_correct"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", help="repository root (defaults to the tree this tool lives in)")
    ap.add_argument("--json", default=str(ARTIFACT), help="where to write the artifact")
    ap.add_argument("--check", action="store_true",
                    help="assert the pre-registered numbers and exit non-zero on any drift")
    args = ap.parse_args(argv)
    root = resolve_root(args.root)

    rows, digest = load_ruler(root)
    usable_rows = sorted((r for r in rows if usable(r)), key=lambda r: r.get("id") or "")
    base = []
    for row in usable_rows:
        # repairs=False ON PURPOSE. This tool exists to size the repair layer, so it must see the
        # pipeline as it was BEFORE the layer — otherwise the layer's own effect is unmeasurable the
        # moment it ships, and every number below would collapse to "no effect". The shipped pipeline
        # is measured separately at the end and asserted against P_SHIPPED.
        pred, _why = render_triple(row["root"], row["wazn_pattern"], case_int(row.get("case")),
                                   engine=ENGINE, token=row["target_token"], repairs=False)
        base.append((row, case_int(row.get("case")), pred))

    baseline = score_final_surface([(r["target_token"], p) for r, _, p in base])
    bucket_rows = [(r, p) for r, _, p in base
                   if p is not None and not stem_match(r["target_token"], p)
                   and classify_defect(r["target_token"], p) == "diacritic_only"]
    groups = collections.OrderedDict()
    for row, pred in bucket_rows:
        groups.setdefault(taxonomy(row["target_token"], pred), []).append((row, pred))

    print(f"ruler      {RULER}  sha256 {digest[:16]}…")
    print(f"rows       {baseline['n']} usable · baseline stem_correct {baseline['stem_correct']}"
          f" = {100*baseline['stem_accuracy_of_covered']:.1f}% of covered")
    print(f"bucket     diacritic_only = {len(bucket_rows)}")
    multi = sum(1 for r, p in bucket_rows if len(diff_positions(r["target_token"], p)) > 1)
    print(f"           of which {multi} carry more than one simultaneous defect (bucket = first matching rule)")
    print("\n--- sub-rules (classified by diff structure, not by label) ---")
    print(f"  {'sub-rule':<28} {'rows':>5} {'§2be':>5} {'Δ':>3}   example")
    for name, members in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        rec = P_SUBRULES.get(name, 0)
        delta = len(members) - rec
        print(f"  {name:<28} {len(members):>5} {rec:>5} {delta:>+3}   {members[0][0]['id']} "
              f"{members[0][0]['target_token']} -> {members[0][1]}")

    classified = sum(len(v) for k, v in groups.items() if k != "unexplained")
    pct = 100 * classified / max(len(bucket_rows), 1)
    print(f"\n  classified {classified}/{len(bucket_rows)} = {pct:.1f}%  ·  "
          f"unexplained {len(groups.get('unexplained', []))}")

    print("\n--- candidate rules, measured on the frozen ruler ---")
    print(f"  {'rule':<28} {'fixed':>6} {'broken':>7} {'net':>5} {'correct':>8}  verdict")
    results = collections.OrderedDict()
    for name in RULES:
        m = measure(base, [name])
        verdict = "propose" if m["net"] > 0 else "dropped"
        results[name] = {**m, "verdict": verdict}
        star = "*" if name in PROPOSED else " "
        print(f" {star}{name:<28} {m['fixed']:>6} {m['broken']:>7} {m['net']:>+5} {m['correct']:>8}  {verdict}")
    four = measure(base, list(PROPOSED))
    print(f"  {'FOUR TOGETHER':<28} {four['fixed']:>6} {four['broken']:>7} {four['net']:>+5} "
          f"{four['correct']:>8}  = {100*four['correct']/baseline['n']:.1f}%")
    dropped = {n: results[n]["net"] for n in results if results[n]["verdict"] == "dropped"}
    print(f"\n  dropped with their numbers: {dropped or 'none'}")

    # THE SHIPPED PIPELINE. The four rules now live in src/final_surface.py behind `repairs=`, so this is
    # the pre-registered prediction (+120 rows) turned into a live regression test: if the layer ever
    # stops matching the measurement that justified it, this number moves.
    shipped = score_final_surface([
        (row["target_token"], render_triple(row["root"], row["wazn_pattern"], ci,
                                            engine=ENGINE, token=row["target_token"])[0])
        for row, ci, _p in base])
    print(f"\n  SHIPPED pipeline (repairs on): stem_correct {shipped['stem_correct']} = "
          f"{100*shipped['stem_accuracy_of_covered']:.1f}%  (pre-layer {baseline['stem_correct']}"
          f" = {100*baseline['stem_accuracy_of_covered']:.1f}%)")

    artifact = {
        "tool": "tools/diacritic_split.py",
        "engine": ENGINE,
        "ruler": str(RULER).replace("\\", "/"),
        "ruler_sha256": digest,
        "baseline": {"n": baseline["n"], "stem_correct": baseline["stem_correct"],
                     "accuracy_of_covered": round(100 * baseline["stem_accuracy_of_covered"], 2)},
        "bucket": {"name": "diacritic_only", "rows": len(bucket_rows), "classified": classified,
                   "classified_pct": round(pct, 2), "multi_defect_rows": multi},
        "subrules": {name: {"rows": len(members),
                            "recorded_in_2be": P_SUBRULES.get(name, 0),
                            "delta": len(members) - P_SUBRULES.get(name, 0),
                            "examples": [{"id": r["id"], "target_token": r["target_token"],
                                          "rendered": p, "root": r["root"], "wazn_pattern": r["wazn_pattern"],
                                          "case": r.get("case")} for r, p in members[:8]]}
                     for name, members in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))},
        "rules": results,
        "proposed": list(PROPOSED),
        "four_together": {**four, "accuracy_of_covered": round(100 * four["correct"] / baseline["n"], 2)},
        "shipped_pipeline": {"stem_correct": shipped["stem_correct"],
                             "accuracy_of_covered": round(100 * shipped["stem_correct"] / baseline["n"], 2),
                             "note": "measured with repairs=True, i.e. the layer as it ships in src/final_surface.py"},
        "dropped": dropped,
        "measured_on": "data/annotation/bench-gold.jsonl (the frozen ruler, 973 adjudicated rows)",
    }
    out = Path(args.json)
    if not out.is_absolute():
        out = root / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(f"\nwrote {out}")

    if not args.check:
        return 0

    print("\n--- --check: asserting the pre-registered numbers ---")
    problems = []
    if baseline["stem_correct"] != P_BASELINE:
        problems.append(f"baseline {baseline['stem_correct']} != {P_BASELINE}")
    if len(bucket_rows) != P_BUCKET:
        problems.append(f"bucket {len(bucket_rows)} != {P_BUCKET}")
    if pct < 90:
        problems.append(f"classified {pct:.1f}% < 90%")
    for name, (f, b) in P_RULE_FIXED_BROKEN.items():
        got = (results[name]["fixed"], results[name]["broken"])
        if got != (f, b):
            problems.append(f"{name} {got} != {(f, b)}")
    if four["correct"] != P_FOUR_TOGETHER:
        problems.append(f"four together {four['correct']} != {P_FOUR_TOGETHER}")
    if shipped["stem_correct"] != P_SHIPPED:
        problems.append(f"shipped pipeline {shipped['stem_correct']} != {P_SHIPPED} — the layer in "
                        f"src/final_surface.py no longer matches the measurement that justified it")
    # the taxonomy: asserted with a declared tolerance, because a row with several simultaneous defects has no
    # single true bucket. Its drift is printed either way, so a decomposition that quietly changes shape is
    # visible even when every bucket is inside tolerance.
    for name, rec in P_SUBRULES.items():
        got = len(groups.get(name, []))
        if abs(got - rec) > P_SUBRULE_TOLERANCE:
            problems.append(f"sub-rule {name} {got} beyond ±{P_SUBRULE_TOLERANCE} of {rec}")
    for p in problems:
        print(f"  DRIFT {p}")
    print("  OK — the split reproduces §2be exactly" if not problems else f"  {len(problems)} drift(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
