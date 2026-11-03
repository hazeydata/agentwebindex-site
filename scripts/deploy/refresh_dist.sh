#!/usr/bin/env bash
# refresh_dist.sh - replace wr/dist with a fresh, tested build of agentwebindex-site at an exact commit.
# NEVER deploys.
#
#   refresh_dist.sh <full 40-hex agentwebindex-site sha>   refresh
#   refresh_dist.sh --rollback                             restore newest valid backup (dist.prev.<UTC ts>.<pid>) + its BUILD_SHA
#                                                          (backups whose BUILD_SHA is 'unknown'/invalid or that are empty are skipped)
#   refresh_dist.sh --recover                              only finish/undo an interrupted run (journals), then exit
#
# Guarantees (wr = $AWI_DEPLOY_ROOT/wr):
#  * Clone/checkout/build/run_tests.sh/verify all happen in a mktemp dir; wr is not modified until they pass.
#  * The live swap is ONE atomic rename (mv --exchange): wr/dist always exists and is either the old or the new build,
#    including after kill -9 at any point.
#  * Every step after the swap writes a journal (wr/.dist.new.<pid>.journal); on failure the script swaps the old build
#    back and restores BUILD_SHA; after a crash, --recover (or any next run, which recovers first) finishes or undoes
#    the journal under the lock and sets BUILD_SHA to match wr/dist. After kill -9 between the swap and the BUILD_SHA
#    write, BUILD_SHA lags wr/dist until --recover (or the next run) is done.
#  * Backups: previous build kept as wr/dist.prev.<UTC ts>.<pid> + wr/dist.prev.<UTC ts>.<pid>.BUILD_SHA, newest 3 kept.
#    No backup is made when the current BUILD_SHA already equals SITE_SHA.
#  * One run at a time (flock on wr/.refresh.lock, fd 9). mv --exchange support is checked in wr before any build.
#    Every child process is started with fd 9 closed (9>&- / exec 9>&-), so after kill -9 of this script no orphaned
#    child (git, build.py, run_tests.sh, cp, ...) keeps the lock; the next run / --recover can take it at once.
#  * Build clones live ONLY under the per-wr build root wr/.builds/ (mktemp -d wr/.builds/awibuild.XXXX), which only runs
#    holding THIS wr's lock create. A clone is removed on exit/INT/TERM/HUP; after kill -9 it is recorded in
#    wr/.awibuild.<pid> (written atomically: temp file + mv) and removed by the next run / --recover, unless a process
#    still uses it (then it is left for a later run). A wr/.builds/awibuild.* dir that NO marker records and that no live
#    process uses (kill -9 between mktemp and the marker write) is moved, never deleted, with mv -n into
#    wr/.builds/quarantine/ by --recover and at the start of every run. Nothing in $AWI_TMP_ROOT is ever scanned.
#  * refresh_dist.sh --quarantine-legacy <name...>   opt-in, one-off: moves (mv -n, never deletes) only the named legacy
#    clones $AWI_TMP_ROOT/awibuild.<name> (name must be one of the 10 known pre-rev6 leftovers) into
#    $AWI_TMP_ROOT/awibuild-legacy-quarantine/, each only if no live process uses it. Touches nothing else (in wr it only takes/creates wr/.refresh.lock).
# Test-only env (refused unless AWI_TEST=1): AWI_WR, AWI_REPO_URL, AWI_CP. With AWI_TEST=1, AWI_WR is REQUIRED and must
# be a directory strictly inside a mktemp -d dir directly under $AWI_TMP_ROOT (e.g. $AWI_TMP_ROOT/awi4.AbCd/wr); the
# real $AWI_DEPLOY_ROOT/wr (and anything under $AWI_DEPLOY_ROOT) is refused. With AWI_TEST=1,
# --quarantine-legacy looks in that sandbox dir (<sandbox>/awibuild.<name>) instead of $AWI_TMP_ROOT.
set -euo pipefail

