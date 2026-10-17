"""drive_preflight.py — pull the round artefacts OUT of the shared Drive folder, and prove
they are the approved ones BEFORE a Kaggle session is spent on them.

WHY THIS EXISTS
    The Colab run wrote `checkpoints/` and `results/` into MyDrive/arabic-root-tree/, and the
    Kaggle rescore needs them there. Kaggle cannot mount Drive, so the kernel pulls them over
    HTTPS instead (internet is enabled). This script is that pull, run HERE first: it is the
    same mechanism, so a working local pull is evidence the kernel's pull will work, and the
    sha256 gate turns "the upload is probably fine" into a measurement.

WHY NOT gdown, AND WHY NOT THE WHOLE FOLDER
    `gdown` is not installed here and this host has a measured history of failed installs, so
    the pull is plain `requests` -- which also means the SAME code can be embedded in the
    notebook with no pip step to fail. And the shared folder mirrors the ENTIRE repo (it holds
    `.venv/`, `.git/`, `data/raw/`), so a recursive folder pull would drag gigabytes: this
    fetches the three subtrees that are actually needed, by id.

    Records travel as the `.gz` copies (80 MB) rather than the raw jsonl (1.2 GB) and are
    gunzipped here, because the sha256 the notebook gates on is the one for the PLAIN file.

USAGE
    python tools/drive_preflight.py --index          # resolve folder ids, write the index
    python tools/drive_preflight.py --records        # pull + verify the approved records
    python tools/drive_preflight.py --checkpoint NAME [--checkpoint NAME ...]
    python tools/drive_preflight.py --all            # index + records + one checkpoint
"""
from __future__ import annotations

import argparse
import codecs
import gzip
import hashlib
import json
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
SHARED_FOLDER_FID = "1TPpnjfk1D2h25klCrhwDfvO0ZMF7gDwP"   # arabic-root-tree/ (link-shared)
INDEX_PATH = ROOT / "dist" / "drive-index.json"
PREFLIGHT = ROOT / "dist" / "drive-preflight"

# The round-26 approved hashes, duplicated from the notebook's EXPECT_INPUTS on purpose: if
# the two ever disagree, one of them was edited without the other, and that is worth failing
# on rather than discovering inside a kernel.
APPROVED = {
    "padt-train.jsonl": "6ae53007cb73581ae78bc107a8df7f87bed7879c47f97ebb1e58250b83052e6f",
    "padt-dev.jsonl": "71a720f07cbf1b3056467e872bf657bdca84a19cbc35ef4501f9df7b1b8af232",
    "tashkeela-train.jsonl": "6dfeace847ed24d8e686495285c061b03d949bc88cda6e84481d3fa24dc3b687",
    "tashkeela-dev.jsonl": "8bf74ed10bc02da2d440cc102ab405e0504a048ecee32e66dce459a8de0b960e",
}

# which gz lives in which shared subtree
RECORD_JOBS = [
    ("colab-records", "padt-train.jsonl.gz"),
    ("colab-records", "padt-dev.jsonl.gz"),
    ("upload", "tashkeela-train.jsonl.gz"),
    ("upload", "tashkeela-dev.jsonl.gz"),
]

S = requests.Session()


def children(fid: str) -> list[dict]:
    """Immediate children of a folder, via the anonymous folder page.

    Drive nests the listing in `window['_DRIVE_ivd']` as an escaped JS string: \\xNN escapes
    for every bracket and quote, UTF-8 bytes for anything non-ASCII. A plain regex for the
    key is not enough -- the earlier attempt at this missed and reported the folder as
    private, which would have been a wrong conclusion drawn from a parsing bug.
    """
    r = S.get("https://drive.google.com/drive/folders/" + fid, timeout=90)
    r.raise_for_status()
    m = re.search(r"window\['_DRIVE_ivd'\]\s*=\s*'(.*?)';", r.text, re.S)
    if not m:
        return []
    d = codecs.decode(m.group(1), "unicode_escape")
    try:
        d = d.encode("latin-1").decode("utf-8")     # recover UTF-8 that was escaped byte-wise
    except Exception:
        pass
    out = []
    for row in json.loads(d)[0]:
        if isinstance(row, list) and len(row) >= 4:
            out.append({"id": str(row[0]), "name": str(row[2]), "mime": str(row[3]),
                        "dir": str(row[3]).endswith("folder")})
    return out


def child(fid: str, name: str) -> dict:
    for c in children(fid):
        if c["name"] == name:
            return c
    raise SystemExit("NOT FOUND under %s: %s" % (fid, name))


