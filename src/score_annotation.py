"""score_annotation.py — score a filled annotation sheet (SPEC-REV6 §5.3).

Reads the sheet written by `build_annotation_sheet.py` after human annotation, and reports:

  1. FILL RATE and ABSTAIN rate per column — did the format actually get used?
  2. VALIDITY CHECK — agreement against EQTB's withheld root/case gold. EQTB is an
     independent human treebank, never CALIMA, so this is a legitimate external check on
     whether the annotator's labels mean what we think they mean.
  3. INTER-ANNOTATOR AGREEMENT when two sheets are supplied: Cohen's kappa for `case`,
     and raw agreement for `root`. IAA is what makes any score interpretable — if two
     humans agree on case only 80% of the time, a model at 85% is already above the
     human agreement rate and the paper must say so.
  4. The WAZN column, for which no public gold exists, so it is reported as produced
     gold plus the consistency of the FORMAT (well-formedness), never as accuracy.

NOTHING here reads CALIMA. That is the point of the whole protocol.

USAGE
    python src/score_annotation.py --sheet <filled.csv> [--sheet2 <second.csv>]
"""
from __future__ import annotations

import argparse
import collections
import csv
import re
import sys
from pathlib import Path

from paths import ROOT

ARABIC = re.compile(r"[\u0621-\u063a\u0641-\u064a]")
DIG = re.compile(r"[1-4]")
ABSTAIN_WORDS = {"abstain", "abdtain", "abstain)", "?", "-", "", "na", "n/a", "none"}
CASE_ALLOWED = {"NOM", "ACC", "GEN"}
KEY = ROOT / "data" / "annotation" / "private" / "pilot-annotation-KEY.csv"


def norm_root(s):
    """Accept 'ق ت ل', 'ق.ت.ل', 'قتل' — compare on the radical sequence."""
    if not s:
        return None
    t = "".join(c for c in s if ARABIC.match(c))
    return t or None


def fold_hamza(s):
    """Fold hamza variants onto bare alef for COMPARISON only.

    The pilot showed this dominates the raw disagreement: an annotator writes the root
    of الله as أ.ل.ه while EQTB writes اله, and the same for أجل/اجل, أول/اول,
    آخرة/اخرة, سوء/سوا. That is a REPRESENTATION convention (is the hamza seat written
    as a radical?), not a disagreement about the root. Both raw and folded figures are
    reported so the convention cost stays visible instead of being hidden by the fold.
    """
    if not s:
        return s
    return (s.replace("\u0623", "\u0627").replace("\u0625", "\u0627")
             .replace("\u0622", "\u0627").replace("\u0621", "\u0627"))


def norm_case(s):
    if s is None:
        return None
    t = str(s).strip().upper()
    if t in ABSTAIN_WORDS or t.startswith("ABSTAIN"):
        return "ABSTAIN"
    return t if t in CASE_ALLOWED else f"INVALID({t})"


def norm_pattern(s):
    """A well-formed pattern has digits {1,2,3} or {1,2,3,4}, each exactly once."""
    if not s:
        return None
    t = str(s).strip()
    if not t or t.upper().startswith("ABSTAIN"):
        return None
    digits = DIG.findall(t)
    ds = set(digits)
    if ds in ({"1", "2", "3"}, {"1", "2", "3", "4"}) and len(digits) == len(ds):
        return t
    return f"INVALID({t})"


