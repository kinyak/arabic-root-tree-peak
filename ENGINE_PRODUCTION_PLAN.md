# End-to-End Production Engineering Plan & Release Thresholds for `arabic-root-tree`

## 1. Current Baseline State vs. Production Requirements

From our latest verified 12,000-step run (`code_bundle_sha: 591fc96a...` + CPU post-render fixes), we have two separate checkpoints on disk:
1. **`silver-treatment` (`9.21M` params):**
   - **Strengths:** Strong morphological generalization (`80.6%` beamed root accuracy on Gold-300; `87.3%` beamed root accuracy on cross-domain PADT dev; `94.7%` suffixed `stem_tail` accuracy in-domain; `49.5%` raw / `56.3%` skeleton `wazan` accuracy on Gold-300).
   - **Weakness:** Syntactic case head (`0.475` Macro-F1 on Gold-300; `0.473` on PADT dev) was degraded by noisy CALIMA silver `t_case` labels during training.
2. **`gold-treatment` (`9.21M` params):**
   - **Strengths:** Strong syntactic case (`0.804` Macro-F1 on PADT dev; `0.602` Macro-F1 on Gold-300) and `72.7%` (`218/300`) end-to-end surface accuracy with the spelling resource enabled.
   - **Weakness:** Lower root coverage on classical vocabulary (`53.6%` beamed root on Gold-300) due to training only on 120k modern newswire tokens.

**Production Objective:**
Eliminate the split-brain by training **one unified 9.21M-parameter production checkpoint (`unified-prod-v1`)**, pairing it with a **3-Tier Lexicon + Rasm-Constrained Decision Cascade**, adding a **Deterministic *Naḥw* Counterfactual Verifier & Semantic Binder**, and exporting an **INT8 quantized CPU inference server** with `< 10 ms` latency.

---

## 2. Phase-by-Phase Engineering Plan

### Phase 1: Unified Multi-Source Training (Single Model, Zero Split-Brain)
**Files:** `src/train.py`, `src/wazan_normalizer.py`, `src/model_arms.py`, `config/prod.yaml`

1. **Apply `sparse_wazan_map.json` at Dataset Load Time (`src/wazan_normalizer.py`):**
   - Currently, `sparse_wazan_map.json` (434 mappings from unvocalized CALIMA skeletons like `"123"` $\to$ `"1َ2َ3"` and `"مُ1ْت23"` $\to$ `"مُ1ْتَ2َ3"`) is only applied post-hoc during decoding.
   - Move this mapping inside `split_wazan_stem_and_tail()` before `Vocabs` construction so the model never trains on vowelless CALIMA pattern labels.
2. **50/50 Gold-Silver Interleaving with Per-Head Source Masking (`src/train.py`):**
   - Sample batches 1:1 from `padt-train.jsonl` (Gold) and `tashkeela-train.jsonl` (Silver) for `15,000` steps (`batch_size: 64`).
   - **Hard Masking Rule on Silver Batches:** In `make_batch(..., source="silver")`, force `m_case = IGNORE (-100)` and `m_syntax = IGNORE (-100)`.
   - **Result:** `h_case` (bilinear governor attention) and `h_syntax` (`deprel`) receive 100% of their gradients from human-annotated PADT treebank sentences, while `CharSlotRootHead`, `h_wazan`, `h_stem_tail`, and clitic heads train on the full 2.0M-token union of PADT + Tashkeela.
3. **Root-to-Wazān Feedback Connection (`src/model_arms.py`):**
   - In `Arm.forward` (`kind == "treatment"`), compute `CharSlotRootHead` first using an initial context query, then concatenate the extracted radical-slot context `slot_char_ctx.flatten(-2)` (`512-d`) into `h_wazan_bottleneck` so template prediction knows which character positions are root radicals vs. template infixes.
   - Export `gov_attn_weights` (`(B, L, L)` softmax weights from `case_gov_q @ case_gov_k.T`) in the return dictionary of `Arm.forward` so the app can render syntactic governor arrows (`ʿĀmil` $\to$ `Maʿmūl`).

---

### Phase 2: The 3-Tier Production Decision Cascade (`src/decision_cascade.py`)
**Goal:** Never rely on blind unconstrained generation when a word is in the lexicon, and never let the lexicon pick a contextually wrong homograph without consulting the neural syntax/morphology heads.