# fd 9 (the lock) must not leak into children: every external command used below runs through these wrappers, which
# close fd 9 in the child before exec. flock is NOT wrapped (it needs fd 9).
for _c in git python3 cp diff find sort xargs sha256sum cut mv rm mkdir mktemp head sed ls date touch stat sleep wc \
          readlink cat basename; do
  eval "$_c() { command $_c \"\$@\" 9>&-; }"
done; unset _c
die() { echo "refresh_dist: STOP: $*" >&2; exit 1; }
loud() { echo "refresh_dist: !!! RESTORE FAILED: $* !!! (wr left with journal; run refresh_dist.sh --recover)" >&2; RESTORE_FAIL=1; }

# Box roots come from the environment (no machine paths in the repo). Both are required.
: "${AWI_DEPLOY_ROOT:?set AWI_DEPLOY_ROOT to the box deploy root (the dir that holds wr/)}"
: "${AWI_TMP_ROOT:?set AWI_TMP_ROOT to the box tmp root (sandboxes and legacy build dirs live here)}"
AWI_DEPLOY_ROOT="${AWI_DEPLOY_ROOT%/}"; AWI_TMP_ROOT="${AWI_TMP_ROOT%/}"
case "$AWI_DEPLOY_ROOT$AWI_TMP_ROOT" in *[!A-Za-z0-9_./-]*) die "AWI_DEPLOY_ROOT/AWI_TMP_ROOT must be plain paths";; esac
DEFAULT_WR="$AWI_DEPLOY_ROOT/wr"
if [ "${AWI_TEST:-}" != 1 ]; then
  for v in AWI_WR AWI_REPO_URL AWI_CP; do
    [ -z "${!v+x}" ] || die "$v is set but AWI_TEST!=1; unset AWI_WR AWI_REPO_URL AWI_CP for real runs"
  done
else
  [ -n "${AWI_WR:-}" ] || die "AWI_TEST=1 requires AWI_WR (a sandbox wr inside a mktemp -d dir under $AWI_TMP_ROOT)"
fi
if [ -n "${AWI_WR+x}" ]; then WR_IN="$AWI_WR"; else WR_IN="$DEFAULT_WR"; fi
REPO_URL="${AWI_REPO_URL:-https://github.com/hazeydata/agentwebindex-site.git}"
CP="${AWI_CP:-cp}"

