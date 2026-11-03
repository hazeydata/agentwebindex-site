#!/bin/bash
# rev8 sandbox tests for the refresh_dist functions block. Usage: test_rev8_functions.sh <site worktree with functions/ + signup/>
# Builds a throwaway fixture repo + sandbox wr under one mktemp -d dir in $AWI_TMP_ROOT, runs rev8/refresh_dist.sh with
# AWI_TEST=1, and removes exactly that dir at the end. The live wr is only read (node_modules copied, never written).
SITE="${1:?site worktree}"
R8="$(cd "$(dirname "$0")" && pwd -P)"; RD="$R8/refresh_dist.sh"
: "${AWI_DEPLOY_ROOT:?set AWI_DEPLOY_ROOT}"; : "${AWI_TMP_ROOT:?set AWI_TMP_ROOT}"; export AWI_DEPLOY_ROOT AWI_TMP_ROOT
SBX="$(mktemp -d $AWI_TMP_ROOT/awi8.XXXX)" || exit 9
echo "sandbox: $SBX (mode $(stat -c %a "$SBX"))"
WR="$SBX/wr"; SRC="$SBX/src"; mkdir -p "$WR" "$SRC" "$SBX/xdg"
cp -a $AWI_DEPLOY_ROOT/wr/node_modules $AWI_DEPLOY_ROOT/wr/package.json "$WR/"
export AWI_TEST=1 AWI_WR="$WR" AWI_REPO_URL="$SRC" XDG_CONFIG_HOME="$SBX/xdg" WRANGLER_SEND_METRICS=false
PASS=0; FAIL=0
ok(){ if eval "$2"; then echo "PASS $1"; PASS=$((PASS+1)); else echo "FAIL $1   [$2]"; FAIL=$((FAIL+1)); fi; }
man(){ (cd "$1" && find . \( -type f -o -type l \) -print0 | LC_ALL=C sort -z | xargs -0 -r sha256sum) | sha256sum | cut -c1-64; }
run(){ echo "--- refresh_dist.sh $*"; bash "$RD" "$@" > "$SBX/out" 2>&1; local rc=$?; sed 's/^/    /' "$SBX/out"; echo "    rc=$rc"; return $rc; }
G(){ git -C "$SRC" -c user.name=t -c user.email=t@t "$@"; }
commit(){ G add -A >/dev/null && G commit -qm "$1" && G rev-parse HEAD; }

# fixture: build.py writes dist/index.html with a marker; run_tests.sh passes
G init -q
cat > "$SRC/build.py" <<'PY'
import os, pathlib
d = pathlib.Path("dist"); d.mkdir(exist_ok=True)
(d / "index.html").write_text("<p>build " + pathlib.Path("MARK").read_text().strip() + "</p>\n")
if pathlib.Path("PRE_ROUTES").exists(): (d / "_routes.json").write_text("{}")
PY
echo 'exit 0' > "$SRC/run_tests.sh"
echo A > "$SRC/MARK"; A=$(commit "A static-only")
cp -a "$SITE/functions" "$SITE/signup" "$SRC/"; echo B > "$SRC/MARK"; B=$(commit "B with functions")
echo 'export const onRequest = ( => ;' > "$SRC/functions/api/subscribe.js"; echo C > "$SRC/MARK"; C=$(commit "C broken functions")
cp -a "$SITE/functions/api/subscribe.js" "$SRC/functions/api/subscribe.js"
sed -i 's|=> handleSubscribe(|=> (globalThis.awiMark = "b2-marker", handleSubscribe)(|' "$SRC/functions/api/subscribe.js"   # a string esbuild keeps
grep -q b2-marker "$SRC/functions/api/subscribe.js" || { echo "fixture B2 marker not applied"; exit 9; }
echo B2 > "$SRC/MARK"; B2=$(commit "B2 functions changed")
touch "$SRC/PRE_ROUTES"; echo D > "$SRC/MARK"; D=$(commit "D build emits _routes.json")

echo "== T1 static-only commit (no functions/)"
run "$A"; rcA=$?; ok "T1 refresh A ok" '[ $rcA -eq 0 ]'
ok "T1 says static-only" 'grep -q "no functions/ at $A; static-only dist" "$SBX/out"'
ok "T1 no _worker.js/_routes.json" '[ ! -e "$WR/dist/_worker.js" ] && [ ! -e "$WR/dist/_routes.json" ]'
MA=$(man "$WR/dist")

