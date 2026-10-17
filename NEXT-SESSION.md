# NEXT SESSION — state at handoff

**Written:** 2026-10-11 · **Repo:** `G:\arabic-root-tree` · everything committed, working tree clean.
*(No commit hash is cited on purpose: any commit that contains this file changes the hash it would cite.
`git log --oneline -1` is the authority, and `git status --short` must be empty.)*
**Read this instead of re-deriving anything.** `HANDOFF.md` is the long-form verified-numbers record and its
header predates this state; `EVIDENCE_LOG.md` §2aa–§2ap is the **append-only** decision log for the recent
rounds. **`ACTIVE_BACKLOG.md` is the live plan — that file, not this brief, is where "what to do next" lives.**
`BACKUP.md` covers where the repo lives off-machine, the local↔mirror SHA map, and the backup routine.

---

## 1. Where the project stands

**Round 26 (v26) is trained, audited, AND corrected.** It ran on Colab/A100 against the spread
2,000,000-token silver sample (`data/out/spread-B-2m/`, capped at 1,871,205 train records), conditioning ON,
3 seeds, and its artifact was received and audited. A **reporting defect** was then found in the evaluator —
the majority-class baseline was a hardcoded constant `1/k` rather than a function of the data — and it has
been **fixed and re-scored on Kaggle (CPU, no GPU, no dataset attached)**. The corrected artifact is
consistent and verified.

**Nothing is running. No compute is queued.** All background jobs exited.

## 2. The corrected numbers (this is what to quote)

| eval set | buggy value | corrected floor |
|---|---|---|
| human gold (300 rows) | `0.3333333333333333` | **0.2364341085271318** |
| PADT dev (4000 rows) | `0.3333333333333333` | **0.2533555185801442** |
| silver dev (4000 rows) | `0.3333333333333333` | **0.2523392868398284** |

All three equal the floors derived independently from the label distribution: for an always-majority
predictor, recall is 1 and precision is `support/n`, so macro-F1 is `(2p/(p+1))/k`.

**Round-26 findings, unchanged by the correction** (0 of 24 verdict strings changed):

- silver-side treatment **SEPARATED above** baseline — human gold +0.0779, in-domain +0.0715,
  PADT dev +0.1063 (raw and beamed consistent)
- gold-side treatment **loses** — −0.0744 raw / −0.0971 beamed, SEPARATED
- the case macro-F1 floor comparison must be restated: the in-domain case macro-F1 (~0.79) is **3.0×** the
  honest floor, not 2.4×

The correction moved 106 other metrics by **≤ 6.2e-04 (0.062 pp)** — worst is **3.1% of that metric's own
seed sd**, 42 up / 64 down. Cause: round 26 trained and scored on an A100, the rescore scores the same
tensors on CPU, so float reduction order differs and a few near-tie argmax decisions flip. Ruled out as
"a different model": `config_sha256`, `parity`, `vocab_sizes`, `seeds` all unchanged.

## 3. Artifacts on disk

| what | where |
|---|---|
| corrected artifact (quote this) | `dist/runs/v26-rescore/results/results.json` |
| the as-run BUGGY artifact, preserved for diffing | `dist/incoming/RESULTS-v26-AS-RUN-BUGGY.json` |
| rescore notebook + full kernel log | `dist/runs/v26-rescore/{kaggle-rescore-CPU.ipynb,kernel_full.log}` |
| round-26 kernel log / incoming artifact | `dist/runs/v26/kernel_full.log`, `dist/incoming/` |
| Drive folder index (resolved folder+file ids) | `dist/drive-index.json` |
| locally pulled + verified Drive copies | `dist/drive-preflight/` |

## 4. Commands that reproduce the state

