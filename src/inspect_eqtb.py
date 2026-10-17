"""EQTB reader — Task 1 of START-HERE.md §8: decide EQTB's fate.

WHY THIS EXISTS
    66 MB of EQTB sits in ``data/raw`` and is read by **no script** (CHALLENGES.md
    B18).  SPEC-REV6 §3.1 treats it as the source of the dependency layer and E1b
    as the classical zero-shot test suite, so the docs make claims about data the
    pipeline has never opened.  Either wire it up or delete it — this script is
    the "wire it up" half, and it is also what makes deletion an informed choice.

ACCEPTANCE (START-HERE.md §8 Task 1)
    - reads ``qrtb/Quranic.csv`` (UTF-16, TAB), prints 139,376 data rows
    - confirms the columns
    - if kept as a test suite: its verse IDs are excluded from any QAC training
      range  -> this script therefore also prints the verse-ID space

DESIGN NOTE — DISCOVERY, NOT ASSUMPTION
    The column list is *reported*, never hardcoded.  Docs in this repo have twice
    named the wrong EQTB file (MANIFEST note 1) and three quoted figures have been
    caught as wrong by re-running scripts.  So: read the header, print it, and
    assert the columns we actually depend on are present.
"""
from __future__ import annotations

import collections
import csv
import sys
from pathlib import Path

from paths import EQTB_CSV, EQTB_DECOY, EQTB_ENCODING, RAW, require

# The columns the project's claims depend on (MANIFEST table + E1b's design).
EXPECTED = {
    "root": "Latin-translit root — the head-2 supervision EQTB would add",
    "root_ar": "Arabic-script root",
    "nominal_case": "case marking — head 5",
    "depend_rel": "dependency relation — head 4",
    "head_rel": "head relation — head 4",
}
# verse-ID columns, needed for the E1b hold-out range
VERSE_KEYS = ("chapter_id", "verse_id")


def sniff_preamble() -> None:
    """Report the decoy explicitly — it is the file the old docs pointed at."""
    print("--- files ---")
    for label, p in (("real treebank", EQTB_CSV), ("decoy", EQTB_DECOY)):
        state = f"{p.stat().st_size:,} B" if p.exists() else "ABSENT"
        print(f"  {label:14} {state:>14}  {p}")
    if EQTB_DECOY.exists():
        print("  NOTE: `quranic-treebank.csv` is the DECOY (5 cols of verse text).")
        print("        The treebank is `qrtb/Quranic.csv`. Do not confuse them.")


def main() -> int:
    print("=" * 78)
    print("EQTB — Task 1: is this file wireable, and what does it actually contain?")
    print("=" * 78)

    sniff_preamble()
    if not EQTB_CSV.exists():
        print(require(EQTB_CSV))          # raises with the re-fetch recipe
        return 2

    # ---------------------------------------------------- read (streamed)
    n_rows = 0
    counter: collections.Counter = collections.Counter()
    root_ar_nonempty = 0
    case_nonempty = 0
    dep_nonempty = 0
    chapters: set[str] = set()
    verses: set[str] = set()
    malformed = 0

    with open(EQTB_CSV, encoding=EQTB_ENCODING, newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        cols = list(reader.fieldnames or [])
        print("\n--- header ---")
        print(f"  {len(cols)} columns:")
        for i, c in enumerate(cols):
            print(f"    [{i:2}] {c}")

        for row in reader:
            n_rows += 1
            for k, v in row.items():
                if v:
                    counter[k] += 1
            if (row.get("root_ar") or "").strip():
                root_ar_nonempty += 1
            if (row.get("nominal_case") or "").strip():
                case_nonempty += 1
            if (row.get("depend_rel") or "").strip():
                dep_nonempty += 1
            ch = (row.get("chapter_id") or "").strip()
            vs = (row.get("verse_id") or "").strip()
            if ch:
                chapters.add(ch)
            if vs:
                verses.add(vs)
            if None in row:               # ragged line: more fields than header
                malformed += 1

    # ------------------------------------------- non-degeneracy assertions
    # This project's recorded failure mode is a script that runs, prints a
    # confident number, and means nothing (§2e, §2g, §2h). Guard that here.
    assert n_rows > 100_000, f"only {n_rows} rows — wrong file or wrong encoding?"
    assert cols, "no header parsed — is the encoding really utf-16?"

    print("\n--- rows ---")
    print(f"  data rows : {n_rows:,}   (docs say 139,376; 139,377 counted the header)")
    print(f"  malformed : {malformed:,}")

    print("\n--- the columns the project's claims depend on ---")
    # NON-EMPTY IS NOT COVERAGE. EQTB writes the tatweel 'ـ' (and '_') into root/root_ar
    # when it has no root, and '_' into nominal_case. Measured: 64% of root_ar values are
    # the placeholder. An earlier version of this script reported "100% non-empty" and
    # that was repeated as root coverage — it is not. Both counts are printed.
    PLACEHOLDERS = {"", "_", "\u0640", "-", "\u2014"}
    missing = []
    for name, why in EXPECTED.items():
        if name in cols:
            filled = counter[name]
            print(f"  OK  {name:14} {filled:>7,} non-empty ({100*filled/max(n_rows,1):5.1f}%)"
                  f"  — {why}")
        else:
            missing.append(name)
            print(f"  --  {name:14} ABSENT  — {why}")
    if missing:
        print(f"\n  WARNING: absent -> {missing}. Docs claim EQTB carries these.")

    # placeholder-aware pass
    print("\n--- NON-EMPTY vs REAL VALUE (the distinction that matters) ---")
    for name in ("root", "root_ar", "nominal_case", "depend_rel"):
        if name not in cols:
            continue;  # noqa: E702
        real_n = 0
        with open(EQTB_CSV, encoding=EQTB_ENCODING, newline="") as fh:
            for row in csv.DictReader(fh, delimiter="\t"):
                v = (row.get(name) or "").strip()
                if v not in PLACEHOLDERS:
                    real_n += 1
        print(f"  {name:14} non-empty {counter[name]:>7,} · REAL {real_n:>7,} "
              f"({100*real_n/max(n_rows,1):5.1f}%) · placeholder {counter[name]-real_n:>7,}")

    print("\n--- verse-ID space (needed if EQTB becomes the E1b test suite) ---")
    print(f"  distinct chapter_id : {len(chapters):,}")
    print(f"  distinct verse_id   : {len(verses):,}")
    if chapters:
        num = sorted(int(c) for c in chapters if c.isdigit())
        print(f"  chapter range       : {min(num)} .. {max(num)}")
    print("  REMINDER (CHALLENGES.md §2c): EQTB re-annotates the SAME Qur'anic")
    print("  tokens as QAC. Holding out QAC verses while training on EQTB leaks")
    print("  them. Any hold-out range declared here must be excluded from EQTB too.")

    print("\n--- verdict ---")
    usable = ["root", "depend_rel"]
    have = [c for c in usable if c in cols and counter[c] > 0]
    print(f"  wireable columns present: {have}")
    print(f"  root_ar rows : {root_ar_nonempty:,}")
    print(f"  case rows    : {case_nonempty:,}")
    print(f"  depend rows  : {dep_nonempty:,}")
    print("  No wazan column exists in EQTB (MANIFEST) — head 3 gains nothing here.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