1. **Build the Unified Morphological Lexicon (`data/resources/morph_lexicon.sqlite`):**
   - Compile Arramooz + Tashkeela + PADT into an indexed lookup table keyed by `bare_stem`:
     `(bare_stem, vocalized_stem, root, wazan_stem, stem_tail, upos, definiteness, count)`
2. **Tier 0 — Closed-Class Particle & Loanword Bypass:**
   - If `bare_token` is in `CLOSED_CLASS_PARTICLES` (`من`, `في`, `على`, `إلى`, `لم`, `لن`, `إن`, `أن`, `الذي`, `التي`, `هذا`, `ذلك`, etc.) or `NON_TEMPLATIC_PROPER_NOUNS` (`إبراهيم`, `إسماعيل`, `بغداد`), emit `tier = "PARTICLE_OR_NON_TEMPLATIC"`, `root = None`, `wazan = None`, and return its exact deterministic vocalization + syntactic governor role (`HARF_JARR`, `HARF_NASB`, `ISM_MAWSUL`, etc.).
3. **Tier 1 — Lexicon-Constrained Neural Joint Reranker (In-Lexicon Tokens):**
   - Strip proclitics/enclitics via `affix_frame(bare_token)` and query `morph_lexicon.sqlite` for all attested `(vocalized_stem, root, wazan, tail)` tuples matching `bare_stem`.
   - Score each attested candidate $c$ in a single pass using the neural model's contextual log-probabilities:
     $$S(c) = 2.0 \log P_{\text{neural}}(\text{root}_c) + 1.2 \log P_{\text{neural}}(\text{wazan}_c) + 0.8 \log P_{\text{neural}}(\text{tail}_c) + 1.5 \cdot \mathbb{I}[\text{case\_compatible}(c, \hat{y}_{\text{case}})] + 0.4 \log_{10}(\text{count}_c + 1)$$
   - Apply the contextual case ending (`NOM`, `ACC`, `GEN`, or `None` for verbs/indeclinables) via `apply_case`.
4. **Tier 2 — Rasm-Constrained Compositional Compiler (OOV & Novel Inflections):**
   - When `morph_lexicon.sqlite` has 0 hits for `bare_stem`, execute `decode_rasm_constrained` over the top-$K$ beamed roots and arity-matched vocalized *awzān*, filtering candidates by `rasm(rendered) == rasm(bare_token)`.
5. **Calibrated Abstention (`Noul` Gate):**
   - Apply temperature scaling ($T$) to the joint candidate distribution. If $\max_c P(c \mid x) < \tau_{\text{abstain}}$ ($0.45$), flag the token as `needs_disambiguation: True` and return the top 2 candidates with their contrasting meanings instead of silently guessing.

---

### Phase 3: Pedagogical Explainer, Counterfactual *Naḥw* Verifier & Semantic Translator
**Files:** `src/pedagogy.py`, `src/nahw_verifier.py`, `src/semantic_binder.py`

1. **`src/pedagogy.py` (*Ṣarf* & *Iʿlāl* Explainer):**
   - `to_mizan_sarfi(wazan_stem, stem_tail) -> dict`: Converts numeric slot strings (`مُ1ْتَ2َ3` + `َة`) into standard Arabic *Mīzān* notation (`مُفْتَعَلَة`), identifies Verb Form (`Form I`–`Form X` / `Quad`), and labels the derivative category (*Fiʿl Māḍī*, *Fiʿl Muḍāriʿ*, *Maṣdar*, *Ism Fāʿil*, *Ism Mafʿūl*, *Ṣifah Mushabbahah*, *Ism التفضيل*).
   - `trace_render_triple(root, wazan, case, stem_tail) -> list[dict]`: Instruments `render_rules.py` so every firing phonological rule records `(step_name, before_surface, after_surface, arabic_rule_explanation)` (e.g., *Iʿlāl bil-qalb*: converting `قَوَلَ` $\to$ `قَالَ` because radical 2 is a vocalized *wāw* preceded by *fatḥah*).
