# Juan's Autonomous Real Estate Flip Scout Agent

Scans Redfin for single-family fixer-uppers in Juan's target Bay Area zips,
estimates ARV/reno/spread for each from real sold comps, scores them against
his buy box, and outputs a ranked list of flip candidates.

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

Covers 9 cities / 35 zips: San Francisco, San Mateo, Sunnyvale, Daly City,
South San Francisco, **Oakland, Richmond CA, Berkeley, and San Leandro**.
Richmond CA (East Bay, zips 94801/94804-94806) is a different city than SF's
"Richmond District" neighborhood (zip 94118/94121) - don't confuse the two.

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

## ARV methodology

`build_arv_benchmarks()` pulls each target zip's actual homes sold in the
last 6 months and uses the 75th-percentile $/sqft as that zip's ARV basis -
a proxy for renovated/top-tier condition, since ARV should reflect
after-repair value rather than the neighborhood average. This replaced an
earlier hardcoded per-zip $/sqft table that was never validated against
data; checking it against comps afterward showed it had undervalued San
Mateo and Sunnyvale by 40-77% and overvalued parts of San Francisco by
~20% - which was silently steering every result toward San Francisco even
after the per-zip shortlisting fix above.

This is still an approximation, not an appraisal - it doesn't match comps
by bed/bath count or condition, just by zip and percentile. Pull real,
hand-picked comps before making an offer on anything this script surfaces.
