#!/bin/bash
# AC 12: no secret value in the repo or dist/. Secrets come only from Pages env (BEEHIIV_API_KEY, IP_SALT, EXPORT_TOKEN).
# 1) no assignment of a literal to a secret name outside the test fixtures (whose fake values contain TEST);
# 2) dist/ never names a secret, the Beehiiv API host or an Authorization header;
# 3) if AWI_SECRET_PREFIX is set (e.g. by chief at deploy with the real key's prefix), 0 hits for it in repo + dist.
set -euo pipefail
cd "$(dirname "$0")/../.."
fail=0
hits=$(git ls-files -co --exclude-standard | grep -v '^data/' | xargs rg -n --no-heading -e "(BEEHIIV_API_KEY|IP_SALT|EXPORT_TOKEN)\s*[:=]\s*['\"][^'\"]+" 2>/dev/null | grep -v 'TEST' || true)
[ -z "$hits" ] || { echo "secret_scan FAIL literal secret:"; echo "$hits" | sed -E 's/(["'"'"'])[^"'"'"']{4}[^"'"'"']*/\1****/'; fail=1; }
if rg -l -e 'BEEHIIV_API_KEY|IP_SALT|EXPORT_TOKEN|api\.beehiiv\.com|Authorization' dist/ >/dev/null 2>&1; then echo "secret_scan FAIL: secret name in dist/"; fail=1; fi
if [ -n "${AWI_SECRET_PREFIX:-}" ]; then
  n=$( (git ls-files -co --exclude-standard | xargs rg -c -F -- "$AWI_SECRET_PREFIX" 2>/dev/null; rg -c -F -- "$AWI_SECRET_PREFIX" dist/ 2>/dev/null) | wc -l)
  [ "$n" = 0 ] || { echo "secret_scan FAIL: key prefix found in $n file(s)"; fail=1; }
fi
[ $fail = 0 ] && echo "secret_scan: 0 hits (repo + dist)"
exit $fail