```bash
cd /g/arabic-root-tree                       # git-bash; .venv/Scripts/python.exe

# verify the corrected artifact against the as-run one (the gate; must print RESCORE DIFF: OK)
.venv/Scripts/python.exe tools/diff_rescore.py \
    dist/incoming/RESULTS-v26-AS-RUN-BUGGY.json \
    dist/runs/v26-rescore/results/results.json

# re-pull + re-verify the artefacts from the link-shared Drive folder (~80 MB + 1 checkpoint)
.venv/Scripts/python.exe tools/drive_preflight.py --all

# rebuild the Kaggle rescore notebook, then check notebook<->code jointly (must be 31/31)
.venv/Scripts/python.exe tools/make_kaggle_rescore.py
.venv/Scripts/python.exe tools/verify_notebook_joint.py dist/kaggle-rescore-CPU.ipynb

# after ANY src/ change: regenerate the training notebook, then verify it jointly (must be 31/31)
.venv/Scripts/python.exe src/make_notebook.py
.venv/Scripts/python.exe tools/verify_notebook_joint.py notebooks/run-padt.ipynb

# the local scoring path, incl. the new abstention accounting (CPU, ~4 s on a 300-row gold)
.venv/Scripts/python.exe src/score_arm_gold.py \
    --ckpt dist/drive-preflight/gold-baseline-s20261009.pt

# drive the Kaggle kernel
.venv/Scripts/python.exe tools/kaggle_rescore_push.py --dry-run   # or --push/--status/--log/--fetch
```

Kernel: **https://www.kaggle.com/code/akhiirendi/arabic-root-tree-rescore-cpu** (private, CPU, no dataset).

## 5. Landmines — already paid for, do not re-learn

1. **Kaggle cannot mount Drive, and the Kaggle dataset API is dead from this machine.** A 34 MB single-POST
   upload resets three times in a row (11.8 MB succeeds), and a `datasetDataSources` entry the token cannot
   resolve is dropped **SILENTLY** — the kernel looks configured and mounts nothing. Artefacts therefore
   travel by HTTPS pull from the link-shared Drive folder. `datasets/list` returns **zero datasets** on the
   account; do not plan around one existing.
2. **The plain `uc?export=download` URL LIES.** It serves the small records fine but returns a 2,471-byte
   HTML interstitial for the 65 MB `tashkeela-train.jsonl.gz`, which gzip reports as
   `BadGzipFile: Not a gzipped file (b'<!')` — i.e. as a corrupt upload. It is not one. Use
   `drive.usercontent.google.com/download?...&confirm=t` and reject HTML payloads.
3. **Never compare a metric's move against a *global* noise figure.** The first `diff_rescore.py` compared
   the largest move anywhere to the smallest sd anywhere and printed "1.14× the seed noise" — meaningless,
   different metrics. Compare each metric to **its own** sd.
4. **`src/` is inside the embedded payload**, so editing anything in `src/` (or `tools/fit_parity_union.py`,
   `config/shared.yaml`, the gold) changes the bundle sha256. That is why the new tooling lives in `tools/`.
   Bundle `4c09b828…` (round 26) → `126c58d1…` (fixed): 73 files, 71 byte-identical, the 2 that differ are
   exactly `src/eval_harness.py` and `src/make_notebook.py`.
5. **Long patch payloads can truncate** and write a literal `...[truncated]` into a file — re-read after any
   long edit.
6. **`gold_context_oov_rate` (0.1739) is a COVERAGE quantity, not a model metric** — identical across arms
   and seeds by construction, recorded once, never compared arm-to-arm.
7. **The code payload is now 74 % of Kaggle's cap.** `notebooks/run-padt.ipynb` embeds 75 files at
   sha256 `e1ad53bd…` = **520.8 KB of base64 against the 700 KB limit** (`MAX_EMBED_B64`; Kaggle
   rejects kernel source ≥ 1 MB). It was regenerated when the abstention gate moved into `src/`
   (EVIDENCE_LOG §2am). The next sizeable addition to `src/` may breach the cap — `make_notebook.py`
   refuses rather than producing a file the push would reject, but plan for it (the payload is CODE:
   if it grows, move measurement tooling back to `tools/`).
