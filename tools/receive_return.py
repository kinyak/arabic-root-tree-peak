"""receive_return.py — process ONE returned annotation sheet. Mechanical, fail-closed, no judgement.

WHY THIS EXISTS
    The packet makes the annotator three promises: the return is *hashed immediately on receipt*,
    then *immutable*, and *archived read-only*. Promises like that are worth nothing unless they are
    mechanical — and a hand-run hash + copy is exactly the step that gets skipped when the file
    arrives at midnight. This is that mechanism, and it also checks the two things that silently
    ruin a two-annotator comparison before anyone notices:

      * row IDs and row ORDER against the frozen sheet (if the rows moved, the two annotators are
        answering different item sets and every agreement number computed from them is wrong), and
      * the format, with the same validator the packet names -- a malformed cell that reaches the
        agreement report makes the report wrong, not merely noisy.

WHAT IT DOES
    1. sha256 the file AS RECEIVED, before anything else can touch it
    2. write a read-only copy under data/annotation/private/  (the immutable archive)
    3. append a receipt to data/annotation/receipts.json
    4. check IDs/order against the frozen bench sheet
    5. format-check via tools/iaa_report.py's validator (imported, so there is ONE definition)
    6. print the receipt block, and the exact next command

MODES
    python tools/receive_return.py --file <return.csv> --annotator B
    python tools/receive_return.py --file <return.csv> --annotator B --expected-sha <sha256>
    python tools/receive_return.py --verify      # re-hash every receipt: a changed file is VOID
    python tools/receive_return.py --list        # the receipt ledger

CPU only. Reads no analyser, no model output, no gold.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_root import resolve_root  # noqa: E402
import iaa_report  # noqa: E402

ROOT = resolve_root()
ANN = ROOT / "data/annotation"
PRIVATE = ANN / "private"
LEDGER = ANN / "receipts.json"


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load_ledger() -> dict:
    if LEDGER.exists():
        return json.loads(LEDGER.read_text(encoding="utf-8"))
    return {"kind": "annotation-receipts", "receipts": []}


def save_ledger(led: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(led, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def frozen_ids() -> list[str]:
    with (ANN / "bench-sheet.csv").open(encoding="utf-8-sig", newline="") as fh:
        return [r["id"] for r in csv.DictReader(fh)]


def read_ids(p: Path) -> list[str]:
    with p.open(encoding="utf-8-sig", newline="") as fh:
        return [r["id"] for r in csv.DictReader(fh)]


def do_verify() -> int:
    led = load_ledger()
    if not led["receipts"]:
        print("  no receipts yet.")
        return 0
    bad = 0
    print("=" * 84)
    print("RECEIPT VERIFICATION — a return that changed after hashing is VOID")
    print("=" * 84)
    for r in led["receipts"]:
        for label, key in (("original", "original_path"), ("archive", "archived_path")):
            p = Path(r[key])
            if not p.exists():
                print("  %-14s %-12s MISSING  %s" % (r["annotator"], label, p))
                bad += 1
                continue
            now = sha256_file(p)
            same = now == r["sha256"]
            if not same:
                bad += 1
            print("  %-14s %-12s %s  %s" % (r["annotator"], label,
                                            "UNCHANGED" if same else "CHANGED — VOID",
                                            r["sha256"][:16] + "..."))
    print("\n  %d receipt(s), %d problem(s)" % (len(led["receipts"]), bad))
    return 1 if bad else 0


def do_list() -> int:
    led = load_ledger()
    print("  %d receipt(s)" % len(led["receipts"]))
    for r in led["receipts"]:
        print("  %-3s %-34s %s  rows=%s  validation_exit=%s  %s" % (
            r["annotator"], Path(r["original_path"]).name, r["sha256"][:16] + "...",
            r.get("rows"), r.get("validation_exit"), r.get("received_at")))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file")
    ap.add_argument("--annotator")
    ap.add_argument("--expected-sha", default=None)
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.verify:
        return do_verify()
    if args.list:
        return do_list()
    if not (args.file and args.annotator):
        ap.error("--file and --annotator are required (or use --verify / --list)")

    src = Path(args.file)
    if not src.exists():
        print("  REFUSING: %s does not exist" % src)
        return 2

    print("=" * 84)
    print("RECEIVING annotation return — annotator %s" % args.annotator.upper())
    print("=" * 84)

    h = sha256_file(src)
    nbytes = src.stat().st_size
    print("  file        : %s" % src)
    print("  bytes       : %d" % nbytes)
    print("  sha256      : %s   <- recorded now, before anything else" % h)

    if args.expected_sha:
        ok = args.expected_sha.strip().lower() == h.lower()
        print("  expected    : %s   %s" % (args.expected_sha[:16] + "...",
                                           "MATCH" if ok else "MISMATCH — this is NOT the file that was sent"))
        if not ok:
            print("  REFUSING to receipt a file that does not match the issued hash.")
            return 2

    # 1. immutable archive --------------------------------------------------
    PRIVATE.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    arch = PRIVATE / ("%s-return-%s-%s" % (args.annotator.upper(), stamp, src.name))
    shutil.copy2(src, arch)
    os.chmod(arch, stat.S_IREAD)                     # read-only: chmod 444 on POSIX, +R on Windows
    print("  archived    : %s   (read-only)" % arch)
    print("  archive sha : %s   %s" % (
        sha256_file(arch)[:16] + "...",
        "matches the original" if sha256_file(arch) == h else "MISMATCH — copy failed, investigate"))

    # 2. row identity vs the frozen sheet -----------------------------------
    ids = read_ids(src)
    fids = frozen_ids()
    order_ok = ids == fids
    same_set = sorted(ids) == sorted(fids)
    print("  rows        : %d   (frozen sheet: %d)" % (len(ids), len(fids)))
    print("  id order    : %s" % ("IDENTICAL to the frozen sheet" if order_ok else
                                  ("same IDs, DIFFERENT ORDER — agreement would be confounded"
                                   if same_set else "IDS DIFFER — not the same item set")))
    if not order_ok:
        print("  !! do not compute agreement until this is resolved with the annotator — the receipt")
        print("     is still written, because the file as received is evidence either way.")

    # 3. format check (the packet's promise, one definition) -----------------
    print()
    vrc = iaa_report.validate_file(src)

    # 4. receipt -------------------------------------------------------------
    led = load_ledger()
    led["receipts"].append({
        "annotator": args.annotator.upper(),
        "original_path": str(src),
        "archived_path": str(arch),
        "sha256": h,
        "bytes": nbytes,
        "rows": len(ids),
        "id_order_ok": order_ok,
        "same_id_set": same_set,
        "validation_exit": vrc,
        "expected_sha": args.expected_sha,
        "received_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    save_ledger(led)
    print("\n  receipt appended: %s (%d total)" % (LEDGER, len(led["receipts"])))

    print("\n  NEXT:")
    print("    md5sum/sha256 of this return is now fixed -- any later change VOIDS it:")
    print("      python tools/receive_return.py --verify")
    print("    then the agreement report, per field, BEFORE any adjudication:")
    print("      python tools/iaa_report.py --a data/annotation/bench-annotator-A.csv \\")
    print("             --b %s --key data/annotation/bench-KEY.csv" % src.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
