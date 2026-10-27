# agentwebindex-site
Static site for AgentWebIndex (plain HTML/CSS/JS plus a small stdlib-Python generator; no dependencies).

## Pages and nav
Built by `build.py` into `dist/`: Results `/`, Prices `/prices/`, Methodology `/methodology/`, Data `/data/`, plus Disclosures,
Sponsors, Newsletter and Tell us (`/tell-us/`). `nav.top` holds exactly four links (Results, Prices, Methodology, Data); Disclosures,
Sponsors, Newsletter, Tell us and the "For agents" links (latest.json, prices, llms.txt) are in the footer on every page.
- `src/*.html` are slot templates; `render.py` fills them. All static text comes verbatim from `content/copy.md` (via `copydoc.py`);
  numbers (pass rates, costs, latency, price dates) are computed from `data/benchmarks/latest.json` and `data/_upstream/pricing.yaml`
  through `prices.py` (`priced_*`, `price_rows`, `untested_providers`, `fmt_pct/usd/ms`, half-up rounding). Never from `data/prices/<pid>.json` `fetched_at`.
- Charts: the pinned SVGs in `src/charts/` are copied byte-identical to `dist/assets/charts/` and (R9, option c) inlined into `/` as four `<svg>` per chart, each in a `role="img"` wrapper whose `aria-label` is the QUERIES.md alt text, so the page's Inter/Space Grotesk woff2 fonts draw the chart `<text>`. Inlined markup = file minus the XML prolog/doctype, with ids, `href="#…"` and `url(#…)` prefixed per variant (`<name>-<width>-<scheme>--`; matplotlib's repeated unreferenced `wilson-ci` gid gets `--dupN`). The build fails on any duplicate id on a page. Each file's `<style>` (`*{stroke-linejoin: round; stroke-linecap: butt}`) is kept verbatim and so applies page-wide; it only affects SVG strokes. Four variants per chart
  (720/350 wide x light/dark); CSS shows one (>=768px the 720 file, below it the 350 file; dark default, light under
  `prefers-color-scheme: light` or the theme toggle). Never edit these files.
- Brand tokens (cyan `#5FC4D6`, olive `#616512`/`#8B901A`, Space Grotesk / Inter / IBM Plex Mono) are CSS variables at the top of `src/style.css`.
- Agent surfaces (`llms.txt`, `/data/*`, CSV) are unchanged; `llms.txt` additionally lists `/tell-us/`.
- Run-log links point to `hazeydata/agentwebindex` at the pinned data sha.

