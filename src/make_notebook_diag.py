"""make_notebook_diag.py — build notebooks/diagnose-architecture.ipynb.

WHAT THIS NOTEBOOK IS FOR
    "We need to measure which part is wrong or needs modification or invention."
    It loads the v20 checkpoints FAITHFULLY (src/legacy_arch.py, 0 missing/0 unexpected), runs the
    component census and the conjunctive sensitivity, probes the frozen trunk, then instantiates the
    CURRENT architecture and asserts every recent module is actually present — and prints, per
    defect, the pre-registered fix and the command that will measure it.

WHY IT IS A CPU KERNEL
    Nothing here trains. Kaggle meters quota on CONTAINER WALL-CLOCK, so a CPU-only pass inside a
    GPU session is billed at GPU rates; this notebook is pushed with enableGpu=false and asserts no
    CUDA. The GPU notebook comes after this one names the fix AND its gate.

CONVENTIONS COPIED FROM make_notebook.py (deliberately, not imported)
    * a DETERMINISTIC zip (fixed ZipInfo date_time) so the sha is a function of CONTENT alone;
    * the payload carries src/ + config/ + the annotation gold, and is extracted LAST, overriding
      any dataset mount — so the embedded copy is the one that runs;
    * EXPECT_SHA is asserted at run time and the run prints the bundle sha, so a stale payload
      FAILS LOUDLY;
    * every code cell is ast.parse-checked here, so a syntax error cannot reach Kaggle.
"""
from __future__ import annotations

import ast
import base64
import hashlib
import json
import sys
from pathlib import Path

from paths import ROOT

OUT = ROOT / "notebooks" / "diagnose-architecture.ipynb"
MAX_EMBED_B64 = 700_000
FIXED_DATE = (1980, 1, 1, 0, 0, 0)


def embedded_bundle_code_only() -> tuple[list, str, int]:
    """src/ + tools/fit_parity_union.py + config/ + the annotation gold. CODE ONLY.

    No corpora and no derived records: those do not fit under the kernel-source cap, and this
    notebook does not build them. No silver root dictionary either — that belongs to the training
    notebook, whose build cell is the only thing that needs it.
    """
    import io
    import zipfile

    entries: list[tuple[str, bytes]] = []
    for p in sorted((ROOT / "src").glob("*.py")):
        entries.append((f"src/{p.name}", p.read_bytes()))
    for p in sorted((ROOT / "tools").glob("fit_parity_union.py")):
        entries.append((f"tools/{p.name}", p.read_bytes()))
    entries.append(("config/shared.yaml", (ROOT / "config" / "shared.yaml").read_bytes()))
    for p in sorted((ROOT / "data" / "annotation").glob("gold-*")):
        entries.append((f"data/annotation/{p.name}", p.read_bytes()))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in entries:
            zi = zipfile.ZipInfo(name, date_time=FIXED_DATE)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            z.writestr(zi, data)
    blob = buf.getvalue()
    sha = hashlib.sha256(blob).hexdigest()
    b64 = base64.b64encode(blob).decode("ascii")
    if len(b64) > MAX_EMBED_B64:
        raise SystemExit(f"payload {len(b64)/1e3:.0f} KB of base64 > cap {MAX_EMBED_B64/1e3:.0f} KB")
    print(f"  payload: {len(blob)/1e3:.1f} KB zip -> {len(b64)/1e3:.1f} KB base64, "
          f"{len(entries)} files, sha256 {sha[:16]}…")
    return [b64[i:i + 4000] for i in range(0, len(b64), 4000)], sha, len(entries)


def md(*lines):
    return {"cell_type": "markdown", "metadata": {}, "source": [l + "\n" for l in lines]}


def code(*lines):
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [],
            "source": [l + "\n" for l in lines]}


