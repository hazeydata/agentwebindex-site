# AWI-PAGE-POLISH-001 — copy cuts for agentwebindex.com

Source: live pages fetched with curl, Oct 25, 2026, 1:12 AM EDT (before/ held only screenshots). Page URLs checked against the site nav (Results, Prices, Methodology, Data) and footer (Disclosures, Newsletter, Sponsors, Tell us). Brief: layout-brief.md. Each BEFORE is quoted verbatim; character counts are for the text as shown.

## Newsletter button text (all pages)

Newsletter signup button on every page: "Get the results by email". Box lead-ins are listed per page below. This is the final button text for the brief's CTA rule, replacing the assignee name the brief put where the label goes.

## Results (/) — https://agentwebindex.com/

1. BEFORE (238 chars): We send the same frozen questions and URLs to each search, scrape and browser API, then publish how often each passed our check, and what that cost. Every result traces to our run logs; prices come from providers' published pricing pages.
   AFTER (168 chars): Same frozen questions and URLs for every search, scrape and browser API. We publish each pass rate and its cost, traced to our run logs and providers' published prices.
   Note: Hero para under the lede; brief also suggests demoting it to 17px body.

2. BEFORE (107 chars): Search, 100 evergreen questions. Tavily passed our check on 69 of 100 (69%). Exa passed on 40 of 100 (40%).
   AFTER (32 chars): Search, 100 evergreen questions.
   Note: Run-table bullet 1 of 3. Pass-rate claim cut as a repeat; kept once at the hero findings line (item 8). The "69 of 100" and "40 of 100" counts also stay in the run table's data labels.

3. BEFORE (195 chars): Cost per 1,000 passed checks, at entry-tier list price. Tavily $11.59. Exa $17.50. Exa's list price is lower ($7.00 vs $8.00 per 1,000 calls), but it passed fewer checks, so each pass costs more.
   AFTER (171 chars): Cost per 1,000 passed checks, entry-tier list price: Tavily $11.59, Exa $17.50. Exa lists lower ($7.00 vs $8.00 per 1,000 calls) but passed fewer, so each pass costs more.
   Note: Run-table bullet 2 of 3.

4. BEFORE (146 chars): Scrape, Browserless. 150 URLs; 30 skipped by design under Browserless's terms; 79 of 120 tested passed (66%), at $1.90 per 1,000 successful calls.
   AFTER (133 chars): Scrape, Browserless: 79 of 120 tested passed (66%), $1.90 per 1,000 successful calls. 150 URLs; 30 skipped by design under its terms.
   Note: Run-table bullet 3 of 3. Skip caveat kept.

