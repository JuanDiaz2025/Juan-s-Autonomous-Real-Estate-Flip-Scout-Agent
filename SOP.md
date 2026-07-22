# Flip Scout Agent — Standard Operating Procedure

Twin Home Buyer's automated Redfin flip-lead pipeline: scans the buy box hourly,
runs the flip-analyst methodology on every listing, and appends qualifying
leads to Bryan's Google Sheet. This document is the operating manual — what
runs when, what each number means, what to check before trusting a lead, and
how to fix the handful of things that recur.

## 1. What it is

- **`flip_scout_redfin.py`** — the full scan. Rebuilds ARV comps from scratch
  for every zip, searches every zip's active listings, detail-enriches a
  shortlist, scores and writes the report. Heavy (hundreds of requests) — run
  on demand, not on a schedule.
- **`hourly_check.py`** — the recurring job. Reuses cached comps (rebuilt only
  if 7+ days old), searches active listings, and only enriches/scores
  listings not already in `seen_listings.json`. This is what runs every hour.
- **`FlipScoutSheet.gs`** — Google Apps Script pasted into Bryan's spreadsheet.
  Pulls `leads_for_sheets.json` from the repo and appends new leads,
  deduped by Redfin link, on its own hourly trigger inside Google.
- **State files committed to the repo after every run**, so state survives
  across sessions: `comp_benchmarks_cache.json`, `seen_listings.json`,
  `leads_for_sheets.json`.

## 2. Buy box (current)

64 zips, up to $1.5M single-family, **no price floor** (a motivated seller
can price well under $400k — the profit gate and PRICE ANOMALY flag already
catch anything too-good-to-be-true, so a hard floor would only risk cutting
off real deals): San Francisco, full San Mateo Co. (Peninsula), Sunnyvale,
Oakland (West/North/rest), Richmond CA, Berkeley, San Leandro, San Jose.
Full list: `CONFIG["target_zips"]` in `flip_scout_redfin.py`. Changes to the
buy box only happen on Bryan's explicit instruction — never expand or shrink
it unilaterally.

**Max days on market: 45.** Anything with a confirmed days-on-market over 45
is excluded outright (not just flagged) — `MAX_DAYS_ON_MARKET` in
`flip_scout_redfin.py`. Listings with unverifiable DOM (no usable Sale
History table) are not excluded on this basis, since there's nothing to
compare against.

**Tenant-occupied listings are excluded automatically**, same tier as
already-renovated/multi-unit/vacant-lot — `TENANT_OCCUPIED_FLAGS` in
`flip_scout_redfin.py`, checked against the listing's own description.

## 3. Methodology (Twin Home Buyer standard)

- **ARV** = median $/sqft of sold comps **within a similar size band to the
  subject** (±20%, widening to ±40%/±60% only if too few comps clear the
  tighter band), times subject sqft. Not a flat zip-wide median — that
  overstated ARV by mixing in comps of any size (fixed after Bryan flagged
  it as too optimistic).
- **Rehab** — always both scenarios: Light $70/sqft (cosmetic), Heavy
  $140–150/sqft (everything new), plus itemized add-ons for anything the
  listing text calls out (soft story/foundation, knob-and-tube, roof).
- **Holding costs (3 months)** — 10%/yr financing (prorated) + insurance
  ($2,000/$1M price) + property tax (1.25%/yr, prorated) + $400 flat
  utilities. The last two are documented assumptions, not given verbatim.
- **Profit gate (dollar amount, not %)** — $1M+ ARV needs $100k min,
  $500k–$1M needs $70k min, under $500k needs $50k min. A lead only reaches
  the feed if it clears this under the **Light** scenario.
- **Recommendation**: "Strong Deal" clears the threshold under Heavy too;
  "Marginal" only clears it under Light.
- No ADU Potential, no "Reno Budget" label, no construction-condition risk
  flags (seismic/pre-1940 wiring) — all removed per standing instruction.

