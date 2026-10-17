# Next-run decision criteria — fixed BEFORE the GPU run

**Purpose.** Write the pass/fail rule down while the result is unknown. This file is the
pre-registration for the next cloud run; `EVIDENCE_LOG.md §2ae` is the measurement that
motivated it. Do not edit the criteria after seeing the numbers — add a dated amendment
instead, and say what it changed.

## What changes in the next run, and what does not

**The ONE intended experimental change: the silver sample.** `EVIDENCE_LOG.md §2ae` measured that
the current "120k-token" silver training set is **the opening of a single book** (book 8 of the
train split's 82), and that at an identical token budget a spread sample covers **59× more** of
the 126 OOV gold words.

| held FIXED | changed |
|---|---|
| treatment + baseline arms (matched size) | silver sample: **strategy** (spread across books) |
| wazān→root conditioning **ON** (§2ac: OFF costs the treatment its wazān head) | silver sample: **size** (the token budget, raised) |
| 3 seeds, same three values | |
| decoder variants: raw argmax **and** trie-beamed, reported as a pair | |
| evaluation sets: the 278-row human gold + PADT dev | |
| steps, vocabulary construction rule, config otherwise | |

Rationale for keeping conditioning ON: §2ac showed that removing it coincides with a
**−4.2 pp wazān deficit vs baseline (SEPARATED)** on the human gold. Note the wording —
with three seeds this is an **association in this comparison**, not established causation,
and it does not establish that conditioning has no effect on root.

## Provenance the next run MUST record

Already recorded: `code_bundle_sha`, `config_sha256`, `seeds`, `parity.*`.

**Added for the next run:** a **data manifest with its hash**, alongside the code/config
provenance — so a reader can tell which corpus sample produced the numbers, not just which
code. At minimum, per split: file path, byte size, sha256, token count, **books touched**,
distinct surface types, and coverage of the 126 OOV words under the same rule §2ae used.
Record it in `results.json` and pin it in `tools/verified_runs.json` with the run.

## Decision criteria

| Measurement | What it tells you |
|---|---|
| Distinct training types | How quickly lexical coverage grows |
| Coverage of the 126 words | Whether more records recover the missing types |
| Frequency of each recovered word | Whether the model receives meaningful examples or merely one occurrence |
| Human-gold OOV accuracy | Whether improved coverage translates into better predictions |
| In-vocabulary accuracy | Whether more data helps generally or mainly helps OOV cases |

| Outcome | Verdict |
|---|---|
| Coverage increases, OOV accuracy improves | **Strong support** for data scale as a practical intervention. Check consistency across seeds. |
| Coverage increases, OOV accuracy does not | Lexical exposure alone is **insufficient**. Investigate example quality, contextual variation, morphology, decoding. |
| Coverage barely increases | **Revisit the sampling strategy** before paying for training. A larger nominal sample is not useful if it adds few relevant examples. |

**Statistical precaution.** Compare the new arm against the existing three-seed results using
**per-seed values and uncertainty**, not a change in means alone. `|d| > 2·max(sd)` is a
consistency check, not a significance test, and it is meaningless at n=1 (§2z).

## What would NOT count as success

- OOV accuracy rising while in-vocabulary accuracy falls — that is a trade, not a gain.
- Coverage rising in the *raw text* but not in the *built records* (§2ae's caveat: raw-text
  counts are an upper bound on what the CALIMA pipeline yields).
- A better case number that lands **at** the 0.459 CALIMA ceiling rather than above it — §2ac
  showed the head already sits there within the seed spread, so nothing smaller than a seed sd
  should be called a change.
- Quoting improved OOV figures as evidence about Arabic generally. The gold rows are
  **stratified toward weak/doubled surfaces** (caveat 3); the OOV rate describes *that sample*.

## Budget note

The sample build is **CPU-only — 0 compute units** (COLAB.md §2). Do the build, confirm the
record-level coverage, and only then spend GPU. Units expire 90 days after grant.

---

# Status — the coverage study is in (2026-10-11)

`EVIDENCE_LOG.md §2ae` (raw-text study) and `§2af` (the built records) are complete. **No GPU has
been spent.** The sampler and the manifests exist; the criteria above are unedited.

Record-level, of the 126 OOV gold words, same sampler seed for both spread builds. "Model vocab" means
`min_freq ≥ 2` **and** `max_vocab = 20,000` — i.e. what `model_arms.Vocabs` actually builds. The cap
binds for the first time at Build B, so the uncapped column is shown separately:

| build | sampler | tokens written | of 126 present | **in the model vocab** | uncapped |
|---|---|---|---|---|---|
| original (kept intact) | in-order | 120,000 | 0 | 0 | 0 |
| A | spread | 117,918 | 49 | 35 | 35 |
| B | spread | 1,871,205 | 92 | **56** | 82 |

**Which cell we are in: "coverage increases substantially".** It came mostly from the SAMPLING
STRATEGY rather than from size — strategy alone, at the same budget, accounts for 35 of the 56.
§2ae's raw-text projection survives record generation at **88% present / 54% in the vocabulary
(79% if the cap is raised)**; read every §2ae figure with that factor attached.

**A second lever has appeared — do NOT co-change it.** `max_vocab=20,000` never bound before and binds
now: it excludes **26** words that are in the records and pass `min_freq`. Raising it would take Build B
from 56 to 82 of 126. But this pre-registration holds everything fixed except the sample, so raising it
in the same run would confound the two. It is the **next** lever, not a co-change.

**The open rows are the accuracy ones** (human-gold OOV accuracy, in-vocabulary accuracy). They
need the trained arm at the larger sample with conditioning ON and everything else fixed.

## What the next GPU run must use

- **Data:** `data/out/spread-B-2m/{tashkeela-train,dev,test}.jsonl`, recorded in
  `build_manifest_tashkeela.json` (manifest sha256 `10a244f41e396226…`), with the manifest's
  per-file hashes verified against the files on disk.
- **Held fixed:** treatment + baseline matched size, conditioning **ON**, 3 seeds, both decoder
  variants as a pair, the same evaluation sets, the same steps, and **`min_freq=2` with
  `max_vocab=20,000`** — the cap binds at Build B, and raising it is the *next* lever, not a co-change.
- **Size note:** Build B's train file is **1.05 GB raw / 65.1 MB gzipped** (~9× the old sample), so it
  does not fit a 50 MB chat upload — put the `.gz` on Drive from the desktop. The in-cloud build path
  (COLAB.md §2c) needs the new flags: `--allocate spread --sampler-seed 0 --limit 2000000`.
- **Compare per seed** against the v14/v15 results, never a change in means alone — §2z showed
  the `|d| > 2·max(sd)` rule degenerates at n=1 and is only a consistency check at n=3.

## Experimental invariants — asserted, not remembered

The run's identity, all enforced by the preflight gate in the notebook (cell **4b**), which
**stops** rather than warns.

| invariant | value | why it is an invariant |
|---|---|---|
| `data.min_freq` | 2 | the vocabulary rule |
| `data.max_vocab` | **20000** | binds for the first time here; raising it is the *next* experiment, and changing it now would confound data scale with vocabulary |
| `model.use_soft_wazan_conditioning` | **ON** | §2ac: OFF costs the treatment its wazān head (−4.2 pp, separated) |
| `seeds` | 3 — 20261009/10/11 | the seed protocol is fixed |
| `model.treatment_tower_hidden` | **10018** | re-fitted for the 20,000-entry vocabulary |
| parity fingerprint | **17,041,455 / 17,041,457** (gap 0.00%) | identifies this architecture in the kernel log |
| dataset sha256 | 6 files, pinned in the cell | the gate that would have caught the one-book sample |

The gate was tested **in both directions** (`tools/test_preflight_cell.py`): it accepts the approved
inputs, **stops** on a corrupted dataset hash, and **stops** on a raised `max_vocab`.

**Determinism, measured:** re-running the spread build locally with the same seed reproduced all
three files **byte-for-byte**, which is what makes a hash gate meaningful rather than decorative.
Note `manifest_sha256` is **not** reproducible — it embeds the build's wall-clock timings — so the
gate uses the **output file hashes**, not the manifest hash.

**The gold/silver volume control is deliberately broken by this run.** `limit_train` holds PADT at
120,000 tokens while the silver side is now 1,871,205, so gold-vs-silver VOLUME rows are no longer
matched and must not be read as if they were. PADT cannot be raised to match (223,881 records is the
whole train split). The **arm** comparison inside each source is unaffected — both arms read the same
file — and that is the claim under test.

## Known knob, if a third build is ever wanted

Equal-share allocation under-fills because book sizes differ by orders of magnitude (book 90 has
46,544 windows; book 92 has 125 ≈ 2,100 tokens). Train filled 93.6% of its budget, test 57.7%.
A **proportional** allocation would recover the difference; §2af argues it would not change the
coverage conclusion, so it is not a prerequisite for the GPU run.
