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
(a PR head) is fetched by sha. Current pin: data `8ab7ccc` (agentwebindex#25, Tavily re-verified 2026-10-24).
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
  per chart at 390/720/1440 in both colour schemes, hidden variants display:none, role=img + alt-text name, served chart SVG bytes vs pinned sha256, C2 stacked under C1; chart `<text>` computed font-family Inter via document.fonts and rendered with Inter only (CDP CSS.getPlatformFontsForNode); id rename leaves every element's text and box unchanged vs the original file markup; no sideways scroll, body >=16px and
  tap targets >=44px at 390px; screenshots go to a temp /tmp/awi-shots.* dir that is deleted on exit unless AWI_KEEP_SHOTS=1, which keeps it and prints the path; prints SKIP without Chrome).
- `tests/test_ship.py`: SHIP gates, run separately, all must pass: `test_no_placeholders` (no `[[LINDSAY-PLACEHOLDER]]` in dist), Tavily price equals
  pricing.yaml, `test_tavily_date_is_phase0` (R3: rendered Tavily date == 2026-10-24) and `test_data_pin_moved` (R4/R8: pin is not 6b8bd87, no Tavily input before `phase0_date`).
- `tests/agent_surface_baseline.json`: hashes of the agent surfaces main's code (60a8f4b) builds from the pinned data (regenerated at 8ab7ccc by building
  main's code on the new data). Against the 6b8bd87 baseline the only change is `data/benchmarks/latest.json` (three Tavily `cost_units_note` check dates,
  2026-10-19 to 2026-10-24); the site's `llms.txt` differs from main's only by the added `/tell-us/` entry.

Fonts: all self-hosted as woff2 under `/assets/fonts/` (`src/fonts/`), licensed SIL OFL 1.1, one notice per family: `src/fonts/OFL-Inter.txt`, `OFL-SpaceGrotesk.txt`, `OFL-IBMPlexMono.txt` (copyright lines taken from each font's name table). IBM Plex Mono 400/500/600 are the upstream Latin files.
Inter 400/600/700 and Space Grotesk 600 (`inter-{400,600,700}-latin.woff2`, `space-grotesk-600-latin.woff2`, 17.3, 17.9, 17.9 and 10.9 KB) were subset from the TrueType fonts
of the 2c28c0a charts with fontTools, Latin range. Those TrueType files are not in the repo or in `dist/`. Weights kept are the ones the CSS uses (Inter 700 is the default `<b>` weight).
Charts (R9 supersedes the R8 font bullet; AC14): `dist/assets/charts` holds exactly the 8 pinned SVGs, byte-identical, and the same markup is inlined on `/`; fonts are not byte-checked. A test fails if any font file in the repo
(`git ls-files`) or in `dist/` is over 100 KB (102,400 bytes) or is a TrueType/OpenType file.
Newsletter: beehiiv embed when `site.config.json` -> `beehiiv_embed_url` is set, otherwise a disabled "Coming soon" form.

PR proof map: `python3 tools/proof_map.py` prints the "Proof by AC" section with line numbers read from the test names.

## Deploy (Cloudflare Pages)
Build command `python3 build.py`, output directory `dist`, env `PYTHON_VERSION=3.12`. Not deployed yet.

License: MIT (code); data under data/ is CC BY 4.0 (data/LICENSE).
