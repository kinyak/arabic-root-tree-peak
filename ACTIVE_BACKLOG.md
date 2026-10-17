# ACTIVE BACKLOG — the live items (max 10)

**This is the only file that says what to do next.** `EVIDENCE_LOG.md` is append-only history and
deliberately contains superseded sections; do not read it to decide the next move. Where the two
disagree about *what to do*, this file wins.

## Rules for this file

- **At most 10 items.** Adding an 11th means removing one.
- Every item carries: **hypothesis · metric · split · acceptance threshold · next command.**
- An item leaves this file only by being **closed with a measured verdict** (appended to
  `EVIDENCE_LOG.md` as a dated section) or **dropped with a stated reason**.
- **No item is started before its threshold is written down.** That is the repo's own
  pre-registration rule (`docs/next-run-criteria.md`, round 26) and it is what makes a result mean
  something.
- If a `next command` does not exist yet, it says so. Inventing a plausible command is how a
  backlog becomes fiction.

## Standing constraints

- CPU work is free; **GPU is not** — confirm before spending (`START-HERE.md` §7, RED LINE 1).
- Corpora are copyleft/non-commercial: never commit, never publish (`EVIDENCE_LOG.md` B20).
- **Evaluation must not be CALIMA-mediated** (A14/E1). This is item 1's whole point.
- Report metric **PAIRS** (coverage AND fidelity); one without the other is uninterpretable.
- Quote no number without re-deriving it (RED LINE 12).

- **The frozen ruler's identity:** `data/annotation/bench-gold.jsonl`, sha256
  `7a06a585e065d8cf41358210e74db5c638dafe8c81f67bf1ee87790134885b07`, 1,000 rows, pattern field
  **`wazn_pattern`**. `bench-freeze.json` freezes its INPUTS only, not the adjudicated output. A hash
  quoted for this file without re-deriving it is a claim, not a check (§2cs).
- **A run may not silently change its own objective** (§2cq/§2cs) — **BOTH GUARDS NOW SHIP (§2cx,
  2026-10-14).** The v21 grid trained under a config that exists nowhere in git (bundle
  `cfd992765884bbb4` = the working tree, byte-for-byte, vs the committed `20335ce6434ff198`), normalisation
  OFF, weights rewritten, and nothing in its log said so. `src/make_notebook.py` now **REFUSES** a payload
  carrying an uncommitted `config/` (measured: exit=1 and the notebook left byte-identical; override
  `--allow-dirty-config` prints the objective and accepts it explicitly), and the built notebook **PRINTS its
  effective loss weights** at preflight, resolved exactly as `src/train.py:103-132` resolves them. v21 is
  registered in `tools/verified_runs.json` with `"commit": null` and its objective's sha256
  **`75e725b8f0d50cb9`**. **RESOLVED 2026-10-14 (§2cy): the committed objective was RESTORED.** The uncommitted config
  also carried `batch_size 32→64` and `steps 3000→12000` (**8× the training**, unnoticed by everyone), so the
  restore removed that confound too. The dirty file is preserved at `%TEMP%/config-shared-DIRTY.yaml` and in
  `dist/runs/v21/antigravity-uncommitted.diff`; its sha256 is `75e725b8f0d50cb9`. Note that the committed
  objective still has focal γ=2 on wazān/wazān_canonical **by `train.py` DEFAULT**, since the keys are absent —
  the preflight now prints that source explicitly.
- **A default inside a lookup is a decision** (§2cs): `v.stem_tail.get(raw_tail, 0)` sends a genuine
  unseen affix to a **meaningful** class (bare stem), which is a live wrong gradient — worse than the
  ignore index. Route junk to `IGNORE`, but a real-but-unseen class must go to a **complete** class list.


---

## 1. Independent, blind, double-annotated gold benchmark — **DELIVERED 2026-10-12; this is now the ruler**

> **Closed 2026-10-12 (§2az, §2ba).** Two independent annotators, 178 disputed rows adjudicated with a
> written rationale per row, agreement reported pre-adjudication per field (root 98.66% · wazān 84.58% ·
> case 98.50% · confidence 99.70% · alternatives 99.80%; **human case ceiling 98.50%, κ = 0.9784**).
> The chain that this item's `next command` laid out — receipt ①, IAA ②, disputes ③, adjudication ④,
> corroborating second implementation ⑤ — **ran to completion**; `bench-gold.jsonl` (1000 rows,
> 650 test / 350 calibration, 257 canonical wazān classes) is the frozen reference. The item's *rules*
> below stay in force for every downstream claim; its *blocker* is gone. Consequence: "the benchmark does
> not exist" is no longer a valid reason to defer anything, and **`README.md`/`START-HERE.md` may be
> refreshed** (the deferral was tied to this item's landing — see §2aq for why it was deferred, not why
> it stays deferred). First use of the ruler that was not an annotation task: §2ba —
> `tools/renderer_bench_audit.py`.

