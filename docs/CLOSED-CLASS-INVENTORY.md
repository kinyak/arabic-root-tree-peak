# Closed-class inventory + bypass specification (draft)

**Status:** draft for review, 2026-10-10 · built by `src/build_closed_class_inventory.py`
**Data:** `data/closed_class_inventory.json` (lemmas, surfaces, frequencies, coverage curve)
**Origin:** the structural floor measured in `EVIDENCE_LOG.md` §2x.8 — 911 of 4,000 PADT-test
tokens (22.8%) are closed-class and unrendered, and the root+pattern mechanism cannot reach
them however good the rules get.

---

## 1. Why a bypass exists at all

The renderer plans a word as *(root + pattern + case)* and spells it. That works for content
words. It cannot work for و، فِي، بِ، هُوَ، هٰذَا: they have no root, so no amount of renderer
improvement reaches them, and they cap all-token coverage at **~77%** no matter what
(`§2x.8`). Measured on the PADT test prefix:

| | tokens | share |
|---|---|---|
| rendered (hybrid) | 2,914 | 72.8% |
| **closed-class floor, unrendered** | **911** | **22.8%** |
| content words with no usable root | 149 | 3.7% |
| content words with a usable root that still fail | 18 | 0.45% |

So the floor is the single biggest remaining lever on *coverage* — and it is also **not a
root-tree result**. Everything below is engineered to keep those two facts apart.

## 2. The floor is not one kind of thing

`src/build_closed_class_inventory.py` partitions the floor by the TEST record's own UPOS, so
the rows sum to the floor exactly (verified: per-tag totals = 12,480 = the floor).

| UPOS | train tokens | lemmas | test tokens | covered by a train surface/lemma table | what it actually needs |
|---|---|---|---|---|---|
| ADP | 33,617 | 59 | 4,528 | 4,523 (99.9%) | **table** |
| PUNCT | 17,511 | 19 | 2,052 | 2,049 (99.9%) | **identity — no table** |
| CCONJ | 15,791 | 45 | 1,962 | 1,960 (99.9%) | **table** |
| X | 13,747 | **5,115** | 1,380 | 859 (62.2%) | **not closed-class semantics** |
| PRON | 8,533 | **1** | 1,133 | 1,133 (100%) | table, but see §4.2 |
| DET | 4,648 | 23 | 623 | 623 (100%) | table |
| SCONJ | 4,380 | 5 | 535 | 535 (100%) | table |
| PART | 1,709 | 21 | 226 | 226 (100%) | table |
| SYM | 329 | 4 | 41 | 41 (100%) | identity — no table |

**The headline: the function-word component needs 154 lemmas** — ADP 59 + CCONJ 45 + PRON 1 +
DET 23 + SCONJ 5 + PART 21 — covering **9,007 of the 12,480 test-floor tokens (72.2%)**.

The other two thirds of the *tokens* are not function words at all:
- **PUNCT + SYM = 2,093 tokens (16.8% of the floor)** — identity mapping, no table, no learning.
- **X = 1,380 tokens (11.1% of the floor)** — 5,115 distinct lemmas, only 62% coverable from
  train. `X` is where PADT puts unknown/foreign material (سويف، أوكرانيا، تايتان). These are
  **not** closed-class words with no root; they are content-like words the tagger could not
  place. Putting them in a "function word" bypass would be mislabelling, and a lemma table
  cannot cover them because the tail is unbounded.

## 3. Concentration — how few entries buy how much

Built from PADT **train**, measured against the **coverable** test floor (11,949 tokens):

| share of the coverable floor | entries needed |
|---|---|
| 50% | **7** |
| 80% | **26** |
| 90% | **58** |
| 95% | **188** |
| 99% | 1,866 |
| 100% | 5,247 |

The curve is extremely head-heavy: **7 entries cover half the floor**, and 26 cover four
fifths. A table sized at ~200 entries is where the return flattens.

The 7 entries that buy 50%, in train-frequency order: وَ · هُوَ · فِي · `.` · لِ · بِ · مِن.

## 4. Draft bypass specification

### 4.1 Component

