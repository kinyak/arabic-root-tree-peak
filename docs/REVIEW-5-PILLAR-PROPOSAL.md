# Review — the "5-pillar / ≥90% end-to-end" proposal, adjudicated against measurement

**Status:** external proposal reviewed 2026-10-11. Every headline claim re-derived against this
repository's own artifacts. Two new probes were written to test the load-bearing claims
(`tools/case_from_deprel_probe.py`, `tools/wazan_notation_probe.py`).

**Verdict in one line.** The proposal's *diagnosis* is substantially right and its central
architectural instinct — stop predicting case/wazān as unconditioned local labels, and use
surface structure and syntax as constraints — matches the direction this project's own backlog
already points. Its *numbers* are not: four of its five pillars target levers that are already
implemented, already measured, or already refuted, and its end-to-end arithmetic cannot produce the
number it claims even if every one of its own targets were met.

---

## 1. What the proposal gets right (credit first)

1. **The cascade is real.** Nothing downstream can be better than the renderer, and the renderer is
   the measured binding constraint (§2s.8d). Correct, and independently established here.
2. **Case is not a local labelling task.** It is government and agreement (ʿāmil/maʿmūl). The
   measurement below confirms syntax *is* informative: adding `deprel` to `upos` more than doubles
   case macro-F1 (0.3675 → **0.7331** on PADT, oracle settings). The instinct is sound.
3. **Surface constraints must prune the template space.** Correct instinct; the repo already
   applies it in the beamed decode (`*_root_whole_beamed` beats `*_root_whole` in every cell).
4. **Closed-class words need a structural gate, not a guess.** Already implemented, and stricter
   than the proposal's version.
5. **The proposal's five component readings are mostly accurate.** Re-derived from
   `dist/runs/v26-rescore/results/results.json`: root 91.1% = `silver/in_domain_root_whole`
   0.9115 ✓; 54.4% = `silver/padt_dev_root_whole` 0.5435 ✓; wazān 22.1% =
   `silver/gold_wazan_norm` 0.2206 ✓; case 47.1% = `silver/gold_case_macro_f1` 0.4707 ✓. These are
   **silver-arm** figures on the stated sets, and they are quoted correctly.

## 2. What it gets wrong

### 2.1 The end-to-end arithmetic does not compose — three separate errors

**(a) It multiplies the accuracies of disjoint subsets of the same event.** "In-Domain Root 91.1%"
and "OOV Root Recovery 0.000%" are not two independent stages; they are two *slices of the same
per-token root event*. Multiplying them is meaningless — a token is either in-vocabulary or not,
never both. (17.4% of human-gold tokens are OOV: `context_coverage.gold_context_oov_rate` = 0.1739.)

**(b) The renderer is missing from the bound entirely.** The proposal's product has four factors
(root × wazān × case × clitics) and no renderer term — yet the renderer is measurably the ceiling
on the whole pipeline: with the annotator's *own correct* triple, the renderer reproduces the human
surface **42.8%** of the time, and with the realistic CALIMA triple the **yield is 4.3%**
(`src/final_surface_ceiling.py`, 300 gold rows, §2s.8d). A bound that omits the term which
actually binds is not a bound.

**(c) Its own targets do not reach its own goal.** Taking the proposal's target column at face
value (root 96.5%, OOV 82–88%, wazān 95–97%, case 92–94%, renderer 98.5%) and multiplying the
midpoints — the only way its own reasoning could be applied —

```
0.965 × 0.85 × 0.96 × 0.93 × 0.985  ≈  0.72
```

gives **~72%**, not ≥90%. The `0.975⁴ ≈ 90.3%` line is arithmetically true and plan-irrelevant: it
states the *requirement* (every factor at 97.5%) that the proposal's own component targets then
miss (case 93% mid, OOV 85% mid).

### 2.2 Pillar 1 — "case becomes near-deterministic from deprel (>97%), target 92–94% macro-F1"

Measured, on gold trees, with **gold** `upos` **and gold** `deprel` — i.e. the oracle ceiling for
this rule, which a trained parser can only fall below
(`tools/case_from_deprel_probe.py`):

| setting | accuracy | macro-F1 |
|---|---|---|
| PADT: P(Case \| upos, deprel), train→dev | 0.8324 | **0.7331** |
| NYUAD: same | 0.7834 | **0.6892** |
| PADT: P(Case \| upos) alone | 0.6917 | 0.3675 |
| PADT: gold deprel corrupted at 20% | 0.7516 | 0.6390 |
| PADT → NYUAD transfer | 0.5532 | 0.5364 |
| NYUAD → PADT transfer | 0.3647 | 0.3565 |

