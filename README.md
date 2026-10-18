# arabic-root-tree — research peak snapshot

A frozen snapshot of the `arabic-root-tree` research pipeline, taken 2026-10-17 at the point where it
was most complete, immediately before the project changed direction from a research artefact into a
production backend for a mobile app.

- **Source commit:** `e38160e` — *"feat: add semantic binder, Nahw verifier, pedagogy modules, and
  mutation tests"* (2026-10-17 12:12)
- **Contents:** 137 files — source, configs, tools, tests, docs, results
- **Not included:** corpora, model weights, any derived data. See [WHATS-EXCLUDED.md](WHATS-EXCLUDED.md)

The corpora that make this tree runnable cannot be redistributed. Reproducibility here is preserved by
sha256 pin, not by shipping bytes.

---

## What it is

A neuro-symbolic Arabic analysis engine with **no free-form generation**. A small transformer planner
emits structured decisions — root, wazān (وزن), clitics, case, definiteness, stem/tail — and a
deterministic compiler renders the vocalised surface from those decisions. A grammar sandbox judges
mutated sentences instead of producing text, so it can say *why* a sentence is wrong.

Design documents: [docs/v12-architecture.md](docs/v12-architecture.md),
[docs/SPEC-REV6.md](docs/SPEC-REV6.md) (authoritative), [APP_VISION_AND_METHOD.md](APP_VISION_AND_METHOD.md).

| Property | Value |
|---|---|
| Parameters | 14,206,128 (unified arm) · 9,213,417 (legacy arm, the exported one) |
| INT8 ONNX artifact | 9,712,240 B |
| CPU latency | p50 3.2 ms · p95 6.2 ms · p99 6.6 ms (285 rps) |
| Corpora needed to run | none for `demo.py`; corpora are excluded from this repo |

The point of the size is portability: the model is small enough to run on a phone CPU, and every
output is either rendered by rules or refused.

---

## Measured gates at this snapshot

| Gate | What was measured | Measured | Bar | Status |
|---|---|---|---|---|
| G1a | Oracle compiler — consonant skeleton, `resource=OFF` | 97.49% (272/279) | ≥98.0% | **FAIL** |
| G1b · templatic | Oracle compiler — token-exact, over the **279** rows carrying a gold (root, wazān) triple | 63.8% (178/279) | ≥60.0% v1 · ≥70.0% research | **PASS v1 · FAIL research** |
| G1b · all-rows | Same compiler, with the **21** unattempted non-templatic rows counted as 0 | 59.3% (178/300) | ≥60.0% | **FAIL** — 2 rows short |
| G4 | Case macro-F1 | 0.602 gold-300 · 0.804 PADT dev | research metric | — |
| G6 | 3-tier cascade, token-exact on covered tokens | 24.1% (63/261), coverage 87.0%, 39 abstain | v1 0.200 (owner) | PASS on the v1 bar |
| G7 | Counterfactual Naḥw verifier | 100/100 minimal pairs | 100/100 | PASS |
| G8 | Diacritic-sensitive role binding | 100% | 100% | PASS |
| G9 | A−B invariance | 0 mismatches / 300 rows | 0 | PASS |
| D6 | Licence gate over the served closure | **0 violations / 14 modules / 128 imports** | 0 | **PASS** |

**G1a misses its research bar, and G1b now clears the 60.0 v1 bar only on templatic rows.** Neither
reaches the research bars (≥98.0% / ≥70.0%), which is why the direction changed. The v1 bars for G1b
(0.600) and G6 (0.200) were set lower than the research bars by an explicit owner decision on
2026-10-18; the research bars remain in the record and remain unmet. G1b's scope is stated in its key
on purpose: `0.638` is always `178/279 templatic`, and the all-rows figure is always shown beside it.

G6 and D6 were measured **after** this snapshot, on the production line of work — their code is not
part of this tree, and they are listed here so the peak numbers are not read without them.

## Per-head results on the frozen human gold set (300 rows)

