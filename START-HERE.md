# START HERE — cold-start brief for a fresh agent

**You have no memory of this project. This file is written for exactly that.** It is the fastest path from
zero to useful. Read it fully (5 minutes) before opening anything else.

**This orientation file is anchored at ROUND 18 (2026-10-10) · design rev. 8 · `src/` = 57 files.** It is kept
because its glossary, red lines and environment notes are still correct — but it is **not** the project status,
and the rounds after it moved several load-bearing numbers.

> **STATUS LIVES IN EXACTLY ONE PLACE: [`ACTIVE_BACKLOG.md`](ACTIVE_BACKLOG.md).** That is the live plan —
> at most 10 items, each carrying its hypothesis, metric, dataset split, acceptance threshold and next
> command. **Do not read `EVIDENCE_LOG.md` to find out where the project is:** it is an append-only forensic
> log, and its older sections are superseded by later ones *by design*, so a round-9 line like "nothing has
> been trained" sits beside round-26 3-seed results. Where the log and the backlog disagree about what to do,
> **the backlog wins**.

What has not changed: **a run costs GPU time and moves nothing else** — local CPU work is the cheap part, so
measure before spending (RED LINE 1).

> **READ §2x BEFORE QUOTING ANY RENDERER NUMBER.** Between rev 13 and rev 18 the headline hybrid coverage
> moved 35.3% → 81.8% → **73.1%**, and only the last figure is trustworthy: the middle one was produced with
> the evaluation split inside the dictionary. §2x gives the exact decomposition and the surviving fidelity
> numbers.

---

## 1. What this is, in four sentences

A research project to build a **Native Arabic Root-Tree model**: instead of generating Arabic letter by
letter, it plans the word as *(root جذر + pattern وزن + grammatical role + case)* and lets a **deterministic
renderer** spell the surface. The claim under test is that this representation is better than a matched-size
transformer predicting subword tokens, because case endings and vocalization become correct **by
construction** rather than by memorisation. It is a **paper**, not a product — the corpus is ~98M tokens, which
supports a ~5M-parameter model, and the whole ground-truth stack is copyleft/non-commercial. Everything so far
is **resource acquisition, measurement, and verification**; the only production code is the weak-root
reconciler and the wazān normaliser.

## 2. Read order

| Order | File | Why |
|---|---|---|
| 1 | **this file** | orientation, red lines, glossary |
| 2 | **[`ACTIVE_BACKLOG.md`](ACTIVE_BACKLOG.md)** | **the live plan — what to do next.** ≤10 items, each with hypothesis · metric · split · acceptance threshold · next command |
| 3 | `README.md` | the index + the Kaggle-gate summary |
| 4 | **`EVIDENCE_LOG.md`** | **HISTORY ONLY, append-only.** §2aa–§2ap are the recent rounds; §5 = the Kaggle gate; §0 = the six decisive tests with status. **Never read it for "current state"** |
| 5 | `docs/SPEC-REV6.md` | **the authoritative design** (rev 6.1). §8 = provenance table, §8.1 = claims you must NOT report as results, §8.2 = corrections |
| 6 | `HANDOFF.md` | verified corpus statistics (§3) and the spec's own contradictions (§5) |
| 7 | `PREFLIGHT.md` | theory (A1–A15) + the 16 build artifacts. **Read its rev-8 status block; the triage below it is rev 3/4** |
| 8 | `WORKFLOW.md` | plain-language walkthrough of the intended build |
| 9 | `COLAB.md` / `RESOURCES.md` | run costs / every dataset and tool with licence and URL |
| 10 | `data/raw/MANIFEST.md` + `data/raw/CHECKSUMS.sha256` | what is actually on disk, hashed, and which scripts read it |

Do **not** read `docs/ORIGINAL-SPEC.md` as current — it is the received spec, kept unmodified as the source of
truth for *what was proposed*, and `HANDOFF.md` §5.1 lists its design bugs.

---

## 3. ID glossary — the docs speak in codes

`EVIDENCE_LOG.md`, `PREFLIGHT.md` and `SPEC-REV6.md` refer to findings by code everywhere. Definitions live in
three different files, so here they are in one place.

