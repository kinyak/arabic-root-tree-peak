# Technical Architecture & Implementation Handoff: Native Arabic Root-Tree Foundation Model

**Project**: Dynamic, Interactive, Knowledge-Adaptive Arabic Learning Engine
**Target Scope**: Classical Arabic (الفصحى التراثية) & Modern Standard Arabic (MSA)
**Primary Deliverable**: Foundation Architecture Specification, Data Pipeline, Training Strategy, Mobile Deployment Protocol
**Methodological Framing**: Matched-size controlled architecture study (sub-Chinchilla by design)

> **Revision 6.1 — empirically verified base.** Every quantitative claim below carries a provenance tag
> naming the script in `src/` that produced it, or is explicitly marked **[UNVERIFIED]**. Items that
> changed from REV5 are marked **[FIXED IN REV6]** with the reason. Six defects that survived five prior
> revisions are corrected here (§2.1 topology, §2.2 input leakage, §2.2 operator naming, §2.1 root count,
> §3.1 surface/root conflation, §4 three-slot root head).
> **Known-unvalidated claims are marked; do not report them as results.**
>
> **REV6.1 (2026-10-09)** corrects two provenance defects found by re-executing the cited scripts: the
> gold-dictionary recovery figure in §3.1 was degenerate and in-sample, and PADT's usable root supervision
> is half what §3 implies. Both are detailed in **§8.2**. No architectural decision changes.

---

## 1. Executive Summary & Core Objective

Traditional LLMs process text as linear 1D sequences of subword tokens. For Semitic languages this causes
three systematic failure modes:

1. **Diacritic Blindness** — misplacement of terminal case vowels (*I'rāb*).
2. **Morphological Fragmentation** — arbitrary slicing across roots and vocalic patterns.
3. **Post-Hoc Hallucination** — reverse-engineering *Juthūr* and *Awzān* from surface words after generation.

This handoff specifies a **Native Arabic Root-Tree Model**: rather than generating surface letters first, the
model emits a structured grammatical tuple per token — root, template, clitic features, syntactic role, case —
in **surface word order**, and a **deterministic renderer** produces the fully vocalized surface form.

**The architectural claim is precise:** the model *generates through* a grammatical representation rather
than generating surface text and analysing it afterwards. Grammatical well-formedness is therefore a
property **by construction**, not a hoped-for outcome.

---

## 2. Core Architectural Framework

```
+-----------------------------------------------------------------------------------+
|                           STEP 1: PEDAGOGICAL CONTROLLER                          |
|             Inputs: Learner Proficiency Level, Active Vocabulary, Grammar Goal    |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|        STEP 2: STRUCTURED-TUPLE PLANNER  [FIXED IN REV6 — was "Order-Free"]       |
|  Emits one grammatical tuple per token, LEFT TO RIGHT IN SURFACE WORD ORDER.      |
|  tuple = (root, wazān, clitics, role, case, n_left, n_right)                      |
|  Example: (ك-ت-ب, فَعَلَ, ∅, verb, —, 0, 1)                                       |
|           (ط-ل-ب, فَاعِل, ال, fāʿil, NOM, 0, 0)                                   |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                   STEP 3: DETERMINISTIC RENDERER                                  |
|  (root + template + clitics + case) -> fully vocalized surface.  NOT learned.     |
|  ك-ت-ب + فَعَلَ -> كَتَبَ   |   ط-ل-ب + فَاعِل + ال + NOM -> الطَّالِبُ               |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|               STEP 4: CASE INFLECTION IS AN OUTPUT OF STEP 2, NOT A POST-PASS     |
|   The case field is predicted jointly; Step 4 is the renderer consuming it.       |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                   STEP 5: STRUCTURED JSON DELIVERY TO MOBILE APP                  |
|   Text + Word-by-Word Breakdown (Tashkeel, Root, Wazān, Meaning, Full I'rāb)      |
+-----------------------------------------------------------------------------------+
```

**[FIXED IN REV6] Why "order-free" was removed.** REV5 specified an *order-free* dependency graph. Two
problems: a set of edges has no canonical order, so an autoregressive decoder cannot emit it without
imposing one anyway; and Arabic word order is grammatically load-bearing (جملة فعلية vs جملة اسمية,
fronting for ḥaṣr), so declaring the plan order-free means the renderer must reinvent a layer the grammar
encodes. Surface order is used as the linearisation, and the graph is **observed** during training
(gold trees from the treebanks), so no latent structure is marginalised over — this removes the
non-differentiable-graph problem entirely.

**[FIXED IN REV6] Why the graph is supervised, not latent.** A discrete dependency graph is not
differentiable. The three conventional escapes — REINFORCE, Gumbel relaxation, full marginalisation —
all cost more than they buy here, and all three are unnecessary because the treebanks already contain
the graph. `head`+`deprel` are simply extra **observed** fields on each token.

### 2.1 Root representation — factorized radical embeddings

**[FIXED IN REV6] REV5 specified a `28×28×28×D` coordinate tensor. That is retained only as a display
convention, not as the embedding.** Three defects made the tensor unusable:

**(a) It cannot index 4-radical roots.** Measured (`src/inspect_qac.py`, `src/list_quadriradical.py`):
QAC contains **40 quadrilateral roots, 2.4%** of its 1,642 (`zlzl` زلزل, `wsws` وسوس, `brhn` برهن).
The settled wazān inventory **itself** contains 4-slot templates —
`مُفَعْلِلٌ` · `مُتَفَعْلِلٌ` — so a 3-slot design cannot even represent the target vocabulary
(`src/check_arramooz.py`).

**(b) The topology claim has no mechanism.** REV5 asserted that roots "naturally" land in contiguous
regions capturing **الاشتقاق الأكبر**. With a *separate embedding table per position*, two consonant
permutations share at most one position's vector, so no similarity is induced. Measured
(`src/test_revised_extractor.py`): QAC holds **1,602** triliteral roots and **718 permutation pairs** —
**53.1% of all Quranic triliteral roots participate in at least one permutation pair**, so this is a
majority-of-the-lexicon effect, not a corner case. Counterexamples are common and semantically unrelated:
ر-ق-م (to mark) vs ق-م-ر (*moon*). **[FIXED IN REV6: the claim is removed; the effect becomes an
optional ablation, and the size of the affected set is reported as a finding.]**

**(c) `≈6,500 valid roots` was unsourced.** Measured: Quranic corpus attests **1,642**; the arramooz
lexicon contains **7,650** distinct `root` values — though that field is **not** uniformly a root (it
includes loanwords and proper nouns such as `ءفلم`/film, `آسيا`/Asia, `آذار`/March) and needs cleaning.

**Specification (REV6):**

$$\mathbf{e}_{\text{root}}(r) \;=\; \mathbf{Row}(r) \;+\; \mathbf{r}_1(c_1) + \mathbf{r}_2(c_2) + \mathbf{r}_3(c_3) \;+\; \big[\mathbf{r}_4(c_4)\big]$$

* Four position-indexed radical embedding tables, **not three**; the fourth term applies only to
  quadriliteral roots. There is no tensor and nothing to mask.
* `Row(r)` is a row in a flat root table, **randomly dropped during training** so the model cannot ignore
  the factorized part and then fail on out-of-vocabulary roots.
* **The factorized part is justified by long-tail regularisation only** — a root seen once inherits a
  useful vector from its radical constituents. This is measured, not assumed: **395 of 1,642 Quranic
  roots (24%) are hapax** (`src/inspect_qac.py`).
* **Optional ablation (not a claim).** Add a position-free term $s(c_1)+s(c_2)+s(c_3)$ *alongside* the
  positional terms. Permutations then share exactly that component, and the ablation tests whether
  الاشتقاق الأكبر carries signal. Expect little benefit; finding that is itself a result.

### 2.2 Tuple-to-vector binding — corrected operator and leakage

**[FIXED IN REV6 — target leakage.]** REV5's formula put `+ e_case(Case)` in the **input** word vector
while Head 5's entire job is to **predict** the case. As written the input contains the label. This was
flagged in five consecutive revisions.

The formula is now stated for its actual two roles:

**Training (teacher-forced) input.** All planes are available because they are observed in the gold data:

$$\mathbf{h}_t \;=\; \mathbf{W}_{\text{proj}}\Big( \mathbf{e}_{\text{root}} \odot \mathbf{e}_{\text{wazān}} \odot \mathbf{e}_{\text{clitics}} \Big) \;+\; \mathbf{e}_{\text{pos}}$$

**Inference.** No gold planes exist. The model emits the tuple field by field (§2, Step 2), and its **own
predictions** are embedded and fed back. `e_case` never appears as an input in either setting — case is an
**output** of Head 5 only.

**[FIXED IN REV6 — operator naming.]** REV5 called $\odot$ a "Tensor Product Representation (TPR)". It is
not. A Hadamard product is **commutative and coordinate-wise**: it is multiplicative feature fusion, and it
has no inverse, so it cannot unbind. Smolensky's TPR uses the outer product; the compressed variant is
Plate's circular convolution. **REV6 calls it what it is — multiplicative feature fusion — and makes no
binding claim.** If a true binding is wanted, that is a separate architectural experiment to be stated as
such.

* **e_root** — from §2.1 (four radical tables + a droppable row).
* **e_wazān** — one of **72** templates. Verified against arramooz (`src/check_arramooz.py`).
* **e_clitics** — multi-hot over the proclitic inventory CALIMA exposes directly (`prc0`–`prc3`, `enc0`).
  These are **gold-labelled segments**, not inferred.
* **e_pos** — available at training; at inference POS is implied by the emitted role field.

---

## 3. Data Engineering & Strict Non-Leakage Architecture

### 3.1 Partitioning

```
+-----------------------------------------------------------------------------------+
|                            TRAINING & RECONCILIATION STACK                        |
|  1. PADT   7,664 sents / 282,384 tokens / 21,516 distinct surfaces / 2,884 roots   |
|  2. Arramooz  7,650 root values (needs cleaning) / 72 canonical templates          |
|  3. Tashkeela  75M vocalized words — reconciled via PADT + Arramooz               |
+-----------------------------------------------------------------------------------+
                                          |
                        [ zero data / lexical overlap ]
                                          v
+-----------------------------------------------------------------------------------+
|                        HELD-OUT ZERO-SHOT EVALUATION SUITES                       |
|  Track 1 (Syntax & Case)      : UD_Arabic-NYUAD  19,738 sents                      |
|  Track 2 (Classical Morphology): QAC + EQTB — entire Qur'an held out               |
+-----------------------------------------------------------------------------------+
```

**[FIXED IN REV6]** REV5 called 20,614 the count of *"gold surface roots"*. It is a **surface** count, and
re-measures to **21,516**. PADT contains **2,884 distinct roots** — a factor of **7.5×** fewer
(measured by parsing the `.conllu` directly). Conflating the two overstates the root inventory by 7.5×.

**Zero-leakage rule.** QAC and EQTB are excluded from **both** training and the reconciliation dictionary.
The dictionary is built from **PADT + arramooz only**. (REV5 §3A said "merge PADT + QAC + EQTB" while its
scorecard held QAC out as pristine — those two cannot both hold.)

**Gold-derived root reconciliation.** Measured (`src/test_round4.py`):

| CALIMA `root` field | share |
|---|---|
| clean, usable | **41.3%** |
| contains `#` (weak radical unassigned) | 31.3% |
| contains `NTWS` (fallback marker) | 27.4% |
| **total unusable** | **58.7%** |

A dictionary built from PADT's human `Root=` column recovers:

* **91.7%** of unusable-root tokens with a **held-out** dictionary (1,965 / 2,143), exact surface match
* **92.5%** with the proclitic-stripping fallback (1,982 / 2,143)
* of the tokens it recovers, **99.8%** get the **correct** root (1,962 / 1,965) — i.e. **~92% of CALIMA-unusable
  content words end up with a correct root**; ~7.5% are hard failures (surface absent from the dictionary)

Measured by `src/reconcile.py --limit 12000`: dictionary built from **PADT train** only, probe drawn from
**PADT dev + test** (disjoint documents), comparison against that split's own gold `Root=`.

**[CORRECTED IN REV6.1 — see §8.2]** REV5/REV6 reported **96.4% / 99.8%** here, sourced to
`src/test_round4.py`. Those figures had three defects: (1) the script read `analysis["lemma"]`, a field
CALIMA does **not** have (it exposes `lex`), so with `or ""` it keyed every row on the empty string and
printed a degenerate result — a one-entry table "resolving" 100% of tokens; (2) the figure was **in-sample**
(the dictionary was keyed on surfaces taken from the same file as the unusable tokens); (3) it measured
**coverage only**, never whether the recovered root was correct. The script is fixed and now reproduces the
numbers it was supposed to (13.4% for the hand-written dictionary, 0.8% for the CALIMA-derived one, overlap
≈ 0); the reconciler itself now lives in `src/reconcile.py`.

**[also corrected] PADT's `Root=` column is only ~50% usable root annotation.** Of PADT train's 192,991
`Root=`-bearing tokens, **96,671 (50.1%)** carry a root that survives a POS + radical-count + translit
filter — 33.9% are on closed-class POS, 6.9% are unmappable (loanword stems such as `barlIn`, `'amIrik`),
4.8% are the `OOV` sentinel and 4.4% have the wrong radical count. The "193,012 tokens with a root" figure
in §3 therefore overstates usable root supervision by ~2×.

**Why the dictionary must be gold-derived.** Measured: of the surfaces CALIMA resolves and those it does
not, the intersection is **exactly zero**. CALIMA's failure is strictly **per-lexeme** — a word it fails on,
it fails on every occurrence. A dictionary derived from CALIMA output therefore *cannot* repair a CALIMA
failure, while a gold-derived one repairs almost all.

**[UNVERIFIED — measure before reporting]** Tashkeela coverage is **not yet measured**. REV5 asserted
"reconciled via PADT + Arramooz". Required protocol — report **all three**:

1. **Vocabulary type coverage** — |Tashkeela vocab ∩ gold dict keys| / |Tashkeela vocab|
2. **Token coverage** — covered tokens / 75M, which is what determines how much supervision exists
3. **Masked token fraction** — tokens where Head 2/3 loss is set to zero

Types systematically **understate** token coverage, so reporting one alone misrepresents the result. Note
also that the join keys differ: arramooz keys on the word/lemma, PADT on the unvocalized surface. A joint
dictionary needs a declared key and a stated precedence order.

### 3.2 Label vs rendering separation

* **Head 3 target (label):** normalised to a canonical **3- or 4-slot** stem, with the terminal case vowel
  stripped. Renderer keeps the literal compressed pattern.
* **[FIXED IN REV6]** REV5 said "3-slot" without qualification, and its §6 code left the **case vowel**
  inside the label, so Head 3 remained entangled with Head 5. Corrected implementation:
  `src/wazan_normalizer.py`. Measured well-formed-label coverage rises from **31.7% → 53.6%** (+21.9 pp)
  on 5,062 tokens. **This is coverage of well-formed labels, not accuracy.**
* **[NOT YET DONE — state as open, do not claim]** The label still carries the **proclitic surface**:
  `المُسْتَ1ا3ُ` → `المُسْتَ123`, and `ال1ا2ِ3ُ` → `ال1ا2ِ3`. Head 3 therefore remains entangled with the
  clitic plane.

  **Why this is not a one-line fix.** The obvious rule — "strip everything before the first digit" — is
  wrong, because letters preceding digit 1 are ambiguous between proclitic and **templatic**:
  `المُسْتَ1ا3ُ` (Form X, مُسْتَفْعِل) contains `م`/`س`/`ت` that belong to the *template*, while the
  leading `ا`/`ل` is the definite article. Separating them requires aligning CALIMA's `prc0`–`prc3` fields
  against the pattern, not positional slicing. Until that is implemented and measured, any coverage figure
  for Head 3 must state that proclitics remain in the label.

---

## 4. Multi-Task Training Objectives

$$\mathcal{L}_{\text{Total}} = \mathcal{L}_{\text{NTP}} + \lambda_1 \mathcal{L}_{\text{Root}} + \lambda_2 \mathcal{L}_{\text{Wazān}} + \lambda_3 \mathcal{L}_{\text{Syntax}} + \lambda_4 \mathcal{L}_{\text{Case}}$$

```
                                [ Transformer Latent Hidden State h_t ]
                                                   |
      +--------------------+-----------------------+-----------------------+--------------------+
      |                    |                       |                       |                    |
      v                    v                       v                       v                    v
  Head 1 (NTP)        Head 2 (Root)          Head 3 (Wazān)        Head 4 (Syntax)       Head 5 (Case)
Predict Next Lemma    (C1..C4 radical IDs)   72-class template     Dep role + arity      Case class
[Next-Token Loss]     [4-slot CE]            [Multi-Class CE]      (fāʿil / mafʿūl)      (NOM/ACC/GEN)
```

**[FIXED IN REV6]** Head 2 was "Predict (C1,C2,C3) — 3D Cross-Entropy". Now **four** radical slots, matching
the 4-slot templates the inventory contains.

**Head 4 — arity.** Measured across both treebanks (`src/measure_decoder_requirements.py`): non-projective
arcs are **0.40%** (PADT) and **0.02%** (NYUAD); 91.1% / 99.4% of sentences are fully projective. Right-arity
nevertheless reaches **28** (PADT) and **105** (NYUAD), with >4 right-dependents on 0.73% / 1.55% of tokens.
**Therefore: always emit a distance (the projectivity shortcut saves ~4 bits on 99.6% of tokens and is not
worth the machinery), and use explicit count classes 0–4 plus an overflow class with a unary continuation
bit and a hard cap.**

**Loss weighting.** Cross-entropy scales differ by orders of magnitude across heads (4-slot root CE vs a
3-way case CE). Normalise each head by log(vocab size) as a starting point; Kendall-style learned
uncertainty weights are the principled option. **Weights must live in the shared config file** (§5.2).

### 4.1 `cas` mapping for Head 5 — verified

| `cas` | Meaning | Head 5 target | Measured share |
|:---:|:---:|:---:|:---:|
| `n` | Nominative (مرفوع) | Class 0 `NOM` | ~5.5% |
| `a` | Accusative (منصوب) | Class 1 `ACC` | ~9.2% |
| `g` | Genitive (مجرور) | Class 2 `GEN` | ~33.0% |
| `u` | **Undefined** (غير محدد) | **masked (loss 0)** | ~15.7% |
| `na` | Not applicable | **masked (loss 0)** | ~36.6% |

Source: official CAMeL feature documentation, confirmed empirically (`src/test_proposal_claims.py`).
**`u` is *undefined*, not Damma**, and `i` is not a `cas` value at all. Mapping `u` to Damma would inject
~16% label noise. **Genitive is 67% of case-marked tokens** — so report **macro-F1 per class**, never raw
accuracy, which a constant-`GEN` predictor would score at 0.67.

---

## 5. Experimental Design

### 5.1 Reporting rigor

1. **Renderer accuracy vs coverage** — these are different numbers and must be reported separately.
   Accuracy is measured conditional on the rule applying.
2. **Type vs token coverage vs masked fraction** on Tashkeela — all three (§3.1).
3. **Coverage is never accuracy.** The 53.6% figure in §3.2 is well-formed-label coverage. Validating
   whether a label is *right* requires gold wazān annotation, which is not publicly available.
4. **Per-head, per-class metrics.** Macro-F1 for case; per-root-class breakdown for root.
5. **State the licence position and the non-commercial framing** (§7).

### 5.2 Supervisory parity — the comparison must be fair

**[NEW IN REV6 — this is the largest threat to validity.]** Measured per-step decision cost: a BPE baseline
makes one 32k-way choice = **14.97 bits**; the tuple model makes root × template × offset × role × case =
**27.16 bits** (`src/check_solving_claims.py`). The tuple model therefore does *more* per step — but it also
receives **five labels per token where the baseline receives one**.

Trained that way, the tuple model wins because it was handed five answer keys, which demonstrates nothing
about architecture. **Requirement: give the baseline the same auxiliary heads** predicting root / template /
case / role from its own hidden states, at the same weights from the same config. Then the only remaining
difference is that the treatment **generates through** the grammatical representation while the baseline
generates surface and predicts the labels as auxiliaries. **Without this the headline result is
uninterpretable.**

### 5.3 Evaluation must not be CALIMA-mediated

**[NEW IN REV6.]** The treatment trains on CALIMA-derived silver; the scorer analyses surface with CALIMA.
If the held-out gold labels are CALIMA output plus hand-correction, annotators anchor on the analyser and the
result is a closed loop: the treatment is scored on agreement with an annotator it was trained to imitate,
while the baseline was not.

**Protocol:**
1. Eval labels come from **human annotation or independent treebanks** — never CALIMA.
2. **Blind** annotation subset, no analyser output shown; report inter-annotator agreement.
3. **Report CALIMA-vs-human agreement** so readers can see the metric's ceiling.
4. State plainly that CALIMA silver is **distillation**.

### 5.4 Modelling scale

Target **15M–25M parameters**, framed as a **matched-size comparison, sub-Chinchilla by design**. Both arms
share a config file (size, steps, seeds, splits). Chinchilla-optimal for 25M is ~500M tokens against a
**66.5M-token corpus (measured rev. 10 — see §8.1 item 1; this section previously said ~98M, which was ~1.5×
high)** — a ~7.5× gap that is **acceptable for a matched comparison and must be stated as such**,
not papered over. Note that a factorized embedding table shifts parameters from the easiest-to-train
component (row lookups, dense gradients) to harder ones, so the sample-efficiency gain is smaller than the
parameter arithmetic suggests.

---

## 6. Verified Preprocessing Pipeline

`src/wazan_normalizer.py` — tested. Fixes three defects in REV5's §6.

```python
def normalize_wazan(pat: str, root: str = "") -> tuple:
    """ORDER IS PART OF THE CONTRACT: expand -> map missing slot -> strip case."""
    render = pat
    lab = expand_geminate(pat)                  # 1َ2ُّ -> 1َ2ُ3ُ
    lab = _map_missing_slot_literal(lab, root)  # a trailing weak literal IS the missing radical
    lab = strip_case(lab, root)                 # never eats a radical alif
    return lab, render
```

| defect (REV5) | REV6 fix |
|---|---|
| `strip_case` ate a **radical** alif: `1َ2َا` → `1َ2`, losing slot 3 | A terminal alif is orthographic **only when the radical-digit set is complete**; otherwise it is the missing radical and is mapped to its digit |
| Call **order unspecified**; strip→expand ≠ expand→strip | Order fixed and documented: **expand → map → strip** |
| `lex` guard asserted only non-emptiness | Adds non-Arabic and implausible-length guards, plus a `#`-position agreement check so an affix is never mistaken for a radical |

**Limit, stated plainly:** the `lex` guards validate **shape, not semantics**. CALIMA returns
`lex='راوَنْد'` for رَأَى — valid Arabic, plausible length, passes every check. Only a gold-lexicon
cross-check at use time catches that. Do not describe the function as validating the lemma.

---

## 7. Licensing & Attribution

| Dataset / Tool | Licence | Publication terms |
|:---|:---|:---|
| Quranic Arabic Corpus (QAC) | **GNU GPLv3** | Copyleft. GPL constrains *distribution of derivatives*, not research use |
| EQTB | MIT distribution over GPLv3-derived data | **Treated as GPLv3** here — the derivative-work question is legally contested; we take the conservative reading |
| Arramooz Al-Waseet | **GNU GPL** | Copyleft |
| Tashkeela | **GNU GPL-2.0** | Copyleft |
| CAMeL Tools — **code** | MIT | permissive |
| CAMeL Tools — **data packages** | **GNU GPL v2** | copyleft; the code/data split is often missed |
| UD_Arabic-PADT & NYUAD | **CC BY-NC-SA 4.0** | NonCommercial |
| UD_Arabic-PUD | **NOASSERTION** | Research-only; no commercial clearance claimed |

**Data statement.** Every corpus and tool used here is restricted to non-commercial academic research under
CC BY-NC-SA 4.0 and GNU GPL terms. Any commercial deployment requires independent re-annotation or direct
LDC licensing. **PDFs and models are distributed under the most restrictive licence in the chain.**

Note: REV5's phrase *"published under open academic research license"* is not a licence. Each term is named
individually above.

---

## 8. Appendix — verified measurements and their provenance

| Measurement | Value | Script |
|---|---|---|
| QAC segments / stems / roots | 128,219 / 77,915 / **1,642** | `inspect_qac.py` |
| QAC hapax roots / quadriliteral | 395 (24%) / **40 (2.4%)** | `inspect_qac.py`, `list_quadriradical.py` |
| PADT sentences / tokens | 7,664 / 282,384 | `count_treebanks.py` |
| PADT distinct surfaces / **roots** | 21,516 / **2,884** | `count_treebanks.py` |
| PADT root / case / Vform coverage | 86.0% / 52.0% / 100% | `count_treebanks.py` |
| NYUAD sentences / tokens / `Root=` | 19,738 / 738,889 / **0%** | `count_treebanks.py` |
| EQTB shape | 139,376 data rows × 51 cols, no wazān column | **manual — no script reads EQTB (`EVIDENCE_LOG.md` B18); earlier tag to `count_treebanks.py` was wrong** |
| CALIMA usable root / `#` / `NTWS` | **41.3%** / 31.3% / 27.4% | `test_round4.py` |
| Gold-dict recovery, HELD-OUT (coverage / correctness) | **91.7%** / **99.8%** of recovered (92.5% / 99.7% with proclitic fallback) | `reconcile.py` |
| PADT `Root=` tokens with a USABLE root | **96,671 / 192,991 = 50.1%** | `reconcile.py` |
| CALIMA clean∩unusable surface overlap | **0** | `test_round4.py` |
| `cas` distribution | na 36.6 · g 33.0 · u 15.7 · a 9.2 · n 5.5 (%) | `test_proposal_claims.py` |
| Renderer accuracy (digit-in-place) | **94.3%** at **30.0%** token coverage | `fix_renderer.py` — **superseded rev. 13**: the 94.3% is agreement with CALIMA's own `diac` (a consistency check); re-measured **92.4%** on the rule route, **89–93% skeleton**, **coverage 30.0% → 35.3%** | `renderer.py --measure` |
| Non-projective arcs (PADT/NYUAD) | 0.40% / 0.02% | `measure_decoder_requirements.py` |
| Max right-arity | 28 / 105 | `measure_decoder_requirements.py` |
| `(root × wazān)` fill rate | 0.97% — **sample-scale, not corpus-scale** | `check_solving_claims.py` |
| Per-step bits (baseline / treatment) | 14.97 / 27.16 | `check_solving_claims.py` |
| arramooz roots / templates | 7,650 / **72** (34 skeletons) | `check_arramooz.py` |
| Wazān well-formed coverage | 31.7% → **53.6%** | `measure_normalizer_gain.py` |
| CAMeL generation support | **none** (`GeneratorError`) | `audit_renderer.py` |

### 8.1 Known-unvalidated claims — do not report as results

1. ~~**Tashkeela coverage** (§3.1) — protocol specified, not yet measured.~~ **MEASURED rev. 10 (2026-10-09)**,
   full corpus, all 97 books (`src/measure_tashkeela_coverage.py`): **type coverage 5.7%** (6.9% folded),
   **token coverage 46.2%** (54.1% folded), **masked token fraction 53.8%** (45.9% folded). The type figure is
   **8× lower** than the token figure — precisely the divergence that made reporting one alone misleading.
   **Also corrects the corpus size:** 66,469,247 Arabic tokens + 8,292,742 non-Arabic units = 74.8M whitespace
   units, i.e. **66.5M tokens, not the ~98M this document previously assumed** (75M *words* × 1.3 was the
   error). At ~20 tokens/parameter the Chinchilla-optimal size is **~3.3M parameters**. See §5.4.
2. **Wazān label correctness** (§3.2) — no public gold standard exists; only well-formedness is measured.
   The 53.6% figure is coverage, not accuracy.
3. **`(root × wazān)` fill rate** (§4) — 0.97% comes from a ~6k-token sample covering 390 roots. The
   lexicon denominator is arramooz's **7,650** (the retired `≈6,500` is unsourced — see §2.1(c)); the
   corpus-scale ratio will be higher. Re-measure before quoting.
4. ~~**Renderer token coverage post-reconciliation** (§6)~~ — **MEASURED rev. 13** (`EVIDENCE_LOG.md` §2m):
   **30.0% → 35.3%** (hybrid route). It rises far less than anticipated, and **not because roots are missing**:
   reconciliation supplies a root for 26.9% of tokens, but rendering coverage barely moves because a supplied
   root often **disagrees in arity with the pattern's digit set**. The binding constraint is **pattern–root arity
   agreement**, and the 64.7% residual is 2,550 `no_root` + 39 `digit_set_incomplete`. Also re-measured, and it
   changes how the old pair must be read: the **94.3% was agreement with CALIMA's own `diac`** (a consistency
   check, reproduced at 92.4%), **not gold accuracy** — and **PADT's `FORM` is undiacritized**, so it cannot
   carry the shared final-surface metric at all. Skeleton match is **89–93%**; gold-vocalized evaluation must
   use EQTB's `uthmani_token`.
