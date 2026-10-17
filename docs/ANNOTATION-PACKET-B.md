# ANNOTATION PACKET — ANNOTATOR B

> **This is a controlled issue document, not a cover letter.** Everything an annotator is
> permitted to know about this task is in this file, in the guide it incorporates, and in the
> two data files listed below. If something is not written here, ask — do not infer it.

---

## 0. Version and integrity block

**Protocol version:** v1 (guide) extended by freeze v2 §2a–§2c and **Amendment 1** (the
`alternatives` column, §5.2 below). The numbered rules **Rule 6** (every radical gets its own
slot, even when unwritten) and **Rule 7** (bare alef in roots) are mandatory and are not optional
style.

> **v1.1 — what changed from v1.0, and why you are seeing it before any row is filled.**
> The `alternatives` column is new. Previously rival analyses were recorded as prose inside
> `notes`, which is human-readable but unparseable: they could not be measured for agreement,
> could not be adjudicated, and could not be scored as alternate correct answers for top-k
> evaluation. They are now a structured column with a strict grammar (§5.2). Nothing was sent to
> any annotator before this change, so no work is invalidated.

---

## 1. ORDER OF OPERATIONS — practice pack first

```
STEP 1  Read this packet and the guide.                       (~30 min)
STEP 2  Fill practice-pack.csv (40 rows).  Return it.         (~25-40 min)
STEP 3  The practice pack is format-checked, your questions    (no rows yet)
        are answered IN WRITING, and this file is amended.
        You re-check the practice pack against the amendment.
STEP 4  Only now: fill bench-annotator-B.csv (1,000 rows).    (~10-17 h)
```

**Do not open the real sheet until step 4.** The reason is mechanical, not ceremonial: the
1,000-row sheet is **frozen and hashed**, both annotators must see identical bytes, and an
instruction change made after you have filled 600 rows cannot be applied without invalidating
either the freeze or your work. The practice pack is the only place the instructions may be
tested.

---

## 2. What you are given, and what must never reach you

**You are given exactly three files:**

1. `practice-pack.csv` — 40 rows, outside the benchmark, empty answer cells;
2. `bench-annotator-B.csv` — your 1,000 rows, empty answer cells;
3. this packet (plus the two guides it names).

**You must never be sent, and must not ask for:**

- ☐ the **KEY** file (it maps each row to its stratum — knowing a row is "homographic" tells you
  the answer is arguable, which is exactly the judgement being measured);
- ☐ **annotator A's file**, or any adjudicated or merged file;
- ☐ the **test/calibration split** (§6 of the freeze doc);
- ☐ any **model prediction**, logit, confidence value or abstention decision;
- ☐ any **CALIMA / CAMeL Tools** output, or QAC / EQTB / PADT / any treebank gold;
- ☐ any **stratum label** attached to a row, or any earlier scored summary of this benchmark.

**Why this list is absolute.** If the labels that score the model are produced by someone who
has seen the model's answers, the evaluation becomes a closed loop and the result looks good and
means nothing. Blindness cannot be retrofitted: once seen, permanently contaminated. If any of
the above arrives by mistake, **do not open it** — report it, and the affected rows are re-drawn
rather than repaired.

---

## 3. THE ONE RULE, and the tool policy

**Do not consult any Arabic morphological analyser, parser, tagger, or treebank while filling
this in.** No CAMeL Tools, no CALIMA, no Farasa, no MADAMIRA, no QAC/EQTB/PADT files, no online
analyser, no morphological database.

### 3.1 Artificial-intelligence assistants are prohibited — including "just to check"

**Do not use ChatGPT, Claude, Gemini, Copilot, or any other AI assistant on any row**, not to
verify an answer, not to identify a root, not to sanity-check a pattern. This is the single most
likely way this benchmark gets contaminated by accident, because using one feels like using a
reference book. It is not: an AI assistant is an analyser with extra steps, and its agreement
would be measured instead of your own knowledge.

### 3.2 Dictionaries ARE allowed — and every lookup must be recorded

A **lexicon is allowed**: a printed or PDF dictionary (Lisān al-ʿArab, al-Muʿjam al-Wasīṭ, Lane,
or a general modern dictionary) used the way a person uses a dictionary — to look up what a word
means or what its root is.

