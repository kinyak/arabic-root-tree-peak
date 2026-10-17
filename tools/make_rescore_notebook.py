"""make_rescore_notebook.py — emit dist/colab-rescore-CPU.ipynb (reporting only, no GPU).

Same notebook, one literal flipped: RESCORE_ONLY = True. Same cells, same reporting path, so
the rescored artifact cannot drift from the training artifact's definitions -- it IS the
training artifact's reporting code.
"""
import json

SRC = 'dist/colab-conditioning-ON.ipynb'
OUT = 'dist/colab-rescore-CPU.ipynb'

nb = json.load(open(SRC, encoding='utf-8'))
n = 0
for c in nb['cells']:
    if c.get('cell_type') != 'code':
        continue
    for i, line in enumerate(c['source']):
        if line.strip() == 'RESCORE_ONLY = False':
            c['source'][i] = line.replace('RESCORE_ONLY = False', 'RESCORE_ONLY = True')
            n += 1
assert n == 1, 'expected exactly ONE RESCORE_ONLY literal in the notebook, found %d' % n

nb.setdefault('metadata', {})['hermes'] = {'mode': 'rescore-cpu', 'gpu_required': False}
with open(OUT, 'w', encoding='utf-8') as fh:
    json.dump(nb, fh, indent=1)
print('wrote %s  (RESCORE_ONLY=True, %d substitution)' % (OUT, n))
print('it re-scores the 12 checkpoints from Drive and rewrites results.json. No GPU.')