5. **The `الاشتقاق الأكبر` effect** (§2.1) — now an ablation, not a claim.
6. **arramooz `wazn` coverage** — blank on many rows; measure before relying on it.
7. ~~**Proclitic stripping in the Head 3 label** (§3.2) — specified, **not implemented**.~~ **IMPLEMENTED rev. 9
   (2026-10-09).** The label no longer carries the proclitic, and the *enclitic* edge was stripped with it.
   **The stated method was wrong and is corrected here:** `prc0`–`prc3` are **labels** (`Al_det`, `wa_conj`,
   `bi_prep`) carrying no letters, and `prc0` is the **innermost** clitic — so "alignment against prc0–prc3" is
   not implementable. The surfaces come from **`d3tok`** (`+_` after a proclitic, `_+` before an enclitic).
   Coverage moves 53.6% → **53.9%** on 5,062 lex-backed PADT tokens, with the composition explained in
   `EVIDENCE_LOG.md` §2i. The remaining entanglement is the enclitic (0.4% of tokens).
   **Also fixed there:** `expand_geminate` fired on any shadda and corrupted templatic ones
   (`الطُّلّاب` → `1ُ23ا3`); it is now gated on C2 == C3.
8. **The permutation effect** (§2.1) — 718 pairs / 53.1% of QAC roots is a *lexicon* measurement. Whether a
   position-free embedding term helps is an open ablation.
