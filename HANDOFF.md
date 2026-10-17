# HANDOFF — Native Arabic Root-Tree Foundation Model

> ⚠️ **Restarting a session mid-round-26? Read [`NEXT-SESSION.md`](NEXT-SESSION.md) FIRST.** It carries the
> current state, the exact verification commands, the landmines already paid for, and the open decisions.
> The header below is older than that state — this file is the long-form verified-numbers record.

**Written:** 2026-10-08 · **rev. 8, 2026-10-09** · **Status:** IN PROGRESS — *resource acquisition + tool
validation + the first production module*; **no training code, no merged training data, no notebook, and the
project is not yet Kaggle-ready** (gate: `EVIDENCE_LOG.md` §5).
> **New session with no memory of this project? Start at [`START-HERE.md`](START-HERE.md)** — glossary, red
> lines, environment and the next three tasks. This file is the *verified-numbers* record.
>
> One correction of record: the root-recovery figure long quoted here as 96.4%/99.8% was degenerate and
> in-sample — the held-out measurement is **92.5% coverage at 99.7% correctness**, and PADT's usable root
> supervision is **50.1%** of its `Root=` tokens (`EVIDENCE_LOG.md` §2h, `SPEC-REV6.md` §8.2).

· **Blocking gap:** **the pretraining corpus is too small**, not the GPU. Tashkeela is 75M *words*; **MEASURED
rev. 10: 66,469,247 Arabic-containing tokens** (+8,292,742 non-Arabic units = 74.8M whitespace units). The
earlier "≈98M tokens" was an over-estimate by ~1.5× (it applied 1.3 tokens/word to units that are already
tokens). 66.5M is Chinchilla-optimal for a **~3.3M-parameter** model. Scale the architecture down and
the whole paper fits the budget with room to spare (§5.4) — but nothing can conjure training data that
does not exist. Secondary blocker: the CALIMA analyser is **massively ambiguous** (median **6**
readings/word, only **11%** of words unambiguous), so a disambiguator plus a confidence gate are
**mandatory** before its output can be used as labels. The Head-3 wazān gap is **RESOLVED** (§3.4).

This file is for whoever picks this up next — a future session or your own future self. It records what
exists, how it was verified, what is broken in the source spec, and what remains unresolved.

**Source of truth for the design:** `docs/ORIGINAL-SPEC.md` (the spec as received, 16,452 B, unmodified).
**Resource catalogue:** `RESOURCES.md` (every dataset/tool/model with URL, license, size, status).

---

## 1. TL;DR

The three corpora that carry the project's ground truth are **on disk and verified by parsing**:
QAC morphology v0.4 (128,219 segments, **1,642 distinct Quranic roots**, 100% with a root tag) and
UD Arabic-PADT (7,664 sentences / 282,384 tokens, with per-token root, fully-vocalized form, case, and
dependency head). Combined totals live in §3 below.

**Do not re-download them** — SHA256 for all four primary files is recorded in §3.3.

The single most important structural discovery: **PADT is far richer than the spec assumes.** It supplies
supervision for three of the five auxiliary heads in spec §4 (root, case, syntax) from one file.

**The Head-3 (wazān) blocker is now resolved** — CAMeL Tools' CALIMA analyser emits a `pattern` feature
with radicals encoded as digits `1`/`2`/`3` (**and `4` for quadriliteral roots**), verified empirically in
§3.4. So the "~70 awzān catalogue" the spec treats as a required input **never has to be built by hand**.
What replaces that problem is a harder one: CALIMA output is deeply ambiguous and must be disambiguated.

Second structural discovery: **spec §2.1's 3D root tensor `M_root ∈ R^(28×28×28)` cannot represent
quadrilateral roots at all.** 40 of the 1,642 Quranic roots (2.4%) have four radicals — `zlzl` (زلزل),
`wsws` (وسوس), `brhn` (برهن), `snbl` (سنبل), `kwkb` (كوكب). The design is structurally incomplete
before training begins. **CAMeL's own pattern encoding independently confirms this** — it needs a 4th digit
slot for exactly these roots (§3.4).

Third discovery, and it reframes the budget: **the constraint is the corpus, not the GPU.** The spec's
"45x short" compute problem is an artefact of its choice of **1.5B parameters** — not of the architecture.
A 25M-parameter from-scratch model costs **3.1 compute units**. But Tashkeela, the only large corpus
available, is **66.5M tokens (measured rev. 10; the earlier "~98M" was ~1.5× high)** and therefore only
supports a **~3.3M-parameter** model optimally. The project is
data-limited; §5.4 has the corrected analysis.

---

## 2. What is in this folder

