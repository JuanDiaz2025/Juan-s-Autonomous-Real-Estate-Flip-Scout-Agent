#!/usr/bin/env python3
"""
Juan's Flip Scout Agent - Redfin Edition
Searches Redfin for single-family homes under $1.5M in target Bay Area /
Central Valley zips, runs Twin Home Buyer's flip-analyst methodology on
each, and outputs ranked flip candidates.

Run with: python flip_scout_redfin.py

Notes on this version:
Redfin's markup has changed since the original scraper was written - it no
longer exposes a `window.initialState` JSON blob, and the old `HomeCard-*`
class names have been replaced by `bp-Homecard__*`. This version scrapes the
current markup directly, then enriches shortlisted candidates with data from
each listing's detail page (description, lot size, year built).

METHODOLOGY (Twin Home Buyer standard, effective this revision):
Replaces the earlier spread-percentage model entirely. Rules below are
followed exactly as given - nothing here is a guess:

- ARV: median $/sqft of each zip's actual homes sold in the last 6 months,
  restricted to comps within a similar size band to the subject (+/-20%,
  widening to +/-40% then +/-60% only if too few comps clear the tighter
  band - see SIZE_MATCH_BANDS), times the subject's sqft. Bryan flagged the
  original zip-wide-median version (no size filter at all) as too
  optimistic - it let a handful of large/luxury sold comps set the $/sqft
  for a typical-sized fixer that will never sell at that rate. No lot/bed
  adjustments beyond size-matching. If a zip doesn't have enough
  size-matched comps even at the widest band, it falls back to that zip's
  full comp set (flagged _arv_size_matched=False, surfaced as a risk); if
  the zip has no comps at all, it falls back to every comp fetched this
  run. CAVEAT: still a zip-wide/size-wide aggregate proxy, not 4-8
  hand-picked 1-mile-radius comps with sale dates - the automated scraper
  doesn't pull individual comp addresses. Treat as a screen, verify
  manually before offering.
- Rehab cost: two explicit scenarios, both always computed -
  Light = $70/sqft, Heavy = $140-150/sqft (using $145 as the stated
  midpoint). Plus flat add-ons for specific items mentioned in the listing
  (soft story/foundation +$40k, knob-and-tube/electrical +$20k, roof
  +$15k) - applied to both scenarios, since those are itemized costs, not
  part of the per-sqft blend. No condition-based rate selection or
  contingency multiplier beyond that - the two scenarios ARE the range.
- Holding costs: 3 months. 10% annual rate on purchase price, prorated
  (2.5% of price) + insurance (scaled at $2,000 per $1M of price) +
  property tax (1.25%/year CA-typical estimate, prorated 3 months) +
  a flat $400 utilities estimate for a vacant property over 3 months.
  These last two aren't in the given rules verbatim - "include other
  typical costs (utilities, taxes) conservatively" was instructed without
  exact figures, so reasonable, clearly-documented assumptions are used
  and callable out here rather than silently invented.
- Profit gate: minimum required GROSS PROFIT (not %) by ARV tier -
  $1M+ ARV: $100k min. $500k-$1M ARV: $70k min. Under $500k: $50k min.
- No ADU Potential anywhere (removed from scoring, risks, and output).
- No "Reno Budget" label - "Rehab Cost (Light)" / "Rehab Cost (Heavy)".
"""