9. ~~**Reconciler transfer to Tashkeela**~~ — **MEASURED rev. 10.** The 91.7%/92.5% recovery is **PADT→PADT**
   (same domain, same annotation conventions) and does **not** transfer at that rate: a dictionary of 41,038
   keys (13,255 PADT surfaces + 27,783 arramooz) covers **46.2% of Tashkeela tokens** (54.1% with alef/hamza
   folding), leaving **53.8% masked** for Head 2. The prediction in this item was right, and the number is now
   known rather than assumed. Rule-of-thumb for the paper: **silver root supervision is ~46%, not ~92%.**
10. **Four-digit (quadriliteral) Head-3 supervision does not exist in silver.** Measured (`EVIDENCE_LOG.md` §2i,
    Finding D): for `وَسْوَسَ` the raw analyser offers 43 candidates of which exactly **1** carries digit `4`
    (`root=#.س.#.س`, `pattern=وَ2ْوَ4َ`), and the **MLE disambiguator never selects it** — it returns
    `root=س.#.س`, `pattern=وَ1َوِ3َ` (`prc2=wa_sub`). Undiacritized `ووس` yields **0** candidates and falls back
    to `backoff`. So the 4-slot target space is required by the gold sources (arramooz's 72 awzān, the 40
    quadriliteral Quranic roots) but is **not reachable from CALIMA silver**. Two consequences are binding on
    the pipeline: (a) **mask Head-3 loss to zero** wherever CALIMA emits `backoff`, `#`-only or an ambiguous
    split parse, rather than training on the MLE's substitute reading; (b) report this as a **limitation of
    statistical Arabic morphological taggers** — "the MLE disambiguator systematically misclassifies
    quadriliteral verbs with initial weak consonants as proclitic conjunctions, driving silver quadriliteral
    template coverage to near-zero" — and never as a property of this architecture. Secondary note: the
    analysis is also **input-vocalization sensitive**, so an undiacritized feed adds a second error source.
