"""kaggle_rescore_push.py — push the RESCORE kernel to Kaggle, watch it, and pull the result.

WHY THIS IS NOT src/kaggle_run.py
    src/kaggle_run.py lives INSIDE the embedded payload, so editing it changes the bundle
    sha256. The one provenance claim this run has to support is that its bundle differs from the
    round-26 TRAINING bundle by the reporting fix and nothing else, and a driver tweak has no
    business appearing in that diff. So the rescore driver lives in tools/, which the payload
    does not carry (it carries tools/fit_parity_union.py and nothing else from tools/).

WHY CPU AND NO DATASET
    * No GPU: this re-scores existing tensors. Training is not repeated, so the accelerator
      question does not arise and the weekly GPU quota is not touched.
    * No dataset: the Kaggle dataset API cannot be driven from this workstation (measured: a
      34 MB single-POST upload reset on three consecutive attempts), and a `datasetDataSources`
      entry the token cannot resolve is dropped SILENTLY. The kernel pulls the artefacts from
      the link-shared Drive folder over HTTPS instead -- see tools/drive_preflight.py, which
      proved that pull locally and reproduced every approved sha256.

USAGE
    python tools/kaggle_rescore_push.py --dry-run     # print the payload, send nothing
    python tools/kaggle_rescore_push.py --push        # create/refresh and QUEUE the kernel
    python tools/kaggle_rescore_push.py --status      # poll
    python tools/kaggle_rescore_push.py --log         # the kernel's stdout (read this first)
    python tools/kaggle_rescore_push.py --fetch       # pull the outputs
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
API = "https://www.kaggle.com/api/v1"
USER = "akhiirendi"
KERNEL_SLUG = USER + "/arabic-root-tree-rescore-cpu"
TITLE = "arabic-root-tree rescore CPU"
NOTEBOOK = ROOT / "dist" / "kaggle-rescore-CPU.ipynb"
STATE = ROOT / "dist" / "kaggle-rescore-kernel.json"
OUTDIR = ROOT / "dist" / "kaggle-rescore-output"


def token() -> str:
    p = Path(os.path.expanduser("~/.kaggle/access_token"))
    if not p.exists():
        raise SystemExit("no ~/.kaggle/access_token -- cannot authenticate")
    return p.read_text(encoding="utf-8").strip()


def hdr() -> dict:
    return {"Authorization": "Bearer " + token()}


def slug_of(state: dict) -> str:
    """The slug Kaggle actually assigned, which is NOT always the one requested: it derives the
    slug from the TITLE, and pushing with a slug that does not match the existing kernel makes
    Kaggle try to create a second one and fail with HTTP 409 'title already in use'."""
    return state.get("resolved_slug") or KERNEL_SLUG.split("/")[1]


def load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {}


def payload() -> dict:
    text = NOTEBOOK.read_text(encoding="utf-8")
    kb = len(text) / 1024
    if kb >= 1024:
        raise SystemExit("notebook is %.0f KB; Kaggle rejects kernel source >= 1 MB" % kb)
    return {
        "slug": KERNEL_SLUG,
        "newTitle": TITLE,
        "text": text,
        "language": "python",
        "kernelType": "notebook",
        "isPrivate": True,
        "enableGpu": False,        # no training happens; the quota is not spent
        "enableInternet": True,    # REQUIRED: the artefacts are pulled from Drive over HTTPS
        "datasetDataSources": [],  # deliberately none -- see the module docstring
        "competitionDataSources": [],
        "categoryIds": [],
    }


def push(dry: bool) -> bool:
    p = payload()
    nb = json.loads(p["text"])
    n_code = sum(1 for c in nb["cells"] if c.get("cell_type") == "code")
    txt = "".join("".join(c["source"]) for c in nb["cells"])
    n_rescore = sum(1 for line in txt.splitlines() if line.strip() == "RESCORE_ONLY = True")
    print("  slug       :", p["slug"])
    print("  notebook   : %.0f KB, %d cells (%d code)" % (len(p["text"]) / 1024, len(nb["cells"]), n_code))
    print("  private=%s  gpu=%s  internet=%s  datasets=%s"
          % (p["isPrivate"], p["enableGpu"], p["enableInternet"], p["datasetDataSources"]))
    print("  mode       : RESCORE_ONLY = True statements: %d" % n_rescore)
    # A TRAINING PUSH FROM THIS DRIVER WOULD BE THE WRONG ARTIFACT, SILENTLY. The whole point of
    # this kernel is that no weights move, so if the literal is not exactly once -- zero (it would
    # train for hours and re-sample the seed population) or twice (the notebook is malformed) --
    # stop before Kaggle is told anything.
    if n_rescore != 1:
        raise SystemExit("refusing to push: expected exactly ONE 'RESCORE_ONLY = True', found %d"
                         % n_rescore)
    if p["enableGpu"] is not False:
        raise SystemExit("refusing to push: this kernel must not request a GPU")
    if dry:
        print("  DRY RUN -- not sending")
        return True
    r = requests.post(f"{API}/kernels/push",
                      headers={**hdr(), "Content-Type": "application/json"},
                      data=json.dumps(p), timeout=600)
    ok = r.status_code in (200, 201)
    print("  kernels/push: HTTP %d %s" % (r.status_code, "OK" if ok else ""))
    if not ok:
        print("    ->", r.text[:400].replace("\n", " "))
        return False
    j = r.json()
    url = j.get("url") or ""
    resolved = urlparse(url).path.strip("/").split("/kernels/")[-1] if "kernels/" in url else ""
    state = {"resolved_slug": resolved.split("/")[-1] if resolved else "",
             "version": j.get("versionNumber"), "url": url}
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print("  version    :", j.get("versionNumber"))
    print("  url        :", url)
    print("  state      :", STATE)
    return True


def _poll() -> dict:
    st = load_state()
    r = requests.get(f"{API}/kernels/status", headers=hdr(),
                     params={"userName": USER, "kernelSlug": slug_of(st)}, timeout=120)
    if r.status_code != 200:
        print("  kernels/status HTTP %d: %s" % (r.status_code, r.text[:200]))
        return {}
    print("  ", r.json())
    return r.json()


def status() -> bool:
    return bool(_poll())


def log() -> bool:
    st = load_state()
    r = requests.get(f"{API}/kernels/output", headers=hdr(),
                     params={"userName": USER, "kernelSlug": slug_of(st)}, timeout=600)
    if r.status_code != 200:
        print("  kernels/output HTTP %d: %s" % (r.status_code, r.text[:300]))
        return False
    txt = r.json().get("log") or r.json().get("logNullable") or ""
    OUTDIR.mkdir(parents=True, exist_ok=True)
    (OUTDIR / "kernel.log").write_text(txt, encoding="utf-8")
    print(txt[-14000:])
    print("\n[full log -> %s]" % (OUTDIR / "kernel.log"))
    return True


def fetch() -> bool:
    st = load_state()
    r = requests.get(f"{API}/kernels/output", headers=hdr(),
                     params={"userName": USER, "kernelSlug": slug_of(st)}, timeout=600)
    if r.status_code != 200:
        print("  kernels/output HTTP %d: %s" % (r.status_code, r.text[:300]))
        return False
    OUTDIR.mkdir(parents=True, exist_ok=True)
    j = r.json()
    tgz = j.get("log") or ""
    if tgz:
        (OUTDIR / "kernel.log").write_text(tgz, encoding="utf-8")
    got = 0
    for f in j.get("files", []):
        name = f.get("fileName") or f.get("fileNameNullable")
        url = f.get("url") or f.get("urlNullable")
        if not url or not name:
            continue
        # results/ is the artifact; the 650 MB of pulled checkpoints are not worth pulling back
        if not name.startswith("results/") and not name.endswith("results.json"):
            print("    skipped %s (not the artifact)" % name)
            continue
        dest = OUTDIR / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        b = requests.get(url, timeout=600).content
        dest.write_bytes(b)
        got += 1
        print("    fetched %s (%d bytes)" % (name, len(b)))
    print("  files fetched:", got)
    return got > 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--log", action="store_true")
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    print("=" * 78)
    print("KAGGLE RESCORE -- %s (private, CPU, no dataset, Drive pull)" % KERNEL_SLUG)
    print("=" * 78)
    rc = 0
    if a.push or a.dry_run:
        rc |= 0 if push(a.dry_run) else 1
    if a.status:
        rc |= 0 if status() else 1
    if a.log:
        rc |= 0 if log() else 1
    if a.fetch:
        rc |= 0 if fetch() else 1
    if not any((a.push, a.status, a.log, a.fetch, a.dry_run)):
        ap.print_help()
    return rc


if __name__ == "__main__":
    sys.exit(main())
