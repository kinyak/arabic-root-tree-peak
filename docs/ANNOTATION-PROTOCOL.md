# BLIND ANNOTATION PROTOCOL — v1 (frozen 2026-10-09)

> **This protocol is FROZEN before annotation begins.** That is the whole point: anchoring
> cannot be undone. Once an annotator has seen an analyser's answer, that label is
> contaminated permanently, and no amount of later care recovers it.
>
> **Sheet:** `data/annotation/pilot-annotation-sheet.csv`
> **Frozen sha256:** `fa1bf627fdeda7eee0ed75147b690aa4efa0f27fbad5d4723a255f45a518f8b5`
> **Rows:** 50 (40 carry withheld gold, 10 deliberately carry none)

---

## 1. Why this exists

The treatment model **trains on CALIMA-derived silver**. If the labels that *score* it were
also produced by someone looking at CALIMA, then the evaluation is a closed loop — the
model is being scored on agreement with the very system it was trained to imitate. The
result would look good and mean nothing.

So the scorer must be built from **human judgement formed without seeing any analyser
output** (`docs/SPEC-REV6.md` §5.3).

There is a second, more basic reason. **Wazān (وزن) has no public gold annotation
anywhere.** That is why Head 3 can currently only be reported as *coverage*, never
accuracy. This sheet is the only route to ever scoring it — and wazān is the column that
matters most here.

## 2. THE ONE RULE

**Do not consult any Arabic morphological analyser, parser, dictionary tool, or existing
treebank while filling this in.** That means no CAMeL Tools, no CALIMA, no QAC/EQTB/PADT
files, no online analyser. Use your own knowledge of Arabic grammar (and, if you wish, a
printed or PDF lexicon — but not an analyser that is being evaluated).

**Do not open `data/annotation/private/pilot-annotation-KEY.csv`.** It contains EQTB's own
root and case for 40 of the 50 rows. Opening it destroys the blindness of the entire
exercise. It is `.gitignore`d, and it exists only so I can measure your labels against an
independent gold afterwards.

## 3. What to fill in

| column | what goes in it | format |
|---|---|---|
| `root` | the **stem's** radicals, consonants only | dot-separated Arabic letters: `ق.ت.ل` |
| `wazn_pattern` | the **stem's** pattern, as digits standing for the radicals | digits `1`,`2`,`3` (and `4` if there are four radicals), **with the vowels kept**: `1َ2ْ3` |
| `case` | the nominal case, **nouns/adjectives only** | `NOM` / `ACC` / `GEN` / `ABSTAIN` |
| `confidence` | your confidence in the row | `high` / `medium` / `low` |
| `notes` | anything the format can't express | free text |

### 3a. The `wazn_pattern` format — this is the part that needs the most care

Write the pattern **with the digits in place of the radicals and every vowel written
explicitly**, then **delete the final case vowel** (see 3c).

| word | stem fَعَل style | what to write | because |
|---|---|---|---|
| `كَتَبَ` | فَعَلَ | `1َ2َ3` | three radicals in order |
| `كِتَاب` | فِعَال | `1ِ2ا3` | the long alif is part of the pattern |
| `الْقَتْل` | فَعْل | `1َ2ْ3` | sukun is part of the pattern |
| `مُعَلِّم` | مُفَعِّل | `مُ1َ2ِّ3` | shadda **doubles** the radical — do **not** repeat the digit |
| `مُسْتَشْفَى` | مُسْتَفْعَل | `مُسْتَ1ْ2َ3` | template letters stay as letters |

**A shadda never means "write the digit twice."** `مُعَلِّم` is `مُ1َ2ِّ3`, not `مُ1َ2ّ2ِ3`.
(Getting this wrong is a known failure mode — the project has a recorded bug where a
templatic shadda was expanded into a duplicated slot.)

### 3b. Root and pattern are for the STEM, not the whole word

The target word may carry a preposition, the definite article, or a pronoun suffix. Those
are **not** part of the root or the pattern.

* `بِعَذَابٍ` → stem is `عَذَاب` → root `ع.ذ.ب`, pattern `1َ2ا3`
* `الْقَتْلِ` → stem is `قَتْل` → root `ق.ت.ل`, pattern `1َ2ْ3`
* `يُقَتِلُونَكُمْ` → stem is `قَتِل` → root `ق.ت.ل` (the `يُ`, `ُونَ`, `كُمْ` are affixes)

### 3c. The final case vowel is NOT part of the pattern