11. ~~**The CALIMA-vs-human ceiling** (§5.3 item 3)~~ — **MEASURED rev. 11** (`EVIDENCE_LOG.md` §2k). The ceiling is
    **case macro-F1 0.459** (EQTB, n=1,176; majority-`GEN` baseline 0.333) and **root accuracy 0.451 / 0.444**
    (QAC n=8,000 / EQTB n=4,401 — two independent human corpora agreeing to 0.007). Per root class, CALIMA
    agrees at **0.91 / 0.90 (sound)**, 0.77/0.71 (doubled), 0.82/0.63 (quadriliteral) and **0.000 for
    assimilated, hollow and defective** — because it *abstains* (`#`/`NTWS`), which the harness scores as a
    miss. State it as "no usable root supplied", not "wrong". **The treatment distils CALIMA, so these are
    ceilings, not targets.** Two related data corrections are binding: **UD Arabic-NYUAD is FORM-redacted**
    (0 Arabic characters) and therefore cannot carry a surface metric or a ceiling, and **EQTB's `root_ar` is
    only 35.9% real** (`nominal_case` 22.9%; `depend_rel` 100%) — non-empty is not coverage.

### 8.2 Corrections applied in REV6.1 (2026-10-09)

Three provenance defects, all found by **re-executing the cited scripts** rather than reading them.

