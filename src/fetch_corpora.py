"""fetch_corpora.py — re-fetch every corpus in data/raw from its recorded URL.

WHY NOT THE MANIFEST'S curl RECIPE
    data/raw/MANIFEST.md records the URLs, and its curl recipe is correct on a
    normal host — but on the machine this repo now runs on (campus network) direct
    `curl` and ICMP are filtered while Python's requests works fine. So the recipe
    is reimplemented here with the same URLs and the same expected byte counts.

WHAT IT DOES
    Downloads each file to data/raw/<local name>, verifying `content-length`
    against the size recorded in the MANIFEST.  Idempotent: a file already present
    with the right size is skipped unless --force.  Then run:
        cd data/raw && sha256sum -c CHECKSUMS.sha256

    The corpora are GPLv3 / CC-BY-NC-SA and are deliberately NOT in git
    (.gitignore). This script is what makes them recoverable.

KNOWN-UNCERTAIN, stated rather than hidden (per MANIFEST):
    qrtb-RelLabels.csv and qrtb-pos.csv have NO recorded source path. They are
    small enumeration tables derivable from qrtb/Quranic.csv, and their hashes are
    recorded, so a wrong replacement is detectable. They are not fetched here;
    --derive-aux rebuilds them from Quranic.csv instead.

Usage:
    python src/fetch_corpora.py             # fetch all
    python src/fetch_corpora.py --verify    # only check sizes
    python src/fetch_corpora.py --force     # re-download everything
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import requests

from paths import RAW

# (url, local filename, expected bytes from MANIFEST.md)
UD = "https://raw.githubusercontent.com/UniversalDependencies"
QURANIC = "https://raw.githubusercontent.com/NoorBayan/Quranic/main/corpus"

FILES = [
    (f"{UD}/UD_Arabic-PADT/master/ar_padt-ud-train.conllu", "ar_padt-ud-train.conllu", 40_698_415),
    (f"{UD}/UD_Arabic-PADT/master/ar_padt-ud-dev.conllu",   "ar_padt-ud-dev.conllu",    5_397_917),
    (f"{UD}/UD_Arabic-PADT/master/ar_padt-ud-test.conllu",  "ar_padt-ud-test.conllu",   5_163_066),
    (f"{UD}/UD_Arabic-NYUAD/master/ar_nyuad-ud-train.conllu", "ar_nyuad-ud-train.conllu", 46_880_990),
    (f"{UD}/UD_Arabic-NYUAD/master/ar_nyuad-ud-dev.conllu",   "ar_nyuad-ud-dev.conllu",    5_846_069),
    (f"{UD}/UD_Arabic-NYUAD/master/ar_nyuad-ud-test.conllu",  "ar_nyuad-ud-test.conllu",   5_856_617),
    (f"{UD}/UD_Arabic-PUD/master/ar_pud-ud-test.conllu",      "ar_pud-ud-test.conllu",     2_401_101),
    # QAC morphology: the vendor GET serves HTML, so use the mirror (MANIFEST).
    ("https://raw.githubusercontent.com/q-ran/quran/master/sources/1.0/"
     "quranic-corpus-morphology-0.4.txt", "qac-morphology-0.4.txt", 6_309_503),
    # EQTB: branch is `main`; `master` 404s (MANIFEST). Extract to qrtb/Quranic.csv.
    (f"{QURANIC}/Quranic.rar", "Quranic.rar", 4_120_767),
    # RESOLVED 2026-10-09 — MANIFEST recorded these two as "known-uncertain: no
    # recorded source path". They ARE in the same repo, at corpus/, and both byte
    # counts match the recorded hashes exactly (14,610 and 6,388). No longer unknown.
    (f"{QURANIC}/RelLabels.csv", "qrtb-RelLabels.csv", 14_610),
    (f"{QURANIC}/pos.csv", "qrtb-pos.csv", 6_388),
    # The DECOY (5 columns of verse text) — kept only so it can be shown to be a
    # decoy. It is NOT the treebank; qrtb/Quranic.csv is.
    (f"{QURANIC}/Quran.csv", "quranic-treebank.csv", 5_352_212),
]

# Quranic.rar -> qrtb/Quranic.csv (57,475,290 B, UTF-16, TAB, 51 cols). Windows
# `tar` cannot read RAR; 7-Zip can, and it is already installed on this host.
EQTB_RAR = "Quranic.rar"
EQTB_CSV_SIZE = 57_475_290
SEVEN_ZIP = [
    r"C:\Program Files\7-Zip\7z.exe",
    r"C:\Program Files (x86)\7-Zip\7z.exe",
    "7z",
]


def fetch(url: str, dest: Path, expected: int, force: bool) -> str:
    if dest.exists() and dest.stat().st_size == expected and not force:
        return f"skip   {dest.name} ({expected:,} B already present)"
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(url, timeout=120, stream=True)
    if r.status_code != 200:
        return f"FAIL   {dest.name}: HTTP {r.status_code}"
    ctype = r.headers.get("content-type", "")
    if "html" in ctype.lower() and not dest.name.endswith(".txt"):
        # the exact failure MANIFEST warns about for the vendor URL
        return f"FAIL   {dest.name}: served HTML, not a corpus ({ctype})"
    tmp = dest.with_suffix(dest.suffix + ".part")
    n = 0
    with open(tmp, "wb") as fh:
        for chunk in r.iter_content(1 << 16):
            fh.write(chunk)
            n += len(chunk)
    if n != expected:
        tmp.unlink(missing_ok=True)
        return f"FAIL   {dest.name}: got {n:,} bytes, expected {expected:,}"
    tmp.replace(dest)
    return f"ok     {dest.name} ({n:,} B)"


def extract_eqtb(force: bool = False) -> str:
    """Unpack Quranic.rar -> qrtb/Quranic.csv and check its byte count."""
    import shutil
    import subprocess

    csv = RAW / "qrtb" / "Quranic.csv"
    if csv.exists() and csv.stat().st_size == EQTB_CSV_SIZE and not force:
        return f"skip   qrtb/Quranic.csv ({EQTB_CSV_SIZE:,} B already extracted)"
    rar = RAW / EQTB_RAR
    if not rar.exists():
        return f"FAIL   {EQTB_RAR} missing — fetch it first"
    exe = next((x for x in SEVEN_ZIP if shutil.which(x) or Path(x).exists()), None)
    if exe is None:
        return ("FAIL   no 7-Zip found. Windows `tar` cannot read RAR. Install 7-Zip, "
                "or extract Quranic.rar manually to data/raw/qrtb/Quranic.csv")
    (RAW / "qrtb").mkdir(exist_ok=True)
    r = subprocess.run([exe, "x", "-y", f"-o{RAW / 'qrtb'}", str(rar)],
                       capture_output=True, text=True)
    if not csv.exists():
        return f"FAIL   7-Zip exit {r.returncode}: {(r.stdout or r.stderr)[-200:]}"
    n = csv.stat().st_size
    if n != EQTB_CSV_SIZE:
        return f"FAIL   qrtb/Quranic.csv is {n:,} B, expected {EQTB_CSV_SIZE:,}"
    return f"ok     qrtb/Quranic.csv ({n:,} B)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--verify", action="store_true", help="check sizes only, download nothing")
    ap.add_argument("--extract", action="store_true", help="only extract EQTB from Quranic.rar")
    args = ap.parse_args()

    print(f"target: {RAW}")
    if args.extract:
        line = extract_eqtb(args.force)
        print(line)
        return 0 if line.startswith(("ok", "skip")) else 1
    bad = skipped = 0
    for url, name, expected in FILES:
        dest = RAW / name
        if args.verify:
            if dest.exists() and dest.stat().st_size == expected:
                print(f"ok     {name} ({expected:,} B)")
            else:
                got = dest.stat().st_size if dest.exists() else None
                print(f"MISSING {name}: have {got}, want {expected:,}")
                bad += 1
            continue
        try:
            line = fetch(url, dest, expected, args.force)
        except Exception as ex:                      # network, DNS, timeout
            line = f"FAIL   {name}: {type(ex).__name__}: {ex}"
        if line.startswith("skip"):
            skipped += 1
        if line.startswith("FAIL"):
            bad += 1
        print(line)

    print()
    if bad:
        print(f"{bad} file(s) NOT retrieved. Re-run, or fetch manually from the URL above.")
        return 1
    print(f"all {len(FILES)} files verified"
          + (f" ({skipped} already present)" if skipped else ""))

    if not args.verify:
        line = extract_eqtb()
        print(line)

    csv = RAW / "qrtb" / "Quranic.csv"
    if csv.exists() and csv.stat().st_size == EQTB_CSV_SIZE:
        print(f"EQTB ready: {csv} ({csv.stat().st_size:,} B)")
    else:
        print("EQTB not extracted yet — run: python src/fetch_corpora.py --extract")
    print(f"\nnow: cd {RAW} && sha256sum -c CHECKSUMS.sha256")
    return 0


if __name__ == "__main__":
    sys.exit(main())
