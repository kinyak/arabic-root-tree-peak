# Arabic Root-Tree Model — Resource Manifest

**Collected:** 2026-10-08 · **Host:** HP ProBook 440 (i5-1235U, 15 GB RAM, no CUDA, 44 GB free on `/`)
**Compute:** 200 Google Colab compute units = $20 = **13.3 A100-h / 40 V100-h / 102 T4-h**

> Everything below was probed live. Status tags: **[HAVE]** on disk, **[OK]** verified reachable,
> **[GONE]** URL dead, **[FIXME]** unresolved, **[LICENSE-RISK]** flagged.
>
> **Companion document: [HANDOFF.md](HANDOFF.md)** — the verified corpus statistics, the design bugs in
> the spec, the coverage map (which of the spec's five heads each corpus can actually supervise), and the
> blocking gaps. Read that first; this file is the supply list.

---

## 1. Corpora — the ground truth

### 1.1 Quranic Arabic Corpus (QAC) — morphology v0.4 · [HAVE] ✅
- **File:** `data/raw/qac-morphology-0.4.txt` (6,309,503 B, 128,276 lines, CRLF, ASCII/Buckwalter)
- **Also:** `data/raw/qac-morphology-0.4.zip` (canonical, byte-identical to the GitHub mirror copy)
- **How to get it (the URL changed — the old direct link now serves HTML):**
  ```bash
  # canonical: POST form, downloadID=3
  curl -sSL -X POST -d "downloadID=3&validEmail=null" \
       -o qac-morphology-0.4.zip https://corpus.quran.com/download/default.jsp
  # mirror (verified identical): q-ran/quran repo
  curl -sSL -o qac-morphology-0.4.txt \
    https://raw.githubusercontent.com/q-ran/quran/master/sources/1.0/quranic-corpus-morphology-0.4.txt
  ```
- **Format:** TSV `LOCATION \t FORM \t TAG \t FEATURES` — `(surah:ayah:word:segment)`
- **Verified contents** (built by `src/inspect_qac.py`):
  - 128,219 segments = 28,670 PREFIX + **77,915 STEM** + 21,634 SUFFIX
  - **1,642 distinct roots** (395 hapax, 833 with ≥5 occurrences) — in Buckwalter, e.g. `Alh`, `qwl`, `kwn`, `rbb`, `Amn`
  - Case: `NOM` 8,954 · `ACC` 10,331 · `GEN` 12,629
  - Aspect/voice: `PERF` 9,150 · `IMPF` 8,330 · `IMPV` 1,876 · `ACT` 2,974 · `PASS` 1,691
  - Mood: `SUBJ` 1,330 · `JUS` 1,418
  - Participles: `PCPL` 3,525 · Verb form tagged literally as **`(IV)`**, 4,585 hits
  - POS: N / V / P / PN / REL / PRON / NEG / ACC / ADJ / T / DEM / COND / CONJ / SUB / LOC … (35 tags)
- **⚠ What it does NOT contain:** the dependency graph. Only morphology.
- **License:** GPLv3 (`corpus.quran.com/license.jsp`) — **[LICENSE-RISK]** for a closed app.

### 1.2 Prague Arabic Dependency Treebank (UD conversion) · [HAVE] ✅
- **Files:** `data/raw/ar_padt-ud-{train,dev,test}.conllu` = 40.7 MB + 5.4 MB + 5.2 MB
- **Get:** `https://raw.githubusercontent.com/UniversalDependencies/UD_Arabic-PADT/master/ar_padt-ud-train.conllu` (+ `-dev`, `-test`)
- **Verified counts:** 284,813 / 38,759 / 35,517 lines → **7,664 sentences, 282,384 tokens** (train+dev+test)
  - *The handoff doc says "over 27,000 sentences" — that figure is wrong by 3.5x.*
- **Per-token columns that matter:**

  | column | example | gives you |
  |---|---|---|
  | 2 form | `ترفض` | surface (unvocalized) |
  | 3 lemma | `رَفَض` | lemma |
  | 4 UPOS | `VERB` | coarse POS |
  | 5 XPOS | `VIIA-3FS--` | Arabic-specific tag |
  | 6 feats | `Aspect=Imp\|Gender=Fem\|Number=Sing\|Person=3\|Voice=Act` | **gold case/gender/number/aspect/mood** |
  | 7 head, 8 deprel | `2`, `nsubj` | **the dependency graph** |
  | 10 misc | `Vform=تَرفُضُ\|Gloss=reject\|Root=r f .d` | **fully-vocalized form + ROOT + gloss** |

- **Key implication:** PADT alone gives root + vocalized form + case + head + relation per token.
  QAC gives root + pattern-POS + clitics + voice/aspect/mood. **The two are complementary and
  together they supervise all five heads in §4 of the handoff.** No other corpus is required for v1.
- **⚠ Root is in a translit scheme** (`.h`=ح, `.s`=ص, `^s`=ش, `_h`=خ, `` ` ``=ع) — needs a converter.
- **⚠ No wazān column.** Derive it: abstract root radicals → ف/ع/ل against the vocalized form.
  Deterministic, no external catalog needed (this is why you don't need the "70 awzān" table as an input).
- **License:** CC BY-NC-SA 3.0 — **[LICENSE-RISK]** (NonCommercial).

### 1.3 QAC syntactic treebank (dependency graphs) · [GONE] / [FIXME]
- `quranic-corpus-dependency-0.4.zip`, `dependency-graphs.txt.zip`, `/download/dependency/` → **all return
  the 8,826-byte HTML download page.** The QAC POST form only exposes: `1`=jqurantree-src, `2`=jqurantree-bin,
  `3`=morphology; IDs 4–16 are empty.
- `jqurantree-1.0.0.jar` inspected: contains only `tanzil/quran-uthmani.xml` + classes. **No dep-graph payload.**
- **Conclusion (rev. 3, superseded):** the vendor treebank is unreachable, **but the dependency layer is
  obtainable elsewhere — see §1.3b.** The scraping route is no longer needed.

### 1.3b Extended Quranic Treebank (EQTB) — dependency + root + case for the whole Qur'an · [HAVE] ✅
**This is the resource that closes the dependency-graph gap.** Not obtainable from Leeds (see §1.3 above) —
it is a **third-party 2025 dataset** distributed separately:
- **Repo:** `github.com/NoorBayan/Quranic` — **MIT**, 185★, last pushed 2026-09-17. Paper: *Data in Brief*
  (Extended Quranic Treebank, EQTB), `science.yemen` repo + Mendeley `rk96pn66m4`.
- **Download (note the container, this tripped up a first attempt):** the annotated data is **not** in
  `corpus/Quran.csv` — that file is only verse text (`aid, chapter, verse, ayah, jmlh`, 13,017 rows). The
  treebank is inside **`corpus/Quranic.rar`** (3.93 MB) → **`Quranic.csv`, 57.5 MB, UTF-16 encoded**.
  `7z x Quranic.rar` works; `unrar` is also present on this machine.
- **Verified shape (2026-10-09):** **139,376 data rows × 51 columns** — an earlier note said 139,377, which
  counted the header row. On disk as `data/raw/qrtb/Quranic.csv` (sha256 `38c82933b41b…`); the RAR is
  `data/raw/Quranic.rar`. ⚠️ **Read by no script yet** — see `EVIDENCE_LOG.md` B18 and `data/raw/MANIFEST.md`.
- **Columns that matter:**
  `root`, `root_ar`, `lemma`, `lemma_ar`, `pos`, **`pos_ar`** (Arabic POS names: فعل، اسم، حرف جر…),
  `segment` (PREFIX/STEM/SUFFIX), `prefix`, `suffix`, `verb_form`, `verb_aspect`, `verb_mood`,
  `verb_voice`, **`nominal_case`** (the i'rāb case), `nominal_state`,
  `rel_label`, **`rel_label_ar`** (traditional Arabic relation names, e.g. متعلق),
  `depend_rel`, `head_rel`, `constituent_label`.
- **⚠️ No wazān column** — Head 3 remains CALIMA's job (§4).
- **⚠️ Do not double-count.** EQTB is *derived from the same Leeds QAC* as §1.1. It adds the **dependency
  layer**, not more tokens — counting it as separate supervision inflates the numbers.
- **⚠️ Quality:** some `rel_label_ar` values are untranslated English leaked through (e.g. `root` in the
  Arabic column). Spot-check before trusting field-by-field. 51 columns of UTF-16 needs real parsing work.

### 1.4 Additional UD treebanks now on disk · [HAVE] ✅
Both downloaded 2026-10-08. **Verified: neither carries `Root=` or `Vform=`** — they add *syntax*, not roots.

| Treebank | Sentences | Tokens | `Root=` | `Vform=` | `Case=` |
|---|---|---|---|---|---|
| UD_Arabic-NYUAD | 19,738 | 738,889 | **0%** | **0%** | 45.3% |
| UD_Arabic-PUD | 1,000 | 20,747 | **0%** | **0%** | 45.9% |
| *(PADT, for comparison)* | 7,664 | 282,384 | 86.0% | 100% | 52.0% |

- Sources: `raw.githubusercontent.com/UniversalDependencies/UD_Arabic-NYUAD/master/ar_nyuad-ud-{train,dev,test}.conllu`
  and `.../UD_Arabic-PUD/master/ar_pud-ud-test.conllu`
- **License:** CC BY-NC-SA 3.0 / NOASSERTION — same NonCommercial family as PADT. **[LICENSE-RISK]**
- **Consequence:** merging all three drops combined root coverage to **23.3%**. Root supervision must be
  masked per-source, never pooled.

---

## 2. Diacritization / i'rāb corpora

| Resource | Status | Notes |
|---|---|---|
| **Tashkeela** | [OK] | 75M fully-vocalized words, 97 classical+modern books. `https://huggingface.co/datasets/community-datasets/tashkeela` · **license gpl-2.0** · **[LICENSE-RISK]**. Large — do NOT download locally (44 GB free). Stream it in Colab. |
| **EmanKhater/Tashkeela** | [OK] | 3M+ sentences, 90/5/5 split — the pre-split version, easier to train on. `huggingface.co/datasets/EmanKhater/Tashkeela` |
| **I3rab Treebank** | [FIXME] | Halabi et al. 2021, ~600 MSA sentences with traditional-i'rāb annotation. Paper: `doi.org/10.1145/3472295`, `arxiv.org/abs/2007.05772`. **No public download link found** — likely request-from-authors. Check `Nourjennane/irab_project` for how they obtained it. |
| **QAC (as diacritics+i'rāb)** | [HAVE] | 78K words with diacritics *and* i'rāb — the highest-quality slice you own. |

---

## 3. Lexicons (root → meaning, for the §5.3 SQLite verifier)

| Resource | Status | Notes |
|---|---|---|
| **arramooz** | [OK] | Arabic morphological dictionary, from Ayaspell data. `github.com/linuxscout/arramooz` + sqlite build `arramooz-pysqlite`. Best fit for the on-device trie. |
| **Arabic Lexicons (11 classical dicts)** | [OK] | Hans Wehr, Lane, Lisān al-ʿArab, etc. — offline, GPLv3. `wizsk.github.io/apps/arabic_lexicons.html` — **[LICENSE-RISK]** GPLv3 |
| **ARBML/masader** | [OK] | Catalogue of **500+ Arabic NLP datasets**, 25+ attributes. Use this as the index when you need more. `github.com/ARBML/masader` |
| **qutrub** | [OK] | Arabic verb conjugation engine — useful for generating exercise items. `github.com/linuxscout/qutrub` |
| **Tanzil Uthmani text** | [HAVE] | `data/raw/jqt/.../tanzil/quran-uthmani.xml` (extracted from jqurantree jar) |
| **q-ran/quran XML** | [OK] | `quran-uthmani.xml` (1.5 MB), `quran-simple-min.xml` (1.3 MB), `en.arberry.xml`, `nl.leemhuis.xml` |

---

## 4. Tools

| Tool | Status | Notes |
|---|---|---|
| **CAMeL Tools** `camel-tools` | **[HAVE — VERIFIED]** | **v1.6.0, MIT, Python ≥3.11.** Installed 2026-10-08 in `.venv` (Python 3.11.15). Emits `pattern` (templatic pattern, digit radicals `1`/`2`/`3`/**`4`**), `root`, `cas`, `stt`, `prc0`–`prc3`, `enc0`, `d1/d2/d3seg`+`tok` segmentation, `bw`/`bwtok` Buckwalter, `catib6`, `ud`, `gloss`, `caphi`. Verified test: `src/verify_calima_pattern.py`. **Requires** the MLE disambiguator — raw output is median 6 analyses/word. |
| ↳ `morphology-db-msa-r13` | **[HAVE]** | 40.5 MB, **GPL v2**. CALIMA MSA morphology database. `camel_data -i morphology-db-msa-r13`. 39 MB on disk under `~/.camel_tools`. |
| ↳ `disambig-mle-calima-msa-r13` | **[HAVE]** | 88.7 MB, **GPL v2**. MLE disambiguator — **mandatory** to collapse the analyser's ambiguity. `camel_data -i disambig-mle-calima-msa-r13`. |
| ↳ `morphology-db-msa-s31` | [OK] | 44.8 MB, **LDC license** ⚠️ restricted — prefer r13 unless you have LDC membership. |
| **CATT** | [OK] | `github.com/abjadai/catt` — Character-based Arabic Tashkeel Transformer. Current SOTA-ish diacritizer, encoder-only (fast). |
| **Shakkelha** | [OK] | `github.com/AliOsm/shakkelha` — MIT, EMNLP-IJCNLP 2019, ships trained models. |
| **Shakkala** | [OK] | `github.com/Barqawiz/Shakkala` — MIT, RNN vocalization, claimed 95% accuracy. |
| **Mishkal** | [OK] | `tahadz.com/.../mishkal` — rule-based diacritizer. Author states results are approximate. Useful as a *baseline* / fallback, not a target. |
| **irab_project (HatemSaadallah)** | [OK] | `github.com/HatemSaadallah/irab_project` — **DIRECT PRIOR ART.** Shared char-level encoder, 3 heads: diacritics (15-way) + i'rāb role (11-way) + orthographic error (BIO). Multi-task loss with per-sample masking. Trained on Tashkeela + QAC + I3rab Treebank. This is §4 of your doc, already implemented. |
| **Nourjennane/irab_project** | [OK] | Same name, different repo — investigate; may be the same work continued. |
| **MorphBPE** | [OK] | `arxiv.org/abs/2502.00894` — real, Feb 2025. Constrains BPE merges to respect morpheme boundaries; inference unchanged. Cite it correctly: it's a *merge constraint*, not a tokenizer architecture. |

---

## 5. Models (base + mobile targets)

| Model | Status | Notes |
|---|---|---|
| **Qwen3-1.7B** | [OK] | Apache-2.0 · `huggingface.co/Qwen/Qwen3-1.7B`. **Recommended base** — permissive license, strong small-model quality, first-class mobile story. |
| **Qwen3-0.6B** | [OK] | Apache-2.0, smaller/faster — the safe mobile fallback. |
| **Qwen3-1.7B-GGUF** | [OK] | Official quant, Q8_0. |
| **unsloth/Qwen3-1.7B-GGUF** | [OK] | **26 quantization variants** — use this for `Q4_K_M` export. |
| **gemma-3-1b-it-qat-q4_0-gguf** | [OK] | Google, QAT 4-bit, ~1 GB. Excellent size/perf but Gemma terms are more restrictive than Apache-2.0. |
| **CAMeL-Lab/camelbert-msa** | [OK] | HTTP 401 = gated. Arabic-native BERT — needs HF login/accept. Worth having for embeddings/aux heads. |

---

## 6. Disk & compute reality check

- **Local disk:** 44 GB free. QAC (6 MB) + PADT (51 MB) + tools ≈ **<1 GB**. Fine.
  Tashkeela and 50 GB corpora **do not fit** — stream in Colab, never store locally.
- **Local GPU:** none (`/dev/dri` = Intel UHD only). i5-1235U, 15 GB RAM.
  → Local machine is for **CPU work only**: corpus parsing, Buckwalter↔Arabic conversion,
  wazān derivation, lexicon building, eval-harness authoring. All zero-GPU.
- **Colab budget (200 units = $20):**
  - QLoRA Qwen3-1.7B @ 100M tokens ≈ **23 units** ✅
  - QLoRA @ 500M tokens ≈ **114 units** ✅
  - From-scratch 1.5B pretrain ≈ **9,014 units** ❌ (45x over budget)
- **Free extra compute:** Kaggle = 30 T4/P100 h/week ≈ **120 h/month**, more than the entire
  200-unit Colab balance (102 T4-h). Stack them.

---

## 7. Licensing summary — read before shipping

| Source | License | Commercial app? |
|---|---|---|
| QAC morphology | GPLv3 | ❌ copyleft |
| UD Arabic-PADT | CC BY-NC-SA 3.0 | ❌ NonCommercial |
| Tashkeela | GPL-2.0 | ❌ copyleft |
| CAMeL Tools (code) | MIT | ✅ |
| CATT / Shakkelha / Shakkala | MIT | ✅ |
| Qwen3 | Apache-2.0 | ✅ |
| arramooz | — verify | ? |

**A research paper is unaffected. A shipped commercial app built on QAC+PADT+Tashkeela is not
clean** — the training data is copyleft + non-commercial. Decide which you're building before
you invest in a pipeline, because it changes the corpus list.

---

## 8. Open items

1. **[FIXME]** QAC dependency graphs — scrape path, or drop (PADT covers it).
2. **[FIXME]** I3rab Treebank access — no public download; ask authors or check Nourjennane repo.
3. **[FIXME]** Confirm `Nourjennane/irab_project` vs `HatemSaadallah/irab_project` relationship.
4. ~~**[FIXME]** CAMeL `camel_data` download size — measure in Colab.~~ **RESOLVED 2026-10-08:**
   morphology DB 40.5 MB + MLE disambiguator 88.7 MB, both GPL v2, both installed locally. See §4.
5. **[FIXME]** arramooz license.
6. Verify QAC/PADT root-scheme conversion (Buckwalter → Arabic; PADT translit → Arabic).
   *Possibly moot — CALIMA's `bw`/`bwtok` keys already emit Buckwalter.*
7. **[NEW]** Decompose CALIMA's `pattern` into a clean per-stem wazān (strip `prc*`/`enc0` clitics and the
   `cas` vowel) and define the canonical wazān inventory. ~20% of raw values are fallbacks.
