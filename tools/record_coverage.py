"""record_coverage.py — did the record build actually recover the missing words?

WHY THIS EXISTS
    CHALLENGES 2ae measured coverage in the RAW corpus text and flagged that those counts are
    an UPPER BOUND on what the CALIMA pipeline turns into records. This measures the real
    thing, on the built records, and compares builds so the effect of the sampling strategy is
    not confused with anything else.

FOUR LEVELS, KEPT SEPARATE (they are not the same question):
    1. RAW-CORPUS presence  -- is the word anywhere in the training books at all?
    2. RECORD presence      -- did the build turn it into a record (CALIMA may drop it)?
    3. MODEL VOCABULARY     -- does `model_arms.Vocabs` admit it? That rule is min_freq=2
                               **AND max_vocab=20,000 by frequency**, and the cap is the half
                               that is easy to forget.
    4. UNCAPPED             -- what min_freq=2 alone would admit, i.e. what raising the cap buys.
A word can pass 1 and fail 2 (preprocessing), or pass 2 and fail 3 (rare, or crowded out by
the frequency cap).

WHY LEVEL 3 IS COMPUTED WITH THE REAL CLASS
    The first version of this tool applied `min_freq` only and reported 82 of 126 for a build
    whose true vocabulary admitted 56 -- max_vocab never bound before, so the omission was
    invisible until a sample grew past 20,000 qualifying types. It now builds the vocabulary
    with `model_arms.Vocabs` itself, over the SAME two corpora the model uses (PADT train +
    the silver file under test), so the tool cannot drift from the rule it is measuring.

USAGE
    python tools/record_coverage.py OLD=data/out/tashkeela-train.jsonl \
        NEW=data/out/spread-B-2m/tashkeela-train.jsonl
CPU only, zero GPU.

TARGET SET -- AND THE DEFECT THAT MOVED IT (fixed 2026-10-11)
    The target set is "the gold words that are OOV and ABSENT from a BASELINE build". That baseline
    used to be implicit: it came from `cfg['paths']['silver_train']`, via oov_corpus_presence.
    absent_words(). Round-26 prep (8ab3a16) repointed that key to the spread build, so the set
    silently became "the words absent from the build under test" and every `present` count came
    back 0 BY CONSTRUCTION -- a null measurement that still printed a complete, confident table.
    The baseline is now EXPLICIT (`--anchor PATH`, default = the config's silver_train) and the tool
    REFUSES when the anchor is also one of the builds being measured.

    Re-run of 2af's comparison with `--anchor data/out/tashkeela-train.jsonl` reproduces its
    published row exactly: targets 126, present 92, IN VOCAB 56, uncapped 82, cap binds
    (19,998 capped vs 65,684 uncapped). The 2af numbers were right; only the default was not.
"""
from __future__ import annotations

import collections
import json
import math
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, 'src')
sys.path.insert(0, 'tools')

from model_arms import load_config, read_records, Vocabs   # noqa: E402
import eval_harness as EH                                  # noqa: E402

DIAC = re.compile(r"[\u064b-\u0652\u0670\u0640]")
BOOKS = 'data/raw/tashkeela-books.jsonl'
TRAIN_LO, TRAIN_HI = 8, 89


def load_records(path: Path):
    """Return (Counter over form_bare, sentences) — sentences in the model_arms shape."""
    counts = collections.Counter()
    sents = []
    with open(path, encoding='utf-8') as fh:
        cur = {}
        for line in fh:
            if not line.strip():
                continue
            r = json.loads(line)
            counts[r['form_bare']] += 1
            cur.setdefault(r['si'], []).append(r)
    for si, toks in cur.items():
        sents.append((si, toks))
    return counts, sents


