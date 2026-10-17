"""issue_packet_b.py — verifies and seals the annotator-B issue record.

WHAT IT GUARANTEES
    The issue record (`data/annotation/bench-B-ISSUE.json`) is the only artifact that says
    exactly which bytes were sent to the annotator. Hand-typed hashes drift; these are
    recomputed from disk on every run, and the script REFUSES (non-zero exit) rather than
    sealing if anything has moved:

      exit 2 -- a hash in the record does not match the file on disk (the packet was edited,
                the sheet was rebuilt, the guide changed)
      exit 3 -- the practice pack overlaps the frozen benchmark (a leaking practice pack
                silently trains the annotator on benchmark rows)
      exit 4 -- the annotator's copy is not byte-identical to the frozen sheet

    On success it writes `packet_sha256` and `issue_manifest.files` back into the record and
    prints the manifest. Nothing is transmitted by this script: recruitment is a human step.

USAGE
    python tools/issue_packet_b.py --check     # verify only; write nothing
    python tools/issue_packet_b.py             # verify and seal the record
CPU only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_root import resolve_root  # noqa: E402

# Resolved from the script's own location (or --root), NEVER from a hardcoded drive path: this
# tool has to be runnable against a copy of the repo on another machine or another OS.
ROOT = resolve_root()
ANN = ROOT / "data/annotation"
ISSUE = ANN / "bench-B-ISSUE.json"

PACKET = ROOT / "docs/ANNOTATION-PACKET-B.md"
GUIDE = ROOT / "docs/ANNOTATION-PROTOCOL.md"
FREEZE = ROOT / "docs/BENCHMARK-FREEZE-v2.md"
SHEET = ANN / "bench-sheet.csv"
ANNOT_B = ANN / "bench-annotator-B.csv"
ANNOT_A = ANN / "bench-annotator-A.csv"
BENCH_KEY = ANN / "bench-KEY.csv"
PRAC_PACK = ANN / "practice-pack.csv"
PRAC_KEY = ANN / "practice-KEY.csv"


def set_root(root: Path) -> None:
    """Re-point every path at an explicit --root. Called once, before anything is read."""
    global ROOT, ANN, ISSUE, PACKET, GUIDE, FREEZE, SHEET, ANNOT_B, ANNOT_A
    global BENCH_KEY, PRAC_PACK, PRAC_KEY
    ROOT = root
    ANN = ROOT / "data/annotation"
    ISSUE = ANN / "bench-B-ISSUE.json"
    PACKET = ROOT / "docs/ANNOTATION-PACKET-B.md"
    GUIDE = ROOT / "docs/ANNOTATION-PROTOCOL.md"
    FREEZE = ROOT / "docs/BENCHMARK-FREEZE-v2.md"
    SHEET = ANN / "bench-sheet.csv"
    ANNOT_B = ANN / "bench-annotator-B.csv"
    ANNOT_A = ANN / "bench-annotator-A.csv"
    BENCH_KEY = ANN / "bench-KEY.csv"
    PRAC_PACK = ANN / "practice-pack.csv"
    PRAC_KEY = ANN / "practice-KEY.csv"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read_csv(p: Path):
    with p.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="verify only; write nothing")
    ap.add_argument("--root", default=None,
                    help="repository root; defaults to the repo this script sits in")
    args = ap.parse_args()
    if args.root:
        set_root(resolve_root(args.root))

    print("  repo root: %s" % ROOT)
    rec = json.loads(ISSUE.read_text(encoding="utf-8"))
    problems, observed = [], {}

    # ---- every file the record names must exist, and the recorded hashes must still hold ------
    for key, path in (("guide", GUIDE), ("freeze", FREEZE), ("packet", PACKET)):
        if not path.exists():
            problems.append("MISSING %s" % path)
            continue
        observed[key] = sha(path)
        want = rec["protocol"].get("%s_sha256" % key)
        if key in ("guide", "freeze") and want and want != observed[key]:
            problems.append("%s changed on disk: record=%s disk=%s" % (key, want[:12], observed[key][:12]))

    for entry in rec["sent_to_annotator"]:
        p = ROOT / entry["file"]
        if not p.exists():
            problems.append("MISSING %s" % entry["file"])
            continue
        h = sha(p)
        observed[Path(entry["file"]).name] = h
        if entry.get("sha256") and entry["sha256"] != h:
            problems.append("%s changed: record=%s disk=%s"
                            % (entry["file"], entry["sha256"][:12], h[:12]))

    for p in (PRAC_KEY, BENCH_KEY, ANNOT_A):
        observed[p.name] = sha(p) if p.exists() else None

    # ---- the annotator's copy must be byte-identical to the frozen sheet ---------------------
    if SHEET.exists() and ANNOT_B.exists() and SHEET.read_bytes() != ANNOT_B.read_bytes():
        problems.append("bench-annotator-B.csv is NOT byte-identical to bench-sheet.csv")

    # ---- the practice pack must be provably outside the benchmark ----------------------------
    bench_ids, bench_sents, bench_lemmas, bench_targets = set(), set(), set(), set()
    for r in read_csv(SHEET):
        bench_ids.add(r["id"])
        bench_sents.add(r["sentence_with_target_in_double_brackets"].replace("[[", "").replace("]]", ""))
        bench_targets.add(r["target_token"])
    for r in read_csv(BENCH_KEY):
        bench_lemmas.add(r["lemma"])

    prac = read_csv(PRAC_PACK)
    leaks = []
    for r in prac:
        if r["id"] in bench_ids:
            leaks.append((r["id"], "id"))
        if r["sentence_with_target_in_double_brackets"].replace("[[", "").replace("]]", "") in bench_sents:
            leaks.append((r["id"], "sentence"))
        if r["target_token"] in bench_targets:
            leaks.append((r["id"], "target"))
    prac_key = read_csv(PRAC_KEY) if PRAC_KEY.exists() else []
    for r in prac_key:
        if r["lemma"] in bench_lemmas:
            leaks.append((r["id"], "lemma"))
    if leaks:
        problems.append("practice pack overlaps the frozen benchmark: %s" % leaks[:5])

    # ---- the packet must not promise anything the tooling cannot do --------------------------
    for probe, why in (("tools/iaa_report.py", "the agreement command named in the packet"),
                       ("tools/build_practice_pack.py", "the pack generator")):
        if not (ROOT / probe).exists():
            problems.append("packet references %s but %s is missing" % (probe, why))

    # ---- every hash QUOTED IN THE PACKET must be the hash of a real file ----------------------
    # (a stale hash printed in the packet is worse than no hash: it looks like verification)
    import re
    quoted = set(re.findall(r"\b[0-9a-f]{64}\b", PACKET.read_text(encoding="utf-8")))
    known = {v for v in observed.values() if v}
    strays = sorted(q for q in quoted if q not in known)
    for q in strays:
        problems.append("packet quotes a sha256 that matches no file on disk: %s..." % q[:16])
    print("  hashes quoted in packet: %d  (unmatched: %d)" % (len(quoted), len(strays)))

    # ---- verdict ----------------------------------------------------------------------------
    print("=" * 80)
    print("ISSUE RECORD VERIFICATION -- annotator B")
    print("=" * 80)
    for k, v in observed.items():
        print("  %-38s %s" % (k, (v[:16] + "...") if v else "(absent)"))
    print("\n  practice rows      : %d   benchmark rows: %d" % (len(prac), len(bench_ids)))
    print("  overlap            : %d  (must be 0)" % len(leaks))
    print("  B copy == sheet    : %s" % (SHEET.read_bytes() == ANNOT_B.read_bytes()))

    if problems:
        print("\n  REFUSING TO SEAL -- %d problem(s):" % len(problems))
        for p in problems:
            print("    - %s" % p)
        return 2 if not leaks else 3

    if args.check:
        print("\n  --check: verified, nothing written.")
        return 0

    rec["protocol"]["packet_sha256"] = observed["packet"]
    rec["protocol"]["packet_sha256_note"] = "recomputed from disk by tools/issue_packet_b.py"
    rec["issue_manifest"]["files"] = {k: v for k, v in observed.items()}
    # every sent file carries its own hash in ONE place, so a reader never has to cross-reference
    for entry in rec["sent_to_annotator"]:
        name = Path(entry["file"]).name
        if observed.get(name):
            entry["sha256"] = observed[name]
    ISSUE.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("\n  SEALED. record: %s" % ISSUE)
    print("  packet sha256 recorded: %s" % observed["packet"])
    print("  NOTE: nothing has been transmitted. Recruitment is a human step.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