def read_sheet(path):
    rows = {}
    with open(path, encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            if not r.get("id"):
                continue
            rows[r["id"].strip()] = {
                "target": (r.get("target_token") or "").strip(),
                "root": norm_root(r.get("root")),
                "pattern": norm_pattern(r.get("wazn_pattern")),
                "case": norm_case(r.get("case")),
                "confidence": (r.get("confidence") or "").strip().lower(),
                "notes": (r.get("notes") or "").strip(),
            }
    return rows


def load_key(path=KEY):
    if not Path(path).exists():
        return {}
    out = {}
    with open(path, encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            g_root = (r.get("EQTB_root_arabic") or "").strip()
            out[r["id"].strip()] = {
                "gold_root": norm_root(g_root),
                "gold_case": norm_case(r.get("EQTB_case")),
                "has_gold": (r.get("has_gold") or "").strip() == "yes",
            }
    return out


def kappa(pairs):
    """Cohen's kappa over (a, b) label pairs; None when undefined."""
    n = len(pairs)
    if n == 0:
        return None, None
    po = sum(1 for a, b in pairs if a == b) / n
    ca, cb = collections.Counter(a for a, _ in pairs), collections.Counter(b for _, b in pairs)
    pe = sum((ca[k] / n) * (cb[k] / n) for k in set(ca) | set(cb))
    if abs(1 - pe) < 1e-12:
        return po, None
    return po, (po - pe) / (1 - pe)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", required=True, help="filled sheet from the annotator")
    ap.add_argument("--sheet2", help="second annotator, for inter-annotator agreement")
    args = ap.parse_args()

    A = read_sheet(args.sheet)
    key = load_key()
    print("=" * 84)
    print("ANNOTATION SCORING")
    print("=" * 84)
    print(f"sheet      : {args.sheet}")
    print(f"rows       : {len(A)}")
    print(f"gold key   : {'loaded' if key else 'NOT FOUND (validity check skipped)'}")

    if not A:
        print("no rows read — check the file")
        return 1

    # ---- 1. fill / abstain rates
    print("\n--- 1. did the format get used? ---")
    for col in ("root", "pattern", "case"):
        vals = [v[col] for v in A.values()]
        filled = sum(1 for v in vals if v)
        bad = sum(1 for v in vals if isinstance(v, str) and v.startswith("INVALID"))
        abst = sum(1 for v in vals if v == "ABSTAIN")
        print(f"  {col:<8} filled {filled:>3}/{len(vals)}  "
              f"abstain {abst:>3}  MALFORMED {bad}")
    conf = collections.Counter(v["confidence"] for v in A.values())
    print(f"  confidence: {dict(conf)}")
    notes = sum(1 for v in A.values() if v["notes"])
    print(f"  notes present on {notes} rows")

    # ---- 4. the wazn column (new gold; no public reference exists)
    pats = [v["pattern"] for v in A.values() if v["pattern"]]
    well = [p for p in pats if not str(p).startswith("INVALID")]
    print(f"\n--- 4. wazān (no public gold exists — reported as produced gold) ---")
    print(f"  patterns given      : {len(well)}/{len(A)}")
    print(f"  distinct patterns   : {len(set(well))}")
    print("  well-formedness is checked by the format rule (digits 1..3/1..4, no repeats).")
    print("  ACCURACY CANNOT BE REPORTED — no human wazān reference for these tokens.")
    print("  This column IS the new gold; it is the first human wazān supervision anywhere.")

    # ---- 2. validity against withheld EQTB gold
    if key:
        print("\n--- 2. validity check against EQTB's WITHHELD gold (independent, not CALIMA) ---")
        rc = collections.Counter()
        case_pairs = []
        for i, v in A.items():
            k = key.get(i)
            if not k or not k["has_gold"]:
                continue
            rc["n"] += 1
            if v["root"] and k["gold_root"]:
                rc["root_n"] += 1
                rc["root_ok"] += 1 if v["root"] == k["gold_root"] else 0
                rc["root_n_f"] += 1
                rc["root_ok_f"] += 1 if (fold_hamza(v["root"]) ==
                                         fold_hamza(k["gold_root"])) else 0
            if v["case"] in CASE_ALLOWED and k["gold_case"] in CASE_ALLOWED:
                rc["case_n"] += 1
                case_pairs.append((v["case"], k["gold_case"]))
                rc["case_ok"] += 1 if v["case"] == k["gold_case"] else 0
        if rc["root_n"]:
            print(f"  root  : {rc['root_ok']}/{rc['root_n']} = "
                  f"{100*rc['root_ok']/rc['root_n']:.1f}% match EQTB gold  (raw)")
            print(f"          {rc['root_ok_f']}/{rc['root_n_f']} = "
                  f"{100*rc['root_ok_f']/max(rc['root_n_f'],1):.1f}% with the HAMZA "
                  f"CONVENTION FOLDED (أ/إ/آ/ء -> ا)")
            print("          The gap between those two lines is a representation")
            print("          convention, not an annotator error. Pick ONE convention for")
            print("          the real sheet and apply it to both sides.")
        if rc["case_n"]:
            print(f"  case  : {rc['case_ok']}/{rc['case_n']} = "
                  f"{100*rc['case_ok']/rc['case_n']:.1f}% match EQTB gold")
        print("  (A LOW number here is not an annotator failure — it means either the")
        print("   instructions or the gold is wrong, and the pilot exists to find that out.)")
        # disagreements, so the instructions can be fixed
        bad = [(i, A[i]["case"], key[i]["gold_case"]) for i in A
               if key.get(i, {}).get("has_gold")
               and A[i]["case"] in CASE_ALLOWED
               and key[i]["gold_case"] in CASE_ALLOWED
               and A[i]["case"] != key[i]["gold_case"]]
        if bad:
            print(f"\n  case disagreements ({len(bad)}):")
            for i, mine, gold in bad[:12]:
                print(f"    {i}  {A[i]['target']:14} you={mine:4} EQTB={gold:4}")

    # ---- 3. inter-annotator agreement
    if args.sheet2:
        B = read_sheet(args.sheet2)
        print(f"\n--- 3. inter-annotator agreement ({len(B)} rows from annotator 2) ---")
        common = sorted(set(A) & set(B))
        cp = [(A[i]["case"], B[i]["case"]) for i in common
              if A[i]["case"] in CASE_ALLOWED and B[i]["case"] in CASE_ALLOWED]
        po, k = kappa(cp)
        if cp:
            print(f"  case  : {len(cp)} comparable · raw agreement {100*po:.1f}% · "
                  f"Cohen's κ = {k:.3f}" if k is not None else
                  f"  case  : {len(cp)} comparable · raw agreement {100*po:.1f}% · κ undefined")
            print("  -> THIS is the human ceiling. Any model score must be quoted against it.")
        rp = [(A[i]["root"], B[i]["root"]) for i in common
              if A[i]["root"] and B[i]["root"]]
        if rp:
            ra = sum(1 for a, b in rp if a == b) / len(rp)
            po_r, k_r = kappa(rp)
            print(f"  root  : {len(rp)} comparable · raw agreement {100*ra:.1f}%"
                  + (f" · κ = {k_r:.3f}" if k_r is not None else ""))
        pp = [(A[i]["pattern"], B[i]["pattern"]) for i in common
              if A[i]["pattern"] and B[i]["pattern"]]
        if pp:
            pa = sum(1 for a, b in pp if a == b) / len(pp)
            print(f"  wazān : {len(pp)} comparable · raw agreement {100*pa:.1f}%")
            print("          (low wazān agreement is EXPECTED and worth reporting — it is")
            print("           evidence for why the task is hard, not a defect.)")
    else:
        print("\n--- 3. inter-annotator agreement: SKIPPED (no second sheet) ---")
        print("  Without a second annotator there is no human ceiling, so every model")
        print("  number remains uninterpretable in the strict sense. State this as a")
        print("  limitation rather than implying the single-annotator labels are gold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