| Head | Gold-treatment arm | Silver-treatment arm |
|---|---|---|
| Root | **51.6%** (144/300) | 74.2–76.3% (207–213/300) |
| Wazān | **29.7%** (83/300) | 48.4–49.5% (135–138/300) |
| Case macro-F1 | **0.602** | 0.462–0.490 |
| Stem + tail, all | 81.0% | 78.1% |
| Stem + tail, suffixed only | **54.5%** | 42.9% |

The constant-bare baseline for stem+tail is **72.4%**, so the gold arm beats "always predict the bare
form" by 8.6 points overall and loses by 18 points on suffixed tokens.

---

## What changed after the peak

Three results belong here because they re-frame the numbers above.

1. **60.4% was an oracle number.** `render_triple` reached it while being handed the *gold* root and
   pattern. A 3-tier cascade (lexicon → neural → abstain) that must predict them gets 24.1% exact on
   the 87% of tokens it answers. Against an argmax-triple baseline measured on the same 300 rows
   (11.3%, 34/300) that is roughly 2×, and still nowhere near the oracle.
2. **A licence gate found a real breach, and then closed it.** A gate written after this snapshot (it
   lives in the production repository, not in this tree) walks every module the server can reach. It
   first reported `modules=17 imports=194 violations=87 exit=1`; one violation was substantive: the
   serving path loaded an 8.4 MB Tashkeela-derived index (GPL-2.0) by default. That branch and its data
   file were removed, the eval-only surface was unbundled, and the gate now reports
   **`modules=14 imports=128 violations=0 exit=0`**.
3. **Two more data files failed inspection.** `dia2_arwiki_spelling_index` is CC-BY-SA-4.0
   (share-alike) and `dia2plus_arwiki_morph` carries no licence field at all. Both were quarantined
   outside the production data directory. Neither is read by the served code.

## Honest comparison

On the identical 279 tokens, CAMeL Tools' CALIMA analyser gets top-1 root **84.9%** (237/279) and
95.3% on any analysis. That beats both arms of this model. The bet here was never raw root accuracy;
it is a licensed, portable, explainable, abstaining parser. Note also that `builtin_db()` ships CALIMA
data, which is not covered by camel_tools' MIT grant — the thing that wins may not be shippable.

## Known defects in this snapshot

Recorded, not fixed. Both reproduce with `python demo.py`, which needs no corpus.

1. **Semantic binder: the Indonesian translation ignores the role flip.** For `ضَرَبَ زَيْدًا عَمْرٌ`
   the roles bind correctly and the English is right ("It was Zayd whom 'Amr struck"), but the
   Indonesian string still says *"Zaid-lah yang memukul 'Amr"* — it asserts the wrong striker.
2. **Renderer: hollow-root surface gap.** `مُحْتَاج` (root ح.و.ج) traces to `مُحْتَوَج`; the weak-radical
   elision that should yield `مُحْتَاج` never fires on this path.

## Licence status

First-party code. It depends on two external works, neither included here:

- `camel_morph` — MIT code, CC BY 4.0 data (the shippable lexicon path)
- `camel_tools` — MIT

No GPL, no CC BY-NC-SA and no CC BY-SA material is present in this repository. That was verified by
path and by archive inspection, not assumed. This snapshot carries **no `data/` directory at all** —
no corpora, no derived dictionaries, no lexicon.

## Run it

```bash
python demo.py     # standard library only: compiler, iʿlāl trace, mīzān, iʿrāb card,
                   # Naḥw sandbox, semantic binder — six sections, all deterministic
```

## Layout

```
src/        model arms, renderer/compiler, pedagogy, Nahw verifier, semantic binder, training
tools/      measurement scripts — every number above is reproducible from one of these
tests/      sandbox mutation suite (G7/G8)
config/     shared.yaml — both arms read one config
docs/       specifications and architecture
results/    results.json — per-seed metrics, gold-300 scoring, ceilings, parity
```

## How to read these numbers

Denominators differ on purpose and must not be mixed: 279 tokens are scorable for the consonant
skeleton, 280 for token-exact vocalisation, 300 for the human gold rows, and 261 for the cascade's
covered tokens. A percentage without its denominator is not a result. When a number in this repo
changes, the command that produced it is in `tools/`; run it again before quoting it.
