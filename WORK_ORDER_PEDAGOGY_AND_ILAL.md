# WORK ORDER — PEDAGOGY LAYER + IʿLĀL TRACE (CPU ONLY), LEXICON GATED BEHIND A LICENCE AUDIT

**Author:** Hermes (Buddy) · **Date:** 2026-10-16 · **Product intent:** SHIPPING — the licence chain binds.
**Tree:** `G:\arabic-root-tree`, HEAD `89d9a60` (2026-10-15), **working tree DIRTY: 10 modified + 3 untracked (`bundle/`, `checkpoints/`, `.agents/`)** — a concurrent agent (Antigravity) holds `src/` edits. Work additively; do not revert, re-commit or re-pin anything that agent holds.

## 0. HARD RULES BEFORE TOUCHING CODE

> 1. **ZERO GPU SPEND.** Every task in this order is CPU-only. No notebook, no kernel, no Colab.
> 2. **The six gates must exit 0 before and after every task.** Pins, in one place:
>    `python src/final_surface.py --selftest` → 46/46, exit 0 · `python src/smoke_test.py` → exit 0 ·
>    `python tools/stem_tail_audit.py --check` → exit 0 · `python tools/hollow_probe.py --check` → exit 0
>    (frozen ruler **614/973 = 63.1%**, hollow 47/100) · `python tools/diacritic_split.py --check` → exit 0
>    (stem 532/614) · `python tools/tanwin_probe.py --check` → exit 0 (net **−143**).
>    **A red gate is a STOP, never a warning.**
> 3. **Never quote `resource_on` as evidence about the neural planner.** Every reported figure logs `resource_off` (thesis metric) and `resource_on` (hybrid product ceiling) side by side, and names its **instrument and denominator** — `gold-300` (300 rows / 278 usable) and the frozen `ruler` (973) are not interchangeable.
> 4. **A number whose licence forbids distribution is not a product number** (ACTIVE_BACKLOG §7). This repo is now a product.
> 5. **No hand-entered thresholds, ever** (§2). No claim in a lesson card that is not backed by a candidate + score, or explicitly abstained (§8).
> 6. **Do not touch:** `src/model_arms.py`, `src/train.py`, `src/wazan_normalizer.py`, `src/eval_harness.py`, `notebooks/run-padt.ipynb`, `results/*` — all carry the other agent's uncommitted edits. Tasks A and B are read-only against them.

### 0.1 Numbers from the relayed roadmap that are STALE — do not inherit them

| Claim in the relayed doc | Artifact |
|---|---|
| "9.2M-parameter Treatment model", "36 MB FP32 → 9.5 MB INT8" | `results.json.parity` = treatment **9,213,417** / baseline **14,459,375**, gap **36.3%**, tolerance 1%, `exact_match: false` — the **abolished fitted-parity** arm. Live architecture: **16,727,400 / 16,727,402** = 0.0000% (§2db §6). INT8 ≈ 16.7 MB, FP32 ≈ 67 MB. |
| "`v.wazan` 2,183 classes → ~1,400" | Same stale block (`vocab_sizes`: wazan 2183, stem_tail 153). Live: **6,633** wazān types (round 26) / **4,255** classes in the grid tree (§2db §3, where canonicalisation renamed 1,194 of them); stem_tail **176** since §2cz. |
| "12-model grid = 7.5 h → one run = 33 min" | `tools/verified_runs.json` v14: 3-seed grid, 12 runs, **3,550 s = 59 min**. The saving is ~1.8×, not 12×. |
| "72.7% ceiling, fixed by a `(root, wazān)`-indexed lexicon, +17–20 pts" | 72.7% **is** the `resource_on` number, and §2cd measured **C == D** — TSV-only == shipped; the rules add **0.000** where the TSV speaks. `resource_on` misses on 300 rows: **diacritic_only 76, tanwin_missing 8**. A root/wazān column touches neither; tanwīn is invisible in undiacritized input (§2ce: **25 rows = 9.0%** of gold-300 that no compiler can reach). No mechanism exists for the claimed jump. |
| "τ = 0.45" | §2 forbids hand-entered thresholds and rules that a structural abstention stays **FINAL**, never re-scored as confidence. |
| "case 0.789–0.804 / 0.602 proves the architecture" | Every case row in `results.json.summary` is **NOT SEPARATED**, and gold-**baseline** in-domain is **0.7932** vs gold-treatment **0.7891**. Case is a **label-source** effect (CALIMA ceiling **0.459**), not a treatment win. |

