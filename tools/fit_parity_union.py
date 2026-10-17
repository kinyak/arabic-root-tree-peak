"""fit_parity_union.py — fit `treatment_tower_hidden` against the UNION vocabulary.

WHY THIS EXISTS (and why `model_arms.py --fit-parity` is not enough)
    The notebook asserts parity on the UNION vocabulary:

        V = Vocabs(GOLD_TR + SILV_TR, min_freq, max_vocab)      # both target sources

    because that is the ONE vocabulary both arms actually train on. But
    `model_arms.py --fit-parity` builds its sizes from `paths.train` (PADT) ALONE:

        sents = read_records(ROOT / cfg["paths"]["train"], cfg["data"]["limit_train"])
        v = Vocabs(sents, ...)

    so it fits a DIFFERENT pair of arms than the ones the run asserts. That went unnoticed
    while the two vocabularies happened to be close; with the round-26 spread sample the
    union vocabulary is 19,998 types and the fit must be done against it or the notebook's
    assertion will fail on a pair nobody fitted.

    `max_vocab` also BINDS for the first time here, so the pair moves by much more than the
    ~0.7% the config's comment records for earlier rounds.

Lives in tools/, not src/: any file under src/ changes the payload sha256 that
src/verify_run_code.py checks. CPU only, zero GPU.
"""
from __future__ import annotations

import copy
import sys

sys.path.insert(0, 'src')

from model_arms import (ROOT, Vocabs, fit_treatment_tower,  # noqa: E402
                        load_config, parity_report, read_records)


def main() -> int:
    if "-h" in sys.argv[1:] or "--help" in sys.argv[1:]:
        print(__doc__)
        return 0
    cfg = load_config(smoke=False)
    gold = read_records(ROOT / cfg['paths']['train'], cfg['data']['limit_train'])
    silver = read_records(ROOT / cfg['paths']['silver_train'], None)
    n_g = sum(len(t) for _, t in gold)
    n_s = sum(len(t) for _, t in silver)
    tol = cfg['parity']['tolerance']
    print('=' * 78)
    print('PARITY FIT AGAINST THE UNION VOCABULARY (the one the notebook asserts on)')
    print('=' * 78)
    print('  gold(train)   : %s tokens  %s' % (f'{n_g:,}', cfg['paths']['train']))
    print('  silver(train) : %s tokens  %s' % (f'{n_s:,}', cfg['paths']['silver_train']))
    V = Vocabs(gold + silver, cfg['data']['min_freq'], cfg['data']['max_vocab'])
    sizes = V.sizes()
    print('  union vocab   : %s' % sizes)
    print('  cutoff        : min_freq=%s  max_vocab=%s   (cap binds: %s)'
          % (cfg['data']['min_freq'], cfg['data']['max_vocab'],
             sizes['surface'] >= cfg['data']['max_vocab'] - 1))
    print('  tolerance     : %.2f%%' % (tol * 100))
    print()
    print('  config as it stands: treatment_tower_hidden = %s'
          % cfg['model']['treatment_tower_hidden'])
    print('  BEFORE fitting:')
    base0, treat0, gap0 = parity_report(cfg, sizes)
    print('    verdict: %s (gap %.4f%%)' % ('OK' if gap0 <= tol else 'FAIL', gap0 * 100))

    hidden, g = fit_treatment_tower(cfg, sizes, lo=8, hi=20_000)
    print()
    print('  fitted treatment_tower_hidden = %d  (coarse+refined gap %.4f%%)'
          % (hidden, g * 100))
    c2 = copy.deepcopy(cfg)
    c2['model']['treatment_tower_hidden'] = hidden
    print()
    print('  AFTER fitting:')
    base, treat, gap = parity_report(c2, sizes)
    print('    verdict: %s (gap %.4f%% <= %.2f%%)'
          % ('OK' if gap <= tol else 'FAIL', gap * 100, tol * 100))
    print()
    print('  -> write into config/shared.yaml:')
    print('     treatment_tower_hidden: %d' % hidden)
    print()
    print('  PARITY FINGERPRINT for this run (prints in the kernel log; it is how a run is')
    print('  identified as THIS architecture, cf. v14 13,087,021/13,087,117 and v15')
    print('  13,436,845/13,436,941):')
    print('     %s / %s' % (f'{base:,}', f'{treat:,}'))
    if gap > tol:
        print()
        print('  *** FAILED TO CLOSE THE GAP within the search range; do not run. ***')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
