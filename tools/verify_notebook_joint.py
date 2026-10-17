"""verify_notebook_joint.py — check the NOTEBOOK and the CODE IT CALLS, together.

WHY THIS EXISTS
    Every round-26 defect found in review had the same shape: the notebook and the code
    agreed in prose and disagreed in fact.  The build wrote to one directory while the
    config read another; the grid passed a limit that train() applied to BOTH sources; the
    gate hashed a file the runtime never stages; the parity remedy named a tool that was
    not in the payload.  None of those are visible by reading either side alone, and all
    of them are mechanical, so they are checked mechanically here.

CHECKS
    1. payload  : the embedded zip == the working tree (src/, tools/, config/, gold)
    2. parse    : every code cell ast.parses
    3. names    : no cell LOADS a name that no earlier cell, import or builtin defines
    4. signatures: every kwarg the notebook passes to a src/ function exists in that
                  function's real signature (AST-derived, so torch is not needed)
    5. config   : every cfg['a']['b'] the notebook reads exists in config/shared.yaml
    6. paths    : files the notebook hashes exist; the silver dir it BUILDS to == the dir
                  the config READS from
    7. strict   : the preflight gate still contains its hard asserts (not relaxed)
    8. staging  : the SHIPPED staging block is EXECUTED, in both branches, in a temp tree
"""
import ast
import builtins
import gzip
import json
import pathlib
import re
import shutil
import sys
import tempfile
import zipfile

ROOT = pathlib.Path('.').resolve()
# A VARIANT NOTEBOOK CAN BE CHECKED, and it must be, because the rescore ships as a different
# file: `python tools/verify_notebook_joint.py dist/kaggle-rescore-CPU.ipynb`. Defaulting to the
# training notebook is the safe direction -- a typo'd path silently checks the wrong file, so
# the path in use is printed on the first line rather than left implicit.
if "-h" in sys.argv[1:] or "--help" in sys.argv[1:]:
    print(__doc__)
    sys.exit(0)

NOTEBOOK = (pathlib.Path(sys.argv[1]) if len(sys.argv) > 1
            else ROOT / 'notebooks' / 'run-padt.ipynb').resolve()
print('NOTEBOOK UNDER TEST:', NOTEBOOK)
FAIL = []
OK = []


def check(name, cond, detail=''):
    (OK if cond else FAIL).append(name)
    print('  %-4s %s%s' % ('ok' if cond else 'FAIL', name, (' -- ' + detail) if detail else ''))


def cells():
    nb = json.load(open(NOTEBOOK, encoding='utf-8'))
    return [''.join(c['source']) for c in nb['cells'] if c['cell_type'] == 'code']


# ---------------------------------------------------------------- 1. payload
print('\n[1] embedded payload vs working tree')
import base64
src = open(NOTEBOOK, encoding='utf-8').read()
m = re.search(r"EMBED_CHUNKS = \[(.*?)\]", src, re.S)
chunks = re.findall(r"'([^']*)'", m.group(1))
blob = base64.b64decode(''.join(chunks))
zf = zipfile.ZipFile(__import__('io').BytesIO(blob))
names = sorted(zf.namelist())
want = sorted([f'src/{p.name}' for p in (ROOT / 'src').glob('*.py')]
              + [f'tools/{p.name}' for p in (ROOT / 'tools').glob('fit_parity_union.py')]
              + ['config/shared.yaml']
              + [f'data/annotation/{p.name}' for p in (ROOT / 'data/annotation').glob('gold-*')]
              + ['data/silver_root_dict_padt.json'])
check('payload file list == working tree', names == want,
      'only in zip: %s | only on disk: %s' % (sorted(set(names) - set(want))[:3],
                                             sorted(set(want) - set(names))[:3]))
mismatch = [n for n in names if n != 'data/silver_root_dict_padt.json'
            and (ROOT / n).exists() and zf.read(n) != (ROOT / n).read_bytes()]
check('payload bytes == working tree', not mismatch, str(mismatch[:4]))
check('fit_parity_union.py shippable (the parity remedy exists in-cloud)',
      'tools/fit_parity_union.py' in names)

