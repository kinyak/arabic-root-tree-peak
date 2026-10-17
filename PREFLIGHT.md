# PREFLIGHT — theoretical review + what to build before spending any compute

Status: **design rev. 3/4 as written; superseded in places — see the rev-8 status block below.** Nothing has
been trained. **Every item below is local CPU work: 0 compute units.**
Companion files: `START-HERE.md` (cold-start brief — read that first if you have no memory of this project),
`HANDOFF.md` (verified facts + blockers), `COLAB.md` (run costs), `RESOURCES.md` (supply list),
`EVIDENCE_LOG.md` (the live register — **its §2g/§2h supersede this file's triage**),
`data/raw/MANIFEST.md` (what is on disk, hashed, and which scripts read it).

---

## Rev-8 status block (2026-10-09) — read before the triage below

**Superseded here:** A15's "no renderer" (a rule renderer exists and is measured — `fix_renderer.py`, 94.3%
exact at 30.0% token coverage), and the state column of Part C item 1 (root converter — the PADT→Arabic and
QAC-Buckwalter mappings are now derived, validated on 2,046 aligned pairs, and shipped in `src/reconcile.py`).

**Corrected numbers:** `EVIDENCE_LOG.md` §2d's root-recovery claim (96.4% / 99.8%) was degenerate and
in-sample; the held-out measurement is **92.5% coverage at 99.7% correctness**, and PADT's usable root
supervision is **50.1%** of its `Root=` tokens, not 100%. See `EVIDENCE_LOG.md` §2h and `SPEC-REV6.md` §8.2.

**Still open, in priority order:** A13 (supervisory parity — the baseline's auxiliary heads are specified
nowhere in code), A14 (non-CALIMA blindness protocol), the wazān proclitic strip, Tashkeela coverage, the
merged JSONL, the eval harness, and every training artifact.

**Kaggle gate:** the nine blockers that keep this off Kaggle are itemised in `EVIDENCE_LOG.md` §5.

---

## Part 0 — Triage (added rev. 4; Part A as written was a list, not a plan)

14 numbered challenges with star ratings does not tell you what to *do*. Sorted by what actually blocks:

**FATAL — the experiment is uninterpretable until these are resolved**
- **A13** baseline gets 1 label/token vs the treatment's ~6 → fix: aux heads on the baseline *(still open — specified in `SPEC-REV6.md` §5.2, implemented nowhere)*
- **A14** evaluation is CALIMA-mediated and the treatment trained on CALIMA → fix: blind, non-CALIMA gold *(still open — no protocol, no OOD set, no harness)*
- **A15** the renderer does not exist → ~~fix: table-based renderer + rule fallback~~ **partly superseded (rev. 8): the rule renderer exists and is measured at 94.3% exact / 30.0% coverage; CAMeL is confirmed unable to generate**

**SERIOUS — mechanical, fixable by writing code or a paragraph**
- wazān extraction is **class-biased**, not merely low-yield (Part B) — the largest single pipeline risk
- A6 tensor/table (delete the tensor) · A7 loss weights (one-line formula) · A8 precedence table ·
  A10 syntax as ablation · A11 gloss as post-step · A12 escape-safe schema

**ALREADY RESOLVED**
- **A1, A2** — dissolved by `docs/SOLVING.md` (observed graph + surface-order linearisation)
- A4 — an ablation, not a blocker · A9/A10 — protocol and framing decisions

**The three that decide whether a paper exists: A13, A14, A15.**

