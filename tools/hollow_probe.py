"""hollow_probe.py — size the hollow-class failures (56) on the frozen ruler, against the pre-registered gate.

WHY THIS EXISTS
    Hollow roots (r2 in {w,y}) are the last class-specific lever left: **44.0%, 56 failures**, and the item the
    original roadmap named as Phase-1 step 3 ("the renderer confuses open-syllable contraction — qala — with
    closed-syllable apocope — qultu —") and never sized. The gate is pre-registered in ACTIVE_BACKLOG.md item 9
    **before this file was written**: the hollow class must reach **>= 80%** (>= +36 rows), no other class may
    regress, and any sub-rule with net <= 0 is dropped with its number.

WHAT THE DUMP SHOWED (and why the rules below are the rules below)
    43 of the 56 failures are LETTER-level, and the two largest shapes are OPPOSITE errors on the same radical:
      * a MISSING HAMZA SEAT where the human writes `ائ` — قَائِل for قَال (pattern `1َا2ِ3`), رَائِغ for رَاغ,
        صَائِم for صَام. The renderer contracts the radical into a mater; the human gives it a seat.
      * a RETAINED MATER where the human contracts — إشَارَة for إشَوَارَة (`إِ1َ2َا3َة`). Here the renderer keeps
        the radical as a mater and the human elides it into the long vowel.
    A blanket "hollow rule" cannot fix both, which is exactly the confusion the roadmap described.

WHAT IT DOES NOT DO
    It implements nothing. Both candidate rules are pure functions of (surface, pattern) — the wazān is a
    renderer INPUT — and neither reads the gold token. Rows that fit no named sub-rule stay `unexplained`.

USAGE
    python tools/hollow_probe.py [--root R] [--json PATH] [--check]
"""
from __future__ import annotations

# ATTRIBUTION SWITCH — this file measures the SURFACE pipeline, so it pins the corpus spelling resource OFF.
# The resource shipped ON at the zero-loss setting (EVIDENCE_LOG §2bn: shipped fidelity 592 -> 695 = 71.4%).
# Every number below is about the repair layer / the diff structure measured WITHOUT that input. Without this
# line the pins drift the moment the resource ships — measured, in this order: diacritic_split --check exit 1,
# tanwin_probe --check -189 -> -266, hollow_probe --check "seat_for_fail net +1 != pinned +0".
import os
os.environ["ARABIC_SPELLING_RESOURCE"] = "0"


import argparse
import collections
import hashlib
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

_TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(_TOOLS))
sys.path.insert(0, str(_TOOLS.parent / "src"))

from repo_root import resolve_root                                    # noqa: E402
from diacritic_split import usable                                    # noqa: E402
from eval_harness import root_class                                   # noqa: E402
from final_surface import (                                           # noqa: E402
    KASRA, case_int, classify_defect, render_triple, score_final_surface, stem_match, strip_diac,
)

ENGINE = "v3"
RULER = Path("data") / "annotation" / "bench-gold.jsonl"
ARTIFACT = Path("dist") / "hollow-probe.json"

P_BASELINE_OVERALL = 614        # shipped pipeline. RE-PINNED 2026-10-14 (§2cv): 613 -> 614, and the VERDICT
                                # IS UNCHANGED (seat_for_fail +0, contract_mater -2, BOTH -2, and the >= 80%
                                # gate is still MISSED). Mechanism: `render_v3` now canonicalises the pattern
                                # via `canonicalize_mater_vowels`, which repairs الْأَوْجَهَ (assimilated +1)
                                # without touching any other class — measured fixed 1 / broken 0 vs HEAD.
                                # History: 592 (§2bj) -> 595 (§2cn) -> 613 (§2co) -> 614 (§2cv).
P_HOLLOW_ROWS = 100
P_HOLLOW_BASE = 47              # 47/100 — was 44 before §2co, a CONSEQUENCE of the seat projection, not
                                # a change to what this probe decides
P_GATE_ROWS = 80                # the pre-registered gate: hollow >= 80%
# Pinned from the deliberate run. The MISS is the finding, so it is guarded like one: if the class ever reaches
# the gate, --check fails and says so, rather than the miss quietly becoming a silent "not yet".
P_RULE_NET = {"seat_for_fail": 0, "contract_mater": -2, "both": -2}
P_HOLLOW_AFTER_BOTH = 46        # was 43: §2co's seat projection repairs 3 of the failures, so the
                                # dropped rules' combination starts higher. STILL FAR BELOW the >= 80 gate,
                                # so the verdict (dropped) is unchanged.
P_HOLLOW_FAILURES = 53          # was 56 — the same 3 rows. This used to be a bare literal in the check
                                # below, which is how a pin stops being visible; it is named now.

SEAT = "\u0626"                 # ئ
ALIF = "\u0627"                 # ا
FAIL_PAT = re.compile(r"\u0627" r"2[\u0650\u064e]")     # ...alif, slot 2, its vowel: the fa'il shape


