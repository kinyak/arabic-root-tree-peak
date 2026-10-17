"""The renderer against the FROZEN item-1 benchmark — the ruler the paper must quote.

WHY THIS TOOL EXISTS
    Until now the renderer's fidelity was only ever measured on the 300-row legacy
    ``gold-tashkeela-300.jsonl`` (max 278 usable triples) — a set that ACTIVE_BACKLOG.md
    item 1 describes as "small, stratified toward weak/doubled surfaces, and whose *case*
    reference is CALIMA-derived". The item-1 benchmark
    (``data/annotation/bench-gold.jsonl``: 1000 rows, two independent annotators,
    per-row adjudication, 650 test / 350 calibration) is now the official reference.
    The renderer had NEVER been scored against it. This tool does that, and nothing else.

WHAT IT REPORTS
    ``coverage`` and ``fidelity`` as a PAIR, per root class, never merged
    (ACTIVE_BACKLOG "standing constraints"; RED LINE: a coverage without a fidelity is
    uninterpretable). Coverage here is ~100% BY CONSTRUCTION on the rows that carry a
    usable triple, because the human supplies the root and the pattern — so the open
    question is fidelity, and abstentions are reported with their REASON.

    The tanwīn probe answers the question §2s.9 item 2 left open: "the gold writes tanwīn
    in some rows and a plain vowel in others at the same case; test whether definiteness is
    recoverable from the pattern before writing the rule." It reports, per (pattern, case)
    cell, whether tanwīn presence is CONSTANT (rule-writable from the triple) or MIXED
    (an input is missing and ``apply_case`` cannot be blamed).

PITFALL THIS TOOL AVOIDS
    The reference surface is a *token*; the renderer produces a *stem*. ``stem_match``
    (final_surface) already carries the clitic plane, so a clitic-bearing reference such as
    بِالْقَرَائِنِ is not charged against the renderer for a plane it was not asked to
    produce. Do not replace that call with string equality — it moves the number by ~30 pp
    (§2s.8b measured exactly that bug).

USAGE
    python tools/renderer_bench_audit.py                    # engine v3, all rows
    python tools/renderer_bench_audit.py --engine v1 --json dist/audit/x.json
    python tools/renderer_bench_audit.py --split test       # 650-row reporting split
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))          # tools/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from repo_root import resolve_root                                  # noqa: E402

ROOT = resolve_root()
sys.path.insert(0, str(ROOT / "src"))

from final_surface import render_triple, score_final_surface, TAN, DIAC, strip_diac  # noqa: E402
from eval_harness import root_class                                                  # noqa: E402
from renderer import CASE_VOWEL                                                      # noqa: E402

CASE_INT = {v: k for k, v in CASE_VOWEL.items()}          # "ُ" -> 0
CASE_STR = {"NOM": 0, "ACC": 1, "GEN": 2}
UNUSABLE = {"", "ABSTAIN", "NONE", "NA", "#", None}
DEF_PRO = ("وال", "فال", "بال", "كال", "ال")   # the ال- family only — و/ف/ب/ك/ل/س are not definiteness


def _is_definite(token: str) -> bool:
    """Definiteness off the TOKEN's own skeleton. An ORACLE input (§2s.8d): the pipeline has
    the token, but `(root, wazān, case)` does not carry definiteness."""
    sk = strip_diac(token) or ""
    return any(sk.startswith(p) and len(sk) > len(p) for p in DEF_PRO)


def load_gold(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.open(encoding="utf-8") if l.strip()]


def case_int(raw) -> int | None:
    if isinstance(raw, int):
        return raw
    if not isinstance(raw, str):
        return None
    raw = raw.strip()
    if raw in CASE_STR:
        return CASE_STR[raw]
    return CASE_INT.get(raw)


def usable_row(r: dict) -> bool:
    if r.get("root") in UNUSABLE or r.get("wazn_pattern") in UNUSABLE:
        return False
    # a root must be dots-separated radicals or a bare radical string
    rads = [c for c in str(r["root"]) if c != "."]
    return 2 <= len(rads) <= 5


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", default=str(ROOT / "data" / "annotation" / "bench-gold.jsonl"))
    ap.add_argument("--engine", default="v3", choices=("v1", "v2", "v3"))
    ap.add_argument("--split", default="all", choices=("all", "test", "calibration"),
                    help="the freeze records test=650 / calibration=350 by row ORDER "
                         "(first 650 / last 350); reported separately, never pooled for a claim")
    ap.add_argument("--json", default=None, help="write the full report to this path")
    args = ap.parse_args()

    rows = load_gold(Path(args.gold))
    if args.split == "test":
        rows = rows[:650]
    elif args.split == "calibration":
        rows = rows[650:]

    pairs, by_class, reasons, tanwin_rows = [], collections.defaultdict(list), \
        collections.Counter(), []
    n_all = len(rows)
    for r in rows:
        if not usable_row(r):
            continue
        ci = case_int(r.get("case"))
        pred, why = render_triple(r["root"], r["wazn_pattern"], ci, engine=args.engine,
                                  token=r["target_token"])
        cls = root_class(str(r["root"]))
        pairs.append((r["target_token"], pred, why))
        by_class[cls].append((r["target_token"], pred, why))
        if pred is None:
            reasons[why] += 1
        if any(ch in TAN for ch in str(r["target_token"])):
            tanwin_rows.append((r, pred, ci))

    overall = score_final_surface(pairs)
    print("=" * 88)
    print(f"RENDERER (engine {args.engine}) vs the FROZEN item-1 BENCHMARK "
          f"[{args.split}] — data/annotation/bench-gold.jsonl")
    print("=" * 88)
    print(f"rows {n_all} · usable triples {overall['n']} "
          f"({100*overall['n']/max(n_all,1):.1f}%) · abstentions {overall['abstain']}")
    print()
    print(f"{'metric':<40} {'count':>7} {'rate':>8}")
    print(f"{'coverage (of usable rows)':<40} {overall['covered']:>7} "
          f"{100*overall['coverage']:>7.1f}%")
    print(f"{'FIDELITY stem_accuracy_of_covered':<40} {overall['stem_correct']:>7} "
          f"{100*overall['stem_accuracy_of_covered']:>7.1f}%")
    print(f"{'YIELD stem_yield (abstain = miss)':<40} {overall['stem_correct']:>7} "
          f"{100*overall['stem_yield']:>7.1f}%")
    print(f"{'token exact (NFC)':<40} {overall['token_exact']:>7} "
          f"{100*overall['token_exact_yield']:>7.1f}%")
    print(f"{'skeleton yield':<40} {overall['skeleton']:>7} "
          f"{100*overall['skeleton_yield']:>7.1f}%")

    print()
    print("-" * 88)
    print("BY ROOT CLASS — coverage and fidelity as a PAIR (never merged)")
    print("-" * 88)
    print(f"{'class':<16} {'n':>5} {'cover':>7} {'fidelity':>9} {'yield':>7} {'skeleton':>9}")
    per_class = {}
    for cls in sorted(by_class, key=lambda c: -len(by_class[c])):
        m = score_final_surface(by_class[cls])
        per_class[cls] = m
        print(f"{cls:<16} {m['n']:>5} {100*m['coverage']:>6.1f}% "
              f"{100*m['stem_accuracy_of_covered']:>8.1f}% {100*m['stem_yield']:>6.1f}% "
              f"{100*m['skeleton_yield']:>8.1f}%")

    print()
    print("-" * 88)
    print("DEFECT TAXONOMY (first reconciling rule; count = UPPER BOUND on that rule)")
    print("-" * 88)
    for b, c in list(overall["defect_buckets"].items())[:14]:
        print(f"  {b:<28} {c:>4}  {100*c/max(overall['n'],1):>5.1f}%")
    if reasons:
        print(f"  abstain reasons: {dict(reasons)}")

    # ---- the tanwin question (§2s.9 item 2). CORRECTED 2026-10-12 — see EVIDENCE_LOG §2bb.
    # The FIRST version of this probe iterated only over rows whose gold token carries tanwin,
    # so its "plain" bucket could never increment and every cell was trivially "constant".
    # It reported "43 cells, 0 mixed" as a finding; that was an artifact of the loop, not a
    # property of the data. The corrected probe below groups EVERY usable row by cell.
    print()
    print("-" * 88)
    print("TANWIN PROBE — is tanwin a function of the (pattern, case) cell?")
    print("-" * 88)
    cell2 = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        if not usable_row(r):
            continue
        cell2[(r["wazn_pattern"], case_int(r.get("case")))][
            0 if any(ch in TAN for ch in str(r["target_token"])) else 1] += 1
    multi2 = {k: v for k, v in cell2.items() if sum(v) >= 2}
    mixed2 = {k: v for k, v in multi2.items() if v[0] and v[1]}
    print(f"usable rows                          : {overall['n']}")
    print(f"distinct (pattern, case) cells        : {len(cell2)}")
    print(f"  cells with >=2 rows                 : {len(multi2)}")
    print(f"    of those tanwin-only              : "
          f"{sum(1 for v in multi2.values() if v[0] and not v[1])}")
    print(f"    of those plain-only               : "
          f"{sum(1 for v in multi2.values() if v[1] and not v[0])}")
    print(f"    of those MIXED (both verdicts)     : {len(mixed2)}  "
          f"<- the triple does NOT decide these")
    print(f"  rows lying inside MIXED cells       : {sum(sum(v) for v in mixed2.values())}")
    d_tan = sum(1 for r in rows if usable_row(r) and _is_definite(r["target_token"])
                and any(ch in TAN for ch in str(r["target_token"])))
    d_all = sum(1 for r in rows if usable_row(r) and _is_definite(r["target_token"]))
    i_tan = sum(1 for r in rows if usable_row(r) and not _is_definite(r["target_token"])
                and any(ch in TAN for ch in str(r["target_token"])))
    i_all = sum(1 for r in rows if usable_row(r) and not _is_definite(r["target_token"]))
    print(f"definite tokens carrying tanwin       : {d_tan} / {d_all}")
    print(f"indefinite tokens carrying tanwin     : {i_tan} / {i_all}  "
          f"({100*i_tan/max(i_all,1):.1f}%)  <- necessary, not sufficient")
    got_tan = sum(1 for r in rows if usable_row(r)
                  and any(ch in TAN for ch in str(r["target_token"])))
    print(f"renderer output carrying tanwin       : 0 / {got_tan} (apply_case cannot emit it)")

    report = {"engine": args.engine, "split": args.split, "gold": args.gold,
              "overall": overall, "by_root_class": per_class,
              "tanwin": {"cells": len(cell2), "cells_ge2": len(multi2),
                         "cells_mixed": len(mixed2),
                         "rows_in_mixed_cells": sum(sum(v) for v in mixed2.values()),
                         "definite_with_tanwin": f"{d_tan}/{d_all}",
                         "indefinite_with_tanwin": f"{i_tan}/{i_all}"},
              "abstain_reasons": dict(reasons)}
    if args.json:
        p = Path(args.json)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nreport written: {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