# ---------------------------------------------------------------- 2. parse + 3. names
print('\n[2/3] every cell parses; no cell reads a name nothing defines')
CS = cells()
trees = []
for i, s in enumerate(CS):
    try:
        trees.append(ast.parse(s))
    except SyntaxError as e:
        trees.append(None)
        FAIL.append('cell %d parse' % i)
        print('  FAIL cell %d does not parse: %s' % (i, e))

ALLOW = {'ART', 'CACHE', 'IN_COLAB', 'ON_KAGGLE', 'INPUT', 'device', 'torch',
         'google', 'np', 'pd', '__name__'}


def defined(tree):
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(n.name)
            for a in list(n.args.args) + list(n.args.kwonlyargs):
                out.add(a.arg)
            for a in (n.args.vararg, n.args.kwarg):   # *args and **kw ARE definitions
                if a is not None:
                    out.add(a.arg)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            out.add(n.id)
        elif isinstance(n, ast.Import):
            for a in n.names:
                out.add((a.asname or a.name).split('.')[0])
        elif isinstance(n, ast.ImportFrom):
            for a in n.names:
                out.add(a.asname or a.name)
        elif isinstance(n, (ast.For, ast.comprehension)):
            t = n.target
            for x in ast.walk(t):
                if isinstance(x, ast.Name):
                    out.add(x.id)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            out.add(n.name)
        elif isinstance(n, (ast.With, ast.AsyncWith)):
            for it in n.items:
                if it.optional_vars is not None:
                    for x in ast.walk(it.optional_vars):
                        if isinstance(x, ast.Name):
                            out.add(x.id)
        elif isinstance(n, ast.Global):
            out.update(n.names)
    return out


have = set(dir(builtins)) | ALLOW
badnames = []
for i, (s, t) in enumerate(zip(CS, trees)):
    if t is None:
        continue
    used = {n.id for n in ast.walk(t) if isinstance(n, ast.Name)
            and isinstance(n.ctx, ast.Load)}
    # CELL-LOCAL definitions count. This is a CROSS-CELL check -- the bug class here is a
    # cell reading a name no EARLIER cell provides -- not a statement-order check inside a
    # cell, so counting the cell's own definitions is correct rather than lenient. Without
    # this the check reported every `import gzip, os` and every loop variable as undefined.
    missing = sorted(used - have - defined(t))
    if missing:
        badnames.append((i, missing))
    have |= defined(t)
for i, miss in badnames:
    print('  cell %d reads undefined: %s' % (i, miss))
check('no use-before-def across cells', not badnames,
      '; '.join('cell %d: %s' % (i, m) for i, m in badnames[:4]))

# ---------------------------------------------------------------- 4. signatures
print('\n[4] notebook kwargs vs the real signatures in src/')
sigs = {}
for p in (ROOT / 'src').glob('*.py'):
    for n in ast.walk(ast.parse(p.read_text(encoding='utf-8'))):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = n.args
            names_ = {a.arg for a in list(args.args) + list(args.kwonlyargs) + list(args.posonlyargs)}
            sigs.setdefault(n.name, (names_, args.kwarg is not None))
callsitch = []
for i, (s, t) in enumerate(zip(CS, trees)):
    if t is None:
        continue
    local = defined(t)
    for n in ast.walk(t):
        # LOCAL HELPERS ARE NOT src/ FUNCTIONS. The silver cell defines its own `run(cmd,
        # **kw)`, and matching calls to it against an unrelated `run` in src/ reported a
        # bogus kwarg error.
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id in sigs and n.func.id not in local):
            params, has_kw = sigs[n.func.id]
            for kw in n.keywords:
                if kw.arg and kw.arg not in params and not has_kw:
                    callsitch.append('cell %d: %s(%s=...) not in %s'
                                     % (i, n.func.id, kw.arg, n.func.id))
for c in callsitch:
    print('  ', c)
