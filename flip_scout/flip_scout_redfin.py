#!/usr/bin/env python3
"""
Juan's Flip Scout Agent - Redfin Edition
Searches Redfin for single-family homes under $1.5M in target Bay Area zips,
scores them against Juan's buy box, and outputs ranked flip candidates.

Run with: python flip_scout_redfin.py

Notes on this version:
Redfin's markup has changed since the original scraper was written - it no
longer exposes a `window.initialState` JSON blob, and the old `HomeCard-*`
class names have been replaced by `bp-Homecard__*`. This version scrapes the
current markup directly, then enriches shortlisted candidates with data from
each listing's detail page (description, lot size, year built) to run the
same financial/scoring model as the original design.

ARV comes from REAL sold comps, not a guess. Earlier drafts of this script
used a hardcoded $/sqft-by-zip table invented without data - it turned out to
undervalue San Mateo/Sunnyvale by 40-77% and overvalue parts of San Francisco
by ~20%, which was silently steering every result toward San Francisco. This
version pulls each zip's actual homes sold in the last 6 months and uses the
75th-percentile $/sqft (a proxy for renovated/top-tier condition, since ARV
should reflect after-repair value, not the neighborhood average) as that
zip's ARV basis. It's still an approximation, not an appraisal - it doesn't
match comps by bed/bath/condition - but it's grounded in this week's actual
market instead of an assumption.
"""

import requests
from bs4 import BeautifulSoup
import re
import json
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
    "min_price": 400_000,
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
    "min_spread_percent": 0.20,
    "preferred_spread_percent": 0.25,
    "reno_cost_per_sqft": 350,
    "holding_months": 6,
    "closing_costs_percent": 0.03,
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

MULTI_UNIT_FLAGS = ['duplex', 'triplex', 'fourplex', 'multi-family', 'multifamily',
                     '2 units', '3 units', '4 units', 'two-unit', 'multi-unit',
                     'tenancy in common', 'two-home', 'two separate residences',
                     'two full residences', 'both units']

# Listing language indicating the flip has effectively already happened - no
# renovation upside left for this buy box. Excluded regardless of score/spread,
# since a big "spread" on an already-renovated house just means it's priced
# below comps (a wholesale play), not a flip opportunity.
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
# there's no existing structure to renovate, so the reno-cost-per-sqft model
# doesn't apply and this isn't the buy-fixer-sell-renovated thesis at all.
VACANT_LAND_FLAGS = [
    'planned for a', 'existing plans', 'development project', 'vacant lot',
    'build your dream home on this lot', 'proposed floor plan', 'lot for sale',
    'buildable lot',
]

# ================================
# REDFIN SCRAPER ENGINE
# ================================

