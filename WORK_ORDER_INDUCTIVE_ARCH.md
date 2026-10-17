# **WORK ORDER: End-to-End Inductive Morphology Architecture & Instrument Repair**

## **0\. Hard Rules Before Touching Code**

> 1. **Zero GPU spend until all 6 CPU verification gates exit 0**.  
> 2. **Never silently map an unseen or malformed suffix to Class 0 ("", bare stem).** Class 0 is strictly reserved for true bare stems (tail \== "") when m\_wazan \== 1\. Malformed/junk tails (َ5) must map to IGNORE \= \-100.  
> 3. **Never quote resource\_on (dictionary lookup) as evidence for the neural planner**. Every evaluation in results.json must explicitly log both resource\_off (the thesis metric: neural plan \+ rule compiler) and resource\_on (the hybrid product ceiling).  
> 4. **No uncommitted config drift:** make\_notebook.py must refuse to build if config/shared.yaml has uncommitted diffs, and the notebook preflight cell must print the exact loss.weights, normalise\_by\_log\_vocab, steps, and batch\_size.

## **Task 1: Fix the wazan \+ stem\_tail Seam & Build the Clean Union Tail Inventory (src/wazan\_normalizer.py & src/model\_arms.py)**

### **Why Current Code Fails**

> 1. tail\_strip(w) strips the suffix and trailing stem vowel (\_VOWEL\_BEFORE\_TAIL), while vocalized\_stem\_tail(w) slices the raw CALIMA tail ("ات", "ان", "اء", "َّة"). When CALIMA writes "ات" without a leading fatha and tail\_strip strips the fatha off the stem, splicing stem \+ "ات" produces un-vocalized "مُقَدِّمات" instead of gold "مُقَدِّمَات".  
> 2. In patterns like مُ1َ2ِّ3َة, the shadda ّ belongs to radical 3, not the tail. Slicing َّة into the tail created 2,186 false out-of-inventory misses in PADT.  
> 3. Because h\_wazan predicts tail\_strip(raw\_w), predicting class 0 ("") on h\_stem\_tail leaves the rendered stem **with no suffix at all** (مُقَدِّم for مُقَدِّمَاتٍ and مَعْرِف for مَعْرِفَتِهَا).

### **Exact Implementation (src/wazan\_normalizer.py)**

> 1. Implement split\_wazan\_stem\_and\_tail(raw\_wazan: str) \-\> tuple\[str, str\] | None:  
>    \_VALID\_WAZAN\_CHARS \= re.compile(r"^\[1234\\u0621-\\u063a\\u0641-\\u064a\\u064b-\\u0652\\u0670\\u0671\]+\$")  
>    \_RADICAL\_DIGITS \= re.compile(r"\[1234\]")

>    def split\_wazan\_stem\_and\_tail(raw\_wazan: str) \-\> tuple\[str, str\] | None:  
>        if not raw\_wazan or not \_VALID\_WAZAN\_CHARS.match(raw\_wazan):  
>            return None  \# Rejects 'َ5', page markers, and non-Arabic junk \-\> IGNORE (-100)  
>        matches \= list(\_RADICAL\_DIGITS.finditer(raw\_wazan))  
>        if not matches:  
>            return None  
>        last\_digit\_end \= matches\[-1\].end()  
>        \# Keep shadda (and any vowel between the last digit and shadda) on the last radical slot\!  
>        \# Only strip the vowel that immediately precedes the suffix (or ends the word).  
>        rest \= raw\_wazan\[last\_digit\_end:\]  
>        shadda\_match \= re.match(r"^(\[\\u064e\\u064f\\u0650\]\*\\u0651)", rest)  
>        if shadda\_match:  
>            last\_digit\_end \+= shadda\_match.end()  
>            rest \= raw\_wazan\[last\_digit\_end:\]

>        \# Strip the connecting stem vowel into the tail so the tail is self-contained for splicing  
>        stem\_raw \= raw\_wazan\[:last\_digit\_end\]  
>        tail\_raw \= rest

>        \# If there are no Arabic letters in tail\_raw, it is a BARE stem (trailing vowels are case/mood)  
>        if not re.search(r"\[\\u0621-\\u063a\\u0641-\\u064a\]", tail\_raw):  
>            stem\_canon \= canonicalize\_mater\_vowels(stem\_raw)  
>            return (stem\_canon, "")