**Real deal-history context**: `DEAL_HISTORY.md` documents Twin Home Buyer's
actual track record (56 completed deals, 86% win rate) and the empirical
pattern behind it — East Bay sub-$1M flips with rehab under ~17% of purchase
are the reliable engine; every historical loss was a high-price
Peninsula/premium-market buy with heavy rehab (>25-30% of purchase, or
purchase >$1.5M in cities like Redwood City, Menlo Park, Foster City, San
Carlos, Walnut Creek). Use it as manual context when sanity-checking outlier
leads per §5/§7 — a lead matching the historical loss profile is worth
flagging even if it clears the model's dollar profit gate. This is
reference context, not (yet) wired into the automated risk-flag logic.

## 4. Reading the Risk column

Only real, verified signals — nothing is fabricated:

| Risk text | Meaning |
|---|---|
| `On market N days[, M price cut(s)]...` | Pulled from Redfin's own Sale History table. Flagged at 60+ days or 2+ cuts. A long stale listing (or repeated cuts) may signal a soft submarket or an overpriced/undesirable property. |
| `Outside the scanned buy box zips...` | The zip isn't one of the 64 (a neighboring-zip search catch). ARV used a citywide comp pool, not that zip's own sold homes — verify comps manually. |
| `ARV not size-matched...` | Even the widest size band didn't have 3+ comps, so ARV fell back to the zip's full comp set. Lower confidence than a size-matched ARV. |
| `Small lot` | Lot < 2,500 sqft. |
| `PRICE ANOMALY...` | SF listing under $500k — verify title/liens before assuming it's just a good deal. |
| `Bayview - neighborhood still transitional` | Address-based neighborhood note. |

If a lead has **no** risk flags, that means none of the above triggered —
not that it's risk-free. Flood zone, code violations, and neighborhood
active-listing-count are never checked (not reliably scrapeable) and are
never fabricated as a flag either.

## 5. Hourly check — what "normal" looks like

1. `git pull`, run `hourly_check.py`.
2. **No `new_leads.json` after the run** → nothing new qualified. Commit
   `seen_listings.json` if it changed, stay silent — do not message Bryan.
3. **`new_leads.json` exists** → something qualified:
   - Sanity-check each lead (oversized-for-zip, outside-buy-box, stale
     listing) before reporting — the code already flags these in `risks`,
     just read them, don't skip the check.
   - Update the published field-report artifact (adds to existing leads,
     never removes).
   - Commit + push `seen_listings.json`, `comp_benchmarks_cache.json`,
     `new_leads.json`, `leads_for_sheets.json`.
   - Message Bryan: address/city/zip, score, price, profit, Redfin link,
     one line per lead. Short — not a full report dump.

**Some zip fetch failures every run are normal** (`⚠️ Error fetching ZIP
XXXXX: no usable response after retries`) — Redfin occasionally returns an
empty/challenge response; the script retries automatically and just skips
that zip for this run rather than guessing. That zip gets a fresh look next
hour. This is not a sign anything is broken unless *every* zip fails.

## 6. Google Sheet — Apps Script menu

