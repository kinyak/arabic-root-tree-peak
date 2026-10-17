# arabic-root-tree — RESEARCH PEAK SNAPSHOT

This repository is a **frozen snapshot** of `arabic-root-tree` at the state where the research
pipeline was most complete — taken 2026-10-17, immediately before the project changed direction from
a research artefact to a commercial production backend for a mobile app.

**Source commit:** `e38160e` — *"feat: add semantic binder, Nahw verifier, pedagogy modules, and
mutation tests"* (2026-10-17 12:12)
**Snapshot contents:** 176 files, ~6.4 MB — source, configs, tools, tests, docs, results.

It is deliberately **not** a runnable data bundle. The corpora that make it runnable are licensed in
ways that forbid redistribution; see `WHATS-EXCLUDED.md`. Reproducibility is preserved by sha256 pin,
not by shipping the bytes.

---

## What was achieved at this point

The project built a neuro-symbolic Arabic analysis engine with **zero free-form generation**: a small
transformer planner producing structured decisions (root, wazān, clitics, case, dependency) plus a
deterministic compiler that renders vocalized surface forms and a deterministic grammar sandbox that
judges mutations rather than generating text.

Measured on the frozen human gold-300 set and PADT dev at this commit:

| Gate | Metric | Value |
|---|---|---|
| G1a | Oracle compiler — consonant skeleton (`resource=OFF`) | **97.49%** (272/279) |
| G1b | Oracle compiler — vocalized token-exact | **60.4%** (169/280) |
| G4 | Case macro-F1 | **0.804** PADT dev / **0.602** gold-300 |
| G7 | Counterfactual Naḥw verifier | **100/100** minimal pairs |
| G8 | Diacritic-sensitive role binding | **100%** |

Those numbers are the honest peak and the honest ceiling: G1a and G1b are the two the project never
closed, which is precisely why the direction changed. Full evidence and the correction history live in
`EVIDENCE_LOG.md`, `ENGINE_PRODUCTION_PLAN.md` §3, and `results/results.json`.

## Why this snapshot exists

Once the repository became a production codebase — export pipeline, decision cascade, HTTP service —
its history stopped being a clean description of the research. This snapshot preserves the research
state as its own artifact: same code, same measurements, no production work in front of it.

## Layout

```
src/            model arms, renderer/compiler, pedagogy, Nahw verifier, semantic binder, training
tools/          measurement scripts — every number above is reproducible from one of these
tests/          sandbox mutation suite (G7/G8)
config/         shared.yaml — both arms read one config
docs/           specifications, reviews, annotation protocol
results/        results.json — per-seed metrics, ceilings, parity
```

## Known defects found while preparing this snapshot

Recorded, not fixed — this is a frozen state, and a research artefact that hides its defects is
worth less than one that names them. Both were reproduced with `python demo.py`, which needs no corpus.

1. **Semantic binder: Indonesian translation does not follow the role flip.** For
   `ضَرَبَ زَيْدًا عَمْرٌ` the roles are correctly bound (`AGENT = عَمْرٌ`, `PATIENT = زَيْدًا`) and the
   English is correct ("It was Zayd whom 'Amr struck"), but the Indonesian string still reads
   *"Zaid-lah yang memukul 'Amr"* — i.e. still asserts Zaid as the striker. The English path
   re-renders from the bound roles; the Indonesian path does not. Any app showing both languages
   would teach the wrong reading on exactly the sentence the binder exists to disambiguate.
2. **Renderer: hollow-root surface gap.** `مُحْتَاج` (root ح.و.ج, pattern مُ1ْتَ2َ3) traces to
   `مُحْتَوَج` and stops there; the weak-radical elision that should give `مُحْتَاج` never fires on
   this path. The trace is honest about each step, which is how the gap was found — but the surface
   is wrong.

## Licence status

Code in this snapshot is first-party. It depends on two external works, **neither included here**:

- `camel_morph` — **MIT code / CC BY 4.0 data** (the shippable lexicon path)
- `camel_tools` — **MIT**

No GPL, no CC BY-NC-SA, and no CC BY-SA material is present in this repository. That was verified by
path and by archive inspection, not assumed — see `WHATS-EXCLUDED.md`.

## Known provenance to confirm before commercial redistribution

`data/weak_radical_dict.json` (614 KB) and `data/closed_class_inventory.json` (1 MB) are derived
dictionaries whose upstream provenance should be re-verified against
`docs/LICENCE-AUDIT-LEXICON.md` before they are reused in a shipped product. They are included as
research artefacts, not as licensed shippable resources.