Head 3's label deliberately excludes the case vowel, which is why `case` is a separate
column (`SPEC-REV6.md` §3.2). So:

* `الْقَتْلِ` → pattern `1َ2ْ3`, case `GEN` — the final kasra is *not* in the pattern
* `نَفْسًا` → pattern `1َ2ْ3`, case `ACC` — the fathatan is *not* in the pattern
* `كَتَبَ` (verb) → pattern `1َ2َ3`, case `ABSTAIN`

**Write the pattern as if the word carried no case ending at all.** If you find yourself
writing `1َ2ْ3ِ`, the trailing `ِ` belongs in the `case` column instead.

### 3d. `case` applies to nominals only

Arabic **verbs have mood (رفع/نصب/جزم), not case.** For any verb, write `ABSTAIN` in the
`case` column and put the mood in `notes` if you want to. `ABSTAIN` is a legitimate,
expected answer — it is not a failure.

### 3e. When there are two possible readings

Decide from the context (governing preposition, verb, or ʿāmil) and record the reading you
chose. If the context genuinely favours neither, that is real information:

* put `ABSTAIN` in `case`, and
* put the two candidates in `notes`.

**Do not guess to avoid writing ABSTAIN.** An honest ABSTAIN is more useful here than a
forced answer, and the 10 rows that deliberately have no gold are there precisely to give
you room to abstain.

## 4. Worked examples

```
الْقَتْلِ      root=ق.ت.ل   pattern=1َ2ْ3      case=GEN       confidence=high
بِعَذَابٍ      root=ع.ذ.ب   pattern=1َ2ا3     case=GEN       confidence=high   (بِ is a preposition, not part of the stem)
نَفْسًا       root=ن.ف.س   pattern=1َ2ْ3      case=ACC       confidence=high
تَأْكُلُوا     root=أ.ك.ل   pattern=تَ1ْ2ُ3ُ   case=ABSTAIN   confidence=medium (verb — mood is نصب here, not case)
اللَّهِ        root=أ.ل.ه   pattern=1َ2ْ3      case=GEN       confidence=low  notes=proper noun, irregular orthography
```

## 5. A caution about the text itself

The pilot text is **Quranic**, and EQTB writes it in Quranic rasm, so:

* the long alif is sometimes omitted — `أَمْوَلَهُمْ` is the standard `أَمْوَالَهُمْ`;
* alef-wasla `ٱ` and the superscript alef `ٰ` have been folded to plain `ا` / removed;
* some words carry the assimilation shadda (`رِّجَالِ`).

Read these as the standard spelling. This makes the pilot **easier than the real target**,
which is Tashkeela prose where no gold exists at all. That is acceptable here — the pilot's
only job is to prove the instructions are unambiguous — but the full sheet must sample
Tashkeela, and this limitation must be stated in the paper.

## 6. What the pilot is testing

1. **Are the instructions unambiguous?** If you find yourself unsure how to format more
   than a couple of rows, the protocol needs fixing before any real annotation.
2. **Is the wazān format usable at all?** Especially the shadda rule (3a) and the
   case-vowel exclusion (3c).
3. **A free validity check.** 40 of the 50 rows have EQTB's own root and case withheld.
   Your case labels can be compared against them directly — if your agreement is low,
   either the instructions or the gold is wrong, and either way we need to know *now*.
4. **Does the ABSTAIN rule get used sensibly?** Not never, and not everywhere.

## 8. PILOT RESULT (2026-10-09) — and the two convention rules it forced

Annotator: Rendi (single annotator). Sheet: `pilot-FILLED-by-Rendi.csv`.
Scored by `src/score_annotation.py` against the withheld EQTB gold.

| check | result |
|---|---|
| `case` agreement with EQTB gold | **39/40 = 97.5%** |
| `root` agreement, raw | 28/40 = 70.0% |
| `root` agreement, **hamza convention folded** | **39/40 = 97.5%** |
| `case` ABSTAIN used | 9 rows (particles, verbs) |
| `pattern` given | 36/50 · **7 flagged malformed** |

**The instructions worked.** 97.5% case agreement against an independent human treebank is
a strong result, and ABSTAIN was used sensibly (9 rows: particles and verbs) rather than
never or everywhere. The `notes` column carries full إعراب reasoning on all 50 rows.

### 🔴 Finding I — the digit-completeness rule is hard for HUMAN annotators too, and only in the weak/doubled classes

