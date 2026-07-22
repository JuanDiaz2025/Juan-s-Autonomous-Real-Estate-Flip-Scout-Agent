"""
Shared KPI logging for the Flip Scout pipeline.

kpi_log.json is an append-only list of events - never rewritten in place -
so a daily/weekly rollup (kpi_report.py) can always be recomputed from the
raw history rather than trusting a running total that could silently drift.
Committed to the repo alongside the other state files after every run.

Two event kinds:
  - "run": one per hourly_check.py (or flip_scout_redfin.py) execution -
    how many new listings were checked, how many qualified, and a breakdown
    of why the rest were excluded.
  - "manual_removal": logged whenever a lead that already reached the feed
    turns out, on manual review, to be a false positive (e.g. the ARV was
    contradicted by Redfin's own estimate, or a renovated-language keyword
    gap let something through) and gets stripped back out. This is a
    distinct removal reason from the automated pre-feed exclusions above -
    it's a correction, not a filter - so it's tracked separately rather than
    folded into "excluded_by_reason".
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
KPI_LOG_PATH = os.path.join(HERE, "kpi_log.json")


def _load():
    if os.path.exists(KPI_LOG_PATH):
        return json.load(open(KPI_LOG_PATH))
    return []


def _save(log):
    json.dump(log, open(KPI_LOG_PATH, "w"), indent=2)


def log_run(now_iso, stats):
    log = _load()
    log.append({"kind": "run", "timestamp": now_iso, **stats})
    _save(log)


def log_manual_removal(now_iso, url, address, reason):
    log = _load()
    log.append({
        "kind": "manual_removal", "timestamp": now_iso,
        "url": url, "address": address, "reason": reason,
    })
    _save(log)
