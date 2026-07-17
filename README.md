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