**C1 — the recovery figure was degenerate and in-sample.** §3.1 (and EVIDENCE_LOG §2d) reported **96.4% /
99.8%** recovery, tagged to `src/test_round4.py`. Re-executing that script printed `distinct lexemes
needed: 1`, 0.0% for the hand-written dictionary and "100.0%" for the derived one. Root cause: CALIMA's
analysis dict exposes **`lex`**, not `lemma`; the script read `a.get("lemma") or ""`, so every row keyed on
the empty string and a one-entry table appeared to resolve everything. This is the project's own catalogued
silent-no-op failure mode, sitting inside its own provenance table. The script is fixed (reads `lex`, with a
guard) and now reproduces the values the earlier prose reported as correct: **13.4%** for the hand-written
dictionary, **0.8%** for the CALIMA-derived one, and a clean∩unusable lexeme overlap of **2** (≈ 0).

**C2 — the replacement is held-out and measures correctness, not just coverage.** The reconciler is now a
module (`src/reconcile.py`) with an acceptance test that builds the dictionary from **PADT train** and
probes **PADT dev + test**. Results in §3.1: 91.7% coverage (92.5% with proclitic fallback), 99.8% of
recovered roots correct. The earlier figure also had no accuracy component — "the dictionary answered" was
never distinguished from "the dictionary answered correctly".

**C3 — PADT's usable root supervision is half the quoted figure.** Of 192,991 `Root=`-bearing train tokens,
only **96,671 (50.1%)** carry a usable root. Root supervision for Head 2 should be planned at ~1.1M tokens
across all splits, not ~1.3M, and per-source masking matters more than §4 implies.

**Also corrected:** the PADT root transliteration is now mapped (was `B5`, "not started"). Units `.h .s .d
^s _h ^g` are digraphs, spaces are radical separators, and `O`/`V` occur only inside the `OOV` sentinel. The
table agreed with CALIMA's Arabic root at 100% on every unambiguous unit over 2,046 aligned token pairs
(`src/derive_padt_translit.py`).