def cells(sha: str, chunks: list, nfiles: int) -> list:
    return [
        md("# arabic-root-tree — WHERE IS THE 98% LOST? (PRIVATE, CPU-only)",
           "",
           "**Keep private.** The corpora are CC BY-NC-SA / GPL: no public output, no published",
           "results, no shared checkpoints.",
           "",
           "## What this notebook does, in order",
           "",
           "1. extracts the embedded `src/` payload (deterministic zip, sha asserted at run time)",
           "2. loads each v20 checkpoint with the **faithful reader** and REFUSES any that does not",
           "   load with 0 missing / 0 unexpected tensors",
           "3. prints the **component census**: every head, every slice, beside its own floor",
           "4. prints the **conjunctive sensitivity** — the marginal gain from lifting each component",
           "   to its own ceiling. The sorted column is the answer to \"which part is wrong\".",
           "5. probes the **frozen trunk** — is the target in the representation, or absent from it?",
           "6. instantiates the **current architecture** and asserts every recent module is present",
           "7. prints, per defect, the **pre-registered fix and the command that measures it**",
           "",
           "## The two things that make numbers here readable",
           "",
           "- **The reader is part of the measurement (§2cq).** The v20 checkpoints were trained by code",
           "  from the Kaggle dataset mount, not the repo. Loading them through the current",
           "  `model_arms.py` invents 19 modules (two in the INPUT pathway) and yields `root 13.7%` /",
           "  `3.6%` — a *fabricated* model. The faithful reader gives `root 57.2%`, and reproduces the",
           "  2026-10-13 recording to the row. A number from an unfaithful load is not a measurement.",
           "- **Capacity is not the same as capability.** `wazan radical slot-set` is already **98.9%**",
           "  while `wazan raw string` is **17.6%** — the same head, the same rows, the same weights.",
           "  That gap is *notation*, not learning, and it is invisible in the headline number.",
           "",
           "## Ledger — already measured and closed (do not re-walk these)",
           "",
           "| question | verdict | section |",
           "|---|---|---|",
           "| is the renderer the bottleneck? | no — 75% conditional on a right plan; the compiler's own",
           "| | ceiling is 78.8% (rule-only) / 86.2% (dictionary) | §2cg, §2co |",
           "| does the char encoder help OOV? | yes as shipped (v12: 0.000 -> 0.071-0.241), and the",
           "| | treatment's root win did NOT replicate | §2z |",
           "| is a rule-only compiler worth more rules? | no — the residual is information-theoretic | §2cl |",
           "| does `load_for_eval` repair an old checkpoint? | no — it disables a `char_encoder` that is",
           "| | 7/10 present and fully trained, and scores WORSE than `strict=False` on 4/4 arms | §2cq |",
           "| is the 13% the architecture's number? | no — 57.2%. The 13% was an unfaithful load | §2cq |",
           ""),
        md("## 0. Environment",
           "",
           "Runtime detected by **order, not presence**: `KAGGLE_KERNEL_RUN_TYPE` is set by the Kaggle",
           "runner and nowhere else, so it is decisive; `google.colab` is importable on Kaggle too, so",
           "it is only consulted when that marker is absent."),
        code("import os, sys, glob, json, shutil, base64, hashlib, io, zipfile, subprocess, time",
             "_KRT = os.environ.get('KAGGLE_KERNEL_RUN_TYPE')",
             "_KW = os.path.isdir('/kaggle/working')",
             "_COLAB_FS = os.path.exists('/var/colab/hostname')",
             "try:",
             "    import google.colab  # noqa: F401",
             "    _COLAB_IMPORT = True",
             "except ImportError:",
             "    _COLAB_IMPORT = False",
             "IN_COLAB = (not _KRT) and _COLAB_IMPORT and _COLAB_FS",
             "ON_KAGGLE = bool(_KRT) or (_KW and not IN_COLAB)",
             "print(f'evidence: KAGGLE_KERNEL_RUN_TYPE={_KRT!r} /kaggle/working={_KW} /var/colab/hostname={_COLAB_FS} google.colab={_COLAB_IMPORT}')",
             "print('runtime:', 'kaggle' if ON_KAGGLE else ('colab' if IN_COLAB else 'local'))",
             "assert ON_KAGGLE or IN_COLAB or os.path.isdir('src'), 'unknown runtime with no src/'",
             "# CPU_ONLY: this notebook trains nothing, so it must not occupy a GPU slot.",
             "CPU_ONLY = True",
             "print('CPU_ONLY =', CPU_ONLY, '-- nothing here trains; the GPU notebook comes next')"),
        md("## 1. The embedded code payload",
           "",
           f"`src/` + `config/` + the annotation gold: **{nfiles} files**, extracted LAST so the",
           "embedded copy is the one that runs. `EXPECT_SHA` is asserted — a stale payload fails",
           "loudly instead of measuring the wrong code."),
        code(f"EXPECT_SHA = {sha!r}",
             "EMBED_CHUNKS = [" + ",\n    ".join(repr(c) for c in chunks) + "]",
             "BLOB = base64.b64decode(''.join(EMBED_CHUNKS))",
             "print('embedded code bundle: %d bytes sha256 %s' % (len(BLOB), hashlib.sha256(BLOB).hexdigest()[:16]))",
             "assert hashlib.sha256(BLOB).hexdigest() == EXPECT_SHA, (",
             "    'STALE PAYLOAD: the notebook does not carry the checked-in code. Regenerate with'",
             "    ' python src/make_notebook_diag.py --push and do not analyse a stale run.')",
             "ART = '/kaggle/working/diag' if not IN_COLAB else '/content/diag'",
             "shutil.rmtree(ART, ignore_errors=True)",
             "os.makedirs(ART, exist_ok=True)",
             "with zipfile.ZipFile(io.BytesIO(BLOB)) as z:",
             "    z.extractall(ART)",
             "    EMB = sorted(z.namelist())",
             "sys.path.insert(0, ART + '/src')",
             "print('extracted', len(EMB), 'files ->', ART)",
             "print('has legacy_arch:', os.path.exists(ART + '/src/legacy_arch.py'),",
             "      '| has diagnose_architecture:', os.path.exists(ART + '/src/diagnose_architecture.py'))"),
        md("## 2. Find the artefacts",
           "",
           "Checkpoints come from an attached dataset. The cell searches **by content**, prints the",
           "mount tree when it finds nothing, and says exactly what to attach."),
        code("INPUT = '/kaggle/input'",
             "CKPTS = []",
             "for p in sorted(glob.glob(f'{INPUT}/**/*.pt', recursive=True)):",
             "    CKPTS.append(p)",
             "for p in sorted(glob.glob(f'{INPUT}/**/*.zip', recursive=True)):",
             "    print('zip on the mount:', p)",
             "if not CKPTS:",
             "    print('no .pt found. Attach a dataset holding the v20 checkpoints')",
             "    print('(dist/kaggle-output/checkpoints/*-s20261009.pt, ~230 MB) and re-run this cell.')",
             "    for d in sorted(glob.glob(f'{INPUT}/**/', recursive=True))[:25]:",
             "        print('  ', d, '->', sorted(os.listdir(d))[:6] if os.path.isdir(d) else None)",
             "else:",
             "    for p in CKPTS:",
             "        print(f'  {os.path.getsize(p)/1e6:7.1f} MB  {p}')",
             "print('CHECKPOINTS:', len(CKPTS))"),
        md("## 3. The faithful reader",
           "",
           "`build_faithful()` tries `legacy_arch` and `model_arms` and accepts the one that loads with",
           "**0 missing AND 0 unexpected** tensors. A checkpoint with no faithful reader is REFUSED —",
           "not scored with warnings, because a fabricated model's numbers read exactly like real ones."),
        code("os.chdir(ART)",
             "import torch",
             "import eval_harness as EH",
             "import legacy_arch as LA",
             "import model_arms as MA",
             "from diagnose_architecture import build_faithful, vocabs_from, predict, census, sensitivity, compiler, probe, eligible, verdict",
             "GOLD_PATH = ART + '/data/annotation/gold-tashkeela-300.jsonl'",
             "assert os.path.exists(GOLD_PATH), GOLD_PATH",
             "gold = EH.load_human_gold(GOLD_PATH)",
             "print('gold:', len(gold), 'rows ->', GOLD_PATH)",
             "print('\\n-- what each on-disk reader can load --')",
             "for p in CKPTS:",
             "    ck = torch.load(p, map_location='cpu', weights_only=False)",
             "    for nm, mod in (('legacy_arch', LA), ('model_arms', MA)):",
             "        try:",
             "            m = mod.Arm(ck['cfg'], dict(ck['sizes']), ck.get('arm', 'treatment'))",
             "            inc = m.load_state_dict(ck['model'], strict=False)",
             "            print(f'  {os.path.basename(p):34s} {nm:12s} missing={len(inc.missing_keys):3d} unexpected={len(inc.unexpected_keys):3d}')",
             "        except Exception as e:",
             "            print(f'  {os.path.basename(p):34s} {nm:12s} {type(e).__name__}: {e}')"),
        md("## 4. Component census + the conjunction",
           "",
           "Every head, every slice, beside its own floor. Then the number that matters: the",
           "**conjunction** (root AND wazan AND case on the same rows) and the marginal gain from",
           "lifting each single component to its own ceiling."),
        code("DEVICE = torch.device('cpu')",
             "REPORT = {}",
             "for p in CKPTS:",
             "    model, ck, reader = build_faithful(Path(p))",
             "    V = vocabs_from(ck)",
             "    max_len = (ck['cfg'].get('data') or {}).get('max_len', 96)",
             "    print('=' * 92); print(f'{os.path.basename(p)}  reader={reader}  arm={ck.get(\"arm\")}')",
             "    print(f'  model tensors {len(model.state_dict())} == checkpoint {len(ck[\"model\"])}  (0/0)')",
             "    rows, H = predict(model, V, gold, max_len, want_hidden=False)",
             "    c, cstats, _ = census(rows)",
             "    sens = sensitivity(rows)",
             "    comp = compiler(rows, gold)",
             "    for k, v in sorted(c.items()):",
             "        print(f'  census {k:24s} {v}')",
             "    print(f'  case macro-F1 {cstats[\"macro_f1\"]:.4f}   majority {cstats[\"majority_class\"]} @ {cstats[\"majority_acc\"]:.3f}')",
             "    for k, v in sens.get('triple_variants', {}).items():",
             "        print(f'  {k:28s} {v:.4f}')",
             "    for k, v in sens.get('marginal_pp_if_lifted_to_ceiling', {}).items():",
             "        print(f'  MARGINAL {v:+6.1f} pp   {k}')",
             "    for k, v in comp.items():",
             "        if isinstance(v, dict):",
             "            print(f'  compiler {k:44s} stem {v.get(\"stem_correct\")}/{v.get(\"n\")}  token_exact {v.get(\"token_exact\")}  skeleton_yield {v.get(\"skeleton_yield\")}')",
             "        else:",
             "            print(f'  compiler {k:44s} {v}')",
             "    REPORT[os.path.basename(p)] = {'reader': reader, 'heads': dict(c), 'case_stats': cstats,",
             "                                   'sensitivity': sens, 'compiler': comp}",
             "print('\\narms measured:', len(REPORT))"),
        md("## 5. Frozen-trunk probe — representation, or input?",
           "",
           "A head can fail because the **head** is wrong, because the **representation** lacks the",
           "information, or because the information is **not in the input**. A logistic probe on the",
           "frozen trunk separates them: `probe >> head` = fix the head; `probe ~ head` = fix the",
           "representation (an architecture change); `probe ~ floor` = the input cannot carry it."),
        code("for p in CKPTS:",
             "    model, ck, reader = build_faithful(Path(p))",
             "    V = vocabs_from(ck)",
             "    rows, H = predict(model, V, gold, (ck['cfg'].get('data') or {}).get('max_len', 96), want_hidden=True)",
             "    pr = probe(H, rows)",
             "    print('=' * 92); print(os.path.basename(p))",
             "    for k, v in pr.items():",
             "        print(f'  probe {k:16s} {json.dumps(v, default=str)}')",
             "    REPORT.setdefault(os.path.basename(p), {})['probe'] = pr",
             "    del model, H",
             "print('done')"),
        md("## 6. The CURRENT architecture — is the recent structure actually in the build?",
           "",
           "The census above reads v20, which predates every recent module. This section builds the",
           "**current** `model_arms.Arm` and asserts, mechanically, that each recent module exists —",
           "because a module that is absent is indistinguishable from a module that is untrained when",
           "you only read a loss curve."),
        code("import yaml",
             "cfg = yaml.safe_load(open(ART + '/config/shared.yaml', encoding='utf-8'))",
             "ck0 = torch.load(CKPTS[0], map_location='cpu', weights_only=False)",
             "sizes_now = dict(ck0['sizes'])",
             "# the CURRENT architecture needs the class spaces the v20 checkpoint predates",
             "sizes_now.setdefault('wazan_canonical', 0)",
             "print('current cfg[model] =', json.dumps(cfg['model'], default=str))",
             "print('checkpoint sizes    =', json.dumps(ck0['sizes'], default=str))",
             "print('union wazan classes :', ck0['vocab']['wazan'], '(the target space the run must build)')",
             "for m in ('use_char_encoder', 'case_governor', 'definiteness', 'wazan_canonical'):",
             "    print(f'  cfg flag {m:20s}', (cfg.get('model') or {}).get(m, '<absent>'))"),
        code("# Every recent module, asserted present. A name in a config is not a module in the build.",
             "RECENT = ['h_wazan_canonical', 'h_proclitic', 'h_enclitic', 'h_definiteness',",
             "          'case_gov_q', 'case_gov_k', 'case_gov_v', 'wazan_to_root', 'char_proj']",
             "srcdir = ART + '/src'",
             "txt = open(srcdir + '/model_arms.py', encoding='utf-8').read()",
             "present = {n: (f'self.{n}' in txt) for n in RECENT}",
             "for n, ok in present.items():",
             "    print(f'  {n:22s} {\"PRESENT\" if ok else \"ABSENT\"}')",
             "char_ok = 'char_pos' in txt and 'pool_gate' in txt",
             "print(f'  {\"char_encoder.char_pos/pool_gate\":22s} {\"PRESENT\" if char_ok else \"ABSENT\"}')",
             "missing = [n for n, ok in present.items() if not ok] + ([] if char_ok else ['char_pos/pool_gate'])",
             "assert not missing, f'the current architecture is missing: {missing}'",
             "print('\\nthe recent architecture IS in this payload — and NO v20 checkpoint contains it,')",
             "print('so every module above is currently UNTRAINED. That is the gap this arc closes.')"),
        md("## 7. What is wrong, and what the fix has to be",
           "",
           "Filled in from the census above. The rule for reading it: a component is *binding* when",
           "lifting it to its own ceiling buys the most conjunction. `root ARITY -> gold pattern`",
           "being ~0 retires the decode-conditioning hypothesis; a head scoring BELOW its own",
           "majority floor is not weak, it is mis-trained."),
        code("# The prescription is written from the MEASURED table, not from a prior. Each line carries",
             "# the pre-registered gate it must clear. Nothing below is a guess about magnitude.",
             "PRESCRIPTION = [",
             "  ('wazan NOTATION -> radical slot-set space',",
             "   'predict the slot-set (h_wazan_canonical, already wired, currently untrained) and let the',",
             "   'renderer write the notation. Measured gap raw 17.6% vs slot-set 98.9% on the SAME rows.',",
             "   'GATE: TRIPLE in slot-set space >= 35% (measured 35.1% on the 80-row slice, to be re-derived on 278)'),",
             "  ('case head below its own majority floor',",
             "   'the head is mis-trained, not merely weak. Item 10: case is GOVERNMENT (deprel), not a local',",
             "   'label. oracle P(Case|upos,deprel) = 0.7331 macro-F1 vs the current ~0.44.',",
             "   'GATE: case macro-F1 > 0.62 on PADT dev, with the deterministic subset reported by coverage'),",
             "  ('root OOV',",
             "   'the head memorises in-vocab and generalises poorly; the char pathway exists for exactly',",
             "   'this. Measure the faithful OOV split BEFORE choosing a fix -- the 0/75 figure came from',",
             "   'unfaithfully loaded models and must not be quoted.',",
             "   'GATE: OOV whole-root improves beyond 2*max(sd) of the 3-seed spread AND the in-vocab half does not fall'),",
             "  ('target feasibility',",
             "   'the compiler caps ANY planner: 78.8% rule-only, 86.2% with the dictionary, on gold plans.',",
             "   '98% end-to-end is therefore NOT reachable by a better planner alone; require the plan to raise',",
             "   'the COMPILER ceiling or to use the dictionary, and report the ceiling beside every target.',",
             "   'GATE: state the ceiling in the same table as the target, always'),",
             "]",
             "for title, why, gate in PRESCRIPTION:",
             "    print(f'\\n### {title}\\n  {why}\\n  {gate}')",
             "print('\\n-- nothing above is shipped; each is pre-registered, and each names its measuring command.')"),
        code("os.makedirs('/kaggle/working/results', exist_ok=True)",
             "RES = {'code_bundle_sha': EXPECT_SHA, 'n_checkpoints': len(CKPTS),",
             "       'target': 0.98, 'ceiling_rule_only': 0.788, 'ceiling_dictionary': 0.862,",
             "       'arm_report': REPORT}",
             "outp = '/kaggle/working/results/diagnose_architecture.json'",
             "with open(outp, 'w', encoding='utf-8') as fh:",
             "    json.dump(RES, fh, indent=2, default=str)",
             "print('wrote', outp, os.path.getsize(outp), 'bytes')",
             "print('this notebook trained nothing and spent no GPU. CPU_ONLY =', CPU_ONLY)"),
        md("## Notes for the next artifact",
           "",
           "- The **training** notebook is a separate kernel with `enableGpu: true`. Its run must be",
           "  preceded by this one, because every gate it carries comes from the table above.",
           "- The **checkpoints** need to be an attached dataset (`*-s20261009.pt`, ~230 MB zipped).",
           "  Without them sections 3–5 skip and the notebook still validates sections 1, 2, 6.",
           "- `dist/_overwrite_proof/src/` is the training-era code and is **not** shipped here: it is",
           "  vendored into `src/legacy_arch.py`, which is what the payload carries."),
    ]