```
arabic-root-tree/
├── HANDOFF.md              ← this file
├── README.md               ← orientation index
├── WORKFLOW.md             ← plain-language walkthrough of the build, no equations
├── RESOURCES.md            ← resource catalogue (URLs, licenses, sizes, status)
├── COLAB.md                ← Colab/Kaggle run manifest: what to download, what to upload, unit costs
├── docs/
│   └── ORIGINAL-SPEC.md    ← the received spec, unmodified (source of truth)
├── data/
│   ├── raw/                ← corpora, as downloaded
│   └── out/                ← (empty) reserved for derived JSONL
├── .venv/                  ← Python 3.11.15 + camel-tools 1.6.0 (data in ~/.camel_tools)
└── src/
    ├── inventory.py             ← parses everything, prints §3 numbers + SHA256
    ├── inspect_qac.py           ← QAC feature vocabulary and root counts
    ├── list_quadriradical.py    ← the 4-radical roots the tensor can't encode
    ├── verify_calima_pattern.py ← proves CALIMA emits `pattern` incl. digit 4
    ├── quantify_calima.py       ← measures analyser ambiguity + pattern entanglement
    └── prune_uv_cuda_cache.py   ← reclaims the CUDA wheels a default install leaves in ~/.cache/uv
```

### 2.1 Inputs — the only sources; nothing downstream goes beyond them

> ⚠️ **This table is incomplete and was written before several downloads landed.** The authoritative,
> hash-verified inventory is **`data/raw/MANIFEST.md`** (17 files) plus `CHECKSUMS.sha256` — including the
> NYUAD/PUD treebanks, the EQTB artefacts, and the **decoy** `quranic-treebank.csv`. Verify with
> `cd data/raw && sha256sum -c CHECKSUMS.sha256`.

| File | Size | Content | License |
|---|---|---|---|
| `data/raw/qac-morphology-0.4.txt` | 6,309,503 B | Quranic Arabic Corpus morphology v0.4, TSV | GPLv3 ⚠ |
| `data/raw/qac-morphology-0.4.zip` | 1,028,754 B | canonical archive of the above | GPLv3 ⚠ |
| `data/raw/ar_padt-ud-train.conllu` | 40,698,415 B | UD Arabic-PADT train split | CC BY-NC-SA 3.0 ⚠ |
| `data/raw/ar_padt-ud-dev.conllu` | 5,397,917 B | UD Arabic-PADT dev split | CC BY-NC-SA 3.0 ⚠ |
| `data/raw/ar_padt-ud-test.conllu` | 5,163,066 B | UD Arabic-PADT test split | CC BY-NC-SA 3.0 ⚠ |
| `data/raw/jqurantree-1.0.0-src.zip` | 754,143 B | QAC Java API source | GPLv3 ⚠ |
| `data/raw/jqurantree-1.0.0-bin.zip` | 686,655 B | QAC Java API binaries | GPLv3 ⚠ |
| `data/raw/jqt/jqurantree-1.0.0.jar` | 364,596 B | extracted jar — **contains only `tanzil/quran-uthmani.xml`, no dep graphs** | GPLv3 ⚠ |

Total project footprint: **60,420,109 B (57.6 MiB)**. Local disk free: 44.1 GB.

**Not present and deliberately not downloaded** (too large for local disk): Tashkeela (75M words),
any 50 GB pretraining corpus, model weights. These must be streamed in Colab.

### 2.2 Artifacts

| Artifact | Shape | Verified how |
|---|---|---|
| `RESOURCES.md` | 11,191 B | written from live probes; every URL row carries its HTTP status |
| `COLAB.md` | ~8,900 B | Colab/Kaggle run manifest; every figure computed from `6·N·D` and live Colab/Kaggle limits |
| `docs/ORIGINAL-SPEC.md` | 16,452 B | `wc -c` → 16452, byte copy of the received document |
| `src/inventory.py` | 4,588 B | `python3 src/inventory.py` → printed §3 numbers (2026-10-08) |
| `src/inspect_qac.py` | 1,559 B | same run; root/feature counts |
| `src/list_quadriradical.py` | 803 B | printed 40 quadrilateral roots |
| `src/verify_calima_pattern.py` | 2,471 B | `.venv/bin/python src/verify_calima_pattern.py` → `pattern` key present: YES; 78 distinct patterns; `زَلْزَلَ` → `1َ2ْ3َ4َ` (2026-10-08) |
| `src/quantify_calima.py` | 3,543 B | `.venv/bin/python src/quantify_calima.py` → median 6 analyses/word; 442 distinct patterns from 1,200 tokens (2026-10-08) |
| `src/prune_uv_cuda_cache.py` | 1,308 B | `python3 src/prune_uv_cuda_cache.py` → removed 17 entries / **5.06 GB** of CUDA+triton cache; camel-tools re-verified working (2026-10-08) |

There are **no derived data artifacts** — `data/out/` is empty by design. No JSONL has been produced.
*(rev. 8: `src/` has since grown to 26 files. `reconcile.py` and `wazan_normalizer.py` are the two that are
production modules rather than probes; the rest are measurement and verification harnesses, listed in
`README.md` and `EVIDENCE_LOG.md` §2h.)*

---

## 3. Verified corpus statistics

All numbers below were produced by parsing the files with `src/inventory.py`, **not** by shell greps and
**not** from the spec's claims. Where the spec disagrees, the correction is called out.

### 3.1 UD Arabic-PADT (dependency + case + root)

