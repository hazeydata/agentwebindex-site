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

## Week 45 results (AWI-W45-PUBLISH-001, staged)
- `section#latest-week` on `/` sits right after the hero. It is built only from `content/w45-tables-regrade.json`. That file is a byte-identical copy of the `python -m awibench.tables runs OUT.json` regrade, rerun for AWI-TINYFISH-001 at agentwebindex `c4556c2` (agentwebindex#52, not merged yet). Compared with the AWI-W45-BASE-RUN-001 file (`7b40782`), the only additions are the 2 TinyFish rows and their freshness note (plus `generated_at`). `content/w45-results.json` records its sha256, the week, the run date (2026-11-02), the regrade commit and the run-log commit (`c4556c2`; it was `7651c2d`, the merge of agentwebindex#48). `pins.check()` fails the build if the regrade file's bytes differ from that sha256. Never hand-edit either file.
- Rows: every regrade row with `run_date` 2026-11-02, in regrade order. Today that is Firecrawl search on news_2026-45 and on search_evergreen, plus Bright Data scrape on scrape_urls. Manifest `extra_rows` (`{"tinyfish": "2026-11-03"}`) also adds TinyFish search on news_2026-45 and fetch on newsfetch_2026-45, which ran Nov 3 and show their own Run date; the heading and source dates still come from the 2026-11-02 rows. `extra_names` gives TinyFish its display name, because the vendored providers.json predates it. Right after the TinyFish fetch row comes a `tr.row-note` with the copy.md field `TinyFish fetch note` (AWI-TINYFISH-001; publish hold lifted per Fred, Nov 3 2026). Failed rows and failed counts are shown as they are. Apify has no week-45 row: it hit its cap and is out until Nov 16. Held providers never reach the regrade (tables.py drops them).
- Columns: Provider, Category, Set, Run date, Passed / checks (`passed.v of attempted.v`, linked to the run log at the manifest `run_logs_commit`, now `c4556c2`), Failed / checks, Pass rate (`fmt_pct`), Per 1,000 passed checks and List price per 1,000 calls (the regrade's own `display` strings), Skipped (terms) and Flags. There is no latency column, because AC19 keeps latency off Results. Each cell's `data-src` names the regrade fields it comes from.
- Copy comes from the `## Week 45 results` section of `content/copy.md` (Title, Ran, Not run, Prior run, Coverage, Apify, Comparison, Sample, Source, Failed, Skipped). It holds no results numbers; Sample and Source are templates (`{provider}`, `{n}`, `{total}`, `{date}`, `{sha}`) filled from data.
- Review edits (Lindsay voice, Ann dataviz): numeric columns (`render.W45_NUM`) are right-aligned with tabular-nums (`#w45-table .num`), and go back to left in the stacked mobile layout. Skipped (terms) shows `n/a` when the regrade has no skipped_tos (`render.w45_skipped`). The Comparison line gets a sample clause for each week-45 search_evergreen row on a reduced sample: n and total come from the row's `sample_note`, and n must equal `set_rows`. The trace re-derives the total from a full-set regrade row on the same `set_sha` (Firecrawl: 40 of 100). After the table, a source line names the manifest `run_logs_commit` (`7651c2d`, the merge of agentwebindex#48). tables.py at that commit reproduces the regrade exactly, apart from `generated_at`.
- Not-run lines: `content/w45-results.json` `live_not_held` lists live providers to account for (today `keenable`). Each one with no week-45 regrade row gets a "<Name>: not run this week" line. The page derives it from the regrade rows, and `trace_w45.py` recomputes it independently.
- Apify retest (`#apify-retest`, Oct 26 copy) opens with "Prior run: Oct 26, 2026" (the date comes from `render.RETEST`), and its copy says "on Oct 26 … that week's" rather than "this week", so it does not read as week-45 Apify data (`ApifyRetest.test_dated_as_prior_run`).
- Apify can appear in the week-45 section only in its own "did not run" copy line (`data-copy="apify"`). Any other mention of the name, in text, attributes or links, fails the build (`render.w45_apify_mentions`, called from `build.py`) and fails `trace_w45.py` independently. This holds even when a copy edit is re-pinned (Kitty t2 K04b; `W45Results.test_apify_only_in_its_did_not_run_line`, `test_build_fails_when_repinned_copy_claims_apify_ran`).
- On every built page (`dist/**/*.html`, including the newsletter thanks pages), "this week" may not appear outside `section#latest-week`, and "Apify" (case-insensitive, after entity, nbsp, soft-hyphen and zero-width normalisation) may appear only in an allowlisted container. Text, attributes, `<meta>` content, comments, `<noscript>` and scripts are all scanned. Each container must appear exactly once, sit where listed, and hold exactly its pinned number of mentions (Kitty t4). The build enforces this with `render.APIFY_ALLOW` and `apify_outside_allowlist`, and `trace_w45.py` checks it independently with its own HTMLParser and its own copy of the list:
  - `/`: `section#latest-week p.lcopy[data-copy="apify"]` (2: the attribute and "Apify did not run this week.")
  - `/`: `section#apify-retest` (9, the Oct 26 prior run)
  - `/`: `figure#chart-pass-rate` (8) and `figure#chart-cost` (4), the legacy charts from data pin 303efdf4
  - `/`: `details#notes` (1), `details#earlier-runs` (3), `details#every-row` (4)
  - `/methodology/`: `div#limits` (1)
  - `/prices/`: `div#price-rows div.price-row[data-provider="apify"]` (4)
- `live_not_held` is pinned to exactly `{"keenable": "Keenable"}` (the Keenable-only ruling). Both `pins.check` (the build fails) and `trace_w45.py` reject any other value (`W45Results.test_live_not_held_pinned_to_keenable_only`).
- Prior-run label: `#run` and `#details` (the older weekly tables from the `data` pin) open with "Prior run: <latest.json run_date>", currently "Prior run: Oct 23, 2026" (`W45Results.test_prior_run_label_on_old_tables`).
- `tools/trace_w45.py [dist/index.html] [--evidence tables-regrade.json] [--json OUT]` uses its own column map and its own formatters. It checks every cell against the regrade file, plus the row set, the run-log links and that Apify has no row. It also fails on any number in the section that is not in a traced cell, the copy or a column header. `run_tests.sh` runs it, and `tests.test_dist.W45Results` adds mutants (a changed number, a hidden fail, a dropped row, a wrong field, a stray number, a wrong log link, an Apify row) plus the build failing on an edited regrade file. `Polish.test_no_number_added_or_changed` skips this section, because the trace covers it.
- The weekly tables, charts and the `data` pin (303efdf4) are unchanged. `latest.json` is not re-vendored.

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
  excluded), unranked Results rows equal to what the data pin produces, in main's order (`tests/results_rows_baseline.json`; at 303efdf4: run summary 3 rows (Exa, Tavily, Browserless) and the full Every row table 11 rows / 4 providers, Apify 2 rows), no raw hex in button rules (`--on-acc` token), the held provider's name (AC-4; the test assembles its pattern so the repo itself stays clean) in no tracked file and no `dist/` file. AC-4 is lifted for Keenable only, by Lucille 2's Nov 2 2026 ruling: "AC-4 predates Fred's Oct 26 publish approval for Keenable." (`test_ac4_lifted_for_keenable_only`), the Tavily claim once
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
  `IP_SALT`, `EXPORT_TOKEN`. The Beehiiv `source` custom field (string) was created on the publication on 2026-10-26 (asserted by implement; not independently verified by Test), so the AWI tag should be stored.
- Tests (in `run_tests.sh`): `node --test tests/signup/` (mocked D1/KV/fetch/clock; no network), `tests/signup/sql_check.py` (every statement against
  the migration in real SQLite), `tests/signup/secret_scan.sh`, `tests/signup/mutants.py` (defects injected into the save order and fallback logic must
  all be caught), plus `test_dist` (`test_signup_*`) and `browser_check.check_signup` (first screenful at 1280x800 and 390x844, label, "Subscribe",
  honeypot off-screen, contrast >= 4.5:1, keyboard order, aria-live error) and `browser_check.check_signup_goatcounter` (R3, AC 13: against
  `tests/signup/dev_server.mjs`, which serves `dist/` and the real handler on mocks, the form submits with JS on and off while gc.zgo.at is
  blocked, and with GoatCounter allowed (a stub `count.js` that beacons path, query, hash, referrer and title) no third-party request carries the email
  in its URL, Referer or body). AC 13 covers the form and `/api/subscribe` only; the site-wide GoatCounter script is left as it was.

## Deploy (Cloudflare Pages)
Build command `python3 build.py`, output directory `dist`, env `PYTHON_VERSION=3.12`.

Deploy script: `scripts/deploy/refresh_dist.sh` (rev8; moved here from the box deploy dir per chief's ruling, Nov 2 2026). Chief runs it on the box after Fred approves.
Both roots come from the environment and are required: `AWI_DEPLOY_ROOT` (the dir that holds `wr/`, where `wrangler pages deploy dist` runs) and `AWI_TMP_ROOT` (sandboxes).
These are checked first, before `set -u`: if either is missing or empty the script exits 2 with `refresh_dist: STOP: set <VAR> ...`.
`refresh_dist.sh <site sha>` clones this repo at that sha, runs `build.py` and `run_tests.sh`, then, if `functions/` exists, runs
`wrangler pages functions build functions --outdir dist/_worker.js --output-routes-path dist/_routes.json --compatibility-date 2026-10-01`.
It checks that `dist/_worker.js/index.js` exists and that `dist/_routes.json` includes exactly `/api/subscribe` and `/api/signups/export.csv`
(everything else stays static), then swaps the new `dist/` in atomically. `--rollback` restores the newest valid backup of `dist/` and its BUILD_SHA; `--recover` only finishes or undoes an interrupted run.
Sandbox tests (no network, no account): `AWI_DEPLOY_ROOT=... AWI_TMP_ROOT=... scripts/deploy/test_refresh_dist_functions.sh <site worktree>`.
Pages runs `dist/_worker.js/` as the advanced-mode worker and does not publish it as static files (checked on production, Nov 2 2026).

Post-deploy smoke: `python3 scripts/deploy/smoke.py https://agentwebindex.com https://<deployment>.agentwebindex.pages.dev`.
Pages answers every unknown path with 200 plus index.html, so a bare 200 proves nothing. A check passes only on the right status, content type and body:
- `/` returns 200 HTML containing `AgentWebIndex`.
- `GET /api/subscribe` returns 405 and is not HTML.
- `GET /api/signups/export.csv` without a token returns 401 `Unauthorized` and is not HTML.
- `/_worker.js*` and `/_routes.json` must be the SPA fallback or 404. They fail on any JavaScript or JSON content type at any status (404 included), on `text/plain` with 200, and on any body that contains worker code.
Unit tests, both run by `run_tests.sh`: `tests/test_deploy_smoke.py` (smoke rules, including the SPA-fallback false positive and JS/JSON at any status) and `tests/test_refresh_dist_guards.py` (refresh_dist.sh exits non-zero with its guard message when `AWI_DEPLOY_ROOT` or `AWI_TMP_ROOT` is unset or empty).

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
