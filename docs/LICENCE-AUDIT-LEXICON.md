# LEXICON LICENCE AUDIT & COMPLIANCE REPORT

**Document:** `docs/LICENCE-AUDIT-LEXICON.md`  
**Date:** 2026-10-16  
**Auditor:** Antigravity (Adhering to WORK_ORDER_PEDAGOGY_AND_ILAL.md §TASK C)  
**Product Objective:** Commercial Mobile Pedagogical Arabic App (Offline, On-Device, Proprietary / App Store Distribution)  
**Governing Rule:** *"A number whose licence forbids distribution is not a product number."* (ACTIVE_BACKLOG §7; WORK ORDER §0.4)

---

## 1. Executive Summary

As the project pivots from an exploratory research benchmark to a **pedagogical Arabic product for mobile distribution**, all dependencies, corpora, and lexicon assets must undergo a rigorous licence audit. 

Under research conditions, academic fair use and non-commercial exceptions permit evaluation across heterogeneous corpora. However, in a shipped mobile application, **licence obligations bind strictly**:
1. **Copyleft (GPL-2.0, GPLv3)**: Incorporating copyleft data or derived binaries forces the entire application source code to be released under copyleft terms.
2. **Non-Commercial (CC BY-NC-SA 3.0)**: Precludes any commercial distribution, monetization, paid download, or in-app subscription.
3. **The Pipeline Paradox (C == D)**: As measured in `EVIDENCE_LOG.md` §2cd, the `spelling_resource` index (`tashkeela_spelling_index.tsv.gz`) is what lifted raw surface exactness from ~60% to 72.7%. But because Tashkeela is GPL-2.0, **the thing that produces the product number is the thing that cannot ship**.

Below is the definitive source-by-source audit table and compliance determinations.

---

## 2. Source-by-Source Licence Audit Table

| Resource / Corpus | Declared Licence | Legal Obligations & Restrictions | Shippable in Commercial Mobile App? | Evidence & Risk Analysis |
|---|---|---|:---:|---|
| **Tashkeela** (75M vocalized words, 97 books) | **GPL-2.0** (`[LICENSE-RISK]`) | Strong copyleft. Any derivative dataset, index, or compiled table distributed with the app triggers GPL-2.0 copyleft obligations for the whole binary. | **NO (❌)** | `RESOURCES.md:119`. The existing `data/resources/tashkeela_spelling_index.tsv.gz` (8.4 MB) is gitignored specifically due to this risk. Per §2cd, TSV-only == shipped (C == D). Storing this table in a commercial app exposes the binary to GPL infection. |
| **arramooz** (`linuxscout/arramooz`, `arramooz-pysqlite`) | **GPL** (Ayaspell / GPL) | Strong copyleft. Resolving `RESOURCES.md:211` item 5 (`[FIXME] arramooz license`). The SQLite dictionary package is licensed under GNU GPL. | **NO (❌)** | PyPI metadata (`arramooz-pysqlite 0.4.2`) confirms `License: GPL`. Embedding this SQLite database or querying it inside a proprietary mobile app requires GPL compliance. Gated: cannot ship without a clean-room or dual-licensed alternative. |
| **PADT / NYUAD** (Prague Arabic Dependency Treebank) | **CC BY-NC-SA 3.0** | **NonCommercial** (NC) and **ShareAlike** (SA). Strictly prohibits commercial exploitation and requires derivative datasets to remain NC-SA. | **NO (❌)** | `RESOURCES.md:191, 198`. PADT data cannot be bundled, distilled, or incorporated into a commercial product. No product claim may derive from PADT. |
| **QAC** (Quranic Arabic Corpus morphology) | **GPLv3** | Strong copyleft. Derivative representations, parsed trees, or lookups packaged inside client software trigger GPLv3 terms. | **NO (❌)** | `RESOURCES.md:190, 198`. High-quality gold reference for evaluation, but cannot be distributed in a commercial closed-source app. |
| **CAMeL Tools Library** (`camel-tools`) | **MIT** | Permissive. Requires copyright and permission notices. | **YES (✅)** | `RESOURCES.md:143`. Permissive for library usage. |
| ↳ `morphology-db-msa-r13` | **GPLv2** (40.5 MB) | Strong copyleft database. | **NO (❌)** | Shipped locally for developer annotation/tokenization, but the database file cannot be embedded in a proprietary mobile bundle. |
| ↳ `morphology-db-msa-s31` | **LDC Licence** | Proprietary / Restricted academic membership. | **NO (❌)** | Restrictive; non-distributable. |
| **Qwen3-1.7B / Qwen3-0.6B** (Base Weights) | **Apache-2.0** | Permissive open commercial licence. Notice preservation and patent grant clauses. | **YES (✅)** | `RESOURCES.md:161`. Permitted base architecture for mobile inference (e.g. INT8 / GGUF). |
| **Shakkelha / Shakkala / CATT** | **MIT** | Permissive. | **YES (✅)** | Suitable for baseline comparison and toolchains. |
| **Repo Rule Engine** (`src/render_rules.py`, `src/renderer.py`, `src/pedagogy.py`) | **Proprietary / In-House** | First-party code, algorithmic and rule-based. Zero copyleft data dependencies. | **YES (✅)** | Deterministic, zero-ML, clean-room authored. Fully shippable. |

