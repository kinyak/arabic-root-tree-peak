"""tanwin_probe.py — size the TANWĪN family (202 rows, the largest remaining block) on the frozen ruler
BEFORE anyone implements it.

WHY THIS EXISTS
    `tanwin_missing` (149) + `tanwin_alif_acc` (53) is the biggest failure family left on the frozen ruler —
    larger than the entire `diacritic_only` bucket was before the repair layer shipped. It was rejected once,
    at **+2.9 pp** against a ≥ +10 pp gate (§2bb), and that rejection is now STALE rather than wrong: it was
    measured before Option A (§2bd) made the token's proclitic visible to the assembly layer, and proclitic
    visibility is precisely the input a tanwīn rule needs (tanwīn is written on INDEFINITE nouns). So the
    family gets re-sized with the live input, by the same discipline that sized the repair layer — and the
    gate was **pre-registered in ACTIVE_BACKLOG.md before this file was written**, because a threshold
    chosen after seeing the number is not a threshold.

WHAT IT MEASURES
    The baseline is the SHIPPED pipeline (repairs on, 583/973 = 59.9%). It then splits the 202-row family by
    the structure of the diff, applies each candidate rule to the assembled surface, and reports rows fixed,
    rows broken and net per rule — plus the combined rule against the pre-registered gate.

WHAT IT DOES NOT DO
    It implements nothing. The rules live here as pure functions of (surface, token, case) and are applied in
    the measurement only; shipping them is a separate decision governed by a gate this tool can only report
    against. It also does not decide that tanwīn is *worth* having: it reports the number, and whether that
    number clears the gate is the whole finding.

THE PITFALL IT AVOIDS
    Reading the answer. The definiteness the rule consults comes from the TOKEN's proclitic — a legal input,
    since the model reads the token — and the case comes from the case head; the rule NEVER asks whether the
    gold string happens to carry tanwīn when deciding what to write. A rule that peeked there would score
    enormously and mean nothing. Rows that fit no named sub-rule stay in `unexplained` rather than being
    force-fitted, and the classification must reach 90% or the decomposition is wrong.

USAGE
    python tools/tanwin_probe.py [--root R] [--json PATH] [--check]
"""
from __future__ import annotations

# ATTRIBUTION SWITCH — this file measures the SURFACE pipeline, so it pins the corpus spelling resource OFF.
# The resource shipped ON at the zero-loss setting (EVIDENCE_LOG §2bn: shipped fidelity 592 -> 695 = 71.4%).
# Every number below is about the repair layer / the diff structure measured WITHOUT that input. Without this
# line the pins drift the moment the resource ships — measured, in this order: diacritic_split --check exit 1,
# tanwin_probe --check -189 -> -266, hollow_probe --check "seat_for_fail net +1 != pinned +0".
import os
os.environ["ARABIC_SPELLING_RESOURCE"] = "0"
# AND THE AFFIX PLANE (§2cn), for the same reason the resource is pinned: the plane shipped at §2ce,
# after these numbers were written, so without this line the probe measures a pipeline the pins never
# described. The plane is a separate layer with its own measurements (§2ce, §2cn).
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

from repo_root import resolve_root                                       # noqa: E402
from final_surface import (                                              # noqa: E402
    DIAC, case_int, classify_defect, is_definite, nfc, render_triple, score_final_surface,
    stem_match, strip_diac,
)

ENGINE = "v3"
RULER = Path("data") / "annotation" / "bench-gold.jsonl"
ARTIFACT = Path("dist") / "tanwin-probe.json"

# --- the pre-registered numbers (ACTIVE_BACKLOG.md, item 9; written before this tool existed) ---------
P_BASELINE = 614                 # the SHIPPED pipeline: 583 -> 592 (§2bj) -> 595 (§2cn) -> 613 (§2co) ->
                                 # 614 (§2cv, `render_v3` canonicalising the pattern). RE-PINNED, and the
                                 # VERDICT IS UNCHANGED: combined net -143 <= +50, so the family is still
                                 # DROPPED. Every move is an improved STARTING POINT, not a moved verdict —
                                 # see the note below, which now covers four re-pins instead of three.
P_FAMILY = 211                   # tanwin_missing + tanwin_alif_acc. Was 202: §2co's seat projection
                                 # repaired 9 of the family's rows outright (they were mahmūz, not tanwīn),
                                 # which is exactly the "a bucket's size is not a lever's size" effect.
P_GATE_NET = 50                  # implement ONLY if the combined rule nets >= +50 rows (+5.1 pp -> 633)
# Pinned from the first deliberate run. The gate verdict is the finding, so it is guarded like one: if a later
# change moves these numbers, --check fails rather than quietly re-deciding whether to implement. Re-pinned
# 2026-10-12 after §2bj moved the shipped baseline 583 -> 592 (nets −183 → −189, −131 → −136), 2026-10-14
# after §2cn moved it 592 -> 595 (−189 → −191, −136 → −138), and again after §2co moved it 595 -> 613
# (−191 → −196, −138 → −143) — every time because a change rewrote surfaces these rules then read. The
# VERDICT is untouched: the combined rule still misses a +50 gate by a wide margin, and `accusative_alif`
# still nets exactly its pinned +41.
P_COMBINED_NET = -143
P_RULE_NET = {"tanwin_for_indefinite": -196, "accusative_alif": 41, "combined": -143}