echo "== T2 functions compile into dist"
run "$B"; rcB=$?; ok "T2 refresh B ok" '[ $rcB -eq 0 ]'
ok "T2 dist/_worker.js/index.js non-empty" '[ -s "$WR/dist/_worker.js/index.js" ]'
ok "T2 _routes.json is exactly the 2 routes" 'python3 -c "import json,sys; r=json.load(open(sys.argv[1])); assert r[\"version\"]==1 and sorted(r[\"include\"])==[\"/api/signups/export.csv\",\"/api/subscribe\"] and r[\"exclude\"]==[], r" "$WR/dist/_routes.json"'
ok "T2 worker bundles both handlers" 'grep -q handleSubscribe "$WR/dist/_worker.js/index.js" && grep -q "X-Export-Token\|x-export-token" "$WR/dist/_worker.js/index.js"'
ok "T2 BUILD_SHA=B" '[ "$(head -1 "$WR/BUILD_SHA")" = "$B" ]'
ok "T2 static index from B" 'grep -q "build B" "$WR/dist/index.html"'
MB=$(man "$WR/dist")

echo "== T3 broken functions fail the run, live dist untouched"
run "$C"; rcC=$?; ok "T3 refresh C fails" '[ $rcC -ne 0 ]'
ok "T3 failure is the functions build" 'grep -q "STOP: pages functions build failed" "$SBX/out"'
ok "T3 live dist unchanged (= B)" '[ "$(man "$WR/dist")" = "$MB" ] && [ "$(head -1 "$WR/BUILD_SHA")" = "$B" ]'
ok "T3 no build clone or stage left" '[ -z "$(ls -A "$WR/.builds" | grep -v "^quarantine$")" ] && ! ls -d "$WR"/.dist.new.* >/dev/null 2>&1'

echo "== T4 build that already emits _routes.json is refused"
run "$D"; rcD=$?; ok "T4 refresh D fails" '[ $rcD -ne 0 ] && grep -q "build already produced dist/_worker.js or dist/_routes.json" "$SBX/out"'
ok "T4 live dist unchanged (= B)" '[ "$(man "$WR/dist")" = "$MB" ]'

echo "== T5 --rollback restores the previous dist (with its worker), then the static one"
run "$B2"; rcB2=$?; ok "T5 refresh B2 ok" '[ $rcB2 -eq 0 ] && [ "$(man "$WR/dist")" != "$MB" ] && grep -q b2-marker "$WR/dist/_worker.js/index.js"'
run --rollback; rcR=$?; ok "T5 rollback ok" '[ $rcR -eq 0 ]'
ok "T5 dist = B exactly (incl. _worker.js, _routes.json)" '[ "$(man "$WR/dist")" = "$MB" ] && [ -s "$WR/dist/_worker.js/index.js" ] && ! grep -q b2-marker "$WR/dist/_worker.js/index.js"'
ok "T5 BUILD_SHA=B" '[ "$(head -1 "$WR/BUILD_SHA")" = "$B" ]'
run --rollback; rcR2=$?; ok "T5 second rollback ok -> A" '[ $rcR2 -eq 0 ] && [ "$(man "$WR/dist")" = "$MA" ] && [ "$(head -1 "$WR/BUILD_SHA")" = "$A" ]'
ok "T5 A has no worker" '[ ! -e "$WR/dist/_worker.js" ] && [ ! -e "$WR/dist/_routes.json" ]'

echo "== T6 functions/ present but wrangler missing -> STOP"
mv "$WR/node_modules" "$SBX/nm.aside"
run "$B"; rcW=$?; ok "T6 no wrangler fails" '[ $rcW -ne 0 ] && grep -q "functions/ present but .* missing" "$SBX/out"'
mv "$SBX/nm.aside" "$WR/node_modules"
ok "T6 live dist unchanged (= A)" '[ "$(man "$WR/dist")" = "$MA" ]'

echo "RESULT: $PASS passed, $FAIL failed"
rm -rf -- "$SBX"; [ ! -e "$SBX" ] && echo "removed $SBX"
[ "$FAIL" -eq 0 ]
