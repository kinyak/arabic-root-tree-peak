"""build_abstention_homographs.py — the surfaces that have NO context-free word class.

WHY THIS EXISTS
    CHALLENGES.md §2al. The Tier-1 abstention gate was abstaining on tokens that are
    perfectly analysable: قَدْ (particle) and قَدَّ (verb, root ق-د), أَي (which) and أَيّ
    (root ء-ي-ي). For a surface attested BOTH ways in the treebank, no gate can decide the
    word class from the string alone, so hard-abstaining is a false abstention by
    construction. Those surfaces are recorded here and deferred to the Tier-2/3 confidence
    policy instead.

DISCIPLINE (the repo's, not a preference)
    · Built from the PADT TRAIN split ONLY. The test split is read by the EVALUATION, never
      by the builder — the same rule §2x.1 had to enforce for the silver dictionary.
    · The writer records its provenance, and the loader refuses a table whose provenance
      names an evaluation split (see uncertainty_abstention.load_homograph_table).

OUTPUT
    data/abstention_homographs.json

Run:  .venv/Scripts/python.exe tools/build_abstention_homographs.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from uncertainty_abstention import strip_tashkeel  # noqa: E402

TRAIN = ROOT / "data" / "out" / "padt-train.jsonl"
OUT = ROOT / "data" / "abstention_homographs.json"


def main() -> int:
    if not TRAIN.exists():
        print(f"REFUSING: {TRAIN} is not present. This table is built from PADT train only "
              f"and will not be built from any other split.")
        return 2
    with_root: dict[str, int] = {}
    no_root: dict[str, int] = {}
    n = 0
    with open(TRAIN, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            n += 1
            s = strip_tashkeel(r.get("form_bare") or "").strip()
            if not s:
                continue
            if r.get("root_from") == "ok" and any(x for x in (r.get("t_root") or [])):
                with_root[s] = with_root.get(s, 0) + 1
            elif r.get("root_from") == "closed_class_pos":
                no_root[s] = no_root.get(s, 0) + 1

    both = sorted(set(with_root) & set(no_root))
    payload = {
        "what": "surfaces attested BOTH root-bearing and closed-class in PADT train — no "
                "context-free word class, so the structural gate defers them to Tier 2/3",
        "built_from": "PADT train split only (the held-out split is read by the evaluation, never here)",
        "splits_read": ["train"],
        "measured_on": "PADT test (evaluation only)",
        "train_records": n,
        "surfaces": both,
        "counts": {s: {"root_bearing": with_root[s], "closed_class": no_root[s]} for s in both},
    }
    # Machine-readable provenance, asserted. (A textual guard alone fired on this file's own
    # prose the first time it was run: the sentence "never the test split" contains "test".)
    assert payload["splits_read"] == ["train"], payload["splits_read"]
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                   encoding="utf-8")
    print(f"  PADT train records: {n:,}")
    print(f"  root-bearing surfaces: {len(with_root):,} | closed-class surfaces: {len(no_root):,}")
    print(f"  HOMOGRAPHS (both): {len(both)}")
    print(f"  examples: {both[:16]}")
    print(f"  wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
