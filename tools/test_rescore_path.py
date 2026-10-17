"""test_rescore_path.py — does the RESCORE branch actually load and score a checkpoint?

The round-26 checkpoints live on Drive, so this validates the code path locally: train a
tiny model on the SMOKE config, save it in exactly the notebook's checkpoint format, then
run the same load-and-assert sequence the rescore branch uses, then evaluate. If the branch
is wrong, this fails here instead of after the user spends a CPU session finding out.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, 'src')
import torch
from model_arms import Vocabs, Arm, read_records, resolve_device
from model_arms import load_config
if "-h" in sys.argv[1:] or "--help" in sys.argv[1:]:
    print(__doc__)
    sys.exit(0)

from train import train, evaluate

cfg = load_config(smoke=True)
device = resolve_device(cfg)
print('device:', device, '| smoke limit_train:', cfg['data']['limit_train'])

GOLD_TR = read_records(cfg['paths']['train'], cfg['data']['limit_train'])
GOLD_DV = read_records(cfg['paths']['dev'], cfg['data']['limit_dev'])
SILV_TR = read_records(cfg['paths']['silver_train'], None)
V = Vocabs(GOLD_TR + SILV_TR, cfg['data']['min_freq'], cfg['data']['max_vocab'])
sizes = V.sizes()
print('vocab sizes:', {k: v for k, v in sizes.items() if k in ('surface', 'wazan', 'case')})

arm, seed, src = 'treatment', cfg['seeds'][0], 'gold'
model, _hist, _, _ = train(cfg, arm, seed, device, quiet=True,
                           vocab_sents=V, train_limit=cfg['data']['limit_train'])
print('trained a smoke model for %d steps' % cfg['training']['steps'])

tmp = tempfile.mkdtemp()
ckpt = os.path.join(tmp, arm + '.pt')
torch.save({'model': model.state_dict(), 'cfg': cfg, 'arm': arm, 'seed': seed,
            'source': src, 'sizes': sizes, 'vocab': V.to_dict()}, ckpt)
print('saved checkpoint in the notebook format: %.1f KB' % (os.path.getsize(ckpt) / 1024))

# ---------------- the RESCORE branch, verbatim -------------------------------
print()
print('--- running the rescore load path ---')
assert os.path.exists(ckpt), 'missing checkpoint for ' + arm
blob = torch.load(ckpt, map_location='cpu')
assert blob['cfg'] == cfg, arm + ' was trained under a different config'
assert blob['vocab'] == V.to_dict(), (arm + ': the checkpoint vocabulary is not this run'
                                      ' vocabulary')
model2 = Arm(cfg, sizes, arm).to(device)
model2.load_state_dict(blob['model'])
model2.eval()
print('OK: config matched, vocabulary matched, weights loaded')

# negative controls: the gates must actually fire
import copy
bad = copy.deepcopy(blob)
bad['vocab'] = dict(bad['vocab'])
bad['vocab']['max_vocab'] = 12345
fired = False
try:
    assert bad['vocab'] == V.to_dict(), 'vocab mismatch'
except AssertionError:
    fired = True
print('negative control (tampered vocab): gate fired =', fired)

bad2 = copy.deepcopy(blob)
bad2['cfg'] = dict(bad2['cfg'])
bad2['cfg']['training'] = dict(bad2['cfg']['training'])
bad2['cfg']['training']['steps'] = 999
fired2 = False
try:
    assert bad2['cfg'] == cfg, 'config mismatch'
except AssertionError:
    fired2 = True
print('negative control (tampered config): gate fired =', fired2)

# ---------------- and the reporting path runs on it --------------------------
print()
res = evaluate(model2, GOLD_DV, V, cfg, sizes, device, trie=None)
case = res.get('case') or {}
print('eval ran: case macro_f1=%s  majority_macro_f1=%s  majority_accuracy=%s'
      % (round(case.get('macro_f1', float('nan')), 4),
         round(case.get('majority_macro_f1', float('nan')), 4),
         round(case.get('majority_accuracy', float('nan')), 4)))
n = case.get('n') or 0
if n:
    print('CROSS-CHECK: majority_macro_f1 should equal the closed form, not 1/3:')
    p = case['majority_accuracy']
    print('   closed form = (2p/(p+1))/k = %.4f   reported = %.4f   (old buggy value 0.3333)'
          % ((2 * p / (p + 1)) / 3.0, case['majority_macro_f1']))
    assert abs(case['majority_macro_f1'] - (2 * p / (p + 1)) / 3.0) < 1e-9
    assert abs(case['majority_macro_f1'] - 1 / 3) > 1e-6, 'the 1/k bug is still present!'
print()
print('RESCORE PATH OK: load -> asserts -> evaluate -> corrected baseline reported')