**`4_closed_class` — a surface-keyed closed-class component, built from the PADT TRAIN split
only.** It is a *lookup*, not a model, and it sits beside the root+pattern route rather than
inside it. Nothing derived from the evaluation split may enter it — that is the §2x.1 leak,
and it must not be reintroduced by a new component.

### 4.2 Key on the SURFACE, never the lemma

The lemma is unusable as a table key: **PADT lemmatises every pronoun to `هُوَ`** (one lemma,
1,133 test tokens). A lemma-keyed table would render هِيَ، هُمْ، أَنَا as هُوَ. Surface keys do
not have this failure mode and cost nothing — coverage is 95.6% by surface vs 95.7% by lemma,
i.e. identical within noise.

### 4.3 Scope — three parts, three treatments

| part | treatment | test-floor tokens |
|---|---|---|
| ADP · CCONJ · PRON · DET · SCONJ · PART | surface → surface table, from train, sized ~200 entries | 9,007 |
| PUNCT · SYM | identity passthrough | 2,093 |
| **X** | **out of scope — needs its own policy, not this component** | 1,380 |

### 4.4 Reporting rules (non-negotiable)

1. The bypass is reported as its own route (`4_closed_class`) and **never merged** into the
   root-tree figures.
2. **Content-word coverage (93.3%) remains the number for the root-tree claim.** All-token
   coverage is reported separately and labelled as including a non-root-tree component.
3. A bypass that lifts all-token coverage from 72.8% to ~93% must not be presented anywhere as
   evidence about the architecture. It raises the *scored fraction*, not the *claim*.
4. The fidelity of the bypass cannot be measured on PADT — PADT's FORM is 98.7% undiacritized
   (§2x.4). Its vocalisation must be scored on the 300-token human gold or EQTB, the same as
   everything else.

### 4.5 Ambiguity — MEASURED, and the loss is concentrated *(2026-10-10)*

`src/measure_closed_class_ambiguity.py` (artifact `data/closed_class_ambiguity.json`). Surface set =
255 closed-class surfaces from PADT TRAIN (function-word tags only). Evidence = fully vocalised corpora,
streamed; **PADT cannot answer this question** because its FORM is 98.7% undiacritized (§2x.4).

**Scope of the number — skeleton vs diacritic, and they are not interchangeable.** This measures the
**vocalised route only**. On the **skeleton route** — bare-surface recovery, which is what the PADT
benchmark scores — من is always من and ان is always ان: **100% by construction, zero ambiguity**. So
91.09% is a statement about *diacritized output on vocalised corpora* and must never be quoted as a
bare-surface figure. Only the vocalised route needs the tiering below; the skeleton route needs none.

**Held out, the number survives — it was not inflated by memorisation.** The 91.09% above is *in-sample*
(map and evidence read from the same books), which is not grounds to sign a policy off.
`src/score_closed_class_bypass.py` trains the map on books 0–9 and scores a **disjoint** slice, books 60–96:
**micro precision 91.00%** — a 0.09 pp drop, so the aggregate generalises. Tier 1 does *better* than
advertised out of sample (**99.75%** over vocalised tokens, vs 99.57% in-sample). Full validation, the
cross-corpus failure, and the recommended threshold are §4.9.

**Tashkeela books — classical/expository vocalised prose (310,339 matched tokens, 179 surfaces seen):**

| metric | value |
|---|---|
| **MICRO majority-vote accuracy** | **91.09%** |
| MACRO (mean over surfaces) | 85.01% |
| surfaces with >1 vocalisation | 110 / 179 (61.5%) |

**The gate is not met — but the loss is almost entirely a handful of surfaces:**

| surface | errors | share of ALL errors | volume | majority share |
|---|---|---|---|---|
| ان | 14,324 | **51.8%** | 23,267 | 38.4% |
| من | 4,630 | 16.7% | 31,102 | 85.1% |
| غير | 1,557 | 5.6% | 3,100 | 49.8% |
| علي | 996 | 3.6% | 19,228 | 94.8% |
| لما | 678 | 2.5% | 1,990 | 65.9% |
| الا | 470 | 1.7% | 5,366 | 91.2% |
| … + مثل، لكن، بعد، قبل | | | | |

**Top-10 surfaces carry 86.8% of ALL errors.** Split by confidence:

| surfaces with majority ≥ | count | share of volume | accuracy on that volume |
|---|---|---|---|
| 0.99 | 91 | 55.5% | **99.85%** |
| 0.95 | 108 | 65.3% | **99.57%** |
| 0.90 | 116 | 77.1% | 98.63% |

The user's predicted hotspots are exactly the measured ones: **ان** (أَنْ subjunctive vs أَنَّ vs إِنْ vs
إِنَّ) is the single worst entry in the language of this corpus at 38.4%; **من** (مِنْ ≈85% vs مَنْ) matches
the predicted 85–90%; **ما** and **ل** behave as expected. Note also that several worst entries — غير، مثل،
قرب، حسب، عوض، خلال، بعد، قبل — are **preposition-tagged nouns**, so part of the measured ambiguity is
part-of-speech homography, not vocalisation choice. This script matches on surface alone and therefore
cannot separate those; a tagger can.

**EQTB (Quranic) — reported as a contrast, NOT as a comparable number.** Raw micro is 54.51%, but **45.7%
of its matched tokens are left unvocalised**, because Uthmani orthography writes many particles bare
(`و×6056` vs `وَ×3969`; `ال×1614` alongside `الْ`). Collapsing the bare convention raises it to 67.82% on
the vocalised tokens only — still not comparable to Tashkeela, because Uthmani is a **different
orthographic system** (ٱ vs ا, pausal forms), not merely a different register. Use Tashkeela for the
policy decision; use EQTB only to show the convention gap is not the ambiguity.

### 4.5.1 Policy decision — TWO TIERS, not one

The static-map question as posed has no clean yes/no answer; the measurement says the table should be
split, and the pipeline already has what the hard tier needs.

1. **Static tier** — for the **108 surfaces with majority ≥ 0.95** (65.3% of floor volume): a static
   surface → vocalised map, deterministic and O(1), **measured 99.57% accurate on its own volume.**
2. **Conditioned/abstain tier** — for the ~10–20 surfaces carrying 86.8% of the error (ان، من، ما، ل،
   الا، لما، لكن، غير، مثل، بعد، قبل…): require a conditioning signal. The available one, at no extra
   cost, is the model's own **UPOS/dependency** prediction — already a head in both arms (A13 parity holds,
   so this must be applied identically to the baseline). Where no signal decides it, **abstain and emit the
   bare surface**, and report the abstained volume rather than guessing.
3. **Reporting rule:** the bypass is reported as **three numbers — coverage, accuracy-on-covered, and
   abstained share** — never as one "closed-class accuracy". A single figure would hide exactly the tier
   structure that makes the component honest.

**Rejected:** majority-vote across all 179 surfaces (91.09%) as the sole policy — it is below the 95% gate
and would put ~1 token in 11 wrong in running text, concentrated in the highest-frequency function words.

### 4.6 X / loanwords — the formal policy

**Linguistic justification.** Classical morphologists designate foreign borrowings and non-derived nouns as
**الأعجمي / الجامد** — *laysa lahu wazn qiyāsī*, "it has no analogical pattern". A root-and-pattern
pipeline cannot derive them, by definition; this is not a defect of the renderer.

**Distributional divergence — MEASURED on the same basis (2026-10-10).** The earlier "<2%" here was an
unverified expectation; `src/measure_tashkeela_x_proxy.py` (artifact `data/tashkeela_x_proxy.json`) replaces
it. Tashkeela has **no POS tags**, so PADT's `X` label cannot be counted there; what is counted is the share
of tokens CAMeL gives **no templatic analysis** to (no analysis / `NTWS` / `backoff`) — a proxy, and an
upper-ish bound, because it also catches dialectal and odd forms:

| basis: share of **ALL** tokens | value |
|---|---|
| Tashkeela, untemplatic proxy (30,000 tokens, 10 books) | **2.80%** (NTWS 1.4% · backoff 1.4%) |
| PADT train, `X` | **6.14%** |
| PADT test, `X` | **4.88%** |
| ratio, PADT news ÷ classical text | **≈2.2×** |