Every lookup is recorded in `notes` on that row:

```
LOOKUP: al-Muʿjam al-Wasīṭ, ك.ت.ب           # source, then the headword you checked
```

**Not allowed, and distinct from a lexicon:** reading a **commentary or edition of the source
text itself** to find the answer for that row. That recovers someone else's analysis of exactly
this item, which is the thing being measured. A general dictionary is a tool; the source's own
annotated edition is a leaked answer key. Web-searching the sentence or the word's analysis is
prohibited for the same reason. Do not ask another person either.

### 3.3 Work from your own knowledge first

Record a lookup **only when you actually made one**. A row with no `LOOKUP` tag is understood to
be answered from your own knowledge — do not write `LOOKUP: none`.

---

## 4. The fields — exact names, allowed values, format

The sheet has exactly **nine** columns. **Fill only the six answer columns. Do not rename,
reorder, add, or delete any column.**

| # | column | fill it? | allowed values | format |
|---|---|---|---|---|
| 1 | `id` | **no** | pre-filled, opaque | leave exactly as-is |
| 2 | `sentence_with_target_in_double_brackets` | **no** | pre-filled | target is the `[[…]]` word — **do not edit** |
| 3 | `target_token` | **no** | pre-filled | the same word alone |
| 4 | `root` | **yes** | dot-separated Arabic letters, **bare alef** (Rule 7) — or `ABSTAIN` | `ق.ت.ل` · `ه.د.ي` · `ا.ل.ه` |
| 5 | `wazn_pattern` | **yes** | digits `1`–`4` standing for the radicals, **vowels kept**, **final case vowel excluded** — or `ABSTAIN` | `1َ2ْ3` · `مُ1َ2ِّ3` · `مُسْتَ1ْ2َ3` |
| 6 | `case` | **yes** | `NOM` · `ACC` · `GEN` · `ABSTAIN` | upper case exactly |
| 7 | `alternatives` | **yes — on every row** | `NONE`, or one or more candidate analyses | strict grammar, §5.2 |
| 8 | `confidence` | **yes** | `high` · `medium` · `low` | lower case exactly |
| 9 | `notes` | when §5 applies | free prose plus the fixed tags in §5 | one cell, tags separated by ` \| ` |

Mnemonic for `case`: `NOM` = مرفوع, `ACC` = منصوب, `GEN` = مجرور.

### 4.1 `root` — the STEM's radicals only

Affixes are not part of the root. Use bare alef `ا` never the hamza seat (Rule 7): `الله` →
`ا.ل.ه`, `أجل` → `ا.ج.ل`, `آخرة` → `ا.خ.ر`.

**Exactly one slot per radical, even when that radical is not written** (Rule 6): a doubled or
defective radical keeps its slot. This is the rule that all seven of the earlier pilot's malformed
patterns violated, and every one of them was in the weak or doubled class.

### 4.2 `wazn_pattern` — digits with the vowels kept

Write the pattern with a digit in place of each radical and **every vowel written explicitly**,
then delete the final case vowel.

- `كَتَبَ` → `1َ2َ3`
- `كِتَاب` → `1ِ2ا3`
- `الْقَتْل` → `1َ2ْ3`
- `مُعَلِّم` → `مُ1َ2ِّ3` — **a shadda never means "write the digit twice"**
- `مُسْتَشْفَى` → `مُسْتَ1ْ2َ3` — template letters stay as letters

If you find yourself writing a pattern ending in a case vowel (`1َ2ْ3ِ`), that vowel belongs in
the `case` column instead.

### 4.3 `case` — nominals only

Arabic **verbs have mood, not case**. For any verb write `ABSTAIN` in `case`; the mood can go in
`notes` if you wish. Particles, pronouns and other closed-class words also take `ABSTAIN`.
**`ABSTAIN` is a legitimate, expected answer, not a failure** — closed-class words genuinely have
no root and no case.

### 4.4 `confidence` — how sure you are about YOUR OWN answer to THIS row

