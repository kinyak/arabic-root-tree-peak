"""oov_lever_check.py — is a BIGGER VOCABULARY the right lever for the 141 OOV rows?

WHY THIS EXISTS
    CHALLENGES 2ac ends by pointing at "vocabulary scale" as the next lever, on the strength
    of 2z's per-row OOV cliff -- which 2ad has now replicated at n=3. But that is a pointer,
    not a measurement. Vocab construction is:

        for f, c in forms.most_common():
            if len(self.form) >= max_vocab: break      # 20,000
            if c >= min_freq: self.form[f] = ...       # 2

    and the surface vocab comes out at 13,143, i.e. the max_vocab break NEVER fires. So
    max_vocab is not binding and the ONLY vocab-side lever is min_freq. Which means the
    question "would a bigger vocabulary help?" reduces to: how many of the OOV gold target
    words are in the training records AT ALL, and how many are hapaxes that min_freq=2 cut?

    count == 0  -> no vocabulary setting can recover it; the lever is DATA SCALE or a
                   char-level decoder, not vocab.
    count == 1  -> min_freq=1 would recover it. Cheap, and measurable in advance.

    Lives in tools/, not src/: any file under src/ changes the payload sha that
    src/verify_run_code.py checks. CPU only, zero GPU.
"""
from __future__ import annotations

import collections
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, 'src')

from model_arms import load_config, read_records, Vocabs   # noqa: E402
import eval_harness as EH                                  # noqa: E402


def main() -> int:
    if "-h" in sys.argv[1:] or "--help" in sys.argv[1:]:
        print(__doc__)
        return 0
    cfg = load_config(smoke=False)
    gold_recs = read_records(cfg['paths']['train'], cfg['data']['limit_train'])
    silv_recs = read_records(cfg['paths']['silver_train'], None)
    n_gold = sum(len(t) for _, t in gold_recs)
    n_silv = sum(len(t) for _, t in silv_recs)
    print('training records: gold(train) %d tokens, silver(train) %d tokens' % (n_gold, n_silv))

    min_freq = cfg['data']['min_freq']
    max_vocab = cfg['data']['max_vocab']
    V = Vocabs(gold_recs + silv_recs, min_freq, max_vocab)
    sizes = V.sizes()
    print('vocab sizes: %s' % sizes)
    print('config cutoff: min_freq=%s  max_vocab=%s' % (min_freq, max_vocab))

    forms = collections.Counter()
    for _, toks in gold_recs + silv_recs:
        for t in toks:
            forms[t['form_bare']] += 1

    n_types = len(forms)
    n_ge2 = sum(1 for c in forms.values() if c >= 2)
    print()
    print('distinct surface types in those records : %d' % n_types)
    print('types with count >= %s (kept by min_freq): %d' % (min_freq, n_ge2))
    print('  -> surface vocab built = %d  (max_vocab=%d never binds: %s)'
          % (sizes['surface'], max_vocab, 'CONFIRMED' if sizes['surface'] < max_vocab else 'binds!'))
    print('  -> types lost to min_freq = %d' % (n_types - n_ge2))

    gold = EH.load_human_gold(cfg['paths']['human_gold'])
    rows = []
    for row in gold:
        if not (row.get('root_valid') and row.get('t_root_arabic')):
            continue
        toks, idx = EH.parse_gold_context(row.get('context') or '')
        if not toks:
            continue
        w = toks[idx]
        rows.append((w, V.encode(w) != 1, forms.get(w, 0)))

    inv = [r for r in rows if r[1]]
    oov = [r for r in rows if not r[1]]
    print()
    print('THE SPLIT (replicating src/diagnose_gold_checkpoint.py):')
    print('  in_vocab %d / oov %d   %s'
          % (len(inv), len(oov),
             '(matches the 137/141 in 2y/2z/2ad)' if (len(inv), len(oov)) == (137, 141)
             else '<-- DOES NOT MATCH 137/141, check the rule'))
    print('  in_vocab words with count>=2: %d of %d'
          % (sum(1 for r in inv if r[2] >= 2), len(inv)))

    zero = [r for r in oov if r[2] == 0]
    one = [r for r in oov if r[2] == 1]
    many = [r for r in oov if r[2] >= 2]
    tot = max(len(oov), 1)
    print()
    print('THE 141 OOV WORDS, by their count in the training records:')
    print('  count == 0  ABSENT from the records : %3d  (%4.1f%%)  no vocab setting can help'
          % (len(zero), 100 * len(zero) / tot))
    print('  count == 1  hapax, cut by min_freq : %3d  (%4.1f%%)  min_freq=1 WOULD recover these'
          % (len(one), 100 * len(one) / tot))
    print('  count >= 2  should be in vocab     : %3d  (%4.1f%%)  %s'
          % (len(many), 100 * len(many) / tot,
             'BUG' if many else 'none - consistent'))
    print()
    print('  top-15 ABSENT :', [r[0] for r in zero[:15]])
    print('  top-15 HAPAX  :', [r[0] for r in one[:15]])

    print()
    print('=== the decision ===')
    if not oov:
        print('  no OOV rows')
    elif len(zero) / tot > 0.5:
        print('  %.0f%% of the OOV rows are words the training records NEVER contain.'
              % (100 * len(zero) / tot))
        print('  So "scale the vocabulary" is the WRONG lever for them: there is no')
        print('  min_freq/max_vocab setting that admits a word with no occurrences.')
        print('  The lever is DATA SCALE (more of the corpus) or decoding that does not')
        print('  need a lookup entry at all (the char encoder is already in both arms;')
        print('  what is missing is a lexicon/trie that covers these forms).')
        if len(one):
            print('  min_freq=1 would additionally recover the %d hapax rows: worth %.1f pp'
                  ' of the OOV half.' % (len(one), 100 * len(one) / tot))
    else:
        print('  most OOV rows are hapaxes -> min_freq=1 is the cheap lever')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