## Pins (`pins.json`)
One file records every pinned input: `data` (agentwebindex sha, ONE line), `copy` + `copy_sha256` (content/copy.md), `charts` +
`charts_sha256` (the 8 chart SVGs in src/charts; fonts are not byte-pinned), `queries` / `queries_sha256` / `chart_alt_sha256` (chart alt text, below), `layout` (visual-desk layout
spec, agentwebindex-meta 76b8b23), and `phase0_date` (2026-10-24).
`build.py` runs `pins.check()` first and exits non-zero if: the vendored `data/_upstream/SOURCE` sha differs from `data`; copy, chart-alt or chart
SVG bytes differ from their sha256; (R8) `data` is the pre-Phase-0 sha `6b8bd87d778b3fe0fe049f9274796ab498928cc5` (`pins.STALE_DATA_SHA`); or any Tavily input date
(every `checked_at` / `verified_date` at any depth under `providers.tavily`) in the vendored `bench/pricing.yaml` (the pricing file at the pinned data sha) is before `phase0_date`. When `AWI_DATA_REPO` points at a local agentwebindex clone, the build also checks that the vendored `pricing.yaml` is byte-identical to `bench/pricing.yaml` at the pin (`git show`); without it that cross-check is skipped.
Re-pin data: `./sync_data.sh <full 40-hex agentwebindex sha> [repo-url-or-path] [recorded-url]` (re-vendors `data/`, writes `data/_upstream/SOURCE`, and regenerates
`tests/data_pin_manifest.json` through `tools/data_manifest.py`), then edit `pins.json` `data` to the same sha. `data/_upstream/SOURCE` always records a URL, never a local path: with a local clone as the second
argument it records the third argument, else `$AWI_RECORD_URL`, else `https://github.com/hazeydata/agentwebindex.git`. A sha that is on no branch
(a PR head) is fetched by sha. Current pin: data `303efdf4` (agentwebindex main, merge commit of #25 whose head 8ab7ccc re-verified Tavily 2026-10-24).
Charts pin: agentwebindex-meta `b748147` (350 variants re-rendered so chart text is >=12px at 390; `cycles/2026-10-24-page-redo/her/her-*.svg`, re-rendered at data 303efdf4; source line checked by `test_chart_source_line_names_data_pin`; titles removed from the SVGs, root `role=img` + `aria-label`; no hard-coded heights). Copy pin: `AWI-PAGE-POLISH-001 copy-cuts.md`.
Re-pin copy/charts: replace `content/copy.md`, `content/chart-alt.md` or `src/charts/*` and update the sha256 values in `pins.json`.
Never hand-edit `data/`.
- `content/chart-alt.md` holds only the `## Alt text` section of Her?'s `QUERIES.md` (agentwebindex-meta 2c28c0a, `cycles/2026-10-24-page-redo/her/QUERIES.md`),
  copied byte-for-byte under one header comment line naming the source. The full original is not vendored (it names a local checkout path); `queries_sha256`
  is the sha256 of that full file, `chart_alt_sha256` of `chart-alt.md`.
- Layout pin 76b8b23 (agentwebindex-meta#8): its only change that touches the build is that each Prices row's date is the oldest input `cost.py` uses
  for that provider, which `prices.py` already does (`priced_tier_checked_at`).
- Only each provider's entry tier is priced. Tavily's Project/Bootstrap/Startup/Growth tiers are not shown (backlog for a later pricing cycle), and no page
  makes a 'cheapest tier covering 100k/month' claim (both are tested over `dist/`).

### AC19 (`ms</`)
AC19 requires `dist/index.html` to contain no literal `ms</`, and the verbatim Browserless sub-label ends in "terms". Any closing tag right after it would
form `ms</`, and the copy cannot change. `render.py` `results_row` therefore puts a trailing newline inside the sub-label `<span>`: invisible whitespace, no extra
element, and the copy test (which collapses whitespace) still matches. A `<wbr>` or empty element would also work but adds markup for no reader benefit, so the
newline stays; if AC19 is ever reworded to ignore whitespace-separated closings, delete it.

## Run locally
```
python3 build.py
python3 -m http.server 8765 -d dist
bash run_tests.sh
python3 -m tests.test_ship
```
- `run_tests.sh`: build, JS smoke test (`tests/app_smoke.js`, theme toggle), `tests/run_dist.py` (requires exactly `EXPECTED` tests in
  `tests/test_dist.py` and exactly `EXPECTED_CANARIES` canaries that inject real defects and must be caught; bump the counts by hand when
  tests change), `tests/test_dist.py` (set `AWI_DATA_REPO` to a local agentwebindex clone and the pre-Phase-0 pin test re-vendors a real 6b8bd87 tree with `sync_data.sh` in a temp copy; without it the case is built by editing the temp copy's SOURCE and pins.json), then `tests/browser_check.py` (headless Chrome over the DevTools protocol: one visible chart variant
  per chart at 390/720/1440 in both colour schemes, hidden variants display:none, role=img + alt-text name, served chart SVG bytes vs pinned sha256, C2 stacked under C1; per chart, ONE non-title Inter `<text>` element is checked: computed font-family Inter via document.fonts and rendered in Inter with no fallback font (CDP CSS.getPlatformFontsForNode); chart titles are not in the SVGs (since e18a54a they are the `<h3>` only); id rename leaves every element's text and box unchanged vs the original file markup; no sideways scroll, body >=16px and
  tap targets >=44px at 390px; then `check_layout` (above); screenshots go to a temp /tmp/awi-shots.* dir that is deleted on exit and included in the leftover check (M7) unless AWI_KEEP_SHOTS=1, which keeps it and prints the path; prints SKIP without Chrome).
- `tests/test_ship.py`: SHIP gates, run separately, all must pass: `test_no_placeholders` (no `[[LINDSAY-PLACEHOLDER]]` in dist), Tavily price equals
  pricing.yaml, `test_tavily_date_is_phase0` (R3: rendered Tavily date == 2026-10-24) and `test_data_pin_moved` (R4/R8: pin is not 6b8bd87, no Tavily input before `phase0_date`).
- `tests/agent_surface_baseline.json`: hashes of the agent surfaces main's code (60a8f4b) builds from the pinned data (regenerated at 8ab7ccc and carried to 303efdf4, whose data files are identical, by building
  main's code on the new data). Against the 6b8bd87 baseline the only change is `data/benchmarks/latest.json` (three Tavily `cost_units_note` check dates,
  2026-10-19 to 2026-10-24); the site's `llms.txt` differs from main's only by the added `/tell-us/` entry.

Fonts: all self-hosted as woff2 under `/assets/fonts/` (`src/fonts/`), licensed SIL OFL 1.1, one notice per family: `src/fonts/OFL-Inter.txt`, `OFL-SpaceGrotesk.txt`, `OFL-IBMPlexMono.txt` (copyright lines taken from each font's name table). IBM Plex Mono 400/500/600 are the upstream Latin files.
Inter 400/600/700 and Space Grotesk 600 (`inter-{400,600,700}-latin.woff2`, `space-grotesk-600-latin.woff2`, 17.3, 17.9, 17.9 and 10.9 KB) were subset from the TrueType fonts
of the 2c28c0a charts with fontTools, Latin range. Those TrueType files are not in the repo or in `dist/`. Weights kept are the ones the CSS uses (Inter 700 is the default `<b>` weight).
Charts (R9 supersedes the R8 font bullet; AC14): `dist/assets/charts` holds exactly the 8 pinned SVGs, byte-identical, and the same markup is inlined on `/`; fonts are not byte-checked. A test fails if any font file in the repo
(`git ls-files`) or in `dist/` is over 100 KB (102,400 bytes) or is a TrueType/OpenType file.
Newsletter: a first-party signup form (AWI-SIGNUP-FORM-001, see "Signup" below) in the Results hero card (`aside#signup-top`, first screenful),
in the Results end box (`#signup-end`) and on `/newsletter/` (`#signup`). No Beehiiv iframe, loader or other third-party script (the earlier
`beehiiv_embed_url` iframe is gone; the site's only external script is the pre-existing GoatCounter analytics).

Page polish (AWI-PAGE-POLISH-001):
- CTA boxes: every page except Newsletter has a hero card (`aside.cta.cta-hero`, 2-column hero at >=768px, compact row at 390) and/or an
  end box (`.cta.cta-end`). On Results the hero card holds the signup form itself; every other hero signup button links to
  `/newsletter/` (`test_hero_button_target`). Data and Disclosures hero cards are not signups (`.cta-info`): Data holds the latest.json/latest.csv
  buttons, Disclosures the Open an issue / Email links, each under one lead-in from copy-cuts "Hero card lead-ins" (`test_hero_lead_ins_from_copy_cuts`). Lead-ins and the button label come from the `## CTA boxes` section of `content/copy.md`; the button text is
  exactly "Get the results by email" on every page (`test_cta_label_same_on_every_page`). Buttons use `--acc` with `--on-acc` text, links `--link`; brand, nav current and the h1 underline use `--acc-tint`;
  the skip link uses `--acc`/`--on-acc`. `--cyan` is only for charts and focus outlines (`test_cyan_only_charts_and_focus`).
- Methodology: each step is `<li id="m-…"><h2>label</h2><p>text</p></li>` in a `56px minmax(0, 68ch)` grid with every child in column 2. The old
  `<b>label</b> text` markup put the bare text node into the 48px number column as an anonymous grid item (~55px wide paragraphs).
- Layout: 64px section padding (48px under 768px), 80px only on major Results/Methodology sections; mobile header: 8px vertical padding, 44px
  brand row, nav row with -8px block margins so links keep a 44px hit area and the header is 88px. Results run rows at 390 are stacked
  label:value lines (provider, then values in IBM Plex Mono 13px); charts have no scroll wrapper.
- Results chart footnotes (`p.footnote`, no `<figcaption>`) and "Not tested" sit in one `section#not-tested` > `details#notes` ("Notes").
- Lindsay's final copy-cuts.md is recorded by `pins.json` `copy_cuts_sha256` (not vendored: it quotes the retired Prices label);
  `content/copy.md` carries the strings. Methodology limits: the Firecrawl sentence is Lindsay's AC-10 ruling (it differs from copy-cuts item 9).
- Guards in `test_dist.Polish`: numbers on each page are a subset of `tests/numbers_baseline.json` (built from main 385a6e3, chart SVGs
  excluded), unranked Results rows equal to what the data pin produces, in main's order (`tests/results_rows_baseline.json`; at 303efdf4: run summary 3 rows (Exa, Tavily, Browserless) and the full Every row table 11 rows / 4 providers, Apify 2 rows), no raw hex in button rules (`--on-acc` token), neither excluded provider name (the AC-4 list; the test assembles its pattern so the repo itself stays clean) in any tracked file or `dist/` file, the Tavily claim once
  (in `#run`) and "No provider pays us" once (Disclosures), chart `<h3>` == every SVG root `aria-label`, no trailing period.
  `browser_check.check_layout`: header <=88px with 8px padding at 390, run-row values Plex Mono 13px <=2 lines, Methodology paragraphs >=480px (1440) / >=300px (390), hero CTA top <=420px (1440) / <=560px (390).
  Every visible `main p` except `.headline` is capped at 68ch of its own font (AC-20; also `test_prose_max_width_68ch`), and every rendered
  chart `<text>` is >=12px at 390 (font-size x screen CTM scale; 390 runs with overlay scrollbars as on phones).

PR proof map: `python3 tools/proof_map.py` prints the "Proof by AC" section with line numbers read from the test names.

## Signup (AWI-SIGNUP-FORM-001)
Store-first, same-origin signup. Copied and adapted from hazeydata/hazeydata.ai `functions/api/subscribe.js` and
`assets/signup/signup-config.js` at **d8ef4bbfa53dd819a5e5a11e1a8eba45707082a5** (HD-SIGNUP-001, PRs #30/#32); the endpoint is not shared (spec R1).
- `signup/config.js`: limits, statuses, visitor copy, `DOUBLE_OPT_IN` (true: every Beehiiv call sends `double_opt_override: "on"`, so the confirmation
  email and the "Check your inbox to confirm your subscription." copy follow one flag), `SEND_WELCOME_EMAIL=false` (R2: the welcome automation is
  switched on only by chief after Fred approves its copy), ASCII-only emails (OQ-5 default). `site.config.json` `signup` carries the same copy and
  double opt-in flag for the build; `tests/signup/config.test.mjs` fails on any drift.
- `signup/core.js`: `handleSubscribe` and `retryPending`. Order: POST only (else 405); `Origin` must equal the request's own origin (else 403, no CORS);
  `IP_SALT` required (else `error`); rate limit (5 per `ip_hash` per 10 min, 50 site-wide per minute; KV binding `SIGNUP_RL`, per-isolate memory without
  it; KV errors fail open); bot check (pluggable `BOT_CHECKS`, only `honeypot` = field `website`; R2: no Turnstile) with a fake success; email
  validation (trim, lowercase the domain; <=254 chars, one `@`, dotted domain) -> `invalid`; INSERT into D1 `SIGNUPS` (unique `email_norm, source`; a
  missing binding or failed write -> `error`, and Beehiiv is never called); then Beehiiv `POST /v2/publications/{BEEHIIV_PUB_ID}/subscriptions` (5 s timeout)
  with `utm_source=agentwebindex`, `custom_fields [{source: AWI}]`, `reactivate_existing:false`.
  2xx -> `sent` + sub id, status `pending_confirmation`. Timeout, network, 5xx, 429, other 4xx -> `failed`, status `queued`.
  No key, 401 or 403 -> `queued` row (CSV main path, AC 8a), status `queued`. A repeat writes nothing and calls nothing, and answers what a first
  signup in that row's state would get (if Beehiiv accepted the email but the D1 status update fails, the answer is a 500 `error`),
  so the response never reveals membership (`already_subscribed` is never sent). Logs hold fixed enums only.
- Statuses and copy: `pending_confirmation` "Check your inbox to confirm your subscription.", `queued` "Thanks, you're on the list. We'll send a confirmation
  email soon.", `invalid`, `rate_limited` "Too many tries, please wait a few minutes.", `error` (`subscribed` only if `DOUBLE_OPT_IN` is false).
  JSON when the request is JSON or `Accept: application/json` (`/signup.js`); otherwise a 303 to the static `/newsletter/thanks/<status>/` page
  (built by `build.py`, noindex, not in the sitemap), so the form works with JS off. (Spec data shape said `?s=<status>`; a per-status page needs no JS.)
- `functions/api/subscribe.js`: the Pages Function. `functions/api/signups/export.csv.js`: `GET` with header `X-Export-Token: <EXPORT_TOKEN>` -> CSV
  `email,source,created_at` of every row not `sent` and not deleted (`deleted_at` set) (formula-guarded); missing or wrong token -> 401. Exporting deletes nothing.
- `workers/signup-retry.js`: scheduled Worker (`*/15 * * * *`, config `workers/wrangler.signup-retry.toml`) running `retryPending`:
  `failed`/`pending` rows with attempts < 5, at most `RETRY_BATCH` (40) per run, oldest id first (Workers Free allows 50 external
  subrequests per invocation; the rest wait for the next run); `sent` rows are never touched (every UPDATE is guarded by `beehiiv_status != 'sent'`); no key -> skips Beehiiv;
  a 401/403 marks the row `queued` and stops the run. The same run then calls `purgeSent` (AC 18, R2): it deletes rows whose
  `beehiiv_status` is `sent` and whose `sent_at` is 30 days (`RETENTION_DAYS`) or more ago. `queued`, `pending` and `failed` rows are never deleted,
  however old; a second run deletes nothing more (idempotent). Purge runs even when retry is skipped for lack of a key.
- `migrations/0001_signups.sql`: D1 table `signups` (idempotent). `ip_hash` = SHA-256 of `IP_SALT` + IP; the raw IP is never stored.
- Bindings and secrets (names only; chief creates them at deploy): D1 `SIGNUPS`, optional KV `SIGNUP_RL`, secrets `BEEHIIV_API_KEY`, `BEEHIIV_PUB_ID`,
  `IP_SALT`, `EXPORT_TOKEN`. The Beehiiv `source` custom field (string) exists on the publication (created 2026-10-26), so the AWI tag is stored.
- Tests (in `run_tests.sh`): `node --test tests/signup/` (mocked D1/KV/fetch/clock; no network), `tests/signup/sql_check.py` (every statement against
  the migration in real SQLite), `tests/signup/secret_scan.sh`, `tests/signup/mutants.py` (defects injected into the save order and fallback logic must
  all be caught), plus `test_dist` (`test_signup_*`) and `browser_check.check_signup` (first screenful at 1280x800 and 390x844, label, "Subscribe",
  honeypot off-screen, contrast >= 4.5:1, keyboard order, aria-live error) and `browser_check.check_signup_goatcounter` (R3, AC 13: against
  `tests/signup/dev_server.mjs`, which serves `dist/` and the real handler on mocks, the form submits with JS on and off while gc.zgo.at is
  blocked, and with GoatCounter allowed (a stub `count.js` that beacons path, query, hash, referrer and title) no third-party request carries the email
  in its URL, Referer or body). AC 13 covers the form and `/api/subscribe` only; the site-wide GoatCounter script is left as it was.

## Deploy (Cloudflare Pages)
Build command `python3 build.py`, output directory `dist`, env `PYTHON_VERSION=3.12`.

Why `/api/subscribe` returns 405 today: the site is a Pages direct upload, and wrangler compiles Functions only from a `functions/` folder in the
directory it runs in. The deploy directory has none, so the upload is static-only and every POST gets 405 from the static asset server.

Deploy route (chief's deploy script, `refresh_dist`): after the tests pass and `dist/` is built, if `functions/` exists it runs
`wrangler pages functions build functions --outdir dist/_worker.js --output-routes-path dist/_routes.json --compatibility-date 2026-10-01`
and checks that `dist/_worker.js/index.js` exists and that `dist/_routes.json` includes exactly `/api/subscribe` and `/api/signups/export.csv`
(everything else stays static). The run fails if the Functions don't compile, and `--rollback` restores the previous `dist/` with its worker.
`wrangler pages deploy` uploads `_worker.js` as the advanced-mode worker and does not publish it as a static file.

Backend setup (names only; every step is gated on Fred's approval via chief, and none of it is done by this repo's code):
1. D1 database `awi-signups`; apply `migrations/0001_signups.sql` (`wrangler d1 migrations apply awi-signups --remote`).
2. Optional KV namespace `awi-signup-rl` (without it the rate limit falls back to per-isolate memory).
3. Pages project `agentwebindex`: copy `wrangler.pages.toml` as `wrangler.toml` into the deploy directory and replace the two
   `<PLACEHOLDER ...>` ids (D1 `SIGNUPS`, KV `SIGNUP_RL`). Secrets: `IP_SALT`, `EXPORT_TOKEN`, `BEEHIIV_PUB_ID`, `BEEHIIV_API_KEY`
   (`wrangler pages secret put NAME --project-name agentwebindex`).
4. Retry Worker `awi-signup-retry`: `workers/wrangler.signup-retry.toml` (cron `*/15 * * * *`, `workers_dev = false`, no route, D1 `SIGNUPS`);
   replace the placeholder id, set secrets `BEEHIIV_PUB_ID`, `BEEHIIV_API_KEY` (`wrangler secret put NAME -c wrangler.signup-retry.toml`), then
   `wrangler deploy -c wrangler.signup-retry.toml` from `workers/`.
5. Test plan: on a preview deploy first, then production, submit `hazeydata@mail.grokbot.com` (the agreed test address); expect
   `/newsletter/thanks/pending_confirmation/` (double opt-in), one D1 row with `beehiiv_status` `sent`, and a Beehiiv subscriber with
   `source` = `AWI`. A second submit of the same address gets the same answer and adds no row (AC 3).

`tests/signup/deploy_config.test.mjs` checks both config files: the env names the code reads equal the declared bindings plus the named secrets,
ids are placeholders, and neither file holds a secret value or publication id. Local `wrangler pages dev` (wrangler 4.86) supports compatibility
dates only up to 2026-05-03, so a local smoke run needs an earlier `--compatibility-date`; deployed Cloudflare uses 2026-10-01.

License: MIT (code); data under data/ is CC BY 4.0 (data/LICENSE).
