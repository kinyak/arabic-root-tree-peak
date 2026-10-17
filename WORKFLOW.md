# WORKFLOW — how this model actually gets built

Plain-language walkthrough. No equations. Companion to `HANDOFF.md` (the problems) and `COLAB.md` (the
run costs).

---

## The idea in one sentence

**Teach the model to decide the grammar first, and let a table write the letters.**

Take the sentence *the student wrote the lesson*:

| Word | Root (جذر) | Mould (وزن) | Its job | Its ending |
|---|---|---|---|---|
| كَتَبَ | ك-ت-ب | فَعَلَ | the verb | — |
| الطَّالِبُ | ط-ل-ب | فَاعِل | the doer | ُ |
| الدَّرْسَ | د-ر-س | فَعْل | the thing done | َ |

An ordinary model does this: **predict ك, then ت, then ب, then َ…** and hope. It has no idea that
"doer" means the ending must be ُ, so it guesses from experience and gets it wrong often — which is exactly
the *I'rāb* failure you see in every general-purpose LLM.

This model does this instead:

1. Decide: *"verb, root ك-ت-ب, mould فَعَلَ; doer, root ط-ل-ب, mould فَاعِل; thing-done, root د-ر-س,
   mould فَعْل."*
2. Hand that to a **fixed lookup table** that assembles the letters.

Step 2 is arithmetic, not intelligence. It cannot be wrong. So the vowels and case endings are correct
**by construction** — the model never gets a chance to mistype them.

That is the whole contribution. Everything below serves it.

---

## Step 1 — Build the answer key

**You cannot train anything until you have truth to train against.**

Three sources, already downloaded and verified:

- **The Quran corpus (QAC)** — every one of the Quran's 128,219 word-parts, hand-labelled by scholars with
  its root and grammar. The cleanest data that exists in Arabic. 1,642 distinct roots.
- **PADT** — 7,664 modern news sentences labelled with root, grammar, and *which word depends on which*.
- **CAMeL Tools** — a program (not a dataset) that, given any Arabic word, reports its root, its mould, its
  case, and its particles. We verified it works, including for four-letter roots.

**What you do:** merge them into one file where every word carries its labels. This is mechanical
file-wrangling. No GPU.

**Why it matters:** this file is the answer key for everything afterwards — training *and* grading.

**Honest limit:** this is 78,000 Quran words plus 282,000 news words. That is small. It is enough to *grade*
a model, and enough to *teach* the extra skills, but nowhere near enough to teach Arabic from nothing.
Step 3 fixes that.

---

## Step 2 — Write the exam before the training

Pick ~500 sentences, set them aside, and never train on them. Decide now what counts as success:

- Did it get the root right?
- Did it get the mould right?
- Did it get the case ending right?
- Did it get the grammatical role right?

**Why before, not after:** if you write the exam after seeing the results, you will unconsciously write an
exam the model passes. A paper needs numbers nobody can argue with.

**One trap to avoid:** about two-thirds of Arabic case endings are genitive (جر). A model that guesses
"genitive" every single time scores 67% while understanding nothing. So grade each case separately, not as
one average.

---

## Step 3 — Give it something to read

**Tashkeela** — 75 million fully-vowelled words from 97 books, classical and modern.

This is the model's reading material, the way a person learns a language by being surrounded by it. The
answer key in Step 1 teaches specific skills; Tashkeela is what makes the model sound like Arabic instead
of like a database.

**Honest limit, and this is the biggest one:** 75 million *words* is about 98 million tokens. It sounds
enormous but it is small for training a model from scratch. It realistically supports a model of about
**5 million parameters** — a few hundred times smaller than ChatGPT. That is fine for a paper, which is
about proving an idea works, not about building a product. But be honest in the write-up about this ceiling.

---

## Step 4 — Change what the model is allowed to say

A normal model's vocabulary is chunks of letters, learned by frequency — which is why Arabic gets chopped
in the middle of roots.

Instead, give this model a vocabulary of **grammatical pieces**:

- the ~1,600 roots
- the ~70 moulds
- the prefixes and suffixes separately (و, ال, ب, and the pronoun endings)
- the small unchangeable words (هذا, الذي, في…)

**Why:** this is where "not just predicting the next word" actually happens. The model's *alphabet* is
grammar. It physically cannot produce a word with a broken root, because roots are single units to it.

---

## Step 5 — Train it to answer five questions at once

The model reads a sentence and, at every position, must answer five things at the same time:

1. **What comes next?** — the ordinary language skill.
2. **What is the root?**
3. **What is the mould?**
4. **What grammatical job does it do?**
5. **What is its case ending?**

**Why five and not one:** if you only ask question 1, the model can fake fluency — it learns which letter
usually follows which and never understands anything, which is exactly the disease you are trying to cure.
Questions 2–5 are un-fakeable. To answer "what is the root" you must actually know the root.

This is the real meaning of "not just next-word prediction": **same reading, more questions asked.** It is
still a normal neural network — that part was never the problem. The representation it predicts over is
what changed.

---

## Step 6 — Turn the plan into letters

At the end, a fixed renderer takes *(root + mould + case)* and produces the exact written form:
ك-ت-ب + فَعَلَ → **كَتَبَ**.

This is a lookup, not a guess. This is the step that makes the case endings correct 100% of the time.

**Why this is the interesting part:** the model never writes Arabic. It writes *grammar*, and Arabic falls
out of it.

---

## Step 7 — Train the honest comparison

Train a **second, identical model** — same size, same data, same settings — but the ordinary way, predicting
surface tokens. Then compare.

**Why this is essential:** if you only show that your model works, you have shown nothing. A reviewer will
say "that's just because it's a transformer," or "that's just because it read the Quran." The comparison
model is the experiment. Everything else is setup.

---

## Step 8 — Grade it and report

Run the Step 2 exam on both models. Report the differences per skill, honestly, including where your model
loses.

---

## The order to actually do the work

| Order | What | Where | Cost |
|---|---|---|---|
| 1 | Merge the three sources into one answer-key file | laptop | free |
| 2 | Write the 500-sentence exam | laptop | free |
| 3 | Split the mould into mould + case + particles | laptop | free |
| 4 | Build the grammatical vocabulary (Step 4) | laptop | free |
| 5 | Train the comparison model | Kaggle | free |
| 6 | Train *this* model | Kaggle | free |
| 7 | Build the renderer (Step 6) | laptop | free |
| 8 | Grade both, write up | laptop | free |
| 9 | *(optional)* Same idea starting from an existing model instead of scratch | Colab | ~15–23 units |

Steps 1–8 cost **nothing**. The whole paper runs on Kaggle's free hours. Only step 9 — which is a side
question, not the experiment — touches your Colab units.

---

## The three things that will actually make this hard

1. **The corpus is small.** ~98M tokens caps you at a tiny model. Accept it, and frame the paper as
   architecture research, not a product.
2. **Grammar supervision is very thin.** Only 7,664 sentences tell the model who depends on whom. That is
   the weakest part of the whole plan and no amount of compute fixes it. This is what to attack if you want
   the paper to be strong.
3. **Splitting the mould from the case is fiddly.** The tool gives them glued together
   (`ال1ا2ِ3ُ` = the + mould + ending). Separating them correctly is real work, and about a fifth of the
   tool's output is unusable junk you must filter out.

---

## What "success" looks like

Not a chatbot that speaks Arabic. A small model that, on held-out sentences, gets **roots, moulds and case
endings right more often than an identical model doing ordinary next-token prediction** — with the
structural guarantee that everything it outputs is correctly voweled and grammatically well-formed.

That is a publishable result. It is also the honest scope.