| Split | Sentences | Tokens | has `Root=` | has `Case=` | has `Vform=` |
|---|---|---|---|---|---|
| train | 6,075 | 223,881 | 193,012 (86.2%) | 116,741 (52.1%) | 223,881 (100%) |
| dev | 909 | 30,239 | 25,345 (83.8%) | 15,082 (49.9%) | 30,239 (100%) |
| test | 680 | 28,264 | 24,513 (86.7%) | 14,977 (53.0%) | 28,264 (100%) |
| **total** | **7,664** | **282,384** | **242,870** | **146,800** | **282,384** |

> **Spec correction.** §3.1 claims PADT has "**over 27,000 sentences**". The actual figure is **7,664** —
> off by 3.5x. Any compute or coverage estimate built on 27k is wrong.

**Case distribution** (the Head-5 target) — note the severe imbalance:

| Case | Count | Share of case-marked tokens |
|---|---|---|
| `Case=Gen` | 98,249 | 66.9% |
| `Case=Acc` | 29,086 | 19.8% |
| `Case=Nom` | 19,465 | 13.3% |

**Top UD morphological features:** `Number=Sing` 134,589 · `Case=Gen` 98,249 · `Definite=Def` 59,523 ·
`AdpType=Prep` 42,555 · `Gender=Masc` 38,293 · `Definite=Cons` 38,093 · `Person=3` 31,534 ·
`Gender=Fem` 29,136 · `Case=Acc` 29,086 · `Voice=Act` 20,523 · `Aspect=Perf` 11,523 ·
`Mood=Ind` 8,185 · `Foreign=Yes` 5,097 · `NumForm=Digit` 5,521.

### 3.2 QAC morphology v0.4

| Metric | Value |
|---|---|
| Segments (prefix + stem + suffix) | 128,219 |
| STEM segments | 77,915 |
| PREFIX / SUFFIX segments | 28,670 / 21,634 |
| **Distinct roots** | **1,642** |
| Hapax roots (occur once) | 395 |
| Roots with ≥5 occurrences | 833 |
| 3-radical roots | 1,602 |
| **4-radical roots** | **40** |
| Other radical counts | **0** |

Case-marked stems in QAC: `NOM` 8,954 + `ACC` 10,331 + `GEN` 12,629 = **31,914 / 77,915 stems = 41.0%**.
Aspect/voice: `PERF` 9,150 · `IMPF` 8,330 · `IMPV` 1,876 · `ACT` 2,974 · `PASS` 1,691.
Mood: `SUBJ` 1,330 · `JUS` 1,418. Derived verb form is tagged literally as **`(IV)`**, 4,585 hits.
Clitics arrive as their own gold segments (`Al+`, `bi+`, `w:CONJ+`, `PRON:3MP`, …).

> **Spec correction.** §2.1 assumes ~6,500 valid roots and a 21,952-cell coordinate space.
> The Quran attests **1,642** — so **~75% of the proposed manifold is empty** from this data alone.
> Lexicons (arramooz and friends) are required to fill it, not optional extras.

### 3.3 Provenance — SHA256

```
a1d12923815341face765083805d2148ed2d9f5cc3f7d6665219d887675d8c46  qac-morphology-0.4.txt
f0b56962b340f5325bb5d293f47717522e706112c19029e82c225355c6d65e85  ar_padt-ud-train.conllu
0d95ee511cf2f26a64e229e86e5e9b37851555ebc8b53c5ebb261f2dfbc185e7  ar_padt-ud-dev.conllu
793c87bf173d491af2092ef7f87b04a2cf6c596490e7347a2065058a053a6389  ar_padt-ud-test.conllu
```

### 3.4 CAMeL Tools CALIMA — verified, and it changes the plan

Installed and run on 2026-10-08: `camel-tools` 1.6.0 (MIT) in `.venv` (Python 3.11.15), plus data packages
`morphology-db-msa-r13` (40.5 MB, **GPL v2**) and `disambig-mle-calima-msa-r13` (88.7 MB, **GPL v2**),
both under `~/.camel_tools` (39 MB on disk, +88 MB extracted).

**The `pattern` feature is real and officially documented** — `camel-tools.readthedocs.io` lists it as
"`pattern` — Templatic pattern", with `None` where no pattern applies. Verified output:

| Word | Root (as emitted) | Pattern | Note |
|---|---|---|---|
| كَتَبَ | `ك.ت.ب` | `1َ2َ3َ` | Form I |
| اسْتَغْفَرَ | `غ.ف.ر` | `ٱِسْتَ1ْ2َ3َ` | Form X — **no 4th slot** |
| عَلَّمَ | `ع.ل.م` | `1َ2َّ3َ` | Form II, shadda preserved |
| **زَلْزَلَ** | **`ز.ل.ز.ل`** | **`1َ2ْ3َ4َ`** | **quadriliteral — digit `4` present** |
| وَسْوَسَ | `#.س.#.س` | `وَ2ْوَ4َ` | ⚠️ root degraded — `#` = missing radical |
| مَدِينَة | `م.د.ن` | `1َ2ِي3َةُ` | noun |
| الطَّالِب | `ط.ل.ب` | `ال1ا2ِ3ُ` | ⚠️ **definite article baked into the pattern** |