**Architecture findings (A, from `PREFLIGHT.md` Part A)** — `A1` dependency graph has no training scheme ·
`A2` "order-free" fights autoregressive decoding · `A3` the two arms are scored on different objects (biggest
validity threat) · `A5` "root+pattern → surface" is not a function · `A6` the 28³ root tensor is 70% empty ·
`A7` no loss-weighting scheme · `A8` merged treebanks *conflict*, not just go missing · `A9` evaluation
contamination · `A10` syntax head is hostage to thin data · `A11` English gloss can't come from the model ·
`A12` the GBNF constrains delivery, not generation · **`A13` supervisory parity — the baseline must get the same
auxiliary heads** · **`A14` evaluation is CALIMA-mediated while the treatment trains on CALIMA** ·
`A15` no renderer.

**Data/pipeline items (M = measured defects, B = open items, R = blocked routes)** — `R1` no renderer
(CAMeL cannot generate) · `R2` licensing · `M1` weak-root extraction is **class-biased** · `M2` CALIMA's
`root` field is noisy · `M6` ~32% of CALIMA roots contain `#` · `E1` evaluation circularity (`E1a` = hold out
NYUAD) · `B5` four incompatible root encodings.

**Corpus acronyms** — `QAC` Quranic Arabic Corpus (morphology, Leeds, GPLv3) · `PADT` UD Arabic-PADT
(newswire, CC BY-NC-SA) · `NYUAD` UD Arabic-NYUAD (**0% roots**, syntax/case only) · `PUD` UD Arabic-PUD
(`NOASSERTION`) · `EQTB` the QAC **dependency layer** as a third-party RAR/CSV · `Tashkeela` 75M vocalized
words (the pretraining corpus, **not downloaded**) · `CALIMA` CAMeL Tools' MSA analyser (`calima-msa-r13`) ·
`arramooz` GPL morphological dictionary with a `wazn` column · `wazān` = pattern (فَعَلَ), `root` = جذر.

**Test/blocker codes** — `T1–T6` the six decisive tests (`EVIDENCE_LOG.md` §0, with rev-8 status) ·
`G1–G9` the Kaggle deployment gate (§5, summarised below).

---

## 4. Environment

**Local (this laptop, CPU-only, no CUDA).** Python **3.11.15**, venv at `.venv` (**1.2 GB**, uv-managed, **no
pip** inside — `python -m pip freeze` prints nothing; use `importlib.metadata`).

```bash
cd ~/arabic-root-tree
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python --torch-backend=cpu -r requirements.txt
.venv/bin/camel_data -i morphology-db-msa-r13         # 40.5 MB, GPL v2
.venv/bin/camel_data -i disambig-mle-calima-msa-r13   # 88.7 MB, GPL v2 — MANDATORY
```

`--torch-backend=cpu` is not optional here (a default install wastes 5 GB on CUDA wheels on a GPU-less
machine). Pinned versions: `camel-tools==1.6.0`, `torch==2.14.1+cpu`, `transformers==5.19.0`,
`numpy==2.4.6`, `pandas==3.0.6`, `arramooz-pysqlite==0.4.2`. `datasets`/`pyarrow` are deliberately absent —
they are only needed to stream Tashkeela, which must happen in the cloud.

**Cloud (Colab/Kaggle).** The reverse applies: **do NOT pass `--torch-backend=cpu`** — the image ships a
working CUDA torch and overriding it silently trains on CPU. Bootstrap cells are in `COLAB.md` §1.
Machine: i5-1235U, 15 GB RAM, **43 GB free disk** (the pipeline cannot hold 50 GB corpora locally, and
Tashkeela must be streamed).

## 5. Data

`data/raw/` holds **17 files, all hashed** in `data/raw/CHECKSUMS.sha256` — verify with
`cd data/raw && sha256sum -c CHECKSUMS.sha256`. `data/raw/MANIFEST.md` says what each one is, its licence,
**and which scripts actually read it**.

Two traps recorded there:

- ⚠️ **`quranic-treebank.csv` is a DECOY** (5 columns of verse text). The real EQTB treebank is
  **`qrtb/Quranic.csv`** — 57 MB, UTF-16, 51 columns, **139,376 data rows**. Several docs have this backwards.
- ⚠️ **66 MB of EQTB is on disk and read by no script.** Treat it as unwired, not as part of the pipeline.
- `data/out/` holds the **built training input** (G1 closed since rev. 10): `padt-{train,dev,test}.jsonl`
  (282,384 records) and `tashkeela-{train,dev,test}.jsonl` (silver), plus `vocab.json` and the build
  manifests. It is **gitignored** — generated and large. Rebuild with `src/build_training_jsonl.py`.
- **Absent by design:** Tashkeela (401 MB, cloud-only), Qwen3 weights, arramooz sqlite (lives in
  site-packages), the Arabic Lexicons.

