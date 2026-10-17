"""kaggle_run.py — drive Kaggle over the REST API (no CLI, no pip).

WHY REST AND NOT THE `kaggle` CLI
    The venv has no pip (built with uv), `uv` is not on PATH here, and this host has
    stalled or failed three package installs (pyarrow twice). `requests` is the one thing
    that has worked reliably on this network, and the Kaggle v1 API accepts the token in
    `~/.kaggle/access_token` as a Bearer credential — verified: `kernels/list` returns 200.

PRIVACY IS NOT OPTIONAL
    The corpora are CC BY-NC-SA 4.0 / GPL, so BOTH the dataset and the kernel are created
    private. `--public` exists and should stay unused.

USAGE
    python src/kaggle_run.py --stage                 # build the upload bundle
    python src/kaggle_run.py --push-dataset          # private dataset
    python src/kaggle_run.py --push-kernel           # private GPU kernel
    python src/kaggle_run.py --status                # poll
    python src/kaggle_run.py --fetch                 # pull outputs
    python src/kaggle_run.py --dry-run               # print payloads, send nothing
"""
from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import sys
import tarfile
import zipfile
from pathlib import Path

import requests

from paths import ROOT

API = "https://www.kaggle.com/api/v1"
USER = "akhiirendi"
DS_SLUG = f"{USER}/arabic-dataset"   # the dataset the bundle was actually uploaded into
# A SECOND dataset, and the reason is measured, not stylistic: one bundle containing both
# corpora is a 34.0 MB zip, and this connection RESET it on three consecutive attempts
# (ConnectionResetError 10054 / ConnectionAbortedError 10053). The 11.8 MB round-16 bundle
# uploaded fine, so the payload is split instead of fought:
#     akhiirendi/arabic-dataset        PADT records + the round-16 src (unchanged)
#     akhiirendi/arabic-root-tree-silver   the SILVER records + the NEW src/config
# The kernel attaches both; the notebook extracts every zip it finds and the SILVER one
# is extracted LAST so the newer src/config wins on shared paths (see make_notebook.py).
SILVER_DS_SLUG = f"{USER}/arabic-root-tree-silver"
# The slug Kaggle ACTUALLY assigned is derived from the title, not from the slug we
# request: we asked for `arabic-root-tree-padt` and got
# `arabic-root-tree-padt-matched-size-run`. Pushing with a slug that does not match the
# existing kernel makes Kaggle try to CREATE a second one and fail with HTTP 409
# ("title already in use"). This must be the real slug, taken from the returned URL.
KERNEL_SLUG = f"{USER}/arabic-root-tree-padt-matched-size-run"
STAGE = ROOT / "dist" / "run-bundle"
STAGE_SILVER = ROOT / "dist" / "silver-bundle"


def token() -> str:
    p = Path(os.path.expanduser("~/.kaggle/access_token"))
    if not p.exists():
        raise SystemExit("no ~/.kaggle/access_token — cannot authenticate")
    return p.read_text(encoding="utf-8").strip()


def hdr() -> dict:
    return {"Authorization": "Bearer " + token()}


def show(r, what: str) -> bool:
    ok = r.status_code in (200, 201)
    print(f"  {what}: HTTP {r.status_code} {'OK' if ok else ''}")
    if not ok:
        print("    ->", r.text[:400].replace("\n", " "))
    return ok


# ------------------------------------------------------------------ staging
def stage() -> Path:
    """Copy exactly what training needs: code, config, derived JSONL, human gold.

    Corpora are excluded on purpose — the JSONL already carries the silver targets and
    CALIMA is never called during training, which keeps the upload ~12 MB instead of
    ~570 MB and avoids CAMeL's 124 MB data package.
    """
    if STAGE.exists():
        shutil.rmtree(STAGE)
    (STAGE / "data").mkdir(parents=True)
    shutil.copytree(ROOT / "src", STAGE / "src")
    shutil.copytree(ROOT / "config", STAGE / "config")
    shutil.copytree(ROOT / "data" / "out", STAGE / "data" / "out")
    (STAGE / "data" / "annotation").mkdir()
    for p in (ROOT / "data" / "annotation").glob("gold-*"):
        shutil.copy2(p, STAGE / "data" / "annotation" / p.name)
    for p in (STAGE / "src").glob("*.pyc"):
        p.unlink()
    shutil.rmtree(STAGE / "src" / "__pycache__", ignore_errors=True)
    n = sum(1 for _ in STAGE.rglob("*") if _.is_file())
    size = sum(p.stat().st_size for p in STAGE.rglob("*") if p.is_file())
    print(f"  staged {n} files, {size/1e6:.1f} MB -> {STAGE}")
    return STAGE