>        \# Canonicalize leading mater vowels on the tail so CALIMA 'ات'/'ان'/'اء'/'ى' match Gold 'َات'/'َان'/'َاء'/'َى'  
>        if tail\_raw.startswith("\\u0627") or tail\_raw.startswith("\\u0649"):  \# bare 'ا' or 'ى'  
>            tail\_canon \= "\\u064e" \+ tail\_raw  \# prepend fatha 'َ'  
>        elif tail\_raw.startswith("\\u0648") and not re.match(r"^\\u0648\[\\u064e\\u064f\\u0650\\u0652\\u0651\]", tail\_raw):  
>            tail\_canon \= "\\u064f" \+ tail\_raw  \# prepend damma 'ُ' before bare waw mater 'ون'/'وا'  
>        elif tail\_raw.startswith("\\u064a") and not re.match(r"^\\u064a\[\\u064e\\u064f\\u0650\\u0652\\u0651\]", tail\_raw):  
>            tail\_canon \= "\\u0650" \+ tail\_raw  \# prepend kasra 'ِ' before bare ya mater 'ين'/'ي'  
>        else:  
>            tail\_canon \= tail\_raw

>        tail\_canon \= canonicalize\_mater\_vowels(tail\_canon)  
>        stem\_canon \= canonicalize\_mater\_vowels(stem\_raw)  
>        return (stem\_canon, tail\_canon)

> 2. **Build the Union stem\_tail Vocabulary in Vocabs.\_\_init\_\_ (src/model\_arms.py):**  
   * Initialize self.stem\_tail \= {"": 0} (Index 0 is explicitly the bare-stem class "").  
   * Iterate over all training sentences (GOLD\_TR \+ SILV\_TR) plus STEM\_TAIL\_VOCALIZED from gold-300, call split\_wazan\_stem\_and\_tail(t\["t\_wazan"\]), and add every valid tail\_canon \!= "" to self.stem\_tail.  
   * In make\_batch():  
     * If not t.get("m\_wazan"): set wazan \= IGNORE (-100), wazan\_canonical \= IGNORE (-100), stem\_tail \= IGNORE (-100).  
     * Else call res \= split\_wazan\_stem\_and\_tail(t.get("t\_wazan")):  
       * If res is None: set wazan \= IGNORE, wazan\_canonical \= IGNORE, stem\_tail \= IGNORE.  
       * Else unpack stem\_c, tail\_c \= res:  
         * wazan\_id \= v.wazan.get(stem\_c, IGNORE)  
         * tail\_id \= 0 if tail\_c \== "" else v.stem\_tail.get(tail\_c, IGNORE) (**NEVER** fallback to 0 when tail\_c \!= ""\!).

### **Gate 1 (CPU)**

> * Run a census script over padt-train.jsonl (223,881 rows), tashkeela-train.jsonl (1,871,205 rows), and gold-tashkeela-300.jsonl (300 rows):  
  * Assert suffixed\_mapped\_to\_zero \== 0 on all three datasets.  
  * Assert non\_arabic\_tails\_in\_vocab \== 0\.  
  * Assert that on gold-300, render\_triple(gold\_root, stem\_c, gold\_case, token=gold\_form, stem\_tail=tail\_c) with resource\_off achieves **\\ge 78.8\\%** stem accuracy.

## **Task 2: True Architectural Separation — Inductive Morphology (Treatment) vs. Flat Probing (Baseline) (src/model\_arms.py)**

### **Why Current Code Fails**

> 1. Both arms currently use the exact same flat linear heads (Linear(256 \-\> C)) on the same pooled trunk vector h, differing only by h\_surface \= nn.Linear(256, 20000).  
> 2. CharEncoder max-pools across the word (Conv1d \\to max), destroying character positions so h\_stem\_tail (4.7% accuracy on suffixed words) cannot see the word's suffix letters and h\_root cannot point to radical positions.  
> 3. h\_ntp (Linear(256, 10070), 2.58M params) is dead weight (0% silver supervision, 0.0002 cross-domain accuracy, used nowhere).  
> 4. case\_gov\_v is zero-initialized (nn.init.zeros\_), which mathematically zeroes out the backward gradient \\frac{\\partial L}{\\partial Q} and \\frac{\\partial L}{\\partial K} to case\_gov\_q and case\_gov\_k\!

### **Exact Implementation (src/model\_arms.py)**

#### **A. Remove h\_ntp Bloat & Keep Sequence-Level Character States in CharEncoder**

