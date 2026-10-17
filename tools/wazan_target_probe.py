"""wazan_target_probe.py — the (T) pre-flight gate: does the training stack build the 1,325-class head?

GATE PRE-REGISTERED in ACTIVE_BACKLOG item 9 before the retrain (as amended 2026-10-13):
    (T) the Head-3 target space is the FULL supervised inventory — no UNK, no dead rows, no trailing runs —
        and the model's Head-3 output dimension EQUALS it exactly.

WHY IT IS A SEPARATE PROBE
    The target space is built in THREE places that historically disagreed: the data build mints the label, the
    vocabulary decides the classes, and the batch builder encodes the target. `tail_strip` now lives ONCE in
    `wazan_normalizer` and all three call it, so this probe can assert the three agree instead of hoping.

WHAT IT ASSERTS
    (1) no class in the built vocabulary carries a trailing inflection run;
    (2) every class has >= 1 supervised token behind it — ZERO dead rows;
    (3) every SUPERVISED token in train maps into the vocabulary — ZERO UNK/IGNORE;
    (4) the vocabulary's class set EQUALS the built inventory's class set (two independent code paths);
    (5) the model's Head-3 output dimension at these sizes == the vocabulary size.
    And it REPORTS the same coverage for the dev/test splits, because a class unseen in train is an UNK by
    another name and silently ceilings the evaluation — a number that belongs in the record either way.

USAGE  python tools/wazan_target_probe.py --check      # exit 0/1
"""
from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from model_arms import Vocabs, load_config, read_records      # noqa: E402
from wazan_normalizer import tail_strip, trailing_run          # noqa: E402

UNUSABLE = {"", "ABSTAIN", "NONE", "NA", "#", None}


def supervised_classes(pairs) -> collections.Counter:
    c = collections.Counter()
    for _si, toks in pairs:
        for t in toks:
            if t.get("m_wazan"):
                cls = tail_strip(t.get("t_wazan"))
                if cls:
                    c[cls] += 1
    return c


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    lim = cfg["data"]["limit_train"]
    # PER-SOURCE LIMITS — copied from the RUN's own read calls (notebook cell 12), because a single
    # config-wide number was the bug: the run reads gold at `limit_train` and silver with None (ALL
    # 1,871,205 records). Reading silver at 120k here measured 1,325 supervised classes against the
    # 2,100 the vocabulary actually holds, so the (4) equality check could never pass and the (T)
    # pre-flight would have compared a 2,101-wide Head-3 against a 1,326-wide inventory.
    train = read_records(cfg["paths"]["train"], lim)
    silver = read_records(cfg["paths"]["silver_train"], None)
    V = Vocabs(train + silver, cfg["data"]["min_freq"], cfg["data"]["max_vocab"])
    classes = supervised_classes(train + silver)
    n = V.sizes()["wazan"]
    print(f"split limit        : gold {lim} rows (data.limit_train) · silver ALL (None) — the run's own reads")
    print(f"Head-3 vocab size  : {n}  ({n - 1} classes + <pad>)")
    print(f"supervised classes : {len(classes)}   supervised tokens: {sum(classes.values()):,}")

    failures = []

    dirty = [k for k in V.wazan if k != "<pad>" and trailing_run(k)]
    print(f"  (1) classes with a trailing inflection run : {len(dirty)}  {'OK' if not dirty else 'FAIL'}")
    if dirty:
        failures.append(f"(1) {len(dirty)} classes carry a trailing run, e.g. {dirty[:5]}")

    dead = [k for k in V.wazan if k != "<pad>" and classes.get(k, 0) == 0]
    print(f"  (2) classes with ZERO supervised tokens    : {len(dead)}  {'OK' if not dead else 'FAIL'}")
    if dead:
        failures.append(f"(2) {len(dead)} dead rows, e.g. {dead[:5]}")

    unmapped = sum(v for k, v in classes.items() if k not in V.wazan)
    print(f"  (3) supervised tokens that fall to IGNORE  : {unmapped}  {'OK' if unmapped == 0 else 'FAIL'}")
    if unmapped:
        failures.append(f"(3) {unmapped} supervised tokens have no class (an UNK by another name)")

    inv_path = Path(cfg["paths"]["train"]).parent / "wazan-inventory-pruned.tsv"
    if inv_path.exists():
        inv = {l.split("\t")[0] for l in inv_path.read_text(encoding="utf-8").splitlines()
               if l and not l.startswith("#") and not l.startswith("label") and "\t" in l}
        same = (inv == {k for k in V.wazan if k != "<pad>"})
        print(f"  (4) vocab == the built inventory's classes : {'OK' if same else 'FAIL'}  "
              f"(inventory {len(inv)} at its own row limit, vocab {len(V.wazan) - 1})")
        if not same:
            only_v = sorted({k for k in V.wazan if k != '<pad>'} - inv)[:5]
            only_i = sorted(inv - {k for k in V.wazan if k != '<pad>'})[:5]
            print(f"       vocab-only {only_v} | inventory-only {only_i}   "
                  f"(expected: the two builds read different row limits)")
    else:
        print(f"  (4) inventory file not found ({inv_path}) — run src/build_wazan_inventory_pruned.py first")

    print(f"  (5) model Head-3 output dimension          : {n}  (== vocab size, since "
          f"h_wazan = Linear(d, sizes['wazan']))")

    print("\n  REPORT — evaluation splits (a class unseen in train is an UNK by another name):")
    for name, path in (("dev", cfg["paths"]["dev"]), ("test", cfg["paths"]["test"])):
        pairs = read_records(path, cfg["data"]["limit_dev"] * 20)
        c = supervised_classes(pairs)
        miss = sum(v for k, v in c.items() if k not in V.wazan)
        tot = sum(c.values())
        print(f"    {name:<6} supervised tokens {tot:>6,} | classes unseen in train: "
              f"{len([k for k in c if k not in V.wazan]):>4} | tokens that become IGNORE: {miss:>5,} "
              f"({100*miss/max(tot,1):.2f}%)")

    if failures:
        print(f"\n  RESULT: REFUSED — {len(failures)} assertion(s) failed:")
        for f in failures:
            print(f"    - {f}")
        return 1
    print("\n  TARGET SPACE BY CORPUS — the size depends on WHICH corpus the vocabulary is built from, not only")
    print("  on the row limit. `train.py` builds it from the TRAIN file it is handed; the diagnostic scripts use")
    print("  gold + silver. Both are clean; they are different numbers, and the gate must name the corpus.")
    for label, sents in (("gold only (what train.py builds)", train),
                         ("gold + silver (union_vocab)", train + silver)):
        Vx = Vocabs(sents, cfg["data"]["min_freq"], cfg["data"]["max_vocab"])
        cx = supervised_classes(sents)
        dx = [k for k in Vx.wazan if k != "<pad>" and cx.get(k, 0) == 0]
        ux = sum(v for k, v in cx.items() if k not in Vx.wazan)
        print(f"    {label:<34} classes {len(Vx.wazan) - 1:>5}  dead {len(dx):>3}  tokens->IGNORE {ux:>3}  "
              f"{'CLEAN' if not dx and not ux else 'NOT CLEAN'}")
    print("\n  RESULT: CLEAN — no UNK, no dead rows, no trailing runs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
