"""per_row_split_compare.py — the in-vocab / OOV split at n=3, and does it replicate?

WHY THIS EXISTS
    CHALLENGES 2y ended on a per-row measurement (137 in-vocab / 141 OOV of the 278
    human-gold rows, every arm scoring 0.000 on the OOV half). 2z then measured v13, the
    character-encoder run -- but at n=1, and it said so: "not that the OOV improvement is
    robust: it is 11 of 141 rows for silver-treatment, at one seed."

    v15 is the same architecture as v13 (char encoder, conditioning OFF) at n=3. So v15 is
    the replication test 2z asked for, and this script is the comparison.

    Lives in tools/, not src/: any file under src/ changes the embedded-payload sha256 that
    src/verify_run_code.py checks.

USAGE
    python src/diagnose_gold_checkpoint.py --ckpt <each>.pt > dist/runs/v15/diag/<run>.txt
    python tools/per_row_split_compare.py dist/runs/v15/diag/*.txt
"""
from __future__ import annotations

import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gold_controls_table import parse            # the ONE parser for diag output

# CHALLENGES 2z, transcribed from its recorded table. v13 = n=1, char encoder, conditioning
# OFF, bundle 4bc0737a2fd19f13 @ ba0394e. Same architecture as v15, so this is a like-for-
# like replication test and NOT a cross-architecture comparison.
V13 = {                                          # (in_vocab, oov, whole)
    'silver-treatment': (0.569, 0.099, 0.331),
    'silver-baseline': (0.504, 0.071, 0.284),
    'gold-treatment': (0.372, 0.121, 0.245),
    'gold-baseline': (0.460, 0.241, 0.349),
}
N_IN, N_OOV = 137, 141


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    if not sys.argv[1:] or "-h" in sys.argv[1:] or "--help" in sys.argv[1:]:
        print("Usage: python tools/per_row_split_compare.py <diag-file1.txt> [diag-file2.txt ...]")
        return 0
    files = [Path(p) for p in sys.argv[1:] if Path(p).is_file()]
    if not files:
        print("no valid files found")
        return 1
    rows = [r for p in files for r in parse(p.read_text(encoding='utf-8', errors='replace'))]
    rows = [r for r in rows if not r['run'].startswith('CONTROL')]
    if not rows:
        print('nothing parsed')
        return 1
    ctrl = [r for p in files for r in parse(p.read_text(encoding='utf-8', errors='replace'))
            if r['run'].startswith('CONTROL')]

    print('n rows parsed: %d trained' % len(rows))
    if ctrl:
        c = ctrl[0]
        print('UNTRAINED CONTROL (must be 0 on both halves for the split to mean anything):')
        print('   in_vocab %.3f   oov %.3f   whole %.3f' %
              (c['in_vocab_whole'], c['oov_whole'], c['whole']))
    print()
    print('%-18s %-22s %-22s %-14s' % ('arm', 'in-vocab (n=%d)' % N_IN,
                                       'OOV (n=%d)' % N_OOV, 'whole (n=278)'))
    agg = {}
    for src in ('silver', 'gold'):
        for arm in ('treatment', 'baseline'):
            g = [r for r in rows if r['run'].startswith('%s-%s-' % (src, arm))]
            if not g:
                continue
            key = '%s-%s' % (src, arm)
            vals = {}
            for c in ('in_vocab_whole', 'oov_whole', 'whole'):
                v = [r[c] for r in g]
                vals[c] = (st.fmean(v), st.stdev(v) if len(v) > 1 else 0.0, v)
            agg[key] = vals
            print('%-18s %.3f [%.3f]        %.3f [%.3f]        %.3f [%.3f]'
                  % (key, vals['in_vocab_whole'][0], vals['in_vocab_whole'][1],
                     vals['oov_whole'][0], vals['oov_whole'][1],
                     vals['whole'][0], vals['whole'][1]))

    print()
    print('=== does the per-row picture replicate v13 (n=1 -> n=3)? ===')
    print('%-18s %-9s %-21s %-21s %s' % ('arm', 'cell', 'v13 (n=1)', 'v15 mean [sd]', 'distance'))
    worst = []
    for key, v13 in V13.items():
        if key not in agg:
            continue
        for cell, i in (('in-vocab', 0), ('OOV', 1), ('whole', 2)):
            m, sd, v = agg[key][{'in-vocab': 'in_vocab_whole', 'OOV': 'oov_whole',
                                 'whole': 'whole'}[cell]]
            dist = abs(v13[i] - m) / sd if sd else float('inf')
            worst.append((dist, key, cell))
            print('%-18s %-9s %.3f             %.3f [%.3f]        %.2f sd%s'
                  % (key, cell, v13[i], m, sd, dist, '   <- >2 sd' if dist > 2 else ''))
    print()
    over = [w for w in worst if w[0] > 2]
    print('within 2 sd: %d of %d cells' % (len(worst) - len(over), len(worst)))
    for d, key, cell in sorted(over, reverse=True):
        print('  ABOVE 2 sd: %s %s at %.2f sd' % (key, cell, d))

    print()
    print('=== the two claims this decides ===')
    for src in ('silver', 'gold'):
        t, b = agg.get('%s-treatment' % src), agg.get('%s-baseline' % src)
        if not t:
            continue
        print('  [%s] in-vocab vs OOV, treatment: %.3f vs %.3f  -> %.1fx'
              % (src, t['in_vocab_whole'][0], t['oov_whole'][0],
                 t['in_vocab_whole'][0] / max(t['oov_whole'][0], 1e-9)))
        d_in = t['in_vocab_whole'][0] - b['in_vocab_whole'][0]
        d_oov = t['oov_whole'][0] - b['oov_whole'][0]
        ref_in = max(t['in_vocab_whole'][1], b['in_vocab_whole'][1])
        ref_oov = max(t['oov_whole'][1], b['oov_whole'][1])
        print('  [%s] treat-base in-vocab %+.4f (2sd=%.4f -> %s) | OOV %+.4f '
              '(2sd=%.4f -> %s)'
              % (src, d_in, 2 * ref_in, 'SEP' if abs(d_in) > 2 * ref_in else 'not sep',
                 d_oov, 2 * ref_oov, 'SEP' if abs(d_oov) > 2 * ref_oov else 'not sep'))
        print('  [%s] OOV answered: treat %.1f of %d rows, base %.1f of %d rows'
              % (src, t['oov_whole'][0] * N_OOV, N_OOV, b['oov_whole'][0] * N_OOV, N_OOV))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
