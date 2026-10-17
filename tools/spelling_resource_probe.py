"""spelling_resource_probe.py — guard the SHIPPED corpus spelling resource and its case-aware selector.

WHAT IT GUARDS
    Two shipped changes, both measured before they landed and both ON by default in the live tree:
      §2bn  the corpus resource          (confidence rule, share >= 0.95)      592 -> 695 = 71.4%
      §2bo  the CASE-AWARE selector      (consult_case, the shipped default)  695 -> 827 = 85.0%
      §2bv  the SOFT STEM-BOUNDARY selector (same consult_case, soft prior + the case head read at the
            enclitic boundary)                    827 -> 838 = 86.1%, worst per-class delta +0.0
    This is the standing guard every shipped verdict has: it FAILS LOUDLY if a number moves, because a changed
    verdict must re-open the decision rather than pass unnoticed.

`--check` ASSERTS
    (a) SHIPPED DEFAULT (soft stem-boundary selector + fallback)     838/973 = 86.1%
    (b) attribution switch: ARABIC_SPELLING_RESOURCE=0 -> the surface pipeline, 592/973 = 60.8%
    (c) no class below its PRE-RESOURCE baseline (sound 70.3 · hollow 44.0 · defective 38.1 ·
        doubled 47.8 · assimilated 31.5 · quadriliteral 60.0)
    (d) LEGALITY: feeding the pipeline a SKELETONISED token (every combining mark erased) leaves the number
        bit-identical. §5.2 bans reading the gold token's diacritics; this pins that prohibition as a number.

    Exit 0 = every pin reproduces. Exit 1 = a pin DRIFTED (both numbers printed); re-open §2bn/§2bo.

WHY THE OTHER PROBES PIN THIS OFF
    `tools/diacritic_split.py`, `tools/tanwin_probe.py` and `tools/hollow_probe.py` measure the SURFACE pipeline
    and set `ARABIC_SPELLING_RESOURCE=0` themselves, so their numbers keep their old meaning (measured: the pin
    cascade fired when the resource landed — diacritic_split exit 1, tanwin_probe -189 -> -266, hollow_probe
    "net +1 != pinned +0" — and was fixed by pinning the new input off, never by rewriting their pins).

USAGE
    python tools/spelling_resource_probe.py            # full table
    python tools/spelling_resource_probe.py --check    # assert the pins, exit 0/1
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))

from final_surface import render_triple, stem_match, score_final_surface, case_int   # noqa: E402
from eval_harness import root_class                                                  # noqa: E402

RULER = ROOT / "data" / "annotation" / "bench-gold.jsonl"
UNUSABLE = {"", "ABSTAIN", "NONE", "NA", "#", None}
MARKS = re.compile(r"[\u064B-\u0652\u0653-\u0655\u0670\u0640\u06D6-\u06ED]")

P_SHIPPED = 838          # soft stem-boundary selector + confidence fallback (the default, §2bv)
P_SURFACE = 592          # resource off (ARABIC_SPELLING_RESOURCE=0) — the pre-shipment pipeline
P_CONFIDENCE_ONLY = 695  # confidence rule alone (share >= 0.95), the §2bn step, now the fallback
PRE_RESOURCE_BASELINE = {"sound": 70.3, "hollow": 44.0, "defective": 38.1,
                         "doubled": 47.8, "assimilated": 31.5, "quadriliteral": 60.0}


def usable(r) -> bool:
    if r.get("root") in UNUSABLE or r.get("wazn_pattern") in UNUSABLE:
        return False
    return 2 <= len([c for c in str(r["root"]) if c != "."]) <= 5


def measure(rows, enabled: bool, skeletonise=False):
    """Score the pipeline with the resource explicitly on or off, optionally handing it SKELETONISED tokens."""
    os.environ["ARABIC_SPELLING_RESOURCE"] = "1" if enabled else "0"
    pairs, per = [], {}
    for r in rows:
        token = r["target_token"]
        if skeletonise:
            token = MARKS.sub("", token).replace("\u0671", "\u0627")
        pred, _ = render_triple(root=r["root"], pattern=r["wazn_pattern"], case=case_int(r.get("case")),
                                token=token, repairs=True)
        pairs.append((r["target_token"], pred))
        c = root_class(r["root"])
        n, k = per.get(c, (0, 0))
        per[c] = (n + 1, k + (1 if stem_match(r["target_token"], pred) else 0))
    return score_final_surface(pairs)["stem_correct"], per


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="assert the pins; exit 1 on drift")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    rows = [r for r in (json.loads(l) for l in RULER.read_text(encoding="utf-8").splitlines() if l.strip())
            if usable(r)]
    n = len(rows)

    shipped, per = measure(rows, True)
    surface, _ = measure(rows, False)
    skeletoned, _ = measure(rows, True, skeletonise=True)

    print(f"{'setting':<46}{'correct':>9}{'pct':>9}")
    print(f"{'resource OFF (surface pipeline, attribution)':<46}{surface:>9}{100*surface/n:>8.1f}%")
    print(f"{'resource ON, confidence rule only (share 0.95)':<46}{P_CONFIDENCE_ONLY:>9}"
          f"{100*P_CONFIDENCE_ONLY/n:>8.1f}%  (pinned, not re-measured here)")
    print(f"{'SHIPPED DEFAULT (case-aware selector)':<46}{shipped:>9}{100*shipped/n:>8.1f}%")
    print(f"{'SHIPPED, token SKELETONISED (legality pin)':<46}{skeletoned:>9}{100*skeletoned/n:>8.1f}%")
    print(f"\n{'class':<16}{'n':>5}{'shipped':>9}{'fid':>8}{'pre-resource':>14}  delta")
    drift = []
    for c, (cn, k) in sorted(per.items(), key=lambda kv: -kv[1][0]):
        fid = 100 * k / cn
        b = PRE_RESOURCE_BASELINE.get(c)
        if b is not None and fid < b - 0.05:
            drift.append(f"{c} {fid:.1f}% < pre-resource {b:.1f}%")
        print(f"{c:<16}{cn:>5}{k:>9}{fid:>7.1f}%{'' if b is None else f'{b:>13.1f}%'}  "
              f"{'' if b is None else f'{fid-b:+.1f}'}")

    print()
    checks = [
        ("shipped default (soft stem-boundary selector) is 838", shipped == P_SHIPPED, shipped, P_SHIPPED),
        ("attribution switch (resource OFF) is 592", surface == P_SURFACE, surface, P_SURFACE),
        ("erasing the gold token's marks changes nothing (legality)", skeletoned == shipped, skeletoned, shipped),
        ("no class below its pre-resource baseline", not drift, "; ".join(drift) or "none", "none"),
    ]
    ok = True
    for label, passed, got, want in checks:
        ok &= bool(passed)
        print(f"  {'OK  ' if passed else 'DRIFT'} {label}" + ("" if passed else f"  (got {got}, pinned {want})"))

    if args.json:
        Path(args.json).write_text(json.dumps(
            {"shipped": shipped, "surface": surface, "skeletonised": skeletoned, "n": n, "drift": drift,
             "pins": {"shipped": P_SHIPPED, "surface": P_SURFACE, "confidence_only": P_CONFIDENCE_ONLY}},
            ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.check and not ok:
        print("\nFAILED: a shipped pin drifted — re-open EVIDENCE_LOG §2bn/§2bo before trusting these numbers.")
        return 1
    if args.check:
        print("\nOK — the shipped numbers reproduce, the legality pin holds, and no class regressed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
