# BLIND BENCHMARK FREEZE — v2 (the independent 1k–2k gold set)

> **STATUS: FULLY LOCKED.** §9 was signed off 2026-10-11 — **1,000 rows (650 test / 350
> calibration)**, the strata quotas as recommended, two independent annotations, and PI
> adjudication of disagreements with a written per-row rationale. **The sheet is generated and
> frozen:** `data/annotation/bench-sheet.csv`, **sha256 `71bdd196334839b4a02ce841c1b396c51e5bdc6d7a3db851de45394539c24fe8`**.
> §2–§8 may no longer change, and neither may the sheet — both annotators receive that exact byte
> sequence, and a rebuild with the same seed reproduces it byte-for-byte (verified).
>
> **Supersedes nothing.** `docs/ANNOTATION-PROTOCOL.md` (v1, frozen 2026-10-09) stays in force —
> its format spec (§3, §3a–§3e), its worked examples (§4) and **Rule 6** (every radical gets a
> slot even when unwritten) and **Rule 7** (bare alef in roots) are incorporated by reference and
> are not restated here. This document adds the five locks that v1 does not cover.
>
> **Why it must exist before any model output is shown to anyone.** Anchoring is permanent. Once
> an annotator has seen an analyser's or a model's answer for an item, that item's label is
> contaminated, and no later care recovers it. This is the same reason v1 existed — it is not a
> formality.

---

## 1. The five locks, and their status

| # | lock | status |
|---|---|---|
| A | annotation guide and examples | **v1 in force** (§3, §3a–§3e, §4, Rules 6–7) **+ new §2a–§2c** for homographs, clitics, OOV |
| B | blind item IDs and randomized order | **locked in §3** — new: no semantic IDs, one frozen shuffle, recorded seed, sheet sha256 |
| C | strata for weak / doubled / homographic / clitic / OOV | **locked in §4** — v1 had only a single 40 % weak/shadda fraction; this defines six strata with surface-only detection |
| D | independent labels before adjudication | **locked in §5** — v1 mentioned κ as a future possibility; this makes the mechanics and the arbitration rule explicit |
| E | frozen test and calibration splits | **locked in §6** — new; v1 had no notion of a calibration split |

## 2. Lock A — the guide

`docs/ANNOTATION-PROTOCOL.md` §3–§4 applies unchanged: root = **stem** radicals, dot-separated;
`wazn_pattern` = digits for radicals **with vowels kept** and the **final case vowel excluded**;
a shadda never means "write the digit twice"; `case` is nominals only and **verbs take `ABSTAIN`**;
`ABSTAIN` is a legitimate answer, never a failure. **Rule 6** and **Rule 7** are mandatory.

Three classes v1 did not address, and the ruling for each:

### 2a. Homographs — annotate the reading the CONTEXT selects
A surface may admit several sound analyses. **Do not annotate every reading and do not split the
row.** Decide from the governing context and record **one** analysis, then put the rival reading in
`notes`. If the context genuinely does not select between them, that is information:
`case=ABSTAIN` and both candidates in `notes`. Homographs are a **stratum** (§4, S3) precisely
because they are the class where a single-answer benchmark is most likely to be wrong about itself.

### 2b. Clitics — annotate the STEM, and say what you stripped
Root and pattern are for the stem only (v1 §3b). New here: **`notes` must name the affixes you
removed**, because the clitic stratum (§4, S4) is scored on whether the *stem* was identified — a
row whose stem is right but whose clitic was silently dropped is not the same result as one where
the clitic was correctly excluded, and the notes column is the only place that distinction survives.