## 6. The numbers you may quote (and how to re-derive each)

**Rule: if a document quotes a number, run the command before repeating it.** Three figures in these docs have
already been caught this way, including one that was cited as proof the root problem was solved.

| Quantity | Value | Command |
|---|---|---|
| QAC segments / stems / roots / quadriliteral | 128,219 / 77,915 / **1,642** / 40 (2.4%) | `python3 src/inventory.py`, `src/list_quadriradical.py` |
| PADT sentences / tokens / surfaces / roots | 7,664 / 282,384 / 21,516 / **2,884** | `python3 src/count_treebanks.py` |
| PADT `Root=` tokens that are **usable** roots | **99,869** of 223,881 train tokens = **44.6%** (of the 192,991 tokens carrying a `Root=` value, **51.7%**). Was 96,671 before the `_t → ث` fix landed (rev. 18) | `.venv/Scripts/python.exe -c "import json,collections;c=collections.Counter(json.loads(l)['root_from'] for l in open('data/out/padt-train.jsonl',encoding='utf-8'));print(c)"` |
| CALIMA gives a usable root | ~41% (`#` 31.3%, `NTWS` 27.4%) | `.venv/bin/python src/test_round4.py` |
| **Root recovery, held out** (rev. 18) | exact dictionary **91.7% coverage, 99.9% of recovered correct** (91.6% of all) · with the proclitic fallback **94.8% / 99.3%**. Report BOTH — a dictionary that answers is not one that answers correctly | `.venv/Scripts/python.exe src/reconcile.py --limit 12000` |
| Renderer — ⚠️ **the CALIMA-match column is a CONSISTENCY check, NOT human fidelity** | **94.5%** on the rule route = can we rebuild CALIMA's OWN `diac` from root+pattern (rev. 18; the historical 92.4% / 94.3% are the same check on earlier code). See §2s.2 and §2x.4 | `.venv/Scripts/python.exe src/renderer.py --measure` |
| Wazān label **well-formed coverage** | **53.9%** — the ladder is 31.7% (SPEC-REV5) → 53.6% (rev 8) → **53.9%** (rev 9). NOT accuracy | `.venv/Scripts/python.exe src/measure_normalizer_gain.py --limit 6000` (rev. 9 prints all five rows) |
| Clitic entanglement (PADT, 5,062 lex tokens) | proclitic **21.2%** · enclitic **0.4%** · strip refusals **0** | same script |
| Tashkeela coverage (rev. 10) | **type 5.7%** · **token 46.2%** (54.1% folded) · **masked 53.8%**; corpus = **66.5M Arabic tokens** (74.8M units), 460,667 types | `.venv/Scripts/python.exe src/measure_tashkeela_coverage.py` |
| EQTB shape (Tasks 1) | 51 cols × **139,376 data rows**, 0 malformed, no wazān col. **Non-empty ≠ coverage:** `root`/`root_ar` **35.9% REAL**, `nominal_case` **22.9% REAL**, `depend_rel`/`head_rel` **100% REAL** (placeholders are `ـ`) | `.venv/Scripts/python.exe src/inspect_eqtb.py` |
| **CEILING — case macro-F1** (rev. 11) | **0.459** (CALIMA vs EQTB, n=1,176) · majority-`GEN` baseline 0.333 | `.venv/Scripts/python.exe src/eval_harness.py --ceiling --source eqtb --limit 12000` |
| **CEILING — root accuracy** (rev. 11) | **0.451** (QAC n=8,000) · **0.444** (EQTB n=4,401) — two independent corpora agree | `... --ceiling --source qac --limit 8000` |
| Root ceiling **per class** | sound 0.91/0.90 · doubled 0.77/0.71 · quadriliteral 0.82/0.63 · **assimilated/hollow/defective all 0.000 — CALIMA ABSTAINS (`#`)** | same |
| **RENDERER** coverage (rev. 18, R18d) | ⭐ **content-word coverage 93.4%** (2,337 / 2,502) is the figure to quote · all-token hybrid **72.8%** = 38.6% rule-branch + 34.5% table-branch · residual **26.9%**, of which **22.8% is a STRUCTURAL floor** (closed-class function words have no root by design), 3.7% root supply, and **17 tokens = 0.43% renderer-relevant — with RULE GAP now 0**. ⚠️ the brief rev-17 "81.8%" was CONTAMINATED — see §2x | `.venv/Scripts/python.exe src/renderer.py --measure --limit 4000` |
| **ALL-TOKEN** coverage (rev. 18e, Tier 1 ∪ Tier 2) | **94.1%** Arabic tokens (3,763 / 4,000) · **94.5% RUNNING TEXT** (4,078 / 4,315 via `--include-punct`; 315 PUNCT/SYM, all identity) · bypass alone 32.5% · Tier 3 `X` (4.7%) excluded · the 4,000-token denominator is **FROZEN** (`--limit` counts Arabic tokens; the punct run writes its own report file) | `.venv/Scripts/python.exe src/renderer.py --measure --limit 4000 [--include-punct]` |
| **BYPASS Tier-1 validation** (HELD OUT, rev. 18g) | **99.54%** out of sample in-register (Tashkeela books 60–96, map 0–9) at **≥ 0.95**, delivering **14.0% of running text** · in-sample 91.09% → held out **91.00%** — **not memorisation** · **QAC Qur'anic in-register 97.31%** (map surahs 1–57, eval 58–114; 1 unmapped token vs 8,074) · ⚠️ **REGISTER-LOCKED, NOT orthography-locked**: cross-register QAC 59.60%, EQTB 31.26% — **47 of 101** surfaces take a different majority vocalisation in the Qur'an → needs **one map per register** | `.venv/Scripts/python.exe src/score_closed_class_bypass.py --fold-uthmani --qac-gold --qac-split` |
| **Uthmani fold layer** (rev. 18g) | `src/normalize_uthmani.py` — self-test **12/12 PASS** · Tashkeela **SKELETON-change 0** (provably non-destructive) vs EQTB 8,363 (intended wasla/dagger folds) · lifted EQTB Tier 1 26.49% → **31.26%** · ⚠️ did NOT reach the projected "unmapped → ≈0%": EQTB leaves **45.7%** of its tokens bare (no vowel to match) | `... --selftest` / `--check eqtb tashkeela` |
| **RENDERER** fidelity (rev. 18) | on the rule route vs CALIMA `diac` **94.5%** · reconciled **91.8%** · hybrid-rule **91.4%** · the table branch has NO `=calima` by construction (PADT FORM is 98.7% undiacritized) and is scored on `= gold` **90.6%** · skeleton 86–93% | same |
| Renderer skeleton by root class | sound **87.2%** · doubled 41.8% · quadriliteral 12.2% · assimilated 3.2% · **hollow/defective/hamza 0.0%** (CALIMA abstains — a root-SUPPLY failure, §2s.4) | same |
| **RENDERER vs the 300 human gold triples** (rev. 17) | **raw 9.4% · NFC 10.4% · clitic-aware 41.7% · +hamza 43.9% · skeleton 24.8%**; coverage 100% by construction, 0 abstentions | `.venv/Scripts/python.exe src/measure_renderer_gold.py` |
| **SHARED FINAL-SURFACE METRIC, on the STEM** (rev. 17) | `src/final_surface.py` — symmetric legal-affix decomposition; `coverage` / `stem_accuracy_of_covered` / `stem_yield` are THREE separate keys. WIRED into `eval_harness.score_human_gold`, so both arms return it | `.venv/Scripts/python.exe src/final_surface.py --selftest` |
| **RENDERER vs EQTB gold VOCALIZED** (rev. 17) | coverage **14.4%**; exact **5.8% → 9.0%** (with case vowel) · folded 6.2% → 10.9% · **skeleton 89.8%** | `.venv/Scripts/python.exe src/renderer.py --eqtb` |
| **RENDERER CEILING on the shared metric** (rev. 17) — 🔴 the paper's binding constraint | **HUMAN oracle triple: 47.1% stem (v3), 100% coverage, 0 abstain** · CALIMA triple: coverage **54.3%**, 8.0% of covered, **4.3% yield**, skeleton 49.0%. No model can exceed the 47.1% | `.venv/Scripts/python.exe src/final_surface_ceiling.py` |
| **Renderer weak-radical RE-REALIZATION (v3)** (rev. 17) | ALL 278: v1 **116** → v2 122 → **v3 131** (41.7% → **47.1%**); weak 98: 19 → **34**; true-weak 69: 19 → **30**. v2 DELETED a weak r2 unconditionally (`قَوْلُ`→`قَلُ`) and is kept registered as the documented WRONG version | `.venv/Scripts/python.exe src/render_rules.py` |
| **WEAK acceptance test** (rev. 17) | `--weak-only` = **98 rows, not 93** — there is NO strata column, and ~30 of the 35 "assimilated" rows are hamza roots written with a bare alif. Weak bucket = **13.3%** of the gold, NOT 5.7% (that is Tashkeela *type coverage*) | `.venv/Scripts/python.exe src/measure_renderer_gold.py --weak-only --engine v3` |
| **v3 residual on true-weak rows** (rev. 17) | 39 of 69 still fail, but **only 11 are weak-radical** — 10 are case/diacritic and 6 are nunation. The next lever is `apply_case`/nunation, NOT more weak rules | same script (`--engine v3`) |
| **Checkpoint vocab is NOT reproducible offline** (rev. 17) | rebuilt union vocab surface **16,503** vs checkpoint **13,143** — the cloud's silver build sampled narrower Tashkeela content. Guard refuses on mismatch; the vocab is now saved INSIDE the checkpoint | `.venv/Scripts/python.exe src/build_union_vocab.py` |
| **Is the surface derivable from (root, wazān, case)?** (rev. 17) | 193 distinct triples, 11 with >1 surface, **0 of those differ in nunation — all 11 differ by CLITICS**. The triple determines the STEM | `.venv/Scripts/python.exe src/check_nunation_derivability.py` |
| wazān inventory | 72 lexicon templates vs 216 running-text patterns | `src/check_arramooz.py`, `src/build_wazan_inventory.py` |
| CAMeL generation support | **none** — `GeneratorError` | `.venv/bin/python src/audit_renderer.py` |
| Case imbalance (PADT) | Gen 66.9% / Acc 19.8% / Nom 13.3% | `src/count_treebanks.py` |
| EQTB | 51 cols × **139,376 data rows** (docs say 139,377 = incl. header) | `data/raw/MANIFEST.md` |
| **SILVER records (rev. 18 — clean single pass)** | train **120,000** · dev **40,000** · test **40,000** (the previous files were 240,000 / 100,300 / 80,000 = TWO appended passes while the manifest described only the last); masks root **71.3 / 67.9 / 65.8%** · wazān **62.3 / 62.7 / 61.4%** · case **13.8 / 27.4 / 29.9%**, syntax & NTP 0% (ABSENT, not failed) | `python src/build_training_jsonl.py --source tashkeela --limit 120000 --limit-eval 40000` |
| Silver root dictionary (rev. 18) | **40,265 keys** = **13,736** PADT `Root=` (TRAIN; was 13,255 before the `_t → ث` fix) + **26,529** arramooz. Without arramooz it is 13,736 and root supervision silently decays | printed by the builder; the PADT half is generated into the Kaggle bundle as `data/silver_root_dict_padt.json` |
| **SILVER-vs-GOLD labels (rev. 17)** | of the **196** gold rows with a silver label: raw exact **24.5%** · hamza/diacritic-normalised **67.3%** · **radical-slot set 99.5%**; **1 row of 196** is structurally different. Root 93.9% bare-alef | `.venv/Scripts/python.exe src/compare_silver_vs_gold.py` |
| **3-seed arm difference (rev. 17)** | case macro-F1 **−0.011 (NOT separated)** · root **+0.057 (SEPARATED)** · wazān **+0.039 (SEPARATED)** · NTP +0.004 (noise). n=3, sd reported | Kaggle v5 results (`dist/runs/v5-3seed-results.json`, `v5_seed_summary.json`) |
| Model size, matched pair | PADT-only vocab (v5): 13,490,865 / 13,491,112 · union vocab 120k+120k (ablation): **13,393,933 / 13,394,029** (tower 6583) | `python src/model_arms.py --parity` |

