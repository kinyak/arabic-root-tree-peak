# Run manifest — Google Colab & Kaggle

**Purpose:** exactly what to download, where it goes, and what it costs in compute units.
Companion to `HANDOFF.md` (design + problems) and `RESOURCES.md` (full catalogue).

Budget: **~200 Colab compute units, on a Colab Pro plan.** Pro grants **100 units/month** and **units expire
90 days after grant** — the balance is perishable, so confirm the expiry date before planning a long
campaign. Rates below are *observed* values and vary by runtime, region and time; **confirm your live burn
rate in the Colab *Resources* panel before launching any long job.**
Host: the corpora live locally at `~/arabic-root-tree/data/raw/`; the laptop cannot train anything
(no CUDA, 15 GB RAM).

---

## 0. Headline: you almost never need to upload anything

Every corpus below is fetchable **directly from inside Colab**. Manual upload is needed for exactly one
category: **your own derived artifacts**. Don't shuttle 400 MB through the browser.

| Resource | Size | How it reaches Colab | Upload needed? |
|---|---|---|---|
| QAC morphology v0.4 | 6.3 MB | `wget` from the GitHub mirror | ❌ no |
| UD Arabic-PADT (3 files) | 51 MB | `wget` from UD GitHub | ❌ no |
| CAMeL `morphology-db-msa-r13` | 40.5 MB | `camel_data -i` | ❌ no |
| CAMeL `disambig-mle-calima-msa-r13` | 88.7 MB | `camel_data -i` | ❌ no |
| **Tashkeela** (full, 97 books) | **401 MB** | `load_dataset` / HF hub | ❌ no |
| arramooz sqlite (verifier) | ~5 MB | `pip install arramooz-pysqlite` | ❌ no |
| Qwen3-1.7B (ablation arm only) | ~3.5 GB | HF hub, on demand | ❌ no |
| **Your merged JSONL** | ~50–150 MB | **you build it locally → upload** | ✅ **yes** |
| Your `src/*.py` / notebooks | KB | upload or `git` | ✅ yes |

**Transfer sizes: what you're choosing between**

| Method | Good for | Practical ceiling |
|---|---|---|
| `files.upload()` | a few files, one-off | ~100 MB before it gets painful |
| Chrome/Drive upload | the JSONL | GBs |
| Google Drive mount | **anything reused across sessions** | best option — see §3 |
| `git` | code | fine |

---

## 1. Bootstrap cell (copy-paste, run once per session)

```python
#@title 1.1 — environment
import os, subprocess, pathlib
os.makedirs("/content/data", exist_ok=True)

# Colab already ships torch WITH CUDA — do NOT use --torch-backend=cpu here.
# (That flag is for the local laptop, where a default install wastes 5 GB on CUDA wheels.)
%pip install -q camel-tools datasets
!camel_data -i morphology-db-msa-r13          # 40.5 MB, GPL v2
!camel_data -i disambig-mle-calima-msa-r13    # 88.7 MB, GPL v2 — MANDATORY (see HANDOFF §3.4)
```

```python
#@title 1.2 — corpora
# QAC morphology: the vendor URL now 302s to an HTML page. Use the mirror.
!wget -q -O /content/data/qac-morphology-0.4.txt \
  https://raw.githubusercontent.com/q-ran/quran/master/sources/1.0/quranic-corpus-morphology-0.4.txt

# UD Arabic-PADT
!for f in train dev test; do wget -q -O /content/data/ar_padt-ud-$f.conllu \
  https://raw.githubusercontent.com/UniversalDependencies/UD_Arabic-PADT/master/ar_padt-ud-$f.conllu; done

# Tashkeela — 401 MB, downloads straight into the session
from datasets import load_dataset
tashkeela = load_dataset("community-datasets/tashkeela", split="train")
print(len(tashkeela), "documents")
```

```python
#@title 1.3 — verify everything landed (cheap sanity gate)
import hashlib, os
EXPECT = {
  "qac-morphology-0.4.txt":  "a1d12923815341face765083805d2148ed2d9f5cc3f7d6665219d887675d8c46",
  "ar_padt-ud-train.conllu":"f0b56962b340f5325bb5d293f47717522e706112c19029e82c225355c6d65e85",
}
for name, want in EXPECT.items():
    p = f"/content/data/{name}"
    got = hashlib.sha256(open(p,'rb').read()).hexdigest() if os.path.exists(p) else "MISSING"
    print(f"{'OK ' if got==want else 'BAD'}  {name}  {got[:16]}")
```

---

## 2. What to upload, and how

Only the derived JSONL. Build it **locally** (`HANDOFF.md` §7 steps 3–4) — it is CPU work and costs
**0 compute units**; paying Colab units to do data prep is waste.

