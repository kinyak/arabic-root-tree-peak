"""make_notebook.py — generate notebooks/run-padt.ipynb (the PRIVATE Kaggle/Colab run).

The notebook is generated, not hand-edited, so it stays diffable in git and can be
regenerated when the config changes. Run:

    python src/make_notebook.py

WHY A NOTEBOOK AT ALL, AND WHAT IT DOES NOT DO
    Training needs a GPU; this box has an RX 6700 XT with no ROCm/WSL (verified), so the
    real runs belong on Kaggle/Colab. The notebook therefore does NOT invent any
    methodology — it imports src/train.py, src/model_arms.py and src/eval_harness.py, the
    exact code the smoke test already exercises locally. Nothing is re-implemented for the
    cloud, because a re-implementation is a second thing that can be wrong.

WHY THE CODE RIDES IN THE NOTEBOOK AND THE SILVER RECORDS ARE BUILT IN-CLOUD
    Measured, not preferred. Kaggle's dataset API will not take this upload:
    `datasets/upload` is a 404, and `datasets/create/new` / `create/version` want a JSON
    body carrying blob tokens from a resumable-upload flow this scope-limited token
    cannot drive. A 34.0 MB combined bundle also reset the connection on three
    consecutive attempts. And the kernel source is capped at **<1 MB**, so an 8.75 MB
    data payload cannot ride here either (HTTP 400, measured). What fits is the
    **code**: src/ + config/ + the human gold are a 188 KB zip (251 KB of base64), and
    they are embedded with the zip's sha256 asserted at run time, so a stale payload
    FAILS LOUDLY instead of training on the wrong code.

    The silver DATA is therefore built inside the kernel, which is what COLAB.md always
    said to do with Tashkeela ("must be streamed"). The build cell installs
    camel-tools AND arramooz-pysqlite (without arramooz the gold-derived root
    dictionary halves: 13,736 keys instead of 40,265), downloads the CALIMA data with
    `python -m camel_tools.cli.camel_data -i …`, and runs the same
    `build_training_jsonl.py --source tashkeela` the local run used — a build, not a
    re-implementation. The PADT half comes from the attached `arabic-dataset`.

WHAT THE GRID IS (2026-10-09, round 17)
    {gold, silver} x {treatment, baseline} x 3 seeds, at a MATCHED 120k tokens per source
    (config `data.limit_train`). The gold row is the matched-size comparison with 3 seeds
    instead of 1; the silver row is the ablation round 16 named as the crux — same
    architecture, same vocabulary, same steps, training TARGET swapped. Every run is
    additionally scored against the 278 human wazān patterns, which is the only reference
    here that CALIMA did not produce. The separate full-corpus 3-seed run (223,881
    tokens) is its own Kaggle version and is reported separately.
"""
from __future__ import annotations

import ast
import base64
import hashlib
import json
import sys
from pathlib import Path

from paths import ROOT

OUT = ROOT / "notebooks" / "run-padt.ipynb"
# Kaggle rejects a kernel source >= 1 MB, so this cap is that limit minus headroom for
# the notebook's own JSON. Past it the build refuses rather than producing a file the
# push will reject — which is exactly how round 17 discovered the limit.
MAX_EMBED_B64 = 700_000


# ------------------------------------------------------------------------------------------------
# A RUN MAY NOT SILENTLY CHANGE ITS OWN OBJECTIVE (EVIDENCE_LOG §2cq, §2cs)
# ------------------------------------------------------------------------------------------------
# MEASURED FAILURE, 2026-10-14. The v21 grid trained under a `config/shared.yaml` that existed NOWHERE
# IN GIT. Its log's own bundle sha was cfd992765884bbb4, which reproduced the WORKING TREE byte-for-byte
# (465,404 B, 81 files) while the committed config produced 20335ce6434ff198 (465,297 B). That payload
# carried a rewritten multi-task loss — log-vocab normalisation OFF, wazān weight 1.0 -> 4.0, focal loss
# ON — which put wazān's CE term at roughly 6x root's, and NOTHING in the run printed it. The grid was
# cancelled with 2 of 12 runs done. So the builder now REFUSES a payload whose `config/` differs from
# HEAD, and the notebook PRINTS its effective loss weights at preflight.
ALLOW_DIRTY_CONFIG = False
PROVENANCE: dict = {}


def _git_dirty(rel: str) -> list:
    """Porcelain status for one path, or [] if git is unavailable (never a silent pass: it says so)."""
    import subprocess
    try:
        r = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--", rel],
                           capture_output=True, text=True)
        return [l.rstrip() for l in r.stdout.splitlines() if l.strip()]
    except Exception as e:                                    # pragma: no cover
        print(f"  ! could not read git status for {rel}: {e}")
        return [f"? git unavailable for {rel}"]


def assert_payload_provenance(allow_dirty: bool = False) -> dict:
    """REFUSE an uncommitted `config/`; report every other uncommitted file the payload carries.

    The objective is part of the code: a config that changes the loss is a training change, and v21 is
    the proof that one can ride in a payload, run to completion, and leave a clean-looking log.
    """
    cfg_dirty = _git_dirty("config/")
    import subprocess
    r_diff = subprocess.run(["git", "-C", str(ROOT), "diff", "--exit-code", "config/shared.yaml"],
                            capture_output=True, text=True)
    if r_diff.returncode != 0 and "config/shared.yaml (unstaged git diff)" not in cfg_dirty:
        cfg_dirty.append("config/shared.yaml (unstaged git diff)")
    other_dirty = _git_dirty("src/") + _git_dirty("tools/")
    prov = {"config_dirty": cfg_dirty, "other_dirty": other_dirty,
            "config_sha256": hashlib.sha256((ROOT / "config" / "shared.yaml").read_bytes()).hexdigest()}
    print("  payload provenance:")
    if cfg_dirty:
        print(f"    !! config/ DIFFERS FROM HEAD ({len(cfg_dirty)} path(s))")
        if not allow_dirty:
            raise SystemExit(
                "REFUSING to build a payload from an uncommitted `config/` (§2cq/§2cs).\n"
                "  A config that changes the loss IS a training change: v21 trained a grid under an\n"
                "  objective that existed nowhere in git, burned 2 of 12 runs, and said nothing.\n"
                "  Dirty:\n    " + "\n    ".join(cfg_dirty) + "\n"
                "  Commit it, or re-run with `--allow-dirty-config` to accept it EXPLICITLY — which\n"
                "  prints this objective at preflight and records the config's sha256 in the notebook.")
        print("    ACCEPTED under --allow-dirty-config — the notebook will print this objective by name.")
    else:
        print("    config/ matches HEAD")
    if other_dirty:
        print(f"    note: {len(other_dirty)} other embedded path(s) differ from HEAD "
              f"(src/, tools/): {', '.join(p.split()[-1] for p in other_dirty)}")
    return prov


