# REVIEW — the "fix the renderer / data / model" roadmap, adjudicated against the artifacts

**Received:** 2026-10-12, as a pasted document ("how to fix the issue or current problem and improve").
**Reviewed:** 2026-10-12, on rev `d76601d` + the working tree.
**Status of the document:** it is a **plan, not evidence**. Nothing in it counts as a measurement until a
dated section of `EVIDENCE_LOG.md` records the run that produced it. This review's job is to say, per claim,
which of three things it is:

1. **Corroborated** — already measured here; the section that paid for it is cited.
2. **New** — accepted; goes into `ACTIVE_BACKLOG.md` as an item (or into an existing item).
3. **Corrected** — plausible but overreaching, or resting on a *superseded* number, or on a number that
   measures something other than what the sentence says it measures.

Precedent: `docs/REVIEW-5-PILLAR-PROPOSAL.md` (round 27) — same exercise, same rules.

---

## 0. Method, and the instrument that matters

Every figure below was re-derived on this machine, and each is pinned to the artifact it came from. The
project has ≥8 near-identical results artifacts (`dist/ablate_minstem.log`, `dist/measure_arity.log`,
`dist/incoming/`, `dist/kaggle-output/`, `dist/runs/*`); the same metric name lives in all of them and only
one is current, so quoting the wrong one silently changes the whole review.

Two instruments exist and they are **not interchangeable**:

| instrument | what it is | can it carry a fidelity claim? |
|---|---|---|
| `dist/ablate_minstem.log`, `dist/measure_arity.log` (2026-10-10) | `renderer.py --measure` on **PADT test, 4,000 tokens**; reference column is PADT `FORM`, which the log itself states is **undiacritized** | **No.** The log's own words: *"PADT cannot carry the shared final-surface metric. It must be measured on a VOCALIZED gold corpus"* |
| `tools/renderer_bench_audit.py` (**new, this review**) | the renderer against **`data/annotation/bench-gold.jsonl`** — the frozen item-1 benchmark: 1000 rows, two independent annotators, per-row adjudication, 650 test / 350 calibration | **Yes.** The reference is a human vocalized token; the metric is `final_surface.score_final_surface` (clitic-aware `stem_match`), the shared metric |

Command for the second, and the only one needed to reproduce §4:

```bash
python tools/renderer_bench_audit.py --engine v3 --json dist/audit-2026-10-12/bench-v3.json
```