def download(fid: str, dest: Path) -> Path:
    """Stream one file, and refuse to save an HTML interstitial as if it were the file.

    THE PLAIN `uc?export=download` URL IS NOT ENOUGH -- and its failure mode is a lie. It
    returned the small records fine, but the 65 MB `tashkeela-train.jsonl.gz` came back as
    2,471 bytes of HTML, which the next step reported as
        gzip.BadGzipFile: Not a gzipped file (b'<!')
    i.e. "the upload is corrupt". It was not: measured, the SAME id returns real gzip bytes
    (magic 1f 8b) from drive.usercontent.google.com with confirm=t. Trusting the status code
    alone would have sent this looking for a bad file that does not exist -- and inside a
    Kaggle kernel it would have looked like a corrupt Drive upload and cost the session. So
    the confirm endpoint is tried first, and the payload is checked for HTML before it counts.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    urls = [
        "https://drive.usercontent.google.com/download?id=%s&export=download&confirm=t" % fid,
        "https://drive.google.com/uc?export=download&id=%s&confirm=t" % fid,
    ]
    last = ""
    for url in urls:
        n = 0
        with S.get(url, stream=True, timeout=1800) as r:
            r.raise_for_status()
            it = r.iter_content(1 << 20)
            first = next(it, b"")
            if first.lstrip()[:1] == b"<":
                last = first[:300].decode("utf-8", "replace")
                continue                      # interstitial, not the file
            with open(dest, "wb") as fh:
                fh.write(first)
                n = len(first)
                for chunk in it:
                    fh.write(chunk)
                    n += len(chunk)
        print("      %-34s %8.2f MB" % (dest.name, n / 1e6), flush=True)
        return dest
    raise SystemExit("Drive returned HTML, not %s: %s" % (dest.name, " ".join(last.split())))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def gunzip(src: Path, dest: Path) -> Path:
    with gzip.open(src, "rb") as fi, open(dest, "wb") as fo:
        while True:
            b = fi.read(1 << 20)
            if not b:
                break
            fo.write(b)
    return dest


def do_index() -> dict:
    ck = child(SHARED_FOLDER_FID, "checkpoints")
    dst = child(SHARED_FOLDER_FID, "dist")
    up = child(dst["id"], "upload-spread-B-2m")
    cr = child(dst["id"], "colab-records")
    idx = {
        "shared_root": SHARED_FOLDER_FID,
        "checkpoints": {"id": ck["id"], "files": children(ck["id"])},
        "dist": dst["id"],
        "upload": {"id": up["id"], "files": children(up["id"])},
        "colab_records": {"id": cr["id"], "files": children(cr["id"])},
    }
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(idx, indent=2), encoding="utf-8")
    print("checkpoints/        id=%s  %d files" % (ck["id"], len(idx["checkpoints"]["files"])))
    print("dist/upload-spread  id=%s  %s" % (up["id"], [f["name"] for f in idx["upload"]["files"]]))
    print("dist/colab-records  id=%s  %s" % (cr["id"], [f["name"] for f in idx["colab_records"]["files"]]))
    print("wrote", INDEX_PATH)
    return idx


def load_index() -> dict:
    if not INDEX_PATH.exists():
        return do_index()
    return json.loads(INDEX_PATH.read_text(encoding="utf-8"))


def do_records(idx: dict) -> bool:
    """Pull the .gz copies, gunzip, and check the PLAIN sha256 against the approval."""
    print("records (gz over the wire, sha256 on the plain file):")
    ok = True
    for key, name in RECORD_JOBS:
        folder = idx["colab_records"] if key == "colab-records" else idx["upload"]
        entry = next((f for f in folder["files"] if f["name"] == name), None)
        if entry is None:
            print("      MISSING on Drive:", name)
            ok = False
            continue
        gz = download(entry["id"], PREFLIGHT / name)
        plain = PREFLIGHT / name[:-3]
        gunzip(gz, plain)
        got, want = sha256(plain), APPROVED[name[:-3]]
        good = got == want
        ok &= good
        print("      %-24s %s  %s" % (name[:-3], got[:16],
                                      "MATCH" if good else "DIFFERS (approved %s)" % want[:16]),
              flush=True)
        plain.unlink()          # 1.2 GB of jsonl is not worth keeping once verified
    print("RECORDS:", "ALL MATCH the approved round-26 build" if ok else "MISMATCH -- DO NOT RUN")
    return ok


def do_checkpoint(idx: dict, name: str) -> bool:
    entry = next((f for f in idx["checkpoints"]["files"] if f["name"] == name), None)
    if entry is None:
        print("      not on Drive:", name)
        return False
    pt = download(entry["id"], PREFLIGHT / name)
    try:
        import torch
    except ImportError:
        print("      (torch absent locally -- size only)")
        return True
    blob = torch.load(pt, map_location="cpu", weights_only=False)
    cfg = blob["cfg"]
    m = cfg["model"]
    print("      conditioning=%s tower_hidden=%s min_freq=%s max_vocab=%s"
          % (m.get("use_soft_wazan_conditioning"), m.get("treatment_tower_hidden"),
             cfg["data"]["min_freq"], cfg["data"]["max_vocab"]))
    print("      silver_train=%s" % cfg["paths"].get("silver_train"))
    print("      seeds=%s  keys=%s  vocab_heads=%s"
          % (cfg.get("seeds"), sorted(blob.keys()),
             {k: v for k, v in list(blob["vocab"].items())[:0]} or "present"))
    is_v26 = (m.get("use_soft_wazan_conditioning") is True
              and m.get("treatment_tower_hidden") == 10018
              and cfg["data"]["max_vocab"] == 20000)
    print("      IDENTIFIES AS ROUND 26:", is_v26)
    return is_v26


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", action="store_true")
    ap.add_argument("--records", action="store_true")
    ap.add_argument("--checkpoint", action="append", default=[])
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    if not any((a.index, a.records, a.checkpoint, a.all)):
        a.index = True

    PREFLIGHT.mkdir(parents=True, exist_ok=True)
    idx = do_index() if (a.index or a.all or not INDEX_PATH.exists()) else load_index()
    rc = 0
    if a.records or a.all:
        rc |= 0 if do_records(idx) else 1
    if a.checkpoint:
        for nm in a.checkpoint:
            rc |= 0 if do_checkpoint(idx, nm) else 1
    if a.all:
        rc |= 0 if do_checkpoint(idx, "gold-baseline-s20261009.pt") else 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