**Three findings that matter more than the feature itself:**

1. **The pattern carries the full vocalization inline** (`1َ2َ3َ`, not a bare skeleton `123`).
   Root + pattern is therefore a *generative recipe* for the exact surface form — which is what §2.2's
   binding step actually needs. This is stronger than the "70-pattern ID classifier" the spec proposes.
2. **The analyser is severely ambiguous.** On 1,200 PADT tokens: median **6** analyses/word, mean **7.2**,
   max **99**; only **129/1,171 (11.0%)** of words have exactly one reading. Verified example — `عَلَّمَ`
   returns 22 analyses including *noun* readings of `عِلْم`/`عَلَم`. **Raw analyzer output is unusable as
   labels.** The MLE disambiguator resolves 1,200/1,200 tokens to a best-ranked analysis and is
   **not optional**.
3. **`pattern` is not a clean wazān.** Over the same 1,200 tokens:
   - **442 distinct pattern strings**, collapsing to **312** once diacritics are stripped (only 1.4x —
     the inflation is *not* mainly case endings, because…)
   - **27% of patterns carry a clitic prefix** baked in (`ال1ا2ِ3ُ`). The wazān is entangled with the
     definite article and with the case vowel simultaneously.
   - **The single most frequent "pattern" value, `NTWS` (215 tokens = 17.9%), is not a pattern at all** —
     it is a raw-surface fallback, as is the literal string `backoff` (29 tokens). ~20% of outputs are junk.
   - So Head 3 and Head 5 cannot be trained as one target: the wazān must be extracted per-stem, with the
     clitic plane (`prc0`–`prc3`, `enc0`) and the case (`cas`) split out first.

**Additional features CALIMA exposes that the spec budgets separately** (from the official feature list):

| CALIMA key | Meaning | Spec section it serves |
|---|---|---|
| `pattern` | templatic pattern | §2.2 `e_wazan` — **Head 3** |
| `root` | "Traditional Arabic root consonants" (`ك.ت.ب`, dot-separated Arabic) | §2.1, **Head 2** |
| `cas` | `n`/`a`/`g` = nominative/accusative/genitive, `u` = **undefined**, `na` = n/a | **Head 5** |
| `stt` | `d` definite · `i` indefinite · `c` **construct/iḍāfa** | not in spec — useful |
| `prc0`–`prc3`, `enc0` | article + preposition + conjunction proclitics, pronominal enclitic | §2.2 `e_clitics` — **gold** |
| `d1seg`/`d1tok`, `d2seg`/`d2tok`, `d3seg`/`d3tok` | **three levels of morphological segmentation** | §3.2 MorphBPE pre-segmentation |
| `bw`, `bwtok` | **Buckwalter form** | removes the Buckwalter↔Arabic converter problem |
| `catib6`, `ud` | CATiB6 and UD POS tags | POS alignment with PADT |
| `gloss`, `stemgloss`, `lex` | English glosses | §5.3 semantic layer |
| `vox`, `asp`, `mod`, `per`, `gen`, `num` | voice/aspect/mood/person/gender/number | already in QAC/PADT |
| `caphi` | CAPHI phonological representation | relevant to §2.1's makhraj topology claim |

**Observed `cas` distribution on the sample** (denominator 1,200): `g` 426 · `na` 404 · **`u` 191
("undefined")** · `a` 115 · `n` 64. Note that **`u` is 16% of tokens** — a third of the way between
"labelled" and "abstained", and it must be excluded from Head 5 rather than treated as a class.
**Observed `stt`:** `na` 404 · `d` 301 · `i` 269 · `c` 226 (construct state is well represented).

**Root quality degrades on weak quadriliterals** — وَسْوَسَ returned root `#.س.#.س`, with `#` marking
elided radicals. Any root head trained on this data inherits that noise.

---

## 4. Coverage map — spec §4's five heads vs. what the data can actually supervise

| Spec head | Supervision source | Status |
|---|---|---|
| **Head 1 — NTP / next-lemma** | Tashkeela (75M vocalized words, **not downloaded**) | ⚠️ available but only in Colab |
| **Head 2 — Root `(C1,C2,C3)`** | QAC (100% of stems) + PADT (**86.2%** of tokens) | ✅ covered; **13.8% must be masked** |
| **Head 3 — Wazān / pattern** | **CAMeL Tools CALIMA `pattern`** (verified §3.4) | ✅ **RESOLVED** — but needs clitic+case stripping; ~20% of raw outputs are fallbacks |
| **Head 4 — Syntactic dependency** | PADT `head`+`deprel` (100%) | ✅ covered by PADT **only** |
| **Head 5 — Terminal case marker** | QAC 41.0% of stems + PADT 52.0% of tokens | ⚠️ partial + heavily imbalanced |

**This is the key planning table.** §4 of the spec presents five heads as equally supported. They are not.
Head 3 has no annotation anywhere in the collected data, and Head 4 has a single point of failure (PADT)
because the QAC dependency-graph download no longer exists (§5.2 below).

---

## 5. Problems and limitations

### 5.1 Conflicts inside the source spec (design bugs, not opinions)

