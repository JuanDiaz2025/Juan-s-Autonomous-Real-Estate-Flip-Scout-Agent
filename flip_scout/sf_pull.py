#!/usr/bin/env python3
"""
SF raw pull (Bryan, 2026-08-01): "remove comping, just pull the data,
something we can fix, do not pull renovated property."

- Scans ALL active listings in the 8 SF buy-box zips (ignores seen_listings -
  full re-pull, not a diff).
- NO comping / ARV / profit gate. No age / $psf / size pre-filter.
- Excludes ONLY the standing hard rules: already-renovated, multi-unit,
  vacant land, fire-damaged. Everything else is included raw.
- Does not touch seen_listings.json or the feed.
"""
import json, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, "flip_scout")
import flip_scout_redfin as fsr

OUT = sys.argv[1] if len(sys.argv) > 1 else "flip_scout/sf_fixables_for_sheets.json"

SF_ZIPS = [z for z in fsr.CONFIG["target_zips"] if z.startswith("941")]
print(f"SF zips: {SF_ZIPS}")

# feed URLs: skip anything already on Bryan's list
feed = json.load(open("flip_scout/leads_for_sheets.json"))
feed_urls = {l.get("url") for l in feed.get("leads", [])}

listings, seen_urls = [], set()
for z in SF_ZIPS:
    found = fsr.search_redfin(z)
    n = 0
    for l in found:
        if l["url"] not in seen_urls:
            seen_urls.add(l["url"])
            listings.append(l)
            n += 1
    print(f"  {z}: {len(found)} active, {n} unique")
    time.sleep(0.3)

already = len([l for l in listings if l["url"] in feed_urls])
listings = [l for l in listings if l["url"] not in feed_urls]
print(f"{len(listings)} active SF listings to pull ({already} already on the list, skipped)")

print("Fetching detail pages (needed only to detect renovated/multi-unit/land/fire)...")
with ThreadPoolExecutor(max_workers=6) as ex:
    futs = [ex.submit(fsr.enrich_detail, l) for l in listings]
    for i, f in enumerate(as_completed(futs)):
        f.result()
        if (i + 1) % 25 == 0:
            print(f"  {i+1}/{len(listings)}")

kept, excl = [], {"already_renovated": 0, "multi_unit": 0, "vacant_land": 0,
                  "fire_damaged": 0}
unverified = 0
for l in listings:
    if l.get("is_already_renovated"): excl["already_renovated"] += 1; continue
    if l.get("is_multi_unit"):        excl["multi_unit"] += 1; continue
    if l.get("is_vacant_land"):       excl["vacant_land"] += 1; continue
    if l.get("is_fire_damaged"):      excl["fire_damaged"] += 1; continue
    if l.get("is_data_incomplete"):
        # keep it - Bryan wants breadth - but flag that the description never
        # loaded, so the renovated check could NOT be applied to this one
        l["_condition_unverified"] = True
        unverified += 1
    kept.append(l)

kept.sort(key=lambda x: (x.get("zip", ""), x.get("price") or 0))
rows = [{
    "address": l.get("address"), "zip": l.get("zip"),
    "price": l.get("price"), "beds": l.get("beds"), "baths": l.get("baths"),
    "sqft": l.get("sqft"), "year_built": l.get("year_built"),
    "lot_sqft": l.get("lot_sqft"), "days_on_market": l.get("days_on_market"),
    "price_cuts": l.get("price_cuts"),
    "condition_unverified": bool(l.get("_condition_unverified")),
    "url": l.get("url"),
    "desc": (l.get("description") or "")[:200],
} for l in kept]
json.dump({"generated_at": __import__("datetime").datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
           "count": len(rows), "fixables": rows}, open(OUT, "w"), indent=2)

print(f"\nRESULT: {len(rows)} fixable-candidate SF listings kept "
      f"({unverified} of them condition-unverified) | excluded: {excl}")
for r in rows:
    p = f"${r['price']:,}" if r["price"] else "?"
    flag = " [cond?]" if r["condition_unverified"] else ""
    print(f"  {r['zip']}  {p:>12}  {r['beds']}/{r['baths']}  {r['sqft']}sqft  "
          f"{r['year_built']}  DOM={r['days_on_market']}  {r['address']}{flag}")
print(f"\nWrote {OUT}")