2. **`src/nahw_verifier.py` (Counterfactual Sandbox Constraint Engine):**
   - Takes an array of user-arranged tiles `[{"surface": ..., "root": ..., "wazan": ..., "tail": ..., "proclitic": ..., "definiteness": ..., "user_case": ...}]`.
   - Runs 8 deterministic syntactic & morphological checks:
     1. `CHECK_AL_TANWIN_CLASH`: Rejects `الـ` combined with *tanwīn* (`ٌ / ً / ٍ`).
     2. `CHECK_PREP_GENITIVE`: Verifies any noun preceded by a preposition (*Ḥarf Jarr*) or proclitic `بِ/لِ/كَ` has `user_case == "GEN"` (or *fatḥah* if diptote / *Mamnūʿ min al-Ṣarf* and indefinite).
     3. `CHECK_VERB_VALENCY_AND_FAIL`: Verifies every active verb has a uniquely identifiable *Fāʿil* (either an attached pronoun tail like `ـتُ/ـوا` or a `NOM` noun in the clause) and flags `MISSING_FAIL` or `DOUBLE_FAIL_COLLISION`.
     4. `CHECK_PASSIVE_NAIB_FAIL`: If the verb template is passive (`1ُ2ِ3َ` or `يُ1ْ2َ3ُ`), verifies the patient takes `NOM` (*Nāʾib al-Fāʿil*) rather than `ACC`.
     5. `CHECK_SVO_VSO_AGREEMENT`: Verifies verb-subject number and gender agreement based on relative position (`VSO` singular verb vs. `SVO` number-matched verb).
     6. `CHECK_IDAFAH_CHAIN`: Verifies the first noun (*Muḍāf*) drops *tanwīn* and `الـ`, and the second noun (*Muḍāf ilayhi*) takes `GEN`.
     7. `CHECK_SOUND_PLURAL_INFLECTION`: Verifies sound masculine plurals use `ـُونَ` for `NOM` and `ـِينَ` for `ACC/GEN`, and sound feminine plurals (`ـَات`) use *kasrah* (`ـِ / ـٍ`) for both `ACC` and `GEN`.
     8. `CHECK_INNA_KANA_GOVERNMENT`: Verifies *Inna* sisters assign `ACC` to the subject and `NOM` to the predicate, while *Kāna* sisters assign `NOM` to the subject and `ACC` to the predicate.
3. **`src/semantic_binder.py` (Diacritic-Driven Meaning & Translation Generator):**
   - Binds semantic roles (`AGENT`, `PATIENT`, `RECIPIENT`, `LOCATION`, `POSSESSOR`, `PREDICATE`) strictly from the verified **morphological voice + `user_case` diacritics + governor links** (never from naive English SVO word order!).
   - Generates a live English/Indonesian translation + an *Information Structure Note* (e.g., explaining emphasis when the user fronts the `ACC` object before the `NOM` subject).

---

### Phase 4: Production Packaging, Quantization & FastAPI Service
**Files:** `src/export_prod.py`, `src/api_server.py`

1. **Dynamic INT8 Quantization:**
   - Apply `torch.ao.quantization.quantize_dynamic(model, {nn.Linear}, dtype=torch.qint8)` to the unified `Treatment` checkpoint, reducing model weight size from `~36 MB` to `~9.5 MB`.
2. **FastAPI Endpoints (`src/api_server.py`):**
   - `POST /v1/analyze`: Full sentence decomposition, vocalization, governor graph, and *Mīzān* / *Iʿlāl* traces.
   - `POST /v1/sandbox/evaluate`: Real-time evaluation of user-manipulated tiles and diacritics, returning `{is_valid, violations[], semantic_roles, live_translation, governor_arrows[], iclaal_traces[]}`.
   - `POST /v1/mastery/next_drill`: Queries `user_knowledge.sqlite` for the user's lowest-mastery or locked nodes and dynamically compiles a targeted exercise.

---

## 3. Production Readiness Gates & Release Metric Thresholds

No model or backend update ships to the learning app unless **all 10 Production Release Gates** pass on CPU:

### A. Accuracy & Linguistic Quality Gates (Evaluated on Frozen Gold-300 & PADT Dev)

