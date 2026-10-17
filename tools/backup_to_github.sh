#!/usr/bin/env bash
# backup_to_github.sh — publish a PRIVATE GitHub mirror of this repo.
#
# WHY A MIRROR AND NOT A PLAIN PUSH
#   build/kaggle-dataset/** (PADT + Tashkeela copies, 250 MB) is in this repo's HISTORY from
#   round 19, before `build/` was gitignored. GitHub rejects it (a 114 MB file exceeds the
#   100 MB limit) and committing corpora violates the project's own licence rule (CHALLENGES
#   B20). So the mirror is built by cloning and purging `build/` from all history.
#
# THIS SCRIPT NEVER TOUCHES THE LOCAL REPO'S OBJECTS OR SHAs.
#   It works in a throwaway clone. The local repo stays authoritative and its SHAs keep
#   matching tools/verified_runs.json. Full details + the local->mirror SHA map: BACKUP.md
#
# USAGE
#   GH_TOKEN=<token> bash tools/backup_to_github.sh
#   (or export GH_TOKEN first; or let it prompt — input is hidden)
#
# CPU only. No GPU. Safe to re-run: the rewrite is deterministic, so re-runs are incremental.
set -euo pipefail

OWNER="kinyak"
REPO="arabic-root-tree"
LOCAL_DIR="G:/arabic-root-tree"
# NOTE: must be a NATIVE-style path. MSYS path translation is disabled on this box, so a
# native git given "/tmp/art-mirror" would literally create C:\tmp\art-mirror and the
# following `cd /tmp/art-mirror` would then fail.
if [ -n "${LOCALAPPDATA:-}" ]; then
  MIRROR_DIR="$LOCALAPPDATA/Temp/art-mirror"
else
  MIRROR_DIR="/tmp/art-mirror"
fi
PURGE_PATH="build"

# ---------------------------------------------------------------- token
if [ -z "${GH_TOKEN:-}" ]; then
  if [ -f "$HOME/.github_token" ]; then
    GH_TOKEN="$(tr -d '\r\n' < "$HOME/.github_token")"
    echo "  token read from ~/.github_token"
  else
    read -r -s -p "  GitHub token (Contents: read+write, hidden): " GH_TOKEN
    echo
  fi
fi
[ -n "$GH_TOKEN" ] || { echo "  no token supplied"; exit 1; }

export GIT_TERMINAL_PROMPT=0
H=(-H "Authorization: Bearer $GH_TOKEN" -H "Accept: application/vnd.github+json"
   -H "User-Agent: hermes-agent" -H "X-GitHub-Api-Version: 2022-11-28")
# --ssl-no-revoke: this network cannot reach the CRL server (see BACKUP.md landmine 2)
CURL=(curl -sS --ssl-no-revoke --max-time 60)
CLEAN="https://github.com/$OWNER/$REPO.git"
AUTHED="https://$OWNER:$GH_TOKEN@github.com/$OWNER/$REPO.git"

# ---------------------------------------------------------------- 1. repo must exist + be PRIVATE
echo "[1/6] checking $OWNER/$REPO ..."
code=$("${CURL[@]}" -o "$MIRROR_DIR.json" -w "%{http_code}" "${H[@]}" \
       "https://api.github.com/repos/$OWNER/$REPO") || true
if [ "$code" = "404" ]; then
  echo "  creating it PRIVATE ..."
  "${CURL[@]}" -X POST "${H[@]}" -d "{\"name\":\"$REPO\",\"private\":true}" \
    "https://api.github.com/user/repos" > /dev/null
elif [ "$code" != "200" ]; then
  echo "  unexpected HTTP $code — is the token valid?"; exit 1
fi
priv=$("${CURL[@]}" "${H[@]}" "https://api.github.com/repos/$OWNER/$REPO" \
       | python -c 'import json,sys; print(json.load(sys.stdin).get("private"))')
if [ "$priv" != "True" ]; then
  echo "  REFUSING: $OWNER/$REPO is not private (private=$priv). Nothing pushed."; exit 2
fi
echo "      private = True  OK"

# ---------------------------------------------------------------- 2. clone
echo "[2/6] cloning $LOCAL_DIR ..."
rm -rf "$MIRROR_DIR"
git clone --no-hardlinks --quiet "$LOCAL_DIR" "$MIRROR_DIR"
cd "$MIRROR_DIR"

# ---------------------------------------------------------------- 3. purge
echo "[3/6] purging '$PURGE_PATH/' from history (this rewrites SHAs in the MIRROR only) ..."
export FILTER_BRANCH_SQUELCH_WARNING=1
git filter-branch --force --index-filter \
  "git rm -r --cached --ignore-unmatch $PURGE_PATH" --prune-empty -- --all > /dev/null 2>&1
rm -rf .git/refs/original
git reflog expire --expire=now --all
git gc --prune=now --quiet

# ---------------------------------------------------------------- 4. GUARD: content must be identical
local_tree=$(git --git-dir="$LOCAL_DIR/.git" rev-parse master^{tree})
mirror_tree=$(git rev-parse master^{tree})
echo "[4/6] content guard"
echo "      local  master tree: $local_tree"
echo "      mirror master tree: $mirror_tree"
if [ "$local_tree" != "$mirror_tree" ]; then
  echo "  REFUSING: the mirror's tree differs from the local tree — content would be lost."; exit 3
fi
big=$(git rev-list --objects --all | git cat-file --batch-check='%(objecttype) %(objectsize) %(rest)' \
      | awk '$1=="blob" && $2>100000000' | wc -l)
if [ "$big" -gt 0 ]; then
  echo "  REFUSING: $big blob(s) still exceed GitHub's 100 MB limit."; exit 3
fi
echo "      trees identical, no blob over 100 MB  OK"

# ---------------------------------------------------------------- 5. push
echo "[5/6] pushing ..."
# filter-branch has already rewritten THIS branch (it was checked out), so only materialise
# the others — `git branch -f` refuses to touch the branch a worktree has checked out.
cur=$(git rev-parse --abbrev-ref HEAD)
# lstrip=3 gives plain branch names; %(refname:short) would render origin/HEAD as "origin"
for b in $(git for-each-ref --format='%(refname:lstrip=3)' refs/remotes/origin/ \
           | grep -v '^HEAD$'); do
  [ "$b" = "$cur" ] && continue
  git branch -f "$b" "refs/remotes/origin/$b"
done
echo "      local branches: $(git branch --format='%(refname:short)' | tr '\n' ' ')"
git remote remove origin
git remote add origin "$AUTHED"
trap 'git remote set-url origin "$CLEAN" 2>/dev/null || true' EXIT
git -c http.schannelCheckRevoke=false push -u origin --all
git -c http.schannelCheckRevoke=false push origin --tags || true

# ---------------------------------------------------------------- 6. verify against the remote
echo "[6/6] verifying (read back from GitHub, not from local assumptions) ..."
git -c http.schannelCheckRevoke=false ls-remote --heads origin | sed 's/^/      /'
echo
echo "  DONE.  private backup: https://github.com/$OWNER/$REPO"
echo "  Remember: the mirror's SHAs are REWRITTEN. See BACKUP.md for the local->mirror map."