def classify_hollow(gold: str, pred: str, pattern: str) -> str:
    """Name the hollow sub-rule from the diff structure, or `unexplained`.

    Letter-level first (the radical itself), because that is where 43 of the 56 failures are: whether the
    radical got a seat, kept a mater, or lost one.
    """
    g, p = strip_diac(gold), strip_diac(pred)
    if g == p:
        return {"tanwin_missing": "tanwin_missing", "tanwin_alif_acc": "tanwin_alif_acc"}.get(
            classify_defect(gold, pred), "marks_only_other")
    if SEAT in g and SEAT not in p and is_fail_pattern(pattern):
        return "seat_missing_for_fail"
    if ALIF in g and len(g) < len(p):
        return "mater_retained_where_contracted"
    if "\u0623" in g or "\u0622" in g:
        return "seat_alif_other"
    return "unexplained"


def is_fail_pattern(pattern: str) -> bool:
    """Does the wazān ask for the `فَاعِل` shape — a long alif, then radical 2 with its own vowel?"""
    return bool(FAIL_PAT.search(pattern or ""))


def rule_seat_for_fail(surface: str, pattern: str) -> str:
    """`قَالَ` -> `قَائِلَ`: a hollow r2 under `فَاعِل` is written with a hamza seat, not a mater.

    POSITION-AWARE on purpose. The first version inserted a seat after the first alif it found, fired on
    hundreds of rows and measured **−89** — that measured the rule, not the idea. The renderer's *contracted*
    output for this pattern is exactly three letters with the alif in the middle (قَالَ, رَاغُ, صَامُ), so the
    rule fires only on that shape: the renderer has to have actually contracted before a seat is re-inserted.
    """
    if not is_fail_pattern(pattern) or SEAT in surface:
        return surface
    sk = strip_diac(surface)
    if len(sk) != 3 or sk[1] != ALIF:
        return surface                       # not the contracted فَاعِل shape: leave it alone
    i = surface.find(ALIF)
    return surface[:i + 1] + SEAT + KASRA + surface[i + 1:]


def rule_contract_mater(surface: str, pattern: str) -> str:
    """`إشَوَارَة` -> `إشَارَة`: where the pattern contracts, the radical is elided into the long vowel.

    The retained radical can carry a vowel of its own before the alif (`...َ و َ ا...` in إشَوَارَة) or not, so
    both spellings are handled; the first version only matched the bare one and therefore never fired.
    """
    if "2" not in (pattern or "") or ALIF not in (pattern or ""):
        return surface
    for mater, mark in (("\u0648", "\u064e"), ("\u064a", "\u0650"), ("\u064a", "\u064e")):
        for variant in (mark + mater + "\u064e" + ALIF, mark + mater + ALIF):
            if variant in surface:
                surface = surface.replace(variant, ALIF)
    return surface


RULES = {"seat_for_fail": rule_seat_for_fail, "contract_mater": rule_contract_mater}