TANWIN = {"\u064b": "\u064e", "\u064c": "\u064f", "\u064d": "\u0650"}     # tanwin -> the single vowel
TANWIN_OF = {v: k for k, v in TANWIN.items()}                            # single vowel -> its tanwin
# The accusative's orthographic alif, as the FROZEN RULER writes it: the tanwin mark comes FIRST, then the
# alif (`064B 0627`). Measured on the gold — 62 rows use that order and **zero** use the reverse — and it
# matters, because the alif is a base letter and Unicode cannot reorder it after a combining mark, so the two
# spellings are different strings and only one of them can match. Emitting the wrong one costs every row.
ALIF_ACC = ("\u064b\u0627", "\u0627\u064b")
UNUSABLE = {"", "ABSTAIN", "NONE", "NA", "#", None}


def usable(row) -> bool:
    if row.get("root") in UNUSABLE or row.get("wazn_pattern") in UNUSABLE:
        return False
    return 2 <= len([c for c in str(row["root"]) if c != "."]) <= 5


def last_mark(surface: str) -> tuple[int, str] | None:
    """(index, mark) of the final diacritic in the string, or None."""
    for i in range(len(surface) - 1, -1, -1):
        if DIAC.match(surface[i]):
            return i, surface[i]
    return None


def classify_tanwin(gold: str, pred: str) -> str:
    """Name the tanwīn sub-rule, from the diff structure alone.

    `accusative_alif_missing` — the gold writes the accusative tanwīn with its orthographic alif (`ـًا`)
    and the surface does not. Checked FIRST, because that alif is part of the accusative's tanwīn itself:
    the surface may end in a bare fatha, in which case both the alif and the doubling are missing.
    `tanwin_for_single_vowel` — the gold carries tanwīn where the surface carries the bare case vowel.
    `unexplained` — anything else, held out rather than force-fitted.
    """
    g = nfc(gold)
    if not any(c in TANWIN for c in g):
        return "unexplained"
    if any(sig in g for sig in ALIF_ACC) and not any(sig in nfc(pred) for sig in ALIF_ACC):
        return "accusative_alif_missing"
    lm = last_mark(pred)
    if lm and lm[1] in TANWIN_OF:
        return "tanwin_for_single_vowel"
    if lm and lm[1] == "\u064b":
        return "tanwin_present_but_not_alif_shaped"
    return "unexplained"


# --- candidate rules (pure; surface + token + case only) ----------------------------------------------

def rule_tanwin_for_indefinite(surface: str, token: str, case: int | None) -> str:
    """`صُورَةِ` -> `صُورَةٍ`: an indefinite noun's final case vowel is written doubled.

    Gated on the token being INDEFINITE, because tanwīn is the indefiniteness marker: a definite noun keeps
    the single vowel, so the rule cannot fire on a token carrying a proclitic `al-`.
    """
    if is_definite(token):
        return surface
    lm = last_mark(surface)
    if not lm or lm[1] not in TANWIN_OF:
        return surface
    i, mark = lm
    return surface[:i] + TANWIN_OF[mark] + surface[i + 1:]


def rule_accusative_alif(surface: str, token: str, case: int | None) -> str:
    """`مَهْرًا` — the accusative tanwīn is written WITH an orthographic alif.

    Handles the case where the renderer wrote a bare fatha (both the alif and the doubling are missing), and
    refuses after `ة` (مَرْأَةً) and after a hamza that follows the alif (مَسَاءً) — the alif is not written
    there, and inserting one is exactly what turns this from a rule into a regression. Gated on the token
    being indefinite, and on the case being accusative.
    """
    if case != 1 or is_definite(token):
        return surface
    lm = last_mark(surface)
    if not lm:
        return surface
    i, mark = lm
    if mark not in ("\u064e", "\u064b"):            # not the accusative's own ending
        return surface
    prev = surface[i - 1] if i else ""
    if prev in "\u0629\u0621" or prev == "\u0627":  # مَرْأَةً / مَسَاءً / the alif is already written
        return surface[:i] + "\u064b" + surface[i + 1:]
    return surface[:i] + "\u064b\u0627" + surface[i + 1:]      # tanwin THEN alif — the ruler's order


def rule_combined(surface: str, token: str, case: int | None) -> str:
    """The alif first, then the doubling — the order the two rules were sized in."""
    out = rule_accusative_alif(surface, token, case)
    return rule_tanwin_for_indefinite(out, token, case)


RULES = {
    "tanwin_for_indefinite": rule_tanwin_for_indefinite,
    "accusative_alif": rule_accusative_alif,
    "combined": rule_combined,
}


