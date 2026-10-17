"""gold_controls_table.py — turn `diagnose_gold_checkpoint.py` outputs into one table.

WHY THIS EXISTS
    A gold score only means something next to its controls, and the controls are printed
    per checkpoint by `src/diagnose_gold_checkpoint.py` — as prose, one block per file. The
    ablation has 12 checkpoints, so the useful object is the GRID: whole-root exact,
    per-slot, the in-vocab/OOV split, the wazan columns, case macro-F1 — by arm and seed,
    with the mean and the spread, next to the constant-predictor baselines and the
    untrained control that come out of the same script.

    Lives in `tools/`, not `src/`: see the note in tools/kernel_log_narrative.py — any file
    under src/ changes the embedded-payload sha256 that `src/verify_run_code.py` checks.

USAGE
    python src/diagnose_gold_checkpoint.py --ckpt dist/runs/v11/checkpoints/<run>.pt \
        > dist/runs/v11/diag-<run>.txt        # one per checkpoint
    python tools/gold_controls_table.py dist/runs/v11/diag-*.txt
"""
from __future__ import annotations

import re
import statistics as st
import sys
from pathlib import Path

F = float
NUM = r"([0-9.]+)"


def parse(text: str) -> list[dict]:
    blocks = re.split(r"^--- (.+) ---$", text, flags=re.M)[1:]
    rows = []
    for name, body in zip(blocks[0::2], blocks[1::2]):
        def g(pat, cast=F, default=0.0):
            m = re.search(pat, body)
            return cast(m.group(1)) if m else default
        row = {
            "run": name.strip(),
            "whole": g(r"whole-root exact\s*:\s*\d+/\d+ = " + NUM),
            "per_slot": g(r"per-slot exact\s*:\s*\d+/\d+ = " + NUM),
            "in_vocab_n": g(r"in_vocab n=(\d+)", int),
            "in_vocab_whole": g(r"in_vocab n=\d+\s+whole " + NUM),
            "in_vocab_slot": g(r"in_vocab n=\d+\s+whole [0-9.]+\s+per-slot " + NUM),
            "oov_n": g(r"oov\s+n=(\d+)", int),
            "oov_whole": g(r"oov\s+n=\d+\s+whole " + NUM),
            "oov_slot": g(r"oov\s+n=\d+\s+whole [0-9.]+\s+per-slot " + NUM),
            "wazan_raw": g(r"WAZAN\s+raw " + NUM),
            "wazan_norm": g(r"WAZAN\s+raw [0-9.]+\s+hamza-normalised " + NUM),
            "wazan_slot": g(r"slot-set " + NUM),
            "case_f1": g(r"CASE\s+macro-F1 " + NUM),
        }
        rows.append(row)
    return rows


def main() -> int:
    if not sys.argv[1:] or "-h" in sys.argv[1:] or "--help" in sys.argv[1:]:
        print("Usage: python tools/gold_controls_table.py <diag-file1.txt> [diag-file2.txt ...]")
        return 0
    files = [Path(p) for p in sys.argv[1:] if Path(p).is_file()]
    if not files:
        print("no valid files found — pass paths to output files from diagnose_gold_checkpoint.py")
        return 1
    rows = [r for f in files for r in parse(f.read_text(encoding="utf-8", errors="replace"))]
    if not rows:
        print("no blocks parsed — is this the output of diagnose_gold_checkpoint.py?")
        return 1

    cols = ["whole", "per_slot", "in_vocab_whole", "oov_whole", "wazan_raw",
            "wazan_slot", "case_f1"]
    print("| run | n | " + " | ".join(cols) + " |")
    print("|---|---|" + "---|" * len(cols))
    for r in rows:
        n = r["in_vocab_n"] + r["oov_n"]
        print(f"| {r['run']} | {n} | " + " | ".join(
            (f"{r[c]:.3f}" if c != "n" else str(r[c])) for c in cols) + " |")

    trained = [r for r in rows if not r["run"].startswith("CONTROL")]
    print("\nMEAN [sd] over the trained checkpoints, by arm x source:")
    for src in ("gold", "silver"):
        for arm in ("treatment", "baseline"):
            grp = [r for r in trained if r["run"].startswith(f"{src}-{arm}-")]
            if not grp:
                continue
            cells = []
            for c in cols:
                v = [r[c] for r in grp]
                cells.append(f"{c} {st.mean(v):.3f} [{st.pstdev(v):.3f}]")
            print(f"  {src}-{arm:<9} n={len(grp)}  " + "  ".join(cells))
    for r in rows:
        if r["run"].startswith("CONTROL"):
            print("  control (untrained weights): " + "  ".join(
                f"{c} {r[c]:.3f}" for c in cols))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
