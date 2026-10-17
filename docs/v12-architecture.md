# v12 Architecture — Character-Level Input + Hierarchical Conditioning + Constrained Decoding

**Date**: 2026-10-10  
**Status**: Design  
**Target**: Close the OOV root cliff (0.000 on 141 OOV rows) and reduce error multiplication in end-to-end surface recovery (~1%)

## Problem Statement

v11 established that the treatment wins on morphology (+0.071 in-domain root, +0.046 OOD root), but three bottlenecks remain:

1. **OOV cliff**: 0.000 root recovery on 141 OOV rows — the model is a lookup table, not a morphological analyzer
2. **Error multiplication**: ~1% end-to-end surface = 0.168 × 0.265 × 0.400 ≈ 0.018 — independent heads multiply errors
3. **Case ceiling**: 0.459 macro-F1 is CALIMA's ceiling, not the model's — pushing case on silver data is bounded by the silver labeler

## Three Architectural Changes

### 1. Character-Level Input Encoding

**Problem**: Word-level embeddings (`nn.Embedding(sizes["surface"], d)`) map OOV tokens to `<unk>`, so the model has no morphological signal for unseen words.

**Solution**: Supplement word embeddings with a character-level CNN that encodes the consonantal skeleton of each token.

**Implementation**:
- Input: character indices (Arabic letters + diacritics stripped)
- Character embedding table: `nn.Embedding(n_chars, char_dim)`
- Character CNN: 1D convolutions with multiple kernel sizes (3, 5, 7) to capture n-gram patterns
- Output: fixed-size character vector per token (max-pool over sequence length)
- Combine: `token_repr = word_emb + char_cnn(char_indices)`

**Why this helps**: Arabic morphology is compositional — the surface form contains the literal consonants of the root interspersed with augmentative letters (hurūf al-ziyādah). A character-level representation allows the model to see the consonantal skeleton directly, preventing OOV tokens from mapping to an uninformative unigram vector.

### 2. Hierarchical Head Conditioning (Wazān → Root)

**Problem**: Root slots and wazān are predicted as completely disjoint parallel heads. Their errors multiply: P(exact surface) ≤ P(root) × P(wazān) × P(case).

**Solution**: Predict wazān first, then feed the wazān embedding as conditioning context into the radical slot decoders.

**Implementation**:
- Forward pass:
  1. Compute wazān logits: `wazan_logits = h_wazan(h)`
  2. Sample or argmax the wazān prediction: `wazan_pred = argmax(wazan_logits)`
  3. Embed the predicted wazān: `wazan_emb = wazan_embedding(wazan_pred)`
  4. Condition root slots on wazān: `root_logits = h_root(h + wazan_emb)`
- Training: use teacher forcing (gold wazān) during training, predicted wazān during inference

**Why this helps**: The wazān is a structural blueprint. If the model knows the pattern is اسْتَفْعَلَ (Form X), the search space for where the three root radicals can physically exist in the token collapses to the exact slots defined by the template. Conditioning breaks the independence assumption and stops the error multiplication.

### 3. Constrained Root Decoding

**Problem**: Unconstrained slot argmax predictions frequently emit non-existent roots (illegal trios).

**Solution**: Project the decoded radical slots onto the valid root inventory using a valid-root mask.

**Implementation**:
- Build a valid-root inventory from training data: `valid_roots = set(all roots in training)`
- At inference time:
  1. Decode slot argmax: `slots = argmax(root_logits)`
  2. Convert to root string: `root_str = decode_root_slots(slots, pattern, inv_r)`
  3. If `root_str` not in `valid_roots`, project onto nearest valid root:
     - Option A: Beam search over slot logits, constrained to valid roots
     - Option B: Trie-based constraint (valid root prefixes)
     - Option C: Simple fallback — if decoded root is invalid, return `<unk>` and let the renderer abstain

**Why this helps**: Filtering slot logits against a static trie of valid Arabic roots forces the output to be linguistically legal before it ever reaches the renderer.

## Implementation Plan

### Phase 1: Character-Level Input (v12a)
- Add `CharEncoder` module to `model_arms.py`
- Modify `Arm.__init__` to include character encoder
- Modify `make_batch` to include character indices in the batch
- Update `Vocabs` to include character vocabulary
- Smoke test: verify character encoder produces valid representations

### Phase 2: Hierarchical Conditioning (v12b)
- Modify `Arm.forward` to predict wazān first, then condition root on wazān
- Add wazān embedding table
- Update training loop to use teacher forcing during training
- Smoke test: verify conditioning improves root accuracy on in-domain dev

### Phase 3: Constrained Decoding (v12c)
- Build valid-root inventory from training data
- Modify `final_surface.decode_root_slots` to check against valid roots
- Add fallback logic for invalid roots
- Smoke test: verify constrained decoding reduces invalid root predictions

### Phase 4: Full v12 Run
- Regenerate notebook with v12 architecture
- Run on Kaggle with same config as v11 (120k tokens per source, 3 seeds)
- Compare against v11 numbers:
  - OOV root recovery (target: > 0.000)
  - In-domain root whole (target: ≥ 0.585)
  - OOD root whole (target: ≥ 0.165)
  - End-to-end surface (target: > 0.01)

## Risk Assessment

1. **Character encoder may not help**: If the character-level signal is too noisy, it could hurt performance. Mitigation: start with a simple CNN, measure impact before adding complexity.

2. **Hierarchical conditioning may break parity**: Adding wazān conditioning changes the treatment arm's parameter count. Mitigation: re-run `--fit-parity` to maintain the 1% tolerance.

3. **Constrained decoding may reduce coverage**: If many decoded roots are invalid, the renderer will abstain more often. Mitigation: measure coverage before and after; if it drops below 95%, relax the constraint.

## Success Criteria

v12 is successful if:
1. OOV root recovery > 0.100 (currently 0.000)
2. In-domain root whole ≥ 0.585 (v11 baseline)
3. OOD root whole ≥ 0.165 (v11 baseline)
4. End-to-end surface > 0.01 (currently ~0.01)
5. Parity maintained within 1% tolerance

If v12 fails to meet these criteria, we revert to v11 and investigate alternative approaches (e.g., data augmentation, larger model, different optimizer).