## TASK A — A PASSIVE STEP TRACE THROUGH THE RENDERER (instrumentation only, zero behaviour change)

**Why.** The relayed doc's best feature — "log the intermediate string before and after each phonological rule" — **assumes instrumentation that does not exist**: `src/render_rules.py` and `src/renderer.py` carry **no `trace` / `history` hook** (verified). The pipeline is layered (`canonicalize_mater_vowels` → `render_*` → `apply_case` → `attach_affix_plane` → repairs → `spelling_resource`), so this is new plumbing, not a 300-line mapper.

**Do.**
1. Add an **opt-in, default-off** trace sink (a `trace: list[dict] | None = None` parameter threaded through the render path, plus `ARABIC_TRACE=1` for the CLI). Each entry: `{stage, rule_id, before, after, changed: bool}`. `rule_id` names the actual clause (`iltiqāʾ al-sākinayn` / `canonicalize_mater_vowels` / `apply_case` / `attach_affix_plane` / `repair:<name>`), never a generic label.
2. **The trace must be provably passive.** With the sink ON vs OFF: **0 changed rows** on the frozen ruler (973) and on `gold-300`; renderer stays **614/973**; all six gates exit 0.
3. **Affix-plane invariance** must survive the trace: output identical for a vocalized and an undiacritized token (§2ce pinned 0 of 1278 rows differ). The trace may never read the gold token's diacritics.
4. Ship `tools/trace_render.py` — CLI: `python tools/trace_render.py --token قُلْتُ --root قول --wazan 1ُ2ْ3` prints the step chain and writes `dist/pedagogy/trace-pins.json`.

**Acceptance.** (a) six gates 0; (b) 0 changed rows on both instruments; (c) `قُلْتُ` prints an honest chain: root `ق و ل` (ajwaf wāwī) → underlying `قَوَلْتُ` → **iʿlāl bil-ḥadhf** (wāw dropped for *iltiqāʾ al-sākinayn*) → `قُلْتُ`; (d) `مُحْتَاج` → root `ح و ج` → `مُ1ْتَ2َ3` Form VIII → `مُحْتَاج` with no invented step.

**Do not:** change any rule, threshold, or output while instrumenting. A trace that moves a pinned number is a defect, not a feature.

## TASK B — `src/pedagogy.py` (deterministic, zero ML, ship-safe)

**B1 — Mīzān ṣarfī converter.** Slot digits `1 2 3 4` → `ف ع ل ل` (`مُ1ْتَ2َ3` → `مُفْتَعَل`), table-driven, returns `(mīzān, form I–X, derivative type)` — e.g. `1َا2ِ3 → فَاعِل` (ism fāʿil, Form I), `مُ1َ2ِّ3 → مُفَعِّل` (Form II), `إِ1ْ2َا3 → إِفْعَال` (maṣdar, Form IV). **Unknown pattern → `None` + reason.** Never a guess.

**B2 — Iʿrāb formatter.** From `(case, deprel, marker, governor_token)` build the card: `بِأُصُولِ → "اسم مجرور — علامة: كسرة — العامل: بِ"`.

**B3 — VERDICT RULE (binding).** Until ACTIVE_BACKLOG §10's dependency-relation route exists, the governor field ships labelled **`source: attention_argmax (UNVALIDATED)`**. `case_gov` exists (`src/model_arms.py:520-524`, q/k/v; weights at 619-621) but nothing in this repo has validated attention-argmax as **ʿāmil**. The §10 oracle is `P(Case | upos, deprel) = 0.7331` macro-F1 **with gold POS+deprel**, so a parser can only do worse; §10 says explicitly *"Do not: target 92–94%"*. The UI may draw the arrow; the card may not assert the governor.

