"""Build the closed-class inventory a bypass component would have to cover.

WHY THIS EXISTS
    `renderer.py --measure` reports that 911 of 4,000 PADT-test tokens (22.8%) are
    closed-class and unrendered, and that this is a STRUCTURAL floor: و، ب، ل، في، هذا are
    not root-and-pattern words, so the root+pattern mechanism cannot reach them however
    good the rules get. Raising all-token coverage at all therefore requires a separate
    closed-class path. This script extracts the exact lemma set that path would need.

DISCIPLINE (this repo's, not a preference)
    · The inventory is built from the PADT TRAIN split ONLY and evaluated on TEST.
      Nothing from the evaluation split enters the table — that is the leak that §2x.1
      had to remove once already.
    · Coverage is measured against the TEST floor, and reported as its own number. It is
      NOT evidence for the root-tree claim and must never be folded into it.

OUTPUT
    data/closed_class_inventory.json  (lemmas, surfaces, frequencies, coverage curve)
    console summary

Run:  .venv/Scripts/python.exe src/build_closed_class_inventory.py
"""
from __future__ import annotations

import collections
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.chdir(Path(__file__).resolve().parent.parent)

from paths import OUT

CONTENT = {"NOUN", "VERB", "ADJ", "ADV", "PROPN", "NUM", "AUX"}
TRAIN = OUT / "padt-train.jsonl"
TEST = OUT / "padt-test.jsonl"
VOCAB = OUT / "vocab.json"
ART = Path("data/closed_class_inventory.json")


def load_upos_tags():
    v = json.loads(VOCAB.read_text(encoding="utf-8"))
    return {i: tag for tag, i in v["upos"].items()}


def rows(path, tags):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            r["_tag"] = tags.get(r.get("upos"), "?")
            yield r


