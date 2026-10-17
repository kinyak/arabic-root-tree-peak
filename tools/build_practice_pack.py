"""build_practice_pack.py — the piloted practice pack that precedes the frozen benchmark.

WHY IT EXISTS
    A format defect found while a real annotator is 600 rows into a 1,000-row sheet cannot be
    fixed: the sheet is frozen, both annotators must see identical bytes, and a mid-flight
    instruction change would confound annotator with instruction. So the instructions get
    piloted on a SEPARATE small set first, and only after every question is resolved does the
    annotator touch a benchmark row. (v1's own §6 did this for the 50-row pilot; this is the
    same discipline for the 1,000-row benchmark.)

WHAT IT PRODUCES (all under data/annotation/)
    practice-pack.csv      what the annotator B sees -- same 8 columns, same blindness rules
    practice-KEY.csv       id -> stratum memberships, lemma, source, and a per-row PITFALL note
                           (PI ONLY -- reveals the class; never sent)
    practice-freeze.json   seed, quotas, realised counts, sha256 of each artifact

PROVABLY OUTSIDE THE BENCHMARK
    Every practice row is excluded if its sentence, its lemma, or its id appears in the frozen
    1,000. The exclusion is checked AFTER selection as well as filtered during it, and the
    script REFUSES (exit 4) if any overlap survives -- the same fail-closed discipline as
    build_benchmark_sheet.py, because a leaking practice pack silently trains the annotator on
    benchmark rows.

DETERMINISM
    Same seed + same inputs => byte-identical outputs, so the hash recorded in the packet is
    meaningful rather than decorative.

USAGE
    python tools/build_practice_pack.py --stats     # measure availability; writes nothing
    python tools/build_practice_pack.py             # build the pack
CPU only, zero GPU. Strata are detected from the SURFACE only (no analyser).
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import random
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_root import resolve_root  # noqa: E402

# Reuse the frozen builder's loaders and detectors verbatim, so the practice pack cannot drift
# from the benchmark it is piloting (same pool, same S1-S6 definitions, same filters).
from build_benchmark_sheet import (  # noqa: E402
    SILVER_TEST, SILVER_TRAIN, DOCUMENTED_ORDER,
    load_pool, load_train_sentences, load_corpus_homographs, load_vocab_forms,
    strata_for, primary_of, sha256_file, PROCLITIC, ENCLITIC,
)
import build_benchmark_sheet as bbs  # noqa: E402  (module access so --root cannot go stale)

import re  # noqa: E402

# 40 rows, proportioned from the approved 18/12/12/18/20/20 over 1,000 -> 7/5/5/7/8/8.
# Every stratum is deliberately over-sampled relative to its share: the pack's job is to expose
# every class's format question, not to estimate prevalence (which is the benchmark's job).
PACK_TOTAL = 40
PACK_QUOTA = {"S1_weak": 7, "S2_doubled": 5, "S3_homographic": 5,
              "S4_clitic": 7, "S5_oov": 8, "S6_sound": 8}
SEED = 20261013
# SAME 9-column schema as the benchmark sheet -- the practice pack is a pilot of the real task, so
# a pack that lacked `alternatives` would calibrate the annotator on the wrong form.
HEADER = ["id", "sentence_with_target_in_double_brackets", "target_token",
          "root", "wazn_pattern", "case", "alternatives", "confidence", "notes"]


def load_bench_exclusions():
    """Sentences, lemmas and ids already spent by the frozen benchmark."""
    bench_sheet = bbs.OUT / "bench-sheet.csv"
    bench_key = bbs.OUT / "bench-KEY.csv"
    sents, lemmas, ids, pairs = set(), set(), set(), set()
    with bench_sheet.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            ids.add(r["id"])
            pairs.add((r["sentence_with_target_in_double_brackets"], r["target_token"]))
    with bench_key.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            lemmas.add(r["lemma"])
    # the sheet's own sentence text (without the [[ ]] marker) is what the pool compares against
    for sent_with_marker, _ in pairs:
        sents.add(sent_with_marker.replace("[[", "").replace("]]", ""))
    return sents, lemmas, ids, pairs


def pitfall_for(rec, variants):
    """A PI-only note saying what this row is designed to expose. Never sent to the annotator."""
    tips = []
    m = rec["members"]
    if "S2_doubled" in m:
        tips.append("Rule 6 / shadda: one radical is doubled -- the digit is written ONCE "
                    "but its slot still exists (`مُ1َ2ِّ3`, never `1َ2ّ`).")
    if "S1_weak" in m:
        tips.append("weak letter as a radical: check hollow/defective/assimilated -- the elided "
                    "radical still gets its slot (v1 Rule 6).")
    if "S3_homographic" in m:
        v = variants.get(rec["bare"])
        if v:
            tips.append("homographic skeleton (TRAIN vocalizations: %s) -- annotate the reading "
                        "the CONTEXT selects, rival reading in notes (freeze §2a)." % " | ".join(sorted(v)))
        else:
            tips.append("homographic (curated surface list) -- annotate the context-selected "
                        "reading, rival in notes (freeze §2a).")
    if "S4_clitic" in m:
        bits = []
        p = PROCLITIC.search(rec["bare"])
        e = ENCLITIC.search(rec["bare"])
        if p:
            bits.append("pro=%s" % p.group(0))
        if e:
            bits.append("encl=%s" % e.group(0))
        tips.append("clitic-heavy (%s): root+pattern are the STEM only, and `notes` must NAME the "
                    "affixes removed (freeze §2b)." % ", ".join(bits))
    if "S5_oov" in m:
        tips.append("OOV for the model (train-only vocab, min_freq>=2, max_vocab=20k): annotate "
                    "what the word IS, not what it resembles (freeze §2c).")
    if "S6_sound" in m:
        tips.append("sound control: no weak letter, no shadda, no clitic, in-vocab.")
    return "  ".join(tips)


def build_variant_map():
    """bare -> set of distinct internal vocalizations in TRAIN (same rule as S3's second detector)."""
    from build_benchmark_sheet import HOMOGRAPH_TAIL
    seen = collections.defaultdict(set)
    with SILVER_TRAIN.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            r = json.loads(line)
            stem = HOMOGRAPH_TAIL.sub("", r["form"])
            if stem and len(seen[r["form_bare"]]) < 6:
                seen[r["form_bare"]].add(stem)
    return {b: s for b, s in seen.items() if len(s) >= 2}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stats", action="store_true", help="measure availability; write nothing")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--prefix", default="practice")
    ap.add_argument("--root", default=None,
                    help="repository root; defaults to the repo this script sits in")
    args = ap.parse_args()
    if args.root:
        r = resolve_root(args.root)
        bbs.set_root(r)
    print("  repo root: %s" % bbs.ROOT)

    bench_sents, bench_lemmas, bench_ids, bench_pairs = load_bench_exclusions()
    print("  frozen benchmark: %d rows, %d distinct lemmas" % (len(bench_ids), len(bench_lemmas)))

    pool = load_pool(SILVER_TEST)
    train_sents = load_train_sentences(SILVER_TRAIN)
    corpus_homo = load_corpus_homographs(SILVER_TRAIN)
    vocab_forms, vsize, minf, maxv = load_vocab_forms()
    print("  pool: %d candidates (before exclusions)" % len(pool))

    kept, dropped = [], collections.Counter()
    seen_lemma = set()
    for rec in pool:
        if rec["sentence"] in train_sents:
            dropped["text also in TRAIN"] += 1
            continue
        if rec["sentence"] in bench_sents:
            dropped["sentence in benchmark"] += 1
            continue
        if rec["lemma"] in bench_lemmas:
            dropped["lemma spent by benchmark"] += 1
            continue
        if rec["lemma"] in seen_lemma:
            dropped["lemma already in pack"] += 1
            continue
        seen_lemma.add(rec["lemma"])
        kept.append(rec)
    print("  excluded: %s" % dict(dropped))
    print("  eligible (one per lemma, outside the benchmark): %d" % len(kept))

    # targets must not duplicate a benchmark target token either -- cheap extra separation
    bench_targets = {t for _, t in bench_pairs}
    kept = [r for r in kept if r["token"] not in bench_targets]
    print("  after target-token separation            : %d" % len(kept))

    homo_surfaces = set(json.loads(bbs.HOMOGRAPHS.read_text(encoding="utf-8"))["surfaces"])
    for rec in kept:
        rec["members"] = strata_for(rec, homo_surfaces, corpus_homo, vocab_forms)
        rec["primary"] = primary_of(rec["members"], DOCUMENTED_ORDER)

    by_stratum = collections.defaultdict(list)
    for rec in kept:
        by_stratum[rec["primary"]].append(rec)

    print("\n  --- pack supply (need %d) ---" % PACK_TOTAL)
    print("  %-16s %6s %8s %s" % ("stratum", "need", "supply", "verdict"))
    short = {}
    for s in DOCUMENTED_ORDER:
        need, have = PACK_QUOTA[s], len(by_stratum[s])
        ok = "OK" if have >= need else "SHORT by %d" % (need - have)
        if have < need:
            short[s] = need - have
        print("  %-16s %6d %8d %s" % (s, need, have, ok))

    if args.stats:
        print("\n  --stats: nothing written.")
        return 0

    if short:
        print("\n  REFUSING to build: practice quotas not fillable -> %s" % short)
        return 3

    rng = random.Random(args.seed)
    chosen = []
    for s in DOCUMENTED_ORDER:
        bucket = sorted(by_stratum[s], key=lambda r: (r["book"], r["si"], r["i"]))
        rng.shuffle(bucket)
        chosen.extend(bucket[:PACK_QUOTA[s]])
    assert len(chosen) == PACK_TOTAL, len(chosen)

    rng.shuffle(chosen)
    for n, rec in enumerate(chosen, start=1):
        rec["id"] = "%s%04d" % (args.prefix.upper(), n)

    # ---- the exclusions, re-asserted on the FINAL selection (fail closed) --------------------
    leaks = []
    for r in chosen:
        if r["sentence"] in bench_sents:
            leaks.append((r["id"], "sentence"))
        if r["lemma"] in bench_lemmas:
            leaks.append((r["id"], "lemma"))
        if r["id"] in bench_ids:
            leaks.append((r["id"], "id"))
        if r["token"] in bench_targets:
            leaks.append((r["id"], "target"))
    print("\n  overlap with the frozen 1,000: %d  (must be 0)" % len(leaks))
    if leaks:
        print("  REFUSING: practice pack leaks benchmark rows -> %s" % leaks[:5])
        return 4

    # ---- write ------------------------------------------------------------------------------
    bbs.OUT.mkdir(parents=True, exist_ok=True)

    def write_sheet(path: Path, rows):
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, lineterminator="\r\n")
            w.writerow(HEADER)
            for r in rows:
                ctx = list(r["context"])
                ctx[r["i"]] = "[[" + ctx[r["i"]] + "]]"
                w.writerow([r["id"], " ".join(ctx), r["token"], "", "", "", "", "", ""])

    pack = bbs.OUT / ("%s-pack.csv" % args.prefix)
    write_sheet(pack, chosen)

    variants = build_variant_map()
    key = bbs.OUT / ("%s-KEY.csv" % args.prefix)
    with key.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\r\n")
        w.writerow(["id", "stratum_memberships", "primary_stratum", "lemma", "book", "si",
                    "target_bare", "pitfall"])
        for r in chosen:
            w.writerow([r["id"], "|".join(sorted(r["members"])), r["primary"], r["lemma"],
                        r["book"], r["si"], r["bare"], pitfall_for(r, variants)])

    realised = collections.Counter(r["primary"] for r in chosen)
    freeze = {
        "pack": pack.name, "rows": len(chosen), "seed": args.seed,
        "pack_quotas": PACK_QUOTA, "realised_counts": dict(realised),
        "pool": SILVER_TEST.name, "outside_frozen_benchmark": True,
        "overlap_with_benchmark": 0,
        "benchmark_sheet_sha256": hashlib.sha256((bbs.OUT / "bench-sheet.csv").read_bytes()).hexdigest(),
        "sha256": {p.name: sha256_file(p) for p in (pack, key)},
    }
    (bbs.OUT / ("%s-freeze.json" % args.prefix)).write_text(
        json.dumps(freeze, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("  REALISED primary strata: %s" % dict(realised))
    print("  pack sha256            : %s" % freeze["sha256"][pack.name])
    print("  pack                   : %s" % pack)
    print("  KEY (never sent)       : %s" % key)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
