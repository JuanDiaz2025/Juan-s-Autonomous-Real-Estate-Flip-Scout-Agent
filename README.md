# Juan's Autonomous Real Estate Flip Scout Agent

Scans Redfin for single-family fixer-uppers in Juan's target Bay Area zips,
estimates ARV/rehab/profit for each from real sold comps, scores them against
Twin Home Buyer's flip-analyst methodology (see below), and outputs a ranked
list of flip candidates.

## Usage

```
pip install -r flip_scout/requirements.txt
python flip_scout/flip_scout_redfin.py
```

Prints a ranked report to the console and writes `flip_report_YYYYMMDD.txt`.
Every run first pulls each target zip's last 6 months of sold homes to build
that zip's ARV basis, then searches active listings - so it makes ~2x the
number of zips in requests before it even starts shortlisting.

## What changed from the original draft

The original script targeted a `window.initialState` JSON blob and
`HomeCard-*` CSS classes that Redfin has since replaced with `bp-Homecard__*`
markup. `flip_scout_redfin.py` now:

- Scrapes the current card markup for address/price/beds/baths/sqft/URL
- Filters out condo/TIC units and multi-address (duplex-style) listings that
  slip through Redfin's "house" filter - checking both the displayed address
  text and the URL slug, since Redfin sometimes shows only one street number
  on the card for a listing whose URL still carries the full range
  (e.g. displays "451 8th Ave" for a listing at `451-453-8th-Ave-...`)
- Enriches shortlisted candidates with each listing's detail page
  (description, lot size, year built) to drive the reno-cost and scoring
  heuristics
- Corrects the ZIP code from the listing's own address rather than the
  searched ZIP, since Redfin's zip search returns some neighboring-zip results
- Shortlists candidates for detail-page enrichment **per zip**, not
  globally - an earlier version ranked all 17 zips in one pool, which let
  San Francisco (assigned a higher assumed ARV at the time) crowd out every
  other city before it was ever analyzed
- Builds ARV from **real sold comps**, not a guess (see below)
- Excludes listings whose own description says the home is already renovated
  or move-in ready (`ALREADY_RENOVATED_FLAGS`) - a big spread on an
  already-updated house just means it's underpriced vs. comps (a wholesale
  play), not a flip opportunity, since there's no renovation left to add
  value through. Only unambiguous phrasing counts ("fully renovated",
  "remodeled kitchen", "recently remodeled") - a bare "refreshed" is
  deliberately NOT flagged, since sellers routinely do light cosmetic
  staging on a genuine fixer without having done the real reno work
