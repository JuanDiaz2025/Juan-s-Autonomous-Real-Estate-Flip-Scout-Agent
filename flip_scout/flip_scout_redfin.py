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

IMPORTANT CAVEAT: `ARV_PSF` below is a rough $/sqft-by-zip table, not a real
comp-based valuation. Treat every ARV/spread number here as a first-pass
screen, not an appraisal - pull real comps before making an offer.
"""

import requests
from bs4 import BeautifulSoup
import re
import json
import time
from datetime import datetime
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

# ================================
# CONFIGURATION (Juan's Buy Box)
# ================================
CONFIG = {
    "max_price": 1_500_000,
    "min_price": 400_000,
    "target_zips": ["94124", "94112", "94134", "94118", "94116", "94122", "94110",
                     "94401", "94402", "94403", "94085", "94086", "94087", "94088",
                     "94014", "94015", "94080"],
    "min_spread_percent": 0.20,
    "preferred_spread_percent": 0.25,
    "reno_cost_per_sqft": 350,
    "holding_months": 6,
    "closing_costs_percent": 0.03,
    "detail_enrich_limit": 85,  # candidates enriched per run, split evenly across zips (detail page fetch is the slow step)
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# Rough neighborhood $/sqft used to back into ARV. NOT a comp-based valuation -
# verify against real recent sold comps before trusting a spread number.
ARV_PSF = {
    '94124': 1100, '94112': 1250, '94134': 950, '94118': 1400, '94116': 1200,
    '94122': 1350, '94110': 1400, '94401': 950, '94402': 1050, '94403': 950,
    '94085': 1050, '94086': 1000, '94087': 1150, '94088': 1050,
    '94014': 850, '94015': 900, '94080': 900,
    'default': 1000
}

MULTI_UNIT_FLAGS = ['duplex', 'triplex', 'fourplex', 'multi-family', 'multifamily',
                     '2 units', '3 units', '4 units', 'two-unit', 'multi-unit',
                     'tenancy in common']

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
            # that Redfin's "house" filter still lets through.
            if '#' in address_text or '/unit-' in href.lower():
                continue
            if re.match(r'^\d+-\d+\s', address_text):
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
        listing['is_multi_unit'] = any(flag in lower_text for flag in MULTI_UNIT_FLAGS)

        if lot:
            listing['lot_sqft'] = lot
        if year:
            listing['year_built'] = year
        listing['description'] = desc
    except Exception:
        pass
    return listing

# ================================
# ANALYTICS ENGINE (Juan's scoring model)
# ================================

def calculate_arv(listing: Dict) -> float:
    """Rough ARV estimate from a per-zip $/sqft heuristic - not a comp analysis."""
    psf = ARV_PSF.get(listing.get('zip', ''), ARV_PSF['default'])
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


def calculate_spread(listing: Dict) -> Dict:
    """Full flip financials: ARV, reno, holding, closing, net spread."""
    arv = calculate_arv(listing)
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
    print("\n" + "=" * 60)
    print("JUAN'S FLIP SCOUT AGENT - REDFIN EDITION")
    print(f"{datetime.now().strftime('%B %d, %Y - %I:%M %p')}")
    print("=" * 60)
    print(f"Target: Single-Family Homes ${CONFIG['min_price']:,.0f}-${CONFIG['max_price']:,.0f}")
    print(f"Zips scanned: {len(CONFIG['target_zips'])}\n")

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
    # globally - zips assigned a higher ARV_PSF otherwise dominate a single
    # global ranking and starve every other zip of detail-page enrichment.
    for l in all_listings:
        l['_rough_spread'] = calculate_spread(l)['spread_percent']

    per_zip_quota = max(1, CONFIG['detail_enrich_limit'] // len(CONFIG['target_zips']))
    by_zip = {}
    for l in all_listings:
        by_zip.setdefault(l['zip'], []).append(l)

    shortlist = []
    for zip_code, items in by_zip.items():
        items.sort(key=lambda x: x['_rough_spread'], reverse=True)
        shortlist.extend(items[:per_zip_quota])

    print(f"Enriching top {len(shortlist)} candidates with detail-page data...")
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = [ex.submit(enrich_detail, l) for l in shortlist]
        for i, fut in enumerate(as_completed(futures)):
            fut.result()
            if (i + 1) % 10 == 0:
                print(f"  enriched {i + 1}/{len(shortlist)}")

    analyzed = []
    for l in shortlist:
        if l.get('is_multi_unit'):
            continue
        financials = calculate_spread(l)
        if financials['spread_percent'] < 0.10:
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
        print(f"Est. ARV:      ${f['arv']:,.0f}  (heuristic - verify against comps)")
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
            f.write(f"ARV (heuristic): ${fin['arv']:,.0f}\n")
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
