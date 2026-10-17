# arabic-root-tree

> **This is the RESEARCH PEAK SNAPSHOT.** Read [`PEAK-README.md`](PEAK-README.md) first: it states the
> frozen source commit, what the model measured at that point, and what is deliberately absent.
> [`WHATS-EXCLUDED.md`](WHATS-EXCLUDED.md) lists every exclusion with its licence and size.
>
> This tree contains **no third-party corpora and no model weights**, by design. `python demo.py`
> exercises the deterministic components (compiler, iʿlāl trace, mīzān, iʿrāb, Naḥw sandbox, semantic
> binder) with no data and no dependencies beyond the standard library.

A **Native Arabic Root-Tree Foundation Model** — a proposed architecture that plans Arabic generation at the
level of the semantic root graph and morphological pattern (وزن) rather than surface letters, then renders
fully-vocalized text with grammatical consistency.

**Status (rev. 18, 2026-10-10): the build is COMPLETE and the first runs have happened.**
`src/` holds **57 files**: two production modules (`reconcile.py`, `wazan_normalizer.py`), the training stack
(`model_arms.py`, `train.py`, `smoke_test.py` + `config/shared.yaml`), the harness carrying the shared
final-surface metric (`eval_harness.py`, `final_surface.py`), the renderer (`renderer.py`, `render_rules.py`)
and the data builder (`build_training_jsonl.py`); the rest are measurement and verification probes. The merged
per-token training JSONL **exists** (`data/out/`), a private Kaggle notebook exists, and the 3-seed grid plus the
silver-vs-gold ablation have run. This **is** a git repository (30 commits). What still gates a Kaggle run is
**not** the existence of the machinery but the renderer's *fidelity*, the blind protocol, and a pre-registered
metric table — the itemised gate is **[EVIDENCE_LOG.md §5](EVIDENCE_LOG.md)**.

> **Status note (2026-10-11):** this header is anchored at **rev. 18 / 30 commits**. The project is now at
> **round 27**, with the 3-seed grids (v14, v15, v26), the abstention-gate work (§2al–§2ao) and a private
> offsite backup (`BACKUP.md`) behind it — so several numbers below have moved.
> **For where the project actually stands, read [`ACTIVE_BACKLOG.md`](ACTIVE_BACKLOG.md).**
> `EVIDENCE_LOG.md` is append-only history: its older sections are superseded by later ones *by design*, so
> never read it as a status document.

---

## Read these in order

| # | File | What it is |
|---|---|---|
| 0 | **[START-HERE.md](START-HERE.md)** | **Cold-start brief: read this first if you have no memory of this project.** Glossary of the docs' ID codes, red lines, environment, and the next three tasks with acceptance criteria. |
| 1 | **[ACTIVE_BACKLOG.md](ACTIVE_BACKLOG.md)** | **The live plan — what to do next. At most 10 items, each with hypothesis · metric · dataset split · acceptance threshold · next command.** This is the only file that states the project's current priorities. |
| 2 | **[EVIDENCE_LOG.md](EVIDENCE_LOG.md)** | **History only — append-only.** Every measured finding with its fallback routes; §2aa–§2ap are the recent rounds and §5 is the Kaggle deployment gate. **Not a status document:** older sections are superseded by later ones by design. Never read it to decide the next move. |
| 3 | [PREFLIGHT.md](PREFLIGHT.md) | Theoretical review (A1–A15), triage, measured decoder/wazān requirements, 16 build artifacts. **Read its rev-8 status block first — the triage below it is rev. 3/4.** |
| 4 | [WORKFLOW.md](WORKFLOW.md) | Plain-language walkthrough of how the model is built. |
| 5 | [HANDOFF.md](HANDOFF.md) | Verified numbers, what is broken in the spec, what blocks progress. |
| 6 | [COLAB.md](COLAB.md) | Run manifest: what Colab/Kaggle download themselves, what you must upload, unit costs. |
| 7 | [RESOURCES.md](RESOURCES.md) | Catalogue of every dataset, tool and model — URLs, licenses, sizes, live status. |
| 8 | [docs/](docs/) | `ORIGINAL-SPEC.md`, `SPEC-REV4.md`, **`SPEC-REV6.md` (authoritative design; §8.2 corrections)**, `SOLVING.md`. |

---

## The five things that matter

**1. The wazān source was never a corpus problem — but it is not a clean label either.** CAMeL Tools' CALIMA
analyser emits a `pattern` feature with radical digits `1`/`2`/`3` and **`4` for quadriliteral roots**
(verified: زَلْزَلَ → `1َ2ْ3َ4َ`), with the full vocalization inline. What replaced the original problem is
decomposition: the pattern bakes in the clitic and the case vowel, and after the corrected pipeline only
**53.6% of tokens yield a well-formed 3/4-slot label** — *coverage of well-formed labels*, not accuracy.
**No public gold wazān exists, so correctness is currently unvalidatable.**