**Retired values — do not quote:** 96.4% / 99.8% root recovery (degenerate and in-sample; see
`SPEC-REV6.md` §8.2), the 18% renderer coverage, the 26.6% gate pass rate, the 0.97% `(root × wazān)` fill
rate, the "216 awzān" as a label inventory, "193,012 tokens with a gold root".

## 7. Red lines — read before writing anything

1. **Do not start training and do not spend compute units.** The user's standing instruction is
   *collect resources only*; confirm before spending. Kaggle's free tier is not an excuse to skip this.
2. **CAMeL cannot generate.** `Generator(db)` raises `GeneratorError` on `calima-msa-r13`; `calima-msa-s31`
   is LDC-gated and not installed. The renderer is a thing you build.
3. **CALIMA's analysis dict has `lex`, NOT `lemma`.** `a.get("lemma")` returns `None`, and `x.get(...) or ""`
   silently keys everything on `''` — that exact bug produced a one-entry table that "resolved" 100% of tokens
   and was cited as a result for six revision rounds. Guard empty keys; assert non-degeneracy.
4. **The reconciliation dictionary must be gold-derived (never from CALIMA output) and must not include the
   evaluation split.** CALIMA's failures are per-lexeme with **zero** overlap between what it gets right and
   what it breaks, so a CALIMA-derived dictionary can never repair a CALIMA failure. QAC and EQTB are held out
   entirely — and note EQTB **re-annotates the same Qur'anic tokens as QAC**, so holding out QAC verses while
   training on EQTB leaks them.