1. **TPR vs. Hadamard contradiction.** §2.2 states words are bound via "Algebraic Tensor Product
   Representations (TPR)". §7's reference code computes `e_root * e_wazan` — an elementwise **Hadamard**
   product. Hadamard is commutative and coordinate-wise; it is gated fusion, not a binding operator
   (no inverse, so no unbinding). Smolensky's TPR uses the outer product; the compressed form is Plate's
   circular convolution. **The prose and the code describe different architectures.**
2. **Target leakage in §2.2.** The word-vector formula adds `+ e_case(Case)` to the *input* embedding,
   while §4 Head 5 is defined to *predict* the final case vowel. As written the input contains the label.
   It is only coherent as teacher forcing, and the spec never says so.
3. **The 3D manifold is not implemented, and is structurally incomplete.** §2.1 specifies
   `M_root ∈ R^(28×28×28×D)`. §7 implements three independent embedding tables concatenated
   (`c1_emb ++ c2_emb ++ c3_emb`) — no tensor, no coordinates. Separately, **the 3D design cannot encode
   quadrilateral roots**; 40 exist in the Quran (verified, §3.2). This needs either a 4th radical slot or
   the factorization the code actually uses.
4. **The claim that makhraj-based topology "naturally" emerges is unbacked.** Neither the tensor nor the
   concatenation implies phonetic neighbourhood structure. It requires an explicit phonetic prior or a
   regularizer. As written it is an assumption presented as a property.
5. **Constant drift between spec and code.** 28 letters in §2.1 vs. `num_consonants=29` in §7;
   "≈70 awzān" in §2.2 vs. `num_awzan=75` in §7.
6. **The GBNF does not guarantee valid JSON.** `string ::= "\"" [^\"]* "\""` admits raw newlines/control
   characters and unescaped backslashes inside string literals. The §6 Phase-4 metric "zero JSON schema
   parse failures" is therefore not enforced by the grammar. Needs `[^"\\\x00-\x1F]`.
7. **§3.2 calls for a 50 GB corpus** for MorphBPE training. Local free disk is **44.1 GB** — the pipeline
   cannot run locally, and Colab sessions cannot hold it either without streaming.
8. **§6's 15-week roadmap covers a from-scratch 1.5B pretrain** in Phase 3. See §5.4.

### 5.2 Data limitations (all verified)

1. **Head 3 (wazān) — RESOLVED 2026-10-08 via CAMeL Tools CALIMA `pattern`** (see §3.4). No hand-built
   catalogue is needed. What replaces the original problem:
   - the feature entangles **wazān × case × clitic** (`ال1ا2ِ3ُ`), so it must be decomposed per-stem;
   - **~20% of outputs are fallbacks** (`NTWS`, `backoff`), not patterns;
   - the analyser needs the **MLE disambiguator**, which is a further 88.7 MB **GPL v2** dependency.
   None of this is a blocker; all of it is extra pipeline work the spec does not budget for.
2. **PADT root coverage is 86.2%.** ~13.8% of tokens (punctuation, foreign words, digits, some function
   words) carry no root → the root head must be masked there.
3. **PADT case coverage is only 52.0%** and QAC's is 41.0%; a merged training signal requires reconciling
   two different tokenizations and tag sets first.
4. **Severe case-class imbalance:** Genitive is 66.9% of case-marked tokens vs. nominative 13.3%.
   A model that always predicts `Gen` scores 66.9% — so the headline "case-marker accuracy" metric is a
   majority-class trap and must be reported per-class (macro-F1), not as raw accuracy.
5. **QAC attests only 1,642 roots**, 395 of them hapax and only 833 with ≥5 occurrences. The long tail is
   not trainable; the root head will effectively cover ~833 roots from this data.
6. **Two different root transliteration schemes.** QAC stores roots in **Buckwalter** (`Alh`, `qwl`, `Smw`);
   PADT stores them in a modified translit (`.h`=ح, `.s`=ص, `^s`=ش, `_h`=خ, `` ` ``=ع). Both need
   converters before the two sources can be merged. Neither converter is written yet.
7. **QAC `FORM` is Buckwalter, not Arabic script** — a Buckwalter→Unicode step is required for any surface
   output, including the §5.2 delivery schema.
8. **The QAC dependency layer *is* obtainable** — not from Leeds (§1.3, dead) but as the third-party
   **EQTB** dataset: `github.com/NoorBayan/Quranic`, MIT, `Quranic.rar` → UTF-16 CSV, verified
   **139,376 data rows × 51 columns** (docs said 139,377 — that counted the header) with `root`, `root_ar`,
   `nominal_case`, `rel_label_ar`, `depend_rel`, `head_rel`, and **no wazān column**.
   ⚠️ **Two corrections (rev. 8):** the real CSV is **`data/raw/qrtb/Quranic.csv`**, and the *decoy* is the
   top-level `quranic-treebank.csv` (5 columns of verse text) — earlier notes had this backwards. And EQTB
   is currently **read by no script**: 66 MB is on disk, unwired (`EVIDENCE_LOG.md` B18).
   **Caveat: EQTB is derived from the same QAC, so it adds the dependency layer, not more tokens.**