**2. What actually blocks is root assignment, not missing data — and it is now measured.** CALIMA returns a
usable root for ~41% of tokens (`#` marks an unassigned weak radical, `NTWS` is a raw-surface fallback). A
dictionary built from **gold** annotation recovers **92.5%** of the rest at **99.7% correctness**, held out
across PADT splits (`src/reconcile.py`). A dictionary built from CALIMA's *own* output recovers ~0% — CALIMA's
failures are per-lexeme and deterministic, so it can never repair itself. **The previously published
96.4%/99.8% figure was degenerate and in-sample; see `SPEC-REV6.md` §8.2.**

**3. The 3D root tensor cannot represent quadrilateral roots.** Spec §2.1 proposes `M_root ∈ R^(28×28×28)`.
40 of the 1,642 Quranic roots (2.4%) have four radicals — زلزل, وسوس, برهن, سنبل — and CAMeL independently
needs a 4th digit slot for exactly these roots. The wazān inventory itself contains 4-slot templates, so the
target vocabulary is not 3-slot either. Fixed in `SPEC-REV6.md` §2.1.

**4. The constraint is the corpus, not the GPU.** Tashkeela is 75M *words* ≈ **98M tokens**, which is
Chinchilla-optimal for only a **~5M-parameter** model. The spec's "45x short" figure was an artefact of its
choice of **1.5B parameters** — the architecture is not the problem. A 25M from-scratch model costs
**3.1 units** on Colab, or **0** on Kaggle's free tier. Qwen3 drops from "foundation" to ablation arm.

**5. Train the baseline from scratch, not from a pretrained trunk** — and give it the same auxiliary heads as
the treatment (`SPEC-REV6.md` §5.2). Otherwise the comparison measures Qwen3's pretraining, or the treatment's
extra supervision density, not the architecture.

Full detail in [HANDOFF.md](HANDOFF.md) §3.4, §5.4, §6; run costs in [COLAB.md](COLAB.md).

---

## Why this is not Kaggle-ready yet

Full statements in **[EVIDENCE_LOG.md §5](EVIDENCE_LOG.md)**. Short form:

- **G1 — training input EXISTS (rev. 10, refreshed rev. 18). ✅** `data/out/` holds the merged per-token JSONL
  with per-head targets and masks (`padt-{train,dev,test}.jsonl` = 282,384 records, 223,881 / 30,239 / 28,264),
  `vocab.json` and a build manifest. Rebuilt from HEAD on 2026-10-10 after the PADT-transliteration fix: usable
  gold-root supervision rose **96,671 → 99,869** records and `unmappable_unit` fell **13,258 → 10,509**.
- **G2 — training code EXISTS (rev. 12). ✅** `config/shared.yaml` (one file, both arms), `src/model_arms.py`
  (both arms + computed parity + `--fit-parity`), `src/train.py` (masked multi-task loop), `src/smoke_test.py`
  (**7 invariants, all passing**) and `requirements.txt`. Parity is computed, not asserted: baseline
  13,490,865 / treatment 13,491,112, gap 0.00%.
- **G3 — renderer BUILT (rev. 13); the shared metric is now measurable on a vocalized corpus.**
  `src/renderer.py` implements digit-in-place rendering (`ال` survives) plus the R1g hybrid (table then
  rule, residual reported). Coverage **30.0% → 35.3%**; skeleton match **89–93%**. Two corrections to how
  the old pair reads: the **94.3% was agreement with CALIMA's own `diac`** (a consistency check, reproduced
  at 92.4%), **not gold accuracy**; and **PADT's FORM is undiacritized**, so it CANNOT carry the shared
  final-surface metric — gold-vocalized scoring must use EQTB's `uthmani_token`. Coverage barely rose
  despite reconciliation supplying 26.9% more roots, because the binding constraint is **pattern–root arity
  agreement**. See `EVIDENCE_LOG.md` §2m.
- **G4 — evaluation: harness + ceilings done, blind protocol outstanding.** `src/eval_harness.py` implements the
  shared final-surface metric (both arms scored on one metric), per-class macro-F1 for case with the
  majority-class baseline beside it, the per-root-class root breakdown, and wazān coverage-only. The required
  CALIMA-vs-human **ceilings exist**: case macro-F1 **0.459**, root **0.451/0.444** on two independent human
  corpora. Still missing: the blind annotation subset + inter-annotator agreement (needs humans; blindness
  cannot be retrofitted). See `EVIDENCE_LOG.md` §2k.
