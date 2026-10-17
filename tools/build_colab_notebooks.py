"""Regenerate dist/colab-conditioning-{ON,OFF}.ipynb from the current src/, and PROVE
each one embeds its OWN config flag (the flag lives inside the notebook payload, so the
repo's config state must not leak in)."""
from __future__ import annotations

import base64
import json
import pathlib
import re
import subprocess
import sys
import zipfile

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = pathlib.Path(__file__).resolve().parent.parent
CFG = ROOT / 'config' / 'shared.yaml'
NB = ROOT / 'notebooks' / 'run-padt.ipynb'
PY = sys.executable
KEY = 'use_soft_wazan_conditioning'


def set_flag(pat: re.Pattern, orig: str, val: str) -> None:
    t = pat.sub(lambda mm: '%s%s: %s' % (mm.group(1), KEY, val), orig, count=1)
    CFG.write_text(t, encoding='utf-8')


def generate() -> None:
    r = subprocess.run([PY, 'src/make_notebook.py'], cwd=ROOT,
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode != 0:
        print(r.stdout[-3000:])
        print(r.stderr[-3000:])
        raise SystemExit('make_notebook.py FAILED (exit %d)' % r.returncode)
    tail = [line for line in (r.stdout or '').strip().splitlines() if line.strip()]
    print('   make_notebook:', tail[-1] if tail else '(no output)')


def embedded_flag(path: pathlib.Path) -> tuple[str, int, int]:
    """Pull the embedded config/shared.yaml out of the notebook's own payload."""
    nb = json.loads(path.read_text(encoding='utf-8'))
    cell = None
    for c in nb['cells']:
        if c['cell_type'] == 'code' and 'EMBED_CHUNKS' in ''.join(c['source']):
            cell = ''.join(c['source'])
            break
    assert cell, 'no EMBED_CHUNKS cell in %s' % path
    head = cell.partition('BLOB = base64.b64decode')[0]
    ns = {}
    exec(compile(head, '<embed>', 'exec'), ns)
    blob = base64.b64decode(''.join(ns['EMBED_CHUNKS']))
    with zipfile.ZipFile(__import__('io').BytesIO(blob)) as z:
        names = z.namelist()
        cfg = z.read('config/shared.yaml').decode('utf-8')
    return (re.search(r'^\s*%s:\s*(\w+)' % KEY, cfg, re.M).group(1),
            len(names), len(blob))


def main() -> int:
    if "-h" in sys.argv[1:] or "--help" in sys.argv[1:]:
        print(__doc__)
        return 0

    orig = CFG.read_text(encoding='utf-8')
    pat = re.compile(r'^(\s*)%s:\s*(\w+)' % KEY, re.M)
    m = pat.search(orig)
    assert m, 'config has no %s' % KEY
    original_flag = m.group(2)
    print('config as found      : %s: %s  (indent %d)'
          % (KEY, original_flag, len(m.group(1))))

    results = {}
    try:
        for val, tag in (('true', 'ON'), ('false', 'OFF')):
            set_flag(pat, orig, val)
            generate()
            dest = ROOT / 'dist' / ('colab-conditioning-%s.ipynb' % tag)
            dest.parent.mkdir(exist_ok=True)
            dest.write_bytes(NB.read_bytes())
            results[tag] = embedded_flag(dest)
            print('   wrote %s' % dest)
    finally:
        set_flag(pat, orig, original_flag)
        generate()
        print('restored config      : %s: %s' % (KEY, original_flag))

    print()
    print('==== embedded config INSIDE each notebook ====')
    bad = 0
    for tag, (flag, files, size) in results.items():
        want = 'true' if tag == 'ON' else 'false'
        ok = flag == want
        bad += not ok
        print('  colab-conditioning-%-3s -> %s: %-5s  (%d files, %d bytes)  %s'
              % (tag, KEY, flag, files, size, 'OK' if ok else 'MISMATCH!'))
    print()
    print('config after restore  :', CFG.read_text(encoding='utf-8').count(KEY),
          'occurrence(s) of', KEY, '=', pat.search(CFG.read_text(encoding='utf-8')).group(2))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
