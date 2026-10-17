# What is excluded from this snapshot, and why

Two independent reasons: **licence** (may not be redistributed) and **platform** (GitHub rejects any
file over 100 MB). The excluded material is required to *run* the pipeline and to *re-measure* the
gates; it is not required to *read* the method or the results.

| Excluded | Size | Licence | Reason |
|---|---:|---|---|
| `bundle/data/out/spread-B-2m/tashkeela-train.jsonl` | **1005.4 MB** | GPL-2.0 | licence **and** >100 MB |
| `bundle/data/out/padt-train.jsonl` | **114.3 MB** | CC BY-NC-SA 4.0 | licence **and** >100 MB |
| `bundle/data/out/padt-dev.jsonl`, `padt-test.jsonl` | 15–16 MB each | CC BY-NC-SA 4.0 | licence |
| `bundle/data/out/spread-B-2m/tashkeela-{dev,test}.jsonl` | 61–79 MB | GPL-2.0 | licence |
| `data/annotation/gold-tashkeela-300.jsonl` | 172 KB | derived from GPL-2.0 text | licence |
| `data/annotation/` (annotation sheets, filled CSVs) | ~1 MB | derived from the above | licence |
| `checkpoints/*.pt` (13 files) | 549 MB total | weights trained on CC BY-NC-SA + GPL data | licence + size |
| `build/arabic_brain_v1/model.onnx` | 9.7 MB | same derivation question | licence |

### The trap this snapshot avoided

`arabic-root-tree-model-core.zip` (12.9 MB) looked like a harmless code archive, but **contained
`padt-dev.jsonl`, `padt-test.jsonl` and `gold-tashkeela-300.jsonl` inside it**. Any path-based
exclusion (`bundle/`, `checkpoints/`, `data/`) would have published CC BY-NC-SA and GPL-2.0 text while
appearing clean. It was removed, and the snapshot was then re-checked for residual corpora: zero
`.jsonl` files remain.

## Reproducing the excluded material

1. **Tashkeela** (GPL-2.0) — obtain from the upstream release and build with
   `tools/build_training_jsonl.py --source tashkeela`, sampler `mode=spread seed=0`. The approved build
   is pinned in `config/shared.yaml` by sha256 for train/dev/test.
2. **PADT** (CC BY-NC-SA 4.0) — obtain from the Universal Dependencies release. Local-only evaluation
   ruler; may not be redistributed or used commercially.
3. **Human gold-300** — regenerate from the annotation protocol in `docs/ANNOTATION-PROTOCOL.md`. The
   canonical file's sha256 is
   `edcdc2eecaaca1ff735f9ec2219d1bf2cfcb1075bfde97ce0a4c0fbc982ba40d`; any regenerated copy that does
   not match this hash is not the ruler the published numbers were measured on.
4. **Checkpoints** — retrain with `src/train.py` (see `COLAB.md` / `notebooks/` in the private repo).
   The published metrics are per-seed in `results/results.json`.

## Note on the checkpoints

The weights are the single most licence-sensitive artefact here: they are derived from corpora that
are GPL-2.0 (Tashkeela) and CC BY-NC-SA (PADT). That makes their redistribution a legal question, not
a packaging one — which is why the production direction moved to a `camel_morph`-only (CC BY 4.0) data
chain before anything is shipped.