> 1. Set heads.ntp.weight: 0.0 in config/shared.yaml and do not instantiate self.h\_ntp when ntp weight is 0.0 (saving 2.58M parameters on both arms).  
> 2. Update CharEncoder.forward(chars) (where chars has shape (B, L, M) with M \= 16 max characters per token):  
   * Compute character embeddings \+ positional embeddings char\_pos, apply the multi-kernel Conv1d (k=3, 5, 7\) with padding so the sequence length M is preserved, and project to d\_c \= 128:  
     * C\_seq: shape (B, L, M, 128\) (un-pooled positional character features).  
     * char\_mask: shape (B, L, M) (True where chars \== 0).  
     * c\_pool: gated/max-pooled projection (B, L, d\_model) added to the trunk input embedding (used by both arms).

#### **B. Fix case\_gov\_v Dead Gradient Initialization**

In Arm.\_\_init\_\_:

> * Replace nn.init.zeros\_(self.case\_gov\_v.weight) with nn.init.xavier\_uniform\_(self.case\_gov\_v.weight, gain=0.1) and a learnable scalar self.gov\_scale \= nn.Parameter(torch.tensor(0.1)) so case\_gov\_q and case\_gov\_k receive non-zero gradients from step 1\.  
> * Remove .detach() from syn\_logits and def\_logits inside h\_case\_in so case supervision helps shape syntax and definiteness representations.

#### **C. Define the Two Distinct Arm Decoders (Treatment vs. Baseline)**

> * **In Baseline (kind \== "baseline"):**  
  * **Flat Probing Decoder:** All heads (h\_proclitic, h\_enclitic, h\_stem\_tail, h\_wazan, h\_wazan\_canonical, h\_root, h\_definiteness, h\_syntax, h\_case, plus h\_surface) read the trunk hidden state h directly via flat projections, with **no** boundary character slicing, **no** wazan\_to\_root, and **no** character-slot cross-attention.  
> * **In Treatment (kind \== "treatment"):**  
  * **No h\_surface lookup table**.  
  * **Stage 1 — Boundary-Aware Affix & Tail Extraction:** Extract the prefix character state c\_prefix \= C\_seq\[:, :, :3, :\].flatten(-2) (3 \* 128 \= 384-d, first 3 chars) and suffix character state c\_suffix \= C\_seq\_right\_aligned\[:, :, \-4:, :\].flatten(-2) (4 \* 128 \= 512-d, last 4 non-pad chars of the token):  
    h\_proc\_in \= torch.cat(\[h, c\_prefix\], dim=-1)      \# d \+ 384  
    h\_tail\_in \= torch.cat(\[h, c\_suffix\], dim=-1)      \# d \+ 512  
    proclitic\_logits \= self.h\_proclitic(h\_proc\_in)  
    enclitic\_logits  \= self.h\_enclitic(h\_tail\_in)  
    stem\_tail\_logits \= self.h\_stem\_tail(h\_tail\_in)

  * **Stage 2 — Affix-Conditioned Wazān Bottleneck:** Project the predicted affix/tail logits into a dense boundary summary b\_affix \= self.affix\_to\_wazan(torch.cat(\[proclitic\_logits, stem\_tail\_logits, enclitic\_logits\], dim=-1)) (128-d), and compute the template bottleneck:  
    wh \= F.gelu(self.h\_wazan\_bottleneck(torch.cat(\[h, b\_affix\], dim=-1)))  \# (B, L, 128\)  
    wazan\_logits \= self.h\_wazan(wh)  
    wazan\_canon\_logits \= self.h\_wazan\_canonical(wh)

  * **Stage 3 — Positional Character-Slot Cross-Attention for Root Extraction (CharSlotRootHead):** Instead of predicting 4 radicals from a flat vector, instantiate 4 learnable radical slot queries self.root\_slot\_queries \= nn.Parameter(torch.randn(4, 128\) \* 0.02) conditioned on wh and h:  
    \# Q: (B, L, 4, 128\) — 4 radical slot queries conditioned on the wazan pattern bottleneck  
    Q\_slots \= self.root\_slot\_queries.view(1, 1, 4, 128\) \+ self.wazan\_to\_slot\_q(wh).view(B, L, 4, 128\)  
    \# Cross-attend from the 4 radical slots over the token's character sequence C\_seq: (B, L, M, 128\)  
    attn\_scores \= torch.einsum("blqd,blmd-\>blqm", Q\_slots, C\_seq) / (128 \*\* 0.5)  
    attn\_scores \= attn\_scores.masked\_fill(char\_mask.unsqueeze(2), \-1e4)  
    attn\_weights \= F.softmax(attn\_scores, dim=-1)  \# (B, L, 4, M)  
    slot\_char\_ctx \= torch.einsum("blqm,blmd-\>blqd", attn\_weights, C\_seq)  \# (B, L, 4, 128\)

    \# Combine character-pointed slot features with contextual trunk state h  
    slot\_hidden \= torch.cat(\[slot\_char\_ctx, h.unsqueeze(2).expand(-1, \-1, 4, \-1)\], dim=-1)  \# (B, L, 4, 384\)  
    root\_logits \= self.h\_root\_slot(F.gelu(self.root\_slot\_proj(slot\_hidden)))  \# (B, L, 4, n\_radicals)

  * **Parity:** Use treatment\_tower\_hidden (or match non-lookup parameter count) and document both total parameters and non-lookup parameters in results.json.

