"""Simulate the generated notebook's cell-2 runtime/paths logic off-Kaggle.

Two bugs this guards:

1. RUNTIME DETECTION. Cell 2 used to decide the runtime with os.path.isdir('/kaggle'), and
   MODERN COLAB MOUNTS ITS SHARED KAGGLE DATASET CACHE AT /kaggle/input (kagglehub
   maintainer, Kaggle/kagglehub#263). So on Colab /kaggle EXISTS, the Kaggle branch ran,
   and the run died with the misdirecting
       AssertionError: no source for src/model_arms.py under /kaggle/input
   while the Colab record staging never executed.

2. RECORD STAGING. The records are the one thing that must be uploaded (corpus-licensed,
   not fetchable in-session). Raw, that is 130 MB; gzipped it is 9.6 MB. Cell 2 accepts
   both, and a TRUNCATED .gz must raise rather than train on half a corpus.

Branch evidence is the first line each branch prints, because both branches assert (and
may abort) BEFORE their trailing 'runtime:' prints:
    Kaggle branch -> "mounted under /kaggle/input:"
    Colab  branch -> the [stub] drive.mount call
"""
import gzip
import io
import json
import os
import shutil
import sys
import tempfile
import types

NB = 'dist/colab-conditioning-ON.ipynb'
nb = json.load(open(NB, encoding='utf-8'))
CELLS = [c for c in nb['cells'] if c['cell_type'] == 'code']

src = None
for c in CELLS:
    s = ''.join(c['source'])
    if 'ON_KAGGLE =' in s and 'drive.mount' in s:
        src = s
        break
assert src, 'cell 2 (paths) not found'

print('===== cell 2 detection block as shipped =====')
keep = False
for ln in src.splitlines():
    if ln.startswith('# WHICH RUNTIME IS THIS?'):
        keep = True
    if keep:
        print('   ', ln)
    if keep and ln.startswith('    INPUT, CACHE'):
        break
print()

TMP = tempfile.mkdtemp(prefix='colabsim-')
FAILED = []
KAGGLE_MARK = 'mounted under /kaggle/input:'
COLAB_MARK = '[stub] drive.mount('

# a payload big enough that gzip's failure modes are exercised, not just the header
PAYLOAD = b''.join(b'{"i": %d, "t": "x"}\n' % i for i in range(20000))


def run_cell2(isdir_map, colab_importable, env, seed):
    """seed: None | 'raw' | 'gz' | 'gz_truncated'."""
    shutil.rmtree(TMP, ignore_errors=True)
    os.makedirs(TMP, exist_ok=True)
    drive = os.path.join(TMP, 'drive_myDrive')
    art_colab = os.path.join(TMP, 'content_art')
    k_in = os.path.join(TMP, 'kaggle_input')
    k_work = os.path.join(TMP, 'kaggle_working')
    if seed:                                   # seed AFTER the wipe
        out = os.path.join(drive, 'data', 'out')
        os.makedirs(out, exist_ok=True)
        for f in ('padt-train.jsonl', 'padt-dev.jsonl'):
            dest = os.path.join(out, f)
            if seed == 'raw':
                open(dest, 'wb').write(PAYLOAD)
            elif seed == 'gz':
                with gzip.open(dest + '.gz', 'wb') as fh:
                    fh.write(PAYLOAD)
            elif seed == 'gz_truncated':
                buf = io.BytesIO()
                with gzip.GzipFile(fileobj=buf, mode='wb') as fh:
                    fh.write(PAYLOAD)
                blob = buf.getvalue()
                with open(dest + '.gz', 'wb') as fh:
                    fh.write(blob[:len(blob) - 40])      # chop the tail: bad stream
            else:
                raise ValueError(seed)

    s = src
    s = s.replace("'/content/drive/MyDrive/arabic-root-tree'", repr(drive))
    s = s.replace("'/content/arabic-root-tree'", repr(art_colab))
    s = s.replace("'/kaggle/input', '/kaggle/working'",
                  repr(k_in) + ', ' + repr(k_work))

    g = types.ModuleType('google')
    m = types.ModuleType('google.colab')
    dr = types.ModuleType('google.colab.drive')
    dr.mount = lambda *a, **k: print('      [stub] drive.mount(%r)' % (a,))
    m.drive = dr
    g.colab = m
    for k in ('google', 'google.colab', 'google.colab.drive'):
        sys.modules.pop(k, None)
    if colab_importable:
        sys.modules['google'] = g
        sys.modules['google.colab'] = m
        sys.modules['google.colab.drive'] = dr
    else:
        sys.modules['google.colab'] = None     # forces ImportError -> Kaggle branch

    for k, v in env.items():
        os.environ[k] = v

    real_isdir = os.path.isdir
    real_exists = os.path.exists
    os.path.isdir = (lambda p: isdir_map.get(p, False if str(p).startswith(('/kaggle', '\\kaggle')) else real_isdir(p)))
    os.path.exists = (lambda p: True if (colab_importable and p == '/var/colab/hostname') else (False if p == '/var/colab/hostname' else real_exists(p)))

    printed = []

    class Tee:
        def write(self, t):
            printed.append(t)

        def flush(self):
            pass

    old_out = sys.stdout
    sys.stdout = Tee()
    try:
        exec(compile(s, '<cell2>', 'exec'), {'__name__': '__main__'})
        ok, err = True, None
    except (AssertionError, SystemExit) as e:
        ok, err = False, str(e)
    finally:
        sys.stdout = old_out
        os.path.isdir = real_isdir
        os.path.exists = real_exists
        for k in env:
            os.environ.pop(k, None)

    return ok, err, ''.join(printed), art_colab