### 2.0 — upload the `.gz`, not the `.jsonl` (measured)

The PADT per-token records compress **~12×**, and the notebook's cell 2 accepts either form: a `.gz`
sitting beside the `.jsonl` is streamed back out in-session.

| file | raw | gzipped | records | sha256 (raw bytes) |
|---|---|---|---|---|
| `padt-train.jsonl` | 119,857,618 B | **8,497,644 B** | 223,881 | `6ae53007cb73581ae78bc107…` |
| `padt-dev.jsonl` | 15,967,095 B | **1,133,957 B** | 30,239 | `71a720f07cbf1b3056467e87…` |

130 MB of browser upload becomes 9.6 MB. Cell 2 does the gunzip itself and a **truncated stream
raises instead of training on half a corpus** (the partial file is deleted, so a re-run re-stages it).

### 2.1 — put them where cell 2 looks

Cell 2 stages `data/out/padt-{train,dev}.jsonl`, accepting `.jsonl` or `.jsonl.gz`, from the first of:

```
$CACHE/data/out/        # CACHE = /content/drive/MyDrive/arabic-root-tree   <- recommended (§3)
/content/data/out/
/content/
```

So either drop them in Drive at `MyDrive/arabic-root-tree/data/out/` (persists across sessions), or
upload into the session with the picker:

```python
#@title 2.1 — upload instead of using Drive (session-only)
from google.colab import files
up = files.upload()                        # select data/out/padt-*.jsonl(.gz) from the laptop
!mkdir -p /content/data/out && mv padt-*.jsonl* /content/data/out/
```

`files.upload()` does not persist between sessions. Missing records are not a mystery either way:
cell 2 fails fast and names the exact path it looked in.

---

## 3. Persistence — Colab sessions are ephemeral

Everything in `/content` dies when the runtime recycles (12 h max, or ~90 min idle). For a multi-session
run, cache on Drive and re-link each session:

```python
from google.colab import drive
drive.mount("/content/drive")
CACHE = "/content/drive/MyDrive/arabic-root-tree"
os.makedirs(f"{CACHE}/data/out", exist_ok=True)
os.makedirs(f"{CACHE}/checkpoints", exist_ok=True)

# symlink so code paths stay short and portable
!ln -sfn {CACHE}/data/out /content/data/out
```

**Always checkpoint to Drive, not `/content`** — a 12-hour cutoff mid-training with checkpoints in
`/content` loses the run. Use `save_steps` short enough that a restart costs minutes, not hours.

---

## 4. Compute allocation — the part that actually matters

### 4.1 The finding that changes the plan

**For models this size, T4 and A100 cost *almost the same in compute units.** A T4 is ~8x slower but
its units/hour rate is ~8x cheaper, so the two cancel:

| GPU | 25M params × 500M tokens | units |
|---|---|---|
| T4 | 1.60 h | **3.1** |
| V100 | 0.56 h | 2.8 |
| A100 | 0.17 h | 2.5 |

So **do not spend A100 units on small models** — there is nothing to buy. Spend them only where VRAM
or speed actually forces it (the 1.7B ablation). Better still: run the small-model work on **Kaggle,
which is free** (§5).

### 4.2 Budget for the paper

| Experiment | GPU | Units |
|---|---|---|
| Control: 25M transformer, surface tokens (3 seeds) | T4 / Kaggle | 3.1 |
| Treatment: 25M root-manifold + 5 heads (3 seeds) | T4 / Kaggle | 3.1 |
| Scaling check: 50M, both arms | T4 / Kaggle | 12.6 |
| **Kaggle-runnable subtotal** | | **18.8** |
| Ablation: Qwen3-1.7B QLoRA, 100M tokens | A100 | **34.1** |
| ~~Ablation at 500M tokens~~ | A100 | ~~170.3~~ ⚠️ blows the budget |
| Data pipeline + eval harness (parse, disambiguate, score) | **your laptop** (CPU) | **0** — genuinely free |
| ↳ the same job on a Colab *CPU* runtime instead | Colab CPU | **<1/h** ⚠️ not zero — see §4.3 |

**Recommended split:** run the three from-scratch arms on **Kaggle (free)**; reserve Colab units for the
A100-only ablation. Net Colab spend ≈ **15–23 of 200 units** (§4.3), leaving ~175+ for reruns and the
scaling check. Do **not** run the ablation at 500M tokens — that alone is 76–114 units.

> Reminder of scale: the *original spec's* plan (1.5B from scratch, 30B tokens) cost **9,014 units**.
> The difference is entirely the model size, not the architecture. A 25M from-scratch model is the
> right instrument for a paper about architecture; 1.5B is the right instrument for a product.

### 4.3 Colab Pro specifics — what your plan actually gives you