[ -n "$WR_IN" ] || die "WR is empty"
[ -d "$WR_IN" ] || die "WR is not a directory: $WR_IN"
WR="$(cd -- "$WR_IN" && pwd -P)"
[ "$WR" != / ] || die "WR is /"
REAL_WR="$(cd -- "$DEFAULT_WR" 2>/dev/null && pwd -P || echo "$DEFAULT_WR")"
if [ "${AWI_TEST:-}" = 1 ]; then
  [ "$WR" != "$REAL_WR" ] || die "AWI_TEST=1 may not target the real wr ($REAL_WR)"
  case "$WR" in "$AWI_DEPLOY_ROOT"|"$AWI_DEPLOY_ROOT"/*) die "AWI_TEST=1 may not target $WR (under $AWI_DEPLOY_ROOT)" ;; esac
  [[ "$WR" =~ ^${AWI_TMP_ROOT}/([A-Za-z0-9_-]+\.[A-Za-z0-9]{4,})/[^/].*$ ]] \
    || die "test WR $WR must be strictly inside a mktemp -d dir directly under $AWI_TMP_ROOT (e.g. $AWI_TMP_ROOT/awi4.XXXX/wr)"
  SBX="$AWI_TMP_ROOT/${BASH_REMATCH[1]}"
  [ -d "$SBX" ] && [ ! -L "$SBX" ] && [ -O "$SBX" ] && [ "$(stat -c %a -- "$SBX")" = 700 ] \
    || die "test sandbox $SBX is not a mktemp -d dir (owned by you, mode 700)"
  LROOT="$SBX"
else
  [ "$WR" = "$REAL_WR" ] || die "WR $WR is not $DEFAULT_WR"
  LROOT="$AWI_TMP_ROOT"
fi
BROOT="$WR/.builds"                 # per-wr build root: only runs holding this wr's lock create clones here
QDIR="$BROOT/quarantine"            # does not match awibuild.*
LQDIR="$LROOT/awibuild-legacy-quarantine"
LEGACY_OK=" 1jXG 3KJB CD2H CjYU JP4F OhXq Qmo9 ZD6r Zozz xqoQ "   # the only names --quarantine-legacy accepts
echo "refresh_dist: effective WR=$WR"

MODE=refresh; SITE_SHA=""
if [ "${1:-}" = --rollback ]; then MODE=rollback; [ $# -eq 1 ] || die "--rollback takes no arguments"
elif [ "${1:-}" = --recover ]; then MODE=recover; [ $# -eq 1 ] || die "--recover takes no arguments"
elif [ "${1:-}" = --quarantine-legacy ]; then MODE=legacy; shift; [ $# -ge 1 ] || die "--quarantine-legacy needs one or more names"
  LNAMES=("$@")
  for n in "${LNAMES[@]}"; do case "$LEGACY_OK" in *" $n "*) ;; *) die "--quarantine-legacy: '$n' is not one of:$LEGACY_OK" ;; esac; done
else
  SITE_SHA="${1:-}"
  [[ "$SITE_SHA" =~ ^[0-9a-f]{40}$ ]] || die "SITE_SHA must be a full 40-hex lowercase sha, got '$SITE_SHA'"
fi

manifest() { (exec 9>&-; cd -- "$1" && find . \( -type f -o -type l \) -print0 | LC_ALL=C sort -z | xargs -0 -r sha256sum) | sha256sum | cut -c1-64; }
atomic_write() {  # atomic_write <path> <content>; set -e safe, never leaves its temp file
  local t="$1.tmp.$$"
  if printf '%s\n' "$2" > "$t" && mv -- "$t" "$1"; then return 0; fi
  rm -f -- "$t"; return 1
}
# ts/read_sha/list_gen/manifest are only ever called inside $(...), so their "exec 9>&-" closes the lock fd in that
# subshell only (never in the main shell).
ts() { exec 9>&-; date -u +%Y%m%dT%H%M%SZ; }
read_sha() { exec 9>&-; [ -f "$1" ] && head -n1 -- "$1" || true; }
backup_set() { # backup_set <dir> <sha>: name a dir as a backup generation (sha file first, then the dir)
  local n="$WR/dist.prev.$(ts).$$"
  atomic_write "$n.BUILD_SHA" "${2:-unknown}" || return 1
  mv -- "$1" "$n" || { rm -f -- "$n.BUILD_SHA"; return 1; }
  echo "refresh_dist: previous build kept as $n (sha ${2:-unknown})"
}
list_gen() { # list_gen <pattern>: generation dirs newest first; empty output (rc 0) when there are none
  exec 9>&-; local d; for d in "$WR/$1".*; do
    [ -d "$d" ] || continue
    case "$d" in *.BUILD_SHA|*.tmp.*) continue ;; esac
    printf '%s\n' "$d"
  done | LC_ALL=C sort -r
}
prune() { # keep newest $2 of pattern $1 (dirs + their .BUILD_SHA); safe under set -e/pipefail with zero matches
  local d n=0
  while IFS= read -r d; do
    [ -n "$d" ] || continue
    n=$((n + 1)); [ "$n" -gt "$2" ] || continue
    rm -rf -- "$d" "$d.BUILD_SHA"
  done <<< "$(list_gen "$1")"
  return 0
}
set_sha() { # set_sha <sha|unknown|''>: write wr/BUILD_SHA, or remove it when the recorded sha was unknown/empty
  if [ -z "$1" ] || [ "$1" = unknown ]; then rm -f -- "$WR/BUILD_SHA"; else atomic_write "$WR/BUILD_SHA" "$1"; fi
}
preflight_exchange() { # fail before any build/swap if this mv / filesystem cannot exchange atomically
  local a="$WR/.xchk.$$.a" b="$WR/.xchk.$$.b" ok=0
  rm -rf -- "$a" "$b"; mkdir -- "$a" "$b" && touch -- "$a/A" "$b/B" || { rm -rf -- "$a" "$b"; return 1; }
  if mv --exchange -T -- "$a" "$b" 2>/dev/null && [ -e "$a/B" ] && [ -e "$b/A" ]; then ok=1; fi
  rm -rf -- "$a" "$b"
  [ "$ok" -eq 1 ]
}

# ---- lock + crash recovery (only while holding the lock) ----
exec 9> "$WR/.refresh.lock"
flock -w 30 9 || die "another refresh_dist.sh holds $WR/.refresh.lock (waited 30s)"

recover() {
  local j stage old new nm pid bk good cur bm f bd
  for j in "$WR"/.dist.new.*.journal; do
    [ -e "$j" ] || continue
    stage="${j%.journal}"; old="$(sed -n 1p "$j")"; new="$(sed -n 2p "$j")"; nm="$(sed -n 3p "$j")"
    if [ -d "$WR/dist" ] && [ "$(manifest "$WR/dist")" = "$nm" ]; then
      echo "refresh_dist: recovery: $j - swap had happened; completing (live = $new)" >&2
      atomic_write "$WR/BUILD_SHA" "$new" || return 1
      if [ -d "$stage" ]; then
        if [ "$old" = "$new" ] || [ -z "$(ls -A -- "$stage")" ]; then rm -rf -- "$stage"; else backup_set "$stage" "$old" || return 1; fi
      fi
    else
      echo "refresh_dist: recovery: $j - swap had not happened (or was swapped back); restoring BUILD_SHA=$old, discarding staged copy" >&2
      set_sha "$old" || return 1
      rm -rf -- "$stage"
    fi
    rm -f -- "$j"
  done
  j="$WR/.rollback.journal"
  if [ -e "$j" ]; then
    bk="$(sed -n 1p "$j")"; good="$(sed -n 2p "$j")"; cur="$(sed -n 3p "$j")"; bm="$(sed -n 4p "$j")"
    if [ -d "$WR/dist" ] && [ "$(manifest "$WR/dist")" = "$bm" ]; then
      echo "refresh_dist: recovery: rollback had swapped; completing (live = $good)" >&2
      atomic_write "$WR/BUILD_SHA" "$good" || return 1
      if [ -d "$bk" ]; then
        local rb="$WR/dist.rolledback.$(ts).$$"
        atomic_write "$rb.BUILD_SHA" "$cur" && mv -- "$bk" "$rb" && rm -f -- "$bk.BUILD_SHA" || return 1
      fi
    else
      echo "refresh_dist: recovery: rollback had not swapped (or was swapped back); restoring BUILD_SHA=$cur" >&2
      set_sha "$cur" || return 1
    fi
    rm -f -- "$j"
  fi
  # stale staging / temp files with no journal: nothing live in them
  for stage in "$WR"/.dist.new.*; do
    case "$stage" in *.journal) continue ;; esac
    [ -e "$stage" ] && [ ! -e "$stage.journal" ] && { echo "refresh_dist: removing stale $stage" >&2; rm -rf -- "$stage"; }
  done
  for f in "$WR"/dist.prev.*.BUILD_SHA "$WR"/dist.rolledback.*.BUILD_SHA; do
    [ -e "$f" ] && [ ! -d "${f%.BUILD_SHA}" ] && rm -f -- "$f"
  done
  rm -f -- "$WR"/BUILD_SHA.tmp.* "$WR"/dist.prev.*.BUILD_SHA.tmp.* "$WR"/dist.rolledback.*.BUILD_SHA.tmp.* \
           "$WR"/.rollback.journal.tmp.* 2>/dev/null
  rm -rf -- "$WR"/.xchk.* 2>/dev/null
  # build clones of killed runs (recorded in wr/.awibuild.<pid>); removed unless a (orphaned) process still uses them
  rm -f -- "$WR"/.awibuild.*.tmp.* 2>/dev/null   # half-written markers: their clone is unrecorded -> quarantined below
  for f in "$WR"/.awibuild.*; do
    [ -e "$f" ] || continue
    bd="$(head -n1 -- "$f" 2>/dev/null || true)"
    if is_clone "$bd" && [ -d "$bd" ]; then
      if in_use "$bd"; then echo "refresh_dist: build clone $bd is still used by a process; keeping it and $f for a later run" >&2; continue; fi
      echo "refresh_dist: removing stale build clone $bd" >&2; rm -rf -- "$bd" || return 1
    fi
    rm -f -- "$f"
  done
  quarantine_orphans
  return 0
}
is_clone() { [[ "$1" =~ ^"$BROOT"/awibuild\.[A-Za-z0-9]{4,}$ ]]; }
in_use() { # in_use <dir>: some live process has its cwd or an open fd inside <dir>
  [ -n "$(command find /proc -mindepth 2 -maxdepth 3 \( -path '/proc/[0-9]*/cwd' -o -path '/proc/[0-9]*/fd/*' \) \
          \( -lname "$1" -o -lname "$1/*" \) -print -quit 9>&- 2>/dev/null)" ]
}
recorded() { # recorded <dir>: a marker wr/.awibuild.<pid> names <dir>
  local m; for m in "$WR"/.awibuild.*; do
    [ -f "$m" ] || continue; case "$m" in *.tmp.*) continue ;; esac
    [ "$(head -n1 -- "$m" 2>/dev/null || true)" = "$1" ] && return 0
  done; return 1
}
quarantine_orphans() { # move (never delete) unrecorded, unused awibuild.* dirs owned by us into $QDIR; warnings only
  local d q
  for d in "$BROOT"/awibuild.*; do
    [ -d "$d" ] && [ ! -L "$d" ] && [ -O "$d" ] && is_clone "$d" || continue
    [ "$d" != "${B:-}" ] || continue
    recorded "$d" && continue
    if in_use "$d"; then echo "refresh_dist: unrecorded build clone $d is in use by a process; leaving it" >&2; continue; fi
    mkdir -p -m 700 -- "$QDIR" || { echo "refresh_dist: warning: cannot create $QDIR; leaving $d" >&2; continue; }
    q="$QDIR/${d##*/}"; [ ! -e "$q" ] || q="$q.$(ts).$$"
    mv -n -T -- "$d" "$q" 2>/dev/null || true
    if [ ! -e "$d" ] && [ -d "$q" ]; then echo "refresh_dist: quarantined unrecorded build clone $d -> $q (not deleted)" >&2
    else echo "refresh_dist: warning: could not quarantine $d (left in place)" >&2; fi
  done
  return 0
}
quarantine_legacy() { # opt-in: move only the named legacy $AWI_TMP_ROOT/awibuild.<name> dirs; never delete
  local n d q rc=0
  for n in "${LNAMES[@]}"; do
    d="$LROOT/awibuild.$n"
    if [ -L "$d" ] || [ ! -d "$d" ]; then echo "refresh_dist: legacy $d: not a directory (or a symlink); skipped" >&2; rc=1; continue; fi
    [ -O "$d" ] || { echo "refresh_dist: legacy $d: not owned by you; skipped" >&2; rc=1; continue; }
    if in_use "$d"; then echo "refresh_dist: legacy $d is in use by a process; skipped" >&2; rc=1; continue; fi
    mkdir -p -m 700 -- "$LQDIR" || { echo "refresh_dist: cannot create $LQDIR" >&2; return 1; }
    q="$LQDIR/awibuild.$n"; [ ! -e "$q" ] || q="$q.$(ts).$$"
    mv -n -T -- "$d" "$q" 2>/dev/null || true
    if [ ! -e "$d" ] && [ -d "$q" ]; then echo "refresh_dist: legacy quarantined $d -> $q (not deleted)"
    else echo "refresh_dist: legacy $d: could not move (left in place)" >&2; rc=1; fi
  done
  return $rc
}
if [ "$MODE" = legacy ]; then
  quarantine_legacy && { echo "refresh_dist: quarantine-legacy OK (only took wr/.refresh.lock, creating it if absent; wr contents not touched)"; exit 0; }
  die "quarantine-legacy: some names were skipped (see above); nothing was deleted"