`high` = you would defend it without hesitation · `medium` = you are fairly sure but a
knowledgeable colleague might differ · `low` = you settled on something but it could easily be
wrong.

**This column is about the annotation, not about any model.** It measures *your* certainty on
this item, and low confidence here is evidence that the *task* is ambiguous. It is not, and is
not used as, a model confidence or an abstention threshold. (When a model's selective-risk curve
is built later, that comes from *model* confidence compared against adjudicated correctness on a
held-out calibration split — a completely separate measurement, which is why nothing about it
belongs in your instructions.) An honest `low` is worth more here than a flattering `high`.

---

## 5. Fixed notation — clitics, alternatives, and "cannot determine"

`notes` is a single cell. Use these fixed tags, separating multiple tags with ` | `.

### 5.1 Clitics — name what you stripped

Root and pattern are for the **stem**. Strip the definite article `ال`, single-letter
prepositions and conjunctions (`و ف ب ك ل`), the vocative `يا`, and enclitic pronouns. Then
**name the affixes you removed** — this is required whenever the target carries one, because the
benchmark's clitic stratum is scored on whether the *stem* was identified, and a row whose stem is
right but whose clitic was silently dropped is a different result from one where the clitic was
correctly excluded:

```
CLITICS: pro=بِ; encl=ها
```

### 5.2 `alternatives` — the rival analyses, as DATA (not prose)

**Every row gets a value in this column.** `NONE` is a value: it means *you considered this row
and found no rival analysis*. A blank cell is not `NONE` — a blank means the row is not finished,
and it will be counted as missing data rather than as a considered judgement.

This column exists because prose is unmeasurable: a rival analysis written inside `notes` cannot
be checked against the other annotator, cannot be adjudicated, and cannot be counted as a second
correct answer when the model is scored at top-2 or top-3. So it is structured.

**The grammar — exactly this, nothing else:**

| you write | when |
|---|---|
| `NONE` | you considered the row and found no rival analysis |
| `case=NOM` | one rival candidate: the same word could also be nominative |
| `root=ق.و.ل \| case=GEN` | two rival candidates, separated by ` \| ` |

- **Allowed field names: `root`, `wazn`, `case`.** (`wazn` means the pattern column; `wazn_pattern`
  is accepted but `wazn` is preferred.)
- A **candidate** is one or more `field=value` pairs separated by **spaces**.
- Candidates are separated by **` | `** (space, pipe, space).
- Values follow the same rules as the columns above: bare-alef dot-separated roots, digit patterns,
  and `NOM`/`ACC`/`GEN`.
- **`ABSTAIN` is never a candidate value.** If the field itself is undecidable, `ABSTAIN` goes in
  the column and the candidate readings go here.
- Order does not matter — `root=ق.و.ل | case=GEN` and `case=GEN | root=ق.و.ل` are the same answer.

**Do not force a single fake answer for genuinely ambiguous text.** Two cases:

**(a) The context selects one reading** → fill that reading in the column, and put the rival here:

```
root=ك.ت.ب   wazn_pattern=1َ2َ3   case=GEN   alternatives=case=NOM
notes: the preposition governs GEN, so GEN is the reading I chose; NOM is the rival
```

**(b) The context genuinely does not select** → the field itself is `ABSTAIN`, the readings are
listed here, and the reason is tagged in `notes`:

```
case=ABSTAIN   alternatives=case=NOM | case=GEN
notes: ABSTAIN:both-readings-viable | no governing ʿāmil visible in the window
```

A row annotated `ABSTAIN` with both readings named is **more useful** to this project than a
guessed single answer, because it measures the task's real ambiguity instead of hiding it.

### 5.3 "Cannot determine from context" — say which kind

`ABSTAIN` alone is ambiguous between "this word class has no such attribute" and "the attribute
exists but I cannot determine it". Always tag which, in `notes`:

| tag | means |
|---|---|
| `ABSTAIN:no-analysis-applies` | the word class has no such attribute — a particle with no root, a verb with no case |
| `ABSTAIN:not-determinable` | the attribute applies, but the surface and the context window do not determine it |
| `ABSTAIN:both-readings-viable` | two analyses fit equally well (§5.2b) — **then at least two candidates must appear in `alternatives`** |

