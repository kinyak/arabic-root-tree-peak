Your doc lists many challenges, so I'll answer the one it calls the fork (A1 + A2, the latent graph and order-free decoding), since the other fixes depend on it. Then I'll give short fixes for the rest.

## Core idea: stop treating the graph as latent, and make surface order the plan order

**Why A1 dissolves.** You only have a differentiable-graph problem if the graph is something the model must *discover*. But your data are treebanks, so the graph is **observed**. Train with plain teacher forcing and put no latent variable in the loss. The "graph" becomes extra supervised fields on each token, not a structure to be marginalised over.

**Why A2 dissolves.** Your own A2 argues that Arabic word order is grammatically load-bearing (verbal vs. nominal, fronting). So don't fight it. Drop "order-free." Use the **surface word order as the canonical linearisation** of the plan. Order is no longer something the renderer must reinvent, because the plan already carries it.

The model is then an ordinary autoregressive model whose "token" is a **structured tuple**, emitted left to right:

`(root_id, wazān_id, suffix/clitic features, role, head_offset, case)`

- The loss is a sum of per-head cross-entropies over the tuple, with the tuple fed back as input via the sum of its field embeddings.
- `head_offset` is a **pointer to an already-emitted token** (relative distance back), so it stays causal. For heads that come later in the sentence (nominal sentences, fronted predicates), use a "defer" label and attach on the later token, so the arc is always created when the dependent or the head arrives second. This is essentially the arc-standard idea restated as a tagging task, and it needs no RL, no Gumbel, and no marginalisation.
- Inference samples discrete tuples, so the deterministic renderer consumes them directly. This also fixes the "soft graph can't be rendered" objection.

What you lose is the "order-free planning" headline. What you gain is a paper you can finish, and the claim becomes "grammar-factored generation," which is cleaner and testable.

## Making the arms comparable (A3, the biggest validity threat)

Score both arms on **final surface output through one analyser**:

1. Generate N sentences from each arm, run them through the same CAMeL analyser, and compare root, wazān, case, and i'rāb accuracy using identical code.
2. Add a surface-level likelihood number both arms share: **bits per character on held-out text**. For the treatment, use the tuple likelihood of the gold analysis, valid when the renderer is deterministic. Report that this is a lower bound on the marginal if several tuples render to the same string.
3. Add a **grammaticality probe**: minimal pairs (correct vs. wrong case or agreement), asking which arm assigns higher likelihood. This is the strongest evidence for the grammar claim and is cheap to build.

## Fixes for the other items

| Item | Proposed fix |
|---|---|
| A4 (Head 5 ≈ f(Head 4)) | Keep both, but run an ablation that predicts case with and without role as input. Report only the *residual* gain of Head 5, plus accuracy on the cases where role doesn't determine case (e.g., after particles like إنّ or prepositions). |
| A5 (renderer) | Use CAMeL's generator and say so plainly. Your claim is the representation and planning. Also report an "oracle renderer" upper bound (gold tuples → surface) so renderer errors can't be confused with model errors. |
| A6 (tensor vs. table) | Drop the 28³ tensor. Use a flat root table, and make each root embedding = table row + sum of three radical embeddings. The radical part gives OOV and rare roots a useful vector and keeps whatever morphological similarity exists. Mask nothing. |
| A7 (loss weights) | Start with per-head loss divided by log(vocab size), so each head begins at roughly the same scale. If you want something principled, use Kendall-style learned uncertainty weights, and fix the weights in the shared config for both arms. |
| A8 (conflicting treebanks) | Write a precedence table: one row per field, listing which source wins and the fallback. Add a **source-ID embedding** or a source-ID-conditional head so the model can absorb source artefacts instead of reporting them as grammar. Evaluate with the source set to a neutral token. |
| A9 (eval contamination) | Use **leave-one-genre-out**: e.g., train on Quranic and MSA news, test on a hand-checked sample of a different genre such as hadith or modern prose. Even 300–500 hand-verified sentences are enough for a convincing OOD set. Exclude any CALIMA-silver data from anything near the test distribution. |
| A10 (thin syntax data) | Put morphology in the headline and syntax in an ablation, as you already suggest. With the design above this is trivial: train a variant with the `role` and `head_offset` fields masked. |
| A11 (`meaning`) | Dictionary lookup keyed on the lemma (arramooz or EQTB). Make it an explicit post-render step, not a model output. |
| A12 (GBNF) | Rename it "delivery schema" in the write-up. Use a proper JSON string rule with escapes, or skip GBNF and validate the output with a JSON schema. Constrained decoding applies only to the *tuple vocabulary* (e.g., masking invalid root/wazān pairs at inference), which is the genuinely interesting use. |

## Minimal v1 experiment

- **Baseline arm:** surface-character or BPE LM, matched parameter count.
- **Treatment arm:** structured-tuple LM, same config file.
- **Treatment ablations:** (a) no syntax fields, (b) no wazān field, (c) no case head.
- **Metrics:** surface-analyser root/wazān/case accuracy, bits per character, minimal-pair accuracy, and OOD genre results. Pre-register all of these.

If you want, I can turn this into the harmonisation/precedence spec (item 4) or the eval-harness skeleton (item 8), since everything else depends on those two.
