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

| Gate | Metric | Value | Bar | Status |
|---|---|---|---|---|
| G1a | Oracle compiler — consonant skeleton (`resource=OFF`) | 97.49% (272/279) | ≥98.0% | **FAIL** — open |
| G1b | Oracle compiler — vocalized token-exact | 60.4% (169/280) | ≥70.0% | **FAIL** — open |
| G4 | Case macro-F1 | 0.804 PADT dev / 0.602 gold-300 | research metric, no production bar | — |
| G7 | Counterfactual Naḥw verifier | 100/100 minimal pairs | 100/100 | PASS |
| G8 | Diacritic-sensitive role binding | 100% | 100% | PASS |
| G6 † | Clean 3-tier cascade — token-exact on covered tokens | 24.1% (63/261), coverage 87.0%, 39 abstain | research metric | — |
| D6 † | Licence gate over the served closure | **87 violations / 17 modules** | 0 | **FAIL** — open |

† measured after the peak, on the production line of work; see the next section.

Those numbers are the honest peak and the honest ceiling: **G1a and G1b are the two the project never
met** — each misses its bar, not merely the round number — which is precisely why the direction
changed. Full evidence and the correction history live in `EVIDENCE_LOG.md`,
`ENGINE_PRODUCTION_PLAN.md` §3, and `results/results.json`.

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

## What changed after the peak (measured, not claimed)

The code carried on past this snapshot as the backend for a mobile app. Three results belong in the
record because they re-frame the numbers above:

1. **The 60.4% was an oracle number.** A 3-tier decision cascade (lexicon → neural → abstain) was
   built on top of the compiler. On the same frozen gold-300 set it covers 87.0% of tokens
   (39 abstain) and is token-exact on **24.1% (63/261)** of what it answers. Against an argmax-triple
   baseline measured on the same 300 rows — **11.3% (34/300)** — that is ~2×, but far from 60.4%.
   The gap is not a regression: `render_triple` reached 60.4% by being handed the *gold* root and
   pattern. A pipeline that must predict them cannot inherit that.
2. **The licence gate found a real breach.** `tools/licence_gate.py` walks the served closure and
   reported `modules=17 imports=194 violations=87 exit=1`. One violation was substantive: the serving
   path loaded an **8.4 MB Tashkeela-derived index (GPL-2.0) by default** through
   `final_surface.apply_spelling_resource`. That branch and its data file have been removed from the
   served path; D6 stays **FAIL** until the remaining 87 (comments, path constants, eval-only helpers
   reachable through two deferred imports) are unbundled.
3. **Two more data files failed inspection.** `dia2_arwiki_spelling_index` is **CC-BY-SA-4.0**
   (share-alike) and `dia2plus_arwiki_morph` carries **no licence field at all**. Both were
   quarantined outside the production data directory. Neither is read by the served code.

The production lexicon remains clean: `morph_lexicon.sqlite` is built from `camel_morph` MSA v1.0
(CC BY 4.0 data, MIT code), with the source database hash recorded in its manifest.

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

## Provenance note

`data/weak_radical_dict.json` and `data/closed_class_inventory.json` were **removed before
publication**: both were derived from CALIMA/PADT rows (`calima_root` keys, `"built_from": "PADT
train"` headers), so shipping them would have distributed encumbered material. `WHATS-EXCLUDED.md`
records them with their licence, size and hash. This snapshot carries **no `data/` directory at all**
— no corpora, no derived dictionaries, no lexicon. `demo.py` runs the compiler, the iʿlāl trace, the
mīzān, the iʿrāb card, the Naḥw sandbox and the semantic binder on built-in examples only.