**Write the literal token `ABSTAIN` in the cell** — not `N/A`, not `?`, not blank. Abstain per
field: if `case` is undecidable but the root is clear, fill the root and abstain only on `case`.

### 5.4 Lookups

```
LOOKUP: al-Muʿjam al-Wasīṭ, ك.ت.ب
```

---

## 6. Worked examples

These are teaching examples, **not** rows from your sheet.

| target | root | wazn_pattern | case | alternatives | confidence | notes |
|---|---|---|---|---|---|---|
| `الْقَتْلِ` | `ق.ت.ل` | `1َ2ْ3` | `GEN` | `NONE` | high | `CLITICS: pro=ال` |
| `بِعَذَابٍ` | `ع.ذ.ب` | `1َ2ا3` | `GEN` | `NONE` | high | `CLITICS: pro=بِ` |
| `نَفْسًا` | `ن.ف.س` | `1َ2ْ3` | `ACC` | `NONE` | high | |
| `تَأْكُلُوا` | `ا.ك.ل` | `تَ1ْ2ُ3ُ` | `ABSTAIN` | `NONE` | medium | `ABSTAIN:no-analysis-applies \| mood is naṣb` |
| `اللَّهِ` | `ا.ل.ه` | `1َ2ْ3` | `GEN` | `NONE` | low | `CLITICS: pro=ال \| proper noun, irregular orthography` |
| `مُعَلِّم` | `ع.ل.م` | `مُ1َ2ِّ3` | `ABSTAIN` | `NONE` | high | shadda doubles one radical — digit written once |
| `حَقّ` | `ح.ق.ق` | `1َ2ّ3` | — | `NONE` | — | Rule 6: the third radical is written, doubled |
| `رَبِّى` | `ر.ب.ب` | `1َ2ِّ3` | `GEN` | `case=NOM` | medium | rival reading: naʿt on the nominative |
| `هُدًى` | `ه.د.ي` | `1ُ2َ3ى` | `ACC` | `NONE` | medium | Rule 6: `ي` is a radical even though not written |
| `يُقَتِلُونَكُمْ` | `ق.ت.ل` | `يُ1َ2ِ3ُ` | `ABSTAIN` | `NONE` | high | `CLITICS: pro=يُ; encl=ُونَ+كُمْ \| verb` |
| *(ambiguous)* | `ك.ت.ب` | `1َ2َ3` | `ABSTAIN` | `case=NOM \| case=GEN` | low | `ABSTAIN:both-readings-viable` — a filled `case` would contradict this |

The last two rows show the habits that most often go wrong: **an invisible radical still gets a
slot**, **an affix never enters the root or the pattern**, and **a rival reading is data in its own
column, not a sentence in `notes`**.

---

## 7. Your question register

Keep a plain list as you work — the row `id`, and the question — and send it with the practice
pack:

```
PRACTICE0007 — target carries both a conjunction and a pronoun; do both go in CLITICS?
PRACTICE0019 — the context rules out one reading entirely; is that alternatives=NONE?
PRACTICE0024 — I want to list a rival wazān pattern but no rival case. Is `wazn=1ُ2ُ3` on its own
               valid?
```

Answers come back **in writing, as an amendment to this packet**, and if an amendment changes a
rule, the practice pack is re-checked against it. The benchmark rows are not started until the
question register is empty. **Finding an ambiguity in the instructions is a contribution, not a
nuisance** — a question asked now is one row that does not have to be discarded later.

---

## 8. Filling rules (mechanics — these protect your own work)

1. **UTF-8, always.** If you use a spreadsheet, save as **CSV UTF-8 (comma delimited)**, not plain
   "CSV". Plain CSV on Windows corrupts the Arabic and the diacritics; a corrupted return is void
   because the benchmark cannot be scored in a different byte encoding from annotator A's.
2. **Never reorder the rows** and never re-sort them. Row order is part of the frozen artifact and
   is identical for both annotators.
3. **Never edit the three pre-filled columns.** In particular do not "clean" the `[[…]]` marker
   or re-spell the target.
