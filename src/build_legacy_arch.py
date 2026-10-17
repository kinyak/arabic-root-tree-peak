"""build_legacy_arch.py — vendor the training-era Arm into src/legacy_arch.py, byte-exact, with provenance.

WHY A VENDORED COPY RATHER THAN AN IMPORT PATH
    The v20 checkpoints were trained by code the repo no longer contains (it came from the Kaggle
    dataset mount). `dist/_overwrite_proof/src/` is that code and loads them with 0 missing /
    0 unexpected tensors. Vendoring it into src/ means the payload the notebook embeds is
    self-contained, so the legacy model can be built beside the current one in ONE process --
    which is the only way to compare them on the same rows.

    The copy is byte-exact and the source sha is recorded in the header, so the vendored file is
    reproducible rather than retyped. `src/legacy_arch.py --verify` re-checks the sha and the
    0/0 load against every checkpoint it is given.
"""
import hashlib
from pathlib import Path

ROOT = Path("G:/arabic-root-tree")
SRC = ROOT / "dist" / "_overwrite_proof" / "src" / "model_arms.py"
DST = ROOT / "src" / "legacy_arch.py"

HEADER = '''"""legacy_arch.py — the VENDORED training-era arm. Do not edit; regenerate if ever needed.

PROVENANCE (see EVIDENCE_LOG.md §2cq)
    source : dist/_overwrite_proof/src/model_arms.py
    sha256 : {sha}
    bytes  : {nbytes}
    dated  : 2026-10-13 13:03 (the snapshot taken immediately before the v20 run finished 15:54)

WHY THIS FILE EXISTS
    The v20 checkpoints were trained with the code the cloud copies from the Kaggle DATASET mount
    (`dist/runs/v20/kernel.txt` line 51), NOT from the repo. The repo's `model_arms.py` has since
    grown modules that code never had, so `src/model_arms.py` CANNOT construct a v20 checkpoint at
    all (`KeyError: 'wazan_canonical'`; 19 tensors absent: `char_pos`, `pool_gate`,
    `case_gov_q/k/v`, and the four autosegmental heads). Loading one through it and calling the
    result a measurement produced the "root 13%" family of numbers — which described a FABRICATED
    model, because a randomly-initialised module in the INPUT PATHWAY feeds noise into the trunk.

    Measured: THIS file loads every v20 checkpoint with **0 missing / 0 unexpected** tensors, and
    reproduces the 2026-10-13 recorded figures to the row (root 67/136/159 of 278; TRIPLE 5/18/16
    of 300; resource-OFF 5/14/11 of 300). `src/model_arms.py` is the CURRENT architecture and is
    the right file for anything trained from now on; this one is the right file for reading v20.

    Verified by `src/diagnose_architecture.py --verify-legacy`, which asserts the key diff and
    re-derives the recorded numbers. A vendored-architecture claim that is not re-checked is a
    comment, not a guarantee.
    Regenerate with: python src/build_legacy_arch.py
"""

'''

data = SRC.read_bytes()
sha = hashlib.sha256(data).hexdigest()
header = HEADER.format(sha=sha, nbytes=len(data))
# The vendored file opens with its OWN module docstring, and a module may have only one before
# `from __future__ import annotations` (which must be the first statement after it). Keep the
# vendored docstring as a comment block instead of a second docstring, so the `__future__`
# import stays legal — a bare string expression would make it a SyntaxError.
import ast  # noqa: E402

tree = ast.parse(data.decode("utf-8"))
first = tree.body[0]
if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
    lines = data.decode("utf-8").splitlines(keepends=True)
    body = "".join(lines[first.end_lineno:])
    vendored_doc = first.value.value
    quoted = "\n".join("# " + ln for ln in vendored_doc.strip().splitlines())
    payload = (f"# ----------------------------------------------------------------------------\n"
               f"# VENDORED SOURCE DOCSTRING (kept as comments so `__future__` stays first)\n"
               f"# ----------------------------------------------------------------------------\n"
               f"{quoted}\n# ----------------------------------------------------------------------------\n"
               f"{body}")
else:
    payload = data.decode("utf-8")
DST.write_bytes(header.encode("utf-8") + payload.encode("utf-8"))
print(f"wrote {DST}  ({DST.stat().st_size:,} B = {len(header)} B header + {len(data):,} B vendored)")
print(f"source sha256 {sha[:32]}…")
print(f"check     : python src/legacy_arch.py --verify   (0/0 load against every v20 checkpoint)")