- **Hypothesis.** Every arm comparison currently rests on a 278-row human gold that is small,
  stratified toward weak/doubled surfaces, and whose *case* reference is CALIMA-derived (the "0.459
  ceiling" is CALIMA-vs-human agreement). So the project may be optimising against a weak, partly
  self-referential ruler — and a genuinely independent set will change which interventions look like wins.
- **Metric.** Root slot-set exactness · wazān well-formedness · case **macro-F1** · plus
  **inter-annotator agreement** (raw agreement and Cohen's κ per head) computed on the overlap
  **before** adjudication.
- **Split.** 1,000–1,500 contextual tokens, **split by lemma/root** — never a random token split.
  Strata fixed in advance and reported separately: weak / hollow / defective / doubled /
  quadriliteral roots; ambiguous unvocalized forms; clitic-heavy forms; learner misspellings.
  MSA only, for now.
- **Acceptance threshold.** (a) two independent annotators + adjudication, with κ reported;
  (b) **no row may originate from CALIMA output**; (c) the split is lemma-disjoint — *verified by a
  script*, not asserted; (d) the benchmark ships with its own re-derivable counts.
- **Freeze.** `docs/BENCHMARK-FREEZE-v2.md` — locks **A–E**: the annotation guide (v1 in force, plus
  homograph/clitic/OOV rulings), blind IDs + one frozen shuffle, six surface-detectable strata,
  independent labels before adjudication, and frozen test/calibration splits. **§9 signed off
  2026-10-11:** 1,000 rows (650 test / 350 calibration), strata quotas 18/12/12/18/20/20, two
  independent annotations, PI adjudication with a written per-row rationale.
- **Status: the sheet is GENERATED AND FROZEN (9 columns, Amendment 1), and the issue packet is SEALED.**
  `data/annotation/bench-sheet.csv`, sha256
  `1b4f8a1e208dd34cebe89bc15570a7d380569db1d0aee59193ef585801c81db7`; annotator copies byte-identical;
  generator `tools/build_benchmark_sheet.py --seed 20261012`; determinism verified; 1,000 rows with
  **0 dirty targets**, 0 page markers, 0 train-text overlap, and the approved quotas realised exactly
  (180/120/120/180/200/200). Build findings and the S6 thin margin: freeze doc §12.
  **Amendment 1** (freeze doc §13) added the **ninth column `alternatives`** — rival analyses as
  structured data with a strict grammar (`NONE` / `field=value` / ` | `-separated), because prose in
  `notes` is unmeasurable, unadjudicable and unusable for **top-k** scoring. The 8-column sheet
  (`71bdd196…`) was **never sent to anyone**; the amendment landed before issue.
  **Sent 2026-10-12** via private Telegram DM. Annotator B acknowledged receipt the same day,
  verified all five file shas against the sealed issue record (all match), and committed in writing
  to the order of operations (practice pack FIRST, benchmark sheet unopened until written approval),
  the return channel (same private DM), and the tool policy (zero AI / analyzer / treebank use;
  dictionary lookups recorded as `LOOKUP: <source>, <headword>`). Issue record
  `data/annotation/bench-B-ISSUE.json` now has `status: SENT`; re-verify any time with
  `python tools/issue_packet_b.py --check` (it recomputes every hash from disk and refuses on drift).
- **Next command.** ~~Await the practice-pack return.~~ **Executed 2026-10-12 — see the closure note above.**
  The chain is kept here as the record of *how* the ruler was admitted, and as the shape any future
  re-issue must follow. In order it was:
  ① `python tools/receive_return.py --file <return.csv> --annotator B --expected-sha <issued sha>` —
  hashes it, writes the **read-only archive**, checks row IDs/order against the frozen sheet, appends a
  receipt, and format-checks it. (Re-verify any time with `--verify`: a return that changed after
  hashing is **VOID**.)
  ② `python tools/iaa_report.py --a <A.csv> --b <B.csv> --key data/annotation/bench-KEY.csv` —
  per field, **pre-adjudication**; records the **human ceiling**: case raw agreement between the two
  annotators is the number the model's case score must be reported against.
  ③ `python tools/build_benchmark_gold.py --emit-disputes` — writes ONLY the rows the two annotators
  disagree on, with both answers side by side and empty PI columns.
  ④ the PI fills `adjudicated_*` **and a rationale for every disputed row**, then
  `python tools/build_benchmark_gold.py --ingest data/annotation/bench-disputes.csv` — **refuses**
  (exit 3) on an empty rationale or an illegal value. Produces the adjudicated gold, the
  **canonical wazān classes derived from the adjudicated data**, and the benchmark's own
  re-derivable counts.
  ⑤ `python src/score_annotation.py --sheet <A> --sheet2 <B>` as an **independent second
  implementation** of the agreement numbers (it computes Cohen's κ for `case` and raw agreement for
  `root`), to corroborate ② rather than replace it.
  **`--validate` is a GATE, not a measurement** — it returns a format verdict, and it does not by
  itself produce the canonical wazān space or the human ceiling; ③/④ do that.
  Correction to `EVIDENCE_LOG.md` §2as/§2at: the claim there was that no inter-annotator-agreement
  implementation existed. **That was too strong** — the named command (`crosscheck_annotation.py`)
  genuinely computes none, but `src/score_annotation.py --sheet2` has computed κ for `case` and raw
  agreement for `root` all along. `tools/iaa_report.py` is still the right tool for this benchmark
  (per-field, `alternatives`, taxonomy, blank≠abstain, prevalence guard, validator), but the earlier
  wording overstated the gap.
- **Report agreement per field, never pooled:** κ for `case`/`confidence` (and **never κ alone** —
  at a skewed marginal κ collapses toward 0 even at 99.9 % raw agreement: measured `po=0.999,
  pe=0.999 → κ=0.000`), **raw exact agreement + a disagreement taxonomy** for `root`/`wazān`
  (high-cardinality labels make a pooled κ uninformative), and a **set comparison for
  `alternatives`** — the rows where one annotator wrote `NONE` and the other listed a candidate are
  the benchmark's direct measurement of ambiguity, and they are what make top-k scoring meaningful.
- **Portability:** the benchmark tooling resolves the repo from its own location or `--root`
  (`tools/repo_root.py`); it must never again be pinned to one absolute path. A bogus `--root`
  **refuses** rather than silently verifying a different tree.
- **Report `wazān` as a PAIR — raw string AND radical slots — never one alone.** `EVIDENCE_LOG.md` §2au
  (probe `tools/wazan_notation_probe.py`): the 278 human patterns are **119 distinct as written but 65
  after canonicalisation**, and one structural skeleton is written **13 different ways**; the model's
  slot accuracy is already **0.9880** against a raw-string 0.1115–0.2206. A raw-string metric charges
  the model for choosing a different legal spelling of the same pattern. The canonical space must come
  **from the adjudicated benchmark**, never be invented on the modelling side.
- **Blocker.** One **second human annotator**. Blindness cannot be retrofitted (RED LINE 7). Until the
  returns are in, nothing downstream counts as an accuracy improvement — only as infrastructure.
- **Accepted fragility (do not "fix"):** S6 supply is thin — 219 distinct-lemma candidates for a 200
  quota (practice pack: 18 for 8). The generator **fails closed**, so a shrinking pool shows up as an
  error. **The quota is not to be loosened to make a rebuild pass.**
- **Do not:** send the KEY, either annotator's file, or any model/CALIMA output · train on more silver
  labels before this exists · refresh `README.md`/`START-HERE.md` before this item lands (`EVIDENCE_LOG.md` §2aq).

## 2. Calibrated abstention, fitted on held-out data

- **Hypothesis.** The current confidence values are proxy/hand-entered, so the policy cannot be used
  as a decision-maker; properly fitted thresholds plus selective-risk reporting can be.
- **Metric.** **Selective-risk curve** — accuracy of the *displayed* root at fixed coverage (report at
  90% / 70% / 50%) · ECE between stated confidence and empirical accuracy · false-abstention rate on
  root-bearing tokens.
- **Split.** Thresholds fitted **only** on a held-out calibration split disjoint from the reporting
  split. The existing gold-300 may not serve as both.
- **Acceptance threshold.** (a) no threshold may be hand-entered; (b) at 90% coverage, displayed-root
  accuracy must exceed the pre-abstention baseline by a measured margin; (c) a **structural (Tier-1)
  abstention stays FINAL** and is never re-scored as confidence; (d) false-abstention on root-bearing
  tokens ≤ **0.25%** (the current gate's own budget).
- **Next command.** `python src/test_uncertainty_abstention.py` (existing gates must stay green, 0
  false positives on valid templatic words), then **write the fitting script — it does not exist yet.**
- **Do not:** ship hand-tuned thresholds.

## 3. Morphological candidate generator (licence-audited)

- **Hypothesis.** A generator over a licensed lexicon guarantees linguistically valid analyses, so the
  neural model only has to *choose*. That directly attacks the failure the OOV cliff exposed
  (in-vocab 0.564 vs OOV 0.073 — a 7.7× gap, `§2ad`).
- **Metric.** **Candidate recall** — the gold analysis appears in the top-k candidate set. This is the
  ceiling for everything downstream, so it is measured first and reported separately by stratum.
- **Split.** The item-1 benchmark (primary) and PADT dev (secondary).
- **Acceptance threshold.** Candidate recall ≥ **0.95** on each benchmark stratum, **with a per-source
  licence audit**, and evidence that recall comes from morphology rather than from the answer key —
  **no evaluation split may enter any dictionary** (RED LINE 4).
- **Next command.** `python src/build_wazan_inventory.py` and `python src/check_arramooz.py` to size
  the candidate space before writing the generator.
- **Do not:** assume a larger word vocabulary solves morphology (measured wrong for the old sample —
  `§2ad`).

## 4. Contextual reranker over candidates, with root×wazān scored JOINTLY

- **Hypothesis.** Reranking candidate analyses with sentence context beats independent argmax heads
  stitched together afterwards, because root and wazān compatibility is a joint constraint, not two
  separate decisions.
- **Metric.** Top-1 and top-k accuracy on the benchmark with calibrated confidence, **measured against
  the candidate-generator's own prior** — the reranker must add value over the prior, not merely
  reproduce it.
- **Split.** The item-1 benchmark, lemma-disjoint, with the hard strata reported separately.
- **Acceptance threshold.** Must beat the prior-only baseline by **more than the seed spread**
  (|d| > 2·max(sd) as a *consistency check*, never a significance test), **and** must not regress the
  in-vocabulary half — a trade is not a gain (`docs/next-run-criteria.md`).
- **Next command.** Does not exist. First establish the prior-only baseline:
  `python src/diagnose_gold_checkpoint.py --ckpt dist/drive-preflight/gold-baseline-s20261009.pt`.

## 5. Input representation: explicit segmentation (the character-encoder half is CLOSED)

- **Hypothesis.** *Narrowed 2026-10-11.* The hypothesis used to read "…plus an always-on character
  encoder"; that half is **already shipped and already measured** — v12 (round 20, `src/model_arms.py`,
  char embedding → Conv1d k=3/5/7 → max-pool, in **both** arms) moved OOV whole-root **0.000 →
  0.071–0.241** and the treatment's root advantage **did not replicate** (`§2z`). What remains open is
  the other half: **explicit proclitic/stem/enclitic segmentation**, which is the part that would let a
  case head see the stem rather than the affix plane.
- **Metric.** Per-row root accuracy, **split in-vocab vs OOV**; the OOV slice is the one that matters.
- **Split.** The item-1 benchmark plus PADT dev, per-row split reported alongside the aggregate.
- **Acceptance threshold.** OOV root accuracy improves beyond **2·max(sd)** of the 3-seed spread
  **and** the in-vocab half does not fall.
- **Next command.** `python tools/per_row_split_compare.py` to fix the baseline row before any change.
- **Do not:** keep tuning CNN kernels · **re-introduce a character encoder as an OOV fix** (measured,
  closed — see `§2z` and the "Explicitly NOT doing" list).

## 6. `max_vocab` — the one pre-registered next-run variable

- **Hypothesis.** With the spread sample the frequency cap binds for the first time, excluding **26**
  words that are present in the records and pass `min_freq` (56 → 82 of 126 reachable).
- **Metric.** Coverage of the 126 OOV gold words, **then** human-gold OOV accuracy.
- **Split.** `data/out/spread-B-2m/*`, with the manifest's per-file hashes verified against disk.
- **Acceptance threshold.** Coverage rises **56 → ≥ 80 of 126** *and* OOV accuracy rises beyond the
  seed spread. **A coverage rise alone is explicitly not success.**
- **Next command.** `python tools/record_coverage.py --anchor data/out/tashkeela-train.jsonl B=data/out/spread-B-2m/tashkeela-train.jsonl`
  (CPU only, ~3 min) **before** any GPU spend.
- **Do not:** co-change it with the sample size — that confound was measured and the fork was made
  deliberately (`§2af`).

## 7. A strong licence-audited pretrained encoder — as TEACHER baseline **and** product baseline

> **Absorbed 2026-10-11:** this item took over former item 10 ("Product baseline = a strong licensed
> encoder + lexicon"). Both asked one question — *how good is the best thing we may legitimately
> ship?* — from two angles; nothing was dropped, the licence-chain requirement and the `--ceiling`
> next-command came with it. `EVIDENCE_LOG.md` §2au referenced the old item 10; it is now §7.

- **Hypothesis.** We do not currently know whether the limit is **data, architecture or objective**. A
  fine-tuned encoder plus lexicon reranker separates those possibilities — and it is also the only
  honest answer to the *product* question.
- **Metric.** The matched research baseline asks "same heads, same splits, same shared final-surface
  metric as the from-scratch arms — the gap reported in identical units". The product half is
  **product-facing accuracy on the item-1 benchmark, with licence status and cost recorded per
  component** — *a number whose licence forbids distribution is not a product number.*
- **Split.** The item-1 benchmark, held out entirely from any tuning; PADT dev for mechanics only.
- **Acceptance threshold.** **Either outcome of the teacher comparison is a result**, but the follow-up
  must be pre-registered before running: *crush* → capacity/data is the binding limit and distillation
  becomes the path; *no crush* → objective/representation is the binding limit. **A gap is not an
  attribution** — the encoder differs in pretraining corpus, tokenizer and objective at once. On the
  product side: any product claim must be stated as a comparison against this baseline **with the
  licence chain attached**, and **no product claim may be derived from arm-vs-arm numbers**.
- **Next command.** `python src/eval_harness.py --ceiling --source eqtb --limit 12000` to restate the
  current ceiling honestly **first**; then the licence audit (`RESOURCES.md` — note PADT/NYUAD are
  CC BY-NC-SA and QAC is GPLv3, all `[LICENSE-RISK]` for a closed app); then
  `python src/model_arms.py --parity`.
- **Do not:** treat pretrained models as magic · run the ablation at 500M tokens (76–114 units) ·
  claim a product number from an NC-licensed teacher without saying so.

## 8. Analysis-first product target (not full vocalization)

- **Hypothesis.** Making full vocalization the first product target forces the renderer to be
  universal, which it measurably is not (weak/hollow/defective skeleton accuracy **0.0%**). An
  *analysis* answer — what this word likely is, why, what alternatives exist, what context would
  disambiguate it, whether the learner can identify the root themselves — is useful **even when the
  renderer abstains**.
- **Metric.** A **pair**: correctness of every displayed analysis claim, and its usefulness — never
  surface exactness alone.
- **Split.** The item-1 benchmark, restricted to the hard strata.
- **Acceptance threshold.** Every displayed claim is either backed by a candidate + reranker score or
  explicitly abstained. **Zero fluent-but-unsupported analyses.** Abstention is counted as a success
  when the alternative would be a guess.
- **Next command.** `python src/final_surface.py --selftest` (the shared metric still stands), then
  `python src/renderer.py --measure --limit 4000` to mark which rows the deterministic renderer must
  **not** be asked for.

## 9. Separate analysis from generation; deterministic generation where covered

- **Hypothesis.** Where a lexicon/rule route is covered, deterministic generation is strictly better
  than neural generation; neural generation should serve only the uncovered residual.
- **Metric.** **coverage% and fidelity% as a pair, per route** — never one alone
  (`coverage / stem_accuracy_of_covered / stem_yield` are three separate keys).
- **Split.** PADT dev plus the item-1 benchmark.
- **Acceptance threshold.** A route is used only where its measured fidelity is at least its claimed
  coverage; residual is reported **with a denominator split by class**, not as a raw failure count
  (closed-class words legitimately have no root).
- **Measured on the FROZEN ruler (2026-10-12, §2ba — `tools/renderer_bench_audit.py`).** 973 usable triples
  of the 1000-row adjudicated gold; coverage 100% **by construction** (the human supplies root + pattern),
  so fidelity is the only open question: **v3 45.6% · v2 44.4% · v1 40.9%** (test split 47.1%), token exact
  16.2%, skeleton 34.9%. By root class (v3): sound 54.8% · hollow 23.0% · defective 29.8% · doubled 26.1% ·
  assimilated 27.8% · quadriliteral 45.0%. **v2 beats v3 on doubled (36.2% vs 26.1%)** — v3's default status
  is a *mixed* win on this ruler, not a given.
- **The residual re-orders this item — but a bucket's size is not a lever's size.** 529 failures:
  `diacritic_only` 157 + `tanwin_missing` 150 + `tanwin_alif_acc` 54 = **361 rows = 68.2%**, against
  **93 rows = 17.6%** for every weak-radical bucket combined. ⚠️ **CORRECTED (§2bb):** the nunation half of
  that 68% is *not* a cheap win — tanwin is **not** a function of `(pattern, case)` (68 MIXED cells of 155;
  433 rows inside them), and the plan's definiteness gate nets **+2.9 pp even with oracle definiteness**,
  below the ≥ +10 pp gate, so it is **not shipped**. It needs a plumbing change (the clitic plane must reach
  the renderer) before it is a lever at all.
- **What the buckets actually contain (§2bb, `dist/audit-2026-10-12/bucket_examples.py`)** — inspected, not
  assumed: `diacritic_only` is three rules under one label (over-diacritization, a missing hamza-seat vowel,
  and **case application on duals/diptotes**, which is item 10's territory); `other` is dominated by **v3
  breaking geminates** (the doubled radical duplicated: `حِصَّتُهُ`→`حِصّصَةُ`, `الْبَزِّ`→`بَزّزِ`,
  `تَمَسُّوهُنَّ`→`تَمَسّسُوا`) — the failure-side view of the v2 > v3 doubled regression; `ta_marbuta` (9) is
  one crisp rule, `ة` → `ت` before an enclitic pronoun.
- **Next command.** (1) ✅ **DONE 2026-10-12 (§2bc) — v3's geminate path fixed.** `_absorbed_geminate()`
  in `src/render_rules.py` (three guards: same *radical* in the previous slot, a shadda between the slots,
  shadda already emitted). Measured: frozen **doubled 26.1% → 37.7%** (bar was ≥ 36.2%; v2 = 36.2%),
  frozen **overall 45.6% → 46.5%** (bar ≥ 45.6%), **every other class identical** (sound 54.8 · hollow 23.0 ·
  defective 29.8 · assimilated 27.8 · quadriliteral 45.0), legacy all-usable 47.1% → **48.9%**, legacy
  weak-only unchanged at 34.7%. `تَتَبُّع` (letter coincidence, root ت.ب.ع) still writes both ت's — the
  guard against over-firing, verified.
  (2) ⏸ **The `ة→ت` "fast-follow" is NOT a renderer rule** — `render_v3` never sees the enclitic. Sized as an
  oracle it wins **11 rows**; and **70 of 521 failures carry an enclitic at all**. Fixing it means changing a
  **shared** component (either the clitic plane reaching the renderer, or `final_surface.candidates` folding a
  de-cliticised stem-final ت to its ة form) — a **ruler decision**, because it moves every reported number
  (§2s.8b moved the headline 41.7% → 32.0% when the metric changed). **Awaiting the PI; not implemented.**
  (3) Then **split `diacritic_only` and size each sub-rule before implementing any of it** — 157 rows is not
  one lever.
- **Option A — the clitic plane reaches the renderer — ✅ DONE 2026-10-12 (§2bd), bar met.**
  `final_surface.render_triple(..., token=None)` now applies the token's affix plane to the stem after the
  case vowel; `pronominal_enclitic()` reuses the *metric's own* enclitic test so the two cannot disagree.
  Scope shipped: **`ة→ت` before a pronominal enclitic only**; it cannot fire without an enclitic (`مَرْأَة`
  untouched). **Result: frozen overall 46.5% → 47.6%** (bar ≥ 47.5%, met by 0.1 pp) with **+11 rows across
  sound 55.9 · hollow 24.0 · doubled 40.6 · quadriliteral 50.0 and NOTHING down**; legacy all-usable
  48.9% → **50.7%**, weak-only unchanged **34.7%**.
  🔴 **The renderer's CEILING moved with it** — §2s.8d's binding "42.8% with the human triple" is now **45.7%
  (v2) / 50.7% (v3)** on the legacy gold and **47.6%** on the frozen ruler. Every previously quoted
  per-engine number must be re-derived; `token=None` reproduces the old behaviour exactly, so old numbers stay
  reproducible rather than merely stale.
  **Still open inside this item:** 70 of 521 failures still carry an enclitic (proclitic vowels, the `ي`/`ه`
  allomorphs, pre-suffix vowel elision) — now *reachable*, not yet done. tanwīn's definiteness input is now
  plumbed, but its gate (≥ +10 pp) is still unmet at +2.9 pp, so **it stays off**.
- **Next command (after Option A).** Split `diacritic_only` (157 rows, the largest bucket) into its three
  measured sub-rules — over-diacritization, missing hamza-seat vowel, dual/diptote case application — and
  **size each before implementing any of it**; the dual/diptote slice belongs with item 10. Then re-derive
  every quoted renderer figure with `python tools/renderer_bench_audit.py --engine v3` (the ruler moved).
- **Diacritic split — PRE-REGISTERED 2026-10-12 before the office run** (item 9's next lever, routed through
  `buddy_office` with cloud-deepseek pi workers, workspace `G:/arabic-root-tree`).
  **Deliverable:** `tools/diacritic_split.py`, a MEASUREMENT tool (no renderer change) that classifies the
  `diacritic_only` bucket (159 rows, 31.2% of failures) into named sub-rules and **sizes each before any rule
  is implemented**. Written as a pair with `--check`.
  **Bar (all must hold):**
  1. **≥ 90% of the 159 rows** classified deterministically into named sub-rules; the remainder left in an
     explicit `unexplained` bucket — **force-fitting is a failure, not a pass**;
  2. for EACH sub-rule, the **measured net effect** on the frozen ruler (`rows fixed − rows broken`, scored
     through the shared metric `final_surface.stem_match`) reported **before** it may be proposed;
  3. `src/renderer.py`, `src/render_rules.py` and `src/final_surface.py` **byte-identical to HEAD** after the
     run (`git diff --stat` must show them untouched) — this is size-before-implement, so a renderer edit
     **fails** the item even if the numbers look good;
  4. deterministic: byte-identical output on re-run; stdlib + the repo venv only (**pytest is NOT installed**,
     so gates are exit-code scripts, not test suites), zero GPU, no network, paths via `tools/repo_root.py`;
  5. `--check` + `python src/smoke_test.py` + `tools/renderer_bench_audit.py --engine v3` +
     `src/measure_renderer_gold.py --engine v3` all exit 0.
  **A sub-rule with net ≤ 0 is DROPPED with its number recorded**, never implemented.
- **Diacritic split — MEASURED 2026-10-12 (round 1 of the office run; see EVIDENCE_LOG §2be).** The bucket is
  **four** rules, not the three named in §2bd: `sun_letter_shadda_missing` **64** (the largest — the renderer
  omits the sun-letter shadda: `الشْمس` for `الشَّمس`), `hamza_seat_vowel_missing` 56,
  `diptote_case_vowel` 11, `redundant_hamza_kasra` 9, `other_extra_mark` 6, `other_case_vowel` 5,
  `dual_case_vowel` 4, `extra_long_vowel_sukun` 3, `unexplained` **1** → **158/159 = 99.4% classified**
  (bar ≥ 90% met; the one residual row left honestly unexplained). Measured net on the frozen ruler
  (baseline 463/973 = 47.6%), each verified by re-running the worker's own read-only script **and** by an
  independent wrapper calling its rule functions: `add_sun_letter_shadda` **+62** (62/0),
  `add_hamza_fatha` **+51** (51/0), `drop_long_vowel_sukun` **+3** (3/0), `dual_nominative_kasra` **+2** (4/2);
  **the four together = 583/973 = 59.9% (+120 rows, +12.3 pp)** — the largest single lever measured on the
  frozen ruler so far, and it clears the ≥ 55% Phase-2 bar. Dropped with numbers recorded:
  `drop_redundant_hamza_kasra` −5, `apply_diptote_fatha` −34, `other_case_vowel`/`other_extra_mark` no safe
  rule. Leakage audit: surface-only or token-definiteness/case-head inputs; no rule reads the gold token to
  decide its output.
  **Round 1's artifact FAILED on budget** — `BUDDY_TIME_BUDGET=420` cut pi off at 418 s mid-analysis
  (`tools/diacritic_split.py` never created; `--check` exited 2). The office reported `failed`/`incomplete`
  rather than a false success. Round 2 (budget 1800, analysis handed over) targets the artifact only.
- **Implementation bar for the four rules — PRE-REGISTERED 2026-10-12 before round 2 lands.** Sizing is not
  shipping: the four rules are hand-simulated post-processors, none exists in `renderer.py`/`render_rules.py`
  or the assembly layer. Implement them **only if**, measured on the frozen ruler through
  `tools/renderer_bench_audit.py --engine v3`: (a) overall fidelity **≥ 55%** (baseline 47.6%); (b) the
  doubled/geminate class **does not regress below 36.2%** and **no other class regresses at all**;
  (c) legacy `measure_renderer_gold --weak-only` **stays ≥ 34.7%**; (d) the rules are implemented as
  deterministic functions of surface + token + case, never fitted to the benchmark rows; (e) smoke green.
  A rule that misses its own +N from §2be by more than 2 rows is a **miss** and is re-sized, not re-justified.
- **Implementation bar for the four rules — MET 2026-10-12; the repair layer SHIPS (EVIDENCE_LOG §2bh).**
  `src/final_surface.py` gained `apply_diacritic_repairs` (sun-letter shadda, hamza fatha, long-vowel sukūn,
  dual nominative), called from `render_triple` after the clitic plane and gated on the token, with
  `repairs=False` as the attribution switch. **Frozen fidelity 463/973 = 47.6% → 583/973 = 59.9% (+120 rows,
  +12.3 pp)** — the exact number the sizing predicted. Against the pre-registered bar: overall **59.9% ≥ 55%** ✅;
  doubled **40.6% → 44.9%** (floor 36.2%) and **every class improved** — sound 55.9→69.3, hollow 24.0→44.0,
  defective 29.8→36.9, doubled 40.6→44.9, assimilated 27.8→31.5, quadriliteral 50.0→60.0 ✅; legacy
  `--weak-only` **34.7%** unchanged ✅; smoke and all gates exit 0 ✅. The `diacritic_only` bucket fell
  **159 → 39**; no other bucket in the taxonomy moved at all. `tools/diacritic_split.py --check` now also
  asserts the shipped **583**, so the prediction is a live regression test. `src/renderer.py` and
  `src/render_rules.py` are byte-identical to HEAD; `src/final_surface.py` is the deliberate implementation site.
- **NEXT LEVER — the tanwin family (202 rows, the largest remaining block): RE-SIZE BEFORE IMPLEMENTING.**
  `tanwin_missing` **149** + `tanwin_alif_acc` **53** = 202 rows, against the 39 rows now left in
  `diacritic_only`. Tanwin was rejected once at **+2.9 pp** (§2bb) against a ≥ +10 pp gate, but that
  measurement **predates Option A** — the definiteness input the rule needs (a proclitic `الـ` visible to the
  assembly layer) now exists. So: re-register the gate, re-size with the same discipline as §2be (measured net
  per sub-rule, dropped if ≤ 0, `unexplained` not force-fitted), and only then implement. The residual 39
  `diacritic_only` rows are second priority; the two dropped rules stay dropped
  (`apply_diptote_fatha` −34 needs a diptote LEXICON, not a suffix test — that is a data item, not a rule).
- **Tanwīn family re-sizing — GATE PRE-REGISTERED 2026-10-12, BEFORE the probe was written** (the whole
  point: a threshold chosen after seeing the number is not a threshold). Baseline is now the SHIPPED
  pipeline, **583/973 = 59.9%**; the family is `tanwin_missing` **149** + `tanwin_alif_acc` **53** = **202
  rows**, untouched by the repair layer (both counts identical before and after §2bh).
  **Gate: implement ONLY if the combined rule nets ≥ +50 rows (+5.1 pp, i.e. ≥ 633/973 = 65.0%)** on the
  frozen ruler, measured the §2be way. Below that it is recorded as dropped with its number and the next
  lever is chosen from what the residual actually is. Also required, exactly as for the repair layer:
  (a) **no class regresses** and the legacy `--weak-only` floor **≥ 34.7%** holds; (b) ≥ 90% of the 202 rows
  classified into named sub-rules, `unexplained` **not** force-fitted; (c) every sub-rule's net reported
  and any sub-rule with net ≤ 0 dropped with its number; (d) the definiteness input read from the TOKEN's
  proclitic via the single shared `final_surface.is_definite` — a legal input — and **never** from whether
  the gold happens to carry tanwīn; (e) deterministic, smoke green, gates exit 0.
  **Why re-size at all:** the family was rejected once at **+2.9 pp** (§2bb) against a ≥ +10 pp gate, but
  that measurement **predates Option A (§2bd)** — the proclitic visibility the rule needs is exactly what
  Option A added, so the old number is stale, not wrong.
- **Tanwīn re-sizing — MEASURED 2026-10-12; the gate is MISSED and the family is DROPPED (EVIDENCE_LOG §2bi).**
  `tools/tanwin_probe.py`, gate pre-registered before the tool was written. Family **202** rows (149 + 53),
  classified **100%** into two sub-rules that reproduce the taxonomy's own counts. Measured: doubling the final
  vowel on indefinites **−183** (142 fixed / 325 broken → 41.1%); accusative alif **+41** (72/31 → 64.1%);
  **combined −131 → 452 = 46.5%**. The gate wanted **≥ +50**; it missed by **181 rows**, so **nothing is
  implemented** — the doubling rule alone would have cost 183 rows, the largest avoidable regression found on
  this project. **§2bb's +2.9 pp is corrected:** it used *oracle* definiteness (a label, unavailable at
  inference); with the legal proclitic input the rule is −183. The accusative-alif sub-rule (+41) **gains but
  is sub-bar and stays unimplemented** — re-cutting a pre-registered gate to the sub-rule that clears it is
  what pre-registration exists to prevent.
- **Residual `diacritic_only` — DUMPED, CLASSIFIED, AND CLOSED 2026-10-12 (EVIDENCE_LOG §2bj).** The 39 rows
  were dumped mark-by-mark and classified: `diptote_case_vowel` 13 (needs a **lexicon** — the suffix version is
  −34), `redundant_hamza_kasra` 9, `other_extra_mark` 7 (5 = the corpus's unvowelled final `ت` of the perfect),
  `other_case_vowel` 5 (2 of them regressions of **our own dual rule**), `hamza_seat_vowel_missing` 3,
  `unexplained` 2. Both proposed families were **sized before being written** and both failed: initial-hamza
  alignment **−4**, perfect-suffix convention **−2**. **One rule was banked:** `repair_initial_hamza_seat` —
  identical rewrite to the −4 rule, gated on the seat being **token-initial** instead of proclitic-preceded
  (the 13 counterexamples ALL carry a proclitic: لِإِظْهَارِ, بِإِنْشَارِ, الْإِفْرَاطَ …) → **+9 fixed, 0 broken**,
  frozen **583 → 592 = 60.8%**, `diacritic_only` **39 → 30**, no class regressed, weak-only floor 34.7% held.
  Pin cascade handled: split `P_SHIPPED` 583 → 592 (four-rule figure stays 583); tanwin probe re-pinned
  (−183 → −189, −131 → −136, **verdict unchanged**). **The bucket is now closed: 9 of 39 were cleanly
  addressable, the other 30 are lexical (13 lexicon / 5 homographic / 3 hamza-seat / 7 corpus convention /
  2 shadda) and no surface lever of size remains in it.**
- **NEXT LEVER — HOLLOW GLIDE-COLOUR (the hand-off condition fired: 9 < 10 cleanly addressable).** Hollow sits
  at **44.0% with 56 failures** and is the only class-specific weak rule left: the open question is **glide
  deletion vs *mater* retention** in medial contraction (قَالَ vs قُلْتُ / يَقُلْ — the roadmap's original
  Phase-1 item 3, never sized). **Pre-register the gate before writing anything**, and size it the §2be way:
  per-sub-rule classification of the 56, measured net per candidate rule on the frozen ruler (baseline now
  **592**), drop any sub-rule with net ≤ 0, no class regresses, weak-only ≥ 34.7%, deterministic, smoke green.
  The roadmap's own claim for this item was **≥ 80%** for the hollow class — pre-register against *that*, and
  record the miss with its number if it misses.
- **HOLLOW GLIDE-COLOUR — GATE PRE-REGISTERED 2026-10-12, BEFORE the dump was written.** The target is the
  roadmap's own claim for this item (Phase-1 item 3, never sized): **hollow class ≥ 80%**. Baseline: hollow
  **44/100 = 44.0%** (56 failures), so the gate is **≥ +36 hollow rows**, i.e. **≥ 80/100**.
  **Implement ONLY if**, measured on the frozen ruler (overall baseline now **592/973 = 60.8%**):
  (a) the hollow class reaches **≥ 80%**; (b) **no other class regresses at all** and overall does not fall
  below 60.8%; (c) legacy `--weak-only` stays **≥ 34.7%**; (d) ≥ 90% of the 56 failures classified into named
  sub-rules, `unexplained` **not** force-fitted; (e) every sub-rule's net reported and any sub-rule with
  **net ≤ 0 dropped with its number**; (f) deterministic, smoke green, all gates exit 0.
  **Zero-loss exception, stated in advance so it is not invented later:** a sub-rule with **zero** counter-
  examples anywhere on the ruler is a strictly dominant move with no trade-off to decide, so it may ship on
  its own measurement (as `repair_initial_hamza_seat` did, §2bj) — but it does **not** discharge this gate,
  which is about the class as a whole.
  **If the gate misses, record the miss with its number and the class target is re-registered, never quietly
  dropped.**
- **HOLLOW GLIDE-COLOUR — MEASURED 2026-10-12; the ≥ 80% gate is MISSED and the class does NOT decompose
  (EVIDENCE_LOG §2bk).** `tools/hollow_probe.py`, gate pre-registered before the dump. 43 of the 56 failures are
  **letter-level**, and the two largest shapes are **opposite errors on the same radical**: a missing hamza seat
  where the human writes `ائ` (قَائِل for قَال, 18 rows, `فَاعِل`) and a retained mater where the human contracts
  (إشَارَة for إشَوَارَة, 2 rows). Measured: **blind seat rule −89** (4 fixed / 93 broken → hollow 25.0%);
  **position-aware seat rule net 0** (2/2); **`contract_mater` −2**; **BOTH → hollow 43/100 = 43.0%** vs the
  **≥ 80** gate. Classification reached only **55.4%** (< the pre-registered 90%) — the class has **no clean
  decomposition into named surface rules**. **Why:** the seat rows are mostly **compound** (seat + tanwīn, and
  tanwīn alone is −189), so no safe composition exists at the surface, and the contraction/apocope decision is
  morphological. **The class target is RE-REGISTERED, not dropped: hollow ≥ 80% now requires an input the
  renderer does not have.**
- **THE CONVERGED CONCLUSION — the next real lever is an INPUT, not a rule (both §2bi and §2bk point here).**
  Tanwīn needs **definiteness**; hollow needs the **glide's behaviour under the pattern's syllable structure**.
  Neither is a property of the string; both were pushed into a surface layer because that layer was cheap, and
  both now measure as unreachable there. The evidenced move is a **model head** (definiteness / morphology) of
  the same kind as the case head — predicted by the model, consumed by the renderer as a legal input, exactly
  as the token and case already are. **Pre-register its ceiling before training anything**, and note the
  standing rule: no GPU before the CPU instruments have been measured and the threshold written down.
- **SHIPPED 2026-10-13 (EVIDENCE_LOG §2bn).** The resource is **ON by default at the zero-loss setting (share ≥ 0.95)** in the live tree: shipped fidelity **592 → 695 = 71.4%**, no class below its pre-resource baseline, legacy `--weak-only` floor still **34.7%**, smoke green, and the new `tools/spelling_resource_probe.py --check` pins 695 / 592 / 756. The three surface-pipeline probes (`diacritic_split`, `tanwin_probe`, `hollow_probe`) now pin the new input **off** so their numbers keep their old meaning — the pin cascade fired and was handled, not bypassed. 
- **SELECTOR SHIPPED 2026-10-13 (EVIDENCE_LOG §2bo) — the gate is CLEARED.** `consult_case` returns the most frequent attested spelling whose last mark carries the **case head**; shipped as the default with the confidence rule behind it. Frozen ruler **695 → 827 = 85.0%** (fixed 213, broken 81, net **+132**), no class regresses, all six classes far above their pre-resource baselines (sound 84.2 · hollow 90.0 · defective 88.1 · doubled 85.5 · assimilated 79.6 · quadriliteral 85.0), and the number is **identical when the gold token's marks are erased** — legality pinned by `tools/spelling_resource_probe.py --check`. **The wazān's LETTERS as a filter were measured and rejected (−55 net: writers contract maters the pattern's literals prescribe).** The 81 counterexamples are named: `case=ABSTAIN` rows (nothing to constrain), the enclitic plane (حِصَّتُهُ), and tanwīn-versus-construct (بِشَارِبِ/بِشَارِبٍ) — the last one being **definiteness**, so §7's missing input is now the ONLY named blocker standing between 85.0% and the ceiling.
  The **0.55** setting (756 = 77.7%) is measured but **not** shipped: 60 unexplained counterexamples make it a decision, not a shipment. `data/resources/` is gitignored — the index is copyleft-derived and is never committed.
- **THE INPUT ARRIVED, AND IT NEEDED NO GPU — MEASURED 2026-10-13 (EVIDENCE_LOG §2bl; harness `G:/aide-harness`).**
  The missing thing turned out not to be a model head but a **resource consulted at render time**, built from
  *other text*: a skeleton→spelling index over `data/raw/tashkeela-books.jsonl` (97 books, **66,190,991 tokens**,
  433,167 skeletons), keyed by the token's **skeleton** — already a legal input. Frozen ruler: **592 → 695 =
  71.4%** at the zero-loss setting (share ≥ 0.95: **+103 rows, 0 broken, all six classes improve**) and **→ 756
  = 77.7%** at share ≥ 0.55 (**net +164, no class regression**) — the largest single gain recorded on this
  project (the four shipped repair rules together were +120). Verified with
  `tools/renderer_bench_audit.py --engine v3` in the sandbox copy, and **invariant to the gold token's
  diacritics** (`A − B = 0` at both settings), so the gain cannot be circular. The leakage duty was discharged
  *before* the number was believed: 2 of 40 of the ruler's own source sentences appear in that corpus (**5%**) —
  it is other text, not the answer key. **The ceiling of this route is 100%, not 74%:** the human's exact
  spelling is among the corpus candidates for **973/973** rows. The hook is inert unless
  `ARABIC_SPELLING_RESOURCE=1`; with it off every existing instrument still prints **592** (measured, and both
  `--check` probes plus smoke remain green).
- **NEXT LEVER — THE SELECTOR (gate pre-registered below, before implementing).** The resource does not fix rows
  by itself: the median skeleton carries **5** attested spellings and only **14.3%** have exactly one, so the
  remaining **217 rows to the ceiling are a *selection* problem, not a coverage problem**. Measured so far:
  unconditional most-frequent **702** (FAILS — `sound` 69.3% < 70.3%), corpus-unanimous-only **642**, share ≥ 0.95
  **695**, **share ≥ 0.55 → 756** (peak of the sweep t ∈ [0.45, 1.0]; both edges worse: 0.45 → +131, 0.95 → +103).
  *Hypothesis:* the wazān pattern and the case head are legal inputs that can rule candidates **out** — a
  candidate whose vocalisation contradicts the pattern's radical slots or the case vowel is not admissible — so
  pattern-conditioned selection beats 756. *Metric:* `stem_correct` on the frozen ruler, reported as
  fixed / broken / net with per-class deltas. *Split:* the frozen 973 rows (the resource comes from another
  corpus; that is the only split this lever has). *Acceptance threshold, pre-registered and structural:*
  **net > 0, no class below its baseline, no read of the gold token's diacritics** (the invariance test is the
  check), and to be worth the change **≥ +25 rows over 756**, i.e. **≥ 781/973 = 80.3%**. *Next command:*
  `python G:/aide-harness/sweep_selector.py` (re-derives the whole curve in seconds from the persisted index)
  and `python G:/aide-harness/diagnose_zero_loss.py --t 0.55`, then **write the pattern-conditioned selector —
  it does not exist yet.** CPU-only by construction: no GPU spend.
- **Not displaced by §2bl:** the diptote lexicon (13 rows) and the corpus convention on the perfect's final `ت`
  (7 rows) remain data items, and `accusative_alif` (**+41**, 73/32) is partly answered by orthographic evidence
  now (§2bl fixes several of exactly those rows). The **model-head** route above is a *different* lever from a
  consulted resource: the 217 rows the resource is silent on are where a predicted definiteness/morphology head
  would have to earn its keep.
- **TWO NEXT LEVERS — GATES PRE-REGISTERED 2026-10-13, BEFORE EITHER PROBE WAS WRITTEN.** The shipped 827
  leaves **146 rows**, and §2bo already named why they are missed. The two smallest of those reasons are now
  sized as levers. Both are **legal** (root, wazān pattern, case, the token's SKELETON, the attested corpus
  candidates and **the pipeline's own output** are all legal inputs; a probe may read the gold token's marks
  **to score, never to choose**) and both are **CPU-only: zero GPU, nothing trained.**
  **(A) The ABSTAIN half — the renderer prior as a tie-break.** Where `consult_case` finds nothing to constrain
  (the annotation abstains, or no attested candidate carries the case head) the selector silently degrades to
  raw frequency. *Hypothesis:* among attested candidates, the one **closest to the pipeline's own output** is
  the better reading — the renderer is a second, legal opinion, and §13 already lists this as the
  "renderer prior" lever. *Gate:* implement ONLY if it nets **≥ +15 rows over the shipped 827**
  (≥ **842/973 = 86.5%**), **no class regresses**, the invariance test stays **A − B = 0**, legacy
  `--weak-only` **≥ 34.7%**, smoke green. The standing **zero-loss exception** applies unchanged: a sub-rule
  with **zero** counterexamples anywhere on the ruler is strictly dominant and may ship on its own number
  (as `repair_initial_hamza_seat` did, §2bj).
  **(B) The DEFINITENESS half — SIZE THE CEILING ONLY; build nothing.** `بِشَارِبِ` / `بِشَارِبٍ` disagree in
  letters not at all, in case not at all, and in the final mark **only** by tanwīn (definite construct vs
  indefinite). The case head *cannot* separate them and **definiteness would** — §7, §2bi, §2bk and §2bo all
  converge on this one input. *Gate, registered before the count is known:* if the rows whose gold is
  separated from the shipped output by **that distinction alone** number **≥ 60** (≥ 6% of the ruler), the
  definiteness head is worth pre-registering as a model head and a ceiling is derived for it; if **< 40**, the
  model-head route is **DROPPED with its number**, and the honest conclusion is that the last 146 rows do not
  justify a training run. Cutting the gap between 40 and 60 after seeing the number is exactly what
  pre-registration exists to prevent.
  *Next command:* `python G:/aide-harness/abstain_probe.py --json dist/audit-2026-10-13/abstain.json` — which
  **does not exist until it is written immediately after this paragraph.** It measures both levers through the
  **shipped hook** (`final_surface.apply_spelling_resource`, not a re-implementation) and asserts the 827 it
  starts from *is* the shipped 827.
- **BOTH GATES MEASURED 2026-10-13 (EVIDENCE_LOG §2bp) — VERDICTS RECORDED; NOTHING SHIPPED, NOTHING SPENT.**
  `G:/aide-harness/abstain_probe.py` re-derived the shipped **827** through the shipped hook (asserted before it
  would report anything) and **enumerated all 146 misses for the first time**: `abstain` **50** · `definiteness`
  **40** · `case head rejects the gold` **28** · `other rank loss` **17** · `gold unattested` **11** — with **117
  of the 146 structurally beyond ANY case-head rule** (the case head is satisfied by the shipped output *and* by
  the gold reading, so no rule of that kind can separate them).
  **(A) MISSED — not shipped.** The renderer-prior tie-break nets **+10 (837/973 = 86.0%, fixed 13 / broken 3,
  changed 42)** against a **≥ +15** gate: misses by **5 rows**, and it is **not zero-loss**, so the
  strict-dominance exception does not apply either. **Why — measured, not argued:** it only ever fires on the
  **42 rows where the renderer's own output is not itself an attested candidate** (it is attested for 931/973),
  and on the ABSTAIN rows it changes **0 of 203** because for **all 203 the renderer's output IS the corpus's
  most-frequent spelling** (`abstain_base_is_top = 203/203`) — one opinion, not two; there is no tie to break.
  Recorded with its number.
  **(B) IN THE GAP — the PI decides, and the gap is NOT re-cut here.** The definiteness-only class is **40 rows**
  against a gate of **≥ 60 pre-register / < 40 drop**. On all 40 the case head accepts **both** readings, so the
  distinction is invisible to it *by construction* (GEN admits kasra and kasratān alike).
  **(NEW, and the most actionable result of the round):** the 28-row class is the **rule** refusing a correct
  reading — **diptotes** (مَسَاجِدَ · بِأَفْعَلَ · لِآخَرَ · لُبَابَةَ: fatha in the genitive, **no tanwīn**) plus
  the enclitic plane (مُرَادَهُ, where the case mark is not on the final visible letter at all). A **third,
  independent confirmation of DATA ITEM #1 (a diptote lexicon)** — now with a **measured ceiling of up to 28
  rows**; the enclitic rows belong to the plumbing item instead.
  **Consequence:** the residual is **no longer a selection problem**. 117 rows want an input the case head does
  not model: definiteness (40, a head — the PI's call above), diptote government (28, a lexicon), and the
  clitic plane reaching the renderer. Re-measure any time in seconds with
  `python G:/aide-harness/abstain_probe.py --json <out>`; the class dump is `python G:/aide-harness/diag_abstain.py`.
- **THE FIRST END-TO-END MEASUREMENT — 2026-10-13 (EVIDENCE_LOG §2bq; harness `end_to_end_probe.py`).**
  The renderer has only ever been measured with the HUMAN's analysis. Asked what the shipped system actually
  does, the model is now in the loop on the only context-bearing human gold (`gold-tashkeela-300.jsonl`;
  the frozen ruler has **no `context` field**, so it structurally cannot answer this). Checkpoint
  `dist/drive-preflight/gold-baseline-s20261009.pt`, vocabulary rebuilt from the checkpoint's own embedded vocab
  and **asserted** against its recorded sizes (the local build differs: 15662/3599/77 vs 20000/6633/86 — the
  shipped `.pt` files do not match the current `data/out`).
  **Measured:** root whole-exact **29.5%** (in-vocab 34.5 / OOV 16.0) · wazān raw **11.9%** — **below the
  constant `1َ2ْ3` baseline of 12.9%** · case 61.7% · **root+pattern 5.0%** · **TRIPLE 2.7%** ·
  **end-to-end 52.0% with the corpus resource, 2.7% with it off.** Of the **292 rows with a WRONG triple, 150
  are nevertheless correct**, because the resource keys on the TOKEN's skeleton and not on the analysis.
  **Meaning: the end-to-end number is carried by a token-keyed lookup, not by root-graph planning. The renderer
  is not the bottleneck (75% conditional on a right triple; 85.0% on the ruler) — the PLANNER is (2.7%).**
  Untrained control through the identical path: 27.0% end-to-end, 0.000 on both heads.
  **This re-orders item 9's own residual work: rendering 146 ruled rows and a 28-row diptote class is low value
  next to whether the planner can emit a triple at all.** Next: the same probe on the **treatment** arm and the
  other two seeds (v14/v15/v26), and only then any further renderer polish.
- **UN-TRAPPING THE RESOURCE + SOFTENING THE SELECTOR — GATES PRE-REGISTERED 2026-10-13, BEFORE THE PROBE.**
  §2bs measured the shipped case-aware selector at **-15.3 points end-to-end** (52.0% shipped vs 68.3% with the
  case constraint removed entirely) while it remains **+132 rows on the frozen ruler** — because the ruler hands
  it the **HUMAN's** case and production hands it a **61.7%-accurate predicted** one. So a *hard* filter fed a
  *noisy* head throws the corpus's dominant spelling away on 38.3% of rows by construction.
  **(E) THE SOFT SELECTOR.** *Hypothesis:* keep the corpus's dominant spelling unless the case-admissible
  candidate is itself well attested — a **soft prior** instead of a hard veto. *Gate, BOTH legs must hold:*
  (i) the frozen ruler stays **>= 827/973** with **no class below its shipped baseline** (the shipped contract),
  and (ii) the 300-row end-to-end gold rises **above 53.0%** (the un-trapped level) and toward 68.3%.
  **A variant that wins on one leg and loses on the other is a DECISION, not a shipment, and goes to the PI** —
  that is exactly the shape of the mistake §2bo made, so it is the shape the gate now forbids.
  Variants measured in one pass: `hard` (shipped) · `case-if-share>=t` for t in {0.5, 0.7, 0.9} ·
  `soft` score `log10(count) + lambda*case_ok` for lambda in {1..5} · `mode-first` (use the case-admissible
  candidate only when the modal spelling does NOT already carry the case head) · `frequency-first` (the 68.3%
  baseline, which is known to score 702/973 = 72.1% on the ruler — so the trade-off is explicit).
  **(F) THE `render_triple` EARLY-EXIT BUG.** A fallback must be a true fallback: `render_triple` returns
  `None` when the digit engine fails, so the **token-keyed resource — which does not depend on the renderer at
  all — is never consulted**. *Gate:* the +3 rows (52.0 -> 53.0%) reproduce on the 300-row gold, and the ruler
  is **unchanged** (its coverage is 100% by construction, so the fix must be a measured no-op there; a change
  would mean the fix touched something else).
  **(G) ROOT PREFIX-SHIFT — measurement only, no gate.** Does the predicted root absorb a MAZID prefix letter
  (`ت ي م ا ن`) into slot 1, and how often is the gold root a contiguous window of the prediction? This is the
  review's hypothesis that "a prefix treated as R1 shifts the whole sequence"; it is measured, not assumed.
  *Next command:* `python G:/aide-harness/selector_soft_probe.py` — written immediately after this paragraph.
  CPU only, no GPU, nothing trained.
- **THE ENCLITIC-AWARE CASE BOUNDARY — GATE PRE-REGISTERED 2026-10-13, BEFORE THE PROBE.** §2bu left exactly
  one regression standing: **−1.4 on `doubled`**, invariant across λ ∈ [0.9, 2.0] *and* every gate setting —
  and every lost row was an **enclitic-plane** row (`عَبْدَهُ`, `عُمْرُهَا`, `إحْجَاجِهَا`, `مُرْسِلَ`).
  *Diagnosis:* `case_marks_ok` reads the **TOKEN's** last mark, and on a token carrying a pronominal enclitic
  that mark is the **enclitic's** vowel (the ـهُ / ـهَا), not the case — so the case test is blind exactly
  where the enclitic sits, the hard filter falls through to the renderer's stem (which the metric credits by a
  legal affix split) and the soft rule pays for the blindness by answering from the corpus.
  *Change:* evaluate the case head on the **stem** — cut the candidate at the enclitic boundary with the
  project's own affix logic (`final_surface.pronominal_enclitic` + the same `_cut_at_letter` the metric
  itself uses) and read the last mark of what remains. Reusing the metric's own enclitic test is deliberate:
  §2bd's lesson is that a second implementation of "what counts as an enclitic" *will* disagree where it
  matters.
  *Gate — all three must hold:*
  (i) **frozen ruler ≥ 827/973** with **no class below its shipped baseline**, i.e. the `doubled` −1.4 must
  become **≤ 0.0**;
  (ii) **end-to-end on the 300-row contextual gold ≥ 159/300 (53.0%)** and in the direction of the
  **213–218** band the soft selector reached, i.e. the majority of the +54…+59 rows must survive;
  (iii) the 15 lost enclitic rows must be **recovered, or fall back lawfully** to the renderer's stem (which
  the metric credits through a legal affix split).
  *A variant meeting all three is a STRICT PARETO IMPROVEMENT and ships; one missing any is a DECISION for
  the PI.* Measured in the same pass, so the choice is informed rather than asserted: the same family with the
  boundary-aware test on the **hard** filter (does the shipped 827 itself improve?), and a
  **`soft+fallthrough`** variant that returns `None` — falling back to the renderer — when **no** candidate
  carries the case head at all, so the soft rule cannot answer from the corpus on rows where the case has
  nothing to say. CPU only, zero GPU, nothing trained.
  *Next command:* `python G:/aide-harness/enclitic_boundary_probe.py` — written immediately after this paragraph.
- **HEAD-3 WAZĀN PRUNE + RETRAIN — GATE PRE-REGISTERED 2026-10-13, BEFORE ANY GPU IS TOUCHED.** The CPU side is
  **DONE and asserts clean**: `src/build_wazan_inventory_pruned.py` builds the **tail-stripped, supervised-only**
  inventory and **REFUSES** on any of a trailing inflection run, an unsupervised class inside the inventory, or
  a source token the inventory cannot map. Measured (200k rows/source): **1,551 classes, 647 of them covering
  99% of 226,148 supervised tokens**; at the training limit (`limit_train=120000`) the same build gives
  **1,325 / 627** (§2bu). A vocabulary built naively from the `t_wazan` **FIELD** would hold **2,062 classes,
  511 of them NEVER supervised (24.8%)** — the measured size of the zombie registry this prune removes.
  **Correction to the criterion as stated:** "≤ 627" is the *99%-coverage subset*, not the inventory, **and it
  is REJECTED as the target** (PI decision, 2026-10-13): an **UNK bucket in a generative target space is a
  guaranteed structural miss**, because `render_triple(root, UNK, case)` has no fallback and drops the token out
  of the pipeline — you do not inject a certain 1% failure to save ~700 logits. **The locked target is the FULL
  supervised inventory, and §2by established that its SIZE IS A FUNCTION OF THE CORPUS, not of a row limit:
  the run's own vocabulary is the UNION — `Vocabs(GOLD_TR + SILV_TR)` with gold at `limit_train` (120,000) and
  silver in FULL (1,871,205 records) — which is **2,099 classes, 2,100 with `<pad>`**. `train.py`'s own build
  from the single file it is handed is 1,032 (1,033), and **the 1,325 / 1,551 figures were MISALIGNED builds
  that read silver at 120k** — the wrong read. Zero UNK mappings, zero dead rows, zero trailing runs.** The old
  head's pathology was never arithmetic — 46% of its rows were ghosts receiving no gradient and 63% carried
  trailing inflection junk; 2,099 classes where 100% of rows are supervised and clean removes it entirely.
  **Pre-registered criteria for the retrained checkpoint — ALL must hold:**
  **(T) target sanity, CPU, before training.** The inventory asserts clean; zero trailing runs; and the
  checkpoint's Head-3 output dimension EQUALS the union inventory size + `<pad>` = **2,100 exactly**, with
  **zero dead/unsupervised rows**: `python src/build_wazan_inventory_pruned.py --check --ckpt <pt>` exits **0**.
  (Teeth re-verified after §2by with a three-branch test, `G:/aide-harness/teeth_check.py` — **3/3 OK**: dead
  rows exit 1, a dim that disagrees with the checkpoint's own vocab exits 1, and a gold-only checkpoint exits
  **0** with a corpus NOTE, i.e. no false alarm. The claim this line used to make named a shipped
  `gold-baseline-s20261009.pt`; **no `.pt` exists anywhere in the tree now**, so that artifact-based claim could
  not be re-run and was replaced rather than repeated.) The
  check now asserts self-consistency FIRST (`dim == len(ckpt vocab['wazan'])` — a property of the file, which
  cannot false-alarm) and treats a corpus mismatch as a NOTE, failing only on a class the corpus never
  supervises. Floor on the ruler is unaffected: (T) is a dimension check, not a metric.
  **(W) the wazān head, on the 300-row context-bearing gold — floors RE-REGISTERED in the NEW label space.**
  The old "**> 12.9%**" belonged to the FULL-label space and is **not comparable** to a head trained on
  tail-stripped classes. Re-derived in the stripped space on the same 278 rows: the constant `1َ2ْ3` predictor
  scores **46/278 = 16.5%** and the shipped head already sits at **43/278 = 15.5%** — so **a gate of "> 12.9%"
  would be PASSED by a head that still loses to the constant predictor in its own space**. The floor is
  therefore **beat 16.5%** (the constant, measured in the space the head now predicts in) and the real target
  remains **skeleton-equal ≥ 65.0%** against the current 42.4%.
  **(E) end-to-end.** Triple-exact **≥ 15.0%** (from 2.7%); **resource OFF ≥ 15.0%**; and **resource ON must not
  regress below 208/300 = 69.3%** — the §2bv shipped number, which the retrain may not spend.
  **Standing rules, unchanged:** no GPU before the gate is written (it now is) and the CPU build asserts; a miss
  is recorded **with its number** and never re-justified; the frozen ruler's **838** is the regression floor for
  anything touching the renderer, and the retrain must not touch `render_triple`.
- **DATA ITEMS (not rules), in priority order:** (1) a **diptote lexicon** — `apply_diptote_fatha` is −34 purely
  because a suffix test is not a diptote test; 13 residual rows want it; (2) `accusative_alif` (**+41**, 73/32)
  if a future round registers a gate it can honestly be measured against; (3) the **corpus convention** on the
  perfect's final `ت` (7 residual rows) — a convention question for the annotator, not a rule to guess.
- **Threshold re-registration (PI decision, 2026-10-12): moved to the frozen ruler.** §2az's Phase-2 target
  ("weak radical re-realization: clitic-aware ≥ 55%") was pre-registered on the **300-row** gold, where v3
  scores **34.7%** of 98 weak rows. Restated on the frozen ruler and named as such: **overall fidelity
  ≥ 55% on the 973 adjudicated rows (baseline 45.6%)**, with the legacy `measure_renderer_gold --weak-only`
  kept as a secondary like-for-like instrument (baseline **34.7%**). Both numbers are quoted together,
  always — the ruler is part of the number.
- **Do not:** quote the PADT per-class rates (`hollow 44.2% / hamza 53.5% / defective 62.0%`) as the renderer's
  fidelity baseline — half of that credit is the hybrid **table returning the memorised undiacritized PADT
  `FORM` verbatim** (§2ba §1); treat the current renderer as universal Arabic generation.
- **§2cm (2026-10-14) — THREE OF §2cl's FOUR RESIDUAL LEVERS ARE CLOSED, +6 / -0.** Measured on the ceiling
  path (gold-300, gold MorphPlan, resource OFF): **66.5% → 68.7% (+6 fixed, -0 broken)**; the frozen ruler is
  **unchanged at 568** (stem-level, resource OFF) and the resource-ON path is **bit-identical** (80.6% / 86.1%).
  So this is competence on the **rule-only** path — the quantity §2cg's verdict says binds — not a change to the
  shipped dictionary path. Closed: **#1 hollow contraction at the stem/tail seam** (قُوْل + ْتُ → قُلْتُ, +1);
  **#2 the divine name**, `repair_divine_name` (اللَّه, **+3** — the class is 9 rows but **6 of the gold
  spellings are bare** `اللهِ`, so 3/9 is this instrument's ceiling for it); **#3 two proclitics** in the affix
  frame (+2), gated to the measured chains `PRO2 = (و,س) (ف,س) (ل,ل)` plus sun-letter assimilation for لِ+الْ —
  **the ungated version measured −4 on the ruler** (`فَلْيُدْمِنْ`: that ل is the jussive lām; `لِلتَّاجِرِ`:
  assimilation). 30/30 self-tests. **The defective-R3 half of this census was then taken in §2cn** — the
  `other` bucket was only part of it (30 nāqiṣ rows, +16); see the §2cn item below.
- **CLOSED 2026-10-14 (§2cn) — the gate was not merely stale: it was REPORTING A REAL REGRESSION, and it is
  repaired.** `G:/aide-harness/attribute_2cn.py`: with the affix plane switched OFF, the SAME code reproduces
  the pinned **592/973 exactly** ⇒ the whole 592 → 568 movement was §2ce's affix plane emitting `الْ`
  unconditionally. That is not a member of `candidates(gold)` for a sun-initial definite noun (`الطَّحْنِ`),
  so it converted **24 rows the bare stem was passing by the metric's affix-split leniency into hard
  misses**. Fixed at the source by lām assimilation. The plane is now **PINNED OFF** in the surface probes
  (`diacritic_split`, `tanwin_probe`), exactly as the resource already was — 10 drifts → 3 — and the
  remaining +3 was re-pinned in all three probes with the **deltas asserted identical** (595−466 = 129 =
  592−463; 586−466 = 120 = 583−463), i.e. a better starting renderer, not a moved verdict.
  **`diacritic_split --check`, `hollow_probe --check`, `tanwin_probe --check`, `smoke_test` all exit 0.**
- **§2cn (2026-10-14) — THE NĀQIṢ DUMP: 30 rows, five mechanisms, +16 / -0.** Corrects the premise in two
  directions: `other` is the classifier's FALLBACK bucket (23 rows, only 14 weak-R3), while the real nāqiṣ
  population is **30**; and the A–E partition has **two EMPTY buckets** (D vocalic tails, E consonant tails
  — the corpus's defective tokens are bare-stem forms). Measured: gold-300 **68.7% → 74.5%** (+16, -0);
  ruler **568 → 631** (+63, -0); resource-ON **bit-identical**. Per-rule, each toggled without editing the
  source: **lām assimilation +61 ruler / +8 gold** (incl. the 24-row §2ce repair), **the seam weak-letter
  replacement +6 gold**, **`align_weak_r3` +2/+3** — the pattern's own vowel before slot 3 selects **ي**
  (…ِ3: قَاضِي, الثَّانِي, يَنْفِي) vs **ى** (…َ3: مُسْتَثْنَى, تَعَالَى), an exact correlation over the
  population with the wazān as the legal input. **Remainder, named:** ~6 rows are MAHMŪZ (the root field
  folds ء→ا, so no template can know) — **the hamza seat read off the TOKEN is the largest reachable family
  left, and the same shape of rule as the affix plane**; ~3 need **definiteness**; and **B164's gold target
  is literally `تَعَالَى(1/4`** — a page marker leaked into the token, unfixable by any rule and needing
  adjudication. The honest ceiling is **+16 rows**, not the +23 the bucket size suggested.
- **§2co (2026-10-14) — THE HAMZA SEAT, READ OFF THE INPUT TOKEN: +12 / -0 (gold-300 78.8%, ruler 66.7%).**
  The premise is confirmed by dump: root extraction folds ء to bare ا (93.9% bare-alef roots), so a numeral
  template writes a bare ا where a SEAT belongs — but a seat is a **consonant in the unvocalized rasm**, so of
  the 71 misses **25 carry one in the gold token**. `project_hamza_from_input()` accepts an edit script only
  when EVERY difference is a seat repair (SUB `{ا,و,ي}∪seats -> seat`; DEL a bare ا beside a seat, which is
  the renderer doubling the radical `إا -> إ`), runs BEFORE the affix plane so the frame can still match, and
  never touches a mark. **The manqūṣ-indefinite rule pays +1** (B129 مُقْتَضِيًا) — and its CEILING with a
  perfect case head is **+9, all of which are the case-vowel family, NOT manqūṣ** (طَلْحَةَ، سَلَمَةَ،
  ثَلَاثَةَ، وَقَالَ، تَخَافُ …). So the honest reading is inverted from the obvious one: **the case head is
  the lever that pays**, and that is a pre-registerable GPU-relevant target, not a surface rule. Three probes
  re-pinned (verdicts unchanged: `accusative_alif` still +41, hollow ≥80% still missed by 33); the tanwīn
  family moved 202 → **211** (+9: fixing the letters exposed marks-only failures, the same direction as the
  `diacritic_only` bucket's 159 → 164). All five gates exit 0; 46/46
  self-tests. **Remaining, named:** a re-rendering class where the seat is right and the renderer's VOWEL is
  stranded (مِائَة → our مِاَئَة), and the "targets that are not fully vocalised" bucket (the six bare
  `اللهِ` rows, B031/B230/B250, and `تَعَالَى(1/4`) — which the FROZEN RULER keeps scoring as they are; a
  noise-adjusted figure is a paper annotation, never a change to `stem_match`.
- **🚩 BLOCKER (2026-10-14, §2cp) — THE (E) LEG'S INSTRUMENT WAS NOT REPRODUCIBLE, SO THE "<4%" IS NOT A
  MEASUREMENT.** `end_to_end_probe.py` seeded `torch.manual_seed(0)` **after** `Arm()` was constructed, so
  the 9 tensors absent from EVERY v20 checkpoint (incl. `char_encoder.char_pos` / `pool_gate`, which are in
  the INPUT PATHWAY) were re-randomised each run. Two identical runs, same checkpoint: root **31 vs 36**/278,
  case **113 vs 117**/222, TRIPLE **0 vs 2**/300 — while the CONTROL (built after the seed) was
  **bit-identical at 165/300**. Seed moved before construction; two runs now agree byte-for-byte, giving the
  stable reading **TRIPLE 3/300, resource-OFF 4/300, resource-ON 190/300** — lower than the recorded 16 / 11.
  **Not this session's renderer work** (TRIPLE never touches the renderer; stashing `src/final_surface.py`
  leaves it at 1/300); candidates are §2ci's `case_gov_v` zero-init and §2cf's merge, but **no attribution is
  defensible yet** — even seeded, an absent tensor is a random value, and the honest repair is
  `model_arms.load_for_eval` (built in §2ci, not yet used by this probe). The verdict's own control clause is
  also unsound: the control reads **165** (was 193; §2ch-ERRATA blames the `causal:false` flip) and the two
  arms are built from DIFFERENT configs (`ck_cfg` vs `cfg`), so the headline inverts (model 190 vs control 165).
  **RESOLVED 2026-10-14 (§2cq) — and the blocker was MISDIAGNOSED.** The recorded 16/300 and 11/300 were
  MEASUREMENTS, not draws: the current `src/model_arms.py` cannot construct a v20 checkpoint at all
  (`KeyError: 'wazan_canonical'`; 19 tensors it never had), so the probe was reading a FABRICATED model, and
  seeding made that error *reproducible* rather than fixing it (`load_for_eval` is the worse of the two bad
  loaders on 4/4 arms — it disables a `char_encoder` that is 7/10 present and fully trained). The faithful
  reader is on disk — `dist/_overwrite_proof/src/` (all 71 files, 2026-10-13 13:03) loads every v20 checkpoint
  with **0 missing / 0 unexpected** — and it reproduces the recorded numbers TO THE ROW on 3/3 arms
  (root 67/136/159, TRIPLE 5/18/16, resource-OFF 5/14/11). **The planner's real number is root
  159/278 = 57.2%, not 13%.** Four-arm faithful map (resource OFF, `dist/runs/v20/faithful_*.txt`):
  gold-baseline 89/278 · gold-treatment 67/278 · silver-baseline 136/278 · silver-treatment 159/278;
  TRIPLE 8/5/18/16 of 278; e2e token-exact 4/1/2/3 of 300. **§2cp is RETRACTED** (banner in place, 3 lines;
  0 lines removed).
  **(E) re-derived on the faithful instrument — UNCHANGED, and now sound:** TRIPLE 5.3% vs ≥15% FAIL ·
  resource-OFF 3.7% vs ≥15% FAIL · resource-ON 191/300 vs ≥208 FAIL. The resource-ON clause now rests on a
  sharper control than the one it replaced: `gold-baseline` scores **202/300 resource-ON while its root head
  is a memoiser** — the leg does not measure the planner at all.
  `treatment_tower_hidden` **SETTLED**: the checkpoint's own `cfg` and its `tower.net.0` both read **10018**,
  so the artifact IS a 10018 model and the notebook's 10018 gate is correct *for this artifact*; the `null`
  change is code-side and yields a DIFFERENT model, so the two are not comparable and the payload stays stale
  until a retrain.
  **Corrected order of work: (1) DONE — instrument repaired by measurement. (2) STANDING HAZARD: no probe may
  report a forward-pass number through the current `src/model_arms.py` until it can load a v20 checkpoint —
  it would be measuring a model that never existed. (3) PI DECISION, both columns reported: leg 1's TRIPLE
  metric space — `wazan RAW` (17.6%, barely over the constant's 16.5% floor) vs `wazan radical SLOTS` (98.9%),
  which §2au already established is the notation-insensitive one. That is a RULER change and is NOT applied
  here. (4) ONLY THEN the case head (§2co ceiling +9) or a retrain — now justified by a specific measured
  defect (root OOV 0/75 in every configuration), not by a contaminated number.**
  **⚠ THAT LAST CLAUSE IS RETRACTED 2026-10-14 (§2cr).** `root OOV = 0/75` was measured on the EIGHT
  FABRICATED loads of §2cq's map, not on the planner. Loaded faithfully, OOV whole-root is
  **20.6 / 8.0 / 10.7 / 16.0 %** across the four arms against in-vocab **43.8 / 30.0 / 63.1 / 72.4 %** —
  a real gap of about 1/4 to 1/5 of in-vocab, not a total failure. A retrain is no longer justified by
  that number.
- **§2cr (2026-10-14) — THE DIAGNOSIS SHIPS: THE BINDING COMPONENT IS THE WAZAN NOTATION SPACE, AND THE
  98% TARGET IS CAPPED BY THE COMPILER.** `python src/diagnose_architecture.py --verify-legacy` reproduces
  the recording to the row. Component census on gold-300 (faithful, resource OFF) and the marginal gain
  from lifting ONE component to its own ceiling on silver-treatment's 215 fully-labelled rows (shipped
  conjunction there = **7.4%**, i.e. the recording's 16 rows on a different denominator):
  **+24.7 pp NOTATION** (the same wazan output scored as a radical slot-SET) · +22.8 wazān→oracle ·
  +5.3 case→oracle · +3.5 root→oracle · **+0.0 root ARITY** (retires the decode-conditioning hypothesis).
  So the lever is **not capacity and not the trunk**: the head already knows the pattern (raw 17.6% vs
  slot-set 98.9% on the SAME rows and weights), and the notation-free head (`h_wazan_canonical`, §2cf)
  **already exists in the current architecture and has never been trained** — it is one of the 19 tensors
  absent from every v20 checkpoint. Second finding: **the case head on the best arm is BELOW the always-GEN
  floor** (115/222 = 51.8% vs 122/222 = 55.0%), and the two treatment arms are the WORSE two on case
  (62.2 / 60.4 / 56.8 / 51.8%) — mis-trained, not weak — with the frozen-trunk probe agreeing (silver arms'
  case probe is AT or BELOW base rate: 0.531 / 0.473 vs 0.550). Third: **the compiler caps everything** —
  gold plan gives **191/300 = 63.7% rule-only, 245/300 = 81.7% with the dictionary**, and the resource-ON
  leg is **ANTI-correlated with planner quality** (worst arm 207, best 191), which is the cleanest proof of
  the §2cg claim. **Therefore 98% end-to-end is unreachable by improving the planner at all** — it must be
  stated against a raised compiler ceiling or a different input. Two instrument defects were caught before
  shipping by a structurally impossible number (a WORSE arm scoring 207 vs the best's 15): an ORDER bug (the
  resource axis was never measured; `resource CHANGED rows` is now printed) and the oracle-token hypothesis,
  which the measurement **REFUTED** (gold-form and context-token renders are identical on all 8 legs, both
  tokens sharing one skeleton). Ships with three gates: `--verify-legacy`, `make_notebook_diag.py --check`
  (freshness vs the working tree, sabotage-tested), and `ast.parse` on every notebook cell.
  Artifacts: `src/legacy_arch.py`, `src/diagnose_architecture.py`, `src/make_notebook_diag.py`,
  `notebooks/diagnose-architecture.ipynb` (CPU-only by design — `enableGpu: false`), and
  `dist/runs/v20/diagnose_architecture.{txt,json}`.


- **§2cs (2026-10-14) — THE `stem_tail` CLASS SPACE IS SIZED FROM A 278-ROW SAMPLE: THE RULER IS CAPPED AT
  98.2%, AND A MEASURABLE BRIDGE REPAIRS 37,570 WRONG LABELS.** Sized before implementing (working tree:
  the whole `stem_tail` head is the concurrent agent's uncommitted work, 8 dirty files under `src/`).
  **Scope, not content, is the defect.** `STEM_TAIL_VOCALIZED` (30 classes, `''` at index 0) was measured
  as `trailing_run` over **the 278 usable gold rows**, so it is exact for its source (gold-300 0% out) and
  under-covers PADT **16.7%**, silver **8.4%**, and the **frozen ruler 18/1000**.
  **The cap:** a space cannot render a tail it lacks, so the ruler's representable ceiling is
  **982/1000 = 98.2%** today, **990/1000 = 99.0%** with the bridge, **999/1000 = 99.9%** with 3 added
  classes (`َا`, `َى`, `َتَيْن`), and the last row (`َّتْ`) is a TIE the notation cannot resolve.
  **The bridge** is a rule, not a row list: base-letter equality, a shadda **before the tail's first base
  letter** moves to the stem (`ُّوا`→`ُوا`) while one **after** it stays (the nisbah `ِيّ`), and the
  variant's marks must be a **sub-multiset** of the candidate's (we add only what the ruler spells out;
  deleting a mark is refused). Mappings are traceable and were **not** hand-picked.
  **The accounting:** repaired **37,570**, masked to `IGNORE` **75,278** (TIE 34,455 / NEW 40,387 /
  JUNK 436), **broken 0** — every changed row carries class 0 today, which is wrong for each of them, so
  no right label is altered. `broken = 0` is measured, not asserted.
  The NEW bucket is **genuine compound morphology** (nisbah+plural: `ِيِّين` 262, `ِيّات` 245, `ِيّا` 180),
  **not** extractor junk; junk is 25/411, matching the earlier count to the row. The **TIE (34,455 rows,
  2.8% of supervision) is the largest residual and is NOT bridgeable** — `َت`/`ت` tie between `َ تْ` and
  `ْ تَ`, and PADT has **zero** in-inventory instances of either, so no corpus prior exists either; it
  needs an input the notation lacks.
  **Retracted in my own working:** "the bridge is the identity on the ruler, Trap B cannot fire" was
  measured on **gold-300 — the inventory's own source, which is circular**. On the real ruler it touches
  18 rows and fixes 8. The plan's "measure both options on the gold-300 ceiling" is the same circularity
  and was replaced by the ruler table.
  **Ruler identity:** `data/annotation/` is clean and `bench-gold.jsonl` has ONE commit ever (`def54f0`);
  sha256 **`7a06a585e065d8cf…`**, 304,159 B, 1,000 records. **No mutation** — but the `6640123d8162` I had
  been quoting for it appears **nowhere in the repo** and is wrong. Also found: `bench-freeze.json` does
  **not** cover the adjudicated gold (inputs only), the pattern field is **`wazn_pattern`**, and the
  recorded "**973 usable**" is **not** reproduced by `root+pattern+case present` (that selects all 1,000)
  — flagged, not adopted. Nothing ships; no `src/` file touched.
  **GATE — PRE-REGISTERED 2026-10-14, BEFORE the bridge is implemented.** Implement the bridge + the 3
  ruler-required classes ONLY IF, measured on the frozen ruler and by the census tool: (a) **zero**
  suffixed tokens land at class 0 and **zero** real affixes land on `IGNORE`; (b) each of the 12
  DETERMINATE mappings resolves to exactly one class under the sub-multiset guard, with its token count
  printed; (c) the ruler's representable ceiling reaches **≥ 990/1000 = 99.0%** from the bridge, and the
  **≥ 999/1000 = 99.9%** figure may only be claimed **once the 3 classes are added** — the bridge may not
  claim the new classes' rows; (d) the bridge is the **IDENTITY on all 982 in-inventory ruler rows** and
  changes **no** in-inventory row on either corpus (`changed_not_inventory == 0`), so **`broken = 0` is
  asserted, not argued**; (e) non-Arabic junk → `IGNORE` (25 PADT / 411 silver) and **never** `IGNORE` for
  a real unseen class; (f) `src/final_surface.py`'s shipped numbers and `--selftest` are unmoved;
  (g) deterministic, smoke green, every existing gate exits 0.
  The **TIE bucket (34,455 rows) is out of scope by construction** — it may not be resolved by a prior
  chosen after seeing the number; it is re-registered as its own item needing a person/gender input.
  **Next command for this block.** **SHIPPED AND GREEN 2026-10-14 (§2cz).** `python tools/stem_tail_audit.py --space both --check` exits **0**.
  The class space is **30 → 176** — every tail the two TRAINING corpora supervise, except the 436 tokens this
  notation cannot spell — so **112,412 supervised rows (9.11% of 1,234,611) stop carrying the class-0 "bare
  stem" label**, and IGNORE falls **75,278 → 436 (0.035%)**. `changed_not_inventory == 0`,
  `zero_class_suffixed == 0` and `ignore_real == 0` are all asserted. The bridge's remaining job is **7 ruler
  rows** — a tail training never attests. Ruler **reachable ceiling 996/1000 = 99.6%**; the last 4 rows need
  `\u064e\u0627`, which **no** training token supervises, so it is reported as a representational ceiling and
  deliberately NOT added (§2cz §6). **Newly sized and NOT fixed:** `DIG = [1-4]` is narrower than the corpora's
  slot digits, so 13 patterns / **436 tokens** leak a digit into the tail (`1\u0650ا234\u06705` → `\u06705`)
  — a notation defect, sized at 0.035%, whose fix touches every consumer of `tail_strip` and is therefore its
  own change. **Still unmeasured, and now the largest item: §2cw's two excluded `wazan_normalizer.py` clauses
  (the `canonical_wazan_skeleton` rewrite costs **73,162 supervised rows** on the `wazan_canonical` head) and
  the 199-line decoder rewrite.**

- **GRID v22 — PRE-REGISTERED 2026-10-14 (§2db), BEFORE any push.** Tree = commit `f4d71f5`, code bundle
  sha256 **`ac64a52cac081fd7`** (recorded in `tools/verified_runs.json` when the run exists; the builder reports every
  embedded path matching HEAD). Shape = the v20 shape unchanged: `{gold, silver} x {treatment, baseline} x
  3 seeds` = 12 runs, matched 120k tokens per source, 3,000 steps, batch 32, lr 3e-4, warmup 200 — i.e. the
  **committed** objective of §2cy, not v21's uncommitted one. **Exactly one thing moves vs v20: the
  `stem_tail` head on the completed 176-class space (§2cz).** Parity re-derived with the head present:
  **16,727,400 / 16,727,402 = 0.0000%** (v14 printed 13.09 M, v15 13.44 M — this pair is how the run
  identifies its architecture). *Acceptance threshold:* the tail channel must show **≥ +8 rows (2.7 pp) per
  source** as a **decode-time pair** (channel off vs on) on the same checkpoints, with the resource-OFF leg
  still ≥ 15%; the measured ceiling with the model plan held fixed is **+19 / +16 rows of 300 = +5.3 / +5.7
  pp**, so a trained head is expected below it. Below +8 → not shippable as built, recorded as a miss with
  its number. *Not decided by this grid:* the (W)/(T) head gates (training-time, PADT-only), the
  interleaved-gold lever (NOT in this tree — own item), and the decoder beyond that pair. *Next command.*
  **No kernel has been pushed.** The command is `python <project venv>/Scripts/kaggle.exe kernels push -p
  build/kaggle-kernel`, and the FIRST thing to check afterwards is the run's own `embedded code bundle: …
  sha256` line against `ac64a52cac081fd7`.

## 10. Case from SYNTAX — the dependency relation as the governor of iʿrāb

> **Replaces** former item 10 ("Product baseline…"), absorbed into item 7 on 2026-10-11.
> **Priority note.** Placed last because its *claim* depends on item 1 returning (the case reference
> must be human-adjudicated, not CALIMA-derived). Mechanically it is the highest-value **modelling**
> change on this list, above 3–6, and its mechanics can start on PADT-dev today.

- **Hypothesis.** Case is government and agreement (ʿāmil/maʿmūl), not a local labelling task, so a
  dependency-relation head should beat the current case head — **but the gain is bounded well below
  what an external proposal claimed.** Measured with **gold** `upos` and **gold** `deprel` (so a
  trained parser can only do worse), `tools/case_from_deprel_probe.py` (2026-10-11):
  P(Case | upos, deprel) = **0.7331 macro-F1 on PADT** (0.6892 on NYUAD), i.e. **+0.37 over POS
  alone** (0.3675) and **+0.26 over the current 0.4707**; the deterministic mapping is reliable only
  on a **selective subset — 0.9782 accuracy at 16.2% coverage** (NYUAD 0.9730 at 25.8%). Degrades
  under parser error (0.7331 → 0.6390 at 20% deprel noise) and cross-treebank transfer is poor
  (PADT→NYUAD 0.5532, NYUAD→PADT 0.3647 accuracy). Target **92–94% is above this oracle** — it is
  not achievable by this route, and the `">97% consistency"` claim is a selective-subset figure.
- **Metric.** Case **macro-F1** on an adjudicated reference, with the CALIMA-derived **0.459** ceiling
  reported beside it (`EVIDENCE_LOG.md` §2au) · the parser's own **deprel accuracy** reported with it,
  never separately · and the deterministic-mapping subset reported as **coverage AND accuracy**.
- **Split.** PADT dev for the mechanics (gold `Case=` exists there); the item-1 benchmark for any
  claim. Supervision **masked per source, never pooled** — pooling NYUAD+PADT+QAC drops combined root
  coverage to **23.3%** (`RESOURCES.md` §1.4) and the case conventions transfer poorly.
- **Acceptance threshold.** **> 0.62 macro-F1 on PADT dev** — above the 0.4707 baseline and the 0.459
  CALIMA ceiling, below the measured 0.7331 oracle — **and** the deterministic subset reported with
  its coverage. Pre-registered before the run; nothing tuned on the reporting split.
- **Next command.** `python tools/case_from_deprel_probe.py` (CPU, ~1 min) to re-derive the ceiling,
  then **write the dependency-relation head — it does not exist yet.** No GPU spend until its CPU
  part is measured and its threshold is written above.
- **Do not:** target 92–94% (above the oracle) · pool treebanks · derive product claims from
  CC BY-NC-SA / GPL sources · multiply marginal accuracies and call it an end-to-end estimate.

---

## Explicitly NOT doing

Recorded so the same ground is not re-walked:

- Training on more silver labels **before** the gold set is independent (item 1 gates this).
- Assuming a larger word vocabulary solves morphology — measured wrong for the one-book sample (`§2ad`);
  the *cap* is a different lever (item 6).
- **Re-proposing a character encoder as the OOV fix** — shipped as v12 (round 20), measured in `§2z`
  (OOV whole-root 0.000 → 0.071–0.241, and the treatment's root win did NOT replicate). Item 5 keeps
  only the segmentation half.
- **Predicting case as an unconditioned local label, or expecting ≥90% case from syntax** — the oracle
  for the syntax route is 0.7331 macro-F1 (item 10); the CALIMA-derived ceiling is 0.459, so a low
  case figure on the current human gold is first a *ruler* problem (item 1).
- **Pruning a "70-class" wazān space** — the label space is 6,633 types, the beamed decode already
  exists, and the 22.1% is dominated by notation, not search (`§2au`).
- **Quoting an end-to-end target as a product of marginal accuracies** — the renderer alone caps it at
  42.8% with a perfect model (`§2s.8d`), and in-domain vs OOV root are slices of one event, not stages.
- Shipping hand-tuned confidence thresholds as the decision-maker (item 2).
- Treating the current renderer as universal Arabic generation (items 8, 9).
- Treating the matched research baseline as the product baseline (item 7, which absorbed the old item 10).
- Further CNN-kernel tuning (item 5).
- Any GPU spend before its threshold is pre-registered and its CPU part is measured.
- **Quoting the PADT hybrid per-class rates (`hollow 44.2% / hamza 53.5% / defective 62.0%`) as the renderer's
  fidelity baseline** — measured on PADT test, against an UNDIACRITIZED reference the repo's own log says
  cannot carry this metric, and roughly half of that credit is the hybrid *table* returning the memorised
  `FORM` verbatim (`§2ba` §1). Re-quote it only as a *routing* diagnostic, never as fidelity.
- **Re-proposing the naive weak-radical route (delete the weak radical in place)** — measured to regress
  (`weak_radical_missing` 1→12, §2s.6; 19 rows under the corrected metric, §2s.8e), and re-attempted as a
  650-line patch in round 28 that crashed the documented v1 baseline and changed nothing on the acceptance
  test (§2ba §5). The weak radical must be **re-realized by position**, including *which* weak letter it is.
- **Re-running the 43-minute training job to "clean up Prong 2 `<pad>` targets"** — Prong 2 has already
  trained and measured **slightly negative on all four cells (−2.5 to −4.4 pp)** (§2x/§2y); re-spending GPU
  on it is re-measuring a closed question.
