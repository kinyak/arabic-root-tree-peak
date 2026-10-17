# BACKUP.md — where this repo lives, and how backups work

**Private mirror:** https://github.com/kinyak/arabic-root-tree — **PRIVATE**, verified
`private: true` via the API on 2026-10-11. Branch `master` is the default.

---

## 1. The two histories are deliberately NOT identical

| | this repo (`G:\arabic-root-tree`) | the GitHub mirror |
|---|---|---|
| history | **original, authoritative** | same 78 commits, **`build/` purged** |
| commit SHAs | original (cited by `tools/verified_runs.json`) | **rewritten** |
| corpora | present in history | **absent** |
| who verifies runs | `verify_run_code.py --run-id` uses THESE SHAs | — |

**Why the mirror has a different history.** `build/kaggle-dataset/` (the staged Kaggle dataset
copies of PADT + Tashkeela — 8 corpus files, 250 MB) was committed in round 19 (`52d3e8c`),
*before* `build/` was added to `.gitignore`. Gitignore does not remove what is already in
history, so those blobs rode along in every subsequent commit. Two consequences:

1. **GitHub rejects the push**: `build/kaggle-dataset/data/out/padt-train.jsonl` is **114.31 MB**,
   over GitHub's hard 100 MB per-file limit (`GH001`, pre-receive hook declined).
2. **It contradicts the project's own licence rule** (EVIDENCE_LOG B20): QAC (GPLv3),
   PADT/NYUAD (CC BY-NC-SA), Tashkeela (GPL-2.0) and CAMeL (GPL v2) must **not** be committed,
   because committing them redistributes them. Adding `.gitignore` stopped *new* commits; it
   did not remove the existing ones.

So the mirror is built by cloning this repo and purging `build/` from all history. **Content is
proven unchanged**: the rewritten `master` tree hash is byte-identical to the local one —
`2a83f7b2286f8dfa41ff08a42ee7706e61085f46` on both sides.

## 2. SHA map — local (authoritative) → GitHub mirror

Needed whenever a document cites a local SHA and you want to see it on GitHub.
`bundle_sha` values in `verified_runs.json` are **content-derived and unchanged** by the rewrite,
so run verification still works; only these human-readable commit SHAs differ.

The rewrite is **deterministic**, so a given commit's mirror SHA never changes once computed — but
this table is a *snapshot*, not exhaustive: later commits simply chain on and their mirror SHAs are
new. To find one, match the subject line (`git log --grep`) on both sides.

| local | mirror (GitHub) | what it is |
|---|---|---|
| `4bbc397` | `5acc184b` | §2ao — the backup record + the routine |
| `8c62701` | `e74379c9` | master tip at the first backup |
| `79a1f5b` | `6f3f0c51` | `v13-abstention-integration` tip |
| `a6854de` | `853a5aa7` | the abstention-integration merge |
| `b280f8f` | `0c9d1442` | v13 gate repair (§2al) |
| `829254b` | `0b7e63a6` | v14 run — `verified_runs.json` |
| `aaf8317` | `9c2be5fe` | v15 control arm — `verified_runs.json` |
| `ba0394e` | `ce1ba1e1` | v13 run — `verified_runs.json` |
| `7999cf3` | `dc8d2eaf` | v11 run — `verified_runs.json` |

## 3. Running a backup

```bash
cd /g/arabic-root-tree
GH_TOKEN=<token> bash tools/backup_to_github.sh          # Linux/git-bash path
```

or double-click **`push-to-github.cmd`** on the Desktop (prompts for the token, hidden).

The script rebuilds the mirror from this repo, **refuses to push if the mirror's tree does not
match the local tree**, and then pushes. The rewrite is deterministic, so re-running is an
incremental push — only new commits travel.

**The token needs:** Repository permissions → **Contents: Read and write**. A read-only token
authenticates fine and then fails the push with `403 Write access to repository not granted`.
A classic token with the `repo` scope also works. The token is used in-process only and is
**not** written to `.git/config`, to disk, or to a credential helper.

## 4. Landmines

1. **Do NOT `git push` from this repo directly.** Local SHAs and mirror SHAs differ by
   construction, so a plain push is rejected as non-fast-forward. Use the script.
2. **`schannel: CRYPT_E_REVOCATION_OFFLINE`** — this network cannot reach the certificate
   revocation server, so *every* HTTPS call fails (curl code 000, git "SSL certificate
   problem"). Workaround: `--ssl-no-revoke` for curl, `-c http.schannelCheckRevoke=false`
   for git. Already applied inside the script. This is independent of the token.
3. **`git -C` needs a native path on this box.** MSYS path conversion is disabled, so
   `git -C /g/arabic-root-tree` fails with *cannot change to*; use `git -C G:/arabic-root-tree`.
