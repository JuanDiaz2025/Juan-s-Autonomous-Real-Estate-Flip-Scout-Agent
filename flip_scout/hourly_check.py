#!/usr/bin/env python3
"""
Lightweight recurring check for Juan's Flip Scout Agent.

Unlike flip_scout_redfin.py (a full scan: rebuild comps for every zip,
search, enrich N candidates per zip), this script is meant to run often
(hourly) without hammering Redfin:

- Reuses cached comp benchmarks (comp_benchmarks_cache.json) unless they're
  older than COMP_CACHE_MAX_AGE_DAYS - sold comps don't meaningfully change
  hour to hour, so rebuilding them every run would be wasted requests.
- Only searches active listings (cheap - one request per zip, no detail
  page fetch) and diffs against previously seen URLs (seen_listings.json).
- Only enriches + scores listings that are actually NEW since last run.

Run with: python flip_scout/hourly_check.py
Prints a summary and writes new_leads.json only if something new cleared
the filters. Updates seen_listings.json and comp_benchmarks_cache.json
in place - commit these back to the repo after each run so state persists
across sessions.
"""

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(__file__))
import flip_scout_redfin as fsr

HERE = os.path.dirname(os.path.abspath(__file__))
SEEN_PATH = os.path.join(HERE, "seen_listings.json")
CACHE_PATH = os.path.join(HERE, "comp_benchmarks_cache.json")

COMP_CACHE_MAX_AGE_DAYS = 7


def load_seen():
    if os.path.exists(SEEN_PATH):
        return set(json.load(open(SEEN_PATH)))
    return set()


def save_seen(urls):
    json.dump(sorted(urls), open(SEEN_PATH, "w"), indent=2)


def load_or_rebuild_benchmarks(now_iso, now_ts, parse_iso):
    if os.path.exists(CACHE_PATH):
        cache = json.load(open(CACHE_PATH))
        age_days = (now_ts - parse_iso(cache["last_built"])) / 86400
        if age_days < COMP_CACHE_MAX_AGE_DAYS:
            print(f"Using cached comp benchmarks ({age_days:.1f} days old, {len(cache['benchmarks'])} zips)")
            return cache["benchmarks"]
        print(f"Comp cache is {age_days:.1f} days old (> {COMP_CACHE_MAX_AGE_DAYS}) - rebuilding")
    else:
        print("No comp cache found - building fresh")

    benchmarks = fsr.build_arv_benchmarks(fsr.CONFIG["target_zips"])
    json.dump({"last_built": now_iso, "benchmarks": benchmarks}, open(CACHE_PATH, "w"), indent=2)
    return benchmarks


def main(now_iso, now_ts, parse_iso):
    """
    now_iso / now_ts / parse_iso are injected by the caller (Date.now() and
    new Date() aren't reliably available in every execution context this
    script might run under - pass real wall-clock values in explicitly).
    """
    seen = load_seen()
    print(f"{len(seen)} previously seen listings")

    fsr.ARV_BENCHMARKS = load_or_rebuild_benchmarks(now_iso, now_ts, parse_iso)

    print(f"Checking {len(fsr.CONFIG['target_zips'])} zips for active listings...")
    new_listings = []
    all_current_urls = set()
    new_seen_urls = set()
    for z in fsr.CONFIG["target_zips"]:
        found = fsr.search_redfin(z)
        for l in found:
            all_current_urls.add(l["url"])
            # a listing can appear under more than one zip's search page
            # (boundary effect) - dedupe so it's only enriched/scored once
            if l["url"] not in seen and l["url"] not in new_seen_urls:
                new_seen_urls.add(l["url"])
                new_listings.append(l)
        time.sleep(0.3)

    print(f"{len(new_listings)} new listings since last check")

    if new_listings:
        with ThreadPoolExecutor(max_workers=6) as ex:
            futures = [ex.submit(fsr.enrich_detail, l) for l in new_listings]
            for fut in as_completed(futures):
                fut.result()

    qualified = []
    for l in new_listings:
        if l.get("is_multi_unit") or l.get("is_already_renovated") or l.get("is_vacant_land"):
            continue
        financials = fsr.calculate_spread(l)
        if financials is None or financials["spread_percent"] < 0.10:
            continue
        l["financials"] = financials
        l["score"] = fsr.score_deal(l, financials)
        l["risks"] = fsr.identify_risks(l)
        l["adu_potential"] = l.get("lot_sqft", 0) >= 2500
        qualified.append(l)

    qualified.sort(key=lambda x: (x["score"], x["financials"]["spread_percent"]), reverse=True)

    # mark everything we saw this run (qualified or not) so it's never
    # re-flagged as "new" again
    save_seen(seen | all_current_urls)

    if qualified:
        json.dump(qualified, open(os.path.join(HERE, "new_leads.json"), "w"), indent=2)
        print(f"\n{len(qualified)} NEW LEADS CLEARED FILTERS:")
        for d in qualified:
            print(f"  {d['score']}/10  {d['address']}, {d['city']} {d['zip']}  "
                  f"${d['price']:,}  spread {d['financials']['spread_percent']:.1%}  {d['url']}")
    else:
        if os.path.exists(os.path.join(HERE, "new_leads.json")):
            os.remove(os.path.join(HERE, "new_leads.json"))
        print("\nNo new leads cleared the filters this run.")


if __name__ == "__main__":
    # Called directly (not from a workflow script) - real wall-clock time is fine here.
    import datetime as _dt
    _now = _dt.datetime.now(_dt.timezone.utc)
    main(_now.isoformat().replace("+00:00", "Z"), _now.timestamp(),
         lambda s: _dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())
