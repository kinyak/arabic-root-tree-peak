"""build_annotation_gold.py — turn a filled sheet into the gold training artifact.

The 300 Tashkeela rows are the FIRST human wazān supervision that exists anywhere for
this project. This converts them into a normalised JSONL that Head 2 (root) and Head 3
(wazān) can be trained against, and records a sha256 so the artifact is reproducible.

Normalisation applied, and why:
  · root       -> bare alef (Rule 7), dots dropped; ABSTAIN becomes null
  · pattern    -> digits validated: exactly {1,2,3} or {1,2,3,4}, each once (Rule 6)
  · case       -> NOM/ACC/GEN or null (ABSTAIN)
  · confidence/notes kept verbatim so a reviewer can audit any row

Nothing is silently repaired: a row that fails validation is written with `valid: false`
and its reason, so the failure count is visible instead of absorbed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

from paths import ROOT

ARABIC = re.compile(r"[\u0621-\u063a\u0641-\u064a]")
DIG = re.compile(r"[1-4]")
CASE_OK = {"NOM", "ACC", "GEN"}
CASE_IDX = {"NOM": 0, "ACC": 1, "GEN": 2}


def norm_root(s):
    if not s:
        return None
    t = s.strip()
    if t.upper().startswith("ABSTAIN"):
        return None
    t = "".join(c for c in t if ARABIC.match(c))
    if not t:
        return None
    return (t.replace("\u0623", "\u0627").replace("\u0625", "\u0627")
             .replace("\u0622", "\u0627").replace("\u0621", "\u0627"))


def check_pattern(p):
    """(pattern|None, valid, reason)."""
    if not p or p.strip().upper().startswith("ABSTAIN"):
        return None, False, "abstain"
    t = p.strip()
    d = DIG.findall(t)
    if set(d) not in ({"1", "2", "3"}, {"1", "2", "3", "4"}):
        return t, False, "digit_set_incomplete"
    if len(d) != len(set(d)):
        return t, False, "repeated_digit"
    return t, True, "ok"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", required=True)
    ap.add_argument("--out", default="data/annotation/gold-tashkeela-300.jsonl")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.sheet, encoding="utf-8-sig")))
    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)

    stats = {"rows": 0, "root": 0, "pattern_valid": 0, "case": 0, "abstain_case": 0,
             "invalid": 0}
    with open(out_path, "w", encoding="utf-8") as fh:
        for r in rows:
            root = norm_root(r["root"])
            pat, ok, why = check_pattern(r["wazn_pattern"])
            cs = (r["case"] or "").strip().upper()
            case = cs if cs in CASE_OK else None
            stats["rows"] += 1
            stats["root"] += 1 if root else 0
            stats["pattern_valid"] += 1 if ok else 0
            stats["case"] += 1 if case is not None else 0
            if case is None:
                stats["abstain_case"] += 1
            if not ok and why not in ("abstain",):
                stats["invalid"] += 1
            rec = {
                "id": r["id"],
                "source": "tashkeela-human-gold",
                "annotator": "Rendi",
                "n_annotators": 1,
                "context": r["sentence_with_target_in_double_brackets"],
                "form": r["target_token"],
                "t_root_arabic": root,
                "t_wazan_pattern": pat,
                "t_case": CASE_IDX.get(case) if case else None,
                "case_name": case,
                "confidence": (r["confidence"] or "").strip().lower() or None,
                "notes": (r["notes"] or "").strip() or None,
                "root_valid": root is not None,
                "pattern_valid": ok,
                "pattern_reason": why,
            }
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    h = hashlib.sha256(out_path.read_bytes()).hexdigest()
    meta = dict(stats, sha256=h, annotator="Rendi", n_annotators=1,
                sheet=Path(args.sheet).name,
                caveat="single-annotator gold; no inter-annotator agreement")
    (out_path.parent / "gold-tashkeela-300.meta.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8")

    print("=" * 84)
    print("GOLD ARTIFACT — first human wazān supervision for this project")
    print("=" * 84)
    for k, v in stats.items():
        print(f"  {k:<16} {v}")
    print(f"\n  -> {out_path}")
    print(f"  sha256 {h}")
    print("\n  CAVEAT recorded in the meta: single annotator, no IAA. Any model score")
    print("  against this gold is measured against ONE person's judgement.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