All **7** malformed patterns have the same cause: a radical that is **not written as a
distinct letter** gets no slot. **Every one is in the weak or doubled class; none is sound.**

| id | word | root | written | why malformed |
|---|---|---|---|---|
| A007 | بِالْحَقِّ | ح.ق.ق doubled | `1َ2ّ` | slot 3 (the doubled radical) absent |
| A030 | رَبِّى | ر.ب.ب doubled | `1َ2ّ` | same |
| A048 | الْغَيِّ | غ.و.ي defective | `1َ2ّ` | slot 3 (weak) absent |
| A014 | وَهُدًى | ه.د.ي defective | `1ُ2َى` | slot 3 absent |
| A023 | الْمُعْتَدين | ع.د.و defective | `مُ1ْتَ2ِين` | slot 3 absent |
| A037 | الْمُمْترين | م.ر.ي defective | `مُ1ْتَ2ِين` | slot 3 absent |
| A028 | ءَالَ | أ.و.ل hollow/assimilated | `1َا3` | **slot 2** absent |

This is the **M1 class bias appearing in a trained human annotator.** The instinct is to
write the pattern as it appears on the page rather than to give the invisible radical a
slot — which is precisely what CALIMA's `#` does.

**Why it matters for the project.** The "well-formed label coverage" figure (53.9%) counts a
label as well-formed only when the digit set is complete. That gate is documented as the
cause of the class bias. The pilot shows the gate also rejects a **knowledgeable human's**
natural notation. So that metric conflates two different things:

1. **analyser failure** on weak roots, and
2. **a representation convention** — must an elided radical keep its slot? — that even a
   trained annotator does not apply spontaneously.

**Decision (consistent with Finding D, "keep the 4-slot space, mask on backoff"): the
canonical target keeps ONE SLOT PER RADICAL even when the radical is elided, and the
instruction must say so explicitly with worked examples.** Otherwise the gold will keep
being rejected by the very format gate it is meant to feed, and Head 3's training data
will systematically lack the weak and doubled classes the project cares most about.

**Rule 6 (new): every radical gets its own slot, even when it is not written.**
`حَقّ` (ح.ق.ق) is `1َ2ّ3`, **not** `1َ2ّ`. `هُدًى` (ه.د.ي) is `1ُ2َ3ى`, **not** `1ُ2َى`.
`آل` (أ.و.ل) is `1َا2َ3`… i.e. write the slot for the assimilated/elided radical too.

### Rule 7 (new): one hamza convention, applied to both sides

The raw root figure (70%) was almost entirely convention: أ.ل.ه vs EQTB's اله, أجل/اجل,
أول/اول, آخرة/اخرة, سوء/سوا — 11 of the 12 mismatches.

**Use bare alef in roots (`ا`), matching the convention of PADT, QAC and EQTB** — i.e. the
corpora this project already trains on. So `الله` → `ا.ل.ه`, `أجل` → `ا.ج.ل`,
`آخرة` → `ا.خ.ر`. Writing the hamza seat is not wrong, but it must match the training
target, and the three existing corpora all use bare alef.

After both conventions, the single remaining root difference is **A009 `إِحْدَى`**, where
the annotator wrote `و.ح.د` and EQTB wrote `احد` — **the annotator is right**; the classical
root of إحدى is و ح د. This is a genuine gold quibble, not an error, and it is exactly the
kind of thing a real annotator is needed to catch.

The single remaining case difference is **A030 `رَبِّى`** (annotator GEN as a بدل/نعت of the
majrūr `الله`; EQTB NOM). Both readings are defensible — a legitimate human disagreement,
and the strongest available argument for the inter-annotator agreement step.

## 10. THE FULL SHEET — 300 tokens, Tashkeela (frozen 2026-10-09)

> **Sheet:** `data/annotation/full-annotation-sheet.csv`
> **Frozen sha256:** `9f66f3e4ec6ff175ceba113a9cfea9e9580ee4ee8f0032964b5619e3e579b581`
> **Rows:** 300 · **source:** Tashkeela (8 books, prose) · **gold withheld:** none — none exists

### Why Tashkeela, and what changes from the pilot

Tashkeela is the corpus the silver pipeline trains on, and it has **no gold annotation
anywhere**. So this sheet does not check against a reference — it **is** the reference.
The pilot's validity check (97.5% case agreement with EQTB) was the evidence that the
protocol produces usable labels; this sheet spends that credibility on the classes where
CaLIMA fails and no other source can help.