| Menu item | Use it when |
|---|---|
| **Refresh Now** | Normal operation — pulls new leads from the feed. Runs hourly on its own once enabled. Never touches existing rows. |
| **Resync Existing Leads** | A lead already in the sheet needs its numbers/risks refreshed from the current feed (e.g. after a methodology fix). Preserves "First Added." Skips rows whose URL isn't in the feed anymore. |
| **Clear All Leads** | You want a clean slate after a real methodology change (asks for confirmation first). Run Refresh Now afterward to repopulate. |
| **Remove Non-Profitable Leads** | One-time backstop for rows added before profitability filtering existed. |
| **Reject Selected Lead(s)** | Bryan has decided against a lead (garbage, tenant-occupied he doesn't want, whatever). Select the row(s), run this — deletes them AND permanently blacklists those Redfin links (stored in Script Properties) so they never reappear on a future Refresh Now, even though they're still sitting in the upstream feed. **Use this instead of plain manual row deletion** — a plain delete has no way to tell the script a row is gone, so the lead just gets silently re-added next refresh. |
| **Show KPI Tab** | Jump straight to the auto-updating "KPI" tab (see below). Also runs automatically whenever the sheet is opened, and after every Refresh/Reject/Clear/Remove action — you never need to ask for this number, it's always current. |
| **Enable/Disable Hourly Auto-Refresh** | Set up once. Idempotent — safe to click again. |

**KPI tab (automated, no manual compiling)**: a "KPI" sheet tab tracks, live:
Currently kept (rows in the sheet right now), Total ever added, Total
rejected (via Reject Selected Lead(s)), Total removed (via Remove
Non-Profitable Leads), and Last updated. These counters (small integers)
persist in Script Properties (not a cell), so they're true running totals since setup, not
just what's visible right now — they survive Clear All Leads, sheet edits,
anything.

**Pipeline-side KPIs (generated vs. excluded, daily)**: every `hourly_check.py`
run (and full-scan run) appends a record to `flip_scout/kpi_log.json` —
how many new listings were checked, how many qualified (generated), and a
breakdown of why the rest were excluded (multi-unit, already-renovated,
vacant-land, tenant-occupied, stale >45 days, data-incomplete, below profit
threshold). Manual corrections (a false positive caught after the fact, like
an ARV contradicted by Redfin's own estimate) are logged separately as
`manual_removal` events, distinct from the automated pre-feed exclusions.
Run `python3 flip_scout/kpi_report.py` for a daily rollup (add `--days N` to
limit to the last N days, `--json` for raw output) — answers "how many did
we generate today" and "how many did we remove today, and why" without
manually tallying hourly-check output by hand.

**Resolved gap:** a lead manually deleted from the sheet used to reappear on
the next refresh, since Refresh Now only knows "is this URL already a row
here" — it has no way to know a row existed and was removed. Fixed via
**Reject Selected Lead(s)** above, which blacklists the URL permanently
instead of just deleting the row. This only works going forward — anything
deleted before this existed will still need Reject run on it again if it
reappears.

**Second, deeper bug (fixed):** the rejected-URL blacklist was originally
stored as one JSON blob in a single Script Property, which has a hard ~9KB
size limit. Once the list grew past roughly 100-120 rejected URLs, the
write silently failed to persist — so rejecting a large batch (confirmed:
102 leads) looked like it worked, but they all reappeared on the next
refresh anyway. Fixed by moving the blacklist to a dedicated hidden sheet
tab ("Rejected (do not edit)", one URL per row — no comparable size
limit), with a one-time automatic migration of anything already saved
under the old Script Property key. After re-pasting the updated script,
any batch of rejects — no matter how large — persists correctly.

## 7. Before actually making an offer on any lead

This system is a **screen, not an appraisal**. Always, before writing an
offer:

1. Pull real, hand-picked comps within a genuine 1-mile radius and 6-12
   months — not just this system's zip/size-band proxy.
2. Verify flood zone and code violations manually (never checked here).
3. If flagged "Outside the scanned buy box zips" or "ARV not size-matched,"
   treat the ARV as a rough placeholder, not a number to offer against.
4. If flagged with a long days-on-market/price-cut note, find out *why* it's
   sitting before assuming it's just underpriced.
5. Confirm the rehab scope in person — Light/Heavy are two fixed-rate
   scenarios, not a substitute for a contractor walkthrough.

## 8. Troubleshooting

- **Sheet still shows old columns after a schema change** → the header row
  only gets rebuilt if it doesn't match the current schema (auto-detected)
  or via Clear All Leads. Re-paste the latest `.gs` and click Refresh Now.
- **Duplicate leads in the sheet** → shouldn't happen; dedup is by Redfin
  link both in the feed merge and in the Apps Script's existing-URL check.
  If you see what looks like a dup, check whether it's actually the same
  property relisted under a new Redfin URL (a genuine "new" listing by
  design) versus a real bug — verify by comparing the Redfin Link column,
  not just the address text.
- **Field report artifact looks stale** → the publish tool occasionally
  fails transiently; the underlying repo data is always current regardless
  of artifact state. Retry the publish; if it keeps failing, the repo
  (`leads_for_sheets.json`) is the source of truth in the meantime.
- **A lead's numbers look off** → re-derive by hand from the same repo data
  (`comp_benchmarks_cache.json` for the zip's real comps) before assuming a
  bug — most "wrong-looking" numbers turn out to be a real, if surprising,
  effect of the methodology (e.g. an oversized home against a zip's typical
  comp size). If the underlying scraped data itself is wrong (wrong price,
  wrong sqft, wrong zip), that's worth investigating and fixing at the
  source, not just excluding the one listing.

## 9. Revision history (major changes, most recent first)

- Fixed a real bug behind "rejected leads keep coming back": the
  rejected-URL blacklist was stored as one JSON blob in a single Script
  Property (hard ~9KB limit), which silently failed to persist once the
  list grew past ~100-120 URLs — confirmed live when 102 rejected leads
  reappeared after a refresh despite being rejected. Moved storage to a
  dedicated hidden sheet tab ("Rejected (do not edit)", one URL per row),
  with an automatic one-time migration from the old Script Property.
- Added automated KPI tracking: a live "KPI" tab in the Google Sheet
  (currently kept / total added / total rejected, updates automatically -
  no need to ask for these numbers), plus `flip_scout/kpi_log.json` +
  `kpi_report.py` on the pipeline side for a daily generated-vs-excluded
  rollup (with a reason breakdown). Also fixed a real scraper bug caught
  along the way: a garbled $14,700 "price" for 642 Mississippi St, which
  had actually sold in 2014 for $1.23M and wasn't for sale - added
  `SANITY_MIN_PRICE` as a data-integrity floor (distinct from the
  deliberately-removed buy-box price floor) to catch this class of
  corruption automatically.
- Added a hard 45-day max-days-on-market exclusion and a tenant-occupied
  exclusion (`TENANT_OCCUPIED_FLAGS`), both per standing instruction. Added
  "Reject Selected Lead(s)" to the Apps Script menu so a manually-rejected
  lead is permanently blacklisted instead of just deleted (which used to
  silently reappear on the next refresh).
- Added `DEAL_HISTORY.md` — real 56-deal track record and empirical
  win/loss pattern, referenced from §3 as manual context for sanity-checking
  outlier leads.
- Removed the $400k price floor per standing instruction — a motivated
  seller can price well under that, and the profit gate/anomaly flag already
  screen out anything that doesn't pencil.
- Added Apps Script menu items for resync/clear-all to handle schema and
  methodology changes without manual sheet surgery.
- Added pagination + retry-on-transient-failure to the scraper (a zip's
  inventory or sold-comp count can exceed one page; a single empty response
  used to look identical to "no listings").
- Fixed a bug where un-enriched candidates from a full scan were
  permanently marked "seen," silently excluding anything past the top-6
  cutoff before it was ever evaluated.
- Replaced flat zip-wide median ARV with size-matched comps (root-caused as
  "too optimistic" — a handful of large/luxury sold comps were setting the
  rate for much smaller subject properties).
- Removed construction-condition risk flags (seismic, pre-1940 wiring) per
  standing instruction; kept only non-construction risks.
- Replaced generic "DOM not verified" disclaimer with a real days-on-market
  /price-cut signal pulled from each listing's own Redfin sale history.
- Rebuilt the entire engine to the Twin Home Buyer methodology (size-matched
  ARV, Light/Heavy rehab, dollar profit gate) — replaced the original
  spread-percentage/ADU-potential model entirely.