5. **Never report wazān numbers as accuracy.** No public gold wazān exists; only *well-formedness* is
   measurable. Say "coverage of well-formed labels".
6. **Case must be reported as per-class macro-F1, never raw accuracy** — always-predict-`Gen` scores 66.9%.
7. **The blind protocol must exist before any annotation.** Blindness cannot be retrofitted, and a
   CALIMA-mediated eval makes the whole experiment uninterpretable (A14/E1).
8. **Do not quote the sample-scale numbers in `PREFLIGHT.md` §B or the `(root × wazān)` fill rate** — they
   come from ≤6k-token samples and at least two are known-biased.
9. **A public Kaggle notebook is a distribution.** QAC (GPLv3), PADT/NYUAD (CC BY-NC-SA), Tashkeela (GPL-2.0)
   and CAMeL data (GPL v2) are all in the chain: keep the notebook **private**, or keep the corpora out of it.
10. **`#` in a CALIMA root means an unassigned weak radical, not "no root"**; `NTWS`/`backoff` are
    raw-surface fallbacks. And in PADT, **spaces inside `Root=` are radical separators** (`r f .d`).
11. **Do not pool NYUAD/PUD with PADT for anything morphological** — they carry 0% `Root=`/`Vform=`.
12. **Do not trust a doc over a script.** Where prose and code disagree, the code is the ground truth and the
    disagreement is itself a finding to report (this has happened at least four times here).

