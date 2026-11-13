#!/usr/bin/env bash
# Publish screenshots for a PR and print Markdown that embeds them.
#
#   scripts/upload-shots.sh <pr-number> <file.png>...
#
# The repo slug comes from the origin remote; set CCDECK_REPO=owner/name to override (use the
# repo's current name: raw URLs of a renamed repo don't always redirect).
# Images go to the orphan branch `screenshots`, under pr-<n>/<short-sha>/, so they never touch
# main and every push gets fresh URLs. The repo must be public for the images to show in the PR.
set -euo pipefail
PR=${1:?usage: scripts/upload-shots.sh <pr-number> <file.png>...}
shift
[ $# -gt 0 ] || { echo "no files given" >&2; exit 1; }
FILES=()
for f in "$@"; do FILES+=("$(realpath "$f")"); done
ROOT=$(git rev-parse --show-toplevel)
cd "$ROOT"
SLUG=${CCDECK_REPO:-$(git remote get-url origin | sed -E 's#(git@github.com:|https://github.com/)##; s#\.git$##')}
SHA=$(git rev-parse --short "${HEAD_REF:-HEAD}")  # the commit the shots show
DEST="pr-$PR/$SHA"
WT=$(mktemp -d)
trap 'git worktree remove --force "$WT" >/dev/null 2>&1 || true; rm -rf "$WT"' EXIT

if git fetch -q origin screenshots 2>/dev/null; then
  git worktree add -q --detach "$WT" FETCH_HEAD
  git -C "$WT" checkout -q -B screenshots
else
  git worktree add -q --detach "$WT" HEAD
  git -C "$WT" checkout -q --orphan screenshots
  git -C "$WT" rm -rfq . >/dev/null
  printf '# Screenshots\n\nPR screenshots made by scripts/upload-shots.sh. Not part of any release.\n' >"$WT/README.md"
fi
mkdir -p "$WT/$DEST"
i=0
NAMES=()
for f in "${FILES[@]}"; do  # compare/board.png -> compare-board.png, so names don't collide
  i=$((i + 1))
  n="$(basename "$(dirname "$f")")-$(basename "$f")"
  cp "$f" "$WT/$DEST/$n"
  NAMES+=("$n")
done
git -C "$WT" add -A
git -C "$WT" commit -qm "Screenshots for #$PR at $SHA"
for i in 1 2 3 4; do git -C "$WT" push -q origin screenshots && break; sleep $((i * 2)); done

for n in "${NAMES[@]}"; do
  echo "![${n%.png}](https://raw.githubusercontent.com/$SLUG/screenshots/$DEST/$n)"
  echo
done