- Also excludes listings describing a vacant lot or development/entitlement
  play (`VACANT_LAND_FLAGS`, e.g. "planned for a 5-bedroom residence...
  existing plans may be transferable") - there's no existing structure for
  the reno-cost model to apply to

## Buy box

Covers 64 zips across San Francisco, the full Peninsula (all of San Mateo
Co.), Sunnyvale, Oakland (incl. West/North Oakland sub-regions), Richmond
CA, Berkeley, San Leandro, and San Jose. Richmond CA (East Bay, zips
94801/94804-94806) is a different city than SF's "Richmond District"
neighborhood (zip 94118/94121) - don't confuse the two.

Rounded out San Mateo Co. to full coverage: Belmont (94002), Brisbane
(94005), Pacifica (94044), Menlo Park (94025), Atherton (94027), Half Moon
Bay (94019). Hillsborough and Woodside don't get their own zips - they
share 94010 (with Burlingame) and 94062 (with Redwood City) respectively,
both already covered.

Two findings from this pass worth knowing:
- **Atherton (94027) has zero single-family listings under $1.5M at all**
  right now - every "candidate" Redfin's zip search returned actually
  belonged to a neighboring zip once its real address was parsed. Real
  comps there run $2,567/sqft (the most expensive zip in the whole scan),
  so a $1.5M cap effectively excludes the entire town. Not a scraping gap.
- The only two leads that cleared the filters here (189 Kent Rd, 100
  Palmetto Ave, both Pacifica) have **no fixer/distress language at all**
  in their listings - they read as oceanfront luxury copy ("gourmet
  kitchen," "iconic residence") - and both are oversized for their zip's
  typical comp (3,000-3,900 sqft), which is the exact pattern where the
  flat $/sqft ARV model is known to overstate value. Flagged low-confidence
  in the feed rather than presented as solid picks.

Juan's own Peninsula/Oakland regional list (added directly to
`target_zips`, verbatim zips): Peninsula (San Mateo Co.) 94010, 94014,
94015, 94030, 94061, 94062, 94063, 94065, 94066, 94070, 94080, 94401,
94402, 94403, 94404; West Oakland 94607, 94608, 94609; North Oakland
94610, 94611, 94618, 94619. 94066 (San Bruno) and 94404 (San Mateo/Foster
City) had zero single-family sold comps in the last 6 months under this
script's search, so their ARV basis falls back to the median $/sqft across
every other zip checked in the same batch rather than a zip-specific
number - treat leads there with extra caution.

This run's validation also caught three more gaps: "meticulously
updated...new plumbing, electrical, roof, foundation" and "tastefully
modernized" as renovation-completed phrasings (added to
`ALREADY_RENOVATED_FLAGS`); "two-home Property...Both units have been
updated" as a multi-unit phrasing (added "two-home", "two separate
residences", "both units" to `MULTI_UNIT_FLAGS`); and two listings whose
detail pages returned literally nothing (no description, no year built) -
these are now excluded automatically (`is_data_incomplete`) rather than
silently scored off default assumptions with zero listing text to verify
against.

San Jose's own search (95111/95112/95116/95121/95122/95123/95127/95133/
95136/95148) turned up only 2 qualifying candidates out of 181 raw active
listings and 75 enriched - most of that inventory was already renovated.
Both survivors carry real caveats: one (657 Woodland Ter) sits right next
to an identical 2006-built twin explicitly listed as "effectively rebuilt in
2026," so it's plausibly already-finished too despite lacking the exact
renovation phrasing this script flags on; the other (538 N White Rd) is a
court/trustee auction - occupied, no inspection allowed, sold sight-unseen.
Neither should be treated as a high-confidence pick without manual
follow-up. This run is also what caught "effectively rebuilt", "newer
kitchen" as renovation-completed phrasings this script hadn't been
flagging - now added to `ALREADY_RENOVATED_FLAGS`.

Oakland/Berkeley/East Bay was added because it's a genuinely different,
cheaper submarket than the Peninsula/SF: real comps there run $510-$1,241/sqft
vs. $860-$1,928/sqft on the Peninsula/SF side, and SF's own Richmond District
turned out to have the priciest comps in the whole scan with almost no
inventory under $1.5M - checking a market against its own comps rather than
assuming similarity to a neighboring one is exactly why the East Bay run
surfaced 8 genuine fixer candidates.

One open ARV caveat found in the East Bay run: the flat $/sqft-percentile
model overstates value for outlier-large homes (a 5,000+ sqft house priced
off the same $/sqft as typical 1,800 sqft comps in its zip) - manually verify
against size-matched comps before trusting a spread on anything unusually
large for its zip.

## Twin Home Buyer flip-analyst methodology (current)

This replaced an earlier spread-percentage/ADU-potential model entirely.
Nothing below is a guess - it's Juan's given rules, with the few
non-specified assumptions (property tax rate, flat utilities estimate)
called out explicitly rather than silently invented:

- **ARV**: median $/sqft of each target zip's actual homes sold in the last
  6 months (`build_arv_benchmarks()`), times the subject's sqft. No
  lot-size/bed-count adjustments layered on top. This is a zip-wide
  aggregate proxy, not 4-8 hand-picked 1-mile-radius comps with sale dates -
  the automated scraper doesn't pull individual comp addresses, so treat it
  as a screen and pull real comps before offering. Zips with zero sold
  comps of their own fall back to the median $/sqft across every other zip
  checked in the same run.