(The 11.1% figure elsewhere in this document is `X` as a share of the **closed-class floor** — a different
denominator; do not put it beside the numbers above.)

So the direction of the original claim survives and is now empirical: **non-templatic material is roughly
twice as common in news-wire Arabic as in classical/expository Arabic.** The size of the X problem is a
property of **the corpus, not the architecture** — report the corpus alongside any X figure.

**Policy:** X is **out of scope** for both the root-tree mechanism and the closed-class bypass. It is
handled by a **verbatim surface pass-through** (Tier 3 below), and the 149 rootless content words in §2x.8
(سوريا، دمشق، الليبرالي) are the same phenomenon approached from the other side — one policy for both:
pass the surface through, mark it, and exclude it from the root-tree claim.

### 4.7 Reporting schema — three tiers, and the MEASURED benchmark *(2026-10-10)*

`renderer.py --measure` now runs route 4 (the bypass) and reports it separately, so the root-tree claim
cannot be inflated by it. Measured, PADT test prefix, 4,000 **Arabic** tokens:

| tier | component | tokens | share of 4,000 | is it the paper's claim? |
|---|---|---|---|---|
| **1. Templatic core** | root + pattern + case → renderer | **2,337 / 2,502 content** | **93.4% of content words** | **YES — this is the contribution** |
| **2. Closed-class bypass** | function words with a TRAIN surface (skeleton half) | 1,298 | 32.5% | NO — grammatical glue, reported separately |
| — with 12 function words abstained (no TRAIN surface) | | 12 | 0.3% | |
| **3. Non-templatic pass-through** | `X` (foreign/unknown) — **excluded from the figure above** | 188 | 4.7% | NO — engineering baseline for running text |

**ALL-TOKEN COVERAGE (Tier 1 ∪ Tier 2) = 3,763 / 4,000 = 94.1%**, with Tier 3 excluded. The 237 uncovered
tokens are 165 content words with no usable root, 12 unseen function words, and 60 `X`.

Three caveats that must travel with that 94.1%:

1. **Now tested — `--include-punct`.** `limit` counts *Arabic* tokens, so the 4,000-token baseline is
   **frozen**: the default run still reports exactly `3,763 / 4,000 = 94.1%`, and the punct run reproduces
   that same Arabic-only figure while adding PUNCT/SYM on top. Measured: `4,315 = 4,000 Arabic +` **315
   PUNCT/SYM**, every one covered by identity (they cannot fail), giving **running text
   `4,078 / 4,315 = 94.5%`**. The punct run writes `renderer_report_punct.json` so the baseline report is
   never overwritten with an altered denominator.
2. **The bypass's accuracy is `n/a` by construction** — it emits the reference surface itself, so any
   "accuracy" printed for it would be a copy. That is exactly why the number above is labelled Tier 2 and
   never merged.
3. **The vocalised half is not measurable on PADT** (FORM is 98.7% undiacritized, §2x.4). Only the skeleton
   half runs here. The 108-surface static vocalised map and its abstaining tail must be scored on Tashkeela
   or the human gold.

Tier 1 is reported alone and on content words only. Tiers 2 and 3 raise the *scored fraction* of running
text; neither is evidence about the architecture, and any all-token figure must be labelled as including a
non-root-tree component.

### 4.8 Expected effect — now MEASURED, not projected

The bypass is implemented as **route 4** in `renderer.py --measure` and reported separately (see §4.7 for the
benchmark table and its caveats). Measured on the test prefix:

| | value |
|---|---|
| bypass coverage (function words reached) | 1,298 tokens = **32.5%** of all tokens |
| function words abstained (no TRAIN surface) | 12 |
| **ALL-TOKEN COVERAGE — Arabic tokens only (Tier 1 ∪ Tier 2)** | **3,763 / 4,000 = 94.1%** |
| **RUNNING TEXT — `--include-punct` (4,000 Arabic + 315 PUNCT/SYM)** | **4,078 / 4,315 = 94.5%** |
| Tier 3, `X`, pass-through, NOT counted | 188 = 4.7% (of 4,000) |
| **content-word coverage (the claim) — unchanged** | **93.4%** |