**B4 — Ship-safety.** `pedagogy.py` imports model output and the repo's own rule inventories only. **No corpus-derived data, no lexicon, no Tashkeela, nothing copyleft.**

**Acceptance — fixtures, each adjudicated by the human annotator before it is pinned.** The repo's known traps, not toy words:
- divine name `اللَّهِ` (the 9-row `other` bucket)
- hamza seat `جَاءَ` / weak radicals `قُلْتُ`, `مُحْتَاجٌ`
- tanwīn vs iḍāfa `بِشَارِبِ` vs `بِشَارِبٍ` (**definiteness is the missing input**, §2ce)
- diptote fatha (`apply_diptote_fatha` is **−34** — needs a **lexicon**, so the correct behaviour here is **ABSTAIN**, not a rule)
- sound plural / dual tanwīn (`tanwin_missing` = 8 rows on gold-300, 149 on the ruler)
Zero fluent-but-unsupported cards is the bar (§8). An abstention is a pass.

## TASK C — LEXICON LICENCE AUDIT (DOCUMENT ONLY — no index is built in this order)

**Produce `docs/LICENCE-AUDIT-LEXICON.md`, one row per source: licence / obligation / shippable Y-N / evidence.**

1. **Tashkeela — GPL-2.0, `[LICENSE-RISK]`** (`RESOURCES.md:119`). The existing `data/resources/tashkeela_spelling_index.tsv.gz` is 8.4 MB and **gitignored for exactly this reason**. It is also, per §2cd, *the pipeline* (C == D): the thing that produces the product number is the thing that cannot ship. State that sentence in the audit, in those terms.
2. **arramooz — `RESOURCES.md:211` = `[FIXME] arramooz license`.** Resolve it **before** any sizing, not after: the licence is the gate, not the engineering.
3. **PADT / NYUAD = CC BY-NC-SA**, **QAC = GPLv3** → *"a shipped commercial app built on QAC+PADT+Tashkeela is not [unaffected]"* (`RESOURCES.md:198`). No product claim may derive from them (§7).
4. **RED LINE 4 — no evaluation split may enter any dictionary.** Concretely: the human gold was **sampled from the Tashkeela books** (`config/shared.yaml`: books 0–7 are the dev split *because* the gold came from them). Any surface → (root, wazān) table built from Tashkeela must be leakage-tested with the `G:/aide-harness/leakage_test.py` method and must report its overlap the way §2bo reported **2 of 40 = 5%**.
5. **The only shape that has survived this audit so far** is the shipped one: **skeleton-keyed, count-only, aggregated** — no per-sentence provenance, no root/wazān attached. Any change to that shape re-opens item 4.
6. **Only if the audit clears:** pre-register ACTIVE_BACKLOG **§3** (candidate generator, recall ≥ 0.95 per stratum, licence audit attached) and **§4** (joint root×wazān reranker — must beat prior-only by **|d| > 2·max(sd)** *and* not regress the in-vocab half). Those two items already exist; they are **not new work**, and they are **not** the fix for the surface number.

## OUT OF SCOPE FOR THIS ORDER (do not start)

- **ONNX / INT8 / FastAPI** (`/analyze_sentence`, `/conjugate`, `/generate_drill`). Nothing named onnx/fastapi exists in `src/`, `tools/` or `docs/` — it is 100% unbuilt, and "<0.1% accuracy loss" is **asserted, not measured**. Quantising an embedding-heavy 16.7M model and ONNX-exporting the residual root-slot query + bilinear `case_gov` is where silent op-fallbacks live. It ships **after** Task B's claims are validated, and its loss is measured on the same instruments.
- Any GPU run. The v22 grid is pre-registered, **NOT PUSHED**, pinned to bundle `ac64a52cac081fd7`, bar **≥ +8 rows per source** — a run without a pinned bundle sha is unreadable in this repo and is not a result.
- Re-pinning or re-quoting any number the concurrent agent may have moved.

## REPORTING

Per task: gates (exit codes), the instrument + denominator of every figure, `resource_off` **and** `resource_on` for anything end-to-end, and — for Task A — the explicit **"0 changed rows, trace ON vs OFF"** line. New files stay **uncommitted and visible** (house convention beside a concurrent writer).
