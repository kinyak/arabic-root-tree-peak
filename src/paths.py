"""Cross-platform path resolution for arabic-root-tree.

WHY THIS EXISTS
    Every script in ``src/`` used to hardcode ``/home/rendi/arabic-root-tree/...``
    and was consequently laptop-only (README "no script reads the files
    cross-platform-safely"; START-HERE.md §9; data/raw/MANIFEST.md note 3).
    This module is the single place a path is defined.

RESOLUTION ORDER
    1. ``$ART_ROOT`` if set (lets you point the corpus elsewhere, e.g. a drive
       with more free space, without touching code).
    2. The repository root this file lives in (``src/..``).

USAGE
    ``from paths import RAW, PADT_TRAIN, QAC_TXT, EQTB_CSV``

    Scripts keep their existing constant names via aliasing, e.g.
    ``from paths import RAW as PD``.  Do not re-introduce a literal path.
"""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------- roots
ROOT: Path = Path(os.environ.get("ART_ROOT") or Path(__file__).resolve().parent.parent)
RAW: Path = ROOT / "data" / "raw"
OUT: Path = ROOT / "data" / "out"

# ------------------------------------------------------- gold corpora
# Names and hashes are catalogued in data/raw/MANIFEST.md; verify with
#     cd data/raw && sha256sum -c CHECKSUMS.sha256
QAC_TXT: Path = RAW / "qac-morphology-0.4.txt"
QAC_ZIP: Path = RAW / "qac-morphology-0.4.zip"

# The human gold (the ONE non-CALIMA-mediated reference). Defined HERE, not as a
# CWD-relative literal, because four scripts read it and three of them were written
# with "../data/..." — which silently broke the moment they were run from the repo
# root instead of src/. A path that only works from one directory is a trap.
GOLD_JSONL: Path = ROOT / "data" / "annotation" / "gold-tashkeela-300.jsonl"

PADT_TRAIN: Path = RAW / "ar_padt-ud-train.conllu"
PADT_DEV: Path = RAW / "ar_padt-ud-dev.conllu"
PADT_TEST: Path = RAW / "ar_padt-ud-test.conllu"

NYUAD_TRAIN: Path = RAW / "ar_nyuad-ud-train.conllu"
NYUAD_DEV: Path = RAW / "ar_nyuad-ud-dev.conllu"
NYUAD_TEST: Path = RAW / "ar_nyuad-ud-test.conllu"   # planned E1a held-out set

PUD_TEST: Path = RAW / "ar_pud-ud-test.conllu"

# EQTB — the QAC dependency layer.  ``EQTB_CSV`` is THE REAL TREEBANK
# (57 MB, UTF-16, TAB, 51 cols, 139,376 data rows).  ``EQTB_DECOY`` is the
# 5-column verse-text file the older docs named by mistake.  See MANIFEST note 1.
EQTB_CSV: Path = RAW / "qrtb" / "Quranic.csv"
EQTB_RAR: Path = RAW / "Quranic.rar"
EQTB_DECOY: Path = RAW / "quranic-treebank.csv"
EQTB_RELLABELS: Path = RAW / "qrtb-RelLabels.csv"
EQTB_POS: Path = RAW / "qrtb-pos.csv"

# Preferred encoding for the EQTB CSV (see MANIFEST) — it is NOT utf-8.
EQTB_ENCODING: str = "utf-16"


def require(path) -> Path:
    """Fail loudly and usefully when a corpus is absent.

    Corpora are deliberately untracked (GPLv3 / CC-BY-NC-SA), so a fresh clone
    has an empty ``data/raw``.  A silent FileNotFoundError 200 lines into a
    probe is the failure mode this project keeps recording.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"corpus missing: {p}\n"
            f"  data/raw is deliberately untracked (copyleft / non-commercial).\n"
            f"  Re-fetch with the recipe in {RAW / 'MANIFEST.md'},\n"
            f"  then verify: cd {RAW} && sha256sum -c CHECKSUMS.sha256"
        )
    return p


def resolve(path) -> Path:
    """Make a config-declared path CWD-independent.

    `config/shared.yaml` declares paths like ``data/out/padt-train.jsonl``, which are
    relative to the REPO ROOT. Scripts that pass them straight to `open()` therefore
    only work when the CWD happens to be the root — running the same script from
    ``src/`` raises FileNotFoundError and looks like missing data rather than a path
    bug. that is not hypothetical: it produced exactly that misleading error while
    building the round-17 union vocabulary. Absolute paths are returned untouched.
    """
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


if __name__ == "__main__":  # quick self-check: python src/paths.py
    print(f"ART_ROOT env : {os.environ.get('ART_ROOT') or '(unset)'}")
    print(f"ROOT         : {ROOT}")
    print(f"RAW          : {RAW}   exists={RAW.exists()}")
    for name in (
        "QAC_TXT", "PADT_TRAIN", "PADT_DEV", "PADT_TEST",
        "NYUAD_TRAIN", "NYUAD_DEV", "NYUAD_TEST", "PUD_TEST",
        "EQTB_CSV", "EQTB_RAR", "EQTB_DECOY",
    ):
        p = globals()[name]
        print(f"  {name:13} {'OK ' if p.exists() else '-- '} {p}")