- **Rehab cost - two scenarios, always both computed**: Light = $70/sqft
  (cosmetic only), Heavy = $145/sqft (stated midpoint of the given
  $140-150/sqft "everything new" range). Flat add-ons for specific items
  found in the listing description (soft story/foundation +$40k,
  knob-and-tube/electrical +$20k, roof +$15k) apply to both scenarios,
  since those are itemized costs, not part of the per-sqft blend. No
  condition-based rate selection or contingency multiplier beyond that -
  the two scenarios ARE the range.
- **Holding costs (3 months)**: 10% annual rate on purchase price, prorated
  (2.5% of price) + insurance ($2,000 per $1M of price) + property tax
  (1.25%/year CA-typical estimate, prorated 3 months - not given verbatim,
  a documented assumption) + a flat $400 utilities estimate for a vacant
  property (also a documented assumption, not given verbatim).
- **Profit gate**: minimum required GROSS PROFIT (a dollar figure, not a
  percentage) tiered by ARV: $1M+ ARV needs $100k min, $500k-$1M needs
  $70k min, under $500k needs $50k min. A lead only reaches the report/feed
  if it clears this threshold under the Light rehab scenario at minimum.
- **Recommended Max Offer**: solved algebraically from ARV, Heavy rehab
  cost, and the min profit threshold, backing out the holding-cost rate.
- No "ADU Potential" anywhere (removed from scoring, risks, and output).
- No "Reno Budget" label - "Rehab Cost (Light)" / "Rehab Cost (Heavy)".
- **Known limitation, flagged not fixed**: the flat $/sqft model
  overstates ARV for outlier-large homes (a zip's comps skew toward
  typical 1,200-2,000 sqft homes, so a 3,000+ sqft subject priced off the
  same $/sqft looks like a much bigger spread than it really is). Rather
  than inventing a size adjustment the given rules don't call for,
  `identify_risks()` flags any listing >=3,000 sqft so it's visibly
  lower-confidence in the report/sheet rather than silently trusted.

This is still an approximation, not an appraisal - it doesn't match comps
by bed/bath count or condition, just by zip and percentile. Pull real,
hand-picked comps before making an offer on anything this script surfaces.

## Recurring check (`hourly_check.py`) and full scans

`hourly_check.py` is a lighter-weight companion script for running on a
schedule (Juan asked for hourly). It does NOT rebuild comps or re-enrich
every listing every run - only a full `flip_scout_redfin.py` scan does
that by default. Instead:

- `comp_benchmarks_cache.json` caches ARV benchmarks; only rebuilt if older
  than 7 days (`COMP_CACHE_MAX_AGE_DAYS`), since sold comps don't move
  hour to hour and rebuilding them every run would be ~45 wasted requests
- `seen_listings.json` tracks every listing URL already checked; each run
  only searches active listings (cheap, no detail-page fetch) and diffs
  against this set, so only genuinely new listings get enriched and scored
- Writes `new_leads.json` only when something new clears the filters, and
  deletes it if nothing does - the caller (a routine/cron resuming this
  session) checks for that file's existence to decide whether to update the
  report artifact and notify Juan, or stay silent

A full `flip_scout_redfin.py` run also now persists this same state
(`persist_full_scan_state()`, called from `main()`) - not just the top 10
leads shown in the console report, but every qualifying lead the run
found. Before this, only `hourly_check.py` wrote to
`leads_for_sheets.json`, so a full scan's results never reached Juan's
spreadsheet unless someone manually converted them afterward.

All three files (`comp_benchmarks_cache.json`, `seen_listings.json`,
`leads_for_sheets.json`) are committed back to the repo after each run so
state survives across sessions - **without doing that, every run would
think everything is "new" again.**