8. **The rescore scores code from the DRIVE BUNDLE, not from this repo.** The rescore notebook
   downloads a bundle into `/kaggle/working/bundle` and runs that `src/`. So a src/ change does not
   reach a rescore until the bundle is refreshed: **a rescore run today would use the pre-integration
   harness and report no abstention counters.** Refresh before claiming cloud numbers.
9. **`data/abstention_homographs.json` is NOT in the code payload** (the payload is src/ + config +
   gold + the PADT dictionary half). In the cloud bundle the Tier-1 gate therefore runs with
   homograph deferral OFF — graceful, and its false-abstention rate is then 0.584 % not 0.086 %
   (§2al). Local and cloud counters are not the same measurement.
10. **A coverage tool's target set was defined by the CONFIG, so `8ab3a16` silently broke it.**
    `tools/record_coverage.py` took "absent" from `cfg['paths']['silver_train']`, which round-26 prep
    repointed to the spread build — so it came to measure Build B against "words absent from Build B"
    and printed `0/0/0` as a complete table (§2an.4). It now takes an explicit **`--anchor`** and
    **refuses** (exit 2) when the anchor is a build under test. `tools/sample_coverage_study.py`
    still uses the config-driven rule: it now prints its baseline, and a re-run's numbers are **not
    comparable** to §2ae/§2af (targets 34 vs 126) unless the baseline is stated.
11. **v13 §6's "immediate next steps" 2 and 3 are STALE** (§2an) — the wazān→root conditioning is
    implemented (v14) *and* was ablated (v15: the root picture does not move; it was masking a 4.2 pp
    treatment wazān deficit), and the char trunk shipped in v12 (§2z). Do **not** spend a run on
    either. The open lever is **`max_vocab`** (56 → 82 of 126 covered; cap binds at 19,998/65,684),
    and it is deliberately a NEXT-run variable, not a co-change.
12. **Do NOT `git push` from this repo — and the corpora are in HISTORY, not just the tree.** The
    private mirror is `kinyak/arabic-root-tree` (**PRIVATE**, verified via API) and it is built by
    `tools/backup_to_github.sh`, which clones + purges `build/` and **refuses to push unless the
    mirror's tree matches the local one** (§2ao, `BACKUP.md`). Two reasons a plain push fails:
    the mirror's SHAs are rewritten (so local→mirror is non-fast-forward by construction), and
    `build/kaggle-dataset/**` sits in local history from round 19 with a **114.31 MB** file — over
    GitHub's hard 100 MB limit, and a licence problem under B20 regardless. Related trap on this
    network: every HTTPS call needs `--ssl-no-revoke` (curl) / `-c http.schannelCheckRevoke=false`
    (git), or TLS fails with `CRYPT_E_REVOCATION_OFFLINE`.

## 6. Open decisions (yours; nothing is blocked)

The registry gate is now satisfied — the corrected artifact is consistent — so all three are live:

1. **Update `tools/verified_runs.json`** with v26 and/or v26-rescore. `v11`, `v14`, `v15` are pinned;
   **v26 is deliberately NOT in it yet** (the earlier instruction was: do not update until consistent).
2. **Compare v14/v15** — deliberately deferred for the same reason, now permitted.
3. **The next experiment is the `max_vocab` cap.** Held fixed at 20,000 this round and asserted as an
   invariant; with the cap removed, B-side gold-word coverage goes 56 → 82. Raising it is the *next*
   run's variable, not a co-change to this one.
4. ~~**Merge `v13-abstention-integration`?**~~ **DONE** — merged into `master` with `--no-ff` (merge
   commit `a6854de`), carrying EVIDENCE_LOG §2am: the Tier-1 gate moved into `src/`, `eval_harness.py`
   counts abstentions additively, `notebooks/run-padt.ipynb` regenerated (sha `e1ad53bd…`). The four
   gates were re-run on the merged tree and are green. The branch still exists (unmerged-in-history is
   no longer true; deleting it is cosmetic and safe).
5. **Refresh the Drive bundle and re-run the rescore?** Only if the abstention counters should exist
   in a *cloud* artifact — landmine 8. The counters are new fields; no existing metric moves, so this
   is new information rather than a correction.