- **G5 — MEASURED (full corpus, all 97 books).** Tashkeela coverage against the gold-keyed dictionary:
  **type 5.7%** (6.9% folded), **token 46.2%** (54.1% folded), **masked 53.8%** (45.9% folded). The type figure
  is **8× lower** than the token figure — the divergence is why the protocol required all three. The corpus
  measures **66.5M Arabic tokens** (74.8M units), not the ~98M the docs assumed: a **~1.5× correction** that
  moves the Chinchilla-optimal size to ~3.3M parameters. See `EVIDENCE_LOG.md` §2j.
- **G6 — wazān labels: proclitic gone, coverage 53.9%, correctness still unvalidatable.** Both clitic edges are
  stripped from `d3tok` surfaces with a zero-refusal rate at corpus scale; the label no longer carries `ال`.
  Gold wazān does not exist publicly, so this stays **coverage of well-formed labels, never accuracy**.
- **G7 — no falsification criterion, no minimum detectable effect, no pre-registered metric table.**
- **G8 — repo hygiene. 🟡 partial (rev. 18).** It **is** a git repository now (30 commits at rev. 18), and
  `data/raw`/`data/out` are gitignored on licence grounds. But `README.md`, `HANDOFF.md` and `PREFLIGHT.md`
  described rev 3–5 state for six revisions; three separate documents carry quantitative claims with no
  automated way to re-derive them before a run; and the renderer's headline coverage moved 35.3% → 81.8%
  without any document noticing. **When a number changes, sweep the repo for the old one** —
  `grep -rn "<old value>" *.md docs/*.md`.
- **G9 — licence.** QAC GPLv3 · PADT/NYUAD CC BY-NC-SA · Tashkeela GPL-2.0 · CAMeL data GPL v2 · arramooz GPL.
  Fine for a paper. **A public Kaggle notebook is a distribution** — keep it private, or keep the corpora out.

All nine are local CPU work costing **0 compute units**. Kaggle's free tier (30 GPU h/week, +15 if you link a
Colab Pro account) is more than enough for the from-scratch arms — ≈9 T4-hours total.

---

## Layout

```
arabic-root-tree/
├── README.md · ACTIVE_BACKLOG.md · EVIDENCE_LOG.md · NEXT-SESSION.md · BACKUP.md
├── PREFLIGHT.md · HANDOFF.md · COLAB.md · RESOURCES.md · WORKFLOW.md
├── docs/
│   ├── ORIGINAL-SPEC.md   the received spec, unmodified
│   ├── SPEC-REV4.md · SPEC-REV6.md   the design (REV6.1 = current)
│   └── SOLVING.md
├── data/
│   ├── raw/               ← corpora as downloaded (~57 MiB)
│   └── out/               ← (EMPTY — reserved for the derived JSONL; see G1)
├── .venv/                 ← Python 3.11.15 + camel-tools 1.6.0 (CALIMA data in ~/.camel_tools)
├── src/                   ← 33 files; all probes except the two marked ★
    ├── reconcile.py             ★ PRODUCTION: weak-root reconciler + root-scheme converters
    │                              (incl. qac_form_to_arabic for vocalized Buckwalter FORMs)
    ├── wazan_normalizer.py      ★ the corrected §6 wazān pipeline: proclitic + enclitic strips
    │                              from d3tok surfaces, root-gated geminate expansion
    ├── eval_harness.py          G4 — the shared final-surface metric, per-class macro-F1,
    │                              per-root-class breakdown, and the CALIMA-vs-human ceilings
    ├── build_training_jsonl.py  Task 3 / G1 — the merged per-token records (5 heads + masks)
    ├── measure_tashkeela_coverage.py  G5 — type/token coverage + masked fraction
    ├── fetch_corpora.py         re-fetches every corpus in data/raw, size-checked per file
    ├── paths.py                 one cross-platform definition of every corpus path
    ├── inspect_eqtb.py          Task 1: reads qrtb/Quranic.csv; non-empty AND REAL counts
    ├── test_label_normalization.py  run live against calima-msa-r13 (proclitic/enclitic/geminate)
    ├── inventory.py · inspect_qac.py · list_quadriradical.py · count_treebanks.py
    │                            corpus statistics, checksums, QAC roots
    ├── verify_calima_pattern.py · quantify_calima.py · audit_renderer.py
    │                            CAMeL capability probes: pattern feature, ambiguity, generation
    ├── fix_renderer.py · retest_renderer.py
    │                            the digit-in-place renderer (94.3% exact at 30.0% coverage)
    ├── build_wazan_inventory.py · measure_normalizer_gain.py
    │                            wazān inventory; label-coverage delta
    ├── measure_decoder_requirements.py · measure_reconciler_generalization.py
    │                            arity/projectivity; held-out reconciler coverage
    ├── derive_padt_translit.py  PADT→Arabic mapping derived from aligned token pairs
    ├── check_arramooz.py · check_solving_claims.py · verify_rev5.py
    ├── test_round*.py · test_proposal*.py · test_revised_extractor.py
    │                            the round-by-round verification harnesses
    └── prune_uv_cuda_cache.py   reclaims CUDA wheels left in ~/.cache/uv
```