## 8. Next tasks, in order — with acceptance criteria

The critical path is now **build**, not measure. Each task is local CPU work, 0 compute units.

> **STATUS rev. 9 (2026-10-09): Tasks 1 and 2 are DONE — see `EVIDENCE_LOG.md` §2i.** EQTB is wired and kept
> (`src/inspect_eqtb.py`), the proclitic **and** enclitic strips are implemented and verified
> (`src/wazan_normalizer.py`), and the templatic-shaddah defect in `expand_geminate` is fixed. The measured
> coverage ladder is 31.7% → 53.6% → **53.9%** with the composition explained. **Task 3 (the merged JSONL,
> G1) is now the critical path**, and two new blockers feed it: **Finding D** (four-digit silver labels are
> unreachable through the MLE disambiguator, so quadriliteral Head-3 supervision must come from gold PADT +
> arramooz) and the still-unmeasured **Tashkeela coverage** (G5).

**✅ Task 1 — decided, executed: KEEP, wired (was: decide EQTB's fate, 30 min).** Either wire it or delete it, but stop leaving 66 MB of unwired data
under a doc that calls it the dependency-layer source. *Acceptance:* a script reads `qrtb/Quranic.csv`
(UTF-16, TAB), prints 139,376 rows and confirms the columns; if it is kept as a test suite, its verse IDs are
excluded from any QAC training range.

**✅ Task 2 — wazān extractor v3 (the proclitic strip). DONE rev. 9.** The label still carried `ال`
(`المستشار` → `المُسْتَ123`), which entangles Head 3 with the clitic plane. Strip via `prc0`–`prc3`
**alignment**, not positional slicing. *Acceptance:* `measure_normalizer_gain.py` re-run, label no longer
contains the proclitic, new coverage reported as coverage. **Met — but the proposed method was NOT
implementable, and that is itself the finding.** `prc0`–`prc3` are LABELS (`Al_det`, `wa_conj`, `bi_prep`) and
carry no letters; `prc0` is also the INNERMOST clitic. The clitic **surfaces** come from `d3tok`. The enclitic
edge was fixed at the same time, and the geminate expansion was found to be corrupting templatic shaddas
(`الطُّلّاب` → `1ُ23ا3`). See §2i for the ladder — including the 32 false positives the strip removed.

**✅ Task 3 — merged JSONL = G1. BUILT (PADT half), rev. 10.** One record per token with per-head target
**and per-head mask**, built only from non-eval sources. **Done:** `data/out/padt-{train,dev,test}.jsonl` —
**282,384 records** (223,881 / 30,239 / 28,264), 151.7 MB, with `vocab.json` + `build_manifest.json`. The
builder is `src/build_training_jsonl.py` and its docstring is the schema reference. Four numbers reproduce a
documented figure **exactly** (total tokens 282,384 · usable roots 96,671 · case-marked 116,741 · 680 test
sentences), and the token stream was independently reconciled against the source `.conllu`. **Remaining:** the
**Tashkeela coverage measurement** — type coverage, token coverage and masked fraction together — which is the
one number that sets the usable corpus size and therefore the model size the paper may claim
(`src/measure_tashkeela_coverage.py`; see G5).

**Then**, in order: the eval harness with macro-F1 (G4) → the blind OOD annotation → supervisory parity in code
(A13) → shared config + smoke test → Kaggle.

> **STATUS rev. 17 (2026-10-09): items 1-3 are DONE and RUN.** The silver records exist
> (`--source tashkeela`), the 3-seed grid ran (v5) and the arm difference is now read **against the
> seed spread** — root and wazān separated, case did NOT (baseline ahead), so the architectural
> claim is half-supported. The silver-vs-gold ablation is built and its **label-level** crux number
> is measured (raw 24.5% / normalised 67.3% / slot-set 99.5%). See `EVIDENCE_LOG.md` §2q for all of
> it, including the three transport failures and the cloud bootstrap that now works.
>
> **The next real work is NOT more runs.** It is: (a) the **renderer** (R1) — it EXISTS and its
> human fidelity is now MEASURED (`EVIDENCE_LOG.md` §2s): **32.0% clitic-aware / 24.8% skeleton /
> 9.4% raw** on the 300 human gold triples, **~90% skeleton but 6-11% exact** on vocalized EQTB,
> at **14-35% coverage**. The remaining work is (i) define the metric on the **STEM** (29.5% of the
> mismatch is the clitic plane, already rendered correctly), (ii) finish the weak-radical rules as
> RE-REALIZATION not deletion (the naive version regresses 11 rows), (iii) nunation (34 rows,
> `apply_case` cannot emit tanwin), (iv) coverage — the only lever that makes a large-scale number
> possible; (b) the **blind annotation subset + inter-annotator agreement** (G4), which needs a
> second human and cannot be retrofitted; and (c) the **wazān label convention gap** measured in
> §2q — the human gold and the CALIMA pipeline spell the same template differently
> (digit-vs-letter for a weak radical), and 39 of 278 gold patterns are in a class the strict gate
> masks entirely. Fixing the *convention* (not the model) is worth more than any further training.

**Do not begin at the model.** `data/out/` now holds 282,384 PADT records **and** 220,300 silver
records, so G1 is closed — but the two arms must still be scored through one shared final-surface
metric, and that metric needs the renderer.

## 9. Repository state and known issues

- **Version control:** initialised in this revision (rev. 8). `.gitignore` excludes `.venv/` and the corpora
  in `data/raw/` — **deliberately**: committing GPLv3/CC-BY-NC-SA corpora into git would redistribute them.
  Re-fetch them and verify against `data/raw/CHECKSUMS.sha256`.
- **Hardcoded absolute paths:** several scripts set `PD = "/home/rendi/arabic-root-tree/data/raw"`. Fine here,
  broken anywhere else. `reconcile.py --raw` is the pattern to follow.
- **Sampling:** the headline reconciler numbers use `--limit 12000`; smaller limits shift them by ~2pp. Quote
  the limit with the number.
- **Doc drift is a recurring failure mode here** (three top-level files described rev 3–5 state until rev 8;
  one figure survived six rounds because nobody re-ran its script). **When you change a number, sweep the whole
  repo for the old one** — `grep -rn "<old value>" *.md docs/*.md`.

## 10. If you have Kaggle access — the runbook

This section is written for an agent that has been handed Kaggle credentials. Round 16 and 17
have now actually run it, so the short version changed: **the cloud path works, and the notebook
carries its own code because nothing else can be uploaded.**

**⚠️ TRANSPORT — read before writing any upload code (round 17, all measured):**

- **`datasets/upload` does not exist** (HTTP 404, an HTML page). `datasets/create/new` and
  `datasets/create/version/{owner}/{slug}` exist but want a **JSON body carrying blob tokens**
  from a resumable-upload flow (`POST /api/v1/blobs/start` → 404) that this kernel-scoped token
  cannot drive. **Assume you cannot create or update a dataset.**
- **The kernel source is capped at <1 MB** — `HTTP 400: The kernel source must be less than 1
  megabytes in size.` So a data payload cannot ride in the notebook either.
- **What works:** `kernels/push` (the notebook, up to ~900 KB), `kernels/status`, `kernels/output`
  — and note those two take **`userName`/`kernelSlug`**, not `user`/`kernel` (400 otherwise).
- **Consequence:** the run bundle is **code only** (~260 KB zip: `src/`, `config/`, the gold, and
  the PADT half of the silver dictionary), embedded as base64 with its **sha256 asserted at run
  time**. The PADT records come from the pre-existing `akhiirendi/arabic-dataset` mount, and the
  **silver records are built inside the kernel** — which is what this file always said to do with
  Tashkeela ("must be streamed", `COLAB.md` §1).
- **A dataset mount is READ-ONLY** and Kaggle may auto-extract it into loose files rather than
  keeping your zip. Never point `ART` at `/kaggle/input`; copy into `/kaggle/working/bundle` and
  assert `os.access(ART, os.W_OK)`.
- **The in-cloud bootstrap works** (verified in the v7 log): `pip install camel-tools==1.6.0
  arramooz-pysqlite==0.4.2` → 12 s; `python -m camel_tools.cli.camel_data -i
  morphology-db-msa-r13` → 40.5 MB; `-i disambig-mle-calima-msa-r13` → 88.7 MB. `arramooz` is NOT
  optional: without it the silver root dictionary falls from 40,265 keys to 13,736 and root
  supervision silently decays, which would read as a modelling result. The build cell therefore
  asserts **mask floors** (root ≥ 55%, wazān ≥ 45%) from the build manifest.
- **Large uploads are unreliable from this host**: a 34.0 MB POST was reset three times
  (10053/10054). Keep every payload small.

**What Kaggle gives you** (`COLAB.md` §5): **30 GPU h/week**, floating and resetting Saturday 00:00 UTC;
**P100 / T4×2** (2× T4, 4 cores, 29 GB RAM); **no A100**; 9 h per session, 12 h max runtime. Linking an
active Colab Pro account adds **+15 h/week that do not consume Colab units**.

**Which experiments fit Kaggle.** The from-scratch arms do: control + treatment (25M, 3 seeds) plus the 50M
scaling check ≈ **9 T4-hours**, free. The **Qwen3-1.7B QLoRA ablation cannot run on Kaggle** (no A100) — that
one stays on Colab at ~15–23 units. Do not run the ablation at 500M tokens (76–114 units).

**What must exist before the first notebook.** None of it exists yet:

1. `data/out/*.jsonl` — the merged per-token records (G1). This is the **only** artifact you upload.
2. The eval harness with macro-F1, scoring **both arms through one shared final-surface metric** (G4/A3).
3. One shared config file both arms read — size, steps, seeds, splits (the matched-size claim is only credible
   if it is literally the same file).
4. A smoke test: tiny model, tiny data, full loop end to end.
5. The baseline's auxiliary heads, so the comparison is supervised the same on both sides (A13/§5.2).

**Session mechanics that bite:**

- **Do not pass `--torch-backend=cpu` in the cloud.** It is correct on the laptop and wrong here.
- **Everything is fetchable in-session except your own artifacts** — QAC via the GitHub mirror, PADT from the
  UD repo, CAMeL data via `camel_data -i`, Tashkeela via `load_dataset`. `COLAB.md` §1 has paste-ready cells
  and §1.3 a checksum gate for the downloads. `datasets`/`pyarrow` are only needed here, not locally.
- **Never hardcode the device** — `device = "cuda" if torch.cuda.is_available() else "cpu"`, then fail loudly
  rather than silently training on CPU.
- **Checkpoint to persistent storage, not the working directory.** Assume a run can be killed without warning;
  set `save_steps` so a restart costs minutes.
- **⚠️ A public Kaggle notebook is a distribution.** QAC (GPLv3), PADT/NYUAD (CC BY-NC-SA), Tashkeela
  (GPL-2.0) and CAMeL data (GPL v2) are all in the chain: keep the notebook **private**, or keep the corpora
  out of the published version. This is a licence constraint, not a preference.
- **Licensing follows the data into the cloud** — fine for a paper, a blocker for anything shipped.

**The gate, restated:** G1–G7 in `EVIDENCE_LOG.md` §5 are all laptop-CPU work at **0 compute units**. Clear them
first; Kaggle time spent before that is spent on nothing.