The earlier projection here was "~+20 pp → ~93% all-token"; the measurement gives **94.1%** on Arabic tokens
and **94.5%** on running text. The running-text lift is *smaller* than the +1–2 pp the projection implied:
this window carries 7.3% punctuation and every one of those tokens is a free cover — a convention that cannot
fail, not a rendering result. Always report the denominator with either number (§4.7).

### 4.9 Held-out validation of the vocalised bypass, and its orthography lock *(2026-10-10)*

`src/score_closed_class_bypass.py` (artifact `data/closed_class_bypass_heldout.json`). Map trained on
Tashkeela books 0–9, scored on a **disjoint** slice (books 60–96), with EQTB as a cross-corpus control. A hit
is exact string equality with the token as it appears; normalisation is used to *match* a surface but never to
award a hit.

**In-domain (Tashkeela books 60–96):** 67,563 matched closed-class tokens in 300,000 scanned.

| | value |
|---|---|
| micro precision, held out | **91.00%** — vs 91.09% in-sample: a 0.09 pp drop, so not memorisation |
| over vocalised tokens only | 91.62% |
| **Tier 1 (conf ≥ 0.95, 86 surfaces)** | **99.54%** · 62.2% of matched tokens |
| Tier 2 (45 surfaces) | 77.85% |
| policy delivered | 42,012 tokens = **14.0% of running text at 99.54%** |
| policy abstained | 25,255 tokens = 8.4% (falls back to bare surface / upstream head) |

Threshold sweep — the gate is a *choice*, so the sweep answers the useful question (how far can it drop and
still hold 99.5%?):

| threshold | surfaces | % of running text | precision |
|---|---|---|---|
| ≥ 0.999 | 74 | 10.4% | 99.66% |
| ≥ 0.99 | 78 | 12.4% | 99.66% |
| ≥ 0.98 | 80 | 13.2% | 99.60% |
| **≥ 0.95** | 86 | **14.0%** | **99.54%** |
| ≥ 0.90 | 93 | 15.9% | 99.44% |
| ≥ 0.80 | 101 | 18.6% | 97.83% ← the cliff |
| ≥ 0.00 | 131 | 22.4% | 91.40% (no real threshold) |

**Recommended threshold: ≥ 0.95** — the smallest threshold still meeting 99.5%, and the placement is not
arbitrary: precision holds ≥ 99.5% from 0.999 down to 0.95, then breaks up at 0.90 (−0.10 pp) and falls off a
cliff at 0.80 (−1.71 pp). Held out, the band is slightly *wider* than the in-sample run implied.

**Cross-corpus — the bypass is ORTHOGRAPHY-LOCKED, and EQTB proves it.** On EQTB uthmani (Qur'anic):

| | value |
|---|---|
| matched closed-class tokens | 68,045 |
| **unvocalised share** | **45.7%** — Uthmani orthography leaves tokens bare (و×6,056 vs وَ×3,969) |
| raw micro precision | 18.67% |
| over vocalised tokens only | 36.10% |
| Tier 1 over vocalised only | **41.41%** — fails outright |
| tokens not in the TRAIN map at all | 8,463 (12.4%) — ٱلْ (alef wasla) and other Uthmani forms |

The 45.7% bare share reproduces the §2x.5 figure exactly, so this is the same convention and not a new
defect. But the split does **not** rescue the number: even over vocalised tokens only, Tier 1 is 41.4%. The
residual cause is orthographic variant forms (alef wasla, Uthmani spellings) that an exact-string map trained
on standard orthography cannot reach. **Conclusion: the bypass is sound for standard-orthography vocalised
text and requires a normalisation layer before Qur'anic/Uthmani input** — which matters here, because EQTB
and QAC are this project's Qur'anic corpora.

**The 300-row human gold cannot validate the bypass**: only 3 of its 300 target tokens are closed-class (it is
content-word focused by design). Recorded so nobody later cites it for this component.

### 4.10 The Uthmani fold layer — what it fixed, what it could NOT, and the register finding *(2026-10-10)*

`src/normalize_uthmani.py` (self-test 12/12 PASS; audit `data/normalize_uthmani_audit.json`). NFC, then
removal of tajwīd/annotation marks (small high letters, sajdah/pause signs, U+06DD end-of-ayah, extended-A),
then letter folding — **alef wasla ٱ→ا and dagger alef ٰ→ا**, because both denote a long /aː/ and the map
contains the folded letter.

**Two of my own first-draft folds were wrong, and measurement caught both:**
- `آ → ا` — corrupted `قُرْآن → قُرْان`, `آية → اية`. U+0622 is *standard* orthography and the map contains it.
  Removed.
- `ى → ي` — corrupted **28.97%** of a Tashkeela sample (`عَلَى → عَلَي`, `حَتَّى → حَتَّي`). `MATCH_NORM` maps
  ى→ي to build a lossy *lookup key*; the emitted/compared string may not be lossy. Removed, and the
  distinction is now written into the source.

**Safety, proven rather than asserted.** The layer includes NFC, so it must be applied to the map as well
(the both-sides contract). Folded both sides, the held-out Tashkeela run returns **91.00% micro / Tier 1
99.54% / 141 surfaces / 67,563 tokens — identical to the unfolded run** (regression guard passes). And the
audit's new **skeleton-change** metric — base-letter substitution, which would be a bug — is:

| corpus | changed by the layer | SKELETON-change | verdict |
|---|---|---|---|
| Tashkeela (60,000 tok) | 24.28% (NFC ordering only) | **0** | provably non-destructive |
| EQTB (60,000 tok) | 24.08% | 8,363 | the intended wasla/dagger folds |

**EQTB: the fold helps, and still does not rescue it.**

| EQTB uthmani | RAW | FOLDED |
|---|---|---|
| micro precision | 18.67% | 20.77% |
| over vocalised only | 36.10% | 37.63% |
| Tier 1 | 26.49% | **31.26%** |
| tokens not in the map | 8,463 (12.4%) | 8,600 (12.6%) |

The fold did fix the unreachable forms — `ال`'s held-out distribution went from `ٱلْ×2168 · ٱل×1032`
(invisible to the map) to `الْ×5377` — which is exactly why Tier 1 rose ~5 pp. But the projected
"unmapped → ≈0%" was **based on a wrong model of the failure and did not happen**, for two measured reasons:
(1) `match_key` already folds wasla for *lookup*, so ا-wasla was never what made tokens unmapped — the
12.4% are surfaces the *evidence slice* never produced; and (2) **45.7% of EQTB's matched tokens are left
bare by Uthmani orthography** (`و×6,056` vs `وَ×3,969`). No transliteration layer can supply a vowel the
corpus did not write. Lowering the threshold cannot help either: no threshold in the sweep reaches 99.5%.

**The right Qur'anic gold already existed locally: QAC 0.4's `FORM` column.** Its layout is
`LOCATION  FORM  TAG  FEATURES` — column 2 is fully-vocalised Buckwalter, decoded by
`reconcile.qac_form_to_arabic` (a `grep FORM:` returns zero because it is positional, which nearly hid it).
Only **6.0%** of QAC's matched tokens are bare, so it is a genuine vocalisation reference. (`quranic-treebank.csv`
beside it is a **decoy** — 5 columns of verse text, flagged by `inspect_eqtb.py`.)

| gold | bare share | micro | Tier 1 |
|---|---|---|---|
| Tashkeela held out (**in-register**) | 1.1% | 91.00% | **99.54% HOLDS** |
| QAC FORM (**cross-register**, map from Tashkeela) | 6.0% | 43.25% | 59.60% |
| QAC FORM (**in-register**: map surahs 1–57, eval 58–114) | 6.0% | 75.10% | **97.31%** (99.26% over vocalised) |
| EQTB folded (cross-register) | 45.6% | 20.77% | 31.26% |

**So the mechanism is sound and the map does not transfer across registers.** In-register QAC finds **1**
unmapped token instead of 8,074, and **47 of 101** closed-class surfaces take a *different* majority
vocalisation in Qur'anic Arabic than in modern edited prose — `إِنَّ×1513` where the Tashkeela map chose
`أَنَّ`, `فِى×1158` where it chose `فِي`, `عَلَيْ×714` where it chose `عَلَى`, `هِنْ/هِمْ` where it chose
`هُمْ`, `لَ` where it chose `لِ`. These are register facts, not defects: the right policy is **one map per
register** (or a register-conditioned map), not more folding. In-register, the gate is reachable at
**≥0.98 → 99.52%**.
(Caveat: the in-register eval slice is surahs 58–114 — the short, oath/rhyme-heavy surahs — so it is a
*conservative* test of the register, not a favourable one.)

## 5. Open questions

1. **X's policy** — 1,380 test-floor tokens, 5,115 train lemmas, 62% coverable. Decided in §4.6:
   verbatim pass-through, out of scope for both mechanisms. Open sub-question: does the pass-through emit
   the surface as it stands (safest) or attempt a guess?
2. **Ambiguity — MEASURED, then HELD OUT (§4.5, §4.9):** 91.09% in-sample → **91.00% held out** on a
   disjoint Tashkeela slice; **Tier 1 99.54%** at the recommended ≥ 0.95 threshold. The remaining open item
   is the *conditioning signal* for the Tier-2 tail (77.85%): UPOS alone, or UPOS + dependency +
   following-clitic? That needs the tail re-measured under each signal, which requires tagged vocalised data
   (Tashkeela is untagged) — the same place the deferred arm-4 work belongs (`score_arm_gold.py`, live head
   logits).
3. **Do the 149 rootless content words (§2x.8) belong with X?** §4.6 says yes — one policy for both.
4. **Punctuation — MEASURED (§4.7): 315 PUNCT/SYM in the test prefix, all identity.** Closed. Remaining nit:
   identity is correct for *scoring*, but a corpus's punctuation set should be asserted, not assumed.
5. **RESOLVED-IN-PART — the "normalisation layer" was the wrong fix (§4.9, §4.10).** The bypass is not
   orthography-locked in the way §4.9 concluded: it is **register**-locked. The Uthmani fold layer
   (`src/normalize_uthmani.py`) is built, self-tested and provably non-destructive (Tashkeela
   skeleton-change 0, in-domain score unchanged), and it lifted EQTB Tier 1 26.49% → 31.26% by reaching
   `ٱلْ`/`ٱل` forms. But EQTB cannot be rescued by folding because **45.7% of its tokens are bare in
   Uthmani orthography** — there is no vowel in the text to match. Against a genuinely vocalised Qur'anic
   gold (QAC `FORM`, 6.0% bare) the Tashkeela-trained map still scores only 59.60%, while the SAME corpus
   scored in-register (map from surahs 1–57) reaches **97.31%** with **1** unmapped token. **47 of 101**
   shared surfaces have a different dominant vocalisation in the Qur'an than in modern prose. The open work
   is therefore: **build one map per register** (or condition the map on register), and re-run the gate per
   register — not more folding.

## 6. Reproduce

```bash
.venv/Scripts/python.exe src/build_closed_class_inventory.py   # writes data/closed_class_inventory.json
.venv/Scripts/python.exe src/audit_arity_failures.py           # the 17 content-word failures, reconciles vs --measure
.venv/Scripts/python.exe src/renderer.py --measure --limit 4000                 # the FROZEN 4,000-Arabic-token baseline
.venv/Scripts/python.exe src/renderer.py --measure --limit 4000 --include-punct # running text; writes renderer_report_punct.json
.venv/Scripts/python.exe src/measure_closed_class_ambiguity.py                  # ambiguity, IN-SAMPLE
.venv/Scripts/python.exe src/score_closed_class_bypass.py                       # Tier-1 precision, HELD OUT (the honest one)
.venv/Scripts/python.exe src/score_closed_class_bypass.py --fold-uthmani --qac-gold --qac-split   # Uthmani fold + QAC gold + in-register split
.venv/Scripts/python.exe src/normalize_uthmani.py --selftest                    # the fold layer's known answers
.venv/Scripts/python.exe src/normalize_uthmani.py --check eqtb tashkeela        # fold audit (Tashkeela skeleton-change must be 0)
```
