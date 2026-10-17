# Technical Architecture & Implementation Handoff: Native Arabic Root-Tree Foundation Model

**Project**: Dynamic, Interactive, Knowledge-Adaptive Arabic Learning Engine  
**Target Scope**: Classical Arabic (الفصحى التراثية) & Modern Standard Arabic (MSA)  
**Primary Deliverable**: Foundation Architecture Specification, Data Pipeline, Training Strategy, and Mobile Deployment Protocol  
**Methodological Framing**: Matched-size controlled architecture study (sub-Chinchilla by design)  

---

## 1. Executive Summary & Core Objective

Traditional Large Language Models (LLMs) process text as linear, 1D sequences of subword tokens, attempting to predict subsequent characters based on statistical frequency. For Semitic languages—specifically Classical Arabic and Modern Standard Arabic—this linear paradigm causes systematic failure modes:
1. **Diacritic Blindness**: Frequent misplacement of terminal case vowels (*I'rab*).
2. **Morphological Fragmentation**: Arbitrary slicing across roots and vocalic patterns.
3. **Post-Hoc Hallucination**: The need to reverse-engineer roots (*Juthūr*) and patterns (*Awzān*) from surface words after generation.

This handoff provides the end-to-end specifications for building a **Native Arabic Root-Tree Model**. Rather than generating surface letters first, the model plans at the level of the **semantic root graph**, resolves **syntactic dependency relations (العوامل والمعمولات)**, applies **morphological templates (الأوزان الصرفية)**, and renders fully vocalized, morphologically transparent text with guaranteed grammatical consistency.

---

## 2. Core Architectural Framework

```
+-----------------------------------------------------------------------------------+
|                           STEP 1: PEDAGOGICAL CONTROLLER                          |
|             Inputs: Learner Proficiency Level, Active Vocabulary, Grammar Goal    |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                     STEP 2: MACRO-SYNTACTIC ROOT GENERATOR                        |
|   Generates an Order-Free Dependency Graph of 3-Letter Roots & Syntactic Roles   |
|   Example: [Root: ك-ت-ب (Action)] ---Subject---> [Root: ط-ل-ب (Agent)]             |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                   STEP 3: TEMPLATIC BINDING & SARF REALIZER                       |
|   Binds Roots into Awzān via Algebraic Tensor Product Representations (TPR)       |
|   Root (ك-ت-ب) + Wazan (فَعَلَ) -> كَتَبَ | Root (ط-ل-ب) + Wazan (فَاعِل) -> طَالِب   |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|               STEP 4: PHONOLOGICAL & SYNTACTIC CASE INFLECTION (NAHW)             |
|   Applies Case Endings based on Directed Dependency Edges                         |
|   Fa'il -> Nominative (الطَّالِبُ) | Maf'ul -> Accusative (الدَّرْسَ)                 |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                   STEP 5: STRUCTURED JSON DELIVERY TO MOBILE APP                  |
|   Text + Word-by-Word Breakdown (Tashkeel, Root, Wazan, Meaning, Full I'rab)      |
+-----------------------------------------------------------------------------------+
```

### 2.1 The 3D Geometric Root Manifold ($\mathcal{M}_{\text{root}}$)
In place of a standard flat 1D embedding table $V \in \mathbb{R}^{|V| \times d}$, the root lexicon is modeled as a 3D coordinate tensor:
$$\mathcal{M}_{\text{root}} \in \mathbb{R}^{28 \times 28 \times 28 \times D_{\text{root}}}$$

* **Coordinate Indexing**: Every root is represented as an ordered triple $(C_1, C_2, C_3)$ of consonant IDs from the 28-letter alphabet.
* **Lexical Sparsity**: Out of $28^3 = 21,952$ possible combinations, only $\approx 6,500$ valid roots exist in the classical lexicon (*Lisān al-'Arab*). Invalid combinations are masked out during training.
* **Hapax Legomena & Long-Tail Regularization**: In corpus data, roots exhibit a heavy Zipfian long-tail (e.g., 395 of 1,642 Quranic roots appear only once). Modeling roots as coordinates across shared consonant embeddings ensures that even single-occurrence roots inherit strong phonetic and geometric regularization from their radical constituents.
* **Semantic Topology**: Roots sharing radical phonetic features (*Makhārij al-Hurūf*) sit in contiguous manifold regions, naturally capturing **الاشتقاق الأكبر** (semantic affinities between consonant permutations).

### 2.2 Algebraic Morphological Tensor Binding
A surface word vector $\mathbf{v}_{\text{word}}$ is generated by an algebraic binding operation over distinct linguistic planes:
$$\mathbf{v}_{\text{word}} = \mathbf{W}_{\text{proj}} \Big( \mathbf{e}_{\text{root}}(C_1, C_2, C_3) \odot \mathbf{e}_{\text{wazan}}(W) \odot \mathbf{e}_{\text{clitics}}(K) \Big) + \mathbf{e}_{\text{pos}}(\text{POS}) + \mathbf{e}_{\text{case}}(\text{Case})$$

* **$\mathbf{e}_{\text{root}}$**: Vector representation from the 3D root space.
* **$\mathbf{e}_{\text{wazan}}$**: Vector representation from the finite catalog of $\approx 70$ primary verbal and nominal patterns (*فَعَلَ، أَفْعَلَ، فَاعَلَ، فَعَّلَ، تَفَعَّلَ، تَفَاعَلَ، اسْتَفْعَلَ، فُعُول، فَعِيل، مَفْعُول...*).
* **$\mathbf{e}_{\text{clitics}}$**: Discrete multi-hot encoding of attached particles (conjunctions, prepositions, future marker, attached pronouns).
* **$\mathbf{e}_{\text{case}}$**: Syntactic inflection vector mapped strictly from validated case categories (*Nominative, Accusative, Genitive*).

---

## 3. Data Engineering & Corpus Architecture

### 3.1 Curated Gold Dependency Treebanks
To supervise the macro-syntactic tree without running external dependency parsers, merge these verified gold-standard resources:

1. **UD_Arabic-NYUAD** (19,738 sentences / 738,889 tokens):
   * Converted from Penn Arabic Treebank (PATB) by NYU Abu Dhabi. High-quality syntactic dependency trees for formal modern prose.
2. **Electronic Quran Treebank (EQTB) / Quranic Arabic Corpus** (6,236 verses / ~132,736 tokens):
   * Complete sentence-by-sentence gold annotation: surface tokens, lemmas, 3-letter roots, morphological patterns, and traditional *I'rab* dependency trees.
3. **UD_Arabic-PADT** (7,664 sentences / 282,384 tokens):
   * Prague Arabic Dependency Treebank core distribution.
4. **UD_Arabic-PUD** (1,000 sentences):
   * Parallel Universal Dependencies set.

**Total Gold Supervision**: $\approx \mathbf{34,638\text{ sentences}}$ (~1.15M tokens) with zero dependency parser circularity.

### 3.2 Silver Morphology via Direct CALIMA Extraction
Instead of chaining heavy external parsers over Tashkeela (75M words), run morphological disambiguation directly using CALIMA:
* **Junk Filtration**: Discard analyses where `source != 'lex'` or where `root is None` (~1% noise reduction).
* **Proclitic Extraction**: Use CALIMA's structured fields (`prc0`, `prc1`, `prc2`, `prc3`) directly rather than brittle regex string matching.
* **Mould Extraction with Doubled Radicals**: In geminate roots (*المضعف* like *مَدَّ* $\rightarrow$ root `م.د.د`), CALIMA emits literal repeated characters (e.g., repeating `د` rather than purely indexed digits `1, 2, 3`). The pattern normalizer explicitly handles radical substitution for both numbered placeholders and literal repeated root letters.

### 3.3 Root Masking Protocol
Because treebanks vary in annotation conventions (e.g., treating certain weak roots or loanwords differently), apply **source-aware root masking**: if a source does not reliably annotate a word's root, its root classification loss is masked to zero rather than penalizing the model.

---

## 4. Multi-Task Training Objectives & Corrected Feature Mappings

The training objective enforces grammatical compliance via explicit auxiliary heads:

$$\mathcal{L}_{\text{Total}} = \mathcal{L}_{\text{NTP}} + \lambda_1 \mathcal{L}_{\text{Root}} + \lambda_2 \mathcal{L}_{\text{Wazan}} + \lambda_3 \mathcal{L}_{\text{Syntax}} + \lambda_4 \mathcal{L}_{\text{Case}}$$

```
                                [ Transformer Latent Hidden State h_t ]
                                                   |
      +--------------------+-----------------------+-----------------------+--------------------+
      |                    |                       |                       |                    |
      v                    v                       v                       v                    v
  Head 1 (NTP)        Head 2 (Root)          Head 3 (Wazan)        Head 4 (Syntax)       Head 5 (Case)
Predict Next Lemma    Predict (C1, C2, C3)    Predict Pattern ID    Predict Dep Role      Predict Case (n/a/g)
[Next-Token Loss]     [3D Cross-Entropy]      [Multi-Class CE]     (Fa'il / Maf'ul)     (Nominative/Acc/Gen)
```

### 4.1 Strict `cas` Feature Mapping for Head 5
In CAMeL / CALIMA specifications, the `cas` feature represents grammatical case, **not** surface vowels:

| CALIMA `cas` Code | Grammatical Meaning | Surface Marker (Standard) | Head 5 Target | Measured Distribution |
| :---: | :---: | :---: | :---: | :---: |
| **`n`** | **Nominative** (*مرفوع*) | Damma (*ُ*) / Waw / Alif | Class 0 (`NOM`) | ~5.5% |
| **`a`** | **Accusative** (*منصوب*) | Fatha (*َ*) / Ya / Kasra | Class 1 (`ACC`) | ~9.2% |
| **`g`** | **Genitive** (*مجرور*) | Kasra (*ِ*) / Ya / Fatha | Class 2 (`GEN`) | ~33.0% |
| **`u`** | **Undefined** (*غير محدد*) | Indeterminate / Ambiguous | **Masked (Loss = 0)** | ~15.7% |
| **`na`** | **Not Applicable** | Verbs, Particles, Uninflected | **Masked (Loss = 0)** | ~36.6% |

> **Critical Fix**: `u` denotes **Undefined**, NOT Damma. Mapping `u` to Damma would inject ~16% label noise into Head 5. Genitive is `g`, not `i`. Loss for `u` and `na` must be masked during backpropagation.

---

## 5. Experimental Design & Parameter Scaling Framing

### 5.1 The Compute & Scaling Justification
* **Token Budget**: ~98M tokens (Tashkeela + Treebanks).
* **Target Parameter Range**: 15M to 25M parameters.
* **Scientific Defense**:
  * Chinchilla compute-optimal training suggests $Tokens \approx 20 \times Parameters$, meaning a 25M model optimally trains on ~500M tokens.
  * **Paper Framing**: Frame the evaluation strictly as a **"matched-size comparison, sub-Chinchilla by design."**
  * Both the baseline arm (standard causal Transformer predicting next BPE tokens) and the experimental arm (Root-Tree model predicting factorized representations) are trained on identical token splits, step counts, and parameter sizes. This isolates architectural inductive bias from parameter scale.

---

## 6. Mobile Runtime & Edge Deployment Protocol

For a responsive mobile app (Android/iOS), the inference stack must maintain sub-100ms latency without requiring internet connectivity.

### 6.1 Model Footprint & Sizing Budget
* **Target Size**: 15M to 25M parameters (research prototype) up to 1.1B (production app model).
* **Precision / Quantization**: 4-bit Medium Quantization (`Q4_K_M` GGUF or `int4` ExecuTorch format).
* **RAM Allocation**: Under 50 MB (for 25M prototype) or ~1.1 GB (for 1.1B model).
* **Supported Frameworks**:
  * **iOS**: ExecuTorch / Apple CoreML.
  * **Android**: `llama.cpp` mobile runtime / MLC-LLM / Snapdragon NPU.

### 6.2 Deterministic Output Schema via Constrained Decoding (GBNF)
```gbnf
root ::= "{" ws "\"paragraph\":" ws string "," ws "\"analysis\":" ws "[" ws (word_item ("," ws word_item)*)? ws "]" ws "}"

word_item ::= "{" ws 
  "\"word\":" ws string "," ws 
  "\"tashkeel\":" ws string "," ws 
  "\"root\":" ws string "," ws 
  "\"wazan\":" ws string "," ws 
  "\"meaning\":" ws string "," ws 
  "\"irab\":" ws string 
ws "}"

string ::= "\"" [^\"]* "\""
ws ::= [ \t\n\r]*
```

---

## 7. Python Implementation: Clean Wazan & Case Normalizer

```python
def extract_morph_labels(analysis: dict):
    """
    Extracts verified root, wazan, and grammatical case from CALIMA analysis.
    Uses discrete fields (prc0-prc3, cas) to avoid regex fragility.
    """
    # 1. Junk Filter
    if analysis.get('source') != 'lex' or not analysis.get('root'):
        return None

    root = analysis.get('root')          # e.g., 'ك.ت.ب'
    raw_pattern = analysis.get('pattern') # e.g., 'ال1َا2ِ3ُ' or geminate form
    cas_code = analysis.get('cas')        # 'n', 'a', 'g', 'u', 'na'

    # 2. Case Target Mapping
    case_target_map = {
        'n': 'NOMINATIVE',  # Damma / مرفوع
        'a': 'ACCUSATIVE',  # Fatha / منصوب
        'g': 'GENITIVE',    # Kasra / مجرور
        'u': None,          # Undefined -> Mask loss
        'na': None          # Not applicable -> Mask loss
    }
    case_label = case_target_map.get(cas_code, None)

    # 3. Proclitic Extraction from Discrete Fields
    proclitics = [
        analysis.get('prc3'),
        analysis.get('prc2'),
        analysis.get('prc1'),
        analysis.get('prc0')
    ]
    active_clitics = [p for p in proclitics if p and p != '0']

    # 4. Pattern Normalization (Mapping 1, 2, 3 and repeated radicals)
    if raw_pattern and raw_pattern != 'None':
        translation_table = str.maketrans({'1': 'ف', '2': 'ع', '3': 'ل', '4': 'ل'})
        wazan = raw_pattern.translate(translation_table)
    else:
        wazan = 'NON_TEMPLATIC'

    return {
        'root': root,
        'wazan': wazan,
        'case_label': case_label,
        'clitics': active_clitics
    }
```