### A15. There is no renderer ★★★ *(new — the preflight assumed A5's fix worked; it does not)*
Verified this round: **`calima-msa-r13` raises `GeneratorError: DB does not support generation`**, and
`Reinflector` raises the same. So "use CAMeL's generator as the renderer" — the fix proposed in
`docs/SOLVING.md` for A5 — **is not available.** The only other MSA database, `calima-msa-s31` (44.8 MB),
is **LDC-licensed** and not installed, so it is a licence question before it is a technical one.
**Consequence:** the renderer must be built. The viable path is a **memorised table**
`(root, wazān, case, clitics) → surface`, harvested from the gold corpora, with a rule-based template
fallback (the pattern's digits say where the radicals go — pure string substitution for sound roots) and
explicit إعلال/إبدال handling for weak roots. This is buildable and it is *not* a neural problem.
**Open measurement:** the table's coverage is currently **unmeasured** — a 487-record sample split in half
gave 18%, but that is an artefact of the sample (too few repeats), not a coverage estimate. Rerun on the
full corpus before quoting any number.

---

## Part A — Theoretical challenges

Ranked by how badly each one threatens the result.

### A1. The dependency graph is a latent variable with no stated training scheme ★★★
§2 says the model "generates an order-free dependency graph." §4's Head 4 is a *supervised* head predicting
head position and label. **Nothing connects the two.** A discrete graph is not differentiable, so you must
choose one of: gold tree supervision at every step (thin data, and inference still needs a decoder);
REINFORCE (very high variance at 25M params); a relaxation (Gumbel-softmax — now the graph is soft and the
deterministic renderer can't consume it); or marginalising over all trees (expensive). The spec picks none.
**This is the deepest gap in the design** — everything else is fixable, this one is a research decision.

### A2. "Order-free" fights autoregressive decoding ★★★
A set of edges has no canonical order; autoregressive models require one. You either impose an order (and
it is no longer order-free) or you do non-autoregressive set generation (which loses the conditioning that
makes transformers strong, and you need a stopping rule). Worse: **Arabic word order is grammatically
load-bearing** — verbal (جملة فعلية) vs nominal (جملة اسمية), and fronting for emphasis/ḥaṣr. Declaring the
plan order-free means the renderer must reinvent a layer the grammar actually encodes.

### A3. The two arms are not scored on the same kind of object ★★★
The treatment emits **grammar**, and a deterministic renderer emits surface. The baseline emits **surface
directly**. If you then report "the treatment gets roots right 94% of the time" against a baseline scored
on next-token loss, the comparison is meaningless — the treatment is judged on a *much smaller hypothesis
space*. Predicting a root is a few digits of entropy; predicting the characters is far more.
**Requirement:** score both arms on the *same* metric computed from their *final surface output* — run both
through the identical analyser and score roots/case/i'rāb the same way. Without this the paper is
refereed as a rigged comparison. **This is the biggest threat to validity, and it is cheap to fix.**

### A4. Head 5 is nearly a function of Head 4 ★★
Case is *governed by the role*: فاعل → nominative, مفعول به → accusative, مضاف إليه → genitive. Once the
role is right, the case is mostly lookup. So Head 5 largely duplicates Head 4, its accuracy is **capped by**
Head 4's, and reporting both as independent achievements is close to double-counting. Keep both as training
signal (auxiliary losses do regularise), but the ablation must show Head 5 adds something Head 4 doesn't.

### A5. "Root + pattern → surface" is not a function ★★
The spec calls §2 Step 3 "Binds Roots into Awzān" as if it were arithmetic. It isn't. Arabic
morphophonology rewrites the stem: **hollow** (قال from ق-و-ل, the و elides), **defective** (دعا from د-ع-و),
**assimilated** (وعد with initial weak radical), **doubled** (مدّ with إدغام), plus hamza seat rules, alef
maqsura vs final ي, and the dagger alif. That is a few hundred ordered rules — which is exactly what
CAMeL Tools' *generator* already implements.
**Consequence:** if you use CAMeL's generator as the renderer, the rendering contribution is **CAMeL's, not
yours**, and the paper must say so plainly. Your contribution is the *representation and planning*, not the
spelling.

### A6. §2.1's two proposals are mutually exclusive ★★
A `28×28×28` tensor with "invalid combinations masked" requires a canonical root list to know what is
invalid. A **factorised per-position embedding** — which is what the reference code actually implements —
has no such table and nothing to mask. You cannot claim both. And 28³ − 6,500 = **15,452 wasted cells
(70%)**, which buys nothing over a flat 6,500-row table except the topology claim in §2.1, which (per
`HANDOFF.md` §5.1 item 4, and the permutation analysis) has no mechanism behind it.

### A7. No scheme for the five-way loss weighting ★★
Cross-entropy over 6,500 roots vs. a 4-way case classifier are wildly different scales. A naive
`L = L₁ + λ₂L₂ + …` is dominated by whichever head has the largest vocabulary, so the small heads barely
learn. You need per-head normalisation or learned uncertainty weighting (Kendall et al.). Unspecified.

### A8. Merged treebanks conflict, not just go missing ★★
§3.3 masks *absent* labels. It does not handle **conflicting** ones: CATiB-derived vs UD conventions,
four incompatible root transliteration schemes, case annotated on only 45–52% of tokens, and four different
deprel inventories. Without a harmonisation spec the model learns *source artefacts* and reports them as
grammar. Needs a written precedence rule per field.

### A9. Evaluation contamination ★★
If the eval set is held-out rows of the same treebanks, you measure in-distribution fit, not grammar. And
because CALIMA supplies silver labels for Tashkeela, silver training leaks into any eval drawn from a
similar distribution. **You need an out-of-domain, hand-checked eval set** — a different genre from every
training source — or the result is uninterpretable.

### A10. Capacity: the syntax claim is hostage to thin data ★
15–25M parameters must carry morphology *and* syntax learned from ~35k sentences of gold trees. Expect the
morphology heads to work and the syntax head to be weak. **Design the paper so the strong claim
(morphology: root/wazān/case) is not hostage to the weak one (syntax).** Make the syntax head an
ablation, not the headline.

### A11. `"meaning"` in §6.2 cannot come from the model ★
The delivery schema includes an English gloss per word. A deterministic renderer can't produce it and no
head in §4 predicts it. It needs either a dictionary lookup (arramooz / EQTB `lemma`) or a sixth head.
Unspecified.

### A12. The GBNF constrains the *delivery* format, not generation ★
The model emits grammar; the renderer emits `"tashkeel"`. The grammar in §6.2 therefore constrains the
*renderer's* output, not the model's. Conflating the two will make the constrained-decoding discussion
incoherent in the write-up. (Its `string` rule is still unsafe regardless — `[^\"]*` admits raw newlines
and unescaped backslashes.)

---

### A13. The baseline gets 1 label per token; the treatment gets ~6 ★★★
Measured per-step decision cost: baseline = **14.97 bits** (14.97 = log₂32k), treatment = **27.16 bits**
(root 390 × wazān 216 × offset 16 × role 37 × case 3). So the treatment does **more** work per step, not
less — my earlier "smaller hypothesis space" framing was wrong. The real confound is **supervision density**:
the treatment receives root + wazān + role + case + arity labels on every token where the baseline receives
one token id. Train the arms that way and the treatment wins because it was given six answer keys, which
proves nothing about the architecture.
**Fix (required):** give the baseline the **same auxiliary heads** predicting root / wazān / case /
role from its own hidden states, at the same weights from the same config file. Then the *only* remaining
difference is that the treatment **generates through** the factorised representation while the baseline
generates surface and predicts the labels as auxiliaries. That isolates the architectural claim.
**Without this the headline result is uninterpretable.**

### A14. Evaluation is CALIMA-mediated, and the treatment was trained on CALIMA ★★★
The treatment trains on CALIMA silver labels (Tashkeela). The scorer analyses surface with CALIMA. If the
OOD gold labels are "CALIMA output plus hand-correction," annotators anchor on the analyser. The result is
a closed loop: **the treatment is scored on agreement with an annotator it was specifically trained to
imitate, while the baseline was not.**
**Fixes:** (a) eval labels must come from human annotation or from independent treebanks — never from
CALIMA; (b) annotate a **blind** subset with no analyser output shown, and report inter-annotator agreement;
(c) report CALIMA-vs-human agreement so readers can see the metric's ceiling; (d) state plainly in the paper
that CALIMA silver is **distillation**, and that the gold treebanks carry the evaluation-relevant signal.

---

## Part B2 — Decoder requirements, measured

`src/measure_decoder_requirements.py` over both treebanks. These numbers size the arity/projectivity design.

| Measure | PADT (news) | NYUAD (PATB) |
|---|---|---|
| Non-projective arcs | **0.40%** (1,108 / 274,720) | **0.02%** (161 / 719,151) |
| Fully projective sentences | 91.13% | 99.40% |
| Max left dependents | 9 | 16 |
| Max **right** dependents | **28** | **105** |
| Tokens with >4 left deps | 0.079% | 0.110% |
| Tokens with >4 right deps | 0.734% | 1.548% |

**Consequences:**
1. **Non-projectivity is negligible (0.4% of arcs).** The "emit distance only for non-projective arcs"
   simplification is safe — but it saves so little that the simpler option is to **always emit distance**:
   ~4 bits on 99.6% of tokens is not worth the projectivity machinery, and it removes the need to verify
   projectivity at all.
2. **Right-arity has a long tail to 105**, so the count must not be truncated. The `>4` overflow class plus
   a unary continuation bit is **necessary**, not over-engineering. A fixed 0–4 vocabulary would corrupt
   ~1.5% of NYUAD tokens.
3. **Arity distribution** (PADT, right): 0 → 165,444 · 1 → 70,069 · 2 → 31,882 · 3 → 9,723 · 4 → 3,193 ·
   5+ → 2,073. So explicit classes 0–4 cover ~99.3% of right-dependents and ~99.9% of left.
4. A hard cap (e.g. 64) on the continuation loop is still needed — an unbounded generation loop is a real
   inference failure mode.

---

## Part B — The wazān inventory, measured (this changes §2.2)

`src/build_wazan_inventory.py`, run over 6,000 PADT tokens. Decomposition = junk filter, structural gate,
strip proclitic, strip terminal case vowel.

**Only 26.6% of tokens survive a strict structural gate.** Full verdict breakdown:

| Verdict | Share | Meaning |
|---|---|---|
| `ok` (digits exactly {1,2,3} or {1,2,3,4}) | **26.6%** | cleanly decomposable |
| `digit_set_none` | 23.6% | **mostly legitimate** — particles, pronouns, proper nouns have no wazān at all (but `NTWS`-style junk hides here too) |
| `digit_set_12` | 11.7% | |
| `digit_set_13` | 8.9% | |
| `digit_set_1` | 7.1% | **weak roots** — the elided radical is written as a literal letter |
| `digit_set_23` / `_2` / `_3` | 6.2% | |
| partial quadriliteral sets | 0.3% | |
| `filtered_out` (not `source=='lex'`) | 15.6% | |

**The finding: the digit convention is only reliable for sound triliteral roots.** For hollow, defective
and assimilated roots — a large share of real Arabic — CALIMA writes the weak radical as a **literal
letter**, so the radical-digit set comes out incomplete. This is the real content of §3.2's "handles
radical substitution" note, and it is **far bigger than the spec implies.**

**The recoverable path:** you already have the `root` field. Align the pattern's literal letters against
the known root to rebuild the full radical skeleton. That is implementable and should be the next build.

**Inventory size — the "≈70" claim does not hold:**

| Measure | Value |
|---|---|
| Distinct wazān, proclitic + case stripped | **216** |
| Covering 50% of tokens | **17** |
| Covering 90% of tokens | **99** |
| Appearing exactly once | 82 |

**And 216 is still an overcount**, because the *suffix* was not stripped: `فَعَلَت`, `فَعَلات`, `فاعَلات`,
`فَعَّلَت` are the same template as `فَعَل` plus a subject-agreement suffix. CALIMA separates pronominal
enclitics in `enc0`, but verb agreement suffixes live in `pgn`/`person`/`gender`/`number` and stay in the
pattern. **Stripping them is unfinished work and the next number to get right.**

**Quadriliteral templates are confirmed present** — `فَعْلَلِيّ`, `فُعْلُلَة`, `فَعْلَلِيَّة`, `فَيْعَلُول`,
`فُعْلُولِيَّة` — independent evidence that a 3-slot tensor cannot hold the inventory (A6 above).

### B1. The extraction failure is CLASS-BIASED, not merely low-yield *(added rev. 4)*

The 26.6% pass rate is the less important number. The distribution of the failures is the real problem.
Measured **unconditionally** over all lexicon-backed analyses with a root (1,275 tokens), so the figure is
not contaminated by the gate itself:

| Root class | Tokens | Share | Passes the gate | **Gate rate** |
|---|---|---|---|---|
| sound (صحيح) | 724 | 56.8% | 437 | **60.4%** |
| quadriliteral (رباعي) | 295 | 23.1% | 14 | **4.7%** |
| short/other | 175 | 13.7% | 0 | **0.0%** |
| doubled (مضعف) | 81 | 6.4% | 36 | 44.4% |
| **TOTAL** | **1,275** | | **487** | **38.2%** |

**The gate admits sound roots at 60.4% and quadriliterals at 4.7%.** So it does not fail randomly — it
systematically **filters the training set toward sound triliteral roots**, which are the one class where the
digit convention works. Head 3 would be trained on a class-skewed subset and then evaluated on everything.
That is a silent distribution shift inside the model, not just wasted data.

⚠️ Two caveats on the table itself: the quadriliteral share (23.1%) is **almost certainly inflated** — Arabic
quadriliterals are ~2.4% of roots (`HANDOFF.md` §3.2), so CALIMA's `root` field evidently carries augmented
forms my classifier mislabels. And hollow/defective/assimilated come out at **0%**, which cannot be right for
real Arabic prose — the classifier or the `root` field is losing them. **Both need validation against the
1,642-root QAC list before this table is quoted anywhere.**

---

## Part C — Build these locally before touching Colab

Nothing here needs a GPU. Doing it now means Colab minutes are spent **only** on training.

| # | Artifact | Why it must exist first | State |
|---|---|---|---|
| 1 | **Canonical root converter** — QAC Buckwalter, PADT translit, CALIMA dot-Arabic, EQTB Arabic → one scheme | 4 incompatible schemes; without this you cannot merge or compute a single accuracy | ✅ **PADT→Arabic + QAC Buckwalter derived and validated** (~2,046 aligned pairs, every unambiguous unit 100%) in `reconcile.py`; CALIMA/EQTB ingestion not wired |
| 2 | **Wazān extractor v3** — + suffix stripping + weak-root alignment via the `root` field | B, above: only 26.6% decomposes today | ⚠️ v1 done, v3 needed |
| 3 | **Canonical wazān inventory** | §2.2 asserts ~70; measured 216 and falling as stripping improves | ⚠️ provisional |
| 4 | **Harmonisation + precedence spec** — per-field rule for conflicting treebanks | A8: otherwise you train on source artefacts | ❌ not started |
| 5 | **Merged JSONL** — one record per token, per-head target + per-head mask | the training input | ❌ not started |
| 6 | **Fixed GBNF** — escape-safe `string` rule | A12 | ❌ not started |
| 7 | **Renderer decision + prototype** — CAMeL generator vs. own rules | A5: determines what you can claim as yours | ⚠️ decided by default: CAMeL **cannot** generate (re-verified), so the rules are yours; prototype = `fix_renderer.py` |
| 8 | **Eval harness** — identical scoring for both arms, from final surface output | **A3 is the validity threat; build this before any training** | ❌ not started |
| 9 | **Out-of-domain gold test set**, hand-checked | A9 | ❌ not started |
| 10 | **One shared config file** both arms read (size, steps, seeds, splits) | matched-size claim is only credible if it's literally the same file | ❌ not started |
| 11 | **Smoke test** — tiny model, tiny data, full loop end to end | catches pipeline breaks before burning units | ❌ not started |
| 12 | **Licence/provenance ledger** — source → licence → permitted use | 4 copyleft/non-commercial sources now; the paper must state it | ✅ named per-source in `SPEC-REV6.md` §7 + `RESOURCES.md` §7 (arramooz added) |
| 13 | **Pre-registered metric table** — the exact numbers you will report, fixed now | stops accidental (or perceived) cherry-picking | ❌ not started |
| 14 | **Renderer** — `(root, wazān, case, clitics) → surface` table + rule fallback | **A15: CAMeL cannot generate.** Now on the critical path, not a later nicety | ⚠️ rule route prototyped (`fix_renderer.py`): 94.3% exact at **30.0% coverage**; coverage after reconciliation **unmeasured** |
| 15 | **Falsification criterion + minimum detectable effect** | without a stated refutation condition the experiment cannot fail, which means it cannot succeed | ❌ not started |
| 16 | **Fallback publication path** | see note below — de-risks the entire project | ⚠️ identified (five resource-paper deliverables, below); not built |

**Tally as of rev. 8: 2 complete (1, 12) · 5 partial (2, 3, 7, 14, 16) · 9 not started.** The not-started set
is exactly the training-side half: merged JSONL, harmonisation, GBNF, eval harness, OOD gold, shared config,
smoke test, pre-registered metrics, falsification criterion.

**Order of work (corrected rev. 4 — the rev. 3 order was stale and contradicted the A14 finding):**

```
1 → 2 → 3 → 14 → 8 → 9 → [annotate] → 4 → 5 → 10 → 11 → (Colab) → 6 → 13
└──────── code track ────────┘  └─ writing/annotation track ─┘
```

**Why this order and not rev. 3's:**
- **14 (renderer) moves onto the critical path.** Rev. 3 had it after the first training run, assuming
  CAMeL's generator was available. It is not (A15), so nothing can be scored until it exists.
- **8 (harness) before 9 (annotation), because blindness cannot be retrofitted** (A14). The moment anyone
  looks at CALIMA output while labelling, the OOD set is compromised and no later work repairs it. The
  protocol must exist *before* a single sentence is annotated.
- **4 (harmonisation) runs in parallel** — it is a writing task, and its precedence rules are easier to
  justify once items 1–3 have produced real numbers.
- 6 (GBNF) and 13 (pre-registration) genuinely come last: you cannot constrain output you cannot yet
  generate, and you cannot pre-register metrics before the syntax ablation is decided.

### Item 16 — the fallback publication path (currently missing, and it is the best risk reducer)

The preflight as written has a single point of failure: **if the architecture does not beat the baseline,
there is no paper.** That is avoidable, because most of the work products are **independently publishable
resources** that exist regardless of whether the root-tree thesis wins:

- a **canonical wazān inventory** with measured frequency (currently 216 and unstable — nobody has published this cleanly)
- a **class-aware (root-class × wazān) validity matrix**, which is a genuinely useful artefact for Arabic
  generation (measured fill rate 0.97% at sample scale)
- a **weak-root pattern-alignment method** — the piece that makes CALIMA's `pattern` usable at all
- a **corrected CALIMA decomposition recipe**, including the `cas` mapping fix (`u` = undefined, not Damma)
- a **class-bias audit** showing that naive filtering silently skews a corpus toward sound roots

Those five are a resource/data paper on their own. **Build them as deliverables in their own right, not as
by-products of the model experiment.** Then the project cannot fail outright — it can only fail to be the
*better* paper.

---

## The four decisions only you can make

1. **How is the graph trained?** (A1) Gold-supervised parsing head, RL, relaxation, or — the cheap option —
   drop explicit graph planning from v1 and let the autoregressive model implicitly learn order through
   the root/wazān representation. **The last one costs you the "order-free planning" headline but makes the
   paper finishable.** This is the fork.
2. **Is the renderer yours or CAMeL's?** (A5) Reusing CAMeL's generator is honest and fast; it moves the
   novel claim entirely onto the representation.
3. **What is the eval set?** (A9) In-domain held-out (easy, weak) vs. out-of-domain hand-annotated (hard,
   convincing). Determines how much of the prep work is yours.
4. **Does the syntax head appear in the headline result?** (A10) Recommend: no. Lead with morphology.