So:

- **The ceiling is 0.733 macro-F1, not 0.92–0.94.** The claimed target is above the oracle for the
  claimed mechanism. Parser error moves it down, not up (0.733 → 0.639 at 20% noise).
- **Where does ">97%" come from?** It is true on a *subset*: restricting to `(upos, deprel)` pairs
  that are ≥95% consistent in training gives accuracy **0.9782** — at **16.2% coverage** (NYUAD:
  0.9730 at 25.8%). The proposal generalised a selective-subset figure to the whole task. This is
  the single most consequential error in the document.
- **Cross-treebank transfer is poor** (0.55 / 0.36 accuracy), so "pool NYUAD + PADT + EQTB" is not
  free: the treebanks' case conventions differ measurably.
- **But the direction is worth money.** Syntax buys **+0.37 macro-F1 over POS alone** and **+0.26
  over the model's current 0.4707**. A syntax-informed case head with a realistic target of
  **~0.70–0.73 macro-F1** is a genuine, large, achievable win. It is Pillar 1's *number* that is
  wrong, not its *idea*.

And the 47.1% itself is a **ruler** problem, not only a model problem: the human gold's case
reference sits at a CALIMA-vs-human ceiling of **0.459** (`ceilings.case_macro_f1`), and the model
is already at/above it (0.4707; §2z records the closest approach yet, 0.454 vs 0.459). That is
exactly why `ACTIVE_BACKLOG` item 1 (the independent blind benchmark) gates everything: until the
reference is human-adjudicated, "case accuracy" is measuring agreement with a noisy teacher.

### 2.3 Pillar 2 — "character CNN trunk to lift OOV from 0.000% to 82–88%"

**Already shipped, in round 20, and already measured.** `src/model_arms.py` carries the character
vocabulary and encoder (v12: char embedding → multi-kernel Conv1d k=3/5/7 → max-pool → Linear,
added to the word+position embedding in **both** arms, so parity is structural). §2z's result:

| arm | in-vocab (n=137) v11 → v13 | OOV (n=141) v11 → v13 |
|---|---|---|
| silver-treatment | 0.496 → 0.569 | **0.000 → 0.099** |
| silver-baseline | 0.384 → 0.504 | **0.000 → 0.071** |
| gold-treatment | 0.192 → 0.372 | 0.002 → 0.121 |
| gold-baseline | 0.165 → 0.460 | 0.000 → **0.241** |

The cliff moved (0.000 → 7–24%), which was the goal — and **not to 82–88%**. Worse for the
proposal's framing: the character encoder raised the *baseline* more than the treatment on root,
so the v11 treatment advantage **did not replicate** (three root cells flipped). "Add a char CNN"
is not an open lever here; it is a completed, documented experiment with a negative result on the
arm it was supposed to help.

### 2.4 Pillar 3 — "collapse a 70-class wazān space to ≤3 and lift accuracy to 95–97%"

Three problems, all measured.

**(a) The label space is not 70 classes.** `context_coverage.vocabulary.sizes` records **wazān =
6,633** types in the current run (3,248 in v13). The proposal is off by ~two orders of magnitude.

**(b) The 22.1% is dominated by notation, not by morphological ignorance.** The project already
measures both levels, and they disagree violently:

| key (silver arm, human gold) | value |
|---|---|
| `gold_wazan_raw` | 0.1115 |
| `gold_wazan_norm` | 0.2206 |
| **`gold_wazan_slots`** | **0.9880** |

The model gets **98.8% of radical slots right** and 22.1% of *written strings*. `tools/wazan_notation_probe.py`
shows why, on the only human wazān annotation that exists (278 patterns, `full-FILLED-by-Rendi.csv`):

| canonicalisation | distinct types |
|---|---|
| raw, as written | **119** |
| trailing case vowel stripped | 110 |
| all diacritics stripped | **65** |
| digit+letter skeleton | 65 |

and the collapse is the point: the structural skeleton `123` alone is written **13 different ways**
(`1َ2َ3`, `1َ2َ3َ`, `1َ2َّ3َ`, `1َ2ُ3`, `1َ2ِ3َ`, …); skeleton `123ة` has 8. **A raw-string metric
charges the model for choosing a different legal spelling of the same pattern.** Pruning a
already-beamed search space cannot fix that; a **canonical, adjudicated label space** can — which is
precisely what item 1's two-annotator benchmark produces.

