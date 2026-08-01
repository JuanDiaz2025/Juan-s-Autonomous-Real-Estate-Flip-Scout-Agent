#!/usr/bin/env python3
"""
Daily KPI rollup for the Flip Scout pipeline - answers "how many are we
generating vs. removing, and why" without manually tallying hourly_check.py
output by hand.

Reads the append-only flip_scout/kpi_log.json (written by kpi.py on every
hourly_check.py / flip_scout_redfin.py run, plus every manual false-positive
correction) and groups it by UTC calendar day.

Run with: python3 flip_scout/kpi_report.py
Optional: python3 flip_scout/kpi_report.py --days 7   (limit to last N days)
"""

import argparse
import json
import os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
KPI_LOG_PATH = os.path.join(HERE, "kpi_log.json")

EXCLUSION_REASONS = [
    "multi_unit", "already_renovated", "vacant_land", "tenant_occupied",
    "data_incomplete", "stale_dom", "below_profit_threshold",
]


def load_log():
    if not os.path.exists(KPI_LOG_PATH):
        return []
    return json.load(open(KPI_LOG_PATH))


def day_of(iso_timestamp):
    return iso_timestamp.split("T")[0]


def build_daily_summary(log):
    days = defaultdict(lambda: {
        "runs": 0, "listings_checked": 0, "qualified": 0, "excluded_total": 0,
        "excluded_by_reason": defaultdict(int), "manual_removals": 0,
        "manual_removal_details": [],
    })

    for entry in log:
        d = days[day_of(entry["timestamp"])]
        if entry.get("kind", "run") == "run":
            d["runs"] += 1
            d["listings_checked"] += entry.get("new_listings_checked", 0)
            d["qualified"] += entry.get("qualified", 0)
            d["excluded_total"] += entry.get("excluded_total", 0)
            for reason, count in entry.get("excluded_by_reason", {}).items():
                d["excluded_by_reason"][reason] += count
        elif entry.get("kind") == "manual_removal":
            d["manual_removals"] += 1
            d["manual_removal_details"].append(
                f"{entry.get('address', '?')} ({entry.get('reason', '?')})")

    return dict(sorted(days.items()))


def print_summary(days, limit=None):
    items = list(days.items())
    if limit:
        items = items[-limit:]

    if not items:
        print("No KPI data logged yet.")
        return

    for date, d in items:
        total_removed = d["excluded_total"] + d["manual_removals"]
        print(f"\n=== {date} ===")
        print(f"  Runs: {d['runs']}")
        print(f"  Checked: {d['listings_checked']}")
        print(f"  Generated (qualified, kept): {d['qualified']}")
        print(f"  Removed (total): {total_removed}"
              f"  = {d['excluded_total']} auto-excluded + {d['manual_removals']} manually corrected")
        if d["excluded_by_reason"]:
            reasons = ", ".join(f"{r}={c}" for r, c in sorted(d["excluded_by_reason"].items()) if c)
            print(f"    Auto-excluded by reason: {reasons}")
        if d["manual_removal_details"]:
            print(f"    Manually corrected: {'; '.join(d['manual_removal_details'])}")

    total_gen = sum(d["qualified"] for _, d in items)
    total_rem = sum(d["excluded_total"] + d["manual_removals"] for _, d in items)
    print(f"\n--- Totals across {len(items)} day(s) ---")
    print(f"  Generated: {total_gen}")
    print(f"  Removed: {total_rem}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=None, help="Limit to the last N days")
    parser.add_argument("--json", action="store_true", help="Print raw JSON instead of a table")
    args = parser.parse_args()

    daily = build_daily_summary(load_log())
    if args.json:
        print(json.dumps(daily, indent=2))
    else:
        print_summary(daily, limit=args.days)