def raw_presence(words: list) -> tuple[collections.Counter, int]:
    """Count these words in the raw TRAIN books. Also returns the books' token total, so
    "absent from the sample" can be tested against how many occurrences a sample of that size
    SHOULD have contained. Without that denominator the verdict is meaningless: a word
    occurring 759 times across 66M tokens is not expected to appear in a 118k-token sample."""
    want = set(words)
    out = collections.Counter()
    total = 0
    with open(BOOKS, encoding='utf-8', errors='replace') as fh:
        for line in fh:
            if not line.strip():
                continue
            rec = json.loads(line)
            i = rec.get('i')
            if i is None or not (TRAIN_LO <= i <= TRAIN_HI):
                continue
            toks = DIAC.sub('', rec['text']).split()
            total += len(toks)
            for t in toks:
                t = t.strip('.,:;!?()[]«»"\'')
                if t in want:
                    out[t] += 1
    return out, total


def anchored_targets(padt_recs, anchor_recs, cfg):
    """The target set, with the baseline build given EXPLICITLY instead of read from the config.

    Mirrors oov_corpus_presence.absent_words() exactly (vocabulary and absence counts both over
    PADT-train + anchor records) -- the only difference is that the anchor is a parameter, so a
    config repoint cannot silently redefine what 'absent' means. Returns (oov, absent).
    """
    V = Vocabs(padt_recs + anchor_recs, cfg['data']['min_freq'], cfg['data']['max_vocab'])
    forms = collections.Counter()
    for _, toks in padt_recs + anchor_recs:
        for t in toks:
            forms[t['form_bare']] += 1
    gold = EH.load_human_gold(cfg['paths']['human_gold'])
    oov = []
    for row in gold:
        if not (row.get('root_valid') and row.get('t_root_arabic')):
            continue
        toks, idx = EH.parse_gold_context(row.get('context') or '')
        if not toks:
            continue
        if V.encode(toks[idx]) == 1:
            oov.append(toks[idx])
    return oov, [w for w in oov if forms.get(w, 0) == 0]


