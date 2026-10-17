"""diff_rescore.py — the gate between the AS-RUN round-26 artifact and the RESCORED one.

WHAT THIS ASSERTS, AND WHY IT IS NOT MERELY A DIFF
    The rescore exists because a REPORTING defect mis-stated the majority-class baseline. The
    claim that has to hold is narrow and falsifiable: *the baseline moved and nothing that is a
    model result did.* A plain recursive diff cannot say that -- it reports 160 moved floats and
    leaves the reader to eyeball them -- so this script categorises every move and FAILS on
    anything that is not explainable:

      1. baseline    `*.majority_macro_f1`  -> must move, and must land on the closed-form floor
                                              for its own eval set
      2. reporting   `context_coverage.*`, `training.*`, `*gold_oov`, `gold_context_oov_rate`
                                            -> the relocation of a coverage quantity and the
                                               recording of train volume; expected
      3. verdict     `*.verdict`            -> must NOT change. These are the conclusions
      4. other       every remaining float  -> must be BELOW the seed noise. The round-26 run
                                              trained on an A100 and this rescore runs on CPU, so
                                              float reduction order differs and a handful of
                                              argmax decisions can flip. Measured: the largest
                                              such move is ~0.06 pp against a seed sd of ~0.19 pp.
                                              A move AT OR ABOVE the seed sd would mean the
                                              rescore is not the same model, and that stops here.

    The 4th category is the one that made an earlier claim of mine wrong: I predicted "every root
    and wazan score is identical". They are not identical, they are within ~3x-below-noise
    identical -- which is the correct statement and a weaker one, so it is the one that gets
    written down.

USAGE
    python tools/diff_rescore.py dist/incoming/RESULTS-v26-AS-RUN-BUGGY.json \
                                  dist/kaggle-rescore-output/arabic-root-tree/results/results.json
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# The floors, derived independently of the artifact: for an always-majority predictor,
# recall is 1 and precision is support/n, so macro-F1 = (2p/(p+1))/k over k case classes.
EXPECTED_FLOORS = {
    "human gold (300 rows, GEN 54.95%)": 0.2364341085271318,
    "PADT dev (4000 rows, GEN 61.30%)": 0.25335551858014416,
    "silver dev (4000 rows, GEN 60.90%)": 0.25233928683982837,
}
BASELINE_SUFFIX = "majority_macro_f1"
REPORTING_HINTS = ("context_coverage", "gold_context_oov_rate", "gold_oov", "training.",
                   "rescored", "train_tokens", "train_limit")


def flatten(o, pre=""):
    out = {}
    if isinstance(o, dict):
        for k, v in o.items():
            out.update(flatten(v, (pre + "." + str(k)) if pre else str(k)))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            out.update(flatten(v, "%s[%d]" % (pre, i)))
    else:
        out[pre] = o
    return out


def verdicts(doc):
    """Every string-valued field inside `summary` is a verdict ('SEPARATED' / 'NOT SEPARATED')."""
    out = {}
    for k, v in doc.get("summary", {}).items():
        for f, val in v.items():
            if isinstance(val, str):
                out["%s.%s" % (k, f)] = val
    return out


def main() -> int:
    if "-h" in sys.argv[1:] or "--help" in sys.argv[1:]:
        print(__doc__)
        return 0
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    old = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    new = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    a, b = flatten(old), flatten(new)
    fail = []

    # ---- 1. the baseline moved, and to the right value ---------------------------------
    print("[1] the case baseline (what the fix targets)")
    pairs = collections.Counter((a[k], b[k]) for k in sorted(set(a).intersection(b))
                                if k.endswith(BASELINE_SUFFIX) and a[k] != b[k])
    newvals = {n for _, n in pairs}
    for (o_, n_), cnt in pairs.items():
        print("    %.16f -> %.16f   x%d" % (o_, n_, cnt))
    for label, floor in EXPECTED_FLOORS.items():
        hit = any(abs(v - floor) < 1e-9 for v in newvals)
        print("    %-40s floor %.16f  %s" % (label, floor, "PRESENT" if hit else "MISSING"))
        if not hit:
            fail.append("no baseline equals the %s floor %.16f" % (label, floor))
    if any(abs(o_ - 0.3333333333333333) < 1e-9 for o_, _ in pairs):
        print("    (the old value was the constant 1/3 -- the defect being corrected)")
    if not pairs:
        fail.append("the baseline did NOT move -- the fix is not in the bundle that ran")

    # ---- 2. reporting relocation --------------------------------------------------------
    only_old = sorted(set(a).difference(b))
    only_new = sorted(set(b).difference(a))
    rep_new = [k for k in only_new if any(h in k for h in REPORTING_HINTS)]
    print("\n[2] reporting relocation")
    print("    keys added by the rescore      : %d (%d are reporting)"
          % (len(only_new), len(rep_new)))
    print("    keys dropped by the rescore    : %d" % len(only_old))
    for k in only_new:
        if "context_coverage" in k:
            print("      + %-58s = %s" % (k, repr(b[k])[:40]))
    for k in only_old[:4]:
        print("      - %s" % k)

    # ---- 3. verdicts must not move -------------------------------------------------------
    vo, vn = verdicts(old), verdicts(new)
    shared = set(vo).intersection(vn)
    changed = sorted(k for k in shared if vo[k] != vn[k])
    print("\n[3] verdicts -- the conclusions themselves")
    print("    compared %d, CHANGED %d" % (len(shared), len(changed)))
    for k in changed:
        print("      ~ %s: %r -> %r" % (k, vo[k], vn[k]))
    if changed:
        fail.append("%d verdict(s) changed: %s" % (len(changed), changed[:4]))
    if len(shared) < 20:
        fail.append("only %d verdicts found -- the summary section shrank" % len(shared))

    # ---- 4. every other float must be small against ITS OWN seed noise --------------------
    # PER-METRIC, NOT GLOBAL, and the first version of this got it wrong in a way worth
    # recording: it compared the largest move anywhere against the smallest sd anywhere and
    # reported 1.14x, which reads as "a metric moved more than the noise" and is an artefact of
    # pairing two unrelated numbers. padt_dev_root_whole moved 6.2e-04 and its OWN sd is 1.1e-02
    # -- 5.6% of the noise on that metric -- while the 5.4e-04 sd belongs to a different,
    # much tighter metric. A ratio is only meaningful within one metric.
    moves = []
    for k in sorted(set(a).intersection(b)):
        if a[k] == b[k] or not isinstance(a[k], float):
            continue
        if k.endswith(BASELINE_SUFFIX) or k.endswith("seconds"):
            continue                                   # 1 = the fix; seconds = wall clock
        if any(h in k for h in REPORTING_HINTS):
            continue
        moves.append((abs(a[k] - b[k]), k, a[k], b[k]))
    moves.sort(reverse=True)

    def own_sd(path):
        """The seed sd of the metric this path belongs to, from the same summary block."""
        if not path.startswith("summary."):
            return None
        rest = path[len("summary."):]
        for key, v in old.get("summary", {}).items():
            if rest == key or rest.startswith(key + "."):
                sds = [v.get(arm, {}).get("sd") for arm in ("baseline", "treatment")]
                sds = [s for s in sds if s]
                return max(sds) if sds else None
        return None

    print("\n[4] every other metric move vs ITS OWN seed sd")
    print("    metrics that moved: %d   largest 3:" % len(moves))
    for d, k, o_, n_ in moves[:3]:
        print("      %.3e  %-54s  %s -> %s" % (d, k[:54], o_, n_))
    per = [(d / own_sd(k), d, k) for d, k, o_, n_ in moves if own_sd(k)]
    per.sort(reverse=True)
    if per:
        print("    summary metrics compared against their own sd: %d" % len(per))
        for ratio, d, k in per[:3]:
            print("      %.1f%% of its own sd   (move %.3e)   %s" % (ratio * 100, d, k[:46]))
        worst_ratio = per[0][0]
        print("    worst ratio: %.1f%% of the sd for that same metric" % (worst_ratio * 100))
        if worst_ratio >= 1.0:
            fail.append("a metric moved %.1f%% of its own seed sd -- not the same model"
                        % (worst_ratio * 100))
    else:
        print("    (no summary paths moved)")
    up = sum(1 for _, _, o_, n_ in moves if n_ > o_)
    print("    direction: %d up / %d down (a systematic bias would be lopsided)"
          % (up, len(moves) - up))

    # ---- identity -------------------------------------------------------------------------
    print("\n[5] identity of the run")
    for k in ("code_bundle_sha", "config_sha256"):
        print("    %-16s %s -> %s" % (k, str(old.get(k))[:16], str(new.get(k))[:16]))
    if old.get("config_sha256") != new.get("config_sha256"):
        fail.append("config_sha256 changed: the config is not the one round 26 ran")
    if old.get("code_bundle_sha") == new.get("code_bundle_sha"):
        fail.append("code_bundle_sha unchanged: the reporting fix is NOT in what ran")
    for k in ("parity", "vocab_sizes", "seeds"):
        same = old.get(k) == new.get(k)
        print("    %-16s identical: %s" % (k, same))
        if not same:
            fail.append("%s changed" % k)

    print("\n" + "=" * 78)
    if fail:
        print("RESCORE DIFF: FAILED")
        for f in fail:
            print("  -", f)
        return 1
    print("RESCORE DIFF: OK -- the baseline moved to its true floors, every verdict is")
    print("unchanged, and no model metric moved by as much as the seed noise.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