def zip_bytes(folder: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(folder.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(folder))
    return buf.getvalue()


# ------------------------------------------------------------------ dataset
def stage_silver() -> Path:
    """The SILVER bundle: the Tashkeela records + the CURRENT src/config + the gold.

    Deliberately small. The PADT records are already in the older dataset and are NOT
    re-uploaded — a 34 MB combined payload is reset by this connection (see SILVER_DS_SLUG).
    """
    if STAGE_SILVER.exists():
        shutil.rmtree(STAGE_SILVER)
    (STAGE_SILVER / "data" / "out").mkdir(parents=True)
    (STAGE_SILVER / "data" / "annotation").mkdir()
    shutil.copytree(ROOT / "src", STAGE_SILVER / "src")
    shutil.copytree(ROOT / "config", STAGE_SILVER / "config")
    for p in (ROOT / "data" / "out").glob("tashkeela-*.jsonl"):
        # train + dev only: `test` is not read by the notebook, and on this connection
        # every megabyte of payload is a megabyte of risk (see SILVER_DS_SLUG).
        if p.name.endswith("-test.jsonl"):
            continue
        shutil.copy2(p, STAGE_SILVER / "data" / "out" / p.name)
    for p in (ROOT / "data" / "annotation").glob("gold-*"):
        shutil.copy2(p, STAGE_SILVER / "data" / "annotation" / p.name)
    shutil.rmtree(STAGE_SILVER / "src" / "__pycache__", ignore_errors=True)
    n = sum(1 for _ in STAGE_SILVER.rglob("*") if _.is_file())
    size = sum(p.stat().st_size for p in STAGE_SILVER.rglob("*") if p.is_file())
    print(f"  staged {n} files, {size/1e6:.1f} MB -> {STAGE_SILVER}")
    return STAGE_SILVER


def push_dataset(dry: bool) -> bool:
    folder = STAGE if STAGE.exists() else stage()
    # see push_silver_dataset(): a stale stage ships a stale artifact. The PADT half has
    # not changed since round 16, but `--stage` is the only way to be sure, and the
    # payload size is printed so a mismatch is visible.
    stage()
    meta = {
        "title": "arabic-root-tree run bundle",
        "id": DS_SLUG,
        "licenses": [{"name": "other"}],
        "description": ("PRIVATE. Code, config, derived per-token JSONL and the "
                        "single-annotator Tashkeela gold for the arabic-root-tree "
                        "matched-size comparison. Corpora are CC BY-NC-SA/GPL: do not "
                        "make public."),
    }
    return _upload_dataset(folder, meta, dry)


def push_silver_dataset(dry: bool) -> bool:
    """The SILVER half: Tashkeela records + the current src/config + the human gold.

    Separate from push_dataset() only because of the measured upload size limit
    (see SILVER_DS_SLUG). Attach BOTH to the kernel.
    """
    folder = STAGE_SILVER if STAGE_SILVER.exists() else stage_silver()
    # A STALE STAGE IS A SILENT WRONG ARTIFACT. This bit once: the silver bundle was
    # staged with a 500k-token train split, the split was then rebuilt at 230k, and the
    # push happily shipped the OLD directory (20.7 MB), because `if exists` only checks
    # that SOMETHING is there. The payload size is printed on every push as the cheap
    # guard against it, and the silver stage is now refreshed unconditionally.
    stage_silver()
    meta = {
        "title": "arabic-root-tree silver records",
        "id": SILVER_DS_SLUG,
        "licenses": [{"name": "other"}],
        "description": ("PRIVATE. SILVER (Tashkeela) per-token records, the CURRENT "
                        "src/ and config/, and the single-annotator human gold for the "
                        "silver-vs-gold ablation. Attach together with "
                        "akhiirendi/arabic-dataset, which holds the PADT records. "
                        "Corpora are CC BY-NC-SA/GPL: do not make public."),
    }
    return _upload_dataset(folder, meta, dry)


def _upload_dataset(folder: Path, meta: dict, dry: bool) -> bool:
    payload = {"dataset": json.dumps(meta)}
    blob = zip_bytes(folder)
    print(f"  dataset {meta['id']}: payload {len(blob)/1e6:.1f} MB zip")
    if dry:
        print("  DRY RUN — not sending")
        return True
    # RETRY. This host aborts long TLS uploads (ConnectionAbortedError 10053 /
    # ConnectionResetError 10054 — measured: a 34.0 MB payload failed three times in a
    # row while an 11.8 MB one succeeded). The upload is a single POST so it cannot be
    # resumed; the only available mitigation is to send it again.
    last = None
    for attempt in range(1, 5):
        try:
            r = requests.post(f"{API}/datasets/upload", headers=hdr(),
                              data=payload, files={"files": ("bundle.zip", blob)},
                              timeout=3600)
            return show(r, f"datasets/upload {meta['id']} (attempt {attempt})")
        except Exception as ex:
            last = ex
            print(f"  attempt {attempt} FAILED: {type(ex).__name__}: {ex}")
            import time as _t
            _t.sleep(10 * attempt)
    print(f"  all attempts failed: {type(last).__name__}: {last}")
    return False


# ------------------------------------------------------------------ kernel
def kernel_payload(one_seed: bool) -> dict:
    nb_path = ROOT / "notebooks" / "run-padt.ipynb"
    text = nb_path.read_text(encoding="utf-8")
    if one_seed:
        # keep the quota honest: the notebook reads config['seeds'], so trim it to one
        nb = json.loads(text)
        for c in nb["cells"]:
            if c["cell_type"] != "code":
                continue
            for i, line in enumerate(c["source"]):
                if line.startswith("cfg = load_config(smoke=False)"):
                    c["source"][i] = ("cfg = load_config(smoke=False)\n"
                                      "cfg['seeds'] = cfg['seeds'][:1]  "
                                      "# 1 seed first: 1/3 the GPU quota\n")
                    break
        text = json.dumps(nb, ensure_ascii=False)
    return {
        "slug": KERNEL_SLUG,
        "newTitle": "arabic-root-tree PADT matched-size run",
        "text": text,
        "language": "python",
        "kernelType": "notebook",
        "isPrivate": True,
        "enableGpu": True,
        # INTERNET IS REQUIRED (round 17): the silver records are BUILT in the kernel
        # (the dataset API will not take the upload and the kernel source is capped at
        # <1 MB), so the run needs pip for camel-tools/arramooz, camel_data for the
        # CALIMA packages, and the HF rows endpoint for Tashkeela itself.
        "enableInternet": True,
        # ONLY the PADT bundle. SILVER_DS_SLUG is defined but was never created — every
        # dataset-creation attempt failed (see SILVER_DS_SLUG) — and naming a dataset the
        # token cannot resolve is "silently dropped" per round 16, so it is not listed.
        "datasetDataSources": [DS_SLUG],
        "competitionDataSources": [],
        "categoryIds": [],
    }


def push_kernel(dry: bool, one_seed: bool) -> bool:
    p = kernel_payload(one_seed)
    print(f"  kernel slug : {p['slug']}")
    print(f"  private     : {p['isPrivate']}   gpu: {p['enableGpu']}")
    print(f"  datasets    : {p['datasetDataSources']}")
    print(f"  notebook    : {len(p['text'])/1024:.1f} KB, one_seed={one_seed}")
    if dry:
        print("  DRY RUN — not sending")
        return True
    r = requests.post(f"{API}/kernels/push", headers={**hdr(),
                      "Content-Type": "application/json"},
                      data=json.dumps(p), timeout=600)
    ok = show(r, "kernels/push")
    if ok:
        try:
            j = r.json()
            print("   version:", j.get("versionNumber"), "| url:",
                  j.get("url") or j.get("ref"))
        except Exception:
            print("   body:", r.text[:200])
    return ok


def status() -> bool:
    # PARAM NAMES MATTER AND CHANGED: the v1 API rejected `user`/`kernel`
    # (HTTP 400 "Invalid field 'user'") and accepted `userName`/`kernelSlug`.
    # `kernels/list` still takes `user`, which is why the old spelling looked
    # plausible. Verified against the live API on 2026-10-09.
    r = requests.get(f"{API}/kernels/status",
                     headers=hdr(),
                     params={"userName": USER, "kernelSlug": KERNEL_SLUG.split("/")[1]},
                     timeout=120)
    if not show(r, "kernels/status"):
        return False
    try:
        print("   ", r.json())
    except Exception:
        print("   ", r.text[:300])
    return True


def fetch(out: Path = ROOT / "dist" / "kaggle-output", only: tuple = ()) -> bool:
    # Same param-name fix as status(): `userName`/`kernelSlug`, not `user`/`kernel`.
    r = requests.get(f"{API}/kernels/output", headers=hdr(),
                     params={"userName": USER, "kernelSlug": KERNEL_SLUG.split("/")[1]},
                     timeout=600)
    if not show(r, "kernels/output"):
        return False
    out.mkdir(parents=True, exist_ok=True)
    try:
        for f in r.json().get("files", []):
            # Newer API returns `fileNameNullable`/`urlNullable` alongside the plain
            # fields, and file names may contain subdirectories (checkpoints/...),
            # so the parent directory has to exist or the write raises.
            name = f.get("fileName") or f.get("fileNameNullable")
            url = f.get("url") or f.get("urlNullable")
            if not url or not name:
                continue
            # `only` exists because a 12-run grid writes ~660 MB of checkpoints and
            # results.json is the artifact a reader needs; pulling the tensors over a
            # throttled link is minutes of nothing.
            if only and not any(name.startswith(p) for p in only):
                print(f"    skipped {name} (not in --only {list(only)})")
                continue
            dest = out / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            b = requests.get(url, timeout=600).content
            dest.write_bytes(b)
            print(f"    fetched {name} ({len(b)} bytes)")
    except Exception as e:
        print("    output parse error:", type(e).__name__, e)
        print("    raw:", r.text[:300])
    return True


def log() -> bool:
    """Print the kernel log (stdout+stderr). The run's honest numbers live here."""
    r = requests.get(f"{API}/kernels/output", headers=hdr(),
                     params={"userName": USER, "kernelSlug": KERNEL_SLUG.split("/")[1]},
                     timeout=600)
    if not show(r, "kernels/output(log)"):
        return False
    txt = r.json().get("log") or r.json().get("logNullable") or ""
    out_path = ROOT / "dist" / "kernel_full.log"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(txt, encoding="utf-8")
    print(f"  [saved kernel log to {out_path}]")
    try:
        print(txt)
    except UnicodeEncodeError:
        print(txt.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8", errors="replace"))
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", action="store_true")
    ap.add_argument("--push-dataset", action="store_true")
    ap.add_argument("--push-silver-dataset", action="store_true",
                    help="push the SILVER bundle (Tashkeela + current src/config)")
    ap.add_argument("--push-kernel", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--log", action="store_true", help="print the kernel log")
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--only", nargs="*", default=[],
                    help="fetch only output files whose name starts with one of these "
                         "(e.g. --only results)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--full-seeds", action="store_true",
                    help="use all 3 seeds (default: 1 seed, to save GPU quota)")
    args = ap.parse_args()

    print("=" * 80)
    print("KAGGLE RUN — user %s  (private dataset + private GPU kernel)" % USER)
    print("=" * 80)
    rc = 0
    if args.stage or not any((args.push_dataset, args.push_silver_dataset,
                              args.push_kernel, args.status, args.fetch, args.log)):
        stage()
    if args.push_dataset:
        rc |= 0 if push_dataset(args.dry_run) else 1
    if args.push_silver_dataset:
        rc |= 0 if push_silver_dataset(args.dry_run) else 1
    if args.push_kernel:
        rc |= 0 if push_kernel(args.dry_run, not args.full_seeds) else 1
    if args.status:
        rc |= 0 if status() else 1
    if args.log:
        rc |= 0 if log() else 1
    if args.fetch:
        rc |= 0 if fetch(only=tuple(args.only)) else 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
