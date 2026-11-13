#!/usr/bin/env bash
# Before/after screenshots of this branch against its base, on the same made-up demo data.
#
#   scripts/pr-shots.sh shots.json [base-ref] [out-dir]
#
# base-ref defaults to origin/main, out-dir to .shots (git-ignored). The "after" side is the
# working tree, or HEAD_REF=<ref> to shoot another branch (e.g. a PR you are reviewing). Produces
#   <out>/after/*.png    this working tree, with the spec's highlights
#   <out>/before/*.png   base-ref, same steps, no highlights
#   <out>/compare/*.png  before | after side by side
set -euo pipefail
SPEC=$(realpath "${1:?usage: scripts/pr-shots.sh shots.json [base-ref] [out-dir]}")
BASE=${2:-origin/main}
OUT=$(realpath -m "${3:-.shots}")
ROOT=$(git rev-parse --show-toplevel)
cd "$ROOT"
TMP=$(mktemp -d)
PIDS=()
cleanup() {
  for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null || true; done
  git worktree remove --force "$TMP/base" 2>/dev/null || true
  git worktree remove --force "$TMP/head" 2>/dev/null || true
  rm -rf "$TMP"
}
trap cleanup EXIT

free_port() { python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])'; }
wait_up() { for _ in $(seq 1 50); do curl -fs "http://127.0.0.1:$1/" >/dev/null && return 0; sleep 0.2; done; echo "server on $1 didn't start" >&2; return 1; }

sleep 3600 & PIDS+=($!)                        # keeps the demo's "running" sessions alive
python3 scripts/demo_data.py "$TMP/home-after" --pid "${PIDS[0]}" >/dev/null
cp -a "$TMP/home-after" "$TMP/home-before"      # same data, separate caches
git worktree add --detach "$TMP/base" "$BASE" >/dev/null 2>&1
AFTER="$ROOT"
if [ -n "${HEAD_REF:-}" ]; then
  git worktree add --detach "$TMP/head" "$HEAD_REF" >/dev/null 2>&1
  AFTER="$TMP/head"
fi

serve() {  # serve <ccdeck script> <home> <port>
  HOME="$2" PATH="$2/bin:$PATH" CCDECK_AUTOSTART=0 CCDECK_NOTIFY=0 \
    python3 "$1" serve --port "$3" >"$TMP/serve-$3.log" 2>&1 &
  PIDS+=($!)
}
PA=$(free_port); PB=$(free_port)
serve "$AFTER/ccdeck" "$TMP/home-after" "$PA"
serve "$TMP/base/ccdeck" "$TMP/home-before" "$PB"
wait_up "$PA"; wait_up "$PB"
sleep 3   # first PR refresh through the fake gh

rm -rf "$OUT"; mkdir -p "$OUT"
node scripts/screenshots.mjs --spec "$SPEC" --url "http://127.0.0.1:$PA" --out "$OUT/after"
node scripts/screenshots.mjs --spec "$SPEC" --url "http://127.0.0.1:$PB" --out "$OUT/before" --lenient
node scripts/screenshots.mjs --compare "$OUT/before" "$OUT/after" --out "$OUT/compare"
echo "Screenshots in $OUT"