### 2c. OOV and rare forms — no cover from analogy
For a word not in the model's vocabulary, the temptation is to pattern-match it onto a familiar
template. **Annotate what the word is, not what it resembles.** If the form is irregular
(quadriliteral, a proper noun, a loanword, a Qur'anic rasm variant) say so in `notes`; do not
force it into a triliteral template to make it fit the format.

## 3. Lock B — blind item IDs and randomized order

- **IDs are opaque.** `<PREFIX><zero-padded index>`, assigned **after** shuffling. No ID may encode
  stratum, class, length, frequency or source — `WEAK001` is forbidden, because the ID travels with
  the row into every downstream report.
- **One frozen shuffle.** The item order is produced by a single seeded shuffle, executed once. The
  seed is recorded in the freeze record (§7). Determinism is required: **the same seed and the same
  source must reproduce a byte-identical sheet**, which is what makes the recorded sha256 meaningful
  rather than decorative.
- **The sheet carries context and nothing else.** Columns are exactly:
  `id, sentence_with_target_in_double_brackets, target_token, root, wazn_pattern, case, alternatives,
  confidence, notes`
  (**nine** columns; `alternatives` added by **Amendment 1**, §13 — see there for why, and for the
  contract that it is filled on every row with `NONE` when there is no rival analysis).
  **No model prediction, no abstention flag, no confidence value, no
  CALIMA output, no stratum label, no gold** may appear in, or be attached to, the sheet.
- **The key is a separate file** (`*-KEY.csv`, gitignored) mapping id → stratum → source, so the PI
  can analyse by stratum without the annotator ever seeing the labels.
- Both annotators receive **the same items in the same order with the same IDs**. Identical sheets
  are what make κ meaningful; a different order would confound ordering effects with annotator
  disagreement.

## 4. Lock C — the strata

Six strata, defined so they can be detected from the **surface alone**. This is deliberate: any
detector that consults an analyser would break the blindness rule at sampling time, before the
annotator is even involved.

| id | stratum | detection — surface only | what it tests |
|---|---|---|---|
| **S1** | weak (incl. hollow/defective/assimilated) | surface contains a weak letter `و`/`ي` in a radical-shaped position | the class where CALIMA's `#` collapses and where v1 found **every** malformed human pattern |
| **S2** | doubled | surface carries a shadda `ّ` | Rule 6's first failure mode |
| **S3** | homographic | the token's **undiacritized skeleton** appears in `data/abstention_homographs.json`, or the bare form has ≥ 2 distinct vocalizations among the training records | whether the benchmark is itself ambiguous (§2a) |
| **S4** | clitic-heavy | surface matches a proclitic (`و|ف|ب|ك|ل|ال`) and/or an enclitic (`ـه|ـها|ـهم|ـهن|ـك|ـكم|ـنا|ـني`) pattern | stem identification under affix noise (§2b) |
| **S5** | OOV | target surface is **not** in the model vocabulary (`min_freq ≥ 2` **and** `max_vocab = 20,000`) built from **TRAIN records only** | the 7.7× in-vocab/OOV gap (`EVIDENCE_LOG.md` §2ad) |
| **S6** | sound (control) | none of S1–S5 | **required** — a benchmark of only hard cases cannot distinguish "hard classes improved" from "everything got worse" |

**S5 does not leak an answer.** Vocabulary membership is a coverage property of the *training data*,
not a model prediction, and it is computed from the train split only. It may be used at sheet-build time.

**Strata are not mutually exclusive.** A token may be S1∩S3∩S5. The key records the **full set** of
stratum memberships per item; quotas (§9) are over *primary* stratum (the first matching row in
S1→S6 order, recorded explicitly) so that the totals add up.

## 5. Lock D — independent labels before adjudication

1. Each annotator gets an identical sheet and fills **their own file**: `<prefix>-annotator-<X>.csv`.
2. **Neither annotator receives**: the other's file, the adjudicated file, the KEY file, any gold,
   any model output, any earlier scored summary. The only thing that travels with the sheet is
   context.
3. Each return is **hashed on receipt** and the hash recorded in the freeze record. A return that
   changes after being hashed is void — this is what makes "independent" checkable rather than promised.
4. **Agreement is computed on the two raw files, before adjudication**, per head:
   root as a **slot-set** (per Rule 6, so an elided radical missing its slot scores as a disagreement,
   not as a shorter answer), wazān well-formedness, and case. Report **raw agreement and Cohen's κ**;
   report κ per head, never pooled into one number.
5. **Adjudication happens only after both files are frozen.** Disputed rows are resolved under the
   tie rule in §9, **with a written rationale per row**. The rationale is part of the artifact.
6. **The disagreement rate is reported, not hidden.** Rows where the two annotators genuinely differ
   are the most informative rows in the benchmark: they are the measurement of how ambiguous the task
   is. Suppressing them would manufacture a cleaner number than the task supports.

## 6. Lock E — frozen test and calibration splits

- The benchmark is split **once, at freeze time**, into **test** and **calibration**, disjoint by
  construction.
- **The split is by lemma/root, never by token.** No lemma may appear on both sides, and no lemma may
  appear twice within a side in a way that makes the sides non-independent. A token-level split of a
  morphology benchmark leaks nearly the whole answer, because the same lemma's other forms carry it.
- **The calibration split exists for exactly one purpose:** fitting the abstention thresholds in
  `ACTIVE_BACKLOG.md` item 2. It may be examined freely by the model side, and it may **never** be
  used to report accuracy, to select an architecture, or to tune anything else.
- **Both sides are frozen** (sha256 recorded, §7) **before any model output is generated for the
  benchmark.** A guard script must assert, mechanically: the two sides are lemma-disjoint, no item
  appears twice, and the stored hashes match the files.

## 7. The freeze record

**FROZEN 2026-10-11. Amendment 1 (§13) applied the same day, BEFORE anything was issued.**
Filled in at freeze time, before any annotator saw anything.

| field | value |
|---|---|
| sheet file | `data/annotation/bench-sheet.csv` (re-generated by Amendment 1) |
| **sheet sha256** | **`1b4f8a1e208dd34cebe89bc15570a7d380569db1d0aee59193ef585801c81db7`** |
| superseded 8-column sheet sha256 | `71bdd196334839b4a02ce841c1b396c51e5bdc6d7a3db851de45394539c24fe8` — **never issued to anyone** |
| columns | 9 — `…, case, alternatives, confidence, notes` |
| annotator copies | `bench-annotator-A.csv`, `bench-annotator-B.csv` — **byte-identical to the sheet** |
| KEY (never sent) | `bench-KEY.csv`, sha256 `1c9ba06b3c3a2eb90567a2f5b9d9bedfffdf78bbddd8c7c61dfbd78a07fe9042`, **gitignored** (`data/annotation/*-KEY.csv`) |
| generator | `tools/build_benchmark_sheet.py --seed 20261012` |
| seed | **20261012** |
| rows | **1,000** |
| test / calibration split | **650 / 350**, lemma-disjoint |
| strata realised (primary) | S1 180 · S2 120 · S3 120 · S4 180 · S5 200 · S6 200 — **exactly the approved quotas** |
| pool | `data/out/spread-B-2m/tashkeela-test.jsonl` (books 90–96, never trained on) |
| distinct target tokens | 1,000 |
| sentences also in TRAIN | **0** (a hard filter, not an assertion — one sentence was found and dropped) |
| vocabulary rule for S5 | `min_freq=2` AND `max_vocab=20,000` over TRAIN only → 19,998 types |
| determinism | **verified** — a rebuild with the same seed reproduced the same sha256 |
| annotator A / B files + sha256 | *(pending receipt — hash each on arrival, per §5.3)* |
| κ per head (raw, pre-adjudication) | *(pending)* |
| adjudication rationale | *(pending)* |
| frozen by / date | PI sign-off of §9, 2026-10-11 |

**Nothing in this table may be filled in retroactively to match a result.**

## 8. What must NEVER be sent to an annotator

Repeated because this is the failure that cannot be undone:

- any CALIMA / CAMEL Tools output of any kind;
- any model prediction, logit, confidence, or abstention decision;
- any gold from QAC, EQTB, PADT or `gold-tashkeela-300.jsonl`;
- the KEY file, the other annotator's file, or any adjudicated file;
- any stratum label attached to a row;
- any earlier scored summary of this benchmark.

## 9. OPEN — the PI's three numbers (must be set BEFORE recruitment)

1. **Total size and the test/calibration split.** Recommendation: **1,000 items = 650 test + 350
   calibration**. At v1's measured pace (300 rows ≈ 3–5 h) that is **≈10–17 h per annotator**, ×2
   annotators. 1,500 would be ≈15–25 h each. The strata below matter more than raw size — a
   stratified 1,000 is worth more than an unstratified 2,000.
2. **Strata quotas** (percent of total, over primary stratum). Recommendation:
   S1 weak 18 % · S2 doubled 12 % · S3 homographic 12 % · S4 clitic 18 % · S5 OOV 20 % · S6 sound 20 %.
   Adjust only now; after freeze the quotas are part of the artifact.
3. **The adjudication tie rule** — who resolves a disputed row, and by what rule. Options: (a) the PI
   adjudicates with a written rationale (default; the PI is annotator A, so disputed rows are
   recorded as "A-preferred, adjudicated" and the raw disagreement is still reported); (b) a third
   independent Arabic specialist; (c) a fixed precedence rule (e.g. classical īʿrāb first). The rule
   must be written down before annotator B starts.

## 10. Effort, and why this is the critical path

Every downstream item in `ACTIVE_BACKLOG.md` is measured against this benchmark, so a defect here
propagates into all of them — which is why it is item 1 and why nothing else counts as an accuracy
improvement until it exists. The cost is **human hours**, not compute: two annotators, independent,
blind, with adjudication. There is no way to buy this with GPU time, and no way to retrofit blindness.

## 11. Builder deltas — IMPLEMENTED (infrastructure; explicitly NOT an accuracy claim)

`src/build_annotation_sheet.py` today supports:
`--source {eqtb,tashkeela} --n N --no-gold K --seed S --prefix P --limit L --strati-frac F`
with opaque IDs and a single weak/shadda stratification fraction. It needs:

1. multi-stratum quotas instead of a single `--strati-frac`;
2. surface-only detectors for S3 (homograph list + corpus vocalization variants) and S4 (clitic
   patterns) — S1/S2/S5 already exist in effect;
3. test/calibration marking with a **lemma-disjointness assertion**;
4. per-annotator file emission (identical sheets, separate destinations);
5. a freeze-record writer (sha256 + seed + realised quotas + provenance).

**Where it goes matters:** `src/` is inside the embedded notebook payload, which is already at ~74 %
of Kaggle's 700 KB cap, so the new builder belongs in **`tools/`** — the same reason the other
measurement tooling lives there. Extending `src/build_annotation_sheet.py` in place would churn the
payload sha and force a notebook regeneration for no informational gain.

**Delivered as `tools/build_benchmark_sheet.py`** (all five deltas: quotas, S3/S4 detectors, split
marking with the lemma-disjointness proof, per-annotator emission, freeze-record writer), with a
`--stats` mode so feasibility can be measured before anything is written.

## 12. What the first build found — two defects and one refusal, all caught before freezing

Recorded because each would have silently corrupted the benchmark rather than failing loudly.

**1. Tashkeela carries printed-edition page markers GLUED to words.** The first sheet had targets
like `الْفِطْرِ(2/402` on **100 of 1,000 rows (10.0 %)**. The marker is attached with no space, so
punctuation stripping cannot salvage it, and such a target corrupts the wazān pattern on every
affected row. v1's `strip_punct` does not handle it. **Fixed** by dropping any *sentence* containing
a marker (so context is clean too) and additionally requiring the target to be Arabic letters +
diacritics only. Re-verified: 0 dirty targets, 0 markers in targets **or** context.

**2. S3's supply was ONE item for a 120-item quota.** The curated 98-surface list is PADT-derived and
covers almost none of Tashkeela prose — 182 raw tokens in a 65,821-token pool. The freeze doc already
sanctions a second detector (same skeleton, ≥ 2 distinct vocalizations in the training records), and
it was needed; but taken literally it is far too broad: **50,560 raw tokens (77 % of the pool)**,
because most words vary only by *case vowel* (كِتَابٌ / كِتَابٍ / كِتَابًا). That made S3 dominant and
starved the sound control (supply 76 for a 200 quota). The implemented rule strips the trailing case
vowel/tanwin **before** comparing, so variants must differ internally (كَتَب vs كُتُب).

Measured ladder, all three states real: **1 → 50,560 → 18,423** skeletons, after which all six
quotas fill. The middle number is the one that looks fine and is not.

**3. A train/test text overlap was found and REFUSED.** The guard stopped the first complete build
with `sentence overlap with TRAIN records: 1` — Tashkeela repeats passages across books, so one
test-sentence also occurs in training. It is now filtered before selection rather than asserted
afterwards, so the guard is a verification rather than the only defence.

**Watch the S6 margin.** 219 distinct-lemma candidates for a 200 quota is thin. If the pool or any
detector changes, S6 is the first quota to fail — and the generator **refuses** rather than
under-filling, so this shows up as an error, not as a quietly smaller benchmark.

**ACCEPTED FRAGILITY — recorded 2026-10-11, after the freeze; no locked content above changed.**
The thin S6 margin is accepted as it stands: it is the *correct* failure mode (fail closed, loudly)
and the quota is **not** to be loosened to make a rebuild pass. Same for S3, whose detector strips
only the trailing case vowel/tanwin and therefore still admits skeletons whose variants differ
solely by the vowel adjacent to a pronoun suffix (e.g. مقامه / مقامَه / مقامُه / مقامِه) — a small
upward bias on S3, direction known, not quantified, and bounded because the quota is fixed.
`tools/build_practice_pack.py` inherits both properties and reports supply as a table before it
writes anything.

---

## 13. AMENDMENT 1 — the `alternatives` column (applied 2026-10-11, BEFORE issue)

**Status: applied to the artifact. Nothing had been issued to any annotator, so no work was
invalidated and no blindness was broken.**

### 13.1 What was wrong

The v1.0 packet recorded rival analyses as a prose tag inside `notes` (`ALT: case=NOM`). That is
human-readable and **machine-invisible**: `tools/iaa_report.py` reads the four scored columns and
never parses free text. The consequences were concrete, not theoretical:

1. **Alternatives could not be measured.** Two annotators could record completely different rival
   readings and the agreement report would show nothing, because nothing read the column.
2. **Alternatives could not be adjudicated.** The adjudication rule resolves *disputed rows*; a
   rival reading buried in prose is not a row-level dispute and had no resolution path.
3. **Alternatives could not be used for top-k evaluation.** A benchmark whose only correct answer
   is the single primary analysis cannot score a top-2 or top-3 model — the model's second
   candidate would be marked simply wrong on exactly the rows where the task is genuinely
   ambiguous. That is the opposite of what a morphology benchmark is for.

### 13.2 What changed

A ninth column, `alternatives`, positioned between `case` and `confidence`. Strict grammar:

| value | meaning |
|---|---|
| `NONE` | considered, and no rival analysis exists |
| `case=NOM` | one candidate |
| `root=ق.و.ل \| case=GEN` | two candidates, ` \| `-separated |

Allowed keys `root`, `wazn` (`wazn_pattern` accepted as an alias), `case`; space-separated
`field=value` pairs within a candidate; `ABSTAIN` is never a candidate value (it belongs in the
column the candidate is an alternative *to*). **Filled on every row** — `NONE` is a considered
value, a blank cell is not. `notes` keeps the human-readable reasoning, including the
`ABSTAIN:` reason tags.

Two consistency rules are now enforced mechanically:
`case=ABSTAIN` with `ABSTAIN:both-readings-viable` must carry **both** case candidates in
`alternatives`; every `case=ABSTAIN` must carry an `ABSTAIN:` reason tag.

### 13.3 Consequences on the artifact

| item | before | after |
|---|---|---|
| sheet sha256 | `71bdd196…` (**never issued**) | **`1b4f8a1e…`** |
| annotator A/B copies | byte-identical to sheet | byte-identical to sheet |
| practice pack sha256 | `e5c56a15…` | `3fb87b63…` |
| columns | 8 | **9** |
| strata quotas, seed, split, lemma-disjointness | — | **unchanged**: 180/120/120/180/200/200, 650/350, seed `20261012` |

The 8-column sheet was **never transmitted to anyone** — it existed only inside the repository
between two commits on 2026-10-11. That is a checkable claim, not a promise: the issue record
(`data/annotation/bench-B-ISSUE.json`) is dated after the amendment and names the amended hashes,
and `EVIDENCE_LOG.md` §2as records that recruitment had not happened.

### 13.4 Also corrected in this amendment

- **The `confidence` column is annotation certainty, not model confidence.** v1.0 said the column
  "is used to build a selective-risk curve", which conflated two different measurements. A model's
  selective-risk curve comes from *model* confidence against adjudicated correctness on the
  calibration split; the annotator's `confidence` measures the certainty of the annotation, and
  low values here are evidence that the *task* is ambiguous. The packet now says so explicitly.
- **`ALTERNATIVE:` prose is gone**, replaced by the column (there is now exactly one way to record
  a rival analysis).
- **A sheet validator exists**: `tools/iaa_report.py --validate <file>` format-checks a return
  (including the alternatives grammar and the two consistency rules above) and exits non-zero on
  any error, so the practice pack is checked before the annotator proceeds to the benchmark and no
  malformed cell can reach the agreement report.
- **The tools are portable**: `tools/repo_root.py` resolves the repository from the script's own
  location or an explicit `--root`, replacing three hardcoded `G:/arabic-root-tree` constants (and
  two CWD-relative `sys.path` insertions) that made the tooling unusable outside one directory on
  one machine. Verified against a copy on a different path, including a poison test.

