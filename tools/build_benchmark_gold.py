"""build_benchmark_gold.py — from two independent returns to the adjudicated benchmark.

WHY THIS EXISTS
    `src/build_annotation_gold.py` turns ONE filled sheet into gold, and it knows the old 7-column
    schema (no `alternatives`). The benchmark is different in kind: two independent annotators, a
    required per-row adjudication rationale, a ninth column, and a freeze record that promises the
    benchmark "ships with its own re-derivable counts". None of that existed.

TWO MODES, DELIBERATELY SEPARATED
    --emit-disputes   A + B -> bench-disputes.csv : ONLY the rows where the two annotators differ,
                      with both answers side by side and EMPTY columns for the PI. The agreement
                      numbers are computed before this file is written (freeze v2 section 5.4) and
                      are not affected by adjudication.
    --ingest          the PI-filled disputes file -> bench-gold.jsonl + bench-gold.meta.json

    The separation is the point: it makes "adjudicated only after both files were frozen" a property
    of the workflow rather than a promise in a document, and it forces the rationale to exist in a
    file instead of in someone's memory.

WHAT THE INGEST REFUSES (fail closed, never warn)
    * a disputed row with an EMPTY rationale            -> exit 3 (freeze v2 section 9.3a: the
      rationale is part of the artifact)
    * an adjudicated value that is not legal             -> exit 3 (root/wazan/case/alternatives
      validated with the same code the packet's validator uses)
    * a disputes file whose ids do not match the A/B pair -> exit 4

WHAT IT PRODUCES BEYOND THE GOLD
    * per-field provenance: how many rows were agreed vs adjudicated
    * the CANONICAL WAZAN CLASSES, derived from the adjudicated data itself (exact -> case-vowel
      stripped -> diacritic stripped), with the equivalence-class table. This is the "canonical
      label space" item 1 requires: derived from adjudication, never invented modelling-side.
    * the HUMAN CEILING: case raw agreement between A and B before adjudication -- the number the
      model's case score must be reported against.
    * re-derivable counts: rows, strata realisation, split sizes, abstain and fill rates.

USAGE
    python tools/build_benchmark_gold.py --emit-disputes
    python tools/build_benchmark_gold.py --ingest data/annotation/bench-disputes.csv
CPU only.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_root import resolve_root  # noqa: E402
import iaa_report as I  # noqa: E402

ROOT = resolve_root()
ANN = ROOT / "data/annotation"
A_CSV, B_CSV, KEY_CSV = ANN / "bench-annotator-A.csv", ANN / "bench-annotator-B.csv", ANN / "bench-KEY.csv"
DISPUTES, GOLD, META = ANN / "bench-disputes.csv", ANN / "bench-gold.jsonl", ANN / "bench-gold.meta.json"

# fields a dispute can concern; `alternatives` is compared as a canonical SET (order-independent)
FIELDS = ("root", "wazn_pattern", "case", "alternatives")
NORM = {"root": I.norm_root, "wazn_pattern": I.norm_wazn,
        "case": I.norm_case, "alternatives": lambda v: I.parse_alternatives(v)[0]}


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read(p: Path):
    with p.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def emit_disputes() -> int:
    A, B = read(A_CSV), read(B_CSV)
    if [r["id"] for r in A] != [r["id"] for r in B]:
        print("  REFUSING: A and B do not carry the same rows in the same order.")
        return 4

    disputed = []
    counts = collections.Counter()
    for ra, rb in zip(A, B):
        diff = [f for f in FIELDS if NORM[f](ra[f]) != NORM[f](rb[f])]
        for f in diff:
            counts[f] += 1
        if diff:
            disputed.append((ra, rb, diff))

    # the human ceiling has to be measured BEFORE adjudication and recorded here
    case_pairs = [(I.norm_case(a["case"]), I.norm_case(b["case"])) for a, b in zip(A, B)]
    case_po = sum(1 for x, y in case_pairs if x == y) / len(case_pairs)
    header = ["id", "target_token", "sentence", "fields_in_dispute"]
    for f in FIELDS:
        header += ["%s_A" % f, "%s_B" % f]
    header += ["adjudicated_%s" % f for f in FIELDS] + ["rationale"]

    with DISPUTES.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\r\n")
        w.writerow(header)
        for ra, rb, diff in disputed:
            row = [ra["id"], ra["target_token"],
                   ra["sentence_with_target_in_double_brackets"], "|".join(diff)]
            row += [ra[f] for f in FIELDS] + [rb[f] for f in FIELDS]
            row += [""] * len(FIELDS) + [""]          # <- the PI fills these
            w.writerow(row)

    print("=" * 88)
    print("DISPUTES EMITTED  (agreement measured on the RAW pair, before this file existed)")
    print("=" * 88)
    print("  rows compared        : %d" % len(A))
    print("  rows with any dispute: %d  (%.1f%%)" % (len(disputed), 100.0 * len(disputed) / len(A)))
    for f in FIELDS:
        print("    %-14s disputed in %4d rows" % (f, counts[f]))
    print("  HUMAN CEILING, case raw agreement (pre-adjudication): %.4f" % case_po)
    print("    ^ the model's case score must be reported beside this number, not alone")
    print("\n  file: %s   sha256 %s" % (DISPUTES, sha(DISPUTES)[:16] + "..."))
    print("  NEXT: the PI fills adjudicated_* and rationale for every row, then")
    print("        python tools/build_benchmark_gold.py --ingest %s" % DISPUTES.name)
    return 0


# ------------------------------------------------------------------ canonical wazan classes ----
TRAIL = re.compile(r"[\u064b-\u0652\u0670]*\u0627?$")


def canon_classes(patterns):
    """Equivalence classes over adjudicated patterns, at three strictnesses.

    Derived from the data: classes are exactly the sets of written forms the adjudication treats as
    the same pattern. This is what makes a canonical label space legitimate -- it is read off the
    adjudicated human annotation, not chosen by the modelling side.
    """
    def strip_tail(p):
        return TRAIL.sub("", p.strip())

    def strip_diac(p):
        return re.sub(r"[\u064b-\u0652\u0670]", "", p.strip())

    out = {}
    for label, fn in (("raw", lambda p: p.strip()),
                      ("case_vowel_stripped", strip_tail),
                      ("diacritics_stripped", strip_diac)):
        groups = collections.defaultdict(set)
        for p in patterns:
            if p:
                groups[fn(p)].add(p.strip())
        out[label] = {
            "classes": len(groups),
            "forms": len(set(patterns) - {""}),
            "largest_class": max((len(v) for v in groups.values()), default=0),
            "table": {k: sorted(v) for k, v in sorted(groups.items()) if len(v) > 1},
        }
    return out


def ingest(path: Path) -> int:
    A, B = read(A_CSV), read(B_CSV)
    disp = read(path)
    ab_ids = [r["id"] for r in A]
    dmap = {r["id"]: r for r in disp}

    problems = []
    for r in disp:
        if r["id"] not in set(ab_ids):
            problems.append("%s: id is not in the benchmark" % r["id"])
            continue
        if not (r.get("rationale") or "").strip():
            problems.append("%s: EMPTY rationale (freeze v2 §9.3a requires a written one)" % r["id"])
        for f in FIELDS:
            v = (r.get("adjudicated_%s" % f) or "").strip()
            if not v:
                if f in r["fields_in_dispute"].split("|"):
                    problems.append("%s: disputed field %s has no adjudicated value" % (r["id"], f))
                continue
            if f == "root":
                ok = (v == "ABSTAIN") or (I.norm_root(v) and len(I.norm_root(v)) >= 3)
            elif f == "wazn_pattern":
                ok = (v == "ABSTAIN") or I.rule6_wellformed(v)
            elif f == "case":
                ok = I.norm_case(v) in ("NOM", "ACC", "GEN", "ABSTAIN")
            else:
                canonical, n, errs = I.parse_alternatives(v)
                ok = not errs and (canonical == I.NONE_TOKEN or canonical)
            if not ok:
                problems.append("%s: adjudicated_%s = %r is not a legal value" % (r["id"], f, v))
    if problems:
        print("  REFUSING to build gold — %d problem(s):" % len(problems))
        for p in problems[:25]:
            print("    - %s" % p)
        if len(problems) > 25:
            print("    ... and %d more" % (len(problems) - 25))
        return 3

    # ---- build the adjudicated rows -------------------------------------------------------
    adjudicated = collections.Counter()
    rows_out = []
    for ra, rb in zip(A, B):
        d = dmap.get(ra["id"])
        row = {"id": ra["id"], "target_token": ra["target_token"],
               "provenance": {}}
        for f in FIELDS:
            adj = ((d or {}).get("adjudicated_%s" % f) or "").strip()
            if adj:
                row[f] = adj
                row["provenance"][f] = "adjudicated"
                adjudicated[f] += 1
            else:
                row[f] = ra[f]
                row["provenance"][f] = "agreed"
        if d:
            row["adjudication_rationale"] = d["rationale"]
        rows_out.append(row)

    with GOLD.open("w", encoding="utf-8") as fh:
        for r in rows_out:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    patterns = [r["wazn_pattern"] for r in rows_out if I.norm_wazn(r["wazn_pattern"])]
    classes = canon_classes(patterns)
    key = read(KEY_CSV) if KEY_CSV.exists() else []
    strata = collections.Counter(r["primary_stratum"] for r in key)
    splits = collections.Counter(r.get("split", "?") for r in key)
    case_pairs = [(I.norm_case(a["case"]), I.norm_case(b["case"])) for a, b in zip(A, B)]

    meta = {
        "built": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rows": len(rows_out),
        "sources": {"A": {"path": A_CSV.name, "sha256": sha(A_CSV)},
                    "B": {"path": B_CSV.name, "sha256": sha(B_CSV)},
                    "disputes": {"path": path.name, "sha256": sha(path)}},
        "adjudicated_field_counts": dict(adjudicated),
        "agreement_before_adjudication": {
            "case_raw_agreement": sum(1 for x, y in case_pairs if x == y) / len(case_pairs),
            "note": "the HUMAN CEILING -- report the model's case score beside this number",
        },
        "canonical_wazan_classes": classes,
        "re_derivable_counts": {
            "rows": len(rows_out),
            "distinct_targets": len({r["target_token"] for r in rows_out}),
            "strata_realised": dict(strata),
            "splits": dict(splits),
            "case_abstain_rate": sum(1 for r in rows_out if I.norm_case(r["case"]) == "ABSTAIN") / len(rows_out),
            "alternatives_filled_rate": sum(1 for r in rows_out
                                            if I.parse_alternatives(r["alternatives"])[0]) / len(rows_out),
        },
    }
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("=" * 88)
    print("ADJUDICATED BENCHMARK GOLD BUILT")
    print("=" * 88)
    print("  rows                : %d" % meta["rows"])
    print("  rows needing adjudication: %d" % len(disp))
    print("  per-field adjudicated: %s" % (dict(adjudicated) or "none — the two annotators agreed"))
    print("  HUMAN CEILING (case raw agreement, pre-adjudication): %.4f"
          % meta["agreement_before_adjudication"]["case_raw_agreement"])
    print("\n  canonical wazan classes (derived from the adjudicated patterns):")
    for k, v in classes.items():
        print("    %-22s classes=%4d  forms=%4d  largest class=%d" % (
            k, v["classes"], v["forms"], v["largest_class"]))
    print("\n  re-derivable counts: %s" % json.dumps(meta["re_derivable_counts"], ensure_ascii=False))
    print("\n  gold : %s  sha256 %s" % (GOLD, sha(GOLD)[:16] + "..."))
    print("  meta : %s  sha256 %s" % (META.name, sha(META)[:16] + "..."))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--emit-disputes", action="store_true")
    ap.add_argument("--ingest", metavar="DISPUTES_CSV")
    args = ap.parse_args()
    if args.emit_disputes:
        return emit_disputes()
    if args.ingest:
        return ingest(Path(args.ingest))
    ap.error("choose --emit-disputes or --ingest <file>")


if __name__ == "__main__":
    raise SystemExit(main())
