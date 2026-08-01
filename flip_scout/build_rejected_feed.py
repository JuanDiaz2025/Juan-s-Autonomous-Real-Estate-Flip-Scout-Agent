#!/usr/bin/env python3
"""
Build the rejected-leads feed for the Google Sheet.

Reads the append-only flip_scout/kpi_log.json and emits
flip_scout/rejected_for_sheets.json - the itemized list of every lead that
was manually removed after review (address, category, reason, date, Redfin
link). The Sheet's "Show Rejected Leads" menu item (FlipScoutSheet.gs)
fetches this feed and renders it into a "Rejected Leads" tab, exactly the
way Refresh Now consumes leads_for_sheets.json.

Why a separate feed instead of reading kpi_log.json directly from the Sheet:
kpi_log.json also holds per-run aggregate counts (no addresses), and the
category derivation below is non-trivial - keeping it in Python means the
Sheet just renders a clean, already-categorized list rather than reimplementing
the keyword bucketing in Apps Script.

NOTE: this feed covers MANUAL removals only. Auto-excluded listings
(multi-unit, already-renovated, data-incomplete, etc.) are recorded in
kpi_log.json as per-run reason COUNTS only - the scanner does not retain
their addresses - so they can't be itemized here.

Run with: python3 flip_scout/build_rejected_feed.py
"""

import json
import os
from collections import Counter
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
KPI_LOG_PATH = os.path.join(HERE, "kpi_log.json")
OUT_PATH = os.path.join(HERE, "rejected_for_sheets.json")


def categorize(reason):
    """Bucket a free-text removal reason into a stable category label.

    Kept in sync with the Rejected Leads Matrix artifact. Order matters -
    the first matching rule wins - so the more specific reasons (fire,
    stale-DOM, unverifiable photos) are tested before the broader ones.
    """
    r = (reason or "").lower()
    if "fire" in r:
        return "Fire damage"
    if "stale" in r or "days on market" in r:
        return "Stale on market (DOM)"
    unverifiable = [
        "rendering", "artist", "withheld", "model plan", "new-construction",
        "new construction", "no photos", "cannot verify", "cannot photo-verify",
        "not extractable", "unverifiable", "does not depict",
    ]
    if any(w in r for w in unverifiable):
        return "Photo audit - unverifiable"
    if "photo" in r:
        return "Photo audit - not a fixer"
    attached = [
        "attached", "townhome", "townhouse", "pud", "row house", "end-unit",
        "end unit", "walk-in unit", "shared-wall",
    ]
    if any(w in r for w in attached):
        return "Attached product (townhome/PUD)"
    if any(w in r for w in ["renovat", "remodel", "upgrad", "updated", "turnkey", "flipped"]):
        return "Already renovated"
    if any(w in r for w in ["fourplex", "triplex", "duplex", "multi-unit", "multifamily",
                            "multi-family", "2-unit", "3-unit", "4-unit"]):
        return "Multi-unit"
    if any(w in r for w in ["vacant land", "entitle", "teardown", "tear-down", "lot only", "raw land"]):
        return "Land / teardown"
    if any(w in r for w in ["arv", "fake deal", "comp", "overstat", "inflat", "estimate"]):
        return "ARV / comp mismatch"
    if any(w in r for w in ["pars", "garbled", "scraper", "sqft error", "duplicate url", "bug"]):
        return "Scraper / data bug"
    if any(w in r for w in ["profit", "spread", "thin", "negative", "pencil", "margin"]):
        return "Profit too thin"
    if "condo" in r or "hoa" in r:
        return "Condo / HOA"
    return "Other / judgment"


def build():
    if not os.path.exists(KPI_LOG_PATH):
        raise SystemExit("kpi_log.json not found - nothing to build.")

    log = json.load(open(KPI_LOG_PATH))
    removals = [e for e in log if e.get("kind") == "manual_removal"]
    removals.sort(key=lambda e: e.get("timestamp", ""))

    rejected = []
    for e in removals:
        reason = e.get("reason", "")
        rejected.append({
            "date": (e.get("timestamp", "") or "")[:10],
            "address": e.get("address", "") or "(address not recorded)",
            "category": categorize(reason),
            "reason": reason,
            "url": e.get("url", "") or "",
        })

    category_counts = dict(Counter(r["category"] for r in rejected).most_common())

    feed = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count": len(rejected),
        "note": "Manually removed leads only. Auto-excluded listings are "
                "recorded in kpi_log.json as per-run counts without addresses "
                "and cannot be itemized here.",
        "category_counts": category_counts,
        "rejected": rejected,
    }

    json.dump(feed, open(OUT_PATH, "w"), indent=2)
    print("Wrote %s (%d rejected leads)" % (OUT_PATH, len(rejected)))
    for cat, n in category_counts.items():
        print("  %3d  %s" % (n, cat))


if __name__ == "__main__":
    build()