check('no notebook kwarg is absent from the target signature', not callsitch)
sig = sigs.get('train')
if sig:
    print('  train() accepts train_limit:', 'train_limit' in sig[0])
    check("train() really has the round-26 train_limit parameter", 'train_limit' in sig[0])
    used = any('train_limit' in s for s in CS)
    check('the grid actually passes train_limit', used)

# ---------------------------------------------------------------- 5. config keys
print('\n[5] cfg[...] keys the notebook reads')
import yaml
cfg = yaml.safe_load(open(ROOT / 'config' / 'shared.yaml', encoding='utf-8'))
keypaths = set()
for s in CS:
    for mm in re.finditer(r"cfg\[(['\"])(\w+)\1\]\[(['\"])([\w_]+)\3\]", s):
        keypaths.add((mm.group(2), mm.group(4)))
badkeys = sorted(k for k in keypaths if k[0] not in cfg or k[1] not in cfg[k[0]])
for k in badkeys:
    print('   missing: cfg[%r][%r]' % k)
check('every cfg[a][b] the notebook reads exists', not badkeys,
      '%d key paths checked' % len(keypaths))

# ---------------------------------------------------------------- 6. paths
print('\n[6] paths: what the notebook hashes exists; build dir == read dir')
silver_dir = str(pathlib.PurePosixPath(cfg['paths']['silver_train']).parent)
print('  config reads  :', cfg['paths']['silver_train'])
silver_cell = next(s for s in CS if 'build_training_jsonl' in s)
check('the silver cell DERIVES its directory from the config',
      "os.path.dirname(_cfg['paths']['silver_train'])" in silver_cell)
check('the silver cell passes --outdir with that derived value',
      "'--outdir', SILVER" in silver_cell)
check('build dir == the dir the config reads (derived, not hardcoded)',
      silver_dir == 'data/out/spread-B-2m', silver_dir)
pref = next(s for s in CS if 'PREFLIGHT GATE' in s)
_mm = re.search(r'EXPECT_INPUTS = \{(.*?)\n\}', pref, re.S)
hashed = re.findall(r"'([^']+\.jsonl)'", _mm.group(1))
missing_files = [h for h in hashed if not (ROOT / h).exists()]
check('every file the preflight hashes exists locally', not missing_files, str(missing_files))
print('  preflight hashes %d files (EXPECT_INPUTS entries; my earlier "7" came from the'
      ' regex double-counting two path-assert strings)' % len(hashed))
tried = [s for s in CS if 'MyDrive' in s]
stage_txt = silver_cell
check('staging looks for the records under the config-derived dir',
      "f'{CACHE}/{SILVER}/tashkeela-{_s}.jsonl.gz'" in stage_txt)
check('staging does NOT double the data/out prefix (the defect the executed test caught)',
      'data/out/{SILVER}' not in stage_txt)

# ---------------------------------------------------------------- 7. gate strictness
print('\n[7] the gate is still STRICT (not relaxed into a warning)')
# THE ASSERTIONS SPAN THREE CELLS -- the silver cell verifies content, the preflight cell
# verifies inputs and invariants, the vocab cell verifies parity -- so a check scoped to
# one cell reported "relaxed" for asserts that simply live in a different cell.
ALL = '\n'.join(CS)
STRICT = [
    ('hashes inputs by sha256', 'hashlib.sha256()'),
    ('compares sha256 for EQUALITY, not a warning', 'got_sha == want_sha'),
    ('compares record counts', 'got_rec == want_rec'),
    ('STOPS via SystemExit on a mismatch', 'raise SystemExit'),
    ('asserts the approved silver record count', 'assert _n == 1871205'),
    ('asserts the min_freq invariant', "cfg['data']['min_freq'] == 2"),
    ('asserts the max_vocab invariant', "cfg['data']['max_vocab'] == 20000"),
    ('asserts conditioning is ON', "use_soft_wazan_conditioning']) is True"),
    ('asserts parity within tolerance', 'PARITY FAIL'),
    ('asserts silver train/dev share one directory', 'silver dirs differ'),
]
for label, needle in STRICT:
    hits = [i for i, c in enumerate(CS) if needle in c]
    check('strict: ' + label, bool(hits), 'cells %s' % hits)

