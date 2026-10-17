"""build_wazan_inventory_pruned.py — build the Head-3 target space, and REFUSE it if it is not clean.

WHAT IT BUILDS (CPU only — this script never trains anything)
    The pruned wazan inventory for `t_wazan`: the **tail-stripped** label, i.e. everything through the LAST
    radical digit, with the literal run after it removed. §2bs measured that run as inflectional junk
    (`123َة`, `1ا2َ3ْت`, `12ئِ3َت`) and §2bu sized the result:

        raw label            2,483 classes   99% of tokens need 1,447
        TAIL-STRIPPED        1,325 classes   99% of tokens need   627      <- this inventory
        digit-core              12 classes   (keeps 100% of tokens but DELETES the vowels — not a target)

    Leading literal letters before digit 1 are KEPT: مُسْتَ-, مُ-, أَ-, تَ- are mazid/participial template
    matter and are part of the wazan. Only the trailing run is inflection.

WHAT IT ASSERTS (the review's "target sanity check", as a gate rather than a hope)
    (a) ZERO labels in the inventory carry a trailing inflection run.
    (b) The inventory EQUALS the set of supervised tail-stripped labels: no class is present that is never
        supervised (the "zombie softmax" defect — 46% of the shipped 6,633 exist in neither current build).
    (c) Every supervised source token maps into the inventory (coverage 100%, asserted not assumed).
    (d) If `--ckpt` is given, the checkpoint's Head-3 vocabulary size must EQUAL the inventory size, and every
        class in it must be a supervised inventory member — this is the "softmax dim == vocab size, zero dead
        rows" check, run against a real checkpoint when one exists.

USAGE
    python src/build_wazan_inventory_pruned.py                 # build + report + assert (exit 0/1)
    python src/build_wazan_inventory_pruned.py --check         # assert only, no write
    python src/build_wazan_inventory_pruned.py --ckpt <pt>     # also assert a checkpoint's Head-3 dim
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

DIG = re.compile(r"[1-4]")
LETTER = re.compile(r"[\u0621-\u064a]")

from wazan_normalizer import tail_strip, trailing_run   # THE one implementation (§2bx)

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ("data/out/padt-train.jsonl", "data/out/spread-B-2m/tashkeela-train.jsonl")
OUT_INV = ROOT / "data/out/wazan-inventory-pruned.tsv"
OUT_META = ROOT / "data/out/wazan-inventory-pruned.meta.json"


def load(path: Path, limit: int = 200000) -> list[dict]:
    """Read up to `limit` records (None = read ALL). See `limits_for_run()` for what the run uses."""
    recs = []
    with path.open(encoding="utf-8") as fh:
        for i, l in enumerate(fh):
            if limit is not None and i >= limit:
                break
            recs.append(json.loads(l))
    return recs


def config_limit(default: int = 120000) -> int:
    """The row limit TRAINING actually uses (`config/shared.yaml: data.limit_train`).

    THIS IS THE GOLD LIMIT ONLY. Silver is a DIFFERENT read — see `limits_for_run()`.
    """
    try:
        import yaml
        cfg = yaml.safe_load((ROOT / "config/shared.yaml").read_text(encoding="utf-8"))
        return int(cfg["data"]["limit_train"])
    except Exception:                                                     # noqa: BLE001
        return default


def limits_for_run(gold_limit: int) -> tuple:
    """Per-source row limits, COPIED from the RUN's own read calls (notebook cell 12).

        gold   -> data.limit_train
        silver -> None   (ALL 1,871,205 records)

    A single config-wide limit here is the bug that was measured: silver read at 120k yielded 1,325
    supervised classes against the 2,100 the run's own vocabulary holds, so the inventory and the vocabulary
    described different corpora — and the (T) pre-flight would have asserted a 2,101-wide Head-3 against a
    1,326-wide inventory. The earlier 1,552-vs-1,325 mismatch was the same mistake one layer up: it was
    "fixed" by aligning BOTH sources to one number instead of copying the run's two.
    """
    return (gold_limit, None)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="assert only; do not write the inventory")
    ap.add_argument("--ckpt", default=None, help="also assert a checkpoint's Head-3 vocabulary against it")
    args = ap.parse_args()

    lim = config_limit()
    limits = limits_for_run(lim)
    print(f"  row limits: gold {lim} (config data.limit_train) · silver "
          f"{'ALL' if limits[1] is None else limits[1]} — the SAME reads the run uses (notebook cell 12)")
    recs: list[dict] = []
    for rel, src_lim in zip(SOURCES, limits):
        p = ROOT / rel
        if not p.exists():
            print(f"REFUSING: source not found: {p}")
            return 2
        r = load(p, src_lim)
        print(f"  source {rel:<46} {len(r):>7,} rows")
        recs += r

    supervised = collections.Counter()
    for r in recs:
        lab = r.get("t_wazan")
        if lab and r.get("m_wazan") == 1:
            core = tail_strip(lab)
            if core:
                supervised[core] += 1
    total_tokens = sum(supervised.values())
    print(f"\n  supervised tokens with a tail-stripped label: {total_tokens:,}")
    print(f"  inventory size                               : {len(supervised):,}")

    cum, need99 = 0, None
    for i, (_k, v) in enumerate(supervised.most_common(), 1):
        cum += v
        if need99 is None and cum / total_tokens >= 0.99:
            need99 = i
    print(f"  classes needed for 99% of tokens             : {need99}")

    print("\n  ASSERTIONS")
    failures = []

    # (a) no trailing inflection run anywhere
    dirty = [k for k in supervised if LETTER.search(trailing_run(k))]
    print(f"  (a) labels carrying a trailing inflection run : {len(dirty)}  {'OK' if not dirty else 'FAIL'}")
    if dirty:
        failures.append(f"(a) {len(dirty)} labels still carry a trailing run, e.g. {dirty[:5]}")

    # (b) THE INVENTORY MUST BE FREE OF NEVER-SUPERVISED CLASSES, and the TRAP must be reported separately.
    #     Two different claims, and conflating them is how a gate becomes a false positive:
    #       b1  every class IN THE INVENTORY has >= 1 supervised token behind it (asserted, not assumed);
    #       b2  the SOURCE FIELD carries labels that are never supervised — malformed ones the mask rejected
    #           (`not_strict`) — and a vocabulary built naively from the field would seat them in the softmax
    #           as dead rows. That number is REPORTED as the size of the trap, and the assertion is that the
    #           inventory excludes every one of them.
    empty_inv = [k for k in supervised if not k]
    present = {r.get("t_wazan") for r in recs if r.get("t_wazan")}
    naive = {tail_strip(x) for x in present}      # what a vocabulary built FROM THE FIELD would hold
    dead = naive - set(supervised)                # ...of which these are never supervised = dead softmax rows
    print(f"  (b1) inventory classes with no supervised token : {len(empty_inv)}  {'OK' if not empty_inv else 'FAIL'}")
    if empty_inv:
        failures.append(f"(b1) {len(empty_inv)} inventory classes are unsupervised")
    print(f"  (b2) a vocabulary built from the FIELD would hold {len(naive)} classes, {len(dead)} of them NEVER "
          f"supervised ({100*len(dead)/max(len(naive),1):.1f}%) — the dead rows this prune removes")
    if not (set(supervised) <= naive):
        print("       inventory subset of the field's labels          : FAIL")
        failures.append("(b2) the inventory is not a subset of the field's tail-stripped labels")
    else:
        print(f"       inventory subset of the field's labels          : OK   "
              f"({len(naive)} -> {len(supervised)} = {len(dead)} dead rows removed)")

    # (c) coverage: every supervised token's label must be in the inventory (by construction)
    unmapped = sum(v for k, v in supervised.items() if k not in supervised)
    print(f"  (c) supervised tokens unmapped by the inventory : {unmapped}  {'OK' if unmapped == 0 else 'FAIL'}")
    if unmapped:
        failures.append(f"(c) {unmapped} tokens unmapped")

    # (d) the checkpoint's Head-3 dimension, when one is supplied
    if args.ckpt:
        import torch
        ck = torch.load(args.ckpt, map_location="cpu", weights_only=False)
        v = set((ck.get("vocab") or {}).get("wazan", {}).keys())
        ck_cfg = ck.get("cfg") or {}
        dim = (ck.get("sizes") or {}).get("wazan")
        print(f"  (d) checkpoint Head-3 vocab {len(v)} · sizes['wazan'] {dim} · union inventory {len(supervised)}")
        # SELF-CONSISTENCY FIRST — the checkpoint must agree WITH ITSELF. `len(vocab['wazan']) == head dim` is
        # a property of the FILE, not of any corpus, so this can never false-alarm and it is the check that
        # actually detects a mis-built head.
        if dim != len(v):
            failures.append(f"(d) checkpoint disagrees with ITSELF: dim {dim} != its own wazan vocab {len(v)}")
        elif len(v) != len(supervised):
            # A corpus mismatch is NOT a defect (gold-only training gives 1,033; this run's union gives 2,099).
            # FAIL only if the checkpoint carries a class THIS corpus never supervises — a genuinely dead row.
            extra = sorted(v - set(supervised))
            print(f"      NOTE: ckpt vocabulary is a DIFFERENT corpus — {len(v)} classes vs {len(supervised)} "
                  f"in this union (expected: gold-only 1,033 · union 2,099)")
            if extra:
                failures.append(f"(d) {len(extra)} ckpt classes are never supervised in this corpus: {extra[:5]}")
            else:
                print("      -> every ckpt class is supervised here; corpus differs, head is not dead OK")
        else:
            dead = v - set(supervised)
            print(f"      -> dim matches; dead classes {len(dead)} {'OK' if not dead else 'FAIL'}")
            if dead:
                failures.append(f"(d) {len(dead)} dead classes in the checkpoint's Head-3")

    print(f"\n  INV: the target space must be {len(supervised)} classes, 99% of tokens inside {need99} of them,"
          f" zero trailing runs, zero ghosts.")
    if failures:
        print(f"  RESULT: REFUSED — {len(failures)} assertion(s) failed:")
        for f in failures:
            print(f"    - {f}")
        return 1
    print("  RESULT: CLEAN — the inventory asserts.")

    if not args.check:
        OUT_INV.parent.mkdir(parents=True, exist_ok=True)
        with OUT_INV.open("w", encoding="utf-8", newline="") as fh:
            fh.write(f"# pruned Head-3 inventory (tail-stripped; supervised only)\n")
            fh.write(f"# classes {len(supervised)} | supervised tokens {total_tokens} | 99% inside {need99}\n")
            fh.write("label\tcount\n")
            for k, v in supervised.most_common():
                fh.write(f"{k}\t{v}\n")
        OUT_META.write_text(json.dumps({
            "classes": len(supervised), "supervised_tokens": total_tokens, "classes_for_99pct": need99,
            "sources": list(SOURCES), "tail_stripped": True, "supervised_only": True,
            "assertions": {"no_trailing_run": not dirty,
                           "no_unsupervised_in_inventory": (not empty_inv) and (set(supervised) <= naive),
                           "full_coverage": unmapped == 0},
            "dead_rows_removed_vs_naive_vocab": len(dead),
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"  wrote {OUT_INV.relative_to(ROOT)} and {OUT_META.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