5. BEFORE (183 chars): Pass rate on our test set, Oct 23, 2026 run. Search: Tavily 69%, Exa 40% (n=100). Scrape: Browserless 66% (79 of 120 tested; 150 URLs, 30 skipped by design under Browserless's terms).
   AFTER (65 chars): Pass rate on our test set, Oct 23, 2026 run. Values in the chart.
   Note: Pass-rate chart caption. Pass-rate claim cut as a repeat; kept once at the hero findings line (item 8). The chart's h3 title (item 9) and its data labels keep their numbers. "n=100" is kept in item 2 ("100 evergreen questions"), and "79 of 120", "150 URLs" and "30 skipped" are kept in item 4.

6. BEFORE (84 chars): What 1,000 passed checks cost at entry-tier list price. Free credits don't lower it.
   AFTER (79 chars): Cost of 1,000 passed checks at entry-tier list price. Free credits don't count.
   Note: Cost chart footnote. Already short; light trim only.

7. BEFORE (226 chars): Brave's terms forbid benchmarking, so we don't test it. Bright Data's collector is ready but hasn't run. Firecrawl had no key for this run. Apify sat out the Oct 23 run to save its free monthly credit for the weekly news runs.
   AFTER (180 chars): Brave's terms forbid benchmarking. Bright Data's collector hasn't run yet. Firecrawl had no key this run. Apify skipped Oct 23 to save its free monthly credit for weekly news runs.
   Note: "Not tested" section. All four reasons kept.

8. BEFORE (100 chars): Tavily passed 69% of our 100 evergreen checks, Exa 40%; Browserless passed 66% of 120 scrape checks.
   AFTER (100 chars): Tavily passed 69% of our 100 evergreen checks, Exa 40%; Browserless passed 66% of 120 scrape checks.
   Note: Hero findings line, under "Results, Oct 23, 2026 run". This is the one kept instance of the pass-rate claim, unchanged.

9. BEFORE (99 chars): Tavily passed 69% of our 100 evergreen checks, Exa 40%; Browserless passed 66% of 120 scrape checks
   AFTER (99 chars): Tavily passed 69% of our 100 evergreen checks, Exa 40%; Browserless passed 66% of 120 scrape checks
   Note: Pass-rate chart h3 title. It's a chart title, so it keeps its numbers under the "Ruling: chart titles" section below (the h3 stays and the SVG title text is dropped). Items 2 and 5 are the repeats that were cut.

CTA labels:
- Above-fold box (in the hero, right after the first lede): lead-in "New runs, logs and prices, straight to your inbox." Button: "Get the results by email"
- End box (Newsletter section): lead-in "One email when a new run lands." Button: "Get the results by email"

## Prices — https://agentwebindex.com/prices/

1. BEFORE (179 chars): Also priced, no published results yet: Brave Search API, Linkup, Parallel, Serper, Firecrawl, Jina Reader, Bright Data Web Unlocker, Hyperbrowser, ScrapingBee, Browserbase, Steel.
   AFTER (164 chars): Priced, not yet tested: Brave Search API, Linkup, Parallel, Serper, Firecrawl, Jina Reader, Bright Data Web Unlocker, Hyperbrowser, ScrapingBee, Browserbase, Steel.
   Note: All 11 provider names kept; only the lead-in is cut. A list this long can't shrink 40% without dropping names.

CTA labels:
- Above-fold box (after the lede): lead-in "Want the next run?" Button: "Get the results by email"
- End box (after the table): lead-in "New prices and new runs, by email." Button: "Get the results by email"

## Methodology — https://agentwebindex.com/methodology/

1. BEFORE (193 chars): Same frozen sets for every provider. A pass means the result passed our check. Every result traces to our run logs; prices come from providers' published pricing pages. Limits are listed below.
   AFTER (159 chars): Same frozen sets for every provider. A pass means the result passed our check. Results trace to our run logs; prices to providers' pricing pages. Limits below.
   Note: Lede.

2. BEFORE (503 chars): How we test. Each provider gets the same frozen set. Evergreen search (100 questions) passes on one check per question: the exact expected URL in the top 10 (42 questions), the expected domain in the top 5 (15), or the expected text in a top-5 title or snippet (43). News search passes on the expected URL in the top 10, or a same-outlet article in the top 5, published within 72 h. Scrape passes when the expected content marker is found, the text meets a minimum length, and there's no challenge page.
   AFTER (366 chars): How we test. Same frozen set for each provider. Evergreen search (100 questions), one check each: exact URL in the top 10 (42), domain in the top 5 (15), or text in a top-5 title or snippet (43). News search: expected URL in the top 10, or a same-outlet article in the top 5 published within 72 h. Scrape: content marker found, minimum length met, no challenge page.
   Note: Every count and threshold kept. Good <details> candidate per the brief.

3. BEFORE (131 chars): What a check is. For search: the exact URL, the right domain, or the right text. For scrape: content, length and no challenge page.
   AFTER (107 chars): What a check is. Search: exact URL, right domain or right text. Scrape: content, length, no challenge page.

4. BEFORE (150 chars): Pass rate on our test set is passed divided by attempted. Attempted leaves out calls skipped under a provider's terms and HTTP 429 rate-limited calls.
   AFTER (138 chars): Pass rate on our test set = passed ÷ attempted. Attempted excludes calls skipped under a provider's terms and HTTP 429 rate-limited calls.
   Note: Both exclusions kept.

5. BEFORE (200 chars): Scrape set. 150 URLs; 30 skipped by design under Browserless's terms; 79 of 120 tested passed. The 30 are the anti-bot URLs, which Browserless's terms forbid, so this score never faced anti-bot pages.
   AFTER (156 chars): Scrape set. 150 URLs; 79 of 120 tested passed. The 30 skipped are anti-bot URLs, which Browserless's terms forbid, so this score never faced anti-bot pages.
   Note: Caveat kept: the score never faced anti-bot pages. "by design" folded into the second sentence.

6. BEFORE (115 chars): Grading. Search is re-graded with grader canon-2026-10-20. Scrape and browser are scored straight from the run log.
   AFTER (108 chars): Grading. Search re-graded with grader canon-2026-10-20. Scrape and browser scored straight from the run log.

7. BEFORE (173 chars): Cost. Entry-tier list price read from each provider's pricing page, with the date we last checked it: list price times calls, divided by passes. Free credits never lower it.
   AFTER (148 chars): Cost. Entry-tier list price from each provider's pricing page, dated when we last checked: list price × calls ÷ passes. Free credits never lower it.

8. BEFORE (125 chars): Latency (p50), Oct 23, 2026 run. Exa search 1,262 ms. Tavily search 1,632 ms. Browserless scrape 1,618 ms. Yours will differ.
   AFTER (125 chars): Latency (p50), Oct 23, 2026 run: Exa search 1,262 ms, Tavily search 1,632 ms, Browserless scrape 1,618 ms. Yours will differ.
   Note: Figures-only line, so formatting tidy only; the "Yours will differ" caveat stays.

9. BEFORE (331 chars): Four providers have rows in these results (Exa, Tavily, Browserless, Apify). Firecrawl ran on Oct 15, 2026, but its row isn't shown: rate limits hit 6 of its 16 calls, over our 20% cutoff. Of the other ten, eight aren't on our month-one free-tier list, Brave's terms forbid benchmarking, and Bright Data's collector hasn't run yet.
   AFTER (303 chars): Four providers have rows: Exa, Tavily, Browserless, Apify. Firecrawl ran Oct 15, 2026, but rate limits hit 6 of its 16 calls, over our 20% cutoff, so its row is hidden. Of the other ten: eight aren't on our month-one free-tier list, Brave's terms forbid benchmarking, Bright Data's collector hasn't run.
   Note: "Four", "ten" and "eight" are words on the live page and stay as words. All exclusion reasons kept.

10. BEFORE (141 chars): Every result traces to our run logs; prices come from providers' published pricing pages. If one is wrong, it's on us, and we'll say so here.
   AFTER (130 chars): Results trace to our run logs; prices to providers' published pricing pages. If one is wrong, that's on us, and we'll say so here.
   Note: Closing para. Repeats the lede; could go, but it carries the corrections promise, so it's kept short.

CTA labels:
- Above-fold box (after the lede, before the TOC): lead-in "Method changes go out by email first." Button: "Get the results by email"
- End box: lead-in "Want the next run's logs?" Button: "Get the results by email"

## Data — https://agentwebindex.com/data/

No items: no flagged or over-150-char paragraphs on this page.

CTA labels:
- Primary button (hero, after the lede): "Download latest.json". Secondary text link beside it: "or latest.csv"
- End box: lead-in "Hear when a new file drops." Button: "Get the results by email"
- Note: no body paragraph here is over about 150 chars, and the 122-char lede is marked fine in the brief. No text cuts.

## Disclosures — https://agentwebindex.com/disclosures/

1. BEFORE (180 chars): We test on our own accounts. Every published result ran within the provider's public free plan. Costs are shown at list price; free credits never lower a cost. No provider pays us.
   AFTER (104 chars): We test on our own accounts, within each provider's public free plan. Costs use list price, not credits.
   Note: Under "Who pays for testing". "No provider pays us" cut as a repeat; kept once in the main disclosures paragraph (item 2). The free-credits rule is condensed, not dropped, and is also stated in full under "Free credits received".

2. BEFORE (129 chars): Short version: nobody. No provider pays us, and there are no sponsors yet. AgentWebIndex is made by Fred and his team of AI bots.
   AFTER (129 chars): Short version: nobody. No provider pays us, and there are no sponsors yet. AgentWebIndex is made by Fred and his team of AI bots.
   Note: Main disclosures paragraph (hero lede), unchanged. This is the one kept instance. The page's meta description and og:description copy this lede; those are page metadata, so they're left alone. The Sponsors page also says "no provider pays us"; that page is left alone.

3. BEFORE (30 chars): None yet. No provider pays us.
   AFTER (9 chars): None yet.
   Note: Under "Current and past sponsors". "No provider pays us" cut as a repeat; kept once in the main disclosures paragraph (item 2).

CTA labels:
- Hero inline secondary links: "Open an issue" · "Email fred@hazeydata.ai"
- End box: lead-in "New runs and any corrections, by email." Button: "Get the results by email"
- Note: no newsletter box above the fold on this page; the brief allows end-only here.

## Newsletter — https://agentwebindex.com/newsletter/

No items: no flagged or over-150-char paragraphs on this page.

CTA labels:
- Single box (wraps the existing signup; no repeat): lead-in "New runs, logs and prices. One email per run." Button: "Get the results by email"
- Page line above the box: "Get updates. Sign up below." (unchanged)
- Note: no body paragraph over about 150 chars.

## Sponsors — https://agentwebindex.com/sponsors/

No items: no flagged or over-150-char paragraphs on this page.

CTA labels:
- Above-fold box (after the first para, which keeps the line that it's made by Fred and his team of AI bots): lead-in "Want a labelled sponsor slot? Let's talk." Button: "Email Fred" (mailto:fred@hazeydata.ai)
- End box: lead-in "Not sponsoring? Get the results instead." Button: "Get the results by email"
- Note: no body paragraph over about 150 chars, so no text cuts.

## Tell us — https://agentwebindex.com/tell-us/

1. BEFORE (144 chars): Tell us. Spot a wrong number, a missing provider, or a test that's unfair? Open an issue and we'll fix it in public. Or email fred@hazeydata.ai.
   AFTER (128 chars): Spot a wrong number, a missing provider or an unfair test? Open an issue and we'll fix it in public, or email fred@hazeydata.ai.
   Note: Leading "Tell us." dropped because it repeats the h1. The live page renders the address through Cloudflare email protection; it decodes to fred@hazeydata.ai.

CTA labels:
- Primary button: "Open an issue"
- Secondary button: "Email Fred" (mailto:fred@hazeydata.ai)
- End box: lead-in "Like the fixes? Get the next run." Button: "Get the results by email"
- Note: the intro line "AgentWebIndex is built by Fred and his team of AI bots at HazeyData…" stays as is.

## Ruling: chart titles (Lindsay, Oct 25, 2026)
Each title shows up in both the h3 and the SVG. Keep the h3 and drop the title text from the SVG, at every size including 390. The h3 is real text: it scales, wraps, gets read by screen readers and can be linked to, and at 390 it saves vertical space inside the chart. The h3 wording stays exactly as written now, numbers included. Each SVG keeps its role="img" plus an aria-label or alt line with the same wording as the h3. Axis labels and data labels stay in the SVG.
Punctuation: chart h3 titles and aria-labels have no trailing period. Drop the period from the pass-rate line in screens/index.html so it matches.
Newsletter page line stays "Get updates. Sign up below." The earlier "in your inbox" wording was disputed by fact as unverified.

## Hero card lead-ins (added Oct 25, 1:35 AM)
- Data hero card, above "Download latest.json": "The raw results behind these pages. Grab them and check our work."
- Disclosures hero card, above "Open an issue" / "Email fred@hazeydata.ai": "Spot something off? Tell us."
- Prices newsletter label: "Get the results by email", the same as on every other page. "Get price updates by email" is retired: one newsletter, one label, and we haven't confirmed it sends price updates.