### **Gate 2 (CPU)**

> * Add an invariant to src/smoke\_test.py asserting that:  
  1. Zeroing C\_seq suffix positions changes stem\_tail\_logits on Treatment.  
  2. case\_gov\_q.weight.grad and case\_gov\_k.weight.grad are strictly non-zero on step 1 (proving the case\_gov\_v zero-init bug is gone).  
  3. root\_slot\_queries.grad is strictly non-zero on Treatment.

## **Task 3: Restore the Training Objective & Schedule (config/shared.yaml & src/train.py)**

### **Why Current Code Fails**

In the last run, normalise\_by\_log\_vocab: True with uniform 1.0 weights divided wazan gradients by \\ln(2100) \= 7.65 and stem\_tail gradients by \\ln(176) \= 5.17, while cutting training from 12,000 steps × batch 64 (768,000 examples) down to 3,000 steps × batch 32 (96,000 examples), crashing root accuracy from 78.4% to 13.0% and stem\_tail to 4.7%.

### **Exact Configuration (config/shared.yaml)**

loss:  
  normalise\_by\_log\_vocab: false  
  ignore\_index: \-100  
  focal\_gamma: 2.0  
  focal\_heads:  
    \- wazan  
    \- wazan\_canonical  
    \- stem\_tail  
  weights:  
    wazan: 4.0  
    wazan\_canonical: 2.0  
    stem\_tail: 2.5  
    root: 2.0  
    case: 1.5  
    syntax: 1.5  
    definiteness: 1.0  
    proclitic: 0.5  
    enclitic: 0.5  
    ntp: 0.0  
    surface: 1.0

training:  
  batch\_size: 64  
  steps: 12000  
  lr: 0.0003  
  weight\_decay: 0.01  
  grad\_clip: 1.0  
  warmup\_steps: 500  
  eval\_every: 1000  
  log\_every: 100

### **Gate 3 (CPU)**

> * Update src/make\_notebook.py so that:  
  1. It runs git diff \--exit-code config/shared.yaml (or asserts config\_sha256 matches the committed config/shared.yaml) before generating the notebook.  
  2. The preflight cell prints cfg\["loss"\] and cfg\["training"\] and asserts cfg\["loss"\]\["normalise\_by\_log\_vocab"\] is False, "stem\_tail" in cfg\["loss"\]\["focal\_heads"\], and cfg\["training"\]\["steps"\] \== 12000\.

## **Task 4: Constrained Morphological Decoding (src/final\_surface.py)**

### **Why Current Code Fails**

> 1. Independent argmax across (root, wazan, stem\_tail, case, definiteness) emits illegal root-pattern combinations where the rendered consonant skeleton (rasm) does not match the input word's consonant skeleton.  
> 2. Triliteral roots still occasionally decode with a 4th consonant if wazan predicts a 4-slot pattern or if slot-4 pad probability is mis-calibrated.

### **Exact Implementation (src/final\_surface.py)**

In decode\_rasm\_constrained(...):

> 1. Compute bare\_token \= strip\_diac(token) upfront so **zero gold diacritics** can ever be read.  
> 2. Extract top-5 roots from decode\_root\_slots\_beamed (which enforces membership in the RootTrie, both 3-radical and 4-radical), top-5 wazan stems, top-3 stem\_tail suffixes, top-3 case, and top-2 definiteness.  
> 3. **Fast Pre-Render Pruning (to keep CPU latency \< 15\\text{s} per checkpoint):**  
   * Skip any (root, wazan) pair where pattern\_arity(wazan) \!= len(root).  
   * Enforce geminate consistency: if len(root) \== 3 and root\[1\] \== root\[2\] (mudaʿʿaf/geminate root), penalize patterns lacking shadda or missing slot 3; if root\[1\] \!= root\[2\], reject 2-slot geminate-only patterns.  