9. **The I3rab Treebank has no public download.** Halabi et al. 2021 (~600 MSA sentences, traditional
   i'rāb annotation) — cite `doi.org/10.1145/3472295` / `arxiv.org/abs/2007.05772`, but obtaining it likely
   requires contacting the authors. Prior art (`HatemSaadallah/irab_project`) used it, so a request path
   may be discoverable there.

### 5.3 Licensing — blocks a commercial product, not a paper

| Source | License | Effect |
|---|---|---|
| QAC morphology | GPLv3 | copyleft — derivative corpora must be GPL |
| UD Arabic-PADT | CC BY-NC-SA 3.0 | **NonCommercial** — forbids commercial use |
| Tashkeela | GPL-2.0 | copyleft |
| CAMeL Tools (code) | MIT | fine |
| CAMeL Tools **data** (morphology DB, MLE disambiguator) | **GPL v2** | ⚠️ copyleft — newly relevant, only discovered on install (§3.4) |
| CATT / Shakkelha / Shakkala | MIT | fine |
| Qwen3 weights | Apache-2.0 | fine |
| Gemma 3 weights | Gemma terms | more restrictive than Apache-2.0 |
| arramooz | **unverified** | check before relying on it |

The entire ground-truth stack is copyleft + non-commercial. **A research paper is unaffected; a shipped
commercial app cannot be built cleanly on this corpus base.** This decision was taken consciously on
2026-10-08 (research-grade chosen, app deferred), but it constrains every future fork.

### 5.4 Compute and corpus budget — corrected (rev. 3)

**The GPU is not the binding constraint. The corpus is.**

200 Colab compute units = **$20** = **13.3 A100-h / 40 V100-h / 102 T4-h**.

The "45x short" figure quoted in rev. 1–2 was accurate but **misleading**: it is a property of the spec's
choice of **1.5B parameters**, not of its architecture. Training cost scales as `6 × params × tokens`, so
shrinking the model shrinks the bill quadratically:

| Model | Tokens | A100-h | **Units** | Fits 200? |
|---|---|---|---|---|
| 5M | 0.10B | 0.02 | **0.3** | ✅ |
| 25M | 0.50B | 0.2 | **3** | ✅ |
| 50M | 1.00B | 0.7 | **10** | ✅ |
| 125M | 2.50B | 4.2 | **63** | ✅ |
| 350M | 7.00B | 32.7 | 491 | ❌ |
| **1.5B (the spec's pick)** | 30B | 601 | **9,014** | ❌ |

**But the corpus caps the model far below the GPU's ceiling.** Chinchilla-optimal is ~20 tokens/parameter.
The largest available corpus is **Tashkeela** — the docs long called it "75M *words* ≈ 98M tokens"; **measured
rev. 10, it is 66,469,247 Arabic tokens** (74.8M whitespace units, 8.3M of them non-Arabic). The 1.3
tokens/word multiplier was applied to units that were already tokens, so the estimate was ~1.5× high. At
~20 tokens/parameter the corpus is optimal for a **~3.3M-parameter** model, not ~5M.

| Constraint | Ceiling |
|---|---|
| Compute budget (200 units) | ~150–200M params |
| **Available corpus (Tashkeela)** | **~5M params optimal; ~25–50M workable with repetition** |
| Gold supervision for the 5 heads | QAC 78k stems · EQTB 139,376 data rows · **35,066 sentences** of dependency graphs (PADT 7,664 + NYUAD 19,738 + PUD 1,000 + EQTB 6,236 verses *[overlaps QAC]*), but **root-labelled tokens are only ~1.3M and NYUAD/PUD contribute 0 roots** — and only **50.1% of PADT's `Root=` values are usable roots** (`SPEC-REV6.md` §8.2 C3), so plan Head 2 at ~1.1M tokens |

**Correction to rev. 1–2.** Those revisions recommended fine-tuning Qwen3-1.7B. That was optimised for
*shipping an app*. For a **paper**, a from-scratch model of matched size is the correct instrument: the
claim is "this architecture beats a same-size transformer on the same data", and initialising from Qwen3
would confound architectural novelty with Qwen3's pretraining. **Qwen3 is demoted to an ablation arm.**

**Unit cost is nearly GPU-independent for small models** — a T4 is ~8x slower than an A100 but its
units/hour rate is ~8x cheaper, so they cancel (25M × 500M tokens = 3.1 units on T4 vs 2.5 on A100).
There is nothing to buy by spending A100 units on small models; use them only for the 1.7B ablation.

**Recommended split — see `COLAB.md` for the runnable manifest:**

| Work | Where | Units |
|---|---|---|
| Control + treatment (25M, 3 seeds each) | Kaggle (free) | 0 |
| Scaling check (50M, both arms) | Kaggle (free) | 0 |
| Ablation: Qwen3-1.7B QLoRA, **100M tokens** | Colab A100 | ~15–23 |
| Data pipeline + eval harness | **laptop** (CPU) — *not* a Colab CPU runtime, which burns <1 u/h | ~0 |
| **Total Colab spend** | | **~15–23 of 200** |

Do **not** run the ablation at 500M tokens — that alone is 76–114 units and would consume most of the balance.

Kaggle supplies **30 GPU h/week free** (floating; often more), and Colab Pro owners can link accounts for
**+15 h/week that do not consume compute units**.

**The unresolved problem is supervision, not compute:** 7,664 sentences with dependency graphs is thin
for the syntactic planner in any configuration, with or without a pretrained trunk.

### 5.5 Environment limitations

Local machine is an i5-1235U with **15 GB RAM, no CUDA device** (`/dev/dri` = Intel UHD only), 44.1 GB free
of 216 GB *before* this project (now **~38 GB** after the CAMeL install). It is suitable for **CPU-only
corpus work** (parsing, conversion, lexicon building, eval-harness authoring) and **cannot** train or
fine-tune anything meaningfully.

**Disk trap when installing CAMeL Tools:** a default `uv pip install camel-tools` drags in `torch`, which
pulls the **NVIDIA CUDA wheel set — 3.2 GB — plus `triton` at 894 MB**, for a venv of **5.6 GB on a machine
with no GPU**. Install CPU-only instead:

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python --torch-backend=cpu camel-tools
```

The CALIMA morphology DB and MLE disambiguator then live under `~/.camel_tools` (124 MB total).

**The same wheels also land in the shared uv cache** (`~/.cache/uv`), which reached **9.5 GB** across the
two installs; `uv cache prune` alone only freed 761 MB. `src/prune_uv_cuda_cache.py` removes just the
CUDA/triton entries and reclaimed **5.06 GB** — verified safe, because uv hardlinks cache entries into the
venv, so deleting a cache entry does not break an installed environment (re-ran the CALIMA test afterwards;
identical output).

**Measured outcome of the cleanup:** venv **5.6 GB → 1.2 GB**; uv cache **9.5 GB → 3.6 GB**;
free disk **43 GB**.

---

## 6. Prior art — read before writing pipeline code

`github.com/HatemSaadallah/irab_project` — shared char-level encoder with three heads: diacritics
(15-way per character), i'rāb role (11-way per word), orthographic error (BIO). Weighted multi-task loss
with per-sample masking, trained on Tashkeela + QAC + I3rab Treebank + synthetic error injection.

**This is spec §4 already built**, at a scale that runs on one GPU. The genuinely novel parts of the spec
are the 3D root manifold and the TPR binding — which are (a) unimplemented in the spec's own reference
code and (b) each provably incomplete or self-contradictory (§5.1 items 1–4). Establishing novelty against
this repo is the first task of any paper.

Also relevant: `abjadai/catt` (CATT transformer diacritizer), `AliOsm/shakkelha`, `Barqawiz/Shakkala`,
and **CAMeL Tools v1.6.0** (MIT, Python ≥3.11) whose Calima-MSA analyzer returns root, pattern, POS and
**case** directly — i.e. it may supply Head 3's wazān without any new annotation.

**Design consequence (rev. 3).** The novelty claim must be established against a **matched-size baseline**,
not against a large pretrained model: a from-scratch transformer of the same parameter count and the same
pretraining data, predicting surface subword tokens instead of roots/patterns. Everything else — size,
data, tokenizer budget, steps, seeds — held constant. That control arm is the experiment; Qwen3-1.7B is a
separate ablation answering a different question ("does a pretrained trunk help?"), not the baseline.

Note also that both prior-art systems above are *encoder* or character-level *diacritizer* models. Neither
attempts order-free root-graph planning, so that — not the auxiliary heads — is where the contribution
would have to live (§5.1 items 1–4 show the spec's own formulation of it is currently broken).

---

## 7. How to resume

```bash
cd ~/arabic-root-tree

# 1. Re-derive every number in §3 (takes ~10 s, CPU only)
python3 src/inventory.py

# 2. Inspect QAC feature vocabulary / root stats
python3 src/inspect_qac.py

# 3. List the quadrilateral roots that §2.1's tensor cannot encode
python3 src/list_quadriradical.py

# 4. Verify the corpora are unmodified
sha256sum data/raw/qac-morphology-0.4.txt data/raw/ar_padt-ud-*.conllu   # compare with §3.3
```

Suggested order of work:

1. ~~**Resolve Head 3 (wazān)**~~ — **DONE 2026-10-08.** CAMeL Tools CALIMA emits `pattern` with digit
   radicals including `4` for quadrilaterals (§3.4). `camel-tools` 1.6.0 is installed in `.venv` with the
   MSA morphology DB and MLE disambiguator under `~/.camel_tools`.
2. **Decompose `pattern`** — strip clitic prefixes (`prc0`–`prc3`, `enc0`) and the terminal case vowel (`cas`)
   to get a clean per-stem wazān; decide what to do with the ~20% fallback values. *(Partial: the corrected
   order + geminate expansion + radical-alif-safe case strip are in `src/wazan_normalizer.py` and lift
   well-formed label coverage 31.7% → 53.6%. **The proclitic strip is still not implemented** — the label
   still carries `ال`; it needs `prc0`–`prc3` alignment, not positional slicing.)*
3. ~~**Write the Buckwalter↔Arabic and PADT-translit↔Arabic converters**~~ — **DONE 2026-10-09 (rev. 8).**
   `src/derive_padt_translit.py` derives the PADT mapping by aligning 2,046 token pairs (every unambiguous
   unit agrees at 100%); both tables ship in `src/reconcile.py`. Also learned: spaces in PADT `Root=` are
   radical separators, `.h .s .d ^s _h ^g` are digraphs, and `O`/`V` occur only inside the `OOV` sentinel.
   Watch the standing trap: `Smw` = **صمو** (capital `S` is ص); سمو is lowercase `smw`.
4. ~~**Reconcile weak roots**~~ — **DONE 2026-10-09 (rev. 8).** `src/reconcile.py`: dictionary from PADT-train
   gold, held-out probe on PADT dev+test → **92.5% coverage, 99.7% of recovered correct**. Note the corrected
   provenance (`EVIDENCE_LOG.md` §2h): the old 96.4%/99.8% came from a script that read `analysis["lemma"]`
   (CALIMA exposes `lex`), so it keyed every row on `''` and "resolved" 100% of tokens from one entry.
5. Build the merged JSONL into `data/out/` (still CPU-only, zero compute units). **This is now the critical
   path — it is the artifact `COLAB.md` §2 expects you to upload, and `data/out/` is still empty.**
6. Write the eval harness **before** training anything, with **macro-F1** for case, not accuracy (§5.2 item 4),
   plus the blind non-CALIMA protocol (`SPEC-REV6.md` §5.3). Blindness cannot be retrofitted.
7. Measure **Tashkeela vocabulary coverage** against the gold dictionary — the one number that sets the usable
   silver-corpus size, and therefore the model size the paper may claim. Everything measured so far is PADT→PADT.
8. Train the two **from-scratch** arms on **Kaggle** (free) — 25M params first, baseline given the **same
   auxiliary heads** (§5.2 supervisory parity). `COLAB.md` §1 has the copy-paste bootstrap cell, §2 the upload
   set (only your derived JSONL), §4–5 the unit costs.
9. Run the Qwen3-1.7B ablation only after the from-scratch comparison is clean — it is not the baseline.

**Do not start any training job yet** — the user's standing instruction (2026-10-08) was
*collect resources only*. Confirm before spending compute units.

---

## 8. Open items / what a next session should chase

1. ~~**Head 3 wazān source**~~ — **RESOLVED 2026-10-08** via CAMeL Tools CALIMA (§3.4).
2. **Decompose `pattern` into a clean wazān** — separate clitic (`prc*`/`enc0`) and case (`cas`) from the
   stem pattern; define the canonical wazān inventory. *Still the highest-value open task, and now the only
   part of §2 done: the case strip, geminate expansion and call order are corrected
   (`src/wazan_normalizer.py`), the **proclitic strip is not**.*
3. **`Nourjennane/irab_project` vs `HatemSaadallah/irab_project`** — two repos, near-identical name and
   description. Establish whether one is a fork/continuation before citing either. *(still open)*
4. **I3rab Treebank access path** — likely author request; check the prior-art repo for how it was obtained.
5. ~~**QAC dependency graphs**~~ — **RESOLVED 2026-10-08** via the third-party **EQTB** dataset
   (`github.com/NoorBayan/Quranic`, MIT, 139,376 data rows × 51 cols with root/case/dependency). Do not
   double-count it against QAC morphology — it is derived from the same Qur'anic tokens.
6. **arramooz license** — unverified; blocks a decision on the §5.3 SQLite verifier lexicon.
7. ~~**CAMeL `camel_data` download footprint**~~ — **measured 2026-10-08:** morphology DB 40.5 MB,
   MLE disambiguator 88.7 MB (both **GPL v2**), 39 MB + ~88 MB on disk. Small enough to install locally.
8. **Not yet collected:** Tashkeela, arramooz sqlite build, the Arabic Lexicons corpus, Qwen3 weights,
   any GGUF. All catalogued in `RESOURCES.md` §2–§5 with URLs and sizes.

*rev. 8 additions to this list:* measure **Tashkeela vocabulary coverage** (the decisive scaling number);
build the **merged JSONL** (`data/out/` is still empty — the critical path now); write the **blind
non-CALIMA eval protocol before any annotation**; implement the baseline's **auxiliary heads** (supervisory
parity). The Kaggle gate that follows from these is itemised in `EVIDENCE_LOG.md` §5.
**And the repo is still not under version control** — every number in this file is a claim about a file that
can change with no diff to prove it.

---

## 9. Sibling work in `~/`

| Folder | Relevance |
|---|---|
| `~/arabic-root-tree/` | this project |
| `~/pdf2word/` | unrelated (Arabic PDF→Word pipeline) |
| `~/SillyTavern/` | user's MSA practice setup — shares the *full-tashkeel Arabic output* requirement that this project's §5.2 schema would need to honour |

Note the standing user requirement that applies to any Arabic output this project produces: **every Arabic
word fully tashkeel'd with correct naḥw/ṣarf** — the §5.2 delivery schema is exactly a machine-readable
form of that requirement.