**(c) Masking is aimed at a search space that is not the bottleneck.** The beamed variants already
exist (`gold_root_whole_beamed` > `gold_root_whole` in every cell), and wazān slot accuracy is
already 0.988. The proposal's own diagnostic ("the model is asked to guess … ignoring the physical
character length and consonants") is contradicted by the 0.988 slot figure.

### 2.5 Pillar 4 — "renderer 43.9% → 98.5% with Engine v4"

**43.9% does not exist in this repository** (repo-wide grep, excluding `.venv`: no hit). The real
ladder, all measured (`src/measure_renderer_gold.py`, `src/final_surface.py`, §2s.3/§2s.8):

| rung (278 gold triples) | count | rate |
|---|---|---|
| raw exact | 26 | 9.4% |
| NFC-normalised | 29 | **10.4%** |
| clitic-aware (some legal affix split) | **116** | **41.7%** |
| skeleton (consonants only) | 69 | 24.8% |
| ceiling: human's own triple, engine v2 | — | **42.8%** |
| yield with the realistic CALIMA triple | — | **4.3%** |

The proposal also **mislabels its own diagnosis**: "weak radical assimilation (10.4%)" is the
NFC-normalisation rung, not a weak-radical bucket. (Its "12.2% missing tanwīn" is right — that is
the nunation bucket, 34 rows.)

The direction of Pillar 4 is nevertheless **convergent with this repo's own measured next step**
(§2s.9 puts renderer accuracy first, as the binding constraint), and the rule families named
(iʿlāl, ibdāl, hamza seating, tanwīn) match §2s.7. Two cautions the proposal's sketch ignores:

- **Order and position matter, and naive deletion regresses.** §2s.8e measured v2 creating **19 new
  `weak_radical_missing`** errors: a weak radical must be **re-realized** (delete / mater / hamza
  seat / final ء / madda) *by position and by what the template already supplies*, never simply
  dropped. The proposal's pseudocode drops first and seats hamza afterwards.
- **Do not rewrite from scratch.** `render_rules.py` is a regression-tested implementation of the
  plan's Steps 1–2 with measured deltas; replacing it discards the tests that found the regression.
  Also note the first fix is a **metric definition** (`final_surface` = the single home; the clitic
  plane was understated by a decomposition bug — 32.0% → 41.7% after the fix).

### 2.6 Pillar 5 — "τ* = 0.65, Tier-1 at 100% precision/recall"

- **A hand-set threshold contradicts a pre-registered rule.** `ACTIVE_BACKLOG` item 2: *"(a) no
  threshold may be hand-entered"* and thresholds are fitted on the frozen calibration split. A
  fixed τ = 0.65 is exactly the artefact the project forbade.
- **Tier-1 already exists and is measured.** §2al: the shipped "0/278" false-abstention figure was a
  300-row artefact; the real PADT rate was **1.285%**, repaired to **0.086%**, against a gate budget
  of `MAX_FALSE_ABSTENTION_RATE = 0.0025`. "100% precision/recall" is unsourced.
- The *architecture* (structural gate → calibrated confidence → hierarchical fallback) is already
  this project's design, including the rule that a structural abstention is **final** and never
  re-scored as confidence.

### 2.7 Step 2's data plan is licence-blocked and double-counts

| proposal says | repository says (`RESOURCES.md` §1.1–§1.4) |
|---|---|
| "~1.15M gold tokens with full syntactic dependency graphs: NYUAD + PADT + EQTB/QAC" | QAC carries **no dependency graph** (morphology only); EQTB is **derived from the same Leeds QAC** — *"⚠️ Do not double-count"* |
| NYUAD for root supervision (implied by "retrain Heads") | NYUAD and PUD carry **0% `Root=`**; only PADT does (86%). *"merging all three drops combined root coverage to **23.3%**"* — root supervision must be masked per-source, never pooled |
| "Train exclusively on gold corpus" as the product path | PADT **CC BY-NC-SA 3.0**, NYUAD **CC BY-NC-SA / NOASSERTION**, QAC **GPLv3** — all flagged **[LICENSE-RISK]** for a closed app; arramooz's licence is still **[FIXME]** |

So the plan is legitimate as a *research* route with per-source masking, and cannot be the
*basis of a product claim* — item 10: *"a number whose licence forbids distribution is not a
product number."*

## 3. The numbers, re-derived side by side

