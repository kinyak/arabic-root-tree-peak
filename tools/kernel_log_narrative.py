"""kernel_log_narrative.py — turn a fetched Kaggle kernel log into plain console text.

WHY THIS EXISTS (and why it is NOT in src/)
    `src/kaggle_run.py --log` prints the raw log, which is a stream of JSON objects:

        {"stream_name": "stdout", "time": 3255.7, "data": "gold-baseline-s20261009 ... \n"}

    Reading a verdict out of that is guesswork, and the per-step progress lines drown the
    ~60 lines that actually carry the result. This script drops the progress lines
    (`step N loss ...`, `eval @N: ...`) and concatenates the rest in order with stderr
    marked, so the build narrative, the ceilings and the mean/sd table read normally.

    It lives in `tools/`, deliberately NOT in `src/`: `src/make_notebook.py` bundles every
    `src/*.py` into the embedded payload whose sha256 `src/verify_run_code.py` checks
    against a fetched log. Adding a file under src/ changes that hash and would make an
    already-verified run read as STALE — i.e. the tooling would destroy the very record it
    exists to inspect. Measured the hard way; do not move this file into src/.

USAGE
    python tools/kernel_log_narrative.py dist/runs/v11/<slug>.log [out.txt]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

OBJ = re.compile(
    r'\{"stream_name":\s*"(stdout|stderr)",\s*"time":\s*[0-9.]+,\s*"data":\s*"((?:[^"\\]|\\.)*)"\}',
    re.S)
PROGRESS = re.compile(r"^\s*(step\s+\d+|eval @\d+|\[\d+/\d+\])")


def narrative(log_text: str) -> str:
    out: list[str] = []
    for stream, raw in OBJ.findall(log_text):
        line = json.loads('"' + raw + '"')
        if PROGRESS.match(line) or "ms/step" in line or "it/s" in line:
            continue
        if stream == "stderr":
            line = "[stderr] " + line
        out.append(line.rstrip("\n") + "\n")
    return "".join(out)


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    if len(sys.argv) < 2 or "-h" in sys.argv[1:] or "--help" in sys.argv[1:]:
        print("Usage: python tools/kernel_log_narrative.py <log-file> [out.txt]")
        return 0
    src = Path(sys.argv[1])
    if not src.is_file():
        print(f"Error: file not found: {src}")
        return 1
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else src.with_suffix(".console.txt")
    text = narrative(src.read_text(encoding="utf-8", errors="replace"))
    dst.write_text(text, encoding="utf-8")
    print(text)
    print(f"--- {len(text.splitlines())} lines written to {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