> **Install CPU-only.** `uv pip install camel-tools` pulls torch, which drags in the NVIDIA CUDA wheels
> (3.2 GB) + triton (894 MB) — a 5.6 GB venv and a 9.5 GB uv cache on a GPU-less laptop. Use
> `--torch-backend=cpu` (venv drops to 1.2 GB) and run `src/prune_uv_cuda_cache.py` afterwards.

---

## Environment note — this repo now also runs on Windows (2026-10-09)

The original environment was a CPU-only Arch laptop. The working copy has moved to a Windows desktop
(Apache-style `G:\arabic-root-tree`) and the repo is no longer laptop-only:

- **Paths:** every script resolves its corpora through `src/paths.py` (the 24 hardcoded
  `/home/rendi/arabic-root-tree/...` constants are gone). Override with `ART_ROOT` if the corpora live
  elsewhere. `python src/paths.py` prints each expected corpus as present/absent.
- **Interpreter:** on Windows the venv interpreter is `.venv/Scripts/python.exe`, not `.venv/bin/python`.
  Build with `uv venv --python 3.11 .venv` then
  `uv pip install --python G:/arabic-root-tree/.venv/Scripts/python.exe --torch-backend=cpu -r requirements.txt`.
- **Verified on Windows:** `camel-tools==1.6.0`, `torch==2.14.1+cpu` (`cuda False`), both CAMeL data
  packages installed (124 MB), `verify_calima_pattern.py` reproduces the documented patterns, and
  `test_proclitic_strip.py` passes against live CALIMA.
- **`data/raw` is still empty here** — the corpora are GPL/NC and were handed over separately. Every
  script that needs one now fails loudly with the re-fetch recipe instead of a bare `FileNotFoundError`.

---

## Reproduce every number

```bash
cd ~/arabic-root-tree

# corpus statistics + SHA256 (CPU, seconds)
python3 src/inventory.py
python3 src/inspect_qac.py
python3 src/list_quadriradical.py
sha256sum data/raw/qac-morphology-0.4.txt data/raw/ar_padt-ud-*.conllu

# CAMeL probes (needs the .venv; CALIMA data in ~/.camel_tools)
.venv/bin/python src/verify_calima_pattern.py   # pattern feature incl. digit 4
.venv/bin/python src/quantify_calima.py         # ambiguity + pattern entanglement
.venv/bin/python src/audit_renderer.py          # PROVES CAMeL cannot generate (R1)

# the reconciler: held-out coverage AND correctness
.venv/bin/python src/reconcile.py --limit 12000

# root-scheme conversion, derived from aligned pairs
.venv/bin/python src/derive_padt_translit.py

# renderer accuracy vs coverage; wazān label coverage
.venv/bin/python src/fix_renderer.py
.venv/bin/python src/measure_normalizer_gain.py
.venv/bin/python src/test_round4.py             # CALIMA-derived dictionary fails (~0.8%)
```

CPU-only, zero GPU. **If a document quotes a number, the command above is what produced it — run it before
repeating the number.** Three figures in these docs have already been caught that way (the retired 96.4%/99.8%
among them).

---

## On disk (verified)

- **QAC morphology v0.4** — 6.3 MB · 128,219 segments · **1,642 distinct Quranic roots** · 100% root-tagged
- **UD Arabic-PADT** — 51 MB · 7,664 sentences · 282,384 tokens · root 86.2% · case 52.0% · vocalized form
  100% — but only **50.1% of those `Root=` values are usable roots** (`SPEC-REV6.md` §8.2 C3)
- **UD Arabic-NYUAD** — 19,738 sentences · **0% `Root=` / 0% `Vform=`** (syntax and case only)
- **EQTB** — **139,376 data rows** × 51 cols, the QAC dependency layer, derived from the same tokens as QAC
  (present on disk as `qrtb/Quranic.csv`; **read by no script yet** — `EVIDENCE_LOG.md` B18)
- **jQuranTree** src + bin — verified to contain no dependency-graph payload

Checksums in [HANDOFF.md](HANDOFF.md) §3.3.

## Licensing warning

QAC **GPLv3** · PADT/NYUAD **CC BY-NC-SA** · Tashkeela **GPL-2.0** · CAMeL data packages **GPL v2** ·
arramooz **GPL** · EQTB **MIT over GPLv3-derived data** (treated as GPLv3 here).
A research paper is unaffected. A commercial app cannot be built cleanly on this corpus base.
See [HANDOFF.md](HANDOFF.md) §5.3 and `SPEC-REV6.md` §7.