def measure(base, rule_names):
    fixed = broken = 0
    pairs = []
    for row, ci, pred in base:
        out = pred
        if out is not None:
            for name in rule_names:
                out = RULES[name](out, row["target_token"], ci)
        pairs.append((row["target_token"], out))
        was = stem_match(row["target_token"], pred) if pred is not None else False
        now = stem_match(row["target_token"], out) if out is not None else False
        if now and not was:
            fixed += 1
        if was and not now:
            broken += 1
    return {"fixed": fixed, "broken": broken, "net": fixed - broken,
            "correct": score_final_surface(pairs)["stem_correct"]}


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

    base = []
    for row in usable_rows:
        ci = case_int(row.get("case"))
        surf, _why = render_triple(row["root"], row["wazn_pattern"], ci, engine=ENGINE,
                                   token=row["target_token"])
        base.append((row, ci, surf))

    baseline = score_final_surface([(r["target_token"], p) for r, _, p in base])
    family = [(r, ci, p) for r, ci, p in base
              if p is not None and not stem_match(r["target_token"], p)
              and classify_defect(r["target_token"], p) in ("tanwin_missing", "tanwin_alif_acc")]
    groups = collections.OrderedDict()
    for row, _ci, pred in family:
        groups.setdefault(classify_tanwin(row["target_token"], pred), []).append((row, pred))

    print(f"ruler    {RULER}  sha256 {digest[:16]}…")
    print(f"baseline SHIPPED pipeline: stem_correct {baseline['stem_correct']} = "
          f"{100*baseline['stem_accuracy_of_covered']:.1f}%")
    print(f"family   tanwīn = {len(family)} rows (pre-registered: {P_FAMILY})")
    print("\n--- sub-rules ---")
    for name, members in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        print(f"  {name:<28} {len(members):>4}   e.g. {members[0][0]['id']} "
              f"{members[0][0]['target_token']} -> {members[0][1]}")
    classified = sum(len(v) for k, v in groups.items() if k != "unexplained")
    pct = 100 * classified / max(len(family), 1)
    print(f"  classified {classified}/{len(family)} = {pct:.1f}%  ·  "
          f"unexplained {len(groups.get('unexplained', []))}")

    print("\n--- candidate rules on the frozen ruler ---")
    results = collections.OrderedDict()
    for name in RULES:
        m = measure(base, [name])
        results[name] = m
        print(f"  {name:<24} fixed={m['fixed']:>4} broken={m['broken']:>4} net={m['net']:>+4} "
              f"correct={m['correct']:>4} = {100*m['correct']/baseline['n']:.1f}%")

    comb = results["combined"]
    clears = comb["net"] >= P_GATE_NET
    print(f"\n  PRE-REGISTERED GATE: combined net >= {P_GATE_NET} rows (+5.1 pp → 633) — "
          f"measured net {comb['net']:+} → {'CLEARS, implement' if clears else 'MISSES, record as dropped'}")
    print(f"  (the family is {len(family)} rows; the combined rule wins {comb['fixed']} and loses {comb['broken']})")

    artifact = {
        "tool": "tools/tanwin_probe.py", "engine": ENGINE, "ruler": str(RULER).replace("\\", "/"),
        "ruler_sha256": digest, "baseline": {"n": baseline["n"], "stem_correct": baseline["stem_correct"],
                                            "accuracy_of_covered": round(100*baseline["stem_accuracy_of_covered"], 2)},
        "family": {"name": "tanwin_missing + tanwin_alif_acc", "rows": len(family),
                   "pre_registered": P_FAMILY, "classified": classified, "classified_pct": round(pct, 2)},
        "subrules": {n: {"rows": len(m), "examples": [
            {"id": r["id"], "target_token": r["target_token"], "rendered": p, "root": r["root"],
             "wazn_pattern": r["wazn_pattern"], "case": r.get("case")} for r, p in m[:8]]}
            for n, m in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))},
        "rules": results,
        "gate": {"pre_registered_net": P_GATE_NET, "measured_net": comb["net"], "clears": clears},
        "measured_on": "data/annotation/bench-gold.jsonl (the frozen ruler, 973 adjudicated rows)",
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
    if baseline["stem_correct"] != P_BASELINE:
        problems.append(f"baseline {baseline['stem_correct']} != {P_BASELINE}")
    if len(family) != P_FAMILY:
        problems.append(f"family {len(family)} != {P_FAMILY}")
    if pct < 90:
        problems.append(f"classified {pct:.1f}% < 90%")
    if P_COMBINED_NET is not None and comb["net"] != P_COMBINED_NET:
        problems.append(f"combined net {comb['net']:+} != pinned {P_COMBINED_NET:+}")
    for name, pinned in P_RULE_NET.items():
        if results[name]["net"] != pinned:
            problems.append(f"{name} net {results[name]['net']:+} != pinned {pinned:+}")
    if clears:
        problems.append("the gate now CLEARS — that is a change of verdict, not a drift; re-open the decision")
    for p in problems:
        print(f"  DRIFT {p}")
    print("  OK — the probe reproduces its recorded numbers" if not problems else f"  {len(problems)} drift(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
