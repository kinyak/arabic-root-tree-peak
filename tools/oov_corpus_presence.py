"""oov_corpus_presence.py — do the OOV words exist in the CORPUS, or only outside it?

WHY THIS EXISTS
    tools/oov_lever_check.py measured that 126 of the 141 OOV gold target words have ZERO
    occurrences in the TRAINING RECORDS. But the training records are a ~0.75% sample of
    Tashkeela (120k records out of a 66.5M-token corpus, per 2y caveat 1), so "absent from
    the records" is not the same as "absent from the corpus". The two cases need different
    levers:

      present in the corpus, absent from the records -> DATA SCALE. A bigger sample admits
          them; no vocabulary setting can, because the vocab is built FROM the records.
      absent from the corpus entirely                -> neither. Needs another corpus, or
          decoding that does not require a lookup entry (lexicon/trie over a bigger
          morphology, or the char encoder -- already in both arms).

    Reads the raw corpus as TEXT with diacritics stripped by the SAME class
    build_training_jsonl.py uses ([\\u064b-\\u0652\\u0670\\u0640]), so a hit here means the
    word would land in a bigger sample of the same corpus. CPU only, zero GPU.
"""
from __future__ import annotations

import collections
import re
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, 'src')

from model_arms import load_config, read_records, Vocabs   # noqa: E402
import eval_harness as EH                                  # noqa: E402

DIAC = re.compile(r"[\u064b-\u0652\u0670\u0640]")
RAW = 'data/raw/tashkeela-books.jsonl'


def absent_words():
    """DEPRECATED as a shared rule -- the baseline is CONFIG-DRIVEN, which makes it unsafe.

    This reads the "original records" build from `cfg['paths']['silver_train']`. Round-26 prep
    (8ab3a16) repointed that key to the spread build, so this function now returns "the words absent
    from the spread build" and any caller that then measures the spread build against them gets
    present=0 BY CONSTRUCTION. Two callers exist: tools/sample_coverage_study.py (still exposed --
    pass an explicit baseline there before trusting a re-run) and tools/record_coverage.py, which now
    takes an explicit `--anchor` and refuses when the anchor is a build under test.

    Kept for reference and for the RAW-CORPUS script's own use. Prefer `anchored_targets()` in
    tools/record_coverage.py for any new coverage measurement.
    """
    cfg = load_config(smoke=False)
    gold_recs = read_records(cfg['paths']['train'], cfg['data']['limit_train'])
    silv_recs = read_records(cfg['paths']['silver_train'], None)
    V = Vocabs(gold_recs + silv_recs, cfg['data']['min_freq'], cfg['data']['max_vocab'])
    forms = collections.Counter()
    for _, toks in gold_recs + silv_recs:
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
        w = toks[idx]
        if V.encode(w) == 1:
            oov.append(w)
    return [w for w in oov if forms.get(w, 0) == 0], oov


def main() -> int:
    if "-h" in sys.argv[1:] or "--help" in sys.argv[1:]:
        print(__doc__)
        return 0
    zero, oov = absent_words()
    print('OOV target words total          : %d' % len(oov))
    print('  of which ABSENT from the records: %d  <- what this script looks for' % len(zero))
    want = set(zero)
    hits = collections.Counter()
    seen_tokens = 0
    t0 = time.time()

    with open(RAW, encoding='utf-8', errors='replace') as fh:
        tail = ''
        while True:
            chunk = fh.read(1 << 22)          # 4M chars
            if not chunk:
                break
            text = DIAC.sub('', tail + chunk)
            cut = text.rfind(' ')
            if cut == -1:
                tail = text
                continue
            tail = text[cut:]
            toks = text[:cut].split()
            seen_tokens += len(toks)
            for t in toks:
                if t in want:
                    hits[t] += 1
    if tail:
        for t in DIAC.sub('', tail).split():
            if t in want:
                hits[t] += 1

    print('corpus scanned: %s  (%.1f GB, %d whitespace tokens, %.0fs)'
          % (RAW, __import__('os').path.getsize(RAW) / 1e9, seen_tokens, time.time() - t0))
    print()
    found = sorted(hits)
    missing = [w for w in zero if w not in hits]
    print('=== RESULT ===')
    print('  of the %d words absent from the TRAINING RECORDS:' % len(zero))
    print('    present in the CORPUS (a bigger sample would admit them): %3d  (%.0f%%)'
          % (len(found), 100 * len(found) / max(len(zero), 1)))
    print('    absent from the corpus ENTIRELY                        : %3d  (%.0f%%)'
          % (len(missing), 100 * len(missing) / max(len(zero), 1)))
    print()
    print('  a sample of corpus-present words with their corpus counts:')
    for w in sorted(found, key=lambda x: -hits[x])[:12]:
        print('     %-14s %d' % (w, hits[w]))
    print('  a sample of corpus-absent words:')
    print('    ', missing[:15])
    print()
    print('=== the decision ===')
    if len(found) / max(len(zero), 1) > 0.5:
        print('  MOST of them ARE in the corpus, so the lever is DATA SCALE, not vocabulary.')
        print('  The training records are a ~0.75% sample of Tashkeela (120k records out of')
        print('  73M whitespace tokens here), and a bigger sample admits them. Vocabulary')
        print('  settings cannot: the vocab is built FROM the records, so no min_freq or')
        print('  max_vocab value can admit a word with no occurrences in them.')
        print('  This is CPU-only work - 0 compute units, per COLAB.md 2.')
    else:
        print('  MOST are absent from this corpus, so neither a bigger sample NOR a bigger')
        print('  vocabulary fixes them: they need another corpus or lookup-free decoding.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