> 4. Render each surviving (root, wazan, stem\_tail, case, definiteness) tuple with **rules only** (resource=False, token=bare\_token, stem\_tail=tail, definiteness=defn).  
> 5. Keep candidates whose rendered consonant skeleton matches rasm(bare\_token) (or a legal affix split of bare\_token), and pick the candidate maximizing: S(y) \= \\log P(\\text{root}) \+ \\log P(\\text{wazan}) \+ \\log P(\\text{stem\\\_tail}) \+ \\log P(\\text{case}) \+ \\log P(\\text{definiteness}) If no candidate matches the rasm, fall back to the top arity-matched beamed (root, wazan, stem\_tail, case, definiteness) and log rasm\_fallback: True.

### **Gate 4 (CPU)**

> * Run the invariance test: decode\_rasm\_constrained given gold\_form vs. strip\_diac(gold\_form) must produce **100% byte-identical outputs (A \- B \== 0\)**.  
> * Benchmark runtime on 300 gold rows: must complete in **\< 20\\text{ seconds}** on CPU.

## **Task 5: Fix the Evaluation Instrument in src/eval\_harness.py**

### **Why Current Code Fails**

As the Desktop audit proved:

> 1. stem\_tail accuracy is not reported in results.json.  
> 2. gold\_wazan\_raw was relaxed in-commit without reporting strict alongside it.  
> 3. results.json does not explicitly separate resource\_off (rules-only) vs. resource\_on (dictionary-enabled) in gold\_scored.

### **Exact Implementation (src/eval\_harness.py)**

> 1. In evaluate() (dev splits) and score\_human\_gold() (gold-300):  
   * Add "stem\_tail" accuracy: report overall\_accuracy, suffixed\_only\_accuracy (on rows where gold tail \!= ""), and constant\_bare\_baseline (58.4% on gold-300, 62.4% on PADT).  
   * Report wazan as an explicit triad:  
     * wazan\_strict\_raw: exact string match against gold tail\_strip(t\_wazan\_pattern).  
     * wazan\_mater\_canon: exact string match after canonicalize\_mater\_vowels.  
     * wazan\_radical\_slots: slot-set match (with its 0.989 constant baseline printed beside it).  
   * In score\_human\_gold(), always run and record **three** surface blocks under final\_surface:  
     * "v3\_resource\_off\_argmax": rules only (resource=False), independent argmax heads.  
     * "v3\_resource\_off\_joint": rules only (resource=False), decode\_rasm\_constrained joint decision. **(THIS IS THE PRIMARY THESIS METRIC.)**  
     * "v3\_resource\_on": hybrid dictionary selector enabled (resource=True). **(THIS IS THE PRODUCT CEILING METRIC.)**

### **Gate 5 (CPU)**

> * Run python src/eval\_harness.py \--selftest, python src/smoke\_test.py, python src/make\_notebook.py, python src/verify\_run\_code.py, and python tools/verify\_notebook\_joint.py notebooks/run-padt.ipynb. All 5 commands must exit 0\.

## **Task 6: Pre-Registered Acceptance Criteria for the GPU Run**

Before launching the Kaggle kernel (on **1x GPU T4 or P100**), register these pass/fail gates for silver-treatment (3-seed mean on gold-300 and padt\_dev):

| Metric | Previous (results.json / Latest Audit) | Pre-Registered Pass Bar | What It Proves |
| :---- | :---- | :---- | :---- |
| **gold-300 Root Whole (Beamed)** | 13.0% (3k steps) / 78.4% (12k steps) | **\\ge 79.0\\%** (treatment \> baseline by \> 2\\cdot\\text{sd}) | CharSlotRootHead \+ restored 12k budget beats flat baseline |
| **gold-300 stem\_tail (Suffixed Rows Only)** | 4.7% (5/106) | **\\ge 60.0\\%** on suffixed rows | Boundary character slicing \+ focal loss \+ clean union inventory works |
| **gold-300 wazan\_mater\_canon** | 18.4% (raw) | **\\ge 48.0\\%** | Affix-conditioned wazan \+ mater canonicalization learns templates |
| **padt\_dev Case Macro-F1** | 0.459 | **\> 0.620** | Non-zero case\_gov\_v init \+ gold batch interleaving \+ 1.5 weight works |
| **gold-300 End-to-End (v3\_resource\_off\_joint)** | 2.8%–6.7% | **\\ge 35.0\\%** (rules-only, zero dictionary\!) | **Proves the core thesis:** compositional neural plan \+ deterministic rules works without dictionary lookup |
| **gold-300 End-to-End (v3\_resource\_on)** | 66.9%–69.3% | **\\ge 75.0\\%** | Hybrid system ceiling improves with better case & stem\_tail predictions |