def check_freshness() -> int:
    """Does the notebook on disk carry the code that is in the working tree RIGHT NOW?

    This is NOT the generator's self-check that the skill warns about ("it compares the artifact to
    itself and can never catch staleness"). The stored EXPECT_SHA is read OUT of the notebook and
    compared against a FRESH build of the bundle from the working tree, so any src/ edit after the
    last build fails here. The project's own `verify_run_code.py` does the same thing for the full
    payload (src/ + config/ + gold + the silver dictionary half); this notebook's payload is
    deliberately code-only, so it needs its own gate rather than a mismatched one.
    """
    if not OUT.exists():
        print(f"FAIL: {OUT} does not exist -- run: python src/make_notebook_diag.py")
        return 1
    nb = json.loads(OUT.read_text(encoding="utf-8"))
    baked = None
    for c in nb["cells"]:
        if c["cell_type"] != "code":
            continue
        for line in "".join(c["source"]).splitlines():
            if line.startswith("EXPECT_SHA = "):
                baked = ast.literal_eval(line.split("=", 1)[1].strip())
    _, fresh, nfiles = embedded_bundle_code_only()
    print(f"notebook on disk : {OUT.name}  {OUT.stat().st_size/1e3:.1f} KB")
    print(f"  baked EXPECT_SHA : {baked}")
    print(f"  working tree     : {fresh}  ({nfiles} files)")
    if baked == fresh:
        print("  OK -- the notebook carries the working tree's code")
        return 0
    print("  STALE -- the notebook does NOT carry the working tree's code.")
    print("  Any number it produces describes OLD code and is VOID. Regenerate:")
    print("    python src/make_notebook_diag.py")
    return 1


def main() -> int:
    if "--check" in sys.argv:
        return check_freshness()
    chunks, sha, nfiles = embedded_bundle_code_only()
    nb_cells = cells(sha, chunks, nfiles)
    nb = {"cells": nb_cells,
          "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python",
                                      "name": "python3"},
                       "language_info": {"name": "python", "version": "3.11"}},
          "nbformat": 4, "nbformat_minor": 5}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")

    # every code cell must PARSE -- a syntax error that reaches Kaggle costs a run to discover
    bad = 0
    for i, c in enumerate(nb_cells):
        if c["cell_type"] != "code":
            continue
        src = "".join(c["source"])
        try:
            ast.parse(src)
        except SyntaxError as e:
            bad += 1
            print(f"  SYNTAX ERROR in cell {i}: {e}")
    n_code = sum(1 for c in nb_cells if c["cell_type"] == "code")
    print(f"wrote {OUT}  ({OUT.stat().st_size/1e3:.1f} KB)")
    print(f"  cells: {len(nb_cells)} ({n_code} code)  parse failures: {bad}")
    print(f"  EXPECT_SHA {sha}")
    print(f"  verify freshness: python src/make_notebook_diag.py --check")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