def check(cond, msg):
    print(('      PASS: ' if cond else '      FAIL: ') + msg)
    if not cond:
        FAILED.append(msg)


def dest(art, name):
    return os.path.join(art, 'data', 'out', name)


# ───────────────────────────────── A: Colab, records missing
print('##### A. Colab (no /kaggle), records NOT uploaded -> must fail fast #####')
ok, err, out, art = run_cell2({}, True, {}, None)
print('   ok =', ok, '| err =', (err or '')[:110], '...')
check(not ok, 'refused to run (fail fast)')
check('Colab is missing' in (err or ''), 'message names the missing records')
check('/kaggle/input' not in (err or ''), 'message does NOT mention /kaggle/input')
check(COLAB_MARK in out, 'took the COLAB branch')
print()

# ───────────────────────────────── B: Colab, raw records on Drive
print('##### B. Colab, RAW records on Drive -> staged #####')
ok, err, out, art = run_cell2({}, True, {}, 'raw')
print('   ok =', ok, '| err =', err)
check(ok, 'ran cleanly')
check('runtime: colab' in out, 'reports runtime: colab')
for f in ('padt-train.jsonl', 'padt-dev.jsonl'):
    check(open(dest(art, f), 'rb').read() == PAYLOAD, f'{f} staged byte-exact')
print()

# ───────────────────────────────── C: Colab WITH /kaggle  (the detection regression)
print('##### C. Colab WITH /kaggle and /kaggle/input -> THE REGRESSION #####')
print("      (the user's environment: Colab mounts its shared Kaggle cache")
print('       at /kaggle/input, so /kaggle exists on Colab)')
ok, err, out, art = run_cell2(
    {'/kaggle': True, '/kaggle/input': True, '/kaggle/working': False},
    True, {}, 'raw')
print('   ok =', ok, '| err =', err)
check(COLAB_MARK in out, 'took the COLAB branch, not the Kaggle one')
check(KAGGLE_MARK not in out, 'never entered the Kaggle branch')
check(not (err and 'no source for' in err),
      'no "no source for ... under /kaggle/input" (the reported failure)')
check(os.path.exists(dest(art, 'padt-train.jsonl')), 'Colab staging actually RAN')
check('google.colab=True' in out, 'detection self-reported: google.colab=True')
print()

# ───────────────────────────────── D: real Kaggle
print('##### D. Kaggle (KAGGLE_KERNEL_RUN_TYPE set) -> must still pick Kaggle #####')
ok, err, out, art = run_cell2(
    {'/kaggle': True, '/kaggle/input': True, '/kaggle/working': True},
    False, {'KAGGLE_KERNEL_RUN_TYPE': 'Interactive'}, 'raw')
print('   ok =', ok, '| err =', (err or '')[:110], '...')
check(KAGGLE_MARK in out, 'took the KAGGLE branch')
check(COLAB_MARK not in out, 'did NOT take the Colab branch')
check(not ok and 'no source for' in (err or ''),
      'correctly complains its Kaggle dataset is not attached')
print()

# ───────────────────────────────── E: Colab, .gz only
print('##### E. Colab, ONLY .gz on Drive -> staged + gunzipped #####')
ok, err, out, art = run_cell2({}, True, {}, 'gz')
print('   ok =', ok, '| err =', err)
check(ok, 'ran cleanly')
for f in ('padt-train.jsonl', 'padt-dev.jsonl'):
    p = dest(art, f)
    check(os.path.exists(p), f'{f} created from .gz')
    check(open(p, 'rb').read() == PAYLOAD, f'{f} gunzipped byte-exact')
check('gunzipped' in out, 'reported the gunzip')
print()

# ───────────────────────────────── F: truncated .gz must NOT train
print('##### F. Colab, TRUNCATED .gz -> must raise, must not leave a partial #####')
ok, err, out, art = run_cell2({}, True, {}, 'gz_truncated')
print('   ok =', ok, '| err =', (err or '')[:130])
check(not ok, 'refused to continue')
check('corrupt/truncated' in (err or ''), 'error says corrupt/truncated')
check('re-upload' in (err or ''), 'error says to re-upload')
check(not os.path.exists(dest(art, 'padt-train.jsonl')),
      'no partial padt-train.jsonl left behind (a re-run re-stages)')
print()

print('=' * 62)
print('FAILURES:', len(FAILED))
for f in FAILED:
    print('   -', f)
sys.exit(1 if FAILED else 0)
