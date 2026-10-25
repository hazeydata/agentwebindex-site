# AWI-PAGE-REDO-001 copy (DRAFT, not for publishing)

Data: hazeydata/agentwebindex @ 6b8bd87d778b3fe0fe049f9274796ab498928cc5 (data/benchmarks/latest.json, generated 2026-10-23T17:33:47+00:00, which is 1:33 PM EDT Oct 23; data/prices; bench/runs/2026-10-23, merge #23). Site read: hazeydata/agentwebindex-site @ 60a8f4bcfd8206389968e9e584ad7713c8d740c2. llms.txt and JSON untouched.
Every number below is PENDING FACT CHECK by Lucille. Display rule (owner ruling): whole percents (half up), money to $0.01, under $0.01 at 2 significant figures. Stored values are in the chart briefs' source fields.

## Page title and nav
**Title:** Results
**Nav:** Results · Prices · Methodology · Data

## Home: hero
**Headline:** Which web API gets your agent the right result? We test it and show the logs.

**Lede:** Same frozen questions and URLs for every search, scrape and browser API. We publish each pass rate and its cost, traced to our run logs and providers' published prices.

Built by Fred and his team of AI bots.

## Home: findings
Our first $0 free-tier run, on Oct 23, 2026, used frozen test sets.

Tavily passed 69% of our 100 evergreen checks, Exa 40%; Browserless passed 66% of 120 scrape checks.

- **Search, 100 evergreen questions.**
- **Cost per 1,000 passed checks, entry-tier list price:** Tavily $11.59, Exa $17.50. Exa lists lower ($7.00 vs $8.00 per 1,000 calls) but passed fewer, so each pass costs more.
- **Scrape, Browserless:** 79 of 120 tested passed (66%), $1.90 per 1,000 successful calls. 150 URLs; 30 skipped by design under its terms.

One run. Early signal, not a verdict. Older, smaller runs are in Earlier runs below.

## Home: section intros
### Pass rate
How often each API passed our check, on our test set. One dot per API, with the n beside it.

### Cost per passed check
List price divided by passes. A cheap call that misses isn't cheap.

### Not tested
Brave's terms forbid benchmarking. Bright Data's collector hasn't run yet. Firecrawl had no key this run. Apify skipped Oct 23 to save its free monthly credit for weekly news runs.

## Earlier runs (collapsed by default)
**Summary line:** Earlier runs: short news weeks, below or near our minimum. Tap to open.

Weekly news sets, before the frozen sets, plus Apify and Browserless browser runs. Small n, so treat them as early.

**Week 2026-42 (16 questions, below minimum)**
- Exa search, run Oct 15, 2026, n=16: 94% pass rate on our test set, $7.47 per 1,000 successful calls.
- Tavily search, run Oct 15, 2026, n=16: 75%, $10.67.
- Apify search, run Oct 19, 2026, n=16: 13% (12 of 14 misses timed out), cost n/a (paid-tier price not captured).
- Browserless browser, run Oct 19, 2026, n=16: 69%, $1.82.

**Week 2026-43 (40 questions, short week)**
- Exa search, run Oct 20, 2026, n=40: 93%, $7.57.
- Tavily search, run Oct 20, 2026, n=40: 73%, $11.03.
- Apify search, run Oct 20, 2026, n=40: 48%, cost n/a (paid-tier price not captured).
- Browserless browser, run Oct 20, 2026, n=40: 93%, $1.35.

## Chart briefs
### Chart 1: Pass rate on our test set
- **Title:** Tavily passed 69% of our 100 evergreen checks, Exa 40%; Browserless passed 66% of 120 scrape checks
- **Shows:** success_rate per provider for the 2026-10-23 run, one panel for search (search_evergreen) and one for scrape (scrape_urls). Dots, labelled "passed/attempted" and whole percent.
- **Data:** data/benchmarks/latest.json, tables.search[] and tables.scrape[] where run_date = 2026-10-23; fields provider, set, success_rate.v, passed.v, attempted.v, flags.
- **File:** assets/charts/awi-pass-rate-{350,720}-{light,dark}.svg
- **Caption:** Pass rate on our test set, Oct 23, 2026 run. Values in the chart.
- **Alt text:** Dot chart with 95% intervals, pass rate on our test set, Oct 23, 2026 run. Search, 100 evergreen questions: Tavily 69% (69/100), Exa 40% (40/100). Scrape, 120 of 150 URLs tested, 30 skipped under Browserless's terms: Browserless 66% (79 of 120).

### Chart 2: Cost per 1,000 passed checks
- **Title:** Exa lists cheaper than Tavily ($7.00 vs $8.00 per 1,000 calls) but costs more per 1,000 passed checks ($17.50 vs $11.59)
- **Subtitle opens with:** Cost per 1,000 passed checks, at entry-tier list price
- **Shows:** entry_tier_cost_per_successful_1k per provider, same run, with list price per 1,000 calls as an open dot.
- **Data:** data/benchmarks/latest.json, same rows; fields entry_tier_cost_per_successful_1k.v and .display, entry_tier_cost_per_1k.v and .display, tier, lower_bound. Price sources in data/prices/{exa,tavily,browserless}.json.
- **File:** assets/charts/awi-cost-per-success-{350,720}-{light,dark}.svg
- **Caption:** Cost of 1,000 passed checks at entry-tier list price. Free credits don't count.
- **Alt text:** Dot chart. Cost per 1,000 passed checks at entry-tier list price: Exa $17.50, Tavily $11.59, Browserless (scrape) $1.90. Open dots show list price per 1,000 calls: Exa $7.00, Tavily $8.00, Browserless $1.25.

### Chart 3 (optional, skipped by dataviz): Prices
- **Title:** Entry-tier list price per 1,000 calls
- **Shows:** entry-tier list price per 1,000 calls for each tested provider, with a dot on each date a vendor's pricing page changed.
- **Data:** data/benchmarks/latest.json rows (provider, entry_tier_cost_per_1k.v, .display, tier); data/prices/{provider}.json (name, url, fetched_at, diff.changed); data/prices/history/{provider}.jsonl (fetched_at, status, text_sha256, prices_found) for change dates.
- **File:** assets/charts/awi-prices-{350,720}-{light,dark}.svg
- **Caption:** Entry-tier list price per 1,000 calls, read from each vendor's own page and dated. Dots mark page changes.
- **Alt text:** Dot chart of list price per 1,000 calls: Exa $7.00, Tavily $8.00, Browserless $1.25, with dots marking dates their pricing pages changed.

## Methodology and limits
**How we test.** Same frozen set for each provider. Evergreen search (100 questions), one check each: exact URL in the top 10 (42), domain in the top 5 (15), or text in a top-5 title or snippet (43). News search: expected URL in the top 10, or a same-outlet article in the top 5 published within 72 h. Scrape: content marker found, minimum length met, no challenge page.

**What a check is.** Search: exact URL, right domain or right text. Scrape: content, length, no challenge page.

**Pass rate on our test set** = passed ÷ attempted. Attempted excludes calls skipped under a provider's terms and HTTP 429 rate-limited calls.

**Scrape set.** 150 URLs; 79 of 120 tested passed. The 30 skipped are anti-bot URLs, which Browserless's terms forbid, so this score never faced anti-bot pages.

**Grading.** Search re-graded with grader canon-2026-10-20. Scrape and browser scored straight from the run log.

**Cost.** Entry-tier list price from each provider's pricing page, dated when we last checked: list price × calls ÷ passes. Free credits never lower it.

**Freshness:** not measured yet (one probe, 16 queries); coming once re-probes run.

**Latency (p50), Oct 23, 2026 run:** Exa search 1,262 ms, Tavily search 1,632 ms, Browserless scrape 1,618 ms. Yours will differ.

**Limits, plainly.**
- One run, Oct 23, 2026. The plan is three runs a week, averaged. We're not there yet.
- Four providers have rows: Exa, Tavily, Browserless, Apify. Firecrawl wasn't run this time (no API key), so it has no row. Of the other ten: eight aren't on our month-one free-tier list, Brave's terms forbid benchmarking, Bright Data's collector hasn't run.
- A pass means the result passed our check. It says nothing about the quality of the rest of the results.

Results trace to our run logs; prices to providers' published pricing pages. If one is wrong, that's on us, and we'll say so here.

## About and tell us
AgentWebIndex is built by Fred and his team of AI bots at HazeyData. No paid placement: sponsors appear only in labelled slots.

Spot a wrong number, a missing provider or an unfair test? [Open an issue](https://github.com/hazeydata/agentwebindex-site/issues) and we'll fix it in public, or email fred@hazeydata.ai.

## Data page
The latest benchmark table is free to download today as CSV and JSON, under CC BY 4.0. Credit "AgentWebIndex" with a link.

## Footer
AgentWebIndex. Logged runs, cited prices. Built by Fred and his team of AI bots. Data CC BY 4.0. [Issues](https://github.com/hazeydata/agentwebindex-site/issues) · fred@hazeydata.ai

## Layout slot: newsletter one-liner (NEWS-SLOT, 90 chars max)
Get updates. Sign up below.

## Layout slot: prices lede (160 chars max)
List prices are read from each provider's pricing page, with the date we last checked shown. Free credits never lower a cost.

## Prices page: also priced
Priced, not yet tested: Brave Search API, Linkup, Parallel, Serper, Firecrawl, Jina Reader, Bright Data Web Unlocker, Hyperbrowser, ScrapingBee, Browserbase, Steel.

## Layout slot: methodology lede (optional, 200 chars max)
Same frozen sets for every provider. A pass means the result passed our check. Results trace to our run logs; prices to providers' pricing pages. Limits below.

## CTA boxes (AWI-PAGE-POLISH-001, Lindsay copy-cuts.md)
**Button:** Get the results by email
**Results top:** New runs, logs and prices, straight to your inbox.
**Results end:** One email when a new run lands.
**Prices top:** Want the next run?
**Prices end:** New prices and new runs, by email.
**Methodology top:** Method changes go out by email first.
**Methodology end:** Want the next run's logs?
**Data top:** The raw results behind these pages. Grab them and check our work.
**Data end:** Hear when a new file drops.
**Disclosures top:** Spot something off? Tell us.
**Disclosures end:** New runs and any corrections, by email.
**Newsletter box:** New runs, logs and prices. One email per run.
**Sponsors top:** Want a labelled sponsor slot? Let's talk.
**Sponsors end:** Not sponsoring? Get the results instead.
**Tell us end:** Like the fixes? Get the next run.

## Disclosures page (fact-cleared, Lucille 6ae70a3)
**Kicker:** Who pays us, if anyone
**Title:** Disclosures

**Intro:** Short version: nobody. No provider pays us, and there are no sponsors yet. AgentWebIndex is made by Fred and his team of AI bots.

**DISC-SPON (Current and past sponsors):** None yet.

**DISC-AFF (Affiliate relationships):** None.

**DISC-CRED (Free credits received):** Costs use list prices. Free credits never lower a cost, so a provider's free tier can't make it look cheaper here.

**Who pays for testing:** We test on our own accounts, within each provider's public free plan. Costs use list price, not credits.

**DISC-CORR (Corrections changelog):** No corrections yet. If we get one wrong, we'll fix it and log it here.

Questions? [Open an issue](https://github.com/hazeydata/agentwebindex-site/issues) or email fred@hazeydata.ai.

## Sponsors page (fact-cleared, Lucille 6ae70a3)
**Kicker:** No sponsors yet
**Title:** Sponsors

**SPON-WHO:** There are no sponsors yet, and no provider pays us. AgentWebIndex is made by Fred and his team of AI bots.

**SPON-SLOT:** Costs here use list prices. Free credits never lower a cost.

**SPON-PRICE:** Questions? [Open an issue](https://github.com/hazeydata/agentwebindex-site/issues) or email fred@hazeydata.ai.

## Notes: layout review (screens/index.html and layout-spec.md @ 0dbe561)
- Row sub-label, Exa: "search · 100 evergreen questions" OK.
- Row sub-label, Tavily: "search · 100 evergreen questions" OK.
- Row sub-label, Browserless: "scrape · 120 of 150 URLs tested (30 skipped under its terms)" replace with "scrape · 150 URLs; 30 skipped by design under its terms" (55 chars). Matches the copy's scrape wording; the row already says 79 of 120 passed.
- Footer line: "Logged runs, cited prices. Data CC BY 4.0. No paid placement." OK. Every part is already in copy.md (footer and About). The first footer line "built by Fred and his team of AI bots" and "AgentWebIndex by HazeyData · fred@hazeydata.ai" are also OK.
- Also stale in the mock (built from copy 926b88c), outside this review's scope: hero/lede still say "right page"; row cost labels say "per 1,000 right answers" (copy: "per 1,000 passed checks"; Browserless row says "successful calls", make all three "passed checks"); "Cost per right answer" and the "returned the page we expected ... One bar per API" intros; Apify "cost n/a" lacks "(paid-tier price not captured)"; Not-tested and footer links are fine. Current wording is in this file above.

## Open questions
- Fact-fix pass applied (Lucille's file at b4a6e4b); re-check of the new methodology wording pending.
- Latency "from one machine" claim removed as unverified.
- Rounding confirmed: half up, whole ms for latency.
