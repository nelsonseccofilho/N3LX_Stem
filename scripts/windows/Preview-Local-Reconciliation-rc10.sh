#!/usr/bin/env bash
# N3LX_Stem rc.10 — read-only three-way merge PREVIEW from verified local source checkpoint.
# Run in Git Bash. Never changes working checkout, personal library, or release refs.
# Files copied to a new private report folder; no build/tests/install/migration/cleanup.
set -Eeuo pipefail

repo="${1:-$HOME/Git/N3LX_Stem}"
checkpoint="${2:-$HOME/Git/N3LX_Stem-Releases/rc10-source-checkpoint-20261113-043900-3dba8393}"
expected_sha="${3:?Expected exact 40-character rc10 candidate SHA as third argument}"
reports="$HOME/Git/N3LX_Stem-Releases"
local_sha="a7c151565b7bd7609f91eef10e00d5daa5221985"
branch="release/v0.21.0-rc.10"

if [[ ! "$expected_sha" =~ ^[0-9a-f]{40}$ ]]; then
  echo "FAIL: expected SHA must be exactly 40 lowercase hexadecimal characters" >&2; exit 2
fi
for executable in git sed cmp grep date; do
  command -v "$executable" >/dev/null 2>&1 || { echo "FAIL: missing $executable" >&2; exit 2; }
done
repo="$(cd "$repo" && pwd -P)"
checkpoint="$(cd "$checkpoint" && pwd -P)"
reports="$(cd "$reports" && pwd -P)"
if [[ "$repo" == "$checkpoint" || "$checkpoint" == "$repo/"* ||
      "$repo" == "$reports" || "$reports" == "$repo/"* ]]; then
  echo "FAIL: reports and checkpoint must be outside repository" >&2; exit 2
fi
[[ "$(git -C "$repo" rev-parse HEAD)" == "$local_sha" ]] ||
  { echo "FAIL: local HEAD changed since checkpoint; no preview attempted" >&2; exit 2; }
grep -q '^CHECKPOINT_VERIFIED:' "$checkpoint/STATUS.txt" ||
  { echo "FAIL: checkpoint is not marked verified" >&2; exit 2; }
[[ -s "$checkpoint/manifest.json" && -s "$checkpoint/tracked-working-tree.patch" ]] ||
  { echo "FAIL: checkpoint manifest or patch missing" >&2; exit 2; }

# Fetch Git references only; do not merge, checkout, reset, clean, stash or modify index.
git -C "$repo" fetch --no-tags origin "refs/heads/$branch" >/dev/null
actual_sha="$(git -C "$repo" rev-parse FETCH_HEAD)"
[[ "$actual_sha" == "$expected_sha" ]] ||
  { echo "FAIL: candidate moved to $actual_sha; expected $expected_sha" >&2; exit 2; }
git -C "$repo" merge-base --is-ancestor "$local_sha" "$actual_sha" ||
  { echo "FAIL: expected local HEAD is not an ancestor of candidate" >&2; exit 2; }

stamp="$(date -u +%Y%m%d-%H%M%S)"
report="$reports/rc10-reconciliation-preview-$stamp-$$"
if [[ -e "$report" ]]; then
  echo "FAIL: refusing existing destination: $report" >&2; exit 2
fi
mkdir -p "$report"
printf '%s\n' 'INCOMPLETE — no verified reconciliation preview' > "$report/STATUS.txt"
printf 'path\toutcome\tconflict_markers\n' > "$report/summary.tsv"