| quantity | proposal | measured (this repo) | source |
|---|---|---|---|
| in-domain whole-root (silver) | 91.1% | **0.9115** ✓ | v26-rescore |
| PADT-dev whole-root (silver) | 54.4% | **0.5435** ✓ | v26-rescore |
| wazān on human gold | 22.1% | **0.2206** ✓ (slots: **0.9880**) | v26-rescore |
| case macro-F1 on human gold | 47.1% | **0.4707** ✓ (ceiling 0.459) | v26-rescore |
| OOV root | 0.000% | **0.071–0.241** — fixed in v12 | §2z |
| renderer on human triples | 43.9% | **41.7%** clitic-aware / 42.8% ceiling | §2s.3, §2s.8 |
| end-to-end surface | ≈1.0% | no E2E key exists; ceiling **42.8%**, realistic yield **4.3%** | §2s.8d |
| wazān classes | 70 | **6,633** (v26) / 3,248 (v13) | `context_coverage` |
| root trie | 6,500 roots | PADT-train has **1,052** distinct `Root=`; QAC 1,642 | `RESOURCES.md` |
| "≥90% E2E" from its own targets | ≥90% | **≈72%** | arithmetic above |

## 4. The solution I propose instead

Ordered by (measured value ÷ cost), CPU-first, each step with its threshold written **before** it
runs. Nothing here needs a GPU until step 4, and step 0 gates everything.

**Step 0 — the benchmark is still the yardstick (existing item 1, unchanged).**
No accuracy claim of any kind is meaningful while the case reference is CALIMA-derived (ceiling
0.459) and wazān has no adjudicated gold. The blind 1,000-row sheet is built, frozen and ready;
recruitment is the only blocker. **The proposal's most valuable contribution to this project would
be annotators, not architecture.**

**Step 1 — fix the metric before the model (cheap, changes every number).**
Adopt a **canonical wazān label space** and report wazān as a pair: `raw` **and** `slots`, never one
alone. Measured basis: 119 raw → 65 canonical forms on 278 human rows, with one skeleton written 13
ways; model slot accuracy already 0.988. Threshold: the canonicalisation must be defined *from the
adjudicated benchmark* (item 1), not invented now.

**Step 2 — the renderer is the binding constraint; finish it with regression tests (existing item 8/9).**
Continue `render_rules.py` along the measured order (§2s.7/§2s.9): weak-radical **re-realization by
position** (not deletion — the regression is measured), then nunation, then enclitic/ta-marbuta.
Thresholds: clitic-aware accuracy on the 278 gold triples must rise **41.7% → ≥55%** before any
model-side work is claimed as an E2E improvement; the `weak_radical_missing` bucket must **not
grow** (it grew 1→12 and 0→19 in the two naive attempts).

**Step 3 — case from syntax, with an honest target (new; the proposal's one real idea).**
An auxiliary **dependency-relation head** whose output feeds case, with the deterministic mapping
applied only where it is reliable — measured here as the **16.2%-coverage subset at 0.9782
accuracy**. Report case macro-F1 against an adjudicated reference. Threshold: **> 0.62 macro-F1**
on PADT-dev (above the 0.4707 baseline and the 0.459 CALIMA ceiling, below the measured 0.7331
oracle), with the parser's own deprel accuracy reported beside it. Train with **per-source masked**
supervision (never pooled — pooling costs root coverage, 23.3%).

**Step 4 — only then revisit architecture (existing items 4/5/6/7).**
The char encoder is done; the `max_vocab` lever is pre-registered and CPU-measurable; a
licence-audited pretrained teacher (item 7) is the correct way to find out whether the limit is
data, architecture or objective. **No GPU run without a written threshold and a measured CPU part.**

**Explicitly not doing, and why:** no hand-set abstention threshold (item 2 forbids it); no
"replace `render_rules.py`" rewrite (it would discard the regression tests that found the weak-radical
regression); no product claims derived from non-commercial treebanks; no E2E target quoted from a
product of marginal accuracies.

## 5. Reproduce

```
python tools/case_from_deprel_probe.py      # the Pillar 1 ceiling: 0.7331 macro-F1 (oracle)
python tools/wazan_notation_probe.py        # the Pillar 3 notation collapse: 119 -> 65
python src/final_surface_ceiling.py         # the E2E ceiling: 42.8% human triple / 4.3% CALIMA
python src/diagnose_gold_checkpoint.py --ckpt dist/drive-preflight/gold-baseline-s20261009.pt
```

CPU only. No model was trained and no GPU time was spent for this review.
