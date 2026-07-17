# Juan's Autonomous Real Estate Flip Scout Agent

Scans Redfin for single-family fixer-uppers in Juan's target Bay Area zips,
estimates ARV/reno/spread for each, scores them against his buy box, and
outputs a ranked list of flip candidates.

## Usage

```
pip install -r flip_scout/requirements.txt
python flip_scout/flip_scout_redfin.py
```

Prints a ranked report to the console and writes `flip_report_YYYYMMDD.txt`.

## What changed from the original draft

The original script targeted a `window.initialState` JSON blob and
`HomeCard-*` CSS classes that Redfin has since replaced with `bp-Homecard__*`
markup. `flip_scout_redfin.py` now:

- Scrapes the current card markup for address/price/beds/baths/sqft/URL
- Filters out condo/TIC units and multi-address (duplex-style) listings that
  slip through Redfin's "house" filter
- Enriches shortlisted candidates with each listing's detail page
  (description, lot size, year built) to drive the reno-cost and scoring
  heuristics
- Corrects the ZIP code from the listing's own address rather than the
  searched ZIP, since Redfin's zip search returns some neighboring-zip results

## Important caveat

`ARV_PSF` in the config is a rough $/sqft-by-neighborhood table, not a
comp-based valuation - every ARV and spread % in the report is a first-pass
screen only. Pull real recent sold comps before making an offer on anything
this script surfaces.
