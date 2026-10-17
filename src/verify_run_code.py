"""verify_run_code.py — assert the notebook / kernel under test carries THIS working tree's code.

WHY THIS EXISTS (round 19, measured)
------------------------------------
`make_notebook.py` embeds src/ as a base64 zip with `EXPECT_SHA` asserted at run time. That
assertion is self-consistent: it compares the payload against a hash baked into the SAME
notebook, so it catches CORRUPTION but can never catch STALENESS.

The failure it missed, for real: v10 was pushed at 16:0x carrying a bundle generated at
13:35. Every round-19 fix landed after it — `52d3e8c` (the NaN fix) at 14:44:53, `f90b1c3`
(Prong 1) at 15:18:38, `f50f093` (Prong 2) at 15:31:46. The kernel therefore trained the
PRE-FIX code and reproduced the old symptoms exactly:
  · 6/6 silver runs `loss nan` at all 60 checkpoints (the unsupervised-head NaN was never fixed)
  · `gold_root treat 0.002` — the pre-Prong-1 root blackout (0/278), not the 23.7% a fixed
    decoder yields on the same weights
Worse, the notebook's cell 4 extracts the attached dataset zips and cell 6 then extracts the
EMBEDDED payload into the SAME tree (`ART`), so the stale embedded src silently OVERWROTE a
freshly re-uploaded dataset `src.zip`. Verifying the dataset was necessary and NOT sufficient.

So freshness must be checked against something OUTSIDE the notebook: the working tree.
Run this BEFORE and AFTER every push. Non-zero exit = do not trust the run.

    .venv/Scripts/python.exe src/verify_run_code.py
    .venv/Scripts/python.exe src/verify_run_code.py --kernel-log dist/runs/v11/kernel_full.log
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import re
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
os.chdir(ROOT)

import make_notebook as MN  # noqa: E402  (reuses the ONE bundling rule, so they cannot drift)

# Substrings that must be present, i.e. the specific fixes this round is testing for. A run
# missing any of these is not the run you think you are running.
REQUIRED_MARKERS = {
    "src/model_arms.py": ["PRONG 2", "SOFT WAZAN -> ROOT CONDITIONING"],
    "src/final_surface.py": ["decode_root_slots", "decode_root_slots_beamed"],
    "src/train.py": ["cross_entropy"],
}


def rebuild() -> tuple[bytes, str, int]:
    """The bundle the working tree WOULD produce right now."""
    chunks, sha, n = MN.embedded_bundle()
    return base64.b64decode("".join(chunks)), sha, n


def notebook_payload(nb_path: Path) -> tuple[bytes, str, int]:
    """(blob, EXPECT_SHA, EXPECT_FILES) as actually written into the notebook on disk."""
    nb = json.loads(nb_path.read_text(encoding="utf-8"))
    cell = None
    for c in nb.get("cells", []):
        s = "".join(c.get("source", []))
        if "EMBED_CHUNKS" in s and "EXPECT_SHA" in s:
            cell = s
    if cell is None:
        raise SystemExit(f"no embedded-payload cell in {nb_path} — is this the generated notebook?")
    sha = re.search(r"EXPECT_SHA\s*=\s*'([0-9a-f]{64})'", cell).group(1)
    files = int(re.search(r"EXPECT_FILES\s*=\s*(\d+)", cell).group(1))
    block = re.search(r"EMBED_CHUNKS\s*=\s*\[(.*?)\]\s*\n", cell, re.S).group(1)
    b64 = "".join(re.findall(r"'([A-Za-z0-9+/=]+)'", block))
    return base64.b64decode(b64), sha, files


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--notebook", default="notebooks/run-padt.ipynb")
    ap.add_argument("--kernel-log", default=None,
                    help="a fetched kernels log; asserts the run's code IS this working tree")
    ap.add_argument("--run-id", default=None,
                    help="a run identifier in tools/verified_runs.json (e.g. 'v11'); "
                         "checks against the pinned commit/bundle sha, not the working tree")
    args = ap.parse_args()
    fails: list[str] = []

    # Load the verified-runs registry if it exists
    registry_path = ROOT / "tools" / "verified_runs.json"
    registry = {}
    if registry_path.exists():
        import json as _json
        registry = _json.loads(registry_path.read_text(encoding="utf-8"))

    rb_raw, rb_sha, rb_n = rebuild()
    print(f"working tree bundle : {len(rb_raw):,} bytes  {rb_n} files  sha256 {rb_sha[:16]}…")

    nb_raw, nb_sha, nb_n = notebook_payload(Path(args.notebook))
    print(f"notebook payload    : {len(nb_raw):,} bytes  {nb_n} files  sha256 {nb_sha[:16]}…")
    if nb_sha != rb_sha:
        fails.append("the pushed notebook is STALE vs the working tree — "
                     "regenerate with `python src/make_notebook.py` before pushing")
    if nb_n != rb_n:
        fails.append(f"file count differs: notebook {nb_n} vs working tree {rb_n}")

    with zipfile.ZipFile(io.BytesIO(nb_raw)) as z:
        names = z.namelist()
        for name in names:
            if not name.startswith("src/") or not name.endswith(".py"):
                continue
            local = ROOT / name
            if not local.exists():
                fails.append(f"{name} is embedded but missing from the working tree")
            elif z.read(name) != local.read_bytes():
                fails.append(f"{name}: embedded bytes differ from the working tree")
        for rel, marks in REQUIRED_MARKERS.items():
            if rel not in names:
                fails.append(f"{rel} not in the bundle at all")
                continue
            txt = z.read(rel).decode("utf-8", "replace")
            for mk in marks:
                if mk not in txt:
                    fails.append(f"{rel} lacks the required marker {mk!r} "
                                 f"→ this bundle predates the fix it is meant to test")

    if args.kernel_log:
        p = Path(args.kernel_log)
        if not p.exists():
            fails.append(f"kernel log not found: {p}")
        else:
            log = p.read_text(encoding="utf-8", errors="replace")
            m = re.search(r"embedded code bundle:\s*(\d+)\s*bytes\s*sha256\s*([0-9a-f]{16})", log)
            if not m:
                fails.append("kernel log carries no 'embedded code bundle' line — "
                             "cannot prove which code ran")
            else:
                log_size = int(m.group(1))
                log_sha = m.group(2)
                print(f"kernel log payload  : {log_size:,} bytes  sha256 {log_sha}…")

                # Check against the pinned registry if --run-id is provided
                if args.run_id and args.run_id in registry:
                    pinned = registry[args.run_id]
                    pinned_sha = pinned.get("bundle_sha", "")
                    pinned_commit = pinned.get("commit", "")
                    print(f"  → checking against pinned run {args.run_id} "
                          f"(commit {pinned_commit[:7]}, bundle sha {pinned_sha})")
                    if log_sha != pinned_sha:
                        fails.append(f"THE RUN USED DIFFERENT CODE: log sha {log_sha}… != "
                                     f"pinned run {args.run_id} sha {pinned_sha}… — results are VOID")
                    else:
                        print(f"  → the run's code IS the pinned run {args.run_id}")
                else:
                    # Fall back to working tree check (with warning)
                    if args.run_id:
                        print(f"  → run-id {args.run_id} not in registry, falling back to working tree")
                    else:
                        print("  → no --run-id provided, checking against working tree")
                    if log_sha != rb_sha[:16]:
                        fails.append(f"THE RUN USED STALE CODE: log sha {log_sha}… != "
                                     f"working tree {rb_sha[:16]}… — results are VOID")
                    else:
                        print("  → the run's code IS this working tree")

    print()
    if fails:
        print(f"VERIFY FAILED — {len(fails)} problem(s):")
        for f in fails:
            print("  -", f)
        return 1
    print("VERIFY OK: notebook payload == working tree, markers present, src byte-identical.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
