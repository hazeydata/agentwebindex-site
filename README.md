# agentwebindex-site
Static site for AgentWebIndex (plain HTML/JS plus a small Python generator; no dependencies).

## Data: vendored copy (chosen as the simplest option)
The build reads **only** `data/` in this repo: a vendored copy of the `agentwebindex` repo's `data/`, plus
`data/_upstream/providers.json` and `data/_upstream/tos_matrix.yaml` (provider names and the
Brave terms exclusion note). Refresh it with `./sync_data.sh ../agentwebindex`, then commit. Nothing is fetched
at build time. Trade-off: the site only updates when the vendored copy is refreshed and committed (a scheduled
sync job or a submodule can replace this later).

## Run locally
```
python3 build.py
python3 -m http.server 8765 -d dist
```
Pages: leaderboard (search / scrape / browser tabs), price history (+ prices.csv / prices.json), methodology,
disclosures, newsletter (beehiiv embed when `site.config.json` → `beehiiv_embed_url` is set, otherwise a disabled
"Coming soon" form). It shows "No data yet" until real data exists.

## Deploy (Cloudflare Pages)
Build command `python3 build.py`, output directory `dist`, env `PYTHON_VERSION=3.12`. Not deployed yet.

License: MIT (code); data under data/ is CC BY 4.0 (data/LICENSE).