---

## 3. The Central Finding: The Pipeline Paradox (C == D)

> **"The thing that produces the product number is the thing that cannot ship."**

1. In `EVIDENCE_LOG.md` §2cd, comparative ablation showed that `spelling_resource.consult` (reading `tashkeela_spelling_index.tsv.gz`) yielded an identical surface result to the hybrid surface pipeline (C == D).
2. The rules add **0.000** where the TSV speaks.
3. However, `tashkeela_spelling_index.tsv.gz` is derived from Tashkeela (GPL-2.0). Distributing this 8.4 MB file inside a mobile application exposes the commercial app to GPL copyleft claims.
4. Furthermore, on the 300 human gold rows, `resource_on` misses:
   - `diacritic_only`: 76 rows
   - `tanwin_missing`: 8 rows
   Because tanwīn is invisible in undiacritized input, 25 rows (9.0% of gold-300) cannot be reached by *any* compiler without an explicit definiteness input (§2ce). A copyleft lexicon cannot solve this gap.

---

## 4. RED LINE 4: Evaluation Split Leakage & Permissible Shapes

**RED LINE 4:** *No evaluation split may enter any dictionary or candidate generator.*

### 4.1 Evaluation Split Provenance
The human gold benchmark (`bench-gold.jsonl`, 1000 rows) and `gold-tashkeela-300.jsonl` were sampled from Tashkeela book sources:
- `config/shared.yaml`: Books 0–7 are formally designated as the dev split *because* the gold was sampled from them.
- Any surface → `(root, wazān)` lookup table generated from Tashkeela risks directly memorizing the gold evaluation split.
- **Mandatory Leakage Protocol**: Any candidate dictionary or frequency index compiled from Tashkeela text must be tested using the `G:/aide-harness/leakage_test.py` methodology, reporting book overlap explicitly (as §2bo reported 2 of 40 = 5%).

### 4.2 The Only Surviving Shape
The only lexicon shape that has survived this audit and compliance protocol is:
- **Skeleton-keyed** (`strip_diac(token)`)
- **Count-only, aggregated** (frequency thresholds, e.g. `min_share = 0.95`)
- **Zero per-sentence provenance**
- **Zero (root, wazān) pairs attached**

Any dictionary associating unvocalized surface text directly to `(root, wazān)` pairs built from Tashkeela without book exclusion re-opens RED LINE 4 and invalidates benchmark claims.

---

## 5. Pre-Registration of ACTIVE_BACKLOG §3 & §4

Because copyleft lexicons (Tashkeela TSV, arramooz) are gated from direct commercial shipping, future work must follow the pre-registered roadmap items in `ACTIVE_BACKLOG.md`:

### 5.1 Pre-Registration of §3: Morphological Candidate Generator
- **Hypothesis:** A generator over an audited, clean-licensed lexicon guarantees linguistically valid analyses, so the neural model only needs to select among legal candidates.
- **Metric:** Candidate recall (the true analysis appears in top-$k$ candidates), reported separately across all benchmark strata.
- **Threshold:** Recall $\ge 0.95$ per benchmark stratum.
- **Compliance Requirement:** Must be accompanied by a per-source licence audit, with proof that recall stems from morphological rules rather than test-split leakage (RED LINE 4).
- **Status:** Pre-registered. *Not new work; strictly gated behind licence compliance.*

### 5.2 Pre-Registration of §4: Contextual Reranker over Candidates (Joint Root × Wazān)
- **Hypothesis:** Scoring root and wazān jointly in context beats independent argmax heads.
- **Metric:** Top-1 and top-$k$ accuracy against the candidate generator's own prior.
- **Threshold:** Must beat prior-only by $|d| > 2 \cdot \max(\text{sd})$ and must *not* regress the in-vocabulary stratum.
- **Status:** Pre-registered. *Not new work; does not replace the deterministic phonological compiler.*

---

## 6. Recommendations for Mobile App Deployment

1. **Ship `src/pedagogy.py` and `src/render_rules.py`**: These contain 100% clean, in-house, deterministic linguistic rules (Form I–X table, iʿlāl bil-ḥadhf, iʿrāb formatter, weak radical realization). They have zero copyleft obligations.
2. **Do Not Ship `tashkeela_spelling_index.tsv.gz` or `arramooz.sqlite`** in the mobile bundle.
3. **Keep `source: attention_argmax (UNVALIDATED)`**: Retain the transparent warning on all governor/ʿāmil predictions in UI cards until a formally validated syntactic dependency parser is trained on clean-licensed data.
4. **All Product Metrics Must Log `resource_off`**: To ensure legal and scientific honesty, all reported numbers must display `resource_off` alongside any `resource_on` ceiling, with the exact instrument (`gold-300` vs frozen `ruler` 973) explicitly identified.