**Consequence to state plainly in the paper:** there is no withheld-gold check here. The
sheet's credibility rests on the pilot, and (if a second annotator is ever added) on
inter-annotator agreement. Until then, label these as *single-annotator* gold and say so.

### Sampling (documented, not hidden)

753 sentences from 8 books. Candidates required: ≥4 Arabic letters, **vocalized** (a wazān
cannot be judged from an unwritten word), and the target is shown in context. Stratified:
**40% deliberately drawn from words whose SURFACE contains a weak letter (و/ي) or a
shadda** — the weak and doubled classes where CALIMA's `#` collapses and where human gold
is most valuable. The stratification uses surface features only, so **no analyser is
consulted and the blindness holds.** Realised: **93 weak-letter targets, 42 shadda targets.**

### THE OPERATIVE RULES — Rule 6 and Rule 7 are now mandatory

Everything in sections 3–5 applies, **plus the two rules the pilot forced**:

> **RULE 6 — every radical gets its own slot, even when it is NOT written.**
> The pilot's 7 malformed patterns were *all* elided-radical cases, **all in the weak or
> doubled classes, none sound.** Write the slot anyway:
>
> | word | root | WRITE | not |
> |---|---|---|---|
> | حَقّ (doubled) | ح.ق.ق | `1َ2ّ3` | ~~`1َ2ّ`~~ |
> | رَبِّى (doubled) | ر.ب.ب | `1َ2ّ3` | ~~`1َ2ّ`~~ |
> | الْغَيّ (defective) | غ.و.ي | `1َ2ِّ3` | ~~`1َ2ّ`~~ |
> | هُدًى (defective) | ه.د.ي | `1ُ2َ3ى` | ~~`1ُ2َى`~~ |
> | مُعْتَدِين (defective) | ع.د.و | `مُ1ْتَ2ِ3ِين` | ~~`مُ1ْتَ2ِين`~~ |
> | آل (hollow) | ا.و.ل | `1َا2َ3` | ~~`1َا3`~~ |
>
> The last digit is often *invisible on the page*. That is precisely the point: the target
> representation is a slot per radical, and the whole reason CALIMA's `#` hurts is that it
> cannot fill these slots. A pattern missing a digit is rejected by the format gate.

> **RULE 7 — use BARE ALEF (ا) in roots, never the hamza seat.**
> `الله` → `ا.ل.ه` · `أجل` → `ا.ج.ل` · `أول` → `ا.و.ل` · `آخرة` → `ا.خ.ر` · `سوء` → `س.و.ا`
> This matches PADT, QAC and EQTB — the corpora this project already trains on. Writing
> أ/إ/آ/ء is not *wrong*, but it must match the training target, and all three use bare alef.
> (This was 11 of the 12 pilot root mismatches; with it, root agreement is 97.5%.)

### Effort

300 rows at the pilot's pace ≈ **3–5 hours**, ideally in 3–4 sittings. Quality over speed:
the pilot's 97.5% was achieved by working carefully and writing the full إعراب reasoning in
`notes`. A rushed sheet is worse than no sheet, because it will look like data.

## 11. How to return it

Fill the CSV and send it back. I will run `src/score_annotation.py`, which reports
coverage, agreement against the withheld EQTB gold, and — if a second annotator is added
later — inter-annotator agreement (Cohen's κ). Nothing in the scoring reads CALIMA.

**Effort:** ~30–45 minutes for 50 rows. If it takes much longer than that, that is itself a
finding about the protocol.

## 12. FULL-SHEET RESULT (2026-10-09)

| check | result |
|---|---|
| patterns failing the digit gate | **0** (pilot: 7) — Rule 6 worked |
| root / pattern given | 278 / 300 |
| case given | 222 · ABSTAIN 78 |
| independent human-gold check (EQTB+QAC subset, 99 rows) | **93.9% agree** |
| annotator vs CALIMA root agreement | 63.3% |
| gold artifact | `gold-tashkeela-300.jsonl` sha256 `03bea605…` |

All six disagreements with the independent gold were adjudicated **in the annotator's
favour** (ناس=ا.ن.س ×2, أحد=و.ح.د ×2, التفت=ل.ف.ت; مَلِيء is a quibble) — cases where the
treebanks' root convention departs from classical practice.

**Standing caveats:** single annotator, **no inter-annotator agreement**, and the sample is
stratified toward weak/doubled surfaces so it is not representative for prevalence claims.
Full analysis: `EVIDENCE_LOG.md` §2n.
