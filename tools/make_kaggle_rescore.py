"""make_kaggle_rescore.py — emit dist/kaggle-rescore-CPU.ipynb: the SAME notebook, the SAME
reporting path, run on Kaggle with no attached dataset.

WHAT THIS IS
    `dist/colab-conditioning-ON.ipynb` with exactly two changes:
      1. `RESCORE_ONLY = False` -> `True`  (no training; re-score the 12 existing checkpoints)
      2. the cell-2 input plumbing, because Kaggle cannot mount Drive and this run attaches NO
         dataset: the artefacts are pulled over HTTPS from the link-shared Drive folder.
    Everything else -- the vocabulary cell, the parity gate, the preflight gate, the eval and
    reporting cells -- is untouched, so the corrected numbers cannot drift from the definitions
    in the artifact they correct. The embedded code payload rides along, which is what ties this
    to the code the round-26 run used.

WHY REPLACING CELL 2 IN THE NOTEBOOK IS THE HONEST MOVE, NOT A SHORTCUT
    The Kaggle branch in the shipped notebook expects `datasetDataSources`. The Kaggle dataset
    API cannot be driven from this workstation (a 34 MB single-POST upload was reset three times
    in a row; 11.8 MB succeeded), and a dataset the token cannot resolve is dropped SILENTLY --
    so the branch would mount nothing and fail 40 minutes in. Pulling over HTTPS is the only
    path that can be verified BEFORE the session, which is what tools/drive_preflight.py did.

USAGE
    python tools/make_kaggle_rescore.py            # writes dist/kaggle-rescore-CPU.ipynb
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "dist" / "colab-conditioning-ON.ipynb"
OUT = ROOT / "dist" / "kaggle-rescore-CPU.ipynb"
INDEX = ROOT / "dist" / "drive-index.json"


def main() -> int:
    idx = json.loads(INDEX.read_text(encoding="utf-8"))
    ckpt_id = idx["checkpoints"]["id"]
    upload_id = idx["upload"]["id"]
    rec_id = idx["colab_records"]["id"]
    nb = json.loads(SRC.read_text(encoding="utf-8"))

    md2 = [
        "## 2. Paths — this run ATTACHES NO DATASET and pulls the artefacts from Drive over HTTPS",
        "",
        "**That is a measurement, not a preference.** The Kaggle dataset API cannot be driven from",
        "the workstation that built this bundle: a 34 MB single-POST upload was reset",
        "(`ConnectionResetError 10054` / `ConnectionAbortedError 10053`) on three consecutive",
        "attempts while an 11.8 MB one succeeded. A `datasetDataSources` entry the token cannot",
        "resolve is dropped **silently** by the push API, so attaching one produces a kernel that",
        "looks configured and mounts nothing at all.",
        "",
        "So the kernel pulls from the link-shared `arabic-root-tree` folder with plain `requests`.",
        "That pull is not written here and hoped for: it is the same code as",
        "`tools/drive_preflight.py`, run locally first, where it reproduced the approved sha256 of",
        "every record file:",
        "",
        "```",
        "padt-train.jsonl        6ae53007cb73581a  MATCH",
        "padt-dev.jsonl          71a720f07cbf1b30  MATCH",
        "tashkeela-train.jsonl   6dfeace847ed24d8  MATCH",
        "tashkeela-dev.jsonl     8bf74ed10bc02da2  MATCH",
        "```",
        "",
        "Records are fetched as their `.gz` copies (74 MB instead of 1.2 GB) and gunzipped here;",
        "every downstream gate hashes the PLAIN file, so the compression is invisible to the",
        "checks. The 12 checkpoints (~650 MB) carry their vocabulary **inside** them — which is",
        "why they can be scored on a machine that has never seen the training records.",
        "",
        "**One endpoint detail, because it cost a diagnosis and its error message lies.** The plain",
        "`uc?export=download` URL returns real bytes for the small records but a 2,471-byte HTML",
        "interstitial for the 65 MB `tashkeela-train.jsonl.gz`; gzip then reports",
        "`Not a gzipped file (b'<!')`, i.e. *\"the upload is corrupt\"*. It is not corrupt. The",
        "`drive.usercontent.google.com` endpoint with `confirm=t` serves the file, and the pull",
        "below rejects any HTML payload rather than writing it to disk as if it were data.",
    ]

    cell2 = [
        "import gzip, os, sys, glob, shutil, zipfile, hashlib",
        "import requests",
        "",
        "# what must exist BEFORE the silver staging: the code, the PADT records, the gold.",
        "NEEDED_BASE = ['src/model_arms.py', 'src/train.py', 'src/eval_harness.py',",
        "               'config/shared.yaml', 'data/out/padt-train.jsonl',",
        "               'data/out/padt-dev.jsonl',",
        "               'data/annotation/gold-tashkeela-300.jsonl']",
        "",
        "# WHICH RUNTIME IS THIS? Detected, never assumed. The old test was",
        "# os.path.isdir('/kaggle') and it was WRONG: modern Colab mounts its shared Kaggle",
        "# dataset cache at /kaggle/input (kagglehub maintainer, Kaggle/kagglehub#263), so /kaggle",
        "# exists on Colab too, and a Colab session took the Kaggle branch and died with",
        "# 'no source for src/model_arms.py under /kaggle/input'. Colab is the only place",
        "# `google.colab` imports; Kaggle sets KAGGLE_KERNEL_RUN_TYPE and owns /kaggle/working.",
        "try:",
        "    import google.colab  # noqa: F401",
        "    IN_COLAB = True",
        "except ImportError:",
        "    IN_COLAB = False",
        "ON_KAGGLE = bool(os.environ.get('KAGGLE_KERNEL_RUN_TYPE')",
        "                 or os.path.isdir('/kaggle/working'))",
        "",
        "# ---------------------------------------------------------------- the three subtrees",
        "# Only these three: the shared folder mirrors the ENTIRE repo (it holds .venv/, .git/ and",
        "# data/raw/), so a recursive folder pull would drag gigabytes of things nobody reads.",
        "DRIVE = {",
        f"    'checkpoints': {ckpt_id!r},   # 12 x ~54 MB tensors, vocabulary inside each",
        f"    'upload': {upload_id!r},   # the four approved silver files (.gz + manifest)",
        f"    'records': {rec_id!r},   # the PADT records (.gz)",
        "}",
        "CACHE = '/kaggle/working/arabic-root-tree'    # persisted: results.json lands here",
        "ART = '/kaggle/working/bundle'                # the working tree, NOT persisted as data",
        "os.makedirs(ART + '/data/out', exist_ok=True)",
        "for _sub in ('results', 'checkpoints', 'data/out/spread-B-2m'):",
        "    os.makedirs(f'{CACHE}/{_sub}', exist_ok=True)",
        "",
        "",
        "def _children(fid):",
        "    r\"\"\"Immediate children of a shared folder, via the anonymous folder page.",
        "",
        "    Drive nests the listing in window['_DRIVE_ivd'] as an escaped JS string: \\xNN for",
        "    every bracket and quote, UTF-8 bytes for anything non-ASCII.\"\"\"",
        "    import codecs, json as _json, re as _re",
        "    _r = _S.get('https://drive.google.com/drive/folders/' + fid, timeout=90)",
        "    _r.raise_for_status()",
        "    _m = _re.search(r\"window\\['_DRIVE_ivd'\\]\\s*=\\s*'(.*?)';\", _r.text, _re.S)",
        "    assert _m, ('Drive returned no listing for folder %s - is it still shared as"
        " \"anyone with the link\"?' % fid)",
        "    _d = codecs.decode(_m.group(1), 'unicode_escape')",
        "    try:",
        "        _d = _d.encode('latin-1').decode('utf-8')",
        "    except Exception:",
        "        pass",
        "    return [{'id': str(_x[0]), 'name': str(_x[2])} for _x in _json.loads(_d)[0]",
        "            if isinstance(_x, list) and len(_x) >= 4]",
        "",
        "",
        "def _find(fid, name):",
        "    for _c in _children(fid):",
        "        if _c['name'] == name:",
        "            return _c['id']",
        "    raise SystemExit('not found in Drive folder %s: %s' % (fid, name))",
        "",
        "",
        "def _get(fid, dest):",
        "    \"\"\"Stream one file, and never save an HTML interstitial as if it were the file.",
        "",
        "    MEASURED: the plain uc?export=download URL served the small records fine but returned",
        "    2,471 bytes of HTML for the 65 MB tashkeela-train.jsonl.gz, which gzip reported as",
        "    'Not a gzipped file (b'<!')' -- i.e. as a corrupt upload. It was not corrupt. The",
        "    confirm endpoint returns real gzip bytes for the same id, and an HTML payload is",
        "    rejected here so a wrong download can never be mistaken for a wrong upload.\"\"\"",
        "    _urls = ('https://drive.usercontent.google.com/download'",
        "             '?id=%s&export=download&confirm=t' % fid,",
        "             'https://drive.google.com/uc?export=download&id=%s&confirm=t' % fid)",
        "    for _u in _urls:",
        "        with _S.get(_u, stream=True, timeout=3600) as _r:",
        "            _r.raise_for_status()",
        "            _it = _r.iter_content(1 << 20)",
        "            _first = next(_it, b'')",
        "            if _first.lstrip()[:1] == b'<':",
        "                continue",
        "            _n = len(_first)",
        "            with open(dest, 'wb') as _fh:",
        "                _fh.write(_first)",
        "                for _c in _it:",
        "                    _fh.write(_c)",
        "                    _n += len(_c)",
        "            break",
        "    else:",
        "        raise SystemExit('Drive served HTML instead of %s (not a file)' % dest)",
        "    print('    %-34s %8.2f MB' % (os.path.basename(dest), _n / 1e6), flush=True)",
        "    return dest",
        "",
        "",
        "_S = requests.Session()",
        "print('pulling the round-26 artefacts over HTTPS (no dataset is attached):')",
        "",
        "# 1. THE CHECKPOINTS. Twelve tensors. Skipped if already present, so an interrupted pull",
        "#    resumes instead of starting the 650 MB again.",
        "CKPT_NAMES = [s + '-' + a + '-s' + str(_sd) + '.pt'",
        "              for s in ('gold', 'silver')",
        "              for a in ('treatment', 'baseline')",
        "              for _sd in (20261009, 20261010, 20261011)]",
        "assert len(CKPT_NAMES) == 12, 'the grid is 2 sources x 2 arms x 3 seeds'",
        "for _nm in CKPT_NAMES:",
        "    _dest = f'{CACHE}/checkpoints/{_nm}'",
        "    if os.path.exists(_dest):",
        "        print('    %-34s already present' % _nm)",
        "    else:",
        "        _get(_find(DRIVE['checkpoints'], _nm), _dest)",
        "",
        "# 2. THE RECORDS, as their .gz copies. ALL FOUR silver files, because the staging cell",
        "#    downstream is all-or-none: a partial set makes it pay the 18.5-min in-cloud rebuild",
        "#    rather than stage. The manifest is one of the four.",
        "_jobs = [('build_manifest_tashkeela.json', DRIVE['upload'], 'data/out/spread-B-2m'),",
        "         ('tashkeela-train.jsonl.gz', DRIVE['upload'], 'data/out/spread-B-2m'),",
        "         ('tashkeela-dev.jsonl.gz', DRIVE['upload'], 'data/out/spread-B-2m'),",
        "         ('tashkeela-test.jsonl.gz', DRIVE['upload'], 'data/out/spread-B-2m'),",
        "         ('padt-train.jsonl.gz', DRIVE['records'], 'data/out'),",
        "         ('padt-dev.jsonl.gz', DRIVE['records'], 'data/out')]",
        "for _nm, _fid, _sub in _jobs:",
        "    _dest = f'{CACHE}/{_sub}/{_nm}'",
        "    if os.path.exists(_dest):",
        "        print('    %-34s already present' % _nm)",
        "    else:",
        "        _get(_find(_fid, _nm), _dest)",
        "",
        "# 3. THE PADT RECORDS must be PLAIN in ART before the vocabulary cell reads them, because",
        "#    read_records() opens the path directly. The silver ones stay compressed here: the",
        "#    staging cell below owns that gunzip and gates on the sha256 of the plain file, so",
        "#    decompressing them twice would only weaken the check.",
        "for _nm in ('padt-train.jsonl', 'padt-dev.jsonl'):",
        "    _gz = f'{CACHE}/data/out/{_nm}.gz'",
        "    _plain = f'{ART}/data/out/{_nm}'",
        "    if os.path.exists(_plain):",
        "        continue",
        "    with gzip.open(_gz, 'rb') as _fi, open(_plain, 'wb') as _fo:",
        "        shutil.copyfileobj(_fi, _fo, 1 << 20)",
        "    print('    staged %s <- %s' % (_nm, _gz))",
        "",
        "assert os.access(ART, os.W_OK), f'{ART} is not writable'",
        "print('runtime:', 'kaggle' if ON_KAGGLE else ('colab' if IN_COLAB else 'local'))",
        "print('detect : google.colab=%s  /kaggle/working=%s  KAGGLE_KERNEL_RUN_TYPE=%r'",
        "      % (IN_COLAB, os.path.isdir('/kaggle/working'),",
        "         os.environ.get('KAGGLE_KERNEL_RUN_TYPE')))",
        "print('ART    :', ART, '(writable)' if os.access(ART, os.W_OK) else '(READ-ONLY!)')",
        "print('CACHE  :', CACHE)",
    ]

    def as_source(lines: list[str]) -> list[str]:
        return [l + "\n" for l in lines]

    flipped = 0
    replaced2 = 0
    replacedmd = 0
    for c in nb["cells"]:
        src = c.get("source", [])
        if c.get("cell_type") == "code":
            for i, line in enumerate(src):
                if line.strip() == "RESCORE_ONLY = False":
                    src[i] = line.replace("RESCORE_ONLY = False", "RESCORE_ONLY = True")
                    flipped += 1
            if src and src[0].startswith("import gzip, os, sys, glob, shutil, zipfile"):
                c["source"] = as_source(cell2)
                replaced2 += 1
        else:
            if src and src[0].startswith("## 2. Paths"):
                c["source"] = as_source(md2)
                replacedmd += 1

    assert flipped == 1, "expected exactly ONE RESCORE_ONLY literal, found %d" % flipped
    assert replaced2 == 1, "expected ONE paths cell, replaced %d" % replaced2
    assert replacedmd == 1, "expected ONE '## 2. Paths' markdown, replaced %d" % replacedmd

    nb.setdefault("metadata", {})["hermes"] = {
        "mode": "kaggle-rescore-cpu",
        "gpu_required": False,
        "dataset_attached": False,
        "input": "https pull from the link-shared Drive folder",
    }
    OUT.write_text(json.dumps(nb, indent=1), encoding="utf-8")
    kb = OUT.stat().st_size / 1024
    print("wrote %s  (%.0f KB)" % (OUT, kb))
    print("  RESCORE_ONLY=True   cell2 replaced   markdown replaced")
    print("  Kaggle kernel-source cap is <1 MB: %s" % ("OK" if kb < 1024 else "TOO BIG"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
