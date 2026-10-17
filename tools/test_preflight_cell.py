"""test_preflight_cell.py — does the preflight gate actually gate?

Extracts the preflight cell from the GENERATED notebook and runs it twice against the real
files: once as shipped (must pass on the approved inputs), once with one approved sha256
corrupted (must STOP). A gate that has never been seen to fail is not a gate.
"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, 'src')

if "-h" in sys.argv[1:] or "--help" in sys.argv[1:]:
    print(__doc__)
    sys.exit(0)

from model_arms import (Vocabs, load_config, parity_report,  # noqa: E402
                        read_records)

NB = 'notebooks/run-padt.ipynb'
src = None
for c in json.load(open(NB, encoding='utf-8'))['cells']:
    s = ''.join(c['source'])
    if c['cell_type'] == 'code' and 'PREFLIGHT GATE' in s and 'EXPECT_INPUTS' in s:
        src = s
        break
assert src, 'preflight cell not found in %s' % NB
print('extracted %d lines of preflight from %s' % (len(src.splitlines()), NB))

cfg = load_config(smoke=False)
gold = read_records(cfg['paths']['train'], cfg['data']['limit_train'])
silver = read_records(cfg['paths']['silver_train'], None)
V = Vocabs(gold + silver, cfg['data']['min_freq'], cfg['data']['max_vocab'])
sizes = V.sizes()
base_n, treat_n, gap = parity_report(cfg, sizes, verbose=False)
ns = {'cfg': cfg, 'sizes': sizes, 'base_n': base_n, 'treat_n': treat_n, 'gap': gap}

print()
print('########## TEST 1: as shipped, on the approved inputs ##########')
try:
    exec(compile(src, '<preflight>', 'exec'), dict(ns))
    print()
    print('-> PASS: the gate accepted the approved inputs')
except SystemExit as e:
    print()
    print('-> FAIL: the gate rejected the APPROVED inputs:', e)
    raise SystemExit(1)

print()
print('########## TEST 2: one approved sha256 corrupted -> must STOP ##########')
bad = src.replace('6dfeace847ed24d8e686495285c061b03d949bc88cda6e84481d3fa24dc3b687',
                  '0' * 64)
assert bad != src, 'the silver train hash was not found in the cell'
stopped, msg = False, ''
try:
    exec(compile(bad, '<preflight-bad>', 'exec'), dict(ns))
except SystemExit as e:
    stopped, msg = True, str(e)
print()
print('-> %s: %s' % ('PASS' if stopped else 'FAIL', msg[:160] if stopped
                    else 'gate did NOT stop on a differing dataset hash'))

print()
print('########## TEST 3: max_vocab raised -> the invariant must catch it ##########')
cfg3 = json.loads(json.dumps(cfg))
cfg3['data']['max_vocab'] = 60000
V3 = Vocabs(gold + silver, cfg3['data']['min_freq'], cfg3['data']['max_vocab'])
sizes3 = V3.sizes()
ns3 = {'cfg': cfg3, 'sizes': sizes3, 'base_n': base_n, 'treat_n': treat_n, 'gap': gap}
print('  (raised cap would give surface=%s instead of 20000)' % sizes3['surface'])
stopped3, msg3 = False, ''
try:
    exec(compile(src, '<raised-cap>', 'exec'), ns3)
except (SystemExit, AssertionError) as e:
    stopped3, msg3 = True, str(e)
print('-> %s: %s' % ('PASS - the invariant caught the raised cap' if stopped3
                    else 'FAIL - nothing caught the raised cap',
                    msg3.splitlines()[0][:140] if msg3 else ''))
print()
if stopped and stopped3:
    print('Gate verified: accepts the approved inputs, stops on a corrupted dataset hash,')
    print('and stops on a changed vocabulary invariant.')
else:
    raise SystemExit('GATE NOT VERIFIED')