# ---------------------------------------------------------------- 8. staging, executed
print('\n[8] EXECUTE the shipped staging block, both branches')
start = silver_cell.index('_cand = {}')
end = silver_cell.index('# THE APPROVED BUILD')
block = silver_cell[start:end]
print('  (%d chars of the shipped cell, taken verbatim)' % len(block))


def run_staging(files_present, label, subdir='data/out/spread-B-2m'):
    tmp = tempfile.mkdtemp()
    art = pathlib.Path(tmp) / 'art'
    cache = pathlib.Path(tmp) / 'cache'
    (art / 'data/out/spread-B-2m').mkdir(parents=True)
    (cache / subdir).mkdir(parents=True, exist_ok=True)
    for f in files_present:
        p = cache / subdir / f
        if f.endswith('.gz'):
            # REAL gzip content. A plain file carrying a .gz NAME fails inside gzip.open, so
            # the test would have been exercising the corrupt-upload path, not staging.
            with gzip.open(p, 'wb') as fh:
                fh.write(b'{"si":0,"ti":0}\n')
        else:
            p.write_bytes(b'{"si":0,"ti":0}')
    calls = []
    env = {
        'os': __import__('os'), 'gzip': __import__('gzip'), 'shutil': shutil,
        'sys': sys, 'json': json,
        'SILVER': 'data/out/spread-B-2m', 'SILVER_DIR': str(art / 'data/out/spread-B-2m'),
        'CACHE': str(cache), 'ART': str(art),
        'run': lambda cmd, **kw: calls.append(cmd),
    }
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(compile(block, '<staging>', 'exec'), env)
    out = buf.getvalue()
    built = [c for c in calls if 'build_training_jsonl' in ' '.join(map(str, c))]
    staged = sorted(p.name for p in (art / 'data/out/spread-B-2m').iterdir())
    print('  %-34s built=%d  staged=%s' % (label, len(built), staged))
    shutil.rmtree(tmp, ignore_errors=True)
    return built, staged, out


built, staged, out = run_staging(
    ['tashkeela-train.jsonl.gz', 'tashkeela-dev.jsonl.gz', 'tashkeela-test.jsonl.gz',
     'build_manifest_tashkeela.json'], 'all four present')
check('all four present -> build is SKIPPED', not built)
check('all four present -> four files land in the config dir',
      staged == sorted(['tashkeela-train.jsonl', 'tashkeela-dev.jsonl',
                        'tashkeela-test.jsonl', 'build_manifest_tashkeela.json']), str(staged))
check('the shipped block needs the manifest too (never a silent 3-of-4 set)',
      'build_manifest_tashkeela.json' in staged)

built2, staged2, _ = run_staging(
    ['tashkeela-train.jsonl.gz', 'tashkeela-dev.jsonl.gz'], 'two of four present')
check('partial upload -> builds rather than mixing staged and built', bool(built2))
check('partial upload -> nothing left half-staged', len(staged2) == 0, str(staged2))
check('the build is told the config-derived --outdir',
      any('--outdir' in c and 'data/out/spread-B-2m' in c for c in built2))

built3, staged3, _ = run_staging(
    ['tashkeela-train.jsonl.gz', 'tashkeela-dev.jsonl.gz', 'tashkeela-test.jsonl.gz',
     'build_manifest_tashkeela.json'], 'flat in arabic-root-tree', subdir='.')
check('a FLAT upload into the root folder is accepted too',
      (not built3) and len(staged3) == 4,
      'built=%d staged=%s' % (len(built3), staged3))

# ---------------------------------------------------------------- verdict
print('\n' + '=' * 72)
print('CHECKS PASSED: %d   FAILED: %d' % (len(OK), len(FAIL)))
if FAIL:
    print('FAILURES:')
    for f in FAIL:
        print('  -', f)
    sys.exit(1)
print('notebook and referenced code agree on names, signatures, config keys,')
print('paths, gate strictness, and the staging behaviour actually executed.')