| Feature | Colab Pro | Consequence for this project |
|---|---|---|
| Compute units | **100/month**, expiring **90 days** after grant | your ~200 balance is perishable — use it, don't bank it |
| Max session | **12 hours** | the 24 h continuous execution is **Pro+ only**; do not plan a 24 h run |
| System RAM | high-memory VMs, **up to ~53 GB**, subject to availability + unit balance | enough to hold the whole disambiguated corpus in memory |
| GPUs | priority access to **V100 / L4 / A100** | actual assignment varies — never hardcode the device |
| CPU runtimes | consume **under 1 unit/hour** — **not free** | run the data pipeline on the laptop instead |

**Check your balance first.** In Colab: *Runtime → View resources* (or the Resources pane, top-right).
It shows your remaining units and your current hardware's burn rate. Units do not refresh at a predictable
instant and the reported rates are approximate, so treat any plan in this file as an estimate and verify
against that panel.

**The A100 rate is uncertain by ~50%.** Sources report **~10 units/h** and **~15 units/h** for the same
class of hardware. That moves the ablation's cost between **~15 and ~23 units**:

| Ablation (Qwen3-1.7B QLoRA, 100M tokens = 1.51 A100-h) | Cost |
|---|---|
| at 10 units/h | **~15 units** |
| at 15 units/h | **~23 units** |
| at 500M tokens (7.57 A100-h) — **do not run** | 76–114 units |

Either way the whole paper fits well inside 200 units. The uncertainty does not change the plan;
it only changes how much you have left over.

---

## 5. Kaggle — the free tier, and how to double it

- **30 GPU h/week free**, *floating* — Kaggle sometimes grants more when demand is low (users report 39 h).
- **Resets Saturday 00:00 UTC.**
- Hardware: **P100** and **T4 x2** (2× T4, 4 CPU cores, 29 GB RAM). **No A100** — so Kaggle cannot run
  the 1.7B ablation; that stays on Colab.
- Enable via the notebook's *Settings → Accelerator → GPU*.
- **Colab Pro owners can link accounts for +15 h/week on Kaggle** (Pro+ = +30 h) which **do not consume
  Colab compute units**. You have Pro, so claim this — it is free capacity for exactly the small-model
  experiments above.
- 9 h max per session, 12 h max runtime.

### 5.1 Claim the Colab Pro bonus (do this now, it's free)

1. Open any Kaggle notebook editor.
2. **File → Link to Colab.**
3. Kaggle verifies your Colab subscription is active (you must be signed in to the same Google account).
4. Check **Account → Settings → GPU quotas** — it should now show **30 + 15 = 45 h/week**.

The extra hours do **not** draw on your Colab compute units. Unlinking is available from the same settings
page at any time. (This is an experimental Kaggle promotion — it can change or end.)

**Net:** Kaggle covers the from-scratch arms (≈9 T4-hours, well inside the quota). Colab covers the
A100 ablation. With the bonus claimed, you realistically never need to spend units on small models at all.

---

## 6. Gotchas

- **Do not use `--torch-backend=cpu` in Colab.** That advice is for the laptop. Colab ships a working
  CUDA torch; overriding it to CPU would silently make training crawl.
- **`camel_data` takes ~2–3 minutes** for both packages. Not an error if it looks stalled.
- **The QAC vendor URL is dead** — `corpus.quran.com/download/quranic-corpus-morphology-0.4.txt.zip`
  returns an 8,826-byte HTML page with HTTP 200. Always use the mirror, and always `file` the result
  to confirm it is not HTML.
- **Tashkeela parquet is compressed.** 401 MB on disk expands considerably once decoded to text. Decode
  once, tokenize, and cache the tokenized artifact on Drive — re-decoding every session is wasted time.
- **The 12 h cutoff is the risk, not the GPU.** Checkpoint to Drive frequently; assume any run can
  be killed without warning.
- **Free-tier runtime may not give you the GPU you asked for.** Don't hardcode device assumptions —
  `device = "cuda" if torch.cuda.is_available() else "cpu"` and fail loudly rather than silently
  training on CPU.
- **Licensing follows the data into Colab.** QAC (GPLv3), PADT (CC BY-NC-SA 3.0), Tashkeela (GPL-2.0),
  CAMeL data packages (GPL v2) — fine for a paper, a blocker for a commercial product. See
  `RESOURCES.md` §7.
- **Only Tashkeela is big enough to be worth caring about**, and at **66.5M tokens (measured rev. 10; the docs'
  earlier "~98M" was ~1.5× high — see `EVIDENCE_LOG.md` §2j)** it is the binding
  constraint on model size — not the GPU. See §4.2 and `HANDOFF.md` §5.4.