import requests
from bs4 import BeautifulSoup
import re
import json
import os
import time
import statistics
from datetime import datetime
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# ================================
# CONFIGURATION (Juan's Buy Box)
# ================================
CONFIG = {
    "max_price": 1_500_000,
    # No price floor - a motivated seller can price well under $400k, and the
    # profit gate + PRICE ANOMALY flag (below $500k in SF) already catch
    # anything actually too-good-to-be-true, so this doesn't need a cutoff.
    "min_price": 0,
    # SF (94124 Bayview, 94112 Excelsior, 94134 Portola, 94118 Inner Richmond,
    #     94116/94122 Sunset, 94110 Mission, 94121 Outer Richmond) - a
    # distinct, expensive Peninsula/SF market that's largely already-renovated
    # or thin on inventory. See East Bay block below for a genuinely
    # different (cheaper, more distressed) submarket.
    "target_zips": ["94124", "94112", "94134", "94118", "94116", "94122", "94110", "94121",
                     # Peninsula (San Mateo Co.) - Juan's full regional list:
                     # 94010 Burlingame, 94014/94015 Daly City, 94030 Millbrae,
                     # 94061/94062/94063 Redwood City, 94065 Redwood Shores,
                     # 94066 San Bruno, 94070 San Carlos, 94080 South SF,
                     # 94401/94402/94403/94404 San Mateo/Foster City
                     "94010", "94014", "94015", "94030", "94061", "94062", "94063",
                     "94065", "94066", "94070", "94080",
                     "94401", "94402", "94403", "94404",
                     # Rest of San Mateo Co. for full Peninsula coverage:
                     # 94002 Belmont, 94005 Brisbane, 94044 Pacifica,
                     # 94025 Menlo Park, 94027 Atherton, 94019 Half Moon Bay
                     # (Hillsborough shares 94010 w/ Burlingame, Woodside
                     # shares 94062 w/ Redwood City - already covered above)
                     "94002", "94005", "94044", "94025", "94027", "94019",
                     # Sunnyvale
                     "94085", "94086", "94087", "94088",
                     # Oakland - split into Juan's own sub-regions:
                     # West Oakland (94607, 94608, 94609 Temescal),
                     # North Oakland (94610 Grand Lake, 94611 Piedmont Ave/
                     #  Upper Rockridge, 94618 Rockridge, 94619 Redwood Hts),
                     # plus the rest of Oakland already covered (94601
                     # Fruitvale, 94602 Redwood Heights/Laurel, 94603
                     # Elmhurst, 94605 Eastmont/Hills, 94606 San Antonio,
                     # 94621 Deep East Oakland)
                     "94607", "94608", "94609",
                     "94610", "94611", "94618", "94619",
                     "94601", "94602", "94603", "94605", "94606", "94621",
                     # Richmond, CA (East Bay - a different, cheaper city than
                     # SF's "Richmond District" neighborhood above)
                     "94801", "94804", "94805", "94806",
                     # Berkeley (94702/94703 - South/West, more affordable)
                     "94702", "94703",
                     # San Leandro
                     "94577", "94578",
                     # San Jose (95111 Blossom Valley, 95112 Central,
                     #  95116/95122/95127/95133 East San Jose - more affordable,
                     #  95121/95123/95136/95148 South/Southeast San Jose)
                     "95111", "95112", "95116", "95121", "95122", "95123",
                     "95127", "95133", "95136", "95148"],

    # --- Rehab cost rates (Twin Home Buyer standard - exact, not adjustable
    # by condition language) ---
    "light_rehab_psf": 70,
    "heavy_rehab_psf": 145,  # stated range is $140-150/sqft; 145 is the midpoint

    # --- Holding costs (3-month hold) ---
    "holding_months": 3,
    "holding_annual_rate": 0.10,      # prorated for 3 months = 2.5% of price
    "insurance_per_million": 2000,    # scales with price, per the "scale appropriately" instruction
    "property_tax_annual_rate": 0.0125,  # CA-typical estimate; not in the given rules verbatim
    "utilities_holding_flat": 400,       # flat conservative estimate, 3 months vacant

    # --- Minimum required GROSS PROFIT by ARV tier (dollar amounts, not %) ---
    "profit_thresholds": [
        (1_000_000, 100_000),   # $1M+ ARV -> min $100k profit (covers the $1M-$1.5M band and above)
        (500_000, 70_000),      # $500k-$1M ARV -> min $70k profit
        (0, 50_000),            # under $500k ARV -> min $50k profit
    ],

    "detail_enrich_limit": 6,  # candidates enriched per zip (detail page fetch is the slow step)
    "sold_lookback": "sold-6mo",
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# Populated at runtime by build_arv_benchmarks() from real sold comps - see
# calculate_arv(). Never hand-edit; it's recomputed fresh on every run.
ARV_BENCHMARKS: Dict[str, float] = {}
# Populated by run_redfin_scout() each call - the full qualifying list before
# the top-10 cut, and every DETAIL-ENRICHED candidate's URL this scan
# (qualifying or not) - deliberately NOT every raw card-level candidate, so
# a candidate the per-zip quota skipped enriching doesn't get marked "seen"
# and permanently excluded from ever being evaluated (see run_redfin_scout).
# Kept as globals (same pattern as ARV_BENCHMARKS) so main() can persist full
# state after a run without run_redfin_scout()'s return signature changing.
LAST_ANALYZED: List[Dict] = []
LAST_ALL_URLS: List[str] = []

MULTI_UNIT_FLAGS = ['duplex', 'triplex', 'fourplex', 'multi-family', 'multifamily',
                     '2 units', '3 units', '4 units', 'two-unit', 'multi-unit',
                     'tenancy in common', 'two-home', 'two separate residences',
                     'two full residences', 'both units',
                     # Caught during a manual renovation audit: "718 26th St"
                     # described an attached ADU + JADU studio ("three
                     # separate living spaces") with none of the phrases
                     # above matching - an ADU/JADU-equipped property is a
                     # multi-unit income play, not a single-family fixer.
                     'accessory dwelling unit', 'jadu', 'junior adu',
                     'attached adu', 'three separate living spaces']

# Listing language indicating the flip has effectively already happened - no
# renovation upside left for this buy box. Excluded regardless of profit
# math, since a big "profit" on an already-renovated house just means it's
# priced below comps (a wholesale play), not a flip opportunity.
ALREADY_RENOVATED_FLAGS = [
    'beautifully updated', 'fully renovated', 'fully updated', 'move-in ready', 'move in ready',
    'previously remodeled', 'thoughtfully updated', 'beautifully remodeled',
    'extensive interior updates', 'extensive updates', 'studs-up', 'beautifully reimagined',
    'updated kitchen', 'updated bath', 'remodeled kitchen', 'remodeled chef', 'designer finishes',
    'newly remodeled', 'refurbished kitchen', 'reimagined home', 'contemporary design',
    'in great condition', 'in move-in condition', 'move-in condition', 'has been updated',
    'turnkey', 'tastefully remodeled', 'recently updated', 'recently renovated',
    'recently remodeled', 'were remodeled', 'was remodeled', 'effectively rebuilt',
    'newer kitchen', 'newly rebuilt', 'complete rebuild', 'tastefully modernized',
    'freshly updated', 'meticulously updated', 'have been updated',
]
# Deliberately NOT included: "refreshed" alone - sellers routinely do light
# cosmetic staging (paint, cleaning) before listing a genuine fixer, and that
# alone doesn't mean the real reno work (kitchen/bath/systems) is done. Only
# flag it if paired with something specific ("kitchen was refreshed", etc);
# a bare "thoughtfully refreshed" is too ambiguous to exclude on.

# Listing describes a vacant lot, teardown, or development/entitlement play -
# there's no existing structure to renovate, so the per-sqft rehab model
# doesn't apply and this isn't the buy-fixer-sell-renovated thesis at all.
VACANT_LAND_FLAGS = [
    'planned for a', 'existing plans', 'development project', 'vacant lot',
    'build your dream home on this lot', 'proposed floor plan', 'lot for sale',
    'buildable lot',
]

# ================================
# REDFIN SCRAPER ENGINE
# ================================

# Safety cap on pages fetched per zip/search - not a guess at real inventory,
# just a backstop against ever looping forever if Redfin's pagination links
# behave unexpectedly. 400+ listings under one zip/price/lookback filter
# would be extraordinary; if it ever happens, this caps the damage rather
# than hanging indefinitely.
MAX_SEARCH_PAGES = 10


def _fetch_redfin_page(url: str, retries: int = 2, delay: float = 1.5) -> Optional[str]:
    """
    GET with retry - confirmed live that Redfin occasionally answers a real,
    populated page with an empty/HTTP-202 "checking your browser"-style
    response, even though an immediate retry of the identical URL returns
    the real content. Without this, a single transient hiccup would look
    exactly like "this zip/page has zero listings" rather than what it
    actually is - a request that needs to be tried again. A short body
    (<5000 bytes) is treated as that same kind of non-answer, real result
    pages are consistently hundreds of KB.
    """
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            if len(r.text) > 5000:
                return r.text
        except Exception:
            pass
        if attempt < retries:
            time.sleep(delay)
    return None


def search_redfin(zip_code: str, max_price: int = CONFIG["max_price"]) -> List[Dict]:
    """
    Search Redfin's current markup for single-family homes in a ZIP code.
    Paginates through every results page (up to MAX_SEARCH_PAGES) rather
    than just the first - some zips have more active listings than fit on
    one page (confirmed live: 94605 had 41 on page 1 and 29 more on page 2,
    zero overlap between them - page 1 alone was missing 41% of that zip's
    actual inventory).
    """
    listings = []
    seen_hrefs = set()
    base_url = (f"https://www.redfin.com/zipcode/{zip_code}/filter/"
                f"property-type=house,max-price={max_price}")

    for page in range(1, MAX_SEARCH_PAGES + 1):
        url = base_url if page == 1 else f"{base_url}/page-{page}"
        text = _fetch_redfin_page(url)
        if text is None:
            if page == 1:
                print(f"  ⚠️ Error fetching ZIP {zip_code}: no usable response after retries")
            break

        soup = BeautifulSoup(text, 'html.parser')
        cards = soup.find_all('div', {'class': re.compile(r'HomeCardContainer')})
        if not cards:
            break  # genuinely no (more) results on this page

        for card in cards:
            html = str(card)
            addr_m = re.search(r'class="bp-Homecard__Address[^"]*"\s+href="([^"]+)"[^>]*>([^<]+)</a>', html)
            price_m = re.search(r'bp-Homecard__Price--value">\$([\d,]+)', html)
            beds_m = re.search(r'bp-Homecard__Stats--beds[^"]*">([\d.]+)\s*bed', html)
            baths_m = re.search(r'bp-Homecard__Stats--baths[^"]*">([\d.]+)\s*bath', html)
            sqft_m = re.search(r'LockedStat--value">([\d,]+)', html)
            if not (addr_m and price_m):
                continue

            href, address_text = addr_m.group(1), addr_m.group(2)
            if href in seen_hrefs:
                continue  # same listing surfaced again across pages (live reordering)
            seen_hrefs.add(href)

            # Exclude condo/TIC units and multi-address (duplex-style) buildings
            # that Redfin's "house" filter still lets through. Check the URL slug,
            # not just the displayed address text - Redfin sometimes shows only the
            # first street number on the card (e.g. "451 8th Ave") while the URL
            # keeps the full multi-address slug ("451-453-8th-Ave-...").
            if '#' in address_text or '/unit-' in href.lower():
                continue
            if re.match(r'^\d+-\d+\s', address_text) or re.search(r'/\d+-\d+-', href):
                continue

            price = int(price_m.group(1).replace(',', ''))
            beds = float(beds_m.group(1)) if beds_m else 0
            baths = float(baths_m.group(1)) if baths_m else 0
            sqft = int(sqft_m.group(1).replace(',', '')) if sqft_m else 0

            parts = [p.strip() for p in address_text.split(',')]
            city = parts[1] if len(parts) > 1 else ''
            zip_match = re.search(r'(\d{5})', parts[-1]) if parts else None
            real_zip = zip_match.group(1) if zip_match else zip_code
            # Cross-check against the zip embedded in the URL slug itself
            # (".../3226-Champion-St-94602/home/1986790") - that's a
            # structurally anchored value Redfin generates from its own
            # listing record, vs. free-text parsing of the displayed card,
            # which has been seen to mis-scrape a digit (94602 -> 92602 on
            # one listing). Prefer the URL's zip whenever it's available.
            url_zip_match = re.search(r'-(\d{5})/home/\d+', href)
            if url_zip_match:
                real_zip = url_zip_match.group(1)

            listing = {
                'address': parts[0],
                'city': city,
                'zip': real_zip,
                'price': price,
                'beds': beds,
                'baths': baths,
                'sqft': sqft,
                'lot_sqft': 0,
                'year_built': 0,
                'property_type': 'Single Family',
                'description': '',
                'url': f"https://www.redfin.com{href}",
                'status': 'Active',
                'is_multi_unit': False,
                'is_already_renovated': False,
                'is_vacant_land': False,
            }
            if CONFIG['min_price'] <= price <= CONFIG['max_price'] and sqft > 0 and beds > 0:
                listings.append(listing)

        if page < MAX_SEARCH_PAGES:
            time.sleep(0.3)  # be respectful between pages, same as between zips

    return listings


SALE_HISTORY_ROW = re.compile(
    r'<div class="BasicTable__col date">([^<]+)</div>'
    r'<div class="BasicTable__col event">([^<]+)</div>'
)

# Events that mark the start of the CURRENT active listing period. Anything
# older than the nearest one of these (scanning from today backwards) belongs
# to a previous ownership/listing cycle and must not be counted.
LISTING_START_EVENTS = ("Listed", "Relisted")
# Events that mean the property is (or very recently was) off-market. If one
# of these shows up before we find a Listed/Relisted marker, Redfin's own
# history table disagrees with the active-search result that put this
# listing in front of us - don't guess a days-on-market figure in that case.
LISTING_BREAK_EVENTS = ("Pending", "Sold", "Listing Removed", "Delisted")


def parse_days_on_market(text: str) -> Dict:
    """
    Real days-on-market and price-cut count from Redfin's own Sale History
    table (not the ambiguous "timeOnRedfin" field, which is a raw duration
    that doesn't distinguish current-listing time from prior cycles).

    Returns {'days_on_market': int, 'price_cuts': int} when the table's most
    recent event is an unambiguous Listed/Relisted, or {} when it isn't
    (property plan/new-construction with no history, or the top event is
    Pending/Sold/Listing Removed - i.e. the table doesn't agree the listing
    is currently active, so don't fabricate a number).
    """
    rows = SALE_HISTORY_ROW.findall(text)
    price_cuts = 0
    for date_str, event in rows:
        event = event.strip()
        if event == "Price Changed":
            price_cuts += 1
            continue
        if event in LISTING_START_EVENTS:
            try:
                listed_date = datetime.strptime(date_str.strip(), "%b %d, %Y")
            except ValueError:
                return {}
            return {
                "days_on_market": (datetime.now() - listed_date).days,
                "price_cuts": price_cuts,
            }
        if event in LISTING_BREAK_EVENTS:
            return {}  # ambiguous vs. the active-search result - don't guess
    return {}  # no history table at all (e.g. a builder "Plan" listing)


def enrich_detail(listing: Dict) -> Dict:
    """Pull description, lot size, year built, and days-on-market from the listing's detail page."""
    try:
        r = requests.get(listing['url'], headers=HEADERS, timeout=20)
        text = r.text

        def find(pattern, cast=int):
            m = re.search(pattern, text)
            return cast(m.group(1)) if m else None

        lot = find(r'\\?"lotSize\\?":(\d+)')
        year = find(r'"yearBuilt":(\d+)')
        desc_m = re.search(r'description\\?":\\?"(.{50,600})', text)
        desc = desc_m.group(1) if desc_m else ''
        desc = desc.split('\\",')[0].split('","')[0]

        lower_text = (desc + ' ' + text[:20000]).lower()
        listing['is_multi_unit'] = (
            any(flag in lower_text for flag in MULTI_UNIT_FLAGS)
            or bool(re.search(r'/\d+-\d+-', listing.get('url', '')))
        )
        # Checked against the listing's OWN description only (not the wider
        # page) to avoid false positives from unrelated nearby-homes copy.
        listing['is_already_renovated'] = any(flag in desc.lower() for flag in ALREADY_RENOVATED_FLAGS)
        listing['is_vacant_land'] = any(flag in desc.lower() for flag in VACANT_LAND_FLAGS)

        if lot:
            listing['lot_sqft'] = lot
        if year:
            listing['year_built'] = year
        listing['description'] = desc
        listing.update(parse_days_on_market(text))
    except Exception:
        pass
    # If the detail page yielded nothing usable (no description, no year
    # built), there's no listing text to judge condition against at all -
    # don't let it get scored with silent default assumptions.
    listing['is_data_incomplete'] = (not listing.get('description')) and not listing.get('year_built')
    return listing


def fetch_zip_comps(zip_code: str) -> List[Dict]:
    """
    Pull actual sold single-family comps for a zip over the lookback window -
    price AND sqft for each (not just a flat $/sqft), so ARV can later be
    computed from comps matched to the SUBJECT's size rather than every
    sold home in the zip regardless of how comparable it is. Paginates
    through every results page (up to MAX_SEARCH_PAGES), same reasoning as
    search_redfin() - confirmed live that 94605 alone has FOUR pages of sold
    comps, so a single-page fetch was quietly building the ARV benchmark
    off a fraction of the real comp pool for busier zips.
    """
    comps = []
    seen_pairs = set()
    base_url = (f"https://www.redfin.com/zipcode/{zip_code}/filter/"
                f"property-type=house,include={CONFIG['sold_lookback']}")

    for page in range(1, MAX_SEARCH_PAGES + 1):
        url = base_url if page == 1 else f"{base_url}/page-{page}"
        text = _fetch_redfin_page(url)
        if text is None:
            if page == 1:
                print(f"  ⚠️ Error fetching comps for {zip_code}: no usable response after retries")
            break

        soup = BeautifulSoup(text, 'html.parser')
        cards = soup.find_all('div', {'class': re.compile(r'HomeCardContainer')})
        if not cards:
            break

        for card in cards:
            html = str(card)
            price_m = re.search(r'bp-Homecard__Price--value">\$([\d,]+)', html)
            sqft_m = re.search(r'LockedStat--value">([\d,]+)', html)
            if not (price_m and sqft_m):
                continue
            price = int(price_m.group(1).replace(',', ''))
            sqft = int(sqft_m.group(1).replace(',', ''))
            if price > 50000 and sqft > 200:
                pair = (price, sqft)  # no per-listing URL scraped here - dedupe on (price, sqft)
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                comps.append({'price': price, 'sqft': sqft, 'psf': price / sqft})

        if page < MAX_SEARCH_PAGES:
            time.sleep(0.3)

    return comps


def build_arv_benchmarks(zip_codes: List[str]) -> Dict[str, List[Dict]]:
    """
    Pull each zip's raw sold comps (price + sqft, not a pre-collapsed
    number) so calculate_arv() can size-match at analysis time. Storing the
    scalar median here (like the earlier revision did) baked in every sold
    home regardless of size, which is exactly what made ARV too optimistic
    for a typical-sized fixer sitting in a zip whose recent sales skew
    larger/pricier.
    """
    benchmarks = {}
    all_comps = []
    for z in zip_codes:
        comps = fetch_zip_comps(z)
        benchmarks[z] = comps
        all_comps.extend(comps)
        if comps:
            med = statistics.median(c['psf'] for c in comps)
            print(f"  {z}: {len(comps)} sold comps, median ${med:,.0f}/sqft")
        else:
            print(f"  {z}: no sold comps found")
        time.sleep(0.3)

    # zips with no comps of their own fall back to every comp fetched this
    # run (still real data, just not zip-specific) - calculate_arv() applies
    # the same size-matching to this pool, not a hand-picked guess
    benchmarks['__fallback__'] = all_comps
    return benchmarks

# ================================
# ANALYTICS ENGINE (Twin Home Buyer flip-analyst methodology)
# ================================

# Progressive size-match bands, as a fraction of the subject's sqft (e.g.
# 0.20 = comps within +/-20% of subject sqft). Widens only if the tighter
# band doesn't have enough comps to be a real median. This convention
# (not a number Twin Home Buyer specified) mirrors standard appraisal
# practice of comparing against similarly-sized homes, not the whole zip.
SIZE_MATCH_BANDS = (0.20, 0.40, 0.60)
MIN_SIZE_MATCHED_COMPS = 3


def _size_matched_psf(comps: List[Dict], sqft: int):
    """Median $/sqft from comps within the tightest size band that still
    clears MIN_SIZE_MATCHED_COMPS; widens the band if needed. Returns
    (psf, comp_count, was_size_matched) or (None, 0, False) if comps is empty."""
    for band in SIZE_MATCH_BANDS:
        lo, hi = sqft * (1 - band), sqft * (1 + band)
        matched = [c['psf'] for c in comps if lo <= c['sqft'] <= hi]
        if len(matched) >= MIN_SIZE_MATCHED_COMPS:
            return statistics.median(matched), len(matched), True
    if comps:
        # not enough size-matched comps even at the widest band - fall back
        # to the full pool, flagged as NOT size-matched rather than pretending
        return statistics.median(c['psf'] for c in comps), len(comps), False
    return None, 0, False


def calculate_arv(listing: Dict) -> Optional[float]:
    """
    ARV = median $/sqft of SIZE-MATCHED sold comps (see SIZE_MATCH_BANDS) x
    subject sqft. Falls back to the zip's full comp set only if too few
    similarly-sized comps exist, and to the global comp pool only if the zip
    has no comps at all (or isn't one of the scanned zips, e.g. a
    neighboring-zip boundary catch) - all of this is flagged on the listing
    (_arv_size_matched, _arv_zip_benchmarked) so identify_risks() can
    surface low confidence rather than presenting it as equally solid. No
    lot-size/bed-count adjustments beyond size-matching - not adding
    anything past what was approved. Still a zip-wide/size-wide proxy, not
    hand-picked 1-mile-radius comps with sale dates - verify manually
    before offering.
    """
    sqft = listing.get('sqft', 0)
    if not sqft:
        return None

    zip_code = listing.get('zip', '')
    zip_benchmarked = zip_code in ARV_BENCHMARKS and zip_code != '__fallback__'
    comps = ARV_BENCHMARKS.get(zip_code, [])
    psf, n, size_matched = _size_matched_psf(comps, sqft)
    if psf is None:
        comps = ARV_BENCHMARKS.get('__fallback__', [])
        psf, n, size_matched = _size_matched_psf(comps, sqft)
        if psf is None:
            return None  # no comp data available anywhere this run

    listing['_arv_comp_count'] = n
    listing['_arv_size_matched'] = size_matched
    listing['_arv_zip_benchmarked'] = zip_benchmarked
    return round(psf * sqft, -3)


def calculate_rehab_cost(listing: Dict) -> Dict[str, float]:
    """
    Both rehab scenarios, always. Light = $70/sqft, Heavy = $145/sqft
    (midpoint of the stated $140-150 range). Flat add-ons for specific
    items mentioned in the listing apply to both scenarios equally.
    """
    sqft = listing.get('sqft', 0)
    desc = listing.get('description', '').lower()

    addons = 0
    if 'soft story' in desc or 'foundation' in desc:
        addons += 40000
    if 'knob' in desc or 'tube' in desc or 'electrical' in desc:
        addons += 20000
    if 'roof' in desc:
        addons += 15000

    light = round(CONFIG['light_rehab_psf'] * sqft + addons, -3)
    heavy = round(CONFIG['heavy_rehab_psf'] * sqft + addons, -3)
    return {'light': light, 'heavy': heavy}


def calculate_holding_costs(price: float) -> Dict[str, float]:
    """
    3-month hold: 10%/year prorated (2.5% of price) + insurance (scaled per
    $1M of price) + property tax (1.25%/year CA estimate, prorated 3mo) +
    a flat utilities estimate. The tax/utilities figures aren't in the
    given rules verbatim (which only said "include conservatively") - kept
    as clearly-labeled, reasonable assumptions rather than invented silently.
    """
    financing = price * CONFIG['holding_annual_rate'] * (CONFIG['holding_months'] / 12)
    insurance = CONFIG['insurance_per_million'] * (price / 1_000_000)
    property_tax = price * CONFIG['property_tax_annual_rate'] * (CONFIG['holding_months'] / 12)
    utilities = CONFIG['utilities_holding_flat']

    total = financing + insurance + property_tax + utilities
    return {
        'financing': round(financing, -2),
        'insurance': round(insurance, -2),
        'property_tax': round(property_tax, -2),
        'utilities': utilities,
        'total': round(total, -2),
    }


def get_min_profit_threshold(arv: float) -> int:
    """Minimum required GROSS PROFIT (dollars, not %) by ARV tier."""
    for floor, threshold in CONFIG['profit_thresholds']:
        if arv >= floor:
            return threshold
    return CONFIG['profit_thresholds'][-1][1]


def calculate_max_offer(arv: float, rehab_heavy: float, min_profit: float) -> float:
    """
    Recommended max purchase price: the price at which gross profit under
    the HEAVY (conservative) rehab scenario exactly equals the minimum
    required profit for this ARV tier. Solves the holding-cost-on-price
    relationship algebraically (financing + insurance + property tax scale
    with price; utilities is flat).
    """
    rate = (CONFIG['holding_annual_rate'] * (CONFIG['holding_months'] / 12)
            + (CONFIG['insurance_per_million'] / 1_000_000)
            + CONFIG['property_tax_annual_rate'] * (CONFIG['holding_months'] / 12))
    numerator = arv - min_profit - rehab_heavy - CONFIG['utilities_holding_flat']
    if numerator <= 0:
        return 0
    return round(numerator / (1 + rate), -3)


def calculate_deal(listing: Dict) -> Optional[Dict]:
    """Full flip financials under both rehab scenarios - the core output block."""
    arv = calculate_arv(listing)
    if arv is None:
        return None
    price = listing.get('price', 0)

    rehab = calculate_rehab_cost(listing)
    holding = calculate_holding_costs(price)
    min_profit = get_min_profit_threshold(arv)

    total_cost_light = price + rehab['light'] + holding['total']
    total_cost_heavy = price + rehab['heavy'] + holding['total']
    gross_profit_light = arv - total_cost_light
    gross_profit_heavy = arv - total_cost_heavy

    meets_threshold_light = gross_profit_light >= min_profit
    meets_threshold_heavy = gross_profit_heavy >= min_profit

    max_offer = calculate_max_offer(arv, rehab['heavy'], min_profit)

    return {
        'arv': arv,
        'rehab_light': rehab['light'],
        'rehab_heavy': rehab['heavy'],
        'holding_costs': holding['total'],
        'holding_breakdown': holding,
        'total_cost_light': round(total_cost_light, -2),
        'total_cost_heavy': round(total_cost_heavy, -2),
        'gross_profit_light': round(gross_profit_light, -2),
        'gross_profit_heavy': round(gross_profit_heavy, -2),
        'min_profit_threshold': min_profit,
        'meets_threshold_light': meets_threshold_light,
        'meets_threshold_heavy': meets_threshold_heavy,
        'recommended_max_offer': max_offer,
    }


def classify_deal(deal: Dict) -> str:
    """Strong Deal / Marginal / Pass, per the required output categories."""
    if deal['meets_threshold_heavy']:
        return 'Strong Deal'
    if deal['meets_threshold_light']:
        return 'Marginal'
    return 'Pass'


def score_deal(listing: Dict, deal: Dict) -> int:
    """
    1-10, for ranking/sorting only (not part of the required output format,
    but useful to order candidates). Based on how far gross profit under the
    heavy (conservative) scenario clears its required threshold.
    """
    threshold = deal['min_profit_threshold']
    if threshold <= 0:
        return 1
    ratio = deal['gross_profit_heavy'] / threshold

    if ratio >= 1.5:
        score = 10
    elif ratio >= 1.2:
        score = 8
    elif ratio >= 1.0:
        score = 7
    elif deal['meets_threshold_light']:
        light_ratio = deal['gross_profit_light'] / threshold
        score = 5 if light_ratio >= 1.2 else 4
    else:
        score = 2 if deal['gross_profit_light'] > 0 else 1

    return min(10, max(1, score))


DAYS_ON_MARKET_STALE_THRESHOLD = 60  # a documented convention, not a given rule - see docstring below


def identify_risks(listing: Dict) -> List[str]:
    """
    Risk flags built only from data actually verified this scan - either the
    listing's own description, or (for days-on-market) Redfin's own Sale
    History table (parse_days_on_market, called from enrich_detail). Nothing
    here is a guess: if a signal can't be verified for a given listing (e.g.
    flood zone, code violations, or an ambiguous/missing sale-history table),
    it's simply left out rather than replaced with a blanket disclaimer.

    Days-on-market threshold (60 days) is a documented convention - real
    estate practice generally treats a listing as "sitting" past ~60 days -
    not a number Twin Home Buyer specified. A long time on market for a
    SPECIFIC listing is used here as the bad-signal proxy for its area,
    since that's what's cheaply verifiable per-listing from Redfin's own
    history; it is not a full area-wide average-DOM benchmark.
    """
    risks = []
    desc = listing.get('description', '').lower()

    if listing.get('price', 0) < 500000 and 'san francisco' in listing.get('city', '').lower():
        risks.append('PRICE ANOMALY - verify title/liens')
    if listing.get('lot_sqft', 0) and listing.get('lot_sqft', 0) < 2500:
        risks.append('Small lot')
    if 'bayview' in listing.get('address', '').lower():
        risks.append('Bayview - neighborhood still transitional')
    if listing.get('_arv_zip_benchmarked') is False:
        n = listing.get('_arv_comp_count', 0)
        risks.append(f'Outside the scanned buy box zips (likely a neighboring-zip search catch) - '
                      f'ARV uses a citywide comp pool ({n} comps), not this zip\'s own sold homes - '
                      f'verify local comps manually before trusting this ARV')
    elif listing.get('_arv_size_matched') is False:
        n = listing.get('_arv_comp_count', 0)
        risks.append(f'ARV not size-matched - only {n} comp(s) total for this zip, none in a '
                      f'comparable size band, so this uses the zip\'s full comp set (may skew '
                      f'high/low vs. a same-size home) - verify against size-matched comps manually')

    dom = listing.get('days_on_market')
    cuts = listing.get('price_cuts', 0)
    if dom is not None and (dom >= DAYS_ON_MARKET_STALE_THRESHOLD or cuts >= 2):
        cut_note = f", {cuts} price cut(s) since listing" if cuts else ""
        risks.append(f'On market {dom} days{cut_note} - possible sign of soft demand in this '
                      f'area or an overpriced/undesirable property, not just a fixer discount')

    return risks

# ================================
# MAIN AGENT
# ================================

def run_redfin_scout() -> List[Dict]:
    """Main entry point: scan Redfin, enrich, analyze, classify."""
    global ARV_BENCHMARKS, LAST_ANALYZED, LAST_ALL_URLS
    print("\n" + "=" * 60)
    print("JUAN'S FLIP SCOUT AGENT - REDFIN EDITION")
    print(f"{datetime.now().strftime('%B %d, %Y - %I:%M %p')}")
    print("=" * 60)
    price_floor = f"${CONFIG['min_price']:,.0f}" if CONFIG['min_price'] > 0 else "no floor"
    print(f"Target: Single-Family Homes {price_floor}-${CONFIG['max_price']:,.0f}")
    print(f"Zips scanned: {len(CONFIG['target_zips'])}\n")

    print("Building ARV benchmarks from real sold comps (last 6 months, median $/sqft)...")
    ARV_BENCHMARKS = build_arv_benchmarks(CONFIG['target_zips'])

    all_listings = []
    for zip_code in CONFIG['target_zips']:
        found = search_redfin(zip_code)
        print(f"  {zip_code}: {len(found)} candidates")
        all_listings.extend(found)
        time.sleep(0.4)  # be respectful

    seen_urls = set()
    deduped = []
    for l in all_listings:
        if l['url'] in seen_urls:
            continue
        seen_urls.add(l['url'])
        deduped.append(l)
    all_listings = deduped

    print(f"\nTotal card-level candidates (deduped): {len(all_listings)}")
    if not all_listings:
        print("No listings found. Redfin may be blocking requests, or no zips matched.")
        return []

    # Rough pre-check (no description yet) to prioritize which candidates are
    # worth the slower detail-page fetch. Quota this PER ZIP rather than
    # globally - otherwise zips with a higher comp-based ARV dominate a single
    # global ranking and starve every other zip of detail-page enrichment.
    for l in all_listings:
        rough = calculate_deal(l)
        l['_rough_profit'] = rough['gross_profit_light'] if rough else -10**9

    by_zip = {}
    for l in all_listings:
        by_zip.setdefault(l['zip'], []).append(l)

    shortlist = []
    for zip_code, items in by_zip.items():
        items.sort(key=lambda x: x['_rough_profit'], reverse=True)
        shortlist.extend(items[:CONFIG['detail_enrich_limit']])

    print(f"Enriching {len(shortlist)} candidates ({CONFIG['detail_enrich_limit']}/zip) with detail-page data...")
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = [ex.submit(enrich_detail, l) for l in shortlist]
        for i, fut in enumerate(as_completed(futures)):
            fut.result()
            if (i + 1) % 10 == 0:
                print(f"  enriched {i + 1}/{len(shortlist)}")

    analyzed = []
    for l in shortlist:
        if (l.get('is_multi_unit') or l.get('is_already_renovated') or l.get('is_vacant_land')
                or l.get('is_data_incomplete')):
            continue
        deal = calculate_deal(l)
        if deal is None or not deal['meets_threshold_light']:
            # doesn't clear the minimum profit threshold even in the best
            # (light rehab) case - not a profitable lead, don't surface it
            continue
        l['deal'] = deal
        l['score'] = score_deal(l, deal)
        l['recommendation'] = classify_deal(deal)
        l['risks'] = identify_risks(l)
        analyzed.append(l)

    analyzed.sort(key=lambda x: (x['score'], x['deal']['gross_profit_heavy']), reverse=True)
    top = [d for d in analyzed if d['recommendation'] == 'Strong Deal'][:10]
    if not top:
        top = analyzed[:10]

    LAST_ANALYZED = analyzed
    # Only mark candidates that were actually DETAIL-ENRICHED (shortlist) as
    # seen - not every raw card-level candidate (all_listings). The per-zip
    # detail_enrich_limit quota means most candidates in a big zip never get
    # enriched at all; marking them "seen" anyway would permanently exclude
    # them from ever being evaluated, since hourly_check.py (which has no
    # quota and fully enriches every genuinely-new listing) only looks at
    # URLs NOT already in seen_listings.json. Leaving them unseen here means
    # the very next hourly run gives them a real, un-quota-limited look.
    LAST_ALL_URLS = [l['url'] for l in shortlist]

    return top

# ================================
# REPORT GENERATOR
# ================================

def print_report(leads: List[Dict]):
    if not leads:
        print("\n" + "=" * 60)
        print("NO DEALS FOUND TODAY")
        print("=" * 60)
        return

    print("\n" + "=" * 60)
    print(f"TOP {len(leads)} DEALS FOUND")
    print("=" * 60 + "\n")

    for idx, lead in enumerate(leads, 1):
        d = lead['deal']
        print(f"{'=' * 60}")
        print(f"LEAD #{idx} — {lead['recommendation'].upper()} (score {lead['score']}/10)")
        print(f"{lead['address']}, {lead.get('city', '')}, CA {lead.get('zip', '')}")
        print(f"Beds/Baths/SqFt: {lead.get('beds', 0)}/{lead.get('baths', 0)}/{lead.get('sqft', 0):,}")
        print()
        arv_note = (f"median $/sqft, {lead.get('_arv_comp_count', 0)} size-matched comps, this zip, last 6mo"
                    if lead.get('_arv_size_matched') else
                    f"median $/sqft, {lead.get('_arv_comp_count', 0)} comps (NOT size-matched), this zip, last 6mo")
        print(f"Purchase Price:      ${lead.get('price', 0):,.0f}")
        print(f"Estimated ARV:       ${d['arv']:,.0f}  ({arv_note})")
        print(f"Rehab Cost (Light):  ${d['rehab_light']:,.0f}  (${CONFIG['light_rehab_psf']}/sqft)")
        print(f"Rehab Cost (Heavy):  ${d['rehab_heavy']:,.0f}  (${CONFIG['heavy_rehab_psf']}/sqft)")
        print(f"Holding Costs (3mo): ${d['holding_costs']:,.0f}")
        print(f"Total Cost (Light):  ${d['total_cost_light']:,.0f}")
        print(f"Total Cost (Heavy):  ${d['total_cost_heavy']:,.0f}")
        print(f"Gross Profit (Light):${d['gross_profit_light']:,.0f}")
        print(f"Gross Profit (Heavy):${d['gross_profit_heavy']:,.0f}")
        print(f"Min. Required Profit:${d['min_profit_threshold']:,.0f}")
        print(f"Meets Threshold?     Light: {'Yes' if d['meets_threshold_light'] else 'No'} | "
              f"Heavy: {'Yes' if d['meets_threshold_heavy'] else 'No'}")
        print(f"Recommended Max Offer: ${d['recommended_max_offer']:,.0f}")
        print()
        if lead.get('risks'):
            print("Risks:")
            for risk in lead['risks']:
                print(f"  - {risk}")
        print(f"Link: {lead['url']}")
        print()


def save_report(leads: List[Dict]):
    filename = f"flip_report_{datetime.now().strftime('%Y%m%d')}.txt"
    with open(filename, 'w') as f:
        f.write(f"Twin Home Buyer - Flip Scout Report - {datetime.now().strftime('%B %d, %Y')}\n")
        f.write("=" * 60 + "\n\n")
        if not leads:
            f.write("No deals found today.\n")
            return
        for idx, lead in enumerate(leads, 1):
            d = lead['deal']
            f.write(f"LEAD #{idx} - {lead['recommendation']} (score {lead['score']}/10)\n")
            f.write(f"Address: {lead['address']}, {lead.get('city', '')}, CA {lead.get('zip', '')}\n")
            f.write(f"Purchase Price: ${lead.get('price', 0):,.0f}\n")
            f.write(f"Estimated ARV: ${d['arv']:,.0f}\n")
            f.write(f"Rehab Cost (Light): ${d['rehab_light']:,.0f}\n")
            f.write(f"Rehab Cost (Heavy): ${d['rehab_heavy']:,.0f}\n")
            f.write(f"Holding Costs (3mo): ${d['holding_costs']:,.0f}\n")
            f.write(f"Gross Profit (Light): ${d['gross_profit_light']:,.0f}\n")
            f.write(f"Gross Profit (Heavy): ${d['gross_profit_heavy']:,.0f}\n")
            f.write(f"Meets Minimum Revenue Threshold (${d['min_profit_threshold']:,.0f})? "
                    f"Light: {'Yes' if d['meets_threshold_light'] else 'No'}, "
                    f"Heavy: {'Yes' if d['meets_threshold_heavy'] else 'No'}\n")
            f.write(f"Recommended Max Offer: ${d['recommended_max_offer']:,.0f}\n")
            f.write(f"Risks: {'; '.join(lead.get('risks', ['None']))}\n")
            f.write(f"Link: {lead['url']}\n")
            f.write("-" * 40 + "\n\n")
    print(f"\nReport saved to: {filename}")

# ================================
# MAIN
# ================================

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(HERE, "comp_benchmarks_cache.json")
SEEN_PATH = os.path.join(HERE, "seen_listings.json")
FEED_PATH = os.path.join(HERE, "leads_for_sheets.json")


def persist_full_scan_state(now_iso: str):
    """
    A full scan already does everything hourly_check.py's incremental run
    does (rebuild comps, search, enrich, analyze) - so it should leave the
    same state behind, otherwise the next hourly run has no cache/seen data
    and re-does all of it from scratch. Writes all three files hourly_check
    also maintains: comp_benchmarks_cache.json, seen_listings.json, and the
    Sheets feed (leads_for_sheets.json) - using every qualifying lead this
    scan found (LAST_ANALYZED), not just the top 10 shown in the report.
    """
    json.dump({"last_built": now_iso, "benchmarks": ARV_BENCHMARKS}, open(CACHE_PATH, "w"), indent=2)

    seen = set()
    if os.path.exists(SEEN_PATH):
        seen = set(json.load(open(SEEN_PATH)))
    seen |= set(LAST_ALL_URLS)
    json.dump(sorted(seen), open(SEEN_PATH, "w"), indent=2)

    feed = {"generated_at": now_iso, "leads": []}
    if os.path.exists(FEED_PATH):
        feed = json.load(open(FEED_PATH))
    existing_urls = {row["url"] for row in feed["leads"]}
    for d in LAST_ANALYZED:
        if d["url"] in existing_urls or not d["deal"]["meets_threshold_light"]:
            continue
        deal = d["deal"]
        feed["leads"].append({
            "score": d["score"], "recommendation": d["recommendation"],
            "address": d["address"], "city": d["city"], "zip": d["zip"],
            "beds": d["beds"], "baths": d["baths"], "sqft": d["sqft"],
            "lot_sqft": d.get("lot_sqft", 0), "year_built": d.get("year_built", ""),
            "price": d["price"], "arv": deal["arv"],
            "rehab_light": deal["rehab_light"], "rehab_heavy": deal["rehab_heavy"],
            "holding_costs": deal["holding_costs"],
            "total_cost_light": deal["total_cost_light"], "total_cost_heavy": deal["total_cost_heavy"],
            "gross_profit_light": deal["gross_profit_light"], "gross_profit_heavy": deal["gross_profit_heavy"],
            "min_profit_threshold": deal["min_profit_threshold"],
            "meets_threshold_heavy": deal["meets_threshold_heavy"],
            "recommended_max_offer": deal["recommended_max_offer"],
            "risks": "; ".join(d.get("risks", [])) or "None",
            "url": d["url"],
        })
    feed["leads"].sort(key=lambda r: (r["score"], r["gross_profit_heavy"]), reverse=True)
    feed["generated_at"] = now_iso
    json.dump(feed, open(FEED_PATH, "w"), indent=2)
    n_zips = len([k for k in ARV_BENCHMARKS if k != "__fallback__"])
    print(f"Persisted state: {n_zips} zip benchmarks, {len(seen)} seen listings, "
          f"{len(feed['leads'])} leads in Sheets feed.")


def main():
    leads = run_redfin_scout()
    print_report(leads)
    save_report(leads)
    now_iso = datetime.now().astimezone().isoformat()
    persist_full_scan_state(now_iso)
    print("\nDone. Run again for fresh deals.")


if __name__ == "__main__":
    main()