def search_redfin(zip_code: str, max_price: int = CONFIG["max_price"]) -> List[Dict]:
    """Search Redfin's current markup for single-family homes in a ZIP code."""
    listings = []
    url = (f"https://www.redfin.com/zipcode/{zip_code}/filter/"
           f"property-type=house,max-price={max_price}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        cards = soup.find_all('div', {'class': re.compile(r'HomeCardContainer')})

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
    except Exception as e:
        print(f"  ⚠️ Error fetching ZIP {zip_code}: {e}")
    return listings


def enrich_detail(listing: Dict) -> Dict:
    """Pull description, lot size and year built from the listing's detail page."""
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
    except Exception:
        pass
    # If the detail page yielded nothing usable (no description, no year
    # built), there's no listing text to judge condition against at all -
    # don't let it get scored with silent default assumptions.
    listing['is_data_incomplete'] = (not listing.get('description')) and not listing.get('year_built')
    return listing


def fetch_zip_comps(zip_code: str) -> List[float]:
    """Pull actual sold single-family $/sqft for a zip over the lookback window."""
    psfs = []
    url = (f"https://www.redfin.com/zipcode/{zip_code}/filter/"
           f"property-type=house,include={CONFIG['sold_lookback']}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        cards = soup.find_all('div', {'class': re.compile(r'HomeCardContainer')})
        for card in cards:
            html = str(card)
            price_m = re.search(r'bp-Homecard__Price--value">\$([\d,]+)', html)
            sqft_m = re.search(r'LockedStat--value">([\d,]+)', html)
            if not (price_m and sqft_m):
                continue
            price = int(price_m.group(1).replace(',', ''))
            sqft = int(sqft_m.group(1).replace(',', ''))
            if price > 50000 and sqft > 200:
                psfs.append(price / sqft)
    except Exception as e:
        print(f"  ⚠️ Error fetching comps for {zip_code}: {e}")
    return psfs


def build_arv_benchmarks(zip_codes: List[str]) -> Dict[str, float]:
    """
    Build a real, comp-based $/sqft benchmark per zip from recent sold homes.
    Uses the 75th percentile as an ARV proxy (renovated/top-tier condition),
    since ARV should reflect after-repair value, not the neighborhood average.
    """
    benchmarks = {}
    all_psfs = []
    for z in zip_codes:
        psfs = fetch_zip_comps(z)
        all_psfs.extend(psfs)
        if psfs:
            psfs.sort()
            p75 = psfs[int(len(psfs) * 0.75)]
            benchmarks[z] = round(p75)
            print(f"  {z}: {len(psfs)} sold comps, p75 ${p75:,.0f}/sqft")
        else:
            print(f"  {z}: no sold comps found")
        time.sleep(0.3)

    # zips with no comps of their own fall back to the overall median across
    # every comp fetched this run, rather than a hand-picked guess
    if all_psfs:
        fallback = round(statistics.median(all_psfs))
        for z in zip_codes:
            benchmarks.setdefault(z, fallback)
    return benchmarks

# ================================
# ANALYTICS ENGINE (Juan's scoring model)
# ================================

def calculate_arv(listing: Dict) -> Optional[float]:
    """ARV from real sold-comp $/sqft (see ARV_BENCHMARKS / build_arv_benchmarks)."""
    psf = ARV_BENCHMARKS.get(listing.get('zip', ''))
    if psf is None:
        return None  # no comp benchmark available for this zip this run

    arv = psf * listing.get('sqft', 1000)

    lot = listing.get('lot_sqft', 0)
    if lot >= 3000:
        arv *= 1.08
    elif lot >= 2500:
        arv *= 1.05

    beds = listing.get('beds', 0)
    if beds >= 4:
        arv *= 1.05
    elif beds <= 2:
        arv *= 0.95

    return round(arv, -3)


def calculate_reno_budget(listing: Dict) -> float:
    """Estimate renovation costs from condition language in the listing description."""
    desc = listing.get('description', '').lower()
    sqft = listing.get('sqft', 1000)
    base_rate = CONFIG['reno_cost_per_sqft']

    if any(w in desc for w in ['gut', 'full reno', 'complete overhaul', 'total']):
        rate = base_rate * 1.2
    elif any(w in desc for w in ['fixer', 'estate', 'original', 'as-is', 'as is', 'needs work', 'tlc', 'potential']):
        rate = base_rate
    elif any(w in desc for w in ['updated', 'remodeled', 'renovated', 'move-in']):
        rate = base_rate * 0.5
    else:
        rate = base_rate * 0.7

    budget = rate * sqft
    if 'soft story' in desc or 'foundation' in desc:
        budget += 40000
    if 'knob' in desc or 'tube' in desc or 'electrical' in desc:
        budget += 20000
    if 'roof' in desc:
        budget += 15000

    budget *= 1.2  # contingency
    return round(budget, -3)


def calculate_spread(listing: Dict) -> Optional[Dict]:
    """Full flip financials: ARV, reno, holding, closing, net spread."""
    arv = calculate_arv(listing)
    if arv is None:
        return None
    reno = calculate_reno_budget(listing)
    price = listing.get('price', 0)

    holding = price * 0.10 * (CONFIG['holding_months'] / 12)
    holding += price * 0.02 * (CONFIG['holding_months'] / 12)

    closing = price * CONFIG['closing_costs_percent'] + arv * CONFIG['closing_costs_percent']

    total_cost = price + reno + holding + closing
    net_spread = arv - total_cost
    spread_pct = net_spread / total_cost if total_cost > 0 else 0

    return {
        'arv': arv,
        'reno_budget': reno,
        'holding_costs': round(holding, -3),
        'total_cost': round(total_cost, -3),
        'net_spread': round(net_spread, -3),
        'spread_percent': spread_pct,
    }


def score_deal(listing: Dict, financials: Dict) -> int:
    """Score 1-10."""
    score = 0

    if financials['spread_percent'] >= CONFIG['preferred_spread_percent']:
        score += 6
    elif financials['spread_percent'] >= CONFIG['min_spread_percent']:
        score += 4
    elif financials['spread_percent'] >= 0.15:
        score += 2

    desc = listing.get('description', '').lower()
    distress_keywords = ['fixer', 'estate', 'as-is', 'as is', 'contractor', 'original', 'tlc', 'needs work', 'potential']
    matches = sum(1 for kw in distress_keywords if kw in desc)
    if matches >= 2:
        score += 2
    elif matches >= 1:
        score += 1

    if listing.get('lot_sqft', 0) >= 2500:
        score += 1
    if listing.get('lot_sqft', 0) >= 3000:
        score += 1

    return min(10, max(1, score))


def identify_risks(listing: Dict) -> List[str]:
    risks = []
    desc = listing.get('description', '').lower()

    if 'soft story' in desc or 'foundation' in desc:
        risks.append('Seismic retrofit likely needed ($40k+)')
    yb = listing.get('year_built', 0)
    if yb and yb < 1940:
        risks.append('Pre-1940 construction - expect old wiring/plumbing')
    if listing.get('price', 0) < 500000 and 'san francisco' in listing.get('city', '').lower():
        risks.append('PRICE ANOMALY - verify title/liens')
    if listing.get('lot_sqft', 0) and listing.get('lot_sqft', 0) < 2500:
        risks.append('Small lot - limited ADU potential')
    if 'bayview' in listing.get('address', '').lower():
        risks.append('Bayview - neighborhood still transitional')

    return risks

# ================================
# MAIN AGENT
# ================================

def run_redfin_scout() -> List[Dict]:
    """Main entry point: scan Redfin, enrich, analyze, score."""
    global ARV_BENCHMARKS
    print("\n" + "=" * 60)
    print("JUAN'S FLIP SCOUT AGENT - REDFIN EDITION")
    print(f"{datetime.now().strftime('%B %d, %Y - %I:%M %p')}")
    print("=" * 60)
    print(f"Target: Single-Family Homes ${CONFIG['min_price']:,.0f}-${CONFIG['max_price']:,.0f}")
    print(f"Zips scanned: {len(CONFIG['target_zips'])}\n")

    print("Building ARV benchmarks from real sold comps (last 6 months)...")
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

    # Rough pre-score (no description yet) to prioritize which candidates are
    # worth the slower detail-page fetch. Quota this PER ZIP rather than
    # globally - otherwise zips with a higher comp-based ARV dominate a single
    # global ranking and starve every other zip of detail-page enrichment.
    for l in all_listings:
        rough = calculate_spread(l)
        l['_rough_spread'] = rough['spread_percent'] if rough else -999

    by_zip = {}
    for l in all_listings:
        by_zip.setdefault(l['zip'], []).append(l)

    shortlist = []
    for zip_code, items in by_zip.items():
        items.sort(key=lambda x: x['_rough_spread'], reverse=True)
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
        financials = calculate_spread(l)
        if financials is None or financials['spread_percent'] < 0.10:
            continue
        l['financials'] = financials
        l['score'] = score_deal(l, financials)
        l['risks'] = identify_risks(l)
        l['adu_potential'] = l.get('lot_sqft', 0) >= 2500
        analyzed.append(l)

    analyzed.sort(key=lambda x: (x['score'], x['financials']['spread_percent']), reverse=True)
    top = [d for d in analyzed if d['score'] >= 8][:10]
    if not top:
        top = analyzed[:10]

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
        f = lead['financials']
        print(f"{'=' * 60}")
        print(f"LEAD #{idx} — SCORE: {lead['score']}/10")
        print(f"{lead['address']}, {lead.get('city', '')}, CA {lead.get('zip', '')}")
        print(f"Beds/Baths/SqFt: {lead.get('beds', 0)}/{lead.get('baths', 0)}/{lead.get('sqft', 0):,}")
        print(f"List Price:    ${lead.get('price', 0):,.0f}")
        print(f"Est. ARV:      ${f['arv']:,.0f}  (from sold comps, p75 $/sqft)")
        print(f"Reno Budget:   ${f['reno_budget']:,.0f}")
        print(f"Total Cost:    ${f['total_cost']:,.0f}")
        print(f"Net Spread:    ${f['net_spread']:,.0f} ({f['spread_percent']:.1%})")
        if lead.get('risks'):
            print("Risks:")
            for risk in lead['risks']:
                print(f"  - {risk}")
        print(f"Link: {lead['url']}")
        print()


def save_report(leads: List[Dict]):
    filename = f"flip_report_{datetime.now().strftime('%Y%m%d')}.txt"
    with open(filename, 'w') as f:
        f.write(f"Juan's Flip Scout Report - {datetime.now().strftime('%B %d, %Y')}\n")
        f.write("=" * 60 + "\n\n")
        if not leads:
            f.write("No deals found today.\n")
            return
        for idx, lead in enumerate(leads, 1):
            fin = lead['financials']
            f.write(f"LEAD #{idx} - Score: {lead['score']}/10\n")
            f.write(f"Address: {lead['address']}, {lead.get('city', '')}, CA {lead.get('zip', '')}\n")
            f.write(f"Price: ${lead.get('price', 0):,.0f}\n")
            f.write(f"ARV (comp-based): ${fin['arv']:,.0f}\n")
            f.write(f"Net Spread: ${fin['net_spread']:,.0f} ({fin['spread_percent']:.1%})\n")
            f.write(f"Risks: {', '.join(lead.get('risks', ['None']))}\n")
            f.write(f"Link: {lead['url']}\n")
            f.write("-" * 40 + "\n\n")
    print(f"\nReport saved to: {filename}")

# ================================
# MAIN
# ================================

def main():
    leads = run_redfin_scout()
    print_report(leads)
    save_report(leads)
    print("\nDone. Run again for fresh deals.")


if __name__ == "__main__":
    main()
