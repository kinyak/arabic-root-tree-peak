"""build_benchmark_sheet.py — the frozen blind benchmark sheet (docs/BENCHMARK-FREEZE-v2.md).

WHAT IT PRODUCES (all under data/annotation/, prefix configurable):
    <prefix>-sheet.csv        the sheet the ANNOTATOR sees: context and nothing else
    <prefix>-annotator-A.csv  byte-identical to the sheet
    <prefix>-annotator-B.csv  byte-identical to the sheet
    <prefix>-KEY.csv          id -> stratum memberships, primary stratum, lemma, book   (gitignored)
    <prefix>-freeze.json      seed, approved quotas, REALISED counts, sha256 of each artifact

DESIGN CONSTRAINTS (locked in the freeze doc; they are the reason this file is not in src/)
  * Strata are detected from the SURFACE only. No analyser is run here, and none of the
    records' CALIMA-derived fields is used for detection — blindness has to hold at SAMPLING
    time, before an annotator is ever involved.
  * The pool is the silver TEST split (books 90-96). Training never read it. A sentence-level
    overlap check against the TRAIN records is asserted to be empty, so the benchmark cannot be
    scoring the model on text it memorised.
  * IDs are opaque and assigned AFTER one seeded shuffle; no ID encodes stratum or class.
  * A lemma appears AT MOST ONCE in the whole benchmark, which makes lemma-disjointness between
    the test and calibration halves true by construction rather than by hope.
  * Deterministic: same seed + same inputs => byte-identical outputs, which is what makes a
    recorded sha256 meaningful.

USAGE
    python tools/build_benchmark_sheet.py --stats          # measure the pool; writes nothing
    python tools/build_benchmark_sheet.py                  # build + freeze the sheet
CPU only, zero GPU.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import random
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_root import resolve_root  # noqa: E402

# Resolved from the script's own location (or --root). The old code hardcoded
# "G:/arabic-root-tree" AND put the relative strings "src"/"tools" on sys.path, so it only worked
# when invoked from one directory on one machine. Both are gone.
ROOT = resolve_root()
OUT = ROOT / "data" / "annotation"
SILVER_TEST = ROOT / "data/out/spread-B-2m/tashkeela-test.jsonl"
SILVER_TRAIN = ROOT / "data/out/spread-B-2m/tashkeela-train.jsonl"
HOMOGRAPHS = ROOT / "data/abstention_homographs.json"

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))


def set_root(root: Path) -> None:
    """Re-point every path at an explicit --root, before any file is read."""
    global ROOT, OUT, SILVER_TEST, SILVER_TRAIN, HOMOGRAPHS
    ROOT = root
    OUT = ROOT / "data" / "annotation"
    SILVER_TEST = ROOT / "data/out/spread-B-2m/tashkeela-test.jsonl"
    SILVER_TRAIN = ROOT / "data/out/spread-B-2m/tashkeela-train.jsonl"
    HOMOGRAPHS = ROOT / "data/abstention_homographs.json"
    for p in (str(ROOT / "src"), str(ROOT / "tools")):
        if p not in sys.path:
            sys.path.insert(0, p)

# ---- APPROVED QUOTAS (docs/BENCHMARK-FREEZE-v2.md section 9, signed off 2026-10-11) ----------
TOTAL = 1000
TEST_N = 650
CAL_N = 350
QUOTA = {"S1_weak": 0.18, "S2_doubled": 0.12, "S3_homographic": 0.12,
         "S4_clitic": 0.18, "S5_oov": 0.20, "S6_sound": 0.20}
DOCUMENTED_ORDER = ["S1_weak", "S2_doubled", "S3_homographic", "S4_clitic", "S5_oov", "S6_sound"]

DIAC = re.compile(r"[\u064b-\u0652\u0670\u0640]")
ARABIC = re.compile(r"[\u0621-\u063a\u0641-\u064a]")
PUNCT = "،؛؟٬٭۔,;:!?.\"'()[]{}*_—–-\u00ab\u00bb\u2018\u2019\u201c\u201d"

# S4: clitic-heavy. OPERATIONAL DEFINITION — stricter than the doc's example list, so the
# stratum discriminates instead of swallowing most of the corpus. A bare single-letter prefix
# (و/ف/ب/ك/ل) matches a huge share of Arabic words and would make S4 meaningless, so S4 requires
# either a COMPOUND proclitic or an ENCLITIC pronoun. Recorded in the KEY and in the freeze record.
PROCLITIC = re.compile(r"^(وال|فال|بال|كال|لل|ال)")
ENCLITIC = re.compile(r"(هما|هم|هن|كما|كم|كن|ها|ه|ك|نا|ني)$")


def strip_punct(w: str) -> str:
    return w.strip(PUNCT)


# A target must be a clean word: Arabic letters + diacritics ONLY.
# Tashkeela carries printed-edition page markers GLUED to words (`الْفِطْرِ(2/402`), which
# `strip_punct` cannot salvage and which would silently poison the wazān pattern. Such
# sentences are DROPPED whole, so the context is clean too — measured at 10.0% of the first
# sheet (100 of 1,000 rows) before this filter existed.
CLEAN_TARGET = re.compile(r"^[\u0621-\u064a\u064b-\u0652\u0670]+$")
MARKER = re.compile(r"[()\d/]")


def load_pool(path: Path):
    """Candidates from the silver test split: one entry per (book, si) sentence."""
    sents = collections.defaultdict(list)
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            r = json.loads(line)
            sents[(r["book"], r["si"])].append(r)
    out = []
    dropped_marker = 0
    for key, toks in sents.items():
        toks.sort(key=lambda t: int(t["ti"]))
        clean = [strip_punct(t["form"]) for t in toks]
        if any(MARKER.search(f) for f in clean):
            dropped_marker += 1
            continue                          # page marker -> drop the sentence whole
        for i, t in enumerate(toks):
            w = strip_punct(t["form"])
            if not CLEAN_TARGET.match(w):
                continue
            letters = [c for c in w if ARABIC.match(c)]
            if len(letters) < 4:
                continue
            if not any("\u064b" <= c <= "\u0652" for c in w):
                continue                      # must be vocalized to judge a wazan
            lo, hi = max(0, i - 5), min(len(clean), i + 6)
            out.append({"token": w, "bare": t["form_bare"], "lemma": t.get("lemma") or t["form_bare"],
                        "book": t["book"], "si": t["si"], "i": i - lo,
                        "context": list(clean[lo:hi]), "sentence": " ".join(clean)})
    if dropped_marker:
        print("  (dropped %d sentences carrying a page marker)" % dropped_marker)
    return out


def load_train_sentences(path: Path):
    """Every sentence in the TRAIN records, keyed the same way the pool keys its own.

    Used as a hard independence filter, not decoration: the first build attempt found ONE test
    sentence that also occurs in training (Tashkeela repeats passages across books), and refused.
    """
    sents = set()
    cur_key, buf = None, []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            r = json.loads(line)
            k = (r["book"], r["si"])
            if k != cur_key:
                if buf:
                    sents.add(" ".join(strip_punct(t["form"]) for t in buf))
                cur_key, buf = k, []
            buf.append(r)
        if buf:
            sents.add(" ".join(strip_punct(t["form"]) for t in buf))
    return sents


HOMOGRAPH_TAIL = re.compile(r"[\u064b-\u0652\u0670]*\u0627?$")


def load_corpus_homographs(path: Path, cap: int = 6):
    """S3's SECOND detector, the one the freeze doc sanctions: a skeleton whose undiacritized
    form carries >= 2 distinct VOCALIZATIONS in the TRAINING records.

    Surface evidence (spelling variants of the same skeleton), not an analyser's opinion, so
    blindness still holds at sampling time.

    THE THRESHOLD IS MEASURED, NOT GUESSED. Two extremes both fail:
      * the curated 98-surface PADT list alone  -> 182 raw tokens -> supply 1 for a 120 quota;
      * ">= 2 distinct vocalizations" literally -> 50,560 raw tokens (77% of the pool), because
        most words vary only by CASE VOWEL (كِتَابٌ / كِتَابٍ / كِتَابًا). That makes S3 dominant and
        starves the sound control (supply 76 for a 200 quota).
    So the comparison strips the trailing case vowel / tanwin first: what remains must differ
    INTERNALLY (كَتَب vs كُتُب), which is the homography the stratum is about. A difference in the
    final vowel alone is case, not homography.
    """
    seen = collections.defaultdict(set)
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            r = json.loads(line)
            b = r["form_bare"]
            stem = HOMOGRAPH_TAIL.sub("", r["form"])
            if not stem:
                continue
            s = seen.get(b)
            if s is None:
                seen[b] = {stem}
            elif len(s) < cap and stem not in s:
                s.add(stem)
    return {b for b, s in seen.items() if len(s) >= 2}


def load_vocab_forms():
    """The MODEL vocabulary's surface set: min_freq>=2 AND max_vocab=20000, built from TRAIN only.

    Reuses model_arms.Vocabs so this cannot drift from the rule the model actually uses.
    """
    from model_arms import load_config, read_records, Vocabs
    cfg = load_config(smoke=False)
    padt = read_records(cfg["paths"]["train"], cfg["data"]["limit_train"])
    silver = read_records(str(SILVER_TRAIN), None)
    V = Vocabs(padt + silver, cfg["data"]["min_freq"], cfg["data"]["max_vocab"])
    return set(V.form), len(V.form) - 2, cfg["data"]["min_freq"], cfg["data"]["max_vocab"]


def strata_for(rec, homo_surfaces, corpus_homo, vocab_forms):
    """Surface-only detection. Returns the FULL membership set."""
    members = set()
    bare = rec["bare"]
    if re.search(r"[\u0648\u064a]", bare):
        members.add("S1_weak")
    if "\u0651" in rec["token"]:
        members.add("S2_doubled")
    if bare in homo_surfaces or bare in corpus_homo:
        members.add("S3_homographic")
    if PROCLITIC.search(bare) or ENCLITIC.search(bare):
        members.add("S4_clitic")
    if bare not in vocab_forms:
        members.add("S5_oov")
    if not members:
        members.add("S6_sound")
    return members


def primary_of(members, order):
    for s in order:
        if s in members:
            return s
    return "S6_sound"


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stats", action="store_true", help="measure the pool; write nothing")
    ap.add_argument("--seed", type=int, default=20261012)
    ap.add_argument("--prefix", default="bench")
    ap.add_argument("--order", choices=("documented", "specific"), default="documented",
                    help="primary-stratum precedence. 'documented' = S1..S6 as the freeze doc "
                         "specifies; 'specific' = rarest/most specific first")
    ap.add_argument("--pool", default=None)
    ap.add_argument("--root", default=None,
                    help="repository root; defaults to the repo this script sits in")
    args = ap.parse_args()
    if args.root:
        set_root(resolve_root(args.root))
    if not args.pool:
        args.pool = str(SILVER_TEST)
    print("  repo root: %s" % ROOT)

    homo = json.loads(HOMOGRAPHS.read_text(encoding="utf-8"))
    homo_surfaces = set(homo["surfaces"])
    print("  homograph surfaces (built from %s): %d" % (homo.get("built_from", "?"), len(homo_surfaces)))

    pool = load_pool(Path(args.pool))
    print("  candidate tokens in the pool     : %d" % len(pool))

    train_sents = load_train_sentences(SILVER_TRAIN)
    before = len(pool)
    pool = [r for r in pool if r["sentence"] not in train_sents]
    print("  dropped, text also in TRAIN      : %d  (of %d candidates; %d remain)"
          % (before - len(pool), before, len(pool)))

    corpus_homo = load_corpus_homographs(SILVER_TRAIN)
    print("  corpus homograph skeletons       : %d  (>=2 distinct vocalizations in TRAIN)" % len(corpus_homo))

    vocab_forms, vsize, minf, maxv = load_vocab_forms()
    print("  model vocabulary (train only)    : %d types (min_freq=%d, max_vocab=%d)" % (vsize, minf, maxv))

    for rec in pool:
        rec["members"] = strata_for(rec, homo_surfaces, corpus_homo, vocab_forms)

    order = DOCUMENTED_ORDER if args.order == "documented" else \
        ["S5_oov", "S3_homographic", "S4_clitic", "S2_doubled", "S1_weak", "S6_sound"]

    # ---- feasibility: how many DISTINCT-LEMMA candidates does each stratum have? -------------
    seen_lemma = set()
    avail = collections.Counter()
    for rec in sorted(pool, key=lambda r: (r["book"], r["si"], r["i"])):
        if rec["lemma"] in seen_lemma:
            continue
        seen_lemma.add(rec["lemma"])
        avail[primary_of(rec["members"], order)] += 1

    print("\n  --- feasible supply under '%s' ordering (distinct-lemma candidates) ---" % args.order)
    print("  %-16s %8s %8s %s" % ("stratum", "need", "supply", "verdict"))
    need_total = 0
    for s in DOCUMENTED_ORDER:
        need = int(round(QUOTA[s] * TOTAL))
        need_total += need
        ok = "OK" if avail[s] >= need else "SHORT by %d" % (need - avail[s])
        print("  %-16s %8d %8d %s" % (s, need, avail[s], ok))
    print("  %-16s %8d" % ("TOTAL", need_total))

    # cross-stratum membership, which is what makes the ordering rule load-bearing
    print("\n  --- membership overlap (an item may belong to several strata) ---")
    for s in DOCUMENTED_ORDER:
        n = sum(1 for r in pool if s in r["members"])
        print("  %-16s %6d raw tokens" % (s, n))

    if args.stats:
        print("\n  --stats: nothing written.")
        return 0

    # ---- selection: one item per lemma, quota per primary stratum ----------------------------
    rng = random.Random(args.seed)
    by_stratum = collections.defaultdict(list)
    seen_lemma = set()
    for rec in pool:
        if rec["lemma"] in seen_lemma:
            continue
        seen_lemma.add(rec["lemma"])
        by_stratum[primary_of(rec["members"], order)].append(rec)

    chosen, shortfalls = [], {}
    for s in DOCUMENTED_ORDER:
        need = int(round(QUOTA[s] * TOTAL))
        bucket = by_stratum[s]
        rng.shuffle(bucket)
        take = bucket[:need]
        if len(take) < need:
            shortfalls[s] = need - len(take)
        chosen.extend(take)
    if shortfalls:
        print("\n  REFUSING to build: quotas not fillable -> %s" % shortfalls)
        print("  Re-run with a different --order, or (better) record the amendment in the freeze doc.")
        return 3

    # ---- one frozen shuffle, then opaque IDs ------------------------------------------------
    rng.shuffle(chosen)
    for n, rec in enumerate(chosen, start=1):
        rec["id"] = "%s%04d" % (args.prefix.upper(), n)

    # ---- split by lemma (unique by construction) --------------------------------------------
    test = chosen[:TEST_N]
    cal = chosen[TEST_N:TEST_N + CAL_N]
    assert len(test) == TEST_N and len(cal) == CAL_N, (len(test), len(cal))
    tl, cl = {r["lemma"] for r in test}, {r["lemma"] for r in cal}
    assert not (tl & cl), "lemma overlap between test and calibration"
    assert len({r["id"] for r in chosen}) == len(chosen) == TOTAL

    # ---- sentence-level independence from TRAIN (assertion; the pool was filtered above) -----
    overlap = sum(1 for r in chosen if r["sentence"] in train_sents)
    print("\n  sentence overlap with TRAIN records: %d  (must be 0)" % overlap)
    if overlap:
        print("  REFUSING: benchmark text appears in training data.")
        return 4

    # ---- write ------------------------------------------------------------------------------
    OUT.mkdir(parents=True, exist_ok=True)
    # The 9th column (alternatives) was added BEFORE any annotator saw anything: `notes` is
    # human-readable and the agreement tool cannot parse it, so alternative analyses recorded only
    # in prose were unmeasurable, unadjudicable and unusable for top-k scoring. See the freeze
    # doc's Amendment 1. Order is part of the frozen artifact.
    HEADER = ["id", "sentence_with_target_in_double_brackets", "target_token",
              "root", "wazn_pattern", "case", "alternatives", "confidence", "notes"]

    def write_sheet(path: Path, rows):
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, lineterminator="\r\n")
            w.writerow(HEADER)
            for r in rows:
                ctx = list(r["context"])
                ctx[r["i"]] = "[[" + ctx[r["i"]] + "]]"
                w.writerow([r["id"], " ".join(ctx), r["token"], "", "", "", "", "", ""])

    sheet = OUT / ("%s-sheet.csv" % args.prefix)
    write_sheet(sheet, chosen)
    for who in ("A", "B"):
        write_sheet(OUT / ("%s-annotator-%s.csv" % (args.prefix, who)), chosen)

    key = OUT / ("%s-KEY.csv" % args.prefix)
    with key.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\r\n")
        w.writerow(["id", "stratum_memberships", "primary_stratum", "lemma", "book", "si",
                    "target_bare", "split"])
        for r in chosen:
            w.writerow([r["id"], "|".join(sorted(r["members"])),
                        primary_of(r["members"], order), r["lemma"], r["book"], r["si"],
                        r["bare"], "test" if r in test else "cal"])

    realised = collections.Counter(primary_of(r["members"], order) for r in chosen)
    freeze = {
        "sheet": sheet.name, "rows": len(chosen),
        "seed": args.seed, "order": args.order, "pool": str(Path(args.pool).name),
        "approved_quotas": QUOTA, "realised_counts": dict(realised),
        "test_rows": len(test), "calibration_rows": len(cal),
        "lemma_unique": True, "sentence_overlap_with_train": overlap,
        "vocab_types_train_only": vsize, "min_freq": minf, "max_vocab": maxv,
        "sha256": {p.name: sha256_file(p) for p in
                   [sheet, key, OUT / ("%s-annotator-A.csv" % args.prefix),
                    OUT / ("%s-annotator-B.csv" % args.prefix)]},
        "frozen_by": "PI sign-off of section 9, 2026-10-11",
    }
    (OUT / ("%s-freeze.json" % args.prefix)).write_text(
        json.dumps(freeze, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("\n  REALISED primary strata: %s" % dict(realised))
    print("  test / calibration     : %d / %d" % (len(test), len(cal)))
    print("  sheet sha256           : %s" % freeze["sha256"][sheet.name])
    print("  sheet                  : %s" % sheet)
    print("  KEY (do not send)      : %s" % key)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