def embedded_bundle() -> tuple[list, str, int]:
    """(base64 chunks, sha256 of the zip, file count) for the CODE-ONLY bundle.

    src/ + tools/fit_parity_union.py + config/ + the human gold + the PADT half of the
    silver root dictionary. No corpora and no derived records: those do not fit under the
    kernel-source cap, and the silver records are built in-cloud (or staged) instead.
    """
    import io
    import zipfile
    PROVENANCE.update(assert_payload_provenance(ALLOW_DIRTY_CONFIG))
    entries: list[tuple[str, bytes]] = []
    for p in sorted((ROOT / "src").glob("*.py")):
        entries.append((f"src/{p.name}", p.read_bytes()))
    # THE PARITY FITTER SHIPS WITH THE BUNDLE. It lives in tools/ because it is a local
    # development tool, but the run's own PARITY FAIL message names it -- and a remedy
    # pointing at a file the payload does not contain is not a remedy. Shipping it also
    # makes the cloud copy the LOCAL copy rather than a rebuild that might differ.
    for p in sorted((ROOT / "tools").glob("fit_parity_union.py")):
        entries.append((f"tools/{p.name}", p.read_bytes()))
    entries.append(("config/shared.yaml", (ROOT / "config" / "shared.yaml").read_bytes()))
    for p in sorted((ROOT / "data" / "annotation").glob("gold-*")):
        entries.append((f"data/annotation/{p.name}", p.read_bytes()))
    # THE GOLD HALF OF THE SILVER ROOT DICTIONARY, computed here from the raw treebank —
    # which is deliberately NOT in the bundle, so the cloud build cannot read it. Shipping
    # this half as data means the cloud dictionary is the LOCAL dictionary, not a
    # rebuild that might differ. The lexicon half (arramooz) comes from the pinned pip
    # package in the build cell.
    import build_training_jsonl as BTJ
    half, surfaces = BTJ.padt_half_of_silver_dict()
    payload = {"what": "PADT `Root=` gold half of the silver root dictionary",
               "padt_surfaces": surfaces, "keys": len(half), "mapping": half}
    entries.append(("data/silver_root_dict_padt.json",
                    json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")))
    print(f"  dictionary half: {len(half):,} gold keys (of {surfaces:,} PADT surfaces)")
    buf = io.BytesIO()
    # DETERMINISTIC ZIP — this is load-bearing, not tidiness. A default ZipInfo stamps every
    # entry with the CURRENT wall-clock time, so rebuilding from an UNCHANGED tree produced a
    # different sha256 each time (measured, one tree, three builds: 30fc4f0f…, 23eea0a5…,
    # e1deaa2a…). EXPECT_SHA therefore could not mean anything: a freshly regenerated notebook
    # could never match a previously recorded hash, so the "stale payload FAILS LOUDLY" guard
    # below was unfalsifiable in the one direction that mattered. Measured consequence on v10:
    # the notebook was generated at 13:35 and every round-19 fix landed 14:44–15:31, yet the
    # run's self-check passed happily and 6/6 silver runs reproduced the pre-fix NaN.
    # A fixed timestamp + fixed compression type make the sha a function of CONTENT alone,
    # which is what lets src/verify_run_code.py compare a notebook against the working tree.
    FIXED_DATE = (1980, 1, 1, 0, 0, 0)
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in entries:
            zi = zipfile.ZipInfo(name, date_time=FIXED_DATE)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            z.writestr(zi, data)
    blob = buf.getvalue()
    sha = hashlib.sha256(blob).hexdigest()
    b64 = base64.b64encode(blob).decode("ascii")
    if len(b64) > MAX_EMBED_B64:
        raise SystemExit(f"embedded payload would be {len(b64)/1e3:.0f} KB of base64, over "
                         f"the {MAX_EMBED_B64/1e3:.0f} KB cap (Kaggle's kernel-source "
                         f"limit is 1 MB) — the payload must stay CODE, never data")
    print(f"  embedded bundle: {len(blob)/1e3:.1f} KB zip -> {len(b64)/1e3:.1f} KB base64"
          f"  {len(entries)} files  sha256 {sha[:16]}…")
    return [b64[i:i + 4000] for i in range(0, len(b64), 4000)], sha, len(entries)


def md(*lines):
    return {"cell_type": "markdown", "metadata": {}, "source": [l + "\n" for l in lines]}


def code(*lines):
    return {"cell_type": "code", "execution_count": None, "metadata": {},
            "outputs": [], "source": [l + "\n" for l in lines]}


CELLS = [
    md("# arabic-root-tree — matched-size run + the silver-vs-gold ablation (PRIVATE)",
       "",
       "**Keep this notebook private.** The corpora are CC BY-NC-SA 4.0 / GPL, so no public",
       "output, no published results, no shared checkpoints.",
       "",
       "## The four caveats that must travel with every number this produces",
       "",
       "1. **Corpus size (rev. 10).** Tashkeela measures **66.5M Arabic tokens**, not the ~98M",
       "   the docs once assumed. The SILVER training set built for this run is a",
       "   **documented 500k-token sample** of it (`build_training_jsonl.py --source",
       "   tashkeela`); the corpus-size claim rests on the coverage measurement, not on this",
       "   sample's size.",
       "2. **The renderer (rev. 13).** Exact vocalization is **~11%**; the consonant skeleton",
       "   is **~90%**. Any end-to-end surface metric is dominated by that, so it is reported",
       "   separately from the head metrics and never as the headline.",
       "3. **Human gold (rev. 14).** The wazān/case gold is **single-annotator with no",
       "   inter-annotator agreement**, and is stratified toward weak/doubled surfaces.",
       "   Scores against it are one person's judgement on a non-representative sample.",
       "4. **WHICH CEILING APPLIES DEPENDS ON THE TRAINING TARGET (round 16).** An",
       "   arm trained on PADT treebank **gold** was taught the answers, so its score",
       "   beside the 0.459/0.451 CALIMA ceilings is meaningless — that is what round 16",
       "   caught about itself. The ceiling only means something for the **silver**-trained",
       "   runs, and cell 7 says which is which rather than leaving it to the reader.",
       "",
       "## What this run is FOR",
       "",
       "Two questions, one grid:",
       "",
       "**(a) matched size.** Both arms read ONE config and their parameter counts are",
       "asserted equal before training starts; the claim under test is that generating",
       "**through** the grammatical representation beats generating surface with the same",
       "heads bolted on as auxiliaries.",
       "",
       "**(b) the target source.** Does any of that survive when the targets are",
       "CALIMA/dictionary **silver** rather than human gold? `config/shared.yaml` §ablation",
       "states, head by head, what actually differs (case is a clean contrast; wazān is",
       "silver on BOTH sides because PADT has no wazān column; syntax and NTP are absent on",
       "the silver side). It is not one clean contrast and is not reported as one."),

    md("## 1. Refuse to run without a GPU",
       "",
       "`device: auto` in the config would quietly train on CPU and burn the session. The",
       "docs say fail loudly instead, so this asserts before anything else."),
    code("import torch, os, sys",
         "",
         "# RESCORE_ONLY re-runs ONLY the evaluator/reporting path on checkpoints that already",
         "# exist in Drive: no training, no GPU, no retraining. It exists because a REPORTING",
         "# defect (the majority-class baseline in src/eval_harness.py) mis-stated numbers",
         "# without touching a single weight -- so the right remedy is to re-score the same",
         "# tensors, and demanding a GPU for that would burn quota recomputing arithmetic.",
         "# The shipped notebook TRAINS (False); the rescore variant flips this one literal.",
         "RESCORE_ONLY = False",
         "assert RESCORE_ONLY or torch.cuda.is_available(), (",
         "    'NO GPU. Refusing to run: the config would fall back to CPU and the session'",
         "    ' would be wasted. Enable a GPU accelerator, or set RESCORE_ONLY = True to'",
         "    ' re-score existing checkpoints without a GPU.')",
         "if torch.cuda.is_available():",
         "    FREE, TOTAL = torch.cuda.mem_get_info()",
         "    print('GPU      :', torch.cuda.get_device_name(0))",
         "    print('VRAM free: %.1f GB / %.1f GB' % (FREE/1e9, TOTAL/1e9))",
         "    print('bf16     :', torch.cuda.is_bf16_supported())",
         "else:",
         "    print('GPU      : none - RESCORE_ONLY, no training will happen')",
         "print('torch    :', torch.__version__)"),

    md("## 2. Paths — Colab (Drive) or Kaggle (`/kaggle/input`), detected not assumed",
       "",
       "Colab is ephemeral and persists via Drive; Kaggle mounts the private datasets",
       "read-only at `/kaggle/input/...` and persists ONLY `/kaggle/working`.",
       "",
       "**The runtime is DETECTED — and the test used to be wrong.** It was",
       "`os.path.isdir('/kaggle')`. But modern Colab mounts its shared Kaggle dataset cache",
       "at `/kaggle/input` (kagglehub maintainer, Kaggle/kagglehub#263), so `/kaggle` exists",
       "on Colab too: a Colab session took the Kaggle branch and died with",
       "`no source for src/model_arms.py under /kaggle/input` — a message about the wrong",
       "runtime — while the Colab staging below never ran at all. Detection is now",
       "`google.colab` importability for Colab, and `KAGGLE_KERNEL_RUN_TYPE` or",
       "`/kaggle/working` for Kaggle; cell 2 prints the evidence for its conclusion.",
       "",
       "On Colab the PADT records must be staged from Drive (COLAB.md §2). They are",
       "corpus-licensed, so they cannot ride in the embedded payload, and cell 2 fails fast",
       "naming the exact Drive path when they are absent.",
       "",
       "**TWO datasets are attached this round**, because one combined bundle is a 34.0 MB",
       "zip that this connection resets (measured, 3 attempts) while an 11.8 MB one",
       "uploads fine: `arabic-dataset` holds the PADT records, `arabic-root-tree-silver`",
       "holds the Tashkeela records plus the CURRENT `src/` and `config/`. The cell below",
       "extracts every zip into ONE tree with the silver bundle LAST (so the newer code",
       "wins on shared paths), then merges anything still missing from wherever it is",
       "mounted, then asserts every required file is present — because a",
       "`datasetDataSources` entry the token cannot resolve is silently dropped by the",
       "push API, and that failure must show up here rather than 40 minutes into training.",
       "",
       "COLAB.md §3: checkpoints must never land in `/content` — a 12 h cutoff would lose",
       "the run."),
    code("import gzip, os, sys, glob, shutil, zipfile",
         "",
         "# what must exist BEFORE the silver build: the code, the PADT records, the gold.",
         "# The Tashkeela records are NOT here — cell 2c builds them in-cloud, because the",
         "# kernel source cap (<1 MB, measured) means they cannot ship with the code.",
         "NEEDED_BASE = ['src/model_arms.py', 'src/train.py', 'src/eval_harness.py',",
         "               'config/shared.yaml', 'data/out/padt-train.jsonl',",
         "               'data/out/padt-dev.jsonl',",
         "               'data/annotation/gold-tashkeela-300.jsonl']",
         "",
         "# WHICH RUNTIME IS THIS? Detected, never assumed - and NOT by testing whether a",
         "# '/kaggle' directory merely EXISTS. MODERN COLAB MOUNTS ITS SHARED KAGGLE DATASET",
         "# CACHE AT /kaggle/input (kagglehub maintainer, Kaggle/kagglehub#263), so /kaggle is",
         "# PRESENT on Colab and the old os.path.isdir('/kaggle') test returned True there.",
         "# That sent a Colab session down the Kaggle branch, where it died with",
         "#   'no source for src/model_arms.py under /kaggle/input'",
         "# - a message about the wrong runtime - while the Colab record staging below never",
         "# TWO MEASURED FAILURES, IN OPPOSITE DIRECTIONS - which is why no single naive probe works:",
         "#   (1) `os.path.isdir('/kaggle')` is True ON COLAB (modern Colab mounts its shared Kaggle",
         "#       dataset cache at /kaggle/input, Kaggle/kagglehub#263), so a Colab session took the",
         "#       Kaggle branch and died with 'no source for src/model_arms.py under /kaggle/input'.",
         "#   (2) the fix for (1) treated `import google.colab` as Colab with 'Colab wins any tie'.",
         "#       MEASURED 2026-10-13, Kaggle kernel v16: the Kaggle image SHIPS google.colab, so that",
         "#       import SUCCEEDS there, IN_COLAB came out True, the Kaggle branch was skipped, and the",
         "#       Colab branch died on drive.mount() with",
         "#           NotImplementedError: Mounting drive is unsupported in this environment",
         "#       The traceback proves it: the failing frame is",
         "#       /usr/local/lib/python3.13/dist-packages/google/colab/drive.py in the KAGGLE image.",
         "#",
         "# SO: ORDER, NOT IMPORTABILITY. `KAGGLE_KERNEL_RUN_TYPE` is set by the Kaggle kernel runner",
         "# and nowhere else, so it is checked FIRST and is decisive. `google.colab` is consulted only",
         "# when that marker is ABSENT, and the Colab branch additionally requires the Colab filesystem",
         "# marker /var/colab/hostname - the exact file google.colab.drive._mount tests before raising",
         "# the NotImplementedError above, so it is present on real Colab and absent on Kaggle.",
         "_KRT = os.environ.get('KAGGLE_KERNEL_RUN_TYPE')",
         "_KW = os.path.isdir('/kaggle/working')",
         "_COLAB_FS = os.path.exists('/var/colab/hostname')",
         "try:",
         "    import google.colab  # noqa: F401",
         "    _COLAB_IMPORT = True",
         "except ImportError:",
         "    _COLAB_IMPORT = False",
         "IN_COLAB = (not _KRT) and _COLAB_IMPORT and _COLAB_FS",
         "ON_KAGGLE = bool(_KRT) or (_KW and not IN_COLAB)",
         "if ON_KAGGLE:",
         "    INPUT, CACHE = '/kaggle/input', '/kaggle/working'",
         "    print('mounted under /kaggle/input:')",
         "    for d in sorted(glob.glob(f'{INPUT}/**/', recursive=True))[:30]:",
         "        if os.path.isdir(d):",
         "            print('   ', d, '->', sorted(os.listdir(d))[:8])",
         "    # ART MUST BE WRITABLE, AND IT MUST BE A COPY - a working copy of the bundle dir.",
         "    # MEASURED FAILURE (round 17, version 6): this used to set ART to the dataset",
         "    # mount whenever src/ was found already extracted, and Kaggle mounts datasets",
         "    # READ-ONLY, so writing the embedded payload died with",
         "    # 'OSError: [Errno 30] Read-only file system'. Copying works whether the upload",
         "    # arrived as loose files or as a zip, so both mount styles are handled here.",
         "    ART = f'{CACHE}/bundle'",
         "    os.makedirs(ART, exist_ok=True)",
         "    zips = sorted(glob.glob(f'{INPUT}/**/*.zip', recursive=True))",
         "    # A DATASET UPLOADED WITH `--dir-mode zip` ARRIVES AS ONE ZIP PER TOP-LEVEL DIRECTORY",
         "    # (config.zip, data.zip, src.zip), and WHICH PREFIX the entries carry is not documented:",
         "    # either the full path from the dataset root ('data/out/x.jsonl') or the path relative to",
         "    # that top-level dir ('out/x.jsonl'). Rather than guess -- and rather than let a wrong",
         "    # guess surface as a confusing missing-file assert three cells later -- detect and nest.",
         "    for zp in zips:",
         "        _pfx = os.path.basename(zp)[:-4]                 # 'data' from 'data.zip'",
         "        with zipfile.ZipFile(zp) as z:",
         "            _names = z.namelist()",
         "            if _names and not any(n.startswith(_pfx + '/') for n in _names):",
         "                _into = os.path.join(ART, _pfx)          # entries are relative to it",
         "                os.makedirs(_into, exist_ok=True)",
         "                z.extractall(_into)",
         "                print('  extracted', zp, '-> %s/ (entries were prefix-relative)' % _pfx)",
         "            else:",
         "                z.extractall(ART)",
         "                print('  extracted', zp, '-> ART (entries carry the full relative path)')",
         "    for f in NEEDED_BASE:",
         "        if os.path.exists(f'{ART}/{f}'):",
         "            continue",
         "        hits = [h for h in glob.glob(f'{INPUT}/**/{os.path.basename(f)}',",
         "                                    recursive=True)",
         "                if f.split('/')[0] in h.replace(os.sep, '/')]",
         "        assert hits, f'no source for {f} under {INPUT}'",
         "        dest = f'{ART}/{f}'",
         "        os.makedirs(os.path.dirname(dest), exist_ok=True)",
         "        shutil.copy2(sorted(hits)[0], dest)",
         "        print('  copied', f, '<- ', sorted(hits)[0])",
         "    res_hits = glob.glob(f'{INPUT}/**/tashkeela_spelling_index.tsv.gz', recursive=True)",
         "    if res_hits:",
         "        dest_res = f'{ART}/data/resources/tashkeela_spelling_index.tsv.gz'",
         "        os.makedirs(os.path.dirname(dest_res), exist_ok=True)",
         "        shutil.copy2(sorted(res_hits)[0], dest_res)",
         "        print('  copied resource <-', sorted(res_hits)[0])",
         "    elif os.path.exists(f'{ART}/data/resources/tashkeela_spelling_index.tsv.gz'):",
         "        print('  resource already staged at %s/data/resources/tashkeela_spelling_index.tsv.gz' % ART)",
         "    else:",
         "        print('  note: tashkeela_spelling_index.tsv.gz not found under INPUT; v3_resource_on will degrade to rules-only')",
         "    assert os.access(ART, os.W_OK), f'{ART} is not writable'",
         "    for sub in ('results', 'checkpoints'):",
         "        os.makedirs(f'{CACHE}/{sub}', exist_ok=True)",
         "else:",
         "    from google.colab import drive",
         "    drive.mount('/content/drive')",
         "    CACHE = '/content/drive/MyDrive/arabic-root-tree'",
         "    for sub in ('results', 'checkpoints'):",
         "        os.makedirs(f'{CACHE}/{sub}', exist_ok=True)",
         "    ART = '/content/arabic-root-tree'",
         "    os.makedirs(ART, exist_ok=True)",
         "    # STAGE THE PADT RECORDS AND ASSERT THEM HERE. The embedded payload CANNOT carry them",
         "    # (corpus licensing) and the corpora are GBs, so COLAB.md 2 uploads the derived records",
         "    # from the laptop. Without this staging the run dies deep inside read_records() with a",
         "    # bare FileNotFoundError - AFTER the GPU is allocated and the pip installs are done.",
         "    # It stages ONLY the records: src/config/gold arrive with the embedded payload, which is",
         "    # extracted in the NEXT cell, so they are legitimately absent at this point.",
         "    _RECORDS = ['data/out/padt-train.jsonl', 'data/out/padt-dev.jsonl']",
         "    for _f in _RECORDS:",
         "        _dest = f'{ART}/{_f}'",
         "        if os.path.exists(_dest):",
         "            continue",
         "        os.makedirs(os.path.dirname(_dest), exist_ok=True)",
         "        # .gz IS THE PRACTICAL UPLOAD. These records compress ~12x (114 MB -> 8.5 MB,",
         "        # 15 MB -> 1.2 MB): the difference between a browser upload that crawls and one",
         "        # that is instant. A .gz beside every .jsonl is accepted and streamed back out,",
         "        # so this cell works whether what you pushed was raw or compressed.",
         "        _cands = []",
         "        for _src in (f'{CACHE}/{_f}', f'{CACHE}/data/out/{os.path.basename(_f)}',",
         "                     f'/content/data/out/{os.path.basename(_f)}', f'/content/{_f}'):",
         "            _cands.append(_src)",
         "            _cands.append(_src + '.gz')",
         "        for _src in _cands:",
         "            if not os.path.exists(_src):",
         "                continue",
         "            if _src.endswith('.gz'):",
         "                # A TRUNCATED UPLOAD MUST NOT BECOME A TRAINING SET. gzip raises on a bad",
         "                # stream; the partial output is deleted so a re-run re-stages rather than",
         "                # finding the half-file on disk and skipping the copy.",
         "                try:",
         "                    with gzip.open(_src, 'rb') as _fi, open(_dest, 'wb') as _fo:",
         "                        _n = 0",
         "                        while True:",
         "                            _chunk = _fi.read(1 << 20)",
         "                            if not _chunk:",
         "                                break",
         "                            _fo.write(_chunk)",
         "                            _n += len(_chunk)",
         "                except Exception as _e:",
         "                    if os.path.exists(_dest):",
         "                        os.remove(_dest)",
         "                    raise SystemExit('corrupt/truncated %s (%s: %s) - re-upload it'",
         "                                     % (_src, type(_e).__name__, _e))",
         "                print('  staged %s <- %s  (gunzipped %d bytes)' % (_f, _src, _n))",
         "            else:",
         "                shutil.copy2(_src, _dest)",
         "                print('  staged', _f, '<-', _src)",
         "            break",
         "    _missing = [f for f in _RECORDS if not os.path.exists(f'{ART}/{f}')]",
         "    assert not _missing, (",
         "        'Colab is missing ' + ', '.join(_missing) + '. Upload them ONCE to Drive at '",
         "        + CACHE + '/data/out/ and re-run (COLAB.md 2). These are the derived PADT '",
         "        'per-token records: 114 MB train / 15 MB dev raw, or 8.5 MB / 1.2 MB gzipped '",
         "        '(upload the .gz - same notebook, 12x less to push). Corpus-licensed, so they '",
         "        'cannot be embedded in the notebook, and they are not fetchable in-session.')",
         "    _res_dest = f'{ART}/data/resources/tashkeela_spelling_index.tsv.gz'",
         "    if not os.path.exists(_res_dest):",
         "        for _src in (f'{CACHE}/data/resources/tashkeela_spelling_index.tsv.gz',",
         "                     f'/content/data/resources/tashkeela_spelling_index.tsv.gz',",
         "                     f'{CACHE}/tashkeela_spelling_index.tsv.gz',",
         "                     f'/content/tashkeela_spelling_index.tsv.gz'):",
         "            if os.path.exists(_src):",
         "                os.makedirs(os.path.dirname(_res_dest), exist_ok=True)",
         "                shutil.copy2(_src, _res_dest)",
         "                print('  staged resource <-', _src)",
         "                break",
         "        if not os.path.exists(_res_dest):",
         "            print('  note: tashkeela_spelling_index.tsv.gz not found in Drive/content; v3_resource_on will degrade to rules-only')",
         "print('runtime:', 'kaggle' if ON_KAGGLE else 'colab')",
         "# SELF-REPORT THE DETECTION. Its absence is why this bug was invisible: the run",
         "# said 'kaggle' and blamed /kaggle/input, and nothing on screen said WHY it had",
         "# concluded Kaggle while the user was sitting in Colab.",
         "print('detect : KAGGLE_KERNEL_RUN_TYPE=%r  /kaggle/working=%s  google.colab=%s'",
         "      '  /var/colab/hostname=%s'",
         "      % (_KRT, _KW, _COLAB_IMPORT, _COLAB_FS))",
         "print('detect : -> IN_COLAB=%s  ON_KAGGLE=%s' % (IN_COLAB, ON_KAGGLE))",
         "print('ART    :', ART, '(writable)' if os.access(ART, os.W_OK) else '(READ-ONLY!)')",
         "print('CACHE  :', CACHE)"),

    md("## 3. Point at the code and derived data",
       "",
       "The corpora are NOT needed for training: `data/out/*.jsonl` already holds the per-token",
       "targets and masks, and the human gold is in `data/annotation/`. That also avoids",
       "CAMeL's 124 MB of data, since CALIMA is never called during training."),
    code("sys.path.insert(0, f'{ART}/src')",
         "os.chdir(ART)",
         "print('cwd    :', os.getcwd())",
         "print('src    :', len(os.listdir('src')), 'files')",
         "print('jsonl  :', sorted(os.path.basename(p) for p in",
         "                         glob.glob('data/out/*.jsonl')))",
         "print('gold   :', sorted(os.path.basename(p) for p in",
         "                         glob.glob('data/annotation/gold-*.jsonl')))",
         "print('resources:', sorted(os.path.basename(p) for p in",
         "                         glob.glob('data/resources/*')))"),

    md("## 4. ONE vocabulary for every run, and PARITY before a single step",
       "",
       "The vocabulary is a property of the **comparison**, not of one run: if each run built",
       "its own from its own corpus, the gold and silver runs would have different head",
       "sizes, their parameter counts would differ, and the matched-size claim would quietly",
       "die on exactly the head the ablation is about. So it is built once, over BOTH",
       "corpora, and passed to every run.",
       "",
       "Parity is then checked against the sizes that will actually be used — including",
       "`treatment_tower_hidden`, which had to be re-fitted (`tools/fit_parity_union.py` —",
       "NOT `model_arms.py --fit-parity`, which fits the PADT-only vocabulary rather than",
       "the union this run asserts on)",
       "for this vocabulary."),
    code("from model_arms import (load_config, read_records, Vocabs, Arm,",
         "                        parity_report, count_params, count_non_lookup_params, resolve_device)",
         "import eval_harness as EH",
         "",
         "cfg = load_config(smoke=False)",
         "device = resolve_device(cfg)",
         "GOLD_TR = read_records(cfg['paths']['train'], cfg['data']['limit_train'])",
         "GOLD_DV = read_records(cfg['paths']['dev'], cfg['data']['limit_dev'])",
         "SILV_TR = read_records(cfg['paths']['silver_train'], None)",
         "SILV_DV = read_records(cfg['paths']['silver_dev'], None)",
         "GOLD = EH.load_human_gold(cfg['paths']['human_gold'])",
         "print('gold   train records:', sum(len(t) for _, t in GOLD_TR))",
         "print('silver train records:', sum(len(t) for _, t in SILV_TR))",
         "print('human gold rows     :', len(GOLD))",
         "",
         "V = Vocabs(GOLD_TR + SILV_TR, cfg['data']['min_freq'], cfg['data']['max_vocab'])",
         "sizes = V.sizes()",
         "print('vocabs (ONE for all runs):', sizes)",
         "assert sizes['radical'] > 5, 'radical vocab degenerate - the translit bug is back'",
         "assert sizes['wazan'] > 5, 'wazan vocab degenerate'",
         "",
         "base_n, treat_n, gap = parity_report(cfg, sizes)",
         "if cfg['model'].get('treatment_tower_hidden') is None:",
         "    b_arm = Arm(cfg, sizes, 'baseline')",
         "    t_arm = Arm(cfg, sizes, 'treatment')",
         "    assert getattr(t_arm, 'h_surface', None) is None, 'PARITY FAIL: treatment must not have surface head'",
         "    surf_n = count_params(b_arm.h_surface)",
         "    base_nl = count_non_lookup_params(b_arm)",
         "    treat_nl = count_non_lookup_params(t_arm)",
         "    non_lookup_delta = abs(base_nl - treat_nl)",
         "    nl_gap = non_lookup_delta / max(base_nl, treat_nl)",
         "    assert nl_gap <= 0.05, (",
         "        f'PARITY FAIL: non-lookup gap {nl_gap:.4f} > 5% (delta: {non_lookup_delta:,} params)')",
         "    print(f'PARITY OK (pure inductive architecture: zero surface head on treatment, non-lookup delta {non_lookup_delta:,} params, gap {nl_gap*100:.2f}%)')",
         "else:",
         "    assert gap <= cfg['parity']['tolerance'], (",
         "        f'PARITY FAIL {gap:.4f} > {cfg[\"parity\"][\"tolerance\"]} - run'",
         "        ' `python tools/fit_parity_union.py`, then write its answer into'",
         "        ' config/shared.yaml -- NOT model_arms.py --fit-parity, which fits the'",
         "        ' PADT-only vocabulary rather than the union this run asserts on')",
         "    print('PARITY OK')",
         "",
         "# ---- FORWARD-PASS TEST: is the soft conditioning ACTUALLY ACTIVE here? -------------",
         "# A config flag is not evidence that a module exists AND is wired into the head. This",
         "# asserts both, on a model built from THIS config in THIS cloud environment:",
         "#   (1) the conditioning modules are present exactly when the flag says so (a bundle and",
         "#       a config that disagree would otherwise train an architecture nobody intended), and",
         "#   (2) ZEROING the conditioning path CHANGES THE ROOT LOGITS - the branch is load-bearing",
         "#       in the root head, not a no-op. A silently-dropped branch fails here.",
         "_cond = bool(cfg['model'].get('use_soft_wazan_conditioning', False))",
         "_probe = Arm(cfg, sizes, 'treatment').to(device).eval()",
         "_has = hasattr(_probe, 'wazan_to_root') and hasattr(_probe, 'h_wazan_bottleneck')",
         "assert _has == _cond, ('conditioning modules present=%s but config flag=%s - the bundle'",
         "                       ' and the config disagree' % (_has, _cond))",
         "if _cond:",
         "    _xb = torch.randint(2, min(200, sizes['surface']), (1, 8), device=device)",
         "    _wr = _probe.wazan_to_root",
         "    _keep = (_wr.weight.detach().clone(), _wr.bias.detach().clone())",
         "    # every mutation sits inside ONE no_grad block: an in-place write to a leaf that",
         "    # requires grad is a RuntimeError OUTSIDE no_grad (measured locally), and the restore",
         "    # is a write too - a probe that leaves the model mutated would poison the real runs.",
         "    with torch.no_grad():",
         "        _r1 = _probe(_xb)['root'].clone()",
         "        # zero the WHOLE layer (weight AND bias): identically zero means the branch",
         "        # contributes exactly nothing, so any difference IS the branch's real effect",
         "        _wr.weight.zero_()",
         "        _wr.bias.zero_()",
         "        _r2 = _probe(_xb)['root'].clone()",
         "        _wr.weight.copy_(_keep[0])",
         "        _wr.bias.copy_(_keep[1])",
         "    _delta = float((_r1 - _r2).abs().max())",
         "    assert _delta > 0, ('zeroing wazan_to_root did NOT change the root logits: the'",
         "                        ' conditioning branch is a no-op')",
         "    print('CONDITIONING ACTIVE: zeroing wazan_to_root moves root logits by %.4f' % _delta)",
         "    print('  (train and inference use the SAME dense bottleneck vector - no teacher'",
         "          ' forcing, so there is no train/eval representation mismatch to have)')",
         "else:",
         "    print('CONDITIONING OFF in this config')",
         "del _probe",
         "",
         "# ---- the valid-root inventory, for the SECOND decode (CHALLENGES 2aa) ----------",
         "# Built from the TRAINING label space ONLY, deliberately: the constraint has to be the",
         "# space the model was trained on, not a wider lexicon. Measured sensitivity: a",
         "# 2,499-root inventory moved whole-root +5.4 pp while a 6,247-root lexicon moved it",
         "# +2.2 pp - a bigger inventory constrains less, so it buys less.",
         "from final_surface import RootTrie",
         "ROOT_INV = set()",
         "for _corp in (GOLD_TR, SILV_TR):",
         "    for _si, _toks in _corp:",
         "        for _t in _toks:",
         "            if _t.get('m_root'):",
         "                _r = ''.join(c for c in _t['t_root'] if c)",
         "                if _r:",
         "                    ROOT_INV.add(_r)",
         "TRIE = RootTrie(ROOT_INV)",
         "print('valid-root inventory:', len(TRIE), 'roots (train label space) -> beamed decode')"),

    md("## 4b. PREFLIGHT GATE — prove this run's inputs before spending a GPU",
       "",
       "Everything below is checked rather than assumed, because every one of these has",
       "silently differed at some point in this project: the vocabulary (it changed with the",
       "sample), the parity pair (it moved 33% when `max_vocab` began binding at the spread",
       "sample), the conditioning flag (a bundle and a config once disagreed), and the data",
       "itself (the last \"120k sample\" was one book's opening and covered 0 of the 126 OOV",
       "gold words).",
       "",
       "**It stops.** Any mismatch raises. A run whose inputs are not the pre-registered ones",
       "answers a different question, and a GPU hour spent on a different question is worse",
       "than not running — the point of `docs/next-run-criteria.md` is that the comparison is",
       "decided in advance, and it is only decided if the inputs are the ones it names."),
    code("import hashlib, os",
         "",
         "# THE APPROVED INPUTS. The silver sha256s are the round-26 spread build (verified",
         "# deterministic: re-running locally with the same seed reproduced all three files",
         "# byte-for-byte). The PADT and gold files are pinned so an accidental re-derivation",
         "# of those cannot slip in unnoticed either.",
         "EXPECT_INPUTS = {",
         "    'data/out/padt-train.jsonl':",
         "        '6ae53007cb73581ae78bc107a8df7f87bed7879c47f97ebb1e58250b83052e6f',",
         "    'data/out/padt-dev.jsonl':",
         "        '71a720f07cbf1b3056467e872bf657bdca84a19cbc35ef4501f9df7b1b8af232',",
         "    # NO padt-test. The run never reads it (train.py reads train + dev, and no src/",
         "    # file references paths.test) and Colab stages only train + dev -- so requiring",
         "    # it made the gate fail on a clean Drive over a file nothing ever opens.",
         "    'data/annotation/gold-tashkeela-300.jsonl':",
         "        'edcdc2eecaaca1ff735f9ec2219d1bf2cfcb1075bfde97ce0a4c0fbc982ba40d',",
         "    'data/out/spread-B-2m/tashkeela-train.jsonl':",
         "        '6dfeace847ed24d8e686495285c061b03d949bc88cda6e84481d3fa24dc3b687',",
         "    'data/out/spread-B-2m/tashkeela-dev.jsonl':",
         "        '8bf74ed10bc02da2d440cc102ab405e0504a048ecee32e66dce459a8de0b960e',",
         "}",
         "",
         "print('=' * 74)",
         "print('PREFLIGHT GATE')",
         "print('=' * 74)",
         "for _k in ('train', 'dev', 'silver_train', 'silver_dev', 'human_gold'):",
         "    _p = cfg['paths'][_k]",
         "    assert os.path.exists(_p), 'config path %s -> %s does not exist' % (_k, _p)",
         "    print('  %-13s %s' % (_k, _p))",
         "",
         "# THE EFFECTIVE TRAINING VOLUME IS THE EXPERIMENT, so it is measured here from the",
         "# FILES. train() applies its limit to WHICHEVER path it is given, so one config-wide",
         "# limit hands BOTH arms 120,000 records and the 1.87M-token silver sample is never",
         "# read -- the run would repeat the previous result and read as a clean negative. The",
         "# limit actually passed is stated in the grid cell and printed by train() itself.",
         "print()",
         "print('EFFECTIVE TRAINING VOLUME (1 record = 1 token in this schema):')",
         "for _src, _rel, _lim in (('gold', cfg['paths']['train'], cfg['data']['limit_train']),",
         "                         ('silver', cfg['paths']['silver_train'], None)):",
         "    _n = 0",
         "    with open(_rel, encoding='utf-8') as _fh:",
         "        for _ln in _fh:",
         "            _n += 1",
         "            if _lim and _n >= _lim:",
         "                break",
         "    print('  %-7s %9d records   %s'",
         "          % (_src, _n, 'ALL (limit=None)' if _lim is None else 'LIMIT %d' % _lim))",
         "assert _n == 1871205, 'silver in full is not the approved 1,871,205 records'",
         "",
         "# THE CONFIG IS PINNED TO THE APPROVED FILE, not merely consistent with it.",
         "assert cfg['paths']['silver_train'] == 'data/out/spread-B-2m/tashkeela-train.jsonl'",
         "assert cfg['paths']['silver_dev'] == 'data/out/spread-B-2m/tashkeela-dev.jsonl'",
         "",
         "# EXPERIMENTAL INVARIANTS (docs/next-run-criteria.md). These are asserted, not just",
         "# printed: this run changes the SAMPLE, and if any of these moves too, no difference",
         "# can be attributed to data scale.",
         "assert cfg['data']['min_freq'] == 2, 'min_freq invariant changed'",
         "assert cfg['data']['max_vocab'] == 20000, (",
         "    'max_vocab invariant changed - raising the cap is the NEXT experiment, not this one')",
         "assert bool(cfg['model']['use_soft_wazan_conditioning']) is True, (",
         "    'conditioning must be ON: CHALLENGES 2ac found OFF costs the treatment its wazan head')",
         "assert len(cfg['seeds']) in (1, 3), 'seed count changed'",
         "# THE DRIVER'S DEFAULT IS ONE SEED, and this assert used to reject it -- a latent bug that",
         "# only surfaced once the run got past the staging cells: v16/v17/v18 all died earlier, so",
         "# nothing had ever reached this line. The invariant's point is that the seed count is not",
         "# arbitrarily varied between runs; 1 and 3 are the two DOCUMENTED modes (kaggle_run.py",
         "# trims to 1 unless --full-seeds). So allow both, and make an n=1 result label itself.",
         "if len(cfg['seeds']) == 1:",
         "    print('!! SEED COUNT = 1 - a SMOKE READ, not a verdict. The pre-registered protocol is 3'",
         "          ' seeds per arm (COLAB.md 4.2), and the n=1 run v13 was recorded as not a test.'",
         "          ' Re-run with --full-seeds before reporting a (W)/(E) pass as a result.')",
         "assert sizes['surface'] == 20000, (",
         "    'surface vocab is %s, not the approved 20000 entries (max_vocab binds at 20000,"
         " so the real word count is 19,998)' % sizes['surface'])",
         "print('  invariants : min_freq=2 max_vocab=20000 conditioning=ON seeds=%s' % cfg['seeds'])",
         "print('  vocab      : %s' % sizes)",
         "print('  loss       : %s' % cfg.get('loss'))",
         "print('  training   : %s' % cfg.get('training'))",
         "assert cfg['loss']['normalise_by_log_vocab'] is False, 'normalise_by_log_vocab must be False'",
         "assert 'stem_tail' in cfg['loss']['focal_heads'], 'stem_tail must be in focal_heads'",
         "assert cfg['training']['steps'] == 12000, 'training steps must be 12000'",
         "",
         "print()",
         "print('DATASET HASHES (this is the gate that would have caught the one-book sample):')",
         "_bad = []",
         "for _rel, _want in EXPECT_INPUTS.items():",
         "    if not os.path.exists(_rel):",
         "        print('  %-46s MISSING' % _rel)",
         "        _bad.append(_rel)",
         "        continue",
         "    _h = hashlib.sha256()",
         "    with open(_rel, 'rb') as _fh:",
         "        for _c in iter(lambda: _fh.read(1 << 20), b''):",
         "            _h.update(_c)",
         "    _got = _h.hexdigest()",
         "    _ok = _got == _want",
         "    print('  %-46s %s  %s' % (_rel, _got[:16], 'MATCH' if _ok else 'DIFFERS'))",
         "    if not _ok:",
         "        _bad.append('%s (got %s, approved %s)' % (_rel, _got[:16], _want[:16]))",
         "",
         "print()",
         "print('PARITY:')",
         "print('  baseline  : %12d params' % base_n)",
         "print('  treatment : %12d params' % treat_n)",
         "if cfg['model'].get('treatment_tower_hidden') is None:",
         "    print('  delta     : %12d params (identically surface LM head)' % (base_n - treat_n))",
         "else:",
         "    print('  gap       : %8.4f%%  (tolerance %.2f%%)' % (gap * 100,",
         "                                                        cfg['parity']['tolerance'] * 100))",
         "print('  FINGERPRINT for this architecture: %s / %s' % (f'{base_n:,}', f'{treat_n:,}'))",
         "print('    v14 printed 13,087,021 / 13,087,117; v15 printed 13,436,845 / 13,436,941.')",
         "print('    A DIFFERENT fingerprint here is EXPECTED; matching either IS a mix-up.')",
         "",
         "if _bad:",
         "    raise SystemExit('PREFLIGHT FAILED - inputs differ from the approved build: %s'",
         "                     % _bad)",
         "print()",
         "print('PREFLIGHT OK - inputs, vocabulary, invariants and parity match the approved build')"),
    md("## 5. Train the 12-run grid: {gold, silver} x {treatment, baseline} x 3 seeds",
       "",
       "Same config, same vocabulary, same steps, same seeds. The ONLY things that move are",
       "the arm and the training target's source. `save_steps` is short enough that a 12 h",
       "cutoff costs minutes (COLAB.md §3)."),
    code("import json, time, torch",
         "from train import train, evaluate",
         "",
         "ABL = {'gold':   (cfg['paths']['train'],        cfg['paths']['dev']),",
         "       'silver': (cfg['paths']['silver_train'], cfg['paths']['silver_dev'])}",
         "DEVS = {'gold': GOLD_DV, 'silver': SILV_DV}",
         "",
         "# THE ROUND-26 VARIABLE IS SILVER VOLUME, SO IT IS STATED HERE. train() applies its",
         "# limit to WHICHEVER path it is given, so one config-wide limit makes BOTH arms read",
         "# 120,000 records: the 1.87M-token silver sample would be truncated in silence, the",
         "# run would repeat the previous result, and the pre-registered criteria would read",
         "# that as evidence against the data-scale hypothesis. gold keeps the matched-volume",
         "# limit; silver reads IN FULL (None), which is what makes the mismatch real.",
         "TRAIN_LIMIT = {'gold': cfg['data']['limit_train'], 'silver': None}",
         "",
         "RESULTS, GOLDSC, MODELS, TRAINING = {}, {}, {}, {}",
         "for src in ('gold', 'silver'):",
         "    for arm in ('treatment', 'baseline'):",
         "        for seed in cfg['seeds']:",
         "            tag = src + '-' + arm + '-s' + str(seed)",
         "            t0 = time.time()",
         "            ckpt = CACHE + '/checkpoints/' + tag + '.pt'",
         "            if RESCORE_ONLY:",
         "                # NO TRAINING. Load what this run already produced and re-score it. The",
         "                # vocabulary travels INSIDE the checkpoint and the checkpoint's own cfg",
         "                # is checked against this cell's cfg, so a rescore cannot silently",
         "                # score a model with a different vocabulary or recipe than it trained.",
         "                assert os.path.exists(ckpt), 'missing checkpoint for ' + tag",
         "                blob = torch.load(ckpt, map_location='cpu')",
         "                assert blob['cfg'] == cfg, tag + ' was trained under a different config'",
         "                assert blob['vocab'] == V.to_dict(), (tag + ': the checkpoint vocabulary'",
         "                                                       ' is not this run vocabulary')",
         "                model = Arm(cfg, sizes, arm).to(device)",
         "                model.load_state_dict(blob['model'])",
         "                model.eval()",
         "                hist = []",
         "            else:",
         "                model, hist, _, _ = train(cfg, arm, seed, device, quiet=False,",
         "                                          train_path=ABL[src][0], dev_path=ABL[src][1],",
         "                                          vocab_sents=V,",
         "                                          train_limit=TRAIN_LIMIT[src])",
         "                torch.save({'model': model.state_dict(), 'cfg': cfg, 'arm': arm,",
         "                            'seed': seed, 'source': src, 'sizes': sizes,",
         "                            # the vocab must travel WITH the weights, or the",
         "                            # checkpoint cannot be scored anywhere the training",
         "                            # records are absent (round 17 lost one that way)",
         "                            'vocab': V.to_dict()}, ckpt)",
         "            MODELS[tag] = ckpt",
         "            RESULTS[tag] = {'in_domain_dev': evaluate(model, DEVS[src], V, cfg,",
         "                                                      sizes, device, trie=TRIE)}",
         "            if src == 'silver':",
         "                # the silver model is ALSO scored on PADT dev, so the two target",
         "                # sources are comparable on a shared SILVER-free reference too.",
         "                # This is cross-domain and is reported as such (cell 7).",
         "                RESULTS[tag]['padt_dev'] = evaluate(model, GOLD_DV, V, cfg,",
         "                                                    sizes, device, trie=TRIE)",
         "            GOLDSC[tag] = EH.score_human_gold(model, V, GOLD, device,",
         "                                              cfg['data']['max_len'], trie=TRIE)",
         "            # `train_tokens` IS RECORDED, NOT JUST PRINTED. Without it the artifact cannot",
         "            # prove its own data scale -- and the round-26 variable IS silver volume, which",
         "            # otherwise lives only in a kernel log that is not part of the artifact.",
         "            _tk = sum(len(t) for _, t in (SILV_TR if src == 'silver' else GOLD_TR))",
         "            TRAINING[tag] = {'seconds': round(time.time() - t0, 1), 'arm': arm,",
         "                             'source': src, 'seed': seed,",
         "                             'train_tokens': _tk, 'train_limit': TRAIN_LIMIT[src],",
         "                             'rescored': bool(RESCORE_ONLY)}",
         "            print('  ' + tag + ': %.0fs -> %s' % (time.time() - t0, ckpt), flush=True)",
         "print('scored:' if RESCORE_ONLY else 'trained:', sorted(RESULTS))"),

    md("## 6. Score every model against the 278 HUMAN patterns",
       "",
       "The gold rows carry their own sentence, so the same function scores a PADT-trained",
       "and a Tashkeela-trained model — nothing has to be located in either corpus. FOUR",
       "wazān columns, because the human gold and the CALIMA pipeline use different",
       "spellings for the same grammar:",
       "",
       "- `wz_raw` — exact string. The honest primary figure.",
       "- `wz_norm` — leading hamzated radical normalised (`أُ1ُ2ُو3` = `1ُ2ُو3`, and the",
       "  annotator wrote أُصُول exactly that way).",
       "- `wz_slots` — do the two agree about WHICH SLOTS hold radicals, ignoring how a weak",
       "  radical is spelled. MEASURED on the label side alone: the exact string agrees on",
       "  28% of gold rows while the slot set agrees on **99%**, so most of the exact-string",
       "  gap is a convention difference (`123` vs `1َا2َ3` for وَقَالَ), not a grammar error.",
       "- `wz_case` — the hamza-normalised, diacritic-free variant, a lower bound.",
       "",
       "`gold_context_oov_rate` is the fraction of gold-context tokens the vocabulary has",
       "never seen. It is a COVERAGE property of the vocabulary over FIXED contexts, not a",
       "model score: being constant across arms and seeds by construction, it is recorded",
       "ONCE with its vocabulary metadata and never compared arm-to-arm (see cell 7)."),
    code("print('HUMAN GOLD - %d rows, single annotator, no inter-annotator agreement'",
         "      % len(GOLD))",
         "print('%-30s %7s %7s %7s %7s %7s %7s %7s %7s' % ('run', 'wz_raw', 'wz_mat', 'st_suff',",
         "                                                  'root_bm', 'caseF1', 'fs_joint', 'fs_on', 'ctx_oov'))",
         "for tag in sorted(GOLDSC):",
         "    g = GOLDSC[tag]",
         "    c = g.get('case', {})",
         "    fs_j = (g.get('final_surface', {}).get('v3_resource_off_joint') or {}).get('stem_yield', 0.0)",
         "    fs_on = (g.get('final_surface', {}).get('v3_resource_on') or {}).get('stem_yield', 0.0)",
         "    print('%-30s %7.3f %7.3f %7.3f %7.3f %7.3f %7.3f %7.3f %7.3f' % (",
         "        tag, (g.get('wazan_strict_raw') or g['wazan'])['accuracy'],",
         "        (g.get('wazan_mater_canon') or g['wazan'])['accuracy'],",
         "        (g.get('stem_tail') or {}).get('suffixed_only_accuracy', 0.0),",
         "        (g.get('root_whole_beamed') or g['root'])['accuracy'],",
         "        c.get('macro_f1', float('nan')), fs_j, fs_on, g['oov_rate']))",
         "first = GOLDSC[sorted(GOLDSC)[0]]",
         "print()",
         "print('n   : %d gold patterns, %d gold roots, %d gold cases (of %d rows)'",
         "      % (first['wazan']['n'], first['root']['n'], first.get('case', {}).get('n', 0),",
         "         first['gold_rows']))",
         "print('case majority-class macro-F1 (the worthless baseline):',",
         "      first['case_majority_macro_f1'])",
         "print()",
         "print('MISMATCH EXAMPLES from the first run - read these before reading the raw'",
         "      ' column as a grammatical error rate:')",
         "for m in first['wazan_mismatch_examples'][:8]:",
         "    print('   ', m)"),

    md("## 7. Report every score BESIDE its ceiling, and the arm difference against the SEED SPREAD",
       "",
       "Case metrics come from `src/eval_harness.py` (via `train.evaluate`): per-class",
       "precision/recall/F1 plus **macro-F1** and the **majority-class baseline**, never raw",
       "accuracy — an always-`GEN` predictor scores high accuracy and is worthless.",
       "",
       "The CALIMA ceilings (rev. 11) are **case macro-F1 0.459** and **root 0.451/0.444**.",
       "They measure CALIMA-vs-HUMAN agreement, so a GOLD-trained arm beating them proves",
       "nothing (it was taught the answers); only the SILVER rows are a ceiling comparison."),
    code("import json, hashlib, statistics as st",
         "",
         "CEIL = {'case_macro_f1': 0.459, 'root_accuracy': 0.451}",
         "",
         "def flat(tag):",
         "    t = TRAINING[tag]",
         "    dom = RESULTS[tag]['in_domain_dev']",
         "    padt = RESULTS[tag].get('padt_dev') or dom",
         "    g = GOLDSC[tag]",
         "    return {'arm': t['arm'], 'source': t['source'], 'seed': t['seed'],",
         "            'in_domain_case_macro_f1': dom.get('case', {}).get('macro_f1'),",
         "            'in_domain_root_acc': dom.get('root', {}).get('accuracy'),",
         "            'in_domain_root_whole': dom.get('root_whole', {}).get('accuracy'),",
         "            'in_domain_root_whole_beamed': (dom.get('root_whole_beamed') or {}).get('accuracy'),",
         "            'in_domain_stem_tail_suffixed': (dom.get('stem_tail') or {}).get('suffixed_only_accuracy'),",
         "            'padt_dev_case_macro_f1': padt.get('case', {}).get('macro_f1'),",
         "            'padt_dev_root_acc': padt.get('root', {}).get('accuracy'),",
         "            'padt_dev_root_whole': padt.get('root_whole', {}).get('accuracy'),",
         "            'padt_dev_root_whole_beamed': (padt.get('root_whole_beamed') or {}).get('accuracy'),",
         "            'padt_dev_stem_tail_suffixed': (padt.get('stem_tail') or {}).get('suffixed_only_accuracy'),",
         "            'gold_wazan_strict_raw': (g.get('wazan_strict_raw') or {}).get('accuracy'),",
         "            'gold_wazan_mater_canon': (g.get('wazan_mater_canon') or {}).get('accuracy'),",
         "            'gold_wazan_raw': g['wazan']['accuracy'],",
         "            'gold_wazan_norm': g['wazan_hamza_normalised']['accuracy'],",
         "            'gold_wazan_slots': g['wazan_radical_slots']['accuracy'],",
         "            'gold_stem_tail_suffixed': (g.get('stem_tail') or {}).get('suffixed_only_accuracy'),",
         "            'gold_root': g['root']['accuracy'],",
         "            'gold_root_beamed': (g.get('root_whole_beamed') or {}).get('accuracy'),",
         "            'gold_case_macro_f1': g.get('case', {}).get('macro_f1'),",
         "            'gold_v3_res_off_joint': (g.get('final_surface', {}).get('v3_resource_off_joint') or {}).get('stem_yield'),",
         "            'gold_v3_res_off_argmax': (g.get('final_surface', {}).get('v3_resource_off_argmax') or {}).get('stem_yield'),",
         "            'gold_v3_res_on': (g.get('final_surface', {}).get('v3_resource_on') or {}).get('stem_yield'),",
         "            'gold_context_oov_rate': g['oov_rate']}",
         "",
         "FLAT = {t: flat(t) for t in RESULTS}",
         "",
         "def spread(source, arm, metric):",
         "    xs = [FLAT[t][metric] for t in FLAT if FLAT[t]['source'] == source",
         "          and FLAT[t]['arm'] == arm and FLAT[t][metric] is not None]",
         "    if not xs:",
         "        return None",
         "    return {'n': len(xs), 'mean': st.fmean(xs),",
         "            'sd': (st.stdev(xs) if len(xs) > 1 else 0.0),",
         "            'min': min(xs), 'max': max(xs), 'vals': xs}",
         "",
         "METRICS = ('in_domain_case_macro_f1', 'in_domain_root_acc',",
         "           'in_domain_root_whole', 'in_domain_root_whole_beamed',",
         "           'in_domain_stem_tail_suffixed',",
         "           'padt_dev_case_macro_f1',",
         "           'padt_dev_root_whole', 'padt_dev_root_whole_beamed',",
         "           'padt_dev_stem_tail_suffixed',",
         "           'gold_wazan_strict_raw', 'gold_wazan_mater_canon',",
         "           'gold_wazan_raw', 'gold_wazan_norm', 'gold_wazan_slots',",
         "           'gold_stem_tail_suffixed',",
         "           'gold_root', 'gold_root_beamed',",
         "           'gold_case_macro_f1',",
         "           'gold_v3_res_off_joint', 'gold_v3_res_on')",
         "print('=== {gold, silver} x {treatment, baseline} x %d seeds: mean [sd], and the'",
         "      ' difference against the seed spread ===' % len(cfg['seeds']))",
         "SUMMARY = {}",
         "for source in ('gold', 'silver'):",
         "    print()",
         "    print('--- target =', source, '---')",
         "    for metric in METRICS:",
         "        a = spread(source, 'treatment', metric)",
         "        b = spread(source, 'baseline', metric)",
         "        if not a or not b:",
         "            continue",
         "        d = a['mean'] - b['mean']",
         "        ref = max(a['sd'], b['sd'])",
         "        # THE VERDICT RULE NEEDS n > 1 TO MEAN ANYTHING. With one seed per arm, sd is 0 by",
         "        # construction, so `abs(d) > 2*ref` becomes `abs(d) > 0` and stamps SEPARATED on a",
         "        # 0.002 difference. v13 ran at n=1 and did exactly that. Report NOT TESTED instead of",
         "        # laundering a single-seed difference as a result.",
         "        n_min = min(a['n'], b['n'])",
         "        if n_min < 2:",
         "            verdict = ('NOT TESTED (n=%d per arm: sd is 0 by construction, so the 2*sd rule'",
         "                       ' would stamp any nonzero difference SEPARATED)' % n_min)",
         "        else:",
         "            verdict = ('SEPARATED' if abs(d) > 2 * ref else 'NOT SEPARATED')",
         "            if n_min < 3:",
         "                verdict += ' (n=%d: weak)' % n_min",
         "        SUMMARY[source + '/' + metric] = {'treatment': a, 'baseline': b,",
         "                                          'diff': d, 'verdict': verdict}",
         "        print('%-22s treat %.3f [%.3f]  base %.3f [%.3f]  d=%+.3f  (%s)'",
         "              % (metric, a['mean'], a['sd'], b['mean'], b['sd'], d, verdict))",
         "",
         "print()",
         "print('=== ceiling check: ONLY the human-gold rows may be compared to the CALIMA ceiling ===')",
         "print('    The ceiling (case %.3f / root %.3f) is CALIMA-vs-HUMAN agreement, so it bounds'",
         "      % (CEIL['case_macro_f1'], CEIL['root_accuracy']))",
         "print('    exactly one quantity: a model SCORED ON THE HUMAN GOLD. An in-domain dev score is'",
         "      )",
         "print('    measured against the SAME labeler the silver arm trained on, so that ceiling does'",
         "      )",
         "print('    not bound it at all. v13 printed in_domain 0.798 beside ceiling 0.459 and stamped it'",
         "      )",
         "print('    \"valid\" — a wrong comparison; the comparable number was gold_case_macro_f1 0.454.'",
         "      )",
         "for source in ('gold', 'silver'):",
         "    cm = spread(source, 'treatment', 'gold_case_macro_f1')",
         "    rm = spread(source, 'treatment', 'gold_root')",
         "    dm = spread(source, 'treatment', 'in_domain_case_macro_f1')",
         "    if not cm or not rm:",
         "        continue",
         "    if source == 'gold':",
         "        note = ('INVALID as a ceiling comparison: this arm trained on PADT gold,'",
         "                ' the ceiling measures CALIMA-vs-human. Round 16 caught exactly this.')",
         "    else:",
         "        note = 'valid: this arm trained on silver, so the ceiling is a real reference.'",
         "    print('target=%s  HUMAN-GOLD case macro-F1 %.3f (ceiling %.3f)  HUMAN-GOLD root %.3f'",
         "          ' (ceiling %.3f)'",
         "          % (source, cm['mean'], CEIL['case_macro_f1'], rm['mean'],",
         "             CEIL['root_accuracy']))",
         "    if dm:",
         "        print('    NOT a ceiling quantity: its own in-domain dev case macro-F1 = %.3f'",
         "              % dm['mean'])",
         "    print('    ' + note)",
         "",
         "# RECORDED ONCE, WITH ITS VOCABULARY. `oov_rate` is the share of the FIXED human-gold",
         "# context tokens that the one shared vocabulary has never seen: a property of the",
         "# vocabulary and the fixed contexts, identical in all 12 runs (measured sd 0.0000).",
         "# It is a COVERAGE quantity, not a model metric, so it is stated once here beside the",
         "# vocabulary it belongs to instead of standing in a per-arm verdict table.",
         "CONTEXT_COVERAGE = {",
         "    'gold_context_oov_rate': first['oov_rate'],",
         "    'gold_rows': first['gold_rows'],",
         "    'vocabulary': {'min_freq': cfg['data']['min_freq'],",
         "                   'max_vocab': cfg['data']['max_vocab'], 'sizes': sizes},",
         "    'note': ('fixed human-gold contexts x ONE shared vocabulary; constant across arms'",
         "             ' and seeds by construction, so it is never compared arm-to-arm'),",
         "}",
         "print()",
         "print('CONTEXT COVERAGE (recorded once -- a vocabulary property, NOT an arm result):')",
         "print('  gold_context_oov_rate = %.4f over %d human-gold rows'",
         "      % (CONTEXT_COVERAGE['gold_context_oov_rate'], CONTEXT_COVERAGE['gold_rows']))",
         "print('  vocabulary: min_freq=%s max_vocab=%s  surface=%s wazan=%s char=%s'",
         "      % (cfg['data']['min_freq'], cfg['data']['max_vocab'], sizes['surface'],",
         "         sizes['wazan'], sizes['char']))",
         "",
         "out = CACHE + '/results/results.json'",
         "with open(out, 'w', encoding='utf-8') as fh:",
         "    json.dump({'results': RESULTS, 'gold_scored': GOLDSC, 'flat': FLAT,",
         "               'summary': SUMMARY, 'training': TRAINING, 'ceilings': CEIL,",
         "               'context_coverage': CONTEXT_COVERAGE,",
         "               'config': cfg,",
         "               # PROVENANCE, so the artifact identifies its own code+config rather than",
         "               # relying on someone finding the right kernel log later. `code_bundle_sha`",
         "               # covers src/ AND config/shared.yaml (both are inside the embedded bundle);",
         "               # `config_sha256` pins the parsed config object on its own.",
         "               'code_bundle_sha': EXPECT_SHA,",
         "               'config_sha256': hashlib.sha256(",
         "                   json.dumps(cfg, sort_keys=True, default=str).encode()).hexdigest(),",
         "               'seeds': list(cfg['seeds']),",
         "               'parity': {'gap': gap, 'baseline': base_n, 'treatment': treat_n,",
         "                          'tolerance': cfg['parity']['tolerance'],",
         "                          'exact_match': bool(base_n == treat_n)},",
         "               'vocab_sizes': sizes}, fh, indent=2, default=str)",
         "print()",
         "print('wrote', out)"),

    md("## 8. Before you quote anything",
       "",
       "- [ ] Both arms ran on the **same config, steps, seeds, vocabulary** (asserted in cell 4).",
       "- [ ] Parameter counts printed and matched (asserted in cell 4).",
       "- [ ] **Which target the run trained on is stated with every number** — a gold-trained",
       "      score beside the CALIMA ceiling is meaningless (round-16 caveat 1).",
       "- [ ] Arm differences are quoted **against the seed spread**, not on their own; a",
       "      difference smaller than ~2x the seed sd is not a result at either sign.",
       "- [ ] The **gold-scored** columns carry the single-annotator/no-IAA caveat.",
       "- [ ] The wazān raw column is not silently replaced by the hamza-normalised one;",
       "      both are reported together.",
       "- [ ] Surface/vocalization results are reported **separately** from head metrics — the",
       "      renderer is ~11% exact, so a blended number would be meaningless.",
       "- [ ] Syntax and NTP are **0% supervised** on the silver side (masked, not faked).",
       "- [ ] Notebook stays **private**."),
]


def embed_cells() -> list:
    """The cells that ship the CODE and then BUILD the silver records in-cloud.

    Generated rather than hand-written, so the payload can never disagree with the code
    that produced it: the zip is built from this repo, and its sha256 is asserted at run
    time — a stale payload fails loudly instead of training on the wrong code.
    """
    chunks, sha, nfiles = embedded_bundle()
    head = md("## 2b. The code and the human gold, embedded in this notebook",
              "",
              "Kaggle's dataset API will not accept an upload (see this file's docstring) and",
              "the kernel source is capped at **<1 MB**, so `src/`, `config/` and the human gold",
              "ride here as base64 and are written out below — 251 KB, which fits. The PADT",
              "records come from the attached `arabic-dataset` and were merged in cell 2.",
              "",
              "Two guards, because the failure that matters is not transport but a SILENTLY",
              "STALE payload: the zip's sha256 is asserted, and so is the file count.")
    body = code(
        "import base64, hashlib, io, zipfile",
        "",
        f"EXPECT_SHA = {sha!r}",
        f"EXPECT_FILES = {nfiles}",
        "EMBED_CHUNKS = [",
        *[f"    {c!r}," for c in chunks],
        "]",
        "BLOB = base64.b64decode(''.join(EMBED_CHUNKS))",
        "print('embedded code bundle: %d bytes  sha256 %s'",
        "      % (len(BLOB), hashlib.sha256(BLOB).hexdigest()[:16]))",
        "assert hashlib.sha256(BLOB).hexdigest() == EXPECT_SHA, (",
        "    'embedded payload does not match the build that produced this notebook -'",
        "    ' regenerate with `python src/make_notebook.py`')",
        "with zipfile.ZipFile(io.BytesIO(BLOB)) as z:",
        "    names = z.namelist()",
        "    z.extractall(ART)",
        "print('extracted %d files (expected %d)' % (len(names), EXPECT_FILES))",
        "assert len(names) == EXPECT_FILES, 'payload file count changed: %d' % len(names)",
        "missing_code = [f for f in NEEDED_BASE if not os.path.exists(ART + '/' + f)]",
        "assert not missing_code, 'still incomplete after the embedded code: %s' % missing_code",
        "print('code + gold in place')",
    )
    build_head = md("## 2c. Build the SILVER (Tashkeela) records in-cloud",
                    "",
                    "This is the step COLAB.md always prescribed for Tashkeela — *stream it in the",
                    "cloud* — forced here by the 1 MB kernel-source cap. It runs **the same",
                    "`build_training_jsonl.py --source tashkeela`** the local run used: a build, not a",
                    "re-implementation, so the artifact is the one the smoke tests cover.",
                    "",
                    "`arramooz-pysqlite` is NOT optional. The root targets come from a gold-derived",
                    "dictionary whose second source is arramooz; without it the dictionary falls from",
                    "**40,265 keys to 13,736** and root supervision silently gets worse — a change that",
                    "would look like a modelling result. The cell prints the dictionary size it got.",
                    "",
                    "Budget: ~10-15 min (camel-tools + 130 MB of CALIMA data, then ~400 MB of books).")
    build = code(
        "import json, subprocess, sys, time",
        "",
        "def run(cmd, **kw):",
        "    print('$ ' + ' '.join(cmd), flush=True)",
        "    t0 = time.time()",
        "    r = subprocess.run(cmd, **kw)",
        "    print('  exit %d in %.0fs' % (r.returncode, time.time() - t0), flush=True)",
        "    assert r.returncode == 0, 'command failed: ' + ' '.join(cmd)",
        "    return r",
        "",
        "run([sys.executable, '-m', 'pip', 'install', '-q', 'camel-tools==1.6.0',",
        "     'arramooz-pysqlite==0.4.2'])",
        "# CAMeL's data packages are the easy thing to forget; without them",
        "# MLEDisambiguator.pretrained() cannot be constructed at all.",
        "run([sys.executable, '-m', 'camel_tools.cli.camel_data', '-i',",
        "     'morphology-db-msa-r13'])",
        "run([sys.executable, '-m', 'camel_tools.cli.camel_data', '-i',",
        "     'disambig-mle-calima-msa-r13'])",
        "",
        "import glob, gzip, hashlib, os, shutil, yaml",
        "",
        "# *** ROUND 26: THE SPREAD SAMPLE (CHALLENGES 2ae/2af). ***",
        "# --limit counts TOKENS, and the old in-order build spent the whole budget inside the",
        "# FIRST book it opened: the '120k training set' was the opening of book 8 and covered",
        "# 0 of the 126 OOV gold words. --allocate spread divides the budget across every book",
        "# and starts each at a seeded random window. --no-resume because a spread sample",
        "# cannot resume: a partial spread file is neither the allocated nor the seeded one.",
        "#",
        "# WRITE WHERE THE CONFIG READS. Taken FROM config/shared.yaml rather than typed twice:",
        "# this cell used to build into the DEFAULT data/out/ while the config (and the gate)",
        "# read data/out/spread-B-2m/, so the build could not satisfy its own gate and a fresh",
        "# machine would have failed on files that were never the ones under test.",
        "_cfg = yaml.safe_load(open(f'{ART}/config/shared.yaml', encoding='utf-8'))",
        "_tr_rel = os.path.dirname(_cfg['paths']['silver_train'])",
        "assert _tr_rel == os.path.dirname(_cfg['paths']['silver_dev']), 'silver dirs differ'",
        "SILVER = _tr_rel",
        "SILVER_DIR = f'{ART}/{SILVER}'",
        "os.makedirs(SILVER_DIR, exist_ok=True)",
        "print('silver dir (read from config):', SILVER)",
        "",
        "# DELETE FIRST. A stale tashkeela-*.jsonl from an earlier round would otherwise be",
        "# silently reused, the build would 'succeed', and the run would train on the wrong",
        "# data -- which is the exact failure this cell exists to prevent.",
        "for _stale in ('train', 'dev', 'test'):",
        "    _p = f'{SILVER_DIR}/tashkeela-{_stale}.jsonl'",
        "    if os.path.exists(_p):",
        "        os.remove(_p)",
        "        print('  removed stale', _p)",
        "# *** STAGE FIRST; BUILD ONLY IF THE UPLOAD IS NOT THERE. *** The approved records are",
        "# a FIXED artifact of a DETERMINISTIC sampler, so rebuilding them buys nothing the",
        "# upload does not already have -- and the rebuild is 18.5 min of CPU (measured)",
        "# GPU-allocated session, spending compute units on work already done (MEASURED:",
        "# 16.2 + 1.3 + 1.0 min per split = 18.5 min of CPU, from the build manifest). Upload",
        "#   MyDrive/arabic-root-tree/data/out/spread-B-2m/tashkeela-{train,dev,test}.jsonl.gz",
        "# (65.1 / 5.2 / 4.0 MB) and this cell skips the build entirely. It is ALL THREE or",
        "# none: --no-resume refuses to touch files it finds, so a half-staged set must build",
        "# the whole set rather than mix staged records with built ones.",
        "_cand = {}",
        "_in_hits = 0",
        "for _s in ('train', 'dev', 'test'):",
        "    # SILVER IS ALREADY THE FULL RELATIVE DIR ('data/out/spread-B-2m'), so it must NOT",
        "    # be prefixed with data/out/ a second time: that built data/out/data/out/spread-B-2m,",
        "    # which never exists, so a CORRECT upload still staged 0/3 and silently paid the",
        "    # 18.5-min build. Caught by tools/verify_notebook_joint.py EXECUTING this block.",
        "    # THE DATASET IS THE DELIVERY CHANNEL (2026-10-13): the approved records ride in the",
        "    # attached dataset, so search /kaggle/input FIRST. A dataset-mounted .jsonl.gz needs no",
        "    # build at all and the run then trains on the PRE-REGISTERED bytes. The measured failure",
        "    # that motivates it: the in-cloud build re-fetched a 1.08 GB corpus differing by 97 BYTES,",
        "    # ground for 35.4 min INSIDE a GPU-metered session, then failed the output-hash gate --",
        "    # 0.59 GPU-h for nothing. The build stays as a fallback; it must simply not be reached.",
        # `.jsonl*` — BOTH forms, and that is not cosmetic. The dataset now carries the approved
        # records as RAW `.jsonl` (measured on the mount: tashkeela-train.jsonl 1,054,255,107 —
        # the approved size), while an earlier plan shipped them gzipped. Matching only `.jsonl.gz`
        # staged 0/3 against a dataset that was already correct, and fell through to the 35-minute
        # build: the data was fine and the PROBE was wrong. The sha256 check below is what makes
        # accepting either form safe — location and compression cannot make a wrong file right.
        "    _in = (sorted(glob.glob(f'{INPUT}/**/tashkeela-{_s}.jsonl*', recursive=True))",
        "           if 'INPUT' in dir() else [])",
        "    _in_hits += len(_in)",
        "    for _c in tuple(_in) + (f'{CACHE}/{SILVER}/tashkeela-{_s}.jsonl.gz',",
        "               f'{CACHE}/{SILVER}/tashkeela-{_s}.jsonl',",
        "               f'{CACHE}/data/out/tashkeela-{_s}.jsonl.gz',",
        "               f'{SILVER_DIR}/tashkeela-{_s}.jsonl.gz',",
        "               # A FLAT UPLOAD straight into the arabic-root-tree folder is accepted",
        "               # too. Being liberal about WHERE the file sits costs nothing, because",
        "               # the CONTENT is verified by sha256 below: location cannot make a wrong",
        "               # file right, and a misplaced CORRECT file no longer costs a rebuild.",
        "               f'{CACHE}/tashkeela-{_s}.jsonl.gz',",
        "               f'{CACHE}/tashkeela-{_s}.jsonl'):",
        "        if os.path.exists(_c):",
        "            _cand[_s] = _c",
        "            break",
        "# THE MANIFEST IS PART OF THE SET (38 KB). The book-split assertions read it, so a",
        "# staged run needs it as much as a built one -- staging it here is what makes the",
        "# upload set exactly FOUR files instead of three plus a separate surprise.",
        "_man_c = None",
        "_man_in = (sorted(glob.glob(f'{INPUT}/**/build_manifest_tashkeela.json', recursive=True))",
        "           if 'INPUT' in dir() else [])",
        "for _c in tuple(_man_in) + (f'{SILVER_DIR}/build_manifest_tashkeela.json',",
        "           f'{CACHE}/{SILVER}/build_manifest_tashkeela.json',",
        "           f'{CACHE}/data/out/build_manifest_tashkeela.json',",
        "           f'{CACHE}/build_manifest_tashkeela.json'):",
        "    if os.path.exists(_c):",
        "        _man_c = _c",
        "        break",
        "if len(_cand) == 3 and _man_c:",
        "    for _s, _c in _cand.items():",
        "        _dest = f'{SILVER_DIR}/tashkeela-{_s}.jsonl'",
        "        if _c.endswith('.gz'):",
        "            try:",
        "                with gzip.open(_c, 'rb') as _fi, open(_dest, 'wb') as _fo:",
        "                    shutil.copyfileobj(_fi, _fo, 1 << 20)",
        "            except Exception as _e:",
        "                if os.path.exists(_dest):",
        "                    os.remove(_dest)",
        "                raise SystemExit('corrupt/truncated %s (%s: %s) -- re-upload it'",
        "                                 % (_c, type(_e).__name__, _e))",
        "        else:",
        "            shutil.copy2(_c, _dest)",
        "        print('  staged %-22s <- %s' % (os.path.basename(_dest), _c))",
        "    if _man_c != f'{SILVER_DIR}/build_manifest_tashkeela.json':",
        "        shutil.copy2(_man_c, f'{SILVER_DIR}/build_manifest_tashkeela.json')",
        "        print('  staged build_manifest_tashkeela.json <-', _man_c)",
        "    print('  STAGED all FOUR files: the build is SKIPPED.')",
        "else:",
        "    # ASSERT THE ROUTE, NOT THE RESULT: if the dataset supplied the approved records, the slow",
        "    # path must NOT run. A successful fallback masks a broken fast path -- this cell once staged",
        "    # 0/3 with every file present and silently paid an 18.5-minute rebuild.",
        "    assert _in_hits < 3, ('the dataset supplied all three approved records under %s but this'",
        "                          ' cell is about to REBUILD them: the fast path is broken' % INPUT)",
        "    print('  staged %d/3 records, manifest=%s -> BUILDING in-cloud (~19 min'",
        "          ' CPU, measured; the upload set is FOUR files)' % (len(_cand), bool(_man_c)))",
        "    run([sys.executable, 'src/build_training_jsonl.py', '--source', 'tashkeela',",
        "         '--split', 'all', '--limit', '2000000', '--limit-eval', '200000',",
        "         '--allocate', 'spread', '--sampler-seed', '0', '--no-resume',",
        "         '--outdir', SILVER,",
        "         '--root-dict', 'data/silver_root_dict_padt.json'], cwd=ART)",
        "",
        "# THE APPROVED BUILD, VERIFIED BY CONTENT. The spread sampler is deterministic:",
        "# re-running it locally with this seed reproduced all three files byte-for-byte. So",
        "# the approved sha256 values below are a real gate, not a formality. If the cloud",
        "# build differs, this sample is NOT the one docs/next-run-criteria.md pre-registered,",
        "# and training on it would answer a different question. Stop rather than proceed on",
        "# almost-the-same data.",
        "APPROVED = {",
        "    'tashkeela-train.jsonl': (",
        "        '6dfeace847ed24d8e686495285c061b03d949bc88cda6e84481d3fa24dc3b687',",
        "        1871205, 82),",
        "    'tashkeela-dev.jsonl': (",
        "        '8bf74ed10bc02da2d440cc102ab405e0504a048ecee32e66dce459a8de0b960e',",
        "        149320, 8),",
        "    'tashkeela-test.jsonl': (",
        "        'b8dd1df81642681af83d4147447b48db98864929f0e5ae7224c5b640e406d316',",
        "        115436, 7),",
        "}",
        "for name, (want_sha, want_rec, want_books) in APPROVED.items():",
        "    _p = f'{SILVER_DIR}/{name}'",
        "    _h = hashlib.sha256()",
        "    with open(_p, 'rb') as _fh:",
        "        for _c in iter(lambda: _fh.read(1 << 20), b''):",
        "            _h.update(_c)",
        "    got_sha = _h.hexdigest()",
        "    got_rec = sum(1 for _ in open(_p, encoding='utf-8'))",
        "    ok = (got_sha == want_sha and got_rec == want_rec)",
        "    print('%-24s %8d records  sha256 %s  %s'",
        "          % (name, got_rec, got_sha[:16], 'MATCHES APPROVED' if ok else 'DIFFERS'))",
        "    if not ok:",
        "        raise SystemExit(name + ' does NOT match the approved round-26 build. want '",
        "                         + str(want_rec) + ' records / ' + want_sha[:16] + ', got '",
        "                         + str(got_rec) + ' records / ' + got_sha[:16]",
        "                         + '. The spread sampler is deterministic, so a difference'",
        "                         ' means this sample is not the pre-registered one. Do not'",
        "                         ' train on it: fix the cause, or re-upload the approved .gz'",
        "                         ' from the desktop build (COLAB.md 2).')",
        "",
        "# THE MANIFEST IS PART OF THE UPLOAD SET (38 KB): it carries the per-book record the",
        "# split assertions below read, so a STAGED run needs it too, not only a built one.",
        "_man_p = f'{SILVER_DIR}/build_manifest_tashkeela.json'",
        "if not os.path.exists(_man_p):",
        "    _man_p = f'{CACHE}/{SILVER}/build_manifest_tashkeela.json'",
        "if not os.path.exists(_man_p):",
        "    _man_p = f'{CACHE}/build_manifest_tashkeela.json'",
        "if not os.path.exists(_man_p):",
        "    raise SystemExit('missing build_manifest_tashkeela.json - upload it beside the'",
        "                     ' three record files in MyDrive/.../data/out/spread-B-2m/')",
        "man = json.load(open(_man_p, encoding='utf-8'))",
        "tr = [m for m in man['splits'] if m['split'] == 'train'][0]",
        "print('sampler: mode=%s seed=%s books_used=%d/%d unused=%s'",
        "      % (tr['sampler']['mode'], tr['sampler']['seed'],",
        "         tr['sampler']['books_used'], tr['sampler']['books_available'],",
        "         tr['sampler']['allocation_unused']))",
        "",
        "# THE BOOK-LEVEL SPLIT MUST SURVIVE THE REBUILD. A build that quietly merged split",
        "# ranges would put evaluation text into training, and no metric would show it. The",
        "# build's own record of which books it consumed is the evidence, not the intent.",
        "_used = {s['split']: sorted({b['book'] for b in s['sampler']['per_book']",
        "                             if b['consumed']}) for s in man['splits']}",
        "assert not (set(_used['dev']) & set(_used['train'])), 'dev and train share a book'",
        "assert not (set(_used['test']) & set(_used['train'])), 'test and train share a book'",
        "assert max(_used['dev']) < min(_used['train']) < min(_used['test'])",
        "print('book ranges: dev %s | train %d..%d (%d books) | test %s'",
        "      % (_used['dev'], min(_used['train']), max(_used['train']),",
        "         len(_used['train']), _used['test']))",
        "",
        "# THE MASKS ARE THE VERIFICATION. A degraded dictionary (arramooz missing, or the",
        "# gold half not shipped) does not crash - it silently lowers root supervision, and",
        "# that would read as a modelling result. The spread build measures root 65.6% /",
        "# wazan 59.8%; the old one-book sample measured 69.3% / 62.3%, and a spread sample is",
        "# NOT supposed to match one book's opening, so the floors stay wide.",
        "MASK_FLOOR = {'root': 0.55, 'wazan': 0.45}",
        "for head, floor in MASK_FLOOR.items():",
        "    u = tr['per_head_unmasked'][head]",
        "    t = tr['per_head_total'][head]",
        "    print('%-8s supervision %7d/%7d = %5.1f%%  (floor %.0f%%)'",
        "          % (head, u, t, 100.0 * u / t, 100 * floor))",
        "    assert u / t >= floor, (head + ' supervision collapsed to %.1f%% - the silver'",
        "                            ' dictionary or the CALIMA gate is broken, and this'",
        "                            ' would look like a modelling result') % (100.0 * u / t)",
        "print('SILVER READY - spread sample, byte-verified against the approved round-26 build')",
    )
    return [head, body, build_head, build]


def objective_cell() -> dict:
    """The preflight that makes a run STATE its own objective (§2cq/§2cs).

    Mirrors src/train.py:103-132 exactly: `loss.weights[head]` overrides `heads.<head>.weight`, which
    overrides the 1.0 default — and `normalise_by_log_vocab` divides each head's CE by log|V|, so the two
    together decide which head dominates. Printed BEFORE the build cell, because a run that does not say
    what it optimises cannot be adjudicated afterwards.
    """
    prov = PROVENANCE or {}
    cd = prov.get("config_dirty") or []
    od = prov.get("other_dirty") or []
    L = [
        "# --- PREFLIGHT: THE EFFECTIVE OBJECTIVE, BEFORE ANYTHING TRAINS -------------------------",
        "# A run may not silently change its own objective (EVIDENCE_LOG §2cq, §2cs). This resolves",
        "# `loss.weights` over `heads.<head>.weight` EXACTLY as src/train.py:103-132 does, and prints",
        "# the weights that will actually be used -- plus what the build tree had UNCOMMITTED, which is",
        "# exactly how the v21 grid came to train under a loss that existed nowhere in git.",
        "import hashlib as _hl",
        "import yaml as _y",
        "_cfgp = '%s/config/shared.yaml' % ART",
        "_raw = open(_cfgp, 'rb').read()",
        "_cfg = _y.safe_load(_raw.decode('utf-8'))",
        "_loss = _cfg.get('loss') or {}",
        "_lw = _loss.get('weights') or {}",
        "_hw = _cfg.get('heads') or {}",
        "# DEFAULTS ARE PART OF THE OBJECTIVE. train.py reads focal_gamma with a 2.0 default and",
        "# focal_heads with a ['wazan','wazan_canonical'] default, so an ABSENT key is NOT 'off' -- an",
        "# earlier version of this cell printed None/[] for a restored config and UNDER-REPORTED it,",
        "# which is the same class of error the cell exists to prevent.",
        "_fg = float(_loss.get('focal_gamma', 2.0))",
        "_fd = _loss.get('focal_heads', ['wazan', 'wazan_canonical'])",
        "_fheads = set(_fd)",
        "print('=' * 78)",
        "print('EFFECTIVE OBJECTIVE (this is what will train)')",
        "print('  config sha256          %s' % _hl.sha256(_raw).hexdigest()[:16])",
        "print('  normalise_by_log_vocab %s' % _loss.get('normalise_by_log_vocab', False))",
        "print('  focal_gamma            %s%s' % (_fg, '' if 'focal_gamma' in _loss else '   <- train.py DEFAULT (key absent)'))",
        "print('  focal_heads            %s%s' % (sorted(_fheads), '' if 'focal_heads' in _loss else '   <- train.py DEFAULT (key absent)'))",
        "print('  %-20s %-9s %-22s%s' % ('head', 'effective', 'source', 'focal'))",
        "for _h in sorted(set(list(_hw) + list(_lw))):",
        "    _spec = _hw.get(_h)",
        "    if _h in _lw:",
        "        _eff, _src = float(_lw[_h]), 'loss.weights'",
        "    elif isinstance(_spec, dict) and 'weight' in _spec:",
        "        _eff, _src = float(_spec['weight']), 'heads.%s.weight' % _h",
        "    else:",
        "        _eff, _src = 1.0, 'default'",
        "    print('  %-20s %-9s %-22s%s' % (_h, _eff, _src, ('FOCAL y=%s' % _fg) if _h in _fheads else ''))",
    ]
    if cd or od:
        L += [
            "print('  !! THIS PAYLOAD WAS BUILT FROM A TREE THAT DID NOT MATCH HEAD:')",
            "for _l in %r + %r:" % (cd, od),
            "    print('       ' + _l)",
            "print('     -> the objective above is NOT necessarily what git describes: read it, not the commit.')",
        ]
    else:
        L += ["print('  payload built from a CLEAN tree: config/ and src/ match HEAD')"]
    L += ["print('=' * 78)", "del _hl, _y, _src, _eff, _h, _spec, _lw, _hw, _loss, _fheads, _cfg, _raw"]
    return code(*L)


def main(argv=None) -> int:
    import argparse
    global ALLOW_DIRTY_CONFIG
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--allow-dirty-config", action="store_true",
                    help="build even though config/ differs from HEAD; the notebook PRINTS the objective")
    args, _unknown = ap.parse_known_args(argv)
    ALLOW_DIRTY_CONFIG = bool(args.allow_dirty_config)

    # The embedded cell goes AFTER the paths cell (it needs ART) and BEFORE cell 3.
    cut = next(i for i, c in enumerate(CELLS)
               if c["cell_type"] == "markdown" and c["source"][0].startswith("## 3."))
    cells = CELLS[:cut] + embed_cells() + [objective_cell()] + CELLS[cut:]

    # ENFORCE the promise in the docstring: a code cell that is not parseable is a cell
    # nobody can verify, and that is the bug class this check exists for.
    bad = []
    for i, c in enumerate(cells):
        if c["cell_type"] != "code":
            continue
        src = "".join(c["source"])
        try:
            ast.parse(src)
        except SyntaxError as e:
            bad.append((i, e))
    if bad:
        for i, e in bad:
            print(f"CELL {i}: NOT PARSEABLE: {e}")
        return 1

    nb = {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python",
                           "name": "python3"},
            "language_info": {"name": "python", "version": "3.11"},
            "accelerator": "GPU",
            "colab": {"provenance": [], "private_outputs": True},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT}  ({len(cells)} cells, "
          f"{sum(1 for c in cells if c['cell_type'] == 'code')} code cells, "
          f"all ast.parse-checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