def measure(base, names):
    fixed = broken = 0
    pairs = []
    for row, ci, pred in base:
        out = pred
        if out is not None:
            for n in names:
                out = RULES[n](out, row["wazn_pattern"])
        pairs.append((row["target_token"], out))
        was = stem_match(row["target_token"], pred) if pred is not None else False
        now = stem_match(row["target_token"], out) if out is not None else False
        if now and not was:
            fixed += 1
        if was and not now:
            broken += 1
    s = score_final_surface(pairs)
    return {"fixed": fixed, "broken": broken, "net": fixed - broken, "correct": s["stem_correct"], "pairs": pairs}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root")
    ap.add_argument("--json", default=str(ARTIFACT))
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    root = resolve_root(args.root)

    raw = (root / RULER).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    rows = [json.loads(l) for l in raw.decode("utf-8").splitlines() if l.strip()]
    usable_rows = sorted((r for r in rows if usable(r)), key=lambda r: r.get("id") or "")

    base, hollow_ids = [], set()
    for row in usable_rows:
        ci = case_int(row.get("case"))
        surf, _ = render_triple(row["root"], row["wazn_pattern"], ci, engine=ENGINE, token=row["target_token"])
        base.append((row, ci, surf))
        if root_class(row.get("root")) == "hollow":
            hollow_ids.add(row["id"])

    baseline = score_final_surface([(r["target_token"], p) for r, _, p in base])
    hollow_base = sum(1 for r, _, p in base if r["id"] in hollow_ids and p is not None
                      and stem_match(r["target_token"], p))

    print(f"ruler    {RULER}  sha256 {digest[:16]}…")
    print(f"baseline overall {baseline['stem_correct']}/{baseline['n']} = "
          f"{100*baseline['stem_accuracy_of_covered']:.1f}%   hollow {hollow_base}/{len(hollow_ids)} = "
          f"{100*hollow_base/len(hollow_ids):.1f}%")

    groups = collections.OrderedDict()
    for row, ci, pred in base:
        if row["id"] not in hollow_ids or pred is None or stem_match(row["target_token"], pred):
            continue
        groups.setdefault(classify_hollow(row["target_token"], pred, row["wazn_pattern"]), []).append((row, pred))
    fails = sum(len(v) for v in groups.values())
    print(f"\nhollow failures {fails}   (pre-registered hollow rows {P_HOLLOW_ROWS})")
    for name, members in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        print(f"  {name:<34} {len(members):>3}   e.g. {members[0][0]['id']} "
              f"{members[0][0]['target_token']} -> {members[0][1]}")
    classified = sum(len(v) for k, v in groups.items() if k != "unexplained")
    pct = 100 * classified / max(fails, 1)
    print(f"  classified {classified}/{fails} = {pct:.1f}%  ·  unexplained {len(groups.get('unexplained', []))}")

    print("\n--- candidate rules (measured on the whole ruler) ---")
    results = collections.OrderedDict()
    for name in RULES:
        m = measure(base, [name])
        results[name] = m
        hh = sum(1 for r, _, p in base if r["id"] in hollow_ids and p is not None
                 and stem_match(r["target_token"], p))
        pairs_map = dict(m["pairs"])
        hh_new = sum(1 for r, _, p in base if r["id"] in hollow_ids
                     and stem_match(r["target_token"], pairs_map.get(r["target_token"])))
        print(f"  {name:<20} fixed={m['fixed']:>3} broken={m['broken']:>3} net={m['net']:>+4} "
              f"overall={m['correct']} hollow={hh_new}/{len(hollow_ids)} = "
              f"{100*hh_new/len(hollow_ids):.1f}%   (hollow was {hh})")

    combo_hollow = None
    for combo_name, combo_rules in (("BOTH", ["seat_for_fail", "contract_mater"]),):
        m = measure(base, combo_rules)
        pm = dict(m["pairs"])
        hh_new = sum(1 for r, _, p in base if r["id"] in hollow_ids
                     and stem_match(r["target_token"], pm.get(r["target_token"])))
        combo_hollow = hh_new
        results[combo_name.lower()] = m
        print(f"  {combo_name:<20} fixed={m['fixed']:>3} broken={m['broken']:>3} net={m['net']:>+4} "
              f"overall={m['correct']} hollow={hh_new}/{len(hollow_ids)} = {100*hh_new/len(hollow_ids):.1f}%")
        clears = hh_new >= P_GATE_ROWS and m["broken"] == 0
        print(f"\n  PRE-REGISTERED GATE: hollow >= {P_GATE_ROWS}/{len(hollow_ids)} with no class regressing — "
              f"measured {hh_new} → {'CLEARS, implement' if clears else 'MISSES, record the miss with its number'}")

    artifact = {
        "tool": "tools/hollow_probe.py", "engine": ENGINE, "ruler": str(RULER).replace("\\", "/"),
        "ruler_sha256": digest,
        "baseline": {"overall": baseline["stem_correct"], "n": baseline["n"],
                     "hollow": hollow_base, "hollow_n": len(hollow_ids)},
        "failures": {"n": fails, "classified": classified, "classified_pct": round(pct, 2)},
        "subrules": {n: {"rows": len(m), "examples": [
            {"id": r["id"], "target_token": r["target_token"], "rendered": p, "root": r["root"],
             "wazn_pattern": r["wazn_pattern"], "case": r.get("case")} for r, p in m[:8]]}
            for n, m in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))},
        "rules": {k: {kk: vv for kk, vv in v.items() if kk != "pairs"} for k, v in results.items()},
        "gate": {"pre_registered_hollow": P_GATE_ROWS, "measured_hollow": combo_hollow},
    }
    out = Path(args.json)
    if not out.is_absolute():
        out = root / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {out}")

    if not args.check:
        return 0
    print("\n--- --check ---")
    problems = []
    if baseline["stem_correct"] != P_BASELINE_OVERALL:
        problems.append(f"overall baseline {baseline['stem_correct']} != {P_BASELINE_OVERALL}")
    if len(hollow_ids) != P_HOLLOW_ROWS:
        problems.append(f"hollow rows {len(hollow_ids)} != {P_HOLLOW_ROWS}")
    if hollow_base != P_HOLLOW_BASE:
        problems.append(f"hollow baseline {hollow_base} != {P_HOLLOW_BASE}")
    if fails != P_HOLLOW_FAILURES:
        problems.append(f"hollow failures {fails} != {P_HOLLOW_FAILURES}")
    for name, pinned in P_RULE_NET.items():
        got = results[name]["net"]
        if got != pinned:
            problems.append(f"{name} net {got:+} != pinned {pinned:+}")
    if combo_hollow != P_HOLLOW_AFTER_BOTH:
        problems.append(f"hollow after BOTH {combo_hollow} != pinned {P_HOLLOW_AFTER_BOTH}")
    if combo_hollow >= P_GATE_ROWS:
        problems.append("the hollow class now REACHES the gate — that is a change of verdict, not a drift; "
                        "re-open the decision instead of letting it pass")
    for p in problems:
        print(f"  DRIFT {p}")
    print("  OK — the probe reproduces its recorded numbers" if not problems else f"  {len(problems)} drift(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