def main():
    tags = load_upos_tags()

    # ---- TRAIN: the inventory
    lemma_freq = collections.Counter()
    surf_freq = collections.Counter()
    lemma_surfaces = collections.defaultdict(collections.Counter)
    lemma_tags = collections.defaultdict(set)
    by_tag = collections.Counter()
    n_train = n_train_closed = 0
    for r in rows(TRAIN, tags):
        n_train += 1
        if r["_tag"] in CONTENT:
            continue
        n_train_closed += 1
        by_tag[r["_tag"]] += 1
        lemma_freq[r["lemma"]] += 1
        surf_freq[r["form_bare"]] += 1
        lemma_surfaces[r["lemma"]][r["form_bare"]] += 1
        lemma_tags[r["lemma"]].add(r["_tag"])

    # ---- TEST: the floor this must cover. Tags come from the TEST record itself, so the
    # per-UPOS split below is a PARTITION (a lemma can carry two tags, and counting by
    # lemma would double-count the same token).
    test_lemmas = collections.Counter()
    test_surfaces = collections.Counter()
    test_by_tag = collections.Counter()
    covered_by_tag = collections.Counter()
    n_test = n_test_closed = 0
    for r in rows(TEST, tags):
        n_test += 1
        if r["_tag"] in CONTENT:
            continue
        n_test_closed += 1
        test_by_tag[r["_tag"]] += 1
        if r["lemma"] in lemma_freq:
            covered_by_tag[r["_tag"]] += 1
        test_lemmas[r["lemma"]] += 1
        test_surfaces[r["form_bare"]] += 1

    covered = sum(c for lem, c in test_lemmas.items() if lem in lemma_freq)
    covered_surf = sum(c for s, c in test_surfaces.items() if s in surf_freq)
    missing = test_lemmas.most_common()
    missing = [(lem, c) for lem, c in missing if lem not in lemma_freq]

    print("=" * 96)
    print("CLOSED-CLASS INVENTORY — built from PADT TRAIN, measured on PADT TEST")
    print("=" * 96)
    print(f"\nTRAIN: {n_train:,} tokens, of which closed-class {n_train_closed:,} "
          f"({100*n_train_closed/max(n_train,1):.1f}%)")
    print(f"  distinct closed-class lemmas   : {len(lemma_freq):,}")
    print(f"  distinct closed-class surfaces : {len(surf_freq):,}")
    print(f"  by UPOS: " + " · ".join(f"{k} {v:,}" for k, v in by_tag.most_common()))
    print(f"\nTEST: {n_test:,} tokens, of which closed-class {n_test_closed:,} "
          f"({100*n_test_closed/max(n_test,1):.1f}%)")
    print(f"  covered by the TRAIN LEMMA table   : {covered:,}/{n_test_closed:,} = "
          f"{100*covered/max(n_test_closed,1):.1f}%")
    print(f"  covered by the TRAIN SURFACE table : {covered_surf:,}/{n_test_closed:,} = "
          f"{100*covered_surf/max(n_test_closed,1):.1f}%")

    # ---- how few lemmas buy how much of the floor
    ranked = lemma_freq.most_common()
    cum, curve = 0, []
    for i, (lem, c) in enumerate(ranked, 1):
        cum += test_lemmas.get(lem, 0)
        curve.append((i, lem, c, cum))
    print(f"\n  CONCENTRATION — lemmas needed to reach a share of the COVERABLE test floor "
          f"({covered:,} tokens):")
    for target in (0.50, 0.80, 0.90, 0.95, 0.99, 1.00):
        need = next((i for i, _, _, c in curve if c >= target * covered), None)
        print(f"    {int(target*100):>3}% -> top {need:,} lemmas" if need
              else f"    {int(target*100):>3}% -> (not reached)")

    # ---- the floor is NOT one kind of thing: punctuation is identity, function words
    # need a table, and X is where foreign/unknown tokens land. Split it per UPOS so the
    # bypass spec can say what each part actually requires.
    print(f"\n  THE FLOOR BY UPOS — what each part of the bypass actually needs")
    print(f"    {'upos':<7}{'train':>9}{'lemmas':>9}{'test':>8}{'test covered':>13}   requirement")
    need_by_tag = {
        "PUNCT": "identity — no table", "SYM": "identity — no table",
        "ADP": "table", "CCONJ": "table", "PRON": "table", "DET": "table",
        "SCONJ": "table", "PART": "table", "INTJ": "table",
        "X": "NOT closed-class semantics — foreign/unknown; needs its own policy",
    }
    for tag, ntok in test_by_tag.most_common():
        lems = {lem for lem, tags_ in lemma_tags.items() if tag in tags_}
        print(f"    {tag:<7}{by_tag.get(tag,0):>9,}{len(lems):>9,}{ntok:>8,}"
              f"{covered_by_tag.get(tag,0):>13,}   {need_by_tag.get(tag, '?')}")
    print(f"\n    PARTITION CHECK: per-tag test totals sum to {sum(test_by_tag.values()):,}, "
          f"the floor is {n_test_closed:,} -> "
          f"{'OK' if sum(test_by_tag.values()) == n_test_closed else 'MISMATCH'}")

    print(f"\n  TOP 30 LEMMAS (train frequency) — the head of the bypass table:")
    for lem, c in ranked[:30]:
        t = test_lemmas.get(lem, 0)
        print(f"    {lem:<14} train {c:>7,}   test {t:>6,}   "
              f"surfaces {list(lemma_surfaces[lem])[:3]}")

    print(f"\n  TEST lemmas NOT in the train inventory: {len(missing):,} "
          f"({sum(c for _, c in missing):,} tokens)")
    if missing:
        print("    (unseen closed-class lemmas — a bypass built from train alone misses")
        print("     these; they are the tail, so size the component to the head)")
        for lem, c in missing[:8]:
            print(f"      {lem:<14} {c:>4,}")

    ART.write_text(json.dumps({
        "built_from": "PADT train",
        "measured_on": "PADT test",
        "why": "closed-class tokens have no root; the root+pattern mechanism cannot "
               "reach them (CHALLENGES.md §2x.8)",
        "train": {"tokens": n_train, "closed_class_tokens": n_train_closed,
                  "distinct_lemmas": len(lemma_freq),
                  "distinct_surfaces": len(surf_freq),
                  "by_upos": dict(by_tag)},
        "test": {"tokens": n_test, "closed_class_tokens": n_test_closed,
                 "covered_by_lemma_table": covered,
                 "covered_by_surface_table": covered_surf,
                 "unseen_lemmas": len(missing)},
        "coverage_curve": [{"rank": i, "lemma": lem, "train_freq": c, "test_cum": cum}
                           for i, lem, c, cum in curve],
        "lemmas": [{"lemma": lem, "train_freq": c,
                    "surfaces": dict(lemma_surfaces[lem])} for lem, c in ranked],
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n  artifact -> {ART}")


if __name__ == "__main__":
    main()