# Only these 7 explicitly identified source files are in scope.
paths=(
  'app/api/karaoke.py'
  'app/main.py'
  'app/pipeline/karaoke_timing.py'
  'scripts/Start-N3LX_Stem.ps1'
  'static/index.html'
  'static/js/i18n.js'
  'static/js/lyrics.js'
)
clean=0
conflicts=0
collisions=0
candidate_only=0
identical=0
for path in "${paths[@]}"; do
  echo "REVIEW: $path"
  local_copy="$checkpoint/source-files/$path"
  [[ -f "$local_copy" && ! -L "$local_copy" ]] ||
    { echo "FAIL: missing verified local source copy $path" >&2; exit 3; }
  work="$report/files/$path"
  mkdir -p "$work"
  git -C "$repo" show "$actual_sha:$path" > "$work/candidate.raw"
  # Text-only LF-normalized temp files remove CRLF-only merge noise;
  # originals stay untouched and available in the checkpoint.
  sed 's/\r$//' "$work/candidate.raw" > "$work/candidate.txt"
  sed 's/\r$//' "$local_copy" > "$work/local.txt"
  if git -C "$repo" cat-file -e "$local_sha:$path" 2>/dev/null; then
    git -C "$repo" show "$local_sha:$path" > "$work/base.raw"
    sed 's/\r$//' "$work/base.raw" > "$work/base.txt"
    if cmp -s "$work/local.txt" "$work/base.txt"; then
      outcome="CANDIDATE_ONLY"
      cp "$work/candidate.txt" "$work/merged-preview.txt"
      candidate_only=$((candidate_only + 1))
    elif cmp -s "$work/local.txt" "$work/candidate.txt"; then
      outcome="ALREADY_IDENTICAL"
      cp "$work/candidate.txt" "$work/merged-preview.txt"
      identical=$((identical + 1))
    else
      merge_status=0
      git merge-file -p \
        -L "rc10:$path" -L "local-base:$path" -L "local-checkpoint:$path" \
        "$work/candidate.txt" "$work/base.txt" "$work/local.txt" \
        > "$work/merged-preview.txt" || merge_status=$?
      if (( merge_status == 0 )); then
        outcome="AUTO_MERGE_PREVIEW_ONLY"
        clean=$((clean + 1))
      elif (( merge_status < 128 )); then
        outcome="CONFLICT_MARKERS_REVIEW"
        conflicts=$((conflicts + 1))
      else
        echo "FAIL: git merge-file failed for $path (exit $merge_status)" >&2
        exit 3
      fi
    fi
  else
    # Both the untracked user workspace and the rc.10 candidate added
    # this path independently: no 3-way base. NEVER silently replace either.
    if cmp -s "$work/local.txt" "$work/candidate.txt"; then
      outcome="NEW_IDENTICAL"
      identical=$((identical + 1))
    else
      outcome="ADD_ADD_COLLISION_MANUAL"
      collisions=$((collisions + 1))
    fi
    cp "$work/candidate.txt" "$work/merged-preview.txt"
  fi
  count="$(grep -c '^<<<<<<< ' "$work/merged-preview.txt" || true)"
  [[ "$count" =~ ^[0-9]+$ ]] || count=0
  printf '%s\t%s\t%s\n' "$path" "$outcome" "$count" >> "$report/summary.tsv"
done

cat > "$report/RESULT.md" <<EOF
# rc.10 reconciliation PREVIEW (private, not an integrated branch)

Candidate SHA: $actual_sha
Local original HEAD: $local_sha
Source: verified checkpoint (not the live working tree)

- Clean three-way previews requiring semantic review: $clean
- Three-way previews with conflict markers: $conflicts
- Independently added paths needing manual review: $collisions
- Candidate-only paths: $candidate_only
- Already identical: $identical

See summary.tsv for per-path outcomes and conflict marker counts.
Private code-level input/output resides in files/ and must NOT be committed or uploaded.

This preview did NOT create an integration commit, run tests, merge a branch,
change the original checkout/index, publish a release, or read/copy any music.
A clean textual merge is NOT proof of correct application behavior.
EOF
printf '%s\n' 'PREVIEW_COMPLETE_REVIEW_REQUIRED: PRIVATE SOURCE NOT INTEGRATED' > "$report/STATUS.txt"
echo 'RECONCILIATION_PREVIEW_COMPLETE'
echo "CANDIDATE_SHA: $actual_sha"
echo "AUTO_MERGE_PREVIEWS: $clean"
echo "CONFLICTING_THREE_WAY: $conflicts"
echo "INDEPENDENT_ADD_ADD: $collisions"
echo "CANDIDATE_ONLY: $candidate_only"
echo "IDENTICAL: $identical"
echo "REPORT: $report"
echo 'STOP: keep code private; share only RESULT.md and summary.tsv if appropriate.'