def main() -> int:
    if "-h" in sys.argv[1:] or "--help" in sys.argv[1:]:
        print(__doc__)
        return 0
    specs, anchor = [], None
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        a = args[i]
        if a == '--anchor':
            i += 1
            if i >= len(args):
                print('--anchor needs a path')
                return 2
            anchor = Path(args[i])
        elif a.startswith('--anchor='):
            anchor = Path(a.split('=', 1)[1])
        elif '=' in a:
            label, path = a.split('=', 1)
            specs.append((label, Path(path)))
        else:
            print('unrecognised argument: %s' % a)
            return 2
        i += 1
    if not specs:
        print(__doc__)
        return 1

    cfg = load_config(smoke=False)
    min_freq, max_vocab = cfg['data']['min_freq'], cfg['data']['max_vocab']

    # ---- the guard: a target set defined by the build it measures is a null measurement --------
    anchor_given = anchor is not None
    if anchor is None:
        anchor = Path(cfg['paths']['silver_train'])
    clash = [lab for lab, p in specs if p.exists() and anchor.exists()
             and p.resolve() == anchor.resolve()]
    if clash:
        print('REFUSING: the anchor (%s) is ALSO a build under test (%s).' % (anchor, ', '.join(clash)))
        print('The target set would then be "words absent from the build under test", so every')
        print('"present" count is 0 by construction -- a null table that still looks complete.')
        print('This is what 8ab3a16 caused by repointing paths.silver_train to the spread build.')
        print('Pass the baseline explicitly, e.g. --anchor data/out/tashkeela-train.jsonl')
        return 2

    padt = read_records(cfg['paths']['train'], cfg['data']['limit_train'])
    anchor_recs = read_records(anchor, None)
    oov_all, want = anchored_targets(padt, anchor_recs, cfg)
    print('targets: %d OOV gold words absent from the baseline records (of %d OOV)'
          % (len(want), len(oov_all)))
    print('baseline (anchor)     : %s%s'
          % (anchor, '' if anchor_given else "  [from cfg['paths']['silver_train'] -- pass --anchor]"))
    print('vocabulary rule under test: min_freq=%s AND max_vocab=%s (model_arms.Vocabs)'
          % (min_freq, max_vocab))
    print()

    results = {}
    print('%-12s %-11s %-9s %-9s %-9s %-9s %-9s'
          % ('build', 'records', 'types', 'present', 'IN VOCAB', 'uncapped', 'min/med/max'))
    for label, path in specs:
        if not path.exists():
            print('%-12s MISSING: %s' % (label, path))
            continue
        counts, sents = load_records(path)
        V = Vocabs(padt + sents, min_freq, max_vocab)
        Vall = Vocabs(padt + sents, min_freq, 10 ** 9)
        present = {w: counts.get(w, 0) for w in want}
        seen = [w for w, n in present.items() if n >= 1]
        invocab = [w for w in want if V.encode(w) != 1]
        uncapped = [w for w in want if Vall.encode(w) != 1]
        vals = sorted(present[w] for w in seen)
        results[label] = {'counts': counts, 'present': len(seen), 'invocab': len(invocab),
                          'uncapped': len(uncapped), 'vocab': len(V.form) - 2,
                          'vocab_unc': len(Vall.form) - 2, 'vals': vals}
        print('%-12s %-11d %-9d %-9d %-9d %-9d %d/%d/%d'
              % (label, sum(counts.values()), len(counts), len(seen), len(invocab),
                 len(uncapped), vals[0] if vals else 0,
                 vals[len(vals) // 2] if vals else 0, vals[-1] if vals else 0))
        print('%-12s vocab=%d (uncapped %d)  cap binds: %s'
              % ('', len(V.form) - 2, len(Vall.form) - 2,
                 len(Vall.form) - 2 > max_vocab))

    if len(results) >= 2:
        (la, ra), (lb, rb) = list(results.items())[0], list(results.items())[1]
        print()
        print('=== %s -> %s ===' % (la, lb))
        print('  present in records   : %d -> %d' % (ra['present'], rb['present']))
        print('  IN the model vocab   : %d -> %d' % (ra['invocab'], rb['invocab']))
        print('  uncapped min_freq=2  : %d -> %d  (what raising max_vocab buys: %+d)'
              % (ra['uncapped'], rb['uncapped'], rb['uncapped'] - rb['invocab']))
        print('  distinct types       : %d -> %d' % (len(ra['counts']), len(rb['counts'])))

    last_label = list(results)[-1]
    last = results[last_label]
    still = [w for w in want if last['counts'].get(w, 0) == 0]
    print()
    print('=== individual diagnosis of the %d words still absent in %s ==='
          % (len(still), last_label))
    if not still:
        print('  none')
        return 0
    raw, book_tokens = raw_presence(still)
    sample_tokens = sum(last['counts'].values())
    rate = sample_tokens / max(book_tokens, 1)
    print('sample = %s tokens of the %s in the train books (%.4f%% of them)'
          % (f'{sample_tokens:,}', f'{book_tokens:,}', 100 * rate))
    print()
    print('%-16s %-9s %-9s %s' % ('word', 'in books', 'expected', 'verdict'))
    unreachable, explained, watch = [], [], []
    for w in still:
        n = raw.get(w, 0)
        exp = n * rate
        if n == 0:
            verdict = 'ABSENT from the train books -> unreachable by sampling this corpus'
            unreachable.append(w)
        elif exp >= 0.5:
            verdict = ('expected %.1f, P(none)=%.2f -> WATCH LIST, still consistent with '
                       'noise' % (exp, math.exp(-exp)))
            watch.append((w, n, exp))
        else:
            verdict = 'consistent with SIZE: %.2f expected in a sample this small' % exp
            explained.append(w)
        print('%-16s %-9d %-9.2f %s' % (w, n, exp, verdict))
    print()
    print('  unreachable (not in the train books at all)      : %d' % len(unreachable))
    print('  explained by sample size (expected < 0.5)        : %d' % len(explained))
    print('  watch list (expected >= 0.5, but P(none) is high): %d' % len(watch))
    if watch:
        print('    -> %s' % [w for w, _, _ in watch][:10])
        print('    NOT a preprocessing finding: at these means a zero is expected about')
        print('    40-60% of the time. A larger sample is the only way to tell them apart.')
    print()
    print('NOTE: the diagnosis above is about RECORD presence. Words present in the records but')
    print('missing from the model vocabulary are capped out, not a sampling failure -- see the')
    print('IN VOCAB vs uncapped columns.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