fi
recover || die "crash recovery failed; inspect $WR (journals .dist.new.*.journal / .rollback.journal)"
if [ "$MODE" = recover ]; then echo "refresh_dist: recover OK (BUILD_SHA=$(read_sha "$WR/BUILD_SHA"))"; exit 0; fi
preflight_exchange || die "mv --exchange is not supported here (needs GNU coreutils >= 9.5 and renameat2 RENAME_EXCHANGE on $WR's filesystem); nothing built, wr unchanged"

B=""; STAGE=""; JOURNAL=""; EXCHANGED=0; BACKED=0; OLDLOC=""; OLD_SHA=""; DONE=0; RESTORE_FAIL=0
cleanup() {
  local rc=$?
  set +e
  if [ "$rc" -ne 0 ] && [ "$DONE" -eq 0 ] && [ "$EXCHANGED" -eq 1 ]; then
    echo "refresh_dist: failure after swap - swapping previous build back" >&2
    if mv --exchange -T -- "$OLDLOC" "$WR/dist"; then
      if [ "$MODE" = refresh ]; then   # $OLDLOC now holds the rejected new build
        rm -rf -- "$OLDLOC" || loud "could not remove $OLDLOC"
        if [ "$BACKED" -eq 1 ]; then rm -f -- "$OLDLOC.BUILD_SHA" || loud "could not remove $OLDLOC.BUILD_SHA"; fi
      fi                                # rollback mode: $OLDLOC is the backup again, keep it
      local try sha_ok=0
      for try in 1 2 3; do set_sha "$OLD_SHA" && { sha_ok=1; break; }; sleep 1; done
      # journal is kept on failure: --recover then sees "not swapped" and restores BUILD_SHA from it (exit != 0 here)
      [ "$sha_ok" -eq 1 ] || loud "could not restore BUILD_SHA=${OLD_SHA:-<none>} (3 tries); wr/dist is the OLD build"
      [ "$RESTORE_FAIL" -ne 0 ] || rm -f -- "$JOURNAL"
    else
      loud "swap-back of $OLDLOC <-> $WR/dist failed; wr/dist holds the NEW build, old build is at $OLDLOC"
    fi
  elif [ -n "$JOURNAL" ] && [ "$EXCHANGED" -eq 0 ]; then
    [ -n "$STAGE" ] && rm -rf -- "$STAGE"
    rm -f -- "$JOURNAL"
  elif [ "$DONE" -eq 0 ] && [ -n "$STAGE" ] && [ "$EXCHANGED" -eq 0 ]; then
    rm -rf -- "$STAGE"
  fi
  if [ -n "$B" ] && is_clone "$B"; then if rm -rf -- "$B"; then rm -f -- "$WR/.awibuild.$$"; else echo "refresh_dist: warning: could not remove $B" >&2; fi; fi
  [ "$RESTORE_FAIL" -eq 0 ] || echo "refresh_dist: !!! state needs attention: run refresh_dist.sh --recover !!!" >&2
  [ -d "$WR/dist" ] || echo "refresh_dist: !!! $WR/dist MISSING !!!" >&2
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 129' HUP; trap 'exit 130' INT; trap 'exit 143' TERM   # run cleanup (incl. build clone removal) on signals

if [ "$MODE" = rollback ]; then
  BK=""; GOOD=""; NB=0
  while IFS= read -r c; do
    [ -n "$c" ] || continue; NB=$((NB + 1))
    s="$(read_sha "$c.BUILD_SHA")"
    if ! [[ "$s" =~ ^[0-9a-f]{40}$ ]]; then echo "refresh_dist: skipping backup $c (BUILD_SHA '${s:-<missing>}' is not a valid sha)" >&2; continue; fi
    if [ -z "$(ls -A -- "$c")" ]; then echo "refresh_dist: skipping backup $c (empty)" >&2; continue; fi
    BK="$c"; GOOD="$s"; break
  done <<< "$(list_gen dist.prev)"
  [ "$NB" -gt 0 ] || die "no backup dist.prev.* in $WR"
  [ -n "$BK" ] || die "no backup in $WR has a valid 40-hex BUILD_SHA and content (all $NB skipped); see RUNBOOK for hand restore"
  [ -d "$WR/dist" ] || die "$WR/dist missing; restore by hand: mv $BK $WR/dist"
  OLD_SHA="$(read_sha "$WR/BUILD_SHA")"; BM="$(manifest "$BK")"
  echo "refresh_dist: rolling back to $BK (sha $GOOD); current ${OLD_SHA:-none}"
  JOURNAL="$WR/.rollback.journal"
  atomic_write "$JOURNAL" "$BK
$GOOD
${OLD_SHA:-unknown}
$BM" || die "could not write journal"
  OLDLOC="$BK"; BACKED=1
  mv --exchange -T -- "$BK" "$WR/dist" || die "swap failed"
  EXCHANGED=1
  atomic_write "$WR/BUILD_SHA" "$GOOD" || die "BUILD_SHA write failed"
  [ "$(manifest "$WR/dist")" = "$BM" ] || die "restored dist does not match backup"
  [ "$(read_sha "$WR/BUILD_SHA")" = "$GOOD" ] || die "BUILD_SHA mismatch after rollback"
  RB="$WR/dist.rolledback.$(ts).$$"
  atomic_write "$RB.BUILD_SHA" "${OLD_SHA:-unknown}" || die "could not write $RB.BUILD_SHA"
  mv -- "$BK" "$RB" || { rm -f -- "$RB.BUILD_SHA"; die "could not move replaced build aside"; }
  DONE=1
  rm -f -- "$BK.BUILD_SHA" "$JOURNAL"
  prune dist.rolledback 3
  echo "refresh_dist: ROLLBACK OK wr/dist = $GOOD (replaced build kept at $RB). Not deployed."
  exit 0
fi

# ---- refresh: everything below until the swap touches only $B and a staging dir ----
mkdir -p -m 700 -- "$BROOT"
B="$(mktemp -d "$BROOT/awibuild.XXXX")"
is_clone "$B" || { B=""; die "bad temp dir"; }
# kill -9 between mktemp and the mv below leaves an unrecorded clone: the next run / --recover quarantines it
atomic_write "$WR/.awibuild.$$" "$B" || die "could not record build clone"   # temp file + mv: never a partial marker

git clone -q -- "$REPO_URL" "$B/repo" 9>&-
git -C "$B/repo" cat-file -e "$SITE_SHA^{commit}" 9>&- 2>/dev/null || die "commit $SITE_SHA not found in $REPO_URL"
git -C "$B/repo" checkout -q --detach "$SITE_SHA" 9>&-
[ "$(git -C "$B/repo" rev-parse HEAD 9>&-)" = "$SITE_SHA" ] || die "checked-out HEAD != SITE_SHA"

(exec 9>&-; cd "$B/repo" && python3 build.py) || die "build failed"   # the build never holds the lock fd
[ -d "$B/repo/dist" ] && [ -n "$(ls -A -- "$B/repo/dist")" ] || die "build produced no or an empty dist/"
(exec 9>&-; cd "$B/repo" && bash run_tests.sh) || die "run_tests.sh failed"
[ -d "$B/repo/dist" ] && [ -n "$(ls -A -- "$B/repo/dist")" ] || die "dist/ missing or empty after tests"
# rev8 (AWI-SIGNUP-FORM-001 backend): compile functions/ into dist/_worker.js/ + dist/_routes.json AFTER run_tests.sh
# (the dist guards would flag the bundled Beehiiv URL) and BEFORE the manifest, so the atomic swap, backups and --rollback
# cover the Functions too and `wrangler pages deploy dist` from wr ships them. Local compile only: no network, no account.
WRANGLER="$WR/node_modules/.bin/wrangler"
if [ -d "$B/repo/functions" ]; then
  [ -x "$WRANGLER" ] || die "functions/ present but $WRANGLER missing (npm ci in $WR)"
  [ ! -e "$B/repo/dist/_worker.js" ] && [ ! -e "$B/repo/dist/_routes.json" ] || die "build already produced dist/_worker.js or dist/_routes.json"
  (exec 9>&-; cd "$B/repo" && WRANGLER_SEND_METRICS=false "$WRANGLER" pages functions build functions \
      --outdir "$B/repo/dist/_worker.js" --output-routes-path "$B/repo/dist/_routes.json" --compatibility-date 2026-10-01) \
    || die "pages functions build failed"
  [ -s "$B/repo/dist/_worker.js/index.js" ] || die "no dist/_worker.js/index.js after functions build"
  python3 - "$B/repo/dist/_routes.json" <<'PY' 9>&- || die "_routes.json is not exactly /api/subscribe + /api/signups/export.csv"
import json, sys
r = json.load(open(sys.argv[1]))
assert r.get("version") == 1 and sorted(r.get("include", [])) == ["/api/signups/export.csv", "/api/subscribe"] and r.get("exclude") == [], r
PY
  echo "refresh_dist: functions compiled into dist/_worker.js (routes: /api/subscribe, /api/signups/export.csv)"
else
  echo "refresh_dist: no functions/ at $SITE_SHA; static-only dist"
fi
NM="$(manifest "$B/repo/dist")"

STAGE="$WR/.dist.new.$$"          # same filesystem as wr/dist
mkdir -- "$STAGE"
"$CP" -a -- "$B/repo/dist/." "$STAGE/" 9>&- || die "copy into staging dir failed"
diff -r -- "$B/repo/dist" "$STAGE" >/dev/null || die "staged dist differs from fresh build"
[ "$(manifest "$STAGE")" = "$NM" ] || die "staged manifest mismatch"

OLD_SHA="$(read_sha "$WR/BUILD_SHA")"
[ -z "$OLD_SHA" ] || [[ "$OLD_SHA" =~ ^[0-9a-f]{40}$ ]] || echo "refresh_dist: note: current BUILD_SHA '$OLD_SHA' is not a sha" >&2
if [ ! -e "$WR/dist" ]; then mkdir -- "$WR/dist"; fi   # first run: empty placeholder so the exchange is atomic

JOURNAL="$STAGE.journal"
atomic_write "$JOURNAL" "${OLD_SHA:-unknown}
$SITE_SHA
$NM" || die "could not write journal"

OLDLOC="$STAGE"
mv --exchange -T -- "$STAGE" "$WR/dist" || die "atomic swap failed"   # live dist = new; $STAGE = old
EXCHANGED=1
atomic_write "$WR/BUILD_SHA" "$SITE_SHA" || die "BUILD_SHA write failed"
diff -r -- "$B/repo/dist" "$WR/dist" >/dev/null || die "wr/dist differs from fresh build"
[ "$(read_sha "$WR/BUILD_SHA")" = "$SITE_SHA" ] || die "wr/BUILD_SHA mismatch"

if [ "$OLD_SHA" = "$SITE_SHA" ] || [ -z "$(ls -A -- "$STAGE")" ]; then
  DONE=1; rm -rf -- "$STAGE"; echo "refresh_dist: no backup made (previous build was the same sha or empty)"
else
  n="$WR/dist.prev.$(ts).$$"
  atomic_write "$n.BUILD_SHA" "${OLD_SHA:-unknown}" || die "could not write backup sha file"
  mv -- "$STAGE" "$n" || { rm -f -- "$n.BUILD_SHA"; die "could not move previous build to backup"; }
  OLDLOC="$n"; BACKED=1
  DONE=1
  echo "refresh_dist: previous build kept as $n (sha ${OLD_SHA:-unknown})"
fi
rm -f -- "$JOURNAL"
prune dist.prev 3
echo "refresh_dist: OK wr/dist = tested build of $SITE_SHA ($(find "$WR/dist" -type f | wc -l) files). Not deployed."