> **Note on paths.** `dist/` is gitignored (the repo's convention for measurement logs), so every
> `dist/audit-2026-10-12/…` reference in this review is a **local, untracked** artifact. The commands
> beside each figure are what travels: re-run them and the numbers come back.

---

## 1. Provenance of every number the plan quotes

| plan's figure | where it actually comes from | what it actually measures | usable as a baseline? |
|---|---|---|---|
| "hamza **53.5%**", "defective **62.0%**", "hollow **44.2%**" | `dist/ablate_minstem.log` L43/L117 (`MIN_STEM=2` and `=3` print the same table), also duplicated in `dist/measure_arity.log` | *"hybrid accuracy by root class (gold radicals, not translit)"* — see §1.1 | **No** — wrong corpus, wrong reference, and half of it is table memorisation |
| "44–62%" as "weak radical accuracy" | the three rows above | three different root classes, not "weak radicals" | **No** |
| "content coverage **93.4%**" | `docs/CLOSED-CLASS-INVENTORY.md` §4.7; `EVIDENCE_LOG.md` §2x.8 | 2,337 / 2,502 **content words** on the PADT-test prefix | yes, but it is a *Tier-1-only* number with a stated denominator |
| "**148** unseen content words" | nearest real artifact says **149** — `EVIDENCE_LOG.md` §2x.8 ("content words, **no usable root**: 149 = 3.7%") | root **supply** failures on PADT test | directionally yes; the count is 149 here |
| "silver token coverage **46.2%**" | `EVIDENCE_LOG.md` L1093 / `SPEC-REV6.md` §8.1 | **dictionary-key coverage of Tashkeela** (30,728,983 / 66,469,247) plus the type figure **5.7%** | **No** — it is not a supervision figure (§3.2) |
| "case macro-F1 flat on silver (~**0.73**)" | `EVIDENCE_LOG.md` §2y (L2950: 0.7357 ± 0.0116 treat vs 0.7018 ± 0.0121 base) | silver-target in-domain/dev case macro-F1 | **Yes** — corroborated |
| "Root and Wazān separated cleanly (+5.0 pp, +4.0 pp)" | consistent with §2y/§2ab/§2ac arm tables | silver-target per-head deltas | yes, but see §3.3: **+5.0 pp did not survive the better decoder** (§2ab) |
| "Case lagged behind the baseline on human gold" | `EVIDENCE_LOG.md` §2y L2956 (0.3941 ± 0.0309 vs 0.3684 ± 0.0142) | human-gold case macro-F1, CALIMA-derived reference | yes — and that is a **ruler** problem, item 1 |
| "13.8% case supervision" | **no artifact found** | — | **unverified** |
| "34 gold nunation failures" | `EVIDENCE_LOG.md` §2s.9 (`tanwin` 33 = 32 `diacritic_only`-adjacent + ACC `ً+ا` 12 … on the **300-row** gold); `src/renderer.py` `apply_case` docstring says **44** tanwin rows | old gold, old ruler | **stale** — on the frozen benchmark it is **204 rows** (§4.3) |
| "300 rows, stratified 40% on weak/geminates" | `full-annotation-meta.json` (`strati_frac: 0.4`) | there is **no strata column** in `full-annotation-sheet.csv` — §2t.1 measured that this claim is not reproducible from any artifact | **No** — §2t.1 |
| "148 rootless content words → Route 3" | policy already decided: `docs/CLOSED-CLASS-INVENTORY.md` §4.6 + `EVIDENCE_LOG.md` §2x.8, implemented as **route 4** (§4.8) | — | already shipped (§3.1) |
| "`full-annotation-sheet.csv` as the official Ground-Truth" | superseded: §2az (2026-10-12) | the ruler is now the 1000-row adjudicated benchmark | **No** — item 1 |

### 1.1 The three per-class numbers are not a renderer-fidelity ladder

`src/renderer.py:575` prints that table under the label *"hybrid accuracy by root class"*, and the column is
`got == t["form"]` — equality with **PADT's undiacritized `FORM`** — for every token on which the **hybrid**
route fired, **whichever branch it took**. The route table immediately above it reports the two branches
separately:

| branch | coverage | `= gold` (vs undiacritized FORM) |
|---|---|---|
| `3a_hybrid_table` | 34.5% | **90.6%** — it returns the memorised PADT FORM *verbatim*; the log itself calls this "a copy" |
| `3b_hybrid_rule` | 40.2% | **0.0%** (expected: a vocalized render cannot match an undiacritized reference) |

The per-class table merges them. Arithmetic from the log's own columns, for hollow:
`207 / 468 = 44.2%`, and a mixture of one branch at 90.6% and one at 0.0% reproducing 44.2% requires
**≈ 48.8% of those hollow tokens to have gone down the memorisation branch** (`0.906x = 0.442 ⇒ x ≈ 0.488`).

So "hollow 44.2%" is, to first order, *"in 44% of hollow tokens the table emitted the answer it had already
seen"* — and the same log reports **49.5% of test keys are in the table**. That is not a fidelity of the
deterministic renderer, and lifting it to 80% is not a rendering problem. The plan's central premise —
"the renderer is deterministic and modular; raising weak radical accuracy from 44–62% to ≥85% requires only
encoding the rules" — is built on these three numbers.

End-to-end re-derivation, run as part of this review:
`python src/renderer.py --measure --limit 4000`, log `dist/audit-2026-10-12/renderer_measure_4000.log`.
It **reproduces the plan's three figures exactly** — `hollow 468 rendered / 207 exact / 44.2%`,
`hamza 273 / 146 / 53.5%`, `defective 245 / 152 / 62.0%` — alongside the branch split that shows what they
are made of (`3a_hybrid_table` 90.6% `= gold` vs `3b_hybrid_rule` 0.0%). The numbers are quoted correctly;
the *reading* of them is the problem.

---

## 2. Corroborated

- **The renderer is the binding constraint on the paper's claim.** §2s.8d measured the treatment's end-to-end
  ceiling as the renderer: **42.8%** with a perfect (human) triple — **re-derived 2026-10-12 after the clitic
  plane became a renderer input: 45.7% (v2) / 50.7% (v3)** on the legacy gold, **47.6%** on the frozen ruler
  (§4.4, §2bd). The plan's Phase 1 is aimed at the right component. Agreed, and it is the strongest thing in
  the document.
- **Hamza roots are stored/written with a bare alif.** §2t.1: the annotator writes `اله`, `امر`, `احد`, `اهل`
  for hamza radicals, and `eval_harness.root_class` counts a bare alif as weak — so ~30 of the 35
  "assimilated" rows are really hamza-seat cases. Reproduced again on the frozen benchmark: `النَّاسِ`
  (root written `انس`) renders as **`أَانَسِ`** — the renderer prepends a hamza to a bare-alif root.
- **`apply_case` structurally cannot emit tanwīn.** Stated in the code and in §2s.9; the plan is right that
  this is a gap and not a search failure.
- **Nunation is a rule to write, not an input to invent.** §2s.5 tested and *disproved* the
  under-specification hypothesis for the clitic case; §2s.9 item 2 left the "is definiteness recoverable
  from the pattern?" question open. **Answered below (§4.3), in the plan's favour.**
- **Evaluation must not be CALIMA-mediated.** Standing constraint (A14/E1); repeated in `ACTIVE_BACKLOG.md`.
  The plan's "stop evaluating primarily against CALIMA (which is circular)" is the project's own rule.
- **The case head is flat and lagging.** §2y (§3 of this review, row 3).
- **Rootless content words are a supply problem, not a morphology problem.** §2x.8; the plan's diagnosis
  (سوريا، دمشق … are A‘jamī/Jāmid) is the same one the adjudicated benchmark already applies — the packet
  admits ABSTAIN for 6 foreign/loanword rows (§2az).

---

## 3. Corrected

### 3.1 The "148 rootless content words → pass-through" fix is already policy *and already shipped* — and the +5.9 pp it promises is a reclassification, not a gain

- Measured and already decided: §2x.8 (149 tokens = 3.7%), `CLOSED-CLASS-INVENTORY.md` §4.6 (*"one policy for
  both: pass the surface through, mark it, and exclude it from the root-tree claim"*), implemented as
  **route 4** and measured in §4.8 (**188 tokens = 4.7%** Tier-3 pass-through, excluded from the claim).
- The plan's arithmetic (`93.4% → 99.3%`) does reproduce as `(2337+148)/2502 = 99.32%` — and it is exactly the
  move the three-tier schema exists to prevent. §4.7 caveat 2: the bypass *"emits the reference surface
  itself, so any 'accuracy' printed for it would be a copy"* — its accuracy is `n/a` **by construction**.
- So: real coverage, real decision, **wrong label**. Report it as Tier 3 (source/supply), never folded into
  the root-tree coverage. "Coverage rise alone is explicitly not success" (`ACTIVE_BACKLOG.md` item 6).

### 3.2 The silver-dictionary expansion is a plausible **direction** with an unmeasured size, and it is argued with the wrong currency

First, in fairness: **46.2% is the project's own "token coverage"** — `EVIDENCE_LOG.md` L1093 /
`SPEC-REV6.md` §8.1 (G5): 30,728,983 / 66,469,247 tokens of Tashkeela whose exact surface key is in the
dictionary and therefore receive root supervision, against a **type** figure of **5.7%** (26,487 / 460,667).
So "silver token coverage 46.2%" is a fair paraphrase, not a misread. Three things are still wrong:

- **"≥ 75%" is a projection, and the merged dictionary already exists as a measurable object.** The group
  measured coverage by frequency band, and the misses are concentrated in the tail where no dictionary
  reaches: hapax **2.7%** covered (150,168 types), 2–4 **4.3%**, 5–99 **11.3%**, 100+ **56.8%**. Reaching 75%
  means covering ≈19M more tokens, essentially by closing the 100+ band (27.0M uncovered). That is *possible*
  and worth testing — but it is a **measurement**, and the instrument is already in the tree:
  `python src/measure_tashkeela_coverage.py` (full corpus, ~814 s). Believe the number after it runs, not
  before.
- **Coverage is not a token budget.** The plan says the expansion "doubl[es] the Chinchilla-optimal token
  pool". The corpus is **fixed** at 66,469,247 tokens — the project's own correction (L1111-1114: the
  "75M words ≈ 98M tokens" estimate was ~1.5× high, so Chinchilla-optimal is ~3.3M parameters, not ~5M).
  Supervising more of a fixed corpus does not enlarge it. And the constraint that was actually measured is
  **sampling, not dictionary size**: §2ae found the silver "120k training set" is **one book**, and at the
  *same token budget* a spread sample covers **59× more OOV words** — the fix for which already exists
  (`data/out/spread-B-2m`, item 6).
- **Licence.** PADT/NYUAD are CC BY-NC-SA and QAC is GPLv3, all already `[LICENSE-RISK]` (`RESOURCES.md`
  §1.4). Merging a **modern extracted** index of a classical dictionary (al-Qāmūs / Lisān) introduces a new
  source of unstated licence status into a dictionary the model would depend on. Item 3 requires a
  **per-source licence audit**; this merge must pass it before it is load-bearing.

Plus the standing rule: **"a coverage rise alone is explicitly not success"** (item 6), and "a larger word
vocabulary does not solve morphology" is already on the "explicitly NOT doing" list (§2ad, measured).

### 3.3 Two of the three model changes are already implemented, already measured, or aimed at an unmeasured defect

- **Arity conditioning (2-D arity embedding + additive `<pad>` mask on slot 4).** The mechanism exists:
  `src/model_arms.py:188-195` trains root slot 4 as `<pad>` *so that arity is learned end-to-end*, and the
  smoke test asserts it — *"root targets: 238 triliteral (slot4=`<pad>`), 4 quadriliteral, 1533 unsupervised;
  violations **0+0** (want 0+0)"*. The defect the plan wants to fix was audited: §2x.9, *"the 18 failures
  audited — **zero** are arity contradictions"*; `dist/audit_arity3.log` reconciles to the same 18. And §2ac
  (the conditioning-OFF arm at n = 3) found *"the root result is NOT the conditioning's"* — conditioning is
  not the lever. **Net: no measured defect to fix; the proposal adds capacity with no target.**
- **Case loss re-weighting "λ_case = 1.0 → 2.0–2.5".** There is **no λ_case in the tree** (`grep` over
  `src/model_arms.py`, `src/train.py`: no case-loss weight, no class-weighted CE). "Increase it from 1.0"
  mis-describes the code. The real correction is upstream: the human-gold case reference is CALIMA-derived
  (§2y, §2au) with a **CALIMA-vs-human ceiling of 0.459**, while the *human* ceiling on the new benchmark is
  **98.50% agreement, κ = 0.9784** (§2az). Re-weighting a loss optimises the old ruler; item 1 exists because
  the ruler is the problem. And case is governed by syntax: the measured oracle for the syntax route is
  **0.7331 macro-F1** (item 10), so no local case head can be pushed past its own ceiling by weighting.
- **"+5.0 pp root / +4.0 pp wazān separation"** — the plan quotes this as a standing result. §2ab (round 22,
  3 seeds) found **"the treatment's root edge does not survive the better decoder"**. Quote §2ab, not §2y.

### 3.4 Locking the 300-row sheet as the primary benchmark would regress the ruler

The principle ("stop evaluating against CALIMA") is the project's own; the remedy is backwards. The 300-row
sheet is what item 1 was created to replace: small, stratified toward weak/doubled surfaces, case reference
CALIMA-derived, and with a stratification claim that is **not reproducible from any artifact** (§2t.1:
no strata column; only `strati_frac: 0.4`). The frozen item-1 benchmark — 1000 rows, two independent
annotators, 178 disputed rows adjudicated with a written per-row rationale, 650/350 split, κ reported per
field — is now in the tree (§2az). The plan's Step 6 ("re-run the local CPU benchmark against the 300 human
gold rows") is superseded by §4 below, which does it against the 1000-row adjudicated gold.

### 3.5 Step 7 ("launch the full 43-minute Kaggle run") re-litigates a measured-negative choice, and breaks a standing constraint

- **Prong 2 (`<pad>` targets) has already trained and been measured.** §2x/§2y: *"Prong 2, recorded rather
  than glossed … R19f has now trained … Prong 2 is **slightly negative on all four cells, −2.5 to −4.4 pp on
  the gold arms**"*. Step 7 would spend GPU to re-measure a closed question.
- **Standing constraint:** *"Any GPU spend before its threshold is pre-registered and its CPU part is
  measured"* (`ACTIVE_BACKLOG.md`, "Explicitly NOT doing"). The CPU part of this plan's Phase 1 is exactly
  what §4 below now supplies.

---

## 4. New — measured on the frozen benchmark, this session

`tools/renderer_bench_audit.py` (new tool, this review). Coverage is ~100% **by construction** on the rows
that carry a usable triple (the human supplies root and pattern), so fidelity is the open question.

### 4.1 The renderer against the 1000-row adjudicated gold (first time ever measured)

> **Re-derived 2026-10-12 after the clitic plane became a renderer input (§4.4, `EVIDENCE_LOG.md` §2bd).**
> The stem-only numbers this table first carried — v1 40.9 · v2 44.4 · **v3 45.6**, split 47.1 — are still
> reproducible with `token=None`; they are superseded, not stale.

| engine | usable triples | fidelity (`stem_accuracy_of_covered`) | token exact | skeleton |
|---|---|---|---|---|
| v1 (digit-in-place) | 973 | **41.7%** | — | — |
| v2 (Steps 1–2, early commit) | 973 | **45.6%** | — | — |
| **v3 (weak re-realization, default)** | 973 | **47.6%** | 16.2% | 34.9% |

By root class, **coverage and fidelity as a pair** (v3):

| class | n | coverage | fidelity | skeleton |
|---|---|---|---|---|
| sound | 646 | 100% | **55.9%** | 41.2% |
| hollow | 100 | 100% | **24.0%** | 27.0% |
| defective | 84 | 100% | **29.8%** | 20.2% |
| doubled | 69 | 100% | **40.6%** | 26.1% |
| assimilated | 54 | 100% | **27.8%** | 9.3% |
| quadriliteral | 20 | 100% | **50.0%** | 35.0% |

Reporting split (`--split test`, the 650 rows): overall **49.3%**.

**A trade the log does not record (now superseded by the fix below):** at the stem-only baseline v2 beat v3
on **doubled** (36.2% vs 26.1%) while v3 won on defective (29.8% vs 11.9%) and assimilated (27.8% vs 24.1%).
v3 became the default before the benchmark existed — and the doubled gap turned out to be a *regression* in
v3, not a property of its rule (§4.4). After the geminate fix v3 leads on doubled (40.6% vs v2's 36.2%).

### 4.2 The residual is NOT dominated by weak radicals — it is dominated by nunation and diacritics

529 of 973 usable rows fail. Decomposition of those failures (v3):

| bucket | rows | % of failures | % of usable rows |
|---|---|---|---|
| `diacritic_only` | 159 | 31.2% | 16.3% |
| `tanwin_missing` | 149 | 29.2% | 15.3% |
| `tanwin_alif_acc` | 53 | 10.4% | 5.4% |
| `other` | 52 | 10.2% | 5.3% |
| `weak_or_hamza` | 52 | 10.2% | 5.3% |
| `hamza_seat` | 22 | 4.3% | 2.3% |
| `weak_radical_written` | 18 | 3.5% | 1.8% |
| `weak_radical_missing` | 5 | 1.0% | 0.5% |

*(Re-derived 2026-10-12 after the geminate fix and the clitic plane: 510 failures, not 529. `ta_marbuta` has
**left the table entirely** — that was the clitic plane's 9 rows. `other` fell 66 → 52 for the same reason.)*

**Nunation + diacritic-only = 361 rows = 70.8% of all failures.** All the weak-radical buckets together are
**97 rows = 19.0%**. The plan puts hamza first, defective second, hollow third, and nunation **fourth**; on
the ruler the project now uses, that order is inverted for the top three places.
⚠️ **But a bucket's size is not a lever's size** — §4.3 shows the nunation bucket's *fixable*
portion is far smaller than its row count. Buckets here are upper bounds, always (see §4.4).

### 4.3 The tanwin question §2s.9 left open — **answered, and the first answer was WRONG**

> **🔴 This subsection is a correction, written the same day.** The version first published here (and in
> `EVIDENCE_LOG.md` §2ba §4) reported *"43 cells with ≥2 rows, 0 mixed ⇒ tanwīn IS derivable from the
> triple"*, and that is **false**. The probe fed **only rows whose gold token carries tanwīn** into the cell
> counter, so its "plain" bucket could never increment and every cell was trivially constant. The number was
> an artifact of the loop, not a property of the data. It was caught while sizing the rule before
> implementing it, and `tools/renderer_bench_audit.py` now carries the corrected probe plus a comment
> recording the bug. Full correction: `EVIDENCE_LOG.md` §2bb.

The corrected probe groups **every** usable row by its `(pattern, case)` cell:

| | |
|---|---|
| distinct (pattern, case) cells | 357 |
| cells with ≥ 2 rows | 155 |
| … tanwīn-only | **17** |
| … plain-only | **70** |
| … **MIXED (both verdicts)** | **68** |
| rows lying inside a MIXED cell | **433** |

**The triple does not decide tanwīn.** Definiteness comes close to necessary — read off the token's own
skeleton, 0 of 252 definite tokens carry tanwīn, while 250 of 721 indefinite ones do (34.7%) — but it is
nowhere near sufficient: the rest are verbs, construct-state first terms, diptotes and proper nouns, none of
which `(root, wazān, case)` carries. **`src/renderer.py`'s `apply_case` docstring was right all along**
("tanwin depends on morphological features … not encoded in (root, pattern, case)"), and §2s.9 item 2's
instinct to test first was right too.

Sizing the plan's mechanism (indefinite + the pattern writes no final vowel → add the case tanwīn), with
definiteness taken from the **gold token** (an oracle, §2s.8d) and scored with the shared metric:

| | |
|---|---|
| current renderer correct | 444 / 973 = **45.6%** |
| with the plan's rule | 472 / 973 = **48.5%** |
| rows **fixed** | 192 |
| rows **broken** | 164 |
| **net** | **+28 rows = +2.9 pp** |

**+2.9 pp is below the ≥ +10 pp gate pre-registered for this lever**, so per the project's own rule the rule
is not shippable as written. The plan's *mechanism* (a definiteness gate) is the right instinct and its
original framing — that this needs an input the triple lacks — was correct; what fails is its size.


---

### 4.4 What the two biggest buckets actually contain (the evidence for the next lever)

Dumping the top mismatches (not theorising about them) changes the ranking again:

**`diacritic_only` (157 rows) is at least three different rules wearing one label.**
- *Over-diacritization* — the renderer writes a diacritic the human does not: `صُورَةِ` → `صُوْرَةِ` (a sukūn
  the pattern does not license), `إقْلَالِ` → `إِقْلَالِ` (a kasra under the hamza).
- *Hamza-seat diacritic missing* — `الْأَنْصَارِ` → `أنْصَارِ` (no fatha on the seat).
- *Case vowel on duals and diptotes* — `مَخْبِزَانِ` (dual, GEN-marked) rendered `مَخْبِزَانُ`; `مَسَاجِدَ` is
  labelled GEN but is diptote, so the gold's fatha is correct and `apply_case`'s kasra is wrong.
  A **part of this bucket is a case-application defect, not a rendering one** — which is exactly item 10's
  territory (case is government, not a local label).

**`other` (66 rows) is dominated by geminates going wrong in v3** — the doubled radical is *duplicated*:
`حِصَّتُهُ` → `حِصّصَةُ`, `الْبَزِّ` → `بَزّزِ`, `السُّرَّةِ` → `سُرّرَةِ`, `الْمُشَاحَّةِ` → `مُشَاحَّحَةِ`, and
`تَمَسُّوهُنَّ` → `تَمَسّسُوا`. This is the same phenomenon as v2 > v3 on doubled roots (36.2% vs 26.1%,
§4.1), seen from the failure side, and it is a **regression introduced by v3**, not an unsolved problem —
which made it the highest-confidence measurable win on the board.

✅ **Fixed 2026-10-12** (`EVIDENCE_LOG.md` §2bc, `_absorbed_geminate()` in `src/render_rules.py`): doubled
class **26.1% → 37.7%** (bar ≥ 36.2%), overall **45.6% → 46.5%**, every other class identical, legacy gold
47.1% → 48.9%. The guard against over-firing is verified — `تَتَبُّع` (root ت.ب.ع, a *letter* coincidence
rather than a geminate root) still writes both ت's.

**`ta_marbuta` (9 rows) is NOT the crisp rule it looked like**: sized as an oracle it wins 11 rows, but
`render_v3` never receives the enclitic, so the fix belongs to a **shared** component — and **70 of 521
failures carry an enclitic at all**, which makes this an enclitic-plane decision, not a ta-marbuta patch
(§2bc §3).

✅ **Shipped 2026-10-12 as a declared change** (`EVIDENCE_LOG.md` §2bd, `final_surface.render_triple(..., token=)`):
the token's affix plane now reaches the stem, starting with `ة→ت` before a pronominal enclitic. Frozen
overall **46.5% → 47.6%** (bar ≥ 47.5%), +11 rows across sound 55.9 · hollow 24.0 · doubled 40.6 ·
quadriliteral 50.0, **nothing down**; legacy all-usable 48.9% → **50.7%**. It cannot fire without an
enclitic (`مَرْأَة` untouched), and `token=None` reproduces the old behaviour bit for bit. **The ceiling moved
with it** — §2s.8d's 42.8% is now 45.7% (v2) / 50.7% (v3) — so every previously quoted per-engine figure is
superseded and must be re-derived. Still open inside the same item: 70 of 521 failures carry an enclitic
(proclitic vowels, the `ي`/`ه` allomorphs, pre-suffix vowel elision).

---

## 5. The plan's execution checklist, adjudicated

| # | plan step | verdict |
|---|---|---|
| 1 | Write the hamza strongest-vowel rule in `renderer.py` (53.5% → ≥95%) | **Baseline is wrong** (§1.1). The seat *mechanism* for final/medial hamza already exists in `render_rules.render_v3` (final-weak→`ء`, madda); the genuine open half is the bare-alif **notation** problem (§2t.1), which is a data/triple fix, not a seat rule. Target ≥95% has no supporting denominator. |
| 2 | Defective: suffix elision (`ـُونَ`/`ـِينَ`/`ـُوا`) + Form II–X `ى` | **Already shipped and measured.** §2t.3: *"suffix ـُونَ / ـِينَ / ـُوا follows → DELETED"*, plus the final-weak→`ء`/madda extras. v1→v3 moved defective **6.0% → 29.8%** on the new ruler. |
| 3 | Hollow: closed-syllable apocope (`قُلْتُ`, `بِعْتُ`) with glide colour | **Half shipped, half genuinely new.** §2t.3 has *"closed syllable (next slot carries sukun) → DELETED"*. The **glide colour** (`و`→u vs `ي`→i) is §2t.4's recorded limitation — *"`1َا2َ3` with r2=و DELETES (قَالَ) while the same shape with r2=ي WRITES the mater (عَايَنَ)"*. **Keep this half.** |
| 4 | Route the rootless content words to Route 3 | **Already policy and already implemented** (route 4); the label is what needs fixing (§3.1). |
| 5 | Tanwīn + accusative alif in `apply_case` | **Right goal, wrong size.** The triple does *not* decide tanwīn (68 mixed cells of 155, §4.3), and the plan's own definiteness gate nets **+2.9 pp** even with oracle definiteness — below the ≥ +10 pp gate. It needs an input the renderer is not given; deferred. |
| 6 | Re-run the local CPU benchmark against the 300 human rows | **Done, against a better ruler** (§4.1) — the 1000-row adjudicated benchmark. |
| 7 | Launch the full 43-minute Kaggle run | **Do not.** Prong 2 is measured-negative (§3.5); the standing GPU constraint is not met; item 1's benchmark landed today, so there is now a *reason* to re-run — but the run must be re-scoped and pre-registered, not inherited from this plan. |

---

## 6. What the plan does not mention

- **The clitic plane** (§2s.5/§2s.8b): the single largest *metric*-level artifact in the project's history,
  fixed by defining the metric on the stem. Any new renderer number must state that it is clitic-aware.
- **The 68% nunation+diacritic residual** (§4.2) — the plan's own Phase 1 order is inverted by it.
- **v2 > v3 on doubled roots** (§4.1).
- **The ruler change**: the project now has a 1000-row, double-annotated, adjudicated benchmark. Every
  figure in the plan predates it.
- **The input problem behind tanwīn** — its presence depends on definiteness, construct state, verb-hood and
  diptote-ness, none of which `(root, wazān, case)` carries (§4.3). Any fix is a *plumbing* change first: the
  clitic plane the harness already has must reach the renderer.
- **That this review published a wrong finding and had to retract it the same day** (§4.3). Recorded
  deliberately: the bug was in *my* probe, not in the plan, and a review that hides its own correction is
  worth less than the plan it audits.

---

## 7. What changed in the tree during this review

1. **`tools/renderer_bench_audit.py` added** — the renderer vs the frozen item-1 benchmark, per root class,
   with the tanwīn derivability probe. Portable via `tools/repo_root.py` (never a hardcoded path).
2. **An uncommitted 650-line patch to `src/renderer.py` was reverted** (bytes archived, hashes recorded):
   `dist/audit-2026-10-12/rejected-patch/`. Reasons, all measured:
   - it makes the **documented v1 baseline unrunnable** — `TypeError: 'bool' object is not subscriptable`
     at `renderer.py:297`, on every weak-root row, so `measure_renderer_gold --engine v1` and
     `final_surface.render_triple(..., engine="v1")` both crash;
   - on the pre-registered acceptance test it changes **nothing** (`--weak-only`, 98 rows: v3 = **34.7%**
     with and without the patch — the patch is not even on v3's path, which is `render_rules.ENGINES`);
   - its own three test scripts each crash on the same line, and their expected values are **wrong Arabic**
     (`إِكَل` for أَكَلَ, `بُدِأ` for بُدِئَ, `جَزِأ` for جُزِئَ, `قَرَا`, `سَاِل`, `دَاء`), so validating
     against them would bake errors in.
3. **A dated `EVIDENCE_LOG.md` section records all of the above**, and `ACTIVE_BACKLOG.md` items 1 and 9 are
   updated with the measured baseline and the tanwīn lever.
4. **The tanwīn probe was found buggy the same day and corrected** — it iterated only over rows whose gold
   token carries tanwīn, so its "plain" counter could never increment (§4.3). `tools/renderer_bench_audit.py`
   now carries the corrected probe *and* a comment recording what the first version did wrong. The correction
   is published as `EVIDENCE_LOG.md` §2bb rather than quietly edited away.
5. **Three diagnostics were run to size the next lever and are kept** (untracked, in `dist/audit-2026-10-12/`):
   `tanwin_discriminant.py` (is definiteness the hidden variable?), `tanwin_corrected.py` (the corrected cell
   analysis + the rule's net effect with oracle input), `bucket_examples.py` (§4.4). They are the evidence for
   §8's ranking, and they re-run in seconds.
6. **`tools/backup_to_github.sh` could NOT be run**: it refuses without a token (no `GH_TOKEN`, no
   `~/.github_token`) — which is the correct behaviour, and why the mirror for `e9f9074` is still outstanding.
7. **Two fixes were shipped after the review, both pre-registered and both measured**: the **v3 geminate
   regression** (§4.4, `EVIDENCE_LOG.md` §2bc) and **Option A — the clitic plane as a renderer input**
   (§2bd). Frozen fidelity **45.6% → 46.5% → 47.6%**; and because `final_surface` is shared, **every
   per-engine figure and the renderer's own ceiling moved with them** — §2s.8d's binding 42.8% is now
   **45.7% (v2) / 50.7% (v3)**. `token=None` reproduces the pre-change behaviour exactly, so the older
   numbers remain reproducible rather than merely stale.

---

## 8. Decisions for the human (not taken here)

- **The Phase 2 threshold in §2az was pre-registered on the old ruler** ("weak radical re-realization:
  clitic-aware ≥ 55%"). Re-registering it on the frozen benchmark is a *ruler change*, so it must be stated
  as such (old: 34.7% of 98 weak rows on the 300-row gold; new: 45.6% overall / hollow 23.0%, defective
  29.8% on 973 adjudicated rows). **Do not silently restate a pre-registered number.**
- **v3 vs v2 as the default engine** — on the new ruler v3 is a mixed win (§4.1), and the doubled regression
  is visible as a *defect* in §4.4. A decision, not a measurement — and the likely answer is "fix v3's
  geminate path", not "branch by class".
- **Lever ranking, measured.** (1) ✅ **v3's geminate/doubled regression — DONE** (§4.4, `EVIDENCE_LOG.md`
  §2bc): doubled 26.1% → **37.7%** (40.6% after the clitic plane), overall 45.6% → **46.5%** → **47.6%**,
  no class moved down. (2) ✅ **The enclitic plane — DONE for `ة→ت`** (`EVIDENCE_LOG.md` §2bd): the token's
  affix plane now reaches the renderer as a declared input (`render_triple(..., token=)`), +11 rows across
  sound · hollow · doubled · quadriliteral, **nothing down**, legacy 48.9% → **50.7%**. The **ceiling moved
  with it** (§2s.8d's 42.8% → **45.7% v2 / 50.7% v3**), so old per-engine figures are superseded. **Remaining
  inside it:** 70 of 521 failures still carry an enclitic (proclitic vowels, `ي`/`ه` allomorphs, pre-suffix
  elision). (3) **Split `diacritic_only` into its three sub-rules and *size* each before implementing** —
  now the biggest bucket at 159 rows (31.2% of failures), but not one lever, and part of it is a
  case-application defect that belongs with item 10. (4) **tanwīn** — last: gate unmet at +2.9 pp (§4.3),
  but its definiteness **input is now plumbed**, so a smaller honest gate can be pre-registered.