| Gate ID | Component / Metric | Current Score | **Production Release Threshold** | Why This Threshold Is Required for the App |
| :--- | :--- | :---: | :---: | :--- |
| **G1** | **Oracle Compiler Accuracy** (`render_triple` + `trace_render_triple` on Gold-300) | `97.49%` (`272/279`) | **$\ge 98.0\%$** | When the user dials a root + *wazn* in the Sandbox, the rendered Arabic word and *Iʿlāl* trace must be virtually flawless. |
| **G2** | **Unified Model Root Extraction** (`gold-300` Beamed Root Accuracy) | `80.65%` (Silver) / `56.99%` (Gold) | **$\ge 82.0\%$** (in-lexicon + OOV) | Ensures the single unified model retains Silver's classical root mastery without regression. |
| **G3** | **Cross-Domain Root Generalization** (`padt-dev` Beamed Root Accuracy) | `87.25%` | **$\ge 87.0\%$** | Guarantees the model handles modern standard Arabic sentences as well as classical prose. |
| **G4** | **Syntactic Case Macro-F1** (`padt-dev` / `gold-300` Nominal Case) | `0.804` (PADT) / `0.602` (Gold-300) | **$\ge 0.800$** (PADT) / **$\ge 0.620$** (Gold-300) | Proves Silver case-masking succeeded and the unified model has Gold-grade *Iʿrāb* prediction. |
| **G5** | **Suffix & Clitic Plane Accuracy** (`padt-dev` `stem_tail` suffixed + `proclitic` + `enclitic`) | `96.1%` / `99.7%` / `99.7%` | **$\ge 95.0\%$** suffixed tail, **$\ge 99.0\%$** clitics | Boundary segmentation errors corrupt the entire downstream analysis card. |
| **G6** | **3-Tier Hybrid End-to-End Surface Accuracy** (`gold-300` with Unified Morph Lexicon) | `72.7%` (`218/300`) | **$\ge 85.0\%$** covered accuracy ($\le 5\%$ calibrated abstention) | Production threshold for showing automatic vocalization and structural cards on arbitrary reading passages. |

### B. Counterfactual Sandbox & System Performance Gates

| Gate ID | System / Sandbox Invariant | **Production Release Threshold** | Verification Method |
| :--- | :--- | :---: | :--- |
| **G7** | **Counterfactual *Naḥw* Verifier Precision & Recall** | **100.0% (100/100)** on the 100-sentence Minimal-Pair Mutation Suite | Automated test suite (`tests/test_sandbox_mutations.py`) testing 50 valid diacritic/order mutations (`V-S-O` $\leftrightarrow$ `V-O-S`, Active $\leftrightarrow$ Passive) and 50 illegal mutations (Double *Fāʿil*, *Jarr* violations, `ال` + *tanwīn*, *Iḍāfah* errors, Sound Plural case mismatches). |
| **G8** | **Diacritic-Sensitive Semantic Role Binding** | **100.0%** role-flip accuracy on minimal pairs (`ضَرَبَ زَيْدٌ عَمْرًا` vs `ضَرَبَ زَيْدًا عَمْرٌ`) | Asserts `semantic_binder.py` flips `AGENT` and `PATIENT` purely from `user_case` and verb voice, regardless of linear word order. |
| **G9** | **Zero Target Leakage (`A - B == 0` Invariance)** | **0 mismatches** (`strip_diac(input)` vs `input` when evaluating unvocalized mode) | `tools/test_gate4.py` must exit `0`. |
| **G10** | **CPU Inference Latency & Footprint** | **$< 15\text{ ms}$** per sentence (`p95` on 4-core CPU), model artifact **$< 15\text{ MB}$** | Benchmark 100 consecutive `/v1/sandbox/evaluate` and `/v1/analyze` requests on CPU with INT8 quantized model. |

---

## 4. Immediate Execution Sequence for the Agent

1. **Milestone 1 (CPU — 1 day):** Build `src/pedagogy.py`, `src/nahw_verifier.py`, `src/semantic_binder.py`, and `tests/test_sandbox_mutations.py` (100 minimal-pair counterfactual sentences). Pass **Gates G1, G7, G8**.
2. **Milestone 2 (CPU — 1 day):** Build `data/resources/morph_lexicon.sqlite` from Arramooz + Tashkeela + PADT and wire `src/decision_cascade.py` (Tier 0 + Tier 1 + Tier 2). Test on existing `gold-treatment-s20261010.pt` and `silver-treatment-s20261009.pt`.
3. **Milestone 3 (1x GPU — 40 mins):** Run the single unified training (`unified-prod-v1`: 50/50 Gold+Silver interleaving with `m_case=0` and `m_syntax=0` on Silver batches, `sparse_wazan_map` applied at load time, and Root $\to$ Wazān feedback). Verify **Gates G2, G3, G4, G5, G6**.
4. **Milestone 4 (CPU — Half day):** Quantize `unified-prod-v1.pt` to INT8, wire `user_knowledge.sqlite` + FastAPI endpoints in `src/api_server.py`, and verify **Gates G9 & G10**.