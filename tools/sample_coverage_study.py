"""sample_coverage_study.py — CPU only, zero GPU. Is the DATA-SCALE lever real, and is SIZE
even the right axis?

WHY THIS EXISTS
    CHALLENGES 2ad ruled out vocabulary settings: 126 of the 141 OOV gold words have zero
    occurrences in the training records, while all 126 ARE in the corpus. The surviving
    hypothesis is data scale. This measures it before any GPU is rented, and it measures the
    two axes SEPARATELY:

      SIZE     -- more tokens under the same sampling strategy
      STRATEGY -- the SAME token budget, drawn in order vs drawn across books

    The second axis matters because the builder's --limit is TOKENS, not records, and it
    streams books in order: --limit 120000 therefore consumes the OPENING OF ONE BOOK
    (book 8), not 120k tokens spread over the train split's 82 books.

    Split design is already document-level (books 0-7 dev, 8-89 train, 90-96 test; no book
    in two splits) and the leakage check below VERIFIES that rather than trusting the
    comment. Front matter is detected from the data (lines that recur at the top of many
    books), not from a guessed prefix list.

CAVEAT THAT TRAVELS WITH EVERY NUMBER HERE: this counts types in the RAW corpus text, which
is upper-bounded by what the CALIMA pipeline will actually turn into records. It measures
lexical AVAILABILITY, which is the right quantity for a coverage curve; the record-level
coverage after the build must be confirmed by building, not assumed.

Reads: data/raw/tashkeela-books.jsonl (97 books), data/out/tashkeela-train.jsonl, the gold.
CPU only -- 0 compute units (COLAB.md 2).
"""
from __future__ import annotations

import collections
import json
import re
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, 'src')
sys.path.insert(0, 'tools')

import eval_harness as EH                       # noqa: E402
from model_arms import load_config              # noqa: E402
from oov_corpus_presence import absent_words    # noqa: E402  (the ONE rule for "absent")

DIAC = re.compile(r"[\u064b-\u0652\u0670\u0640]")
BOOKS = 'data/raw/tashkeela-books.jsonl'
TRAIN_LO, TRAIN_HI = 8, 89                      # the builder's train split
PER_BOOK_CAP = 130_000                          # enough for an 8M-token spread budget
FRONT_HINT = ('http', 'الكتاب :', 'مصدر الكتاب')
BUDGETS = (120_000, 500_000, 2_000_000, 8_000_000)
HEAD_N = 12                                     # lines inspected at the top of each book


def read_train_books() -> dict:
    """{book_i: diacritics-stripped text} for the train split."""
    raw = {}
    with open(BOOKS, encoding='utf-8', errors='replace') as fh:
        for line in fh:
            if not line.strip():
                continue
            rec = json.loads(line)
            i = rec.get('i')
            if i is None or not (TRAIN_LO <= i <= TRAIN_HI):
                continue
            raw[i] = DIAC.sub('', rec['text'])
    return raw


def detect_boilerplate(raw: dict) -> set:
    """Lines that recur near the top of many books are the Shamilah header, not content."""
    c = collections.Counter()
    for txt in raw.values():
        for l in txt.split('\n')[:HEAD_N]:
            l = l.strip()
            if l:
                c[l] += 1
    thr = max(5, len(raw) // 4)
    return {l for l, n in c.items() if n >= thr}


def strip_front(text: str, boiler: set) -> tuple[list, int, int]:
    """Return (tokens, lines_skipped, tokens_removed)."""
    lines = text.split('\n')
    k = 0
    while k < len(lines):
        s = lines[k].strip()
        if not s or s in boiler or any(s.startswith(p) for p in FRONT_HINT):
            k += 1
            continue
        break
    all_toks = text.split()
    body_toks = '\n'.join(lines[k:]).split()
    return body_toks, k, len(all_toks) - len(body_toks)


def evaluate(books: dict, budget: int, strategy: str, want: set) -> dict:
    counts = collections.Counter()
    hit = collections.Counter()
    n, touched = 0, set()
    ids = sorted(books)
    if strategy == 'in-order':                   # what build_training_jsonl.py does today
        for i in ids:
            touched.add(i)
            for t in books[i].split():
                counts[t] += 1
                if t in want:
                    hit[t] += 1
                n += 1
                if n >= budget:
                    break
            if n >= budget:
                break
    else:                                        # 'spread': equal share from every book
        per = max(1, budget // len(ids))
        for i in ids:
            touched.add(i)
            for t in books[i].split()[:per]:
                counts[t] += 1
                if t in want:
                    hit[t] += 1
                n += 1
    vals = sorted(hit.values(), reverse=True)
    return {'n': n, 'distinct': len(counts), 'covered': len(hit),
            'covered_ge2': sum(1 for v in hit.values() if v >= 2),
            'max_count': vals[0] if vals else 0,
            'median_count': vals[len(vals) // 2] if vals else 0,
            'books_touched': len(touched),
            'types_ge2': sum(1 for v in counts.values() if v >= 2)}


def leakage_check(gold) -> None:
    """Do any gold EVALUATION sentences appear in the silver TRAIN split?"""
    train_sents = collections.defaultdict(list)
    with open('data/out/tashkeela-train.jsonl', encoding='utf-8') as fh:
        for line in fh:
            r = json.loads(line)
            train_sents[(r['book'], r['si'])].append(r['form_bare'])
    train_set = {' '.join(v) for v in train_sents.values()}
    gold_seq = set()
    for row in gold:
        toks, _ = EH.parse_gold_context(row.get('context') or '')
        if toks:
            gold_seq.add(' '.join(toks))
    overlap = gold_seq & train_set
    print('leakage check: %d distinct gold sentences vs %d distinct train sentences '
          '-> overlap = %d' % (len(gold_seq), len(train_set), len(overlap)))
    print('  %s' % ('CONFIRMED: no train/eval overlap (books 0-7 vs 8-89)'
                    if not overlap else 'LEAK: %s' % list(overlap)[:3]))


def main() -> int:
    if "-h" in sys.argv[1:] or "--help" in sys.argv[1:]:
        print(__doc__)
        return 0
    want_absent, oov_all = absent_words()
    want = set(want_absent)
    print('=' * 78)
    print('TARGETS: %d OOV gold words, of which %d are absent from the current records'
          % (len(oov_all), len(want)))
    # The baseline is CONFIG-DRIVEN, so it moved when 8ab3a16 repointed paths.silver_train to the
    # spread build: targets were 126 (vs the OLD one-book build) and are 34 (vs Build B) now. The
    # published 2ae/2af numbers belong to the FIRST baseline -- print it so a re-run cannot be
    # silently compared against them.
    print('BASELINE (cfg paths.silver_train) = %s'
          % load_config(smoke=False)['paths']['silver_train'])
    print('  -> report this path with any number from this script; it defines "absent".')
    print('=' * 78)

    t0 = time.time()
    raw = read_train_books()
    boiler = detect_boilerplate(raw)
    print('loaded %d train books (books %d-%d) in %.0fs' % (len(raw), TRAIN_LO, TRAIN_HI,
                                                            time.time() - t0))
    print('boilerplate detected from the data: %d line(s) recurring at the top of >=%d books'
          % (len(boiler), max(5, len(raw) // 4)))
    for b in sorted(boiler)[:3]:
        print('    | %s' % b[:66])

    books, removed_total, raw_total = {}, 0, 0
    for i, txt in raw.items():
        toks, k, removed = strip_front(txt, boiler)
        removed_total += removed
        raw_total += len(txt.split())
        books[i] = ' '.join(toks[:PER_BOOK_CAP])
    total_train = sum(len(v.split()) for v in books.values())
    print('front matter removed: %s tokens of %s (%.2f%%) -- identical boilerplate that every'
          % (f'{removed_total:,}', f'{raw_total:,}', 100 * removed_total / max(raw_total, 1)))
    print('  book opens with, so it is pure waste in a training sample')
    print('train split usable: %s tokens across %d books (capped at %s/book)'
          % (f'{total_train:,}', len(books), f'{PER_BOOK_CAP:,}'))
    print()

    print('=' * 78)
    print('AXIS 1 -- THE SAME TOKEN BUDGET (120,000): in-order vs spread')
    print('=' * 78)
    rows = {}
    for strat in ('in-order', 'spread'):
        r = evaluate(books, 120_000, strat, want)
        rows[strat] = r
        print('  %-8s books=%2d  distinct types=%6d  absent-words covered=%3d (count>=2: %3d)'
              '  max/median=%d/%d'
              % (strat, r['books_touched'], r['distinct'], r['covered'], r['covered_ge2'],
                 r['max_count'], r['median_count']))
    a, b = rows['in-order'], rows['spread']
    print('  -> at the SAME token budget the strategy alone moves coverage %d -> %d (%.0fx)'
          % (a['covered'], b['covered'], b['covered'] / max(a['covered'], 1)))
    print()

    print('=' * 78)
    print('AXIS 2 -- SIZE (spread strategy, equal share from all 82 books)')
    print('=' * 78)
    print('%-13s %-6s %-8s %-9s %-6s %s' % ('budget', 'books', 'types', 'covered', '>=2x',
                                             'max/median'))
    curve = []
    for bud in BUDGETS:
        r = evaluate(books, bud, 'spread', want)
        curve.append((bud, r))
        print('%-13s %-6d %-8d %-9d %-6d %d/%d'
              % (f'{bud:,}', r['books_touched'], r['distinct'], r['covered'],
                 r['covered_ge2'], r['max_count'], r['median_count']))
    full = evaluate(books, total_train, 'spread', want)
    print('%-13s %-6d %-8d %-9d %-6d %d/%d   <- all 82 books'
          % (f'{total_train:,}', full['books_touched'], full['distinct'], full['covered'],
             full['covered_ge2'], full['max_count'], full['median_count']))
    print()

    print('=' * 78)
    leakage_check(EH.load_human_gold('data/annotation/gold-tashkeela-300.jsonl'))
    print()

    print('=' * 78)
    print('AGAINST THE PRE-REGISTERED CRITERIA (fixed before this ran)')
    print('=' * 78)
    print('  "Coverage barely increases -> revisit the sampling strategy"')
    print('     -> at 120k tokens: %d of %d covered in-order, %d spread. Strategy alone is'
          % (a['covered'], len(want), b['covered']))
    print('        worth %.0fx, so the current sample is not merely small: it is ONE book.'
          % (b['covered'] / max(a['covered'], 1)))
    print('  "Coverage increases substantially -> targeted GPU run"')
    print('     -> at the full train split: %d of %d (%.0f%%), median count %d'
          % (full['covered'], len(want), 100 * full['covered'] / len(want),
             full['median_count']))
    print('     -> %d of the %d remain uncovered even then.' % (len(want) - full['covered'],
                                                                 len(want)))
    print('  "Coverage is not accuracy"')
    print('     -> median count climbs %d -> %d -> %d as the budget grows, so the newly'
          % (b['median_count'], curve[1][1]['median_count'], full['median_count']))
    print('        covered words start RARE. Rare types can enter the vocabulary and still')
    print('        be predicted badly; only a trained arm can settle that.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