4. **Fill only the six answer columns.** Do not insert helper columns, strike-throughs, colours or
   comments — nothing survives the CSV anyway, and a shifted column makes the file unreadable.
5. **One row at a time, completely.** Do not leave a field blank to come back to it — a blank
   means *not done*. `NONE` in `alternatives` is the answer for "no rival"; blank is not.
6. **Keep the pipe and equals signs plain ASCII** (`|`, `=`) in `alternatives`. Do not use `\uFF5C`
   or a comma as a separator.
7. **Work in sittings of 60–90 minutes.** The earlier benchmark in this project took 3–5 hours for
   300 rows, and the accuracy achieved was attributed to working carefully rather than long.
8. **Fix an error by editing the cell** — do not add a corrected duplicate row.

---

## 9. Returning the file

- **One channel.** Return by exactly one private channel agreed at issue time (private link or
  encrypted attachment). **Never** by public link, public repository, shared drive, or pasted into
  a chat.
- Return the completed `.csv` **under the same filename** (`bench-annotator-B.csv`), with the same
  column names, same column order, same row order, same row ids.
- Send the practice pack back **first**, separately, with your question register.
- Keep your own working copy; the return is hashed on receipt and that hash is what makes your
  labels citable.

---

## 10. What happens after your file arrives (so nothing is a surprise)

1. **Hashed immediately** on receipt, and the hash recorded in the freeze record. After that the
   file is **immutable**: a return that changes after being hashed is void, because
   "independent" has to be checkable rather than promised.
2. **Archived read-only** (a copy that cannot be edited, kept out of the repository).
3. **Format-checked first**, not scored: `tools/iaa_report.py --validate`. A malformed cell that
   reaches the agreement report makes the report wrong rather than merely noisy, so the check runs
   before any number is computed — including on the practice pack.
4. **Agreement is computed on the two raw files, before any adjudication**, per field:
   - `case` and `confidence` — raw exact agreement **and** Cohen's κ (both are low-cardinality, so
     κ is informative here; `case` especially) — but **never κ alone**: if one category dominates
     the marginals, κ collapses toward 0 even at near-total agreement (`po = 0.999, pe = 0.999` →
     `κ = 0.000`), so raw agreement and the per-stratum table are reported beside it;
   - `root` and `wazn_pattern` — **raw exact agreement plus a disagreement taxonomy**, *not* one
     pooled κ. These labels are very high-cardinality (thousands of possible roots/patterns), and a
     single κ over them is unstable and deflated to the point of being uninformative; what
     actually tells us how hard the task is, is *how* the two of you differ — a missing radical
     slot, a different radical, a hamza-convention fold, an incomplete digit set.
   - `alternatives` — whether you and annotator A found the same set of rival analyses. Rows where
     one of you wrote `NONE` and the other listed a candidate are the most informative rows in the
     whole benchmark about **ambiguity**, and they are exactly what makes a top-2/top-3 model
     score meaningful instead of arbitrary.
5. **Only then** are disputed rows adjudicated, with a **written rationale per row**, and the
   disagreement rate is **reported, not hidden** — rows where two careful annotators genuinely
   differ are the most informative rows in the benchmark, because they measure the task's real
   ambiguity.
6. Your name is recorded as annotator **B** in the freeze record; the labels are published as
   double-annotated, adjudicated gold.

**Effort:** the practice pack is 40 rows (≈25–40 min); the benchmark is 1,000 rows (≈10–17 h at
this project's measured pace), best done in 3–4 sittings per few hundred rows.

---

## 11. Sign-off

By returning the practice pack you confirm:

- ☐ I received **only** the practice pack, my annotator file, and this packet;
- ☐ I have consulted **no** morphological analyser, parser, tagger or treebank;
- ☐ I have used **no** AI assistant, and no web search for any row;
- ☐ any dictionary lookup is recorded with `LOOKUP:` on the row where I made it;
- ☐ I understand that `ABSTAIN` is a valid answer and that guessing is not;
- ☐ I will fill `alternatives` on **every** row, using `NONE` when there is no rival analysis;
- ☐ I will not share my answers, my file, or any row with the other annotator.

```
annotator name ................................................  date ............
countersigned (PI) ............................................  date ............
```
