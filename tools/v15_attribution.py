"""v15 (conditioning OFF) vs v14 (conditioning ON), both n=3.

The attribution question: v14 showed the treatment LOSING root under the better decoder.
v15 is the same grid with the wazan->root conditioning turned OFF - so if the loss is a
property of the CONDITIONING, it should move; if it is a property of the shared encoder or
the vocabulary, it should look the same.

Prints structure first, then the treatment-vs-baseline table per target source, with the
verdict against the seed spread (|d| > 2*max(sd) = SEPARATED).
"""
import json
import statistics as st
import sys

if "-h" in sys.argv[1:] or "--help" in sys.argv[1:]:
    print(__doc__)
    sys.exit(0)

PATHS = {
    'v14 (cond ON)': 'dist/runs/v14/results/results.json',
    'v15 (cond OFF)': 'dist/kaggle-output/results/results.json',
}

DOCS = {}
for tag, p in PATHS.items():
    try:
        DOCS[tag] = json.load(open(p, encoding='utf-8'))
    except FileNotFoundError:
        print('MISSING:', p)
        sys.exit(1)

print('=' * 78)
print('PROVENANCE / PARITY FINGERPRINTS')
print('=' * 78)
FINGER = {'v14 (cond ON)': (13436845, 13436941), 'v15 (cond OFF)': (13436845, 13436941)}
for tag, d in DOCS.items():
    par = d.get('parity', {})
    vs = d.get('vocab_sizes', {})
    print('%-16s bundle %s  runs %2d  seeds %s'
          % (tag, str(d.get('code_bundle_sha'))[:16], len(d.get('results', {})),
             d.get('seeds')))
    print('%-16s parity base %s / treat %s  gap %.2e  char=%s'
          % ('', par.get('baseline'), par.get('treatment'), par.get('gap', -1),
             vs.get('char')))
    print('%-16s config_sha %s' % ('', str(d.get('config_sha256'))[:20]))

# what structure does a run carry?
first = DOCS['v15 (cond OFF)']
tag0 = sorted(first['results'])[0]
print()
print('one run (%s) in_domain_dev keys: %s' % (tag0, sorted(first['results'][tag0].keys())))
print('gold_scored[%s] keys        : %s' % (tag0, sorted(first['gold_scored'][tag0].keys())))

METRICS = ('in_domain_case_macro_f1', 'in_domain_root_acc', 'padt_dev_case_macro_f1',
           'padt_dev_root_acc', 'gold_wazan_raw', 'gold_wazan_norm', 'gold_wazan_slots',
           'gold_root', 'gold_case_macro_f1', 'gold_oov')


def table(doc, label):
    flat = doc['flat']
    print()
    print('-' * 78)
    print('%s  -- treatment vs baseline, mean [sd] over 3 seeds' % label)
    print('-' * 78)
    print('%-26s %-17s %-17s %8s  %s' % ('metric', 'treatment', 'baseline', 'd', 'verdict'))
    out = {}
    for source in ('gold', 'silver'):
        print('  [target = %s]' % source)
        for m in METRICS:
            a = [flat[t][m] for t in flat if flat[t]['source'] == source
                 and flat[t]['arm'] == 'treatment' and flat[t].get(m) is not None]
            b = [flat[t][m] for t in flat if flat[t]['source'] == source
                 and flat[t]['arm'] == 'baseline' and flat[t].get(m) is not None]
            if not a or not b:
                continue
            am, bm = st.fmean(a), st.fmean(b)
            asd = st.stdev(a) if len(a) > 1 else 0.0
            bsd = st.stdev(b) if len(b) > 1 else 0.0
            d = am - bm
            ref = max(asd, bsd)
            v = 'SEPARATED' if abs(d) > 2 * ref else 'not separated'
            print('  %-24s %.3f [%.3f]    %.3f [%.3f]    %+.4f  %s'
                  % (m, am, asd, bm, bsd, d, v))
            out[(source, m)] = (am, bm, d, v, asd, bsd)
    return out


R = {tag: table(d, tag) for tag, d in DOCS.items()}

print()
print('=' * 78)
print('THE ATTRIBUTION QUESTION: does turning conditioning OFF move these?')
print('=' * 78)
KEYS = [('silver', 'in_domain_root_acc'), ('gold', 'in_domain_root_acc'),
        ('silver', 'in_domain_case_macro_f1'), ('gold', 'in_domain_case_macro_f1'),
        ('silver', 'gold_root'), ('gold', 'gold_root'),
        ('silver', 'gold_case_macro_f1'), ('gold', 'gold_case_macro_f1'),
        ('silver', 'padt_dev_root_acc'), ('silver', 'padt_dev_case_macro_f1'),
        ('silver', 'gold_wazan_raw'), ('silver', 'gold_oov')]
print('%-30s %-13s %-13s %s' % ('(target, metric)', 'v14 d (ON)', 'v15 d (OFF)', 'shift'))
for k in KEYS:
    a = R['v14 (cond ON)'].get(k)
    b = R['v15 (cond OFF)'].get(k)
    if not a or not b:
        continue
    print('%-30s %+.4f %-6s %+.4f %-6s %+.4f'
          % ('%s/%s' % (k[0], k[1]), a[2], a[3][:3].upper(), b[2], b[3][:3].upper(),
             b[2] - a[2]))

print()
print('=== ceilings (case macro-F1 0.459, root 0.451) ===')
for tag, d in DOCS.items():
    for source in ('gold', 'silver'):
        c = R[tag].get((source, 'gold_case_macro_f1'))
        r = R[tag].get((source, 'gold_root'))
        if c:
            print('%-16s target=%-7s gold case macro-F1 %.4f  gold root %.4f  %s'
                  % (tag, source, c[0], r[0] if r else float('nan'),
                     'VALID vs ceiling' if source == 'silver' else 'INVALID (trained on the answers)'))
