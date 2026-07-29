# Flip Scout Agent — Standard Operating Procedure

**Owner (operator):** Bryan — automation & daily operation
**Approver:** Juan (CEO) — signs off on buy-box and methodology changes
**Status:** Live · runs hourly · **Source of truth:** this repo (`SOP.md`)
**Last structural update:** 2026-07-29

> Read §0–§2. That's the money and the judgment. Everything from **"Operator
> Runbook"** onward is the day-to-day machine operation — **Juan does not need
> to read that half.**

---

## 0. Bottom line up front

**What it does for us.** Flip Scout automatically sources single-family
fixer-upper leads across our Bay Area buy box every hour, estimates
ARV / rehab / profit for each from real sold comps, and drops the ones that
pencil onto Bryan's Google Sheet (and a live web board). It replaces manual
Redfin trawling — the sourcing + first equity screen — so the team spends its
time on the deals that already clear a profit bar, not on finding them.

**The golden rule: this is a _screen, not an appraisal._** The "gross profit"
number is a first-pass filter to decide what's worth a human look. It is never
the decision. Equity (ARV − price) still has to absorb rehab, closing,
commissions, financing, taxes, holding, permits, surprises, and our profit
before a deal is real. **Always pull real comps and verify before any offer
(§1).**

**Profit gate — a lead only reaches the list if it clears this under the
_Light_ (cosmetic) rehab scenario:**

| Estimated ARV | Minimum gross profit to qualify |
|---|---|
| $1M and up | $100,000 |
| $500k – $1M | $70,000 |
| under $500k | $50,000 |

- **"Strong Deal"** = clears the gate even under the _Heavy_ (everything-new) rehab scenario.
- **"Marginal"** = clears it only under Light.

**Quick-reference card (screenshot this):**

> **FLIP SCOUT — 10-SECOND VERSION**
> • Auto-sources SF/Peninsula/East Bay/San Jose fixer leads, hourly.
> • Every listed lead clears a **$50k–$100k gross-profit gate** (light rehab) on size-matched sold comps.
> • It's a **SCREEN** — before any offer: real 1-mile comps, flood/liens/permits, in-person rehab scope.
> • Our reliable engine (56-deal history): **East Bay, sub-$1M, rehab under ~17% of purchase.**
> • Where we've lost: **premium markets, purchase >$1.5M, heavy rehab.** Treat those leads with extra skepticism even if the math clears.

## 1. Before making an offer on any lead (real money / legal exposure)

This is the one part with real downside. This system is a **screen, not an
appraisal** — before writing an offer, always:

1. Pull real, hand-picked comps within a genuine 1-mile radius and 6–12
   months — not just this system's zip/size-band proxy.
2. Verify flood zone and code violations manually (never checked here).
3. If the lead is flagged "Outside the scanned buy box zips" or "ARV not
   size-matched," treat the ARV as a rough placeholder, not a number to offer
   against.
4. If flagged with a long days-on-market / price-cut note, find out *why* it's
   sitting before assuming it's just underpriced.
5. Confirm the rehab scope in person — Light/Heavy are two fixed-rate
   scenarios, not a substitute for a contractor walkthrough.
6. Sanity-check against our track record: a lead that looks like our historical
   loss profile (premium market, purchase >$1.5M, heavy rehab >25–30% of
   purchase) is worth extra skepticism **even if it clears the dollar gate.**

## 2. Methodology — the numbers Juan interrogates

- **ARV** = median $/sqft of sold comps **within a similar size band to the
  subject** (±20%, widening to ±40%/±60% only if too few comps clear the
  tighter band), times subject sqft. Not a flat zip-wide median — that
  overstated ARV by mixing in comps of any size (fixed after Bryan flagged it
  as too optimistic).
- **Rehab** — always both scenarios: **Light $70/sqft** (cosmetic), **Heavy
  $140–150/sqft** (everything new), plus itemized add-ons for anything the
  listing text calls out (soft story/foundation, knob-and-tube, roof).
- **Holding costs (3 months)** — 10%/yr financing (prorated) + insurance
  ($2,000 per $1M price) + property tax (1.25%/yr, prorated) + $400 flat
  utilities. The last two are documented assumptions, not given verbatim.
- **Profit gate (dollar amount, not %)** — the table in §0. A lead only
  reaches the feed if it clears the gate under the **Light** scenario.
- **Recommendation** — "Strong Deal" clears the threshold under Heavy too;
  "Marginal" only clears it under Light.
- No ADU Potential, no "Reno Budget" label, no construction-condition risk
  flags (seismic/pre-1940 wiring) — all removed per standing instruction.

**Real deal-history context** (`DEAL_HISTORY.md`): Twin Home Buyer's actual
track record — 56 completed deals, 86% win rate — and the empirical pattern
behind it. East Bay sub-$1M flips with rehab under ~17% of purchase are the
reliable engine; every historical loss was a high-price Peninsula/premium
buy with heavy rehab (>25–30% of purchase, or purchase >$1.5M in cities like
Redwood City, Menlo Park, Foster City, San Carlos, Walnut Creek). Manual
context for sanity-checking outliers (§1) — a lead matching the loss profile
is worth flagging even if it clears the model's gate. Reference context, not
(yet) wired into the automated risk logic.

**Acquisition playbook, human-side, post-lead** (`MLS_ACQUISITION_TRAINING.md`):
the canonical training for what happens AFTER a lead clears this pipeline —
the path from a spreadsheet row to a closed, profitable purchase. Core
principle: the end result is not a full spreadsheet or a long report, it is
*a profitable acquisition that closes* — every step is judged by "does this
move us closer to closing?" Key points that bear on how this agent behaves:
  - **Report patterns, don't just delete.** When leads keep getting removed
    for the same reason (stale, outside area, already renovated, unrealistic
    price), that's a signal to improve the search criteria and flag it — not to
    silently drop rows. The agent already does this (KPI log + filter patches +
    notifications).
  - **Equity ≠ profit.** Apparent spread must still absorb rehab, closing,
    commissions, financing, taxes, insurance, holding, permits, surprises, and
    company profit. The model's "gross profit" is a screen, never the decision.
  - **The screen is step 1 of ~13.** After a lead surfaces: comp-analysis
    across AI tools → Paragon/MLS remarks (offer instructions, court-
    confirmation, probate, tenant occupancy, as-is, multiple offers) →
    ownership/liens via PropertyRadar → REI BlackBook profile → offer strategy
    (terms often matter more than price: cash, as-is, fast/flex close,
    rent-back) → credible-buyer agent contact → documented next action +
    follow-up. This agent owns step 1 (sourcing + initial equity screen);
    everything downstream is the human team's playbook.
  - **Every surfaced lead should point toward a next action**, not just sit on
    the sheet — a caution note and a "verify X before offering" is the right
    shape.

---

# OPERATOR RUNBOOK

> **Juan does not need to read past this line.** Everything below is the
> day-to-day operating manual for the automation operator — what runs when,
> the tooling, and how to fix the handful of things that recur. No factual
> content from the methodology above is repeated or changed here.

## 3. What it is (components)

- **`flip_scout_redfin.py`** — the full scan. Rebuilds ARV comps from scratch
  for every zip, searches every zip's active listings, detail-enriches a
  shortlist, scores and writes the report. Heavy (hundreds of requests) — run
  on demand, not on a schedule.
- **`hourly_check.py`** — the recurring job. Reuses cached comps (rebuilt only
  if 7+ days old), searches active listings, and only enriches/scores listings
  not already in `seen_listings.json`. This is what runs every hour.
- **`FlipScoutSheet.gs`** — Google Apps Script pasted into Bryan's spreadsheet.
  Pulls `leads_for_sheets.json` from the GitHub **raw URL on branch
  `claude/python-code-goal-nn6zec`** and appends new leads, deduped by Redfin
  link, on its own hourly trigger inside Google (and on **Flip Scout → Refresh
  Now**). The JSON feed is the *only* path into the Sheet — no direct
  cell-write access.
- **The published field-report board (Artifact)** — a human-readable HTML
  report of every qualifying lead, at a fixed URL:
  `https://claude.ai/code/artifact/5a8c2ce2-db7a-4824-8791-cb2288517c94`.
  Visual companion to the Sheet; updated (never rebuilt from scratch) each
  time a new lead qualifies. See §5b.
- **State files committed to the repo after every run**, so state survives
  across sessions: `comp_benchmarks_cache.json`, `seen_listings.json`,
  `leads_for_sheets.json`, `kpi_log.json`. `new_leads.json` is a **transient**
  hand-off file (only present when the last run produced qualifiers); it is
  regenerated/deleted each run and is safe to commit or lose.

## 3a. Buy box (current)

64 zips, up to $1.5M single-family, **no price floor** (a motivated seller can
price well under $400k — the profit gate and PRICE ANOMALY flag already catch
anything too-good-to-be-true, so a hard floor would only risk cutting off real
deals): San Francisco, full San Mateo Co. (Peninsula), Sunnyvale, Oakland
(West/North/rest), Richmond CA, Berkeley, San Leandro, San Jose. Full list:
`CONFIG["target_zips"]` in `flip_scout_redfin.py`. **Buy-box changes happen
only on explicit instruction from Juan or Bryan — never expand or shrink it
unilaterally.**

**Max days on market: 45.** Anything with a confirmed days-on-market over 45 is
excluded outright (not just flagged) — `MAX_DAYS_ON_MARKET` in
`flip_scout_redfin.py`. Listings with unverifiable DOM (no usable Sale History
table) are not excluded on this basis, since there's nothing to compare against.

**Tenant-occupied listings are excluded automatically**, same tier as
already-renovated/multi-unit/vacant-lot — `TENANT_OCCUPIED_FLAGS` in
`flip_scout_redfin.py`, checked against the listing's own description.

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

If a lead has **no** risk flags, that means none of the above triggered — not
that it's risk-free. Flood zone, code violations, and neighborhood
active-listing-count are never checked (not reliably scrapeable) and are never
fabricated as a flag either.

## 5. Hourly check — what "normal" looks like

1. `git pull`, run `hourly_check.py`.
2. **No `new_leads.json` after the run** → nothing new qualified. Commit
   `seen_listings.json` if it changed, stay silent — do not message Bryan.
3. **`new_leads.json` exists** → something qualified:
   - Sanity-check each lead (oversized-for-zip, outside-buy-box, stale
     listing) before reporting — the code already flags these in `risks`, just
     read them, don't skip the check.
   - Update the published field-report board (adds to existing leads, never
     removes) — §5b.
   - Commit + push `seen_listings.json`, `comp_benchmarks_cache.json`,
     `new_leads.json`, `leads_for_sheets.json`.
   - Message Bryan: address/city/zip, score, price, profit, Redfin link, one
     line per lead. Short — not a full report dump.

**`ZIP XXXXX: HTML route blocked - used stingray API fallback (N listings)` is
normal, not an error.** Redfin now blocks the plain HTML card route for most
zips, so the scraper automatically falls back to Redfin's internal "stingray"
GIS JSON API (`search_redfin_stingray` in `flip_scout_redfin.py`) and still
gets the listings. Seeing this for most/all zips every run is expected.

**Some outright zip fetch failures every run are also normal** (`⚠️ Error
fetching ZIP XXXXX: no usable response after retries`) — when even the fallback
returns an empty/challenge response the script retries, then skips that zip for
this run rather than guessing. That zip gets a fresh look next hour. Not a sign
anything is broken unless *every* zip fails.

**`N listing(s) had empty enrichment (likely rate-limited detail fetch) - left
unseen for retry next run` is also expected.** A listing whose detail page
couldn't be enriched is deliberately **not** marked seen, so it's retried next
hour instead of being silently dropped.

### 5b. The published field-report board (Artifact)

The board at `.../artifact/5a8c2ce2-db7a-4824-8791-cb2288517c94` is updated
**additively** — new leads are inserted, existing ones are never removed.
Because more than one agent session can hold the board, always update it from
the *live* copy, not a local memory of it:

1. `WebFetch` the artifact URL. This both shows the current state (lead list,
   the "Total qualifying leads" stat, the "All N qualifying deals" header, the
   masthead "Rev." line) **and** saves the full served HTML to a
   `tool-results/artifact-5a8c2ce2-*.html` file.
2. Build the new page from that saved file: strip the `<!doctype …>` frame
   wrapper (keep from `<title>` onward), strip the trailing `</body></html>`,
   insert the new lead card just after the ranked-list section head, and bump
   the counts (Total +1, "All N" +1; **Strong Deal** count only if the new lead
   is a Strong Deal). Append the address to the masthead "Rev." line. Write to
   the scratchpad `flip_report_published.html`.
3. Republish with the **Artifact tool, passing `url=` the same board URL** so
   the link is preserved. If it errors "hasn't viewed the latest version,"
   re-`WebFetch` and rebuild on top of that — never `force` over another
   session's changes.

Card conventions: default green left-border for a clean lead; **`var(--warn)`
(amber) left-border + a "Caveat"/"Risks" chip row** whenever the ARV is
lower-confidence or overstated (outside-buy-box citywide comps, above-median
$/sqft, oversized-home distortion). Score chip shows `N / 10 — Strong Deal` or
`— Marginal`. Match the exact markup of the surrounding cards.

### 5c. Concurrent sessions on the same branch

Several agent sessions can run against `claude/python-code-goal-nn6zec` at
once, so `git push` is frequently rejected with `(fetch first)` — a routine
race, not corruption. Resolve by what your run actually produced:

- **Empty run (bookkeeping only — seen/kpi):** your changes are self-healing
  (any listing you marked seen just gets re-checked and re-excluded next hour),
  so `git fetch` + `git reset --hard origin/<branch>` to adopt the other
  session's state is fine. Do not fight a JSON merge.
- **Real change worth keeping (a genuine new lead, or a code/filter fix):**
  `git fetch`, then `git rebase -X ours origin/<branch>` — your new lead and
  code edits apply cleanly while the self-healing data files (`seen_listings`,
  `kpi_log`) resolve to the remote copy. Because a scanner-added lead only ever
  existed locally, discarding it by adopting remote would be wrong here.
- Never `git push --force` over another session's commits.

## 6. Google Sheet — Apps Script menu

| Menu item | Use it when |
|---|---|
| **Refresh Now** | Normal operation — pulls new leads from the feed. Runs hourly on its own once enabled. Never touches existing rows. |
| **Resync Existing Leads** | A lead already in the sheet needs its numbers/risks refreshed from the current feed (e.g. after a methodology fix). Preserves "First Added." Skips rows whose URL isn't in the feed anymore. |
| **Clear All Leads** | You want a clean slate after a real methodology change (asks for confirmation first). Run Refresh Now afterward to repopulate. |
| **Remove Non-Profitable Leads** | One-time backstop for rows added before profitability filtering existed. |
| **Reject Selected Lead(s)** | Bryan has decided against a lead (garbage, tenant-occupied he doesn't want, whatever). Select the row(s), run this — deletes them AND permanently blacklists those Redfin links (stored in a hidden sheet tab) so they never reappear on a future Refresh Now, even though they're still sitting in the upstream feed. **Use this instead of plain manual row deletion** — a plain delete has no way to tell the script a row is gone, so the lead just gets silently re-added next refresh. |
| **Show KPI Tab** | Jump straight to the auto-updating "KPI" tab (see below). Also runs automatically whenever the sheet is opened, and after every Refresh/Reject/Clear/Remove action — you never need to ask for this number, it's always current. |
| **Enable/Disable Hourly Auto-Refresh** | Set up once. Idempotent — safe to click again. |

**KPI tab (automated, no manual compiling)**: a "KPI" sheet tab tracks, live:
Currently kept (rows in the sheet right now), Total ever added, Total rejected
(via Reject Selected Lead(s)), Total removed (via Remove Non-Profitable Leads),
and Last updated. These counters (small integers) persist in Script Properties
(not a cell), so they're true running totals since setup, not just what's
visible right now — they survive Clear All Leads, sheet edits, anything.

**Pipeline-side KPIs (generated vs. excluded, daily)**: every `hourly_check.py`
run (and full-scan run) appends a record to `flip_scout/kpi_log.json` — how
many new listings were checked, how many qualified (generated), and a breakdown
of why the rest were excluded (multi-unit, already-renovated, vacant-land,
tenant-occupied, stale >45 days, data-incomplete, below profit threshold).
Manual corrections (a false positive caught after the fact, like an ARV
contradicted by Redfin's own estimate) are logged separately as `manual_removal`
events, distinct from the automated pre-feed exclusions. Run
`python3 flip_scout/kpi_report.py` for a daily rollup (add `--days N` to limit
to the last N days, `--json` for raw output) — answers "how many did we
generate today" and "how many did we remove today, and why" without manually
tallying hourly-check output.

**Resolved gap:** a lead manually deleted from the sheet used to reappear on the
next refresh, since Refresh Now only knows "is this URL already a row here" — it
has no way to know a row existed and was removed. Fixed via **Reject Selected
Lead(s)** above, which blacklists the URL permanently instead of just deleting
the row. This only works going forward — anything deleted before this existed
will still need Reject run on it again if it reappears.

**Second, deeper bug (fixed):** the rejected-URL blacklist was originally stored
as one JSON blob in a single Script Property, which has a hard ~9KB size limit.
Once the list grew past roughly 100–120 rejected URLs, the write silently failed
to persist — so rejecting a large batch (confirmed: 102 leads) looked like it
worked, but they all reappeared on the next refresh anyway. Fixed by moving the
blacklist to a dedicated hidden sheet tab ("Rejected (do not edit)", one URL per
row — no comparable size limit), with a one-time automatic migration of anything
already saved under the old Script Property key. After re-pasting the updated
script, any batch of rejects — no matter how large — persists correctly.

## 6b. Photo review — mandatory before any new lead is processed (standing rule)

Per Juan's instruction (2026-07-23): every new qualified lead gets a VISUAL
photo review before it reaches the sheet feed or a notification — keyword
filters alone repeatedly missed finished homes ("updated eat-in kitchen"
slipped past 'updated kitchen'; "Hot Home" badges aren't in descriptions).

Procedure per new lead:
1. `python3 flip_scout/fetch_photos.py <redfin_url> <scratch_dir> 6` —
   downloads the subject listing's own photos (the script excludes the "similar
   homes" carousel photos, which are other properties).
2. Review each photo (homescout rubric): Keep = Yes only when the property
   shows visible distress, dated finishes, deferred maintenance, vacancy, or
   clear value-add potential. Keep = No when it looks renovated, staged-clean,
   or luxury-finished — regardless of what the profit math says. Also check the
   listing page for Redfin's "Hot Home" badge: hot + clean = automatic No
   (bid-war teaser pricing makes list-price profit fake).
3. "NO PHOTOS extractable" (exit code 2) is itself a signal — MLS-light /
   auction / off-market listing. Keep only with an explicit caution note.
4. Note: the environment's browser cannot reach Google Maps/Street View;
   Redfin's own listing photos (fetched via the data channel) are the visual
   source. A single stale low-res photo = treat like case 3.

## 6c. Manually adding a listing Bryan sends

Bryan sometimes wants a specific listing on his Sheet that the scanner didn't
surface. Since the JSON feed is the only path in:

1. Add a row to `leads_for_sheets.json` matching the `COLUMNS` schema in
   `FlipScoutSheet.gs`, with a `MANUAL ADD (Bryan)` note in `risks`.
2. For a non-flip asset (e.g. a fourplex kept as a flagged exception), leave
   ARV/rehab/profit **blank** rather than fabricating single-family numbers.
3. Add the matching card to the board (§5b), commit + push to
   `claude/python-code-goal-nn6zec`. Bryan then hits **Refresh Now**.

Per standing rules (see `CLAUDE.md`): **cosmetic renovation candidates go on
the list even when the strict profit gate is thin or negative** — surface them
as a "Renovation candidate" with the honest deal math and the price they would
need to pencil, and let Bryan decide. Keep excluding genuinely already-renovated
homes, multi-unit (unless Bryan flags an exception), vacant land, and
**fire-damaged** listings (never listed — the per-sqft rehab model can't price
fire remediation; `FIRE_DAMAGE_FLAGS` sets `is_fire_damaged` and both the hourly
check and full scan exclude it).

## 7. Troubleshooting

- **Sheet still shows old columns after a schema change** → the header row only
  gets rebuilt if it doesn't match the current schema (auto-detected) or via
  Clear All Leads. Re-paste the latest `.gs` and click Refresh Now.
- **Duplicate leads in the sheet** → shouldn't happen; dedup is by Redfin link
  both in the feed merge and in the Apps Script's existing-URL check. If you see
  what looks like a dup, check whether it's actually the same property relisted
  under a new Redfin URL (a genuine "new" listing by design) versus a real bug —
  verify by comparing the Redfin Link column, not just the address text.
- **Field report board looks stale** → the publish tool occasionally fails
  transiently; the underlying repo data is always current regardless of artifact
  state. Retry the publish; if it keeps failing, the repo
  (`leads_for_sheets.json`) is the source of truth in the meantime.
- **A lead's numbers look off** → re-derive by hand from the same repo data
  (`comp_benchmarks_cache.json` for the zip's real comps) before assuming a bug —
  most "wrong-looking" numbers turn out to be a real, if surprising, effect of
  the methodology (e.g. an oversized home against a zip's typical comp size). If
  the underlying scraped data itself is wrong (wrong price, wrong sqft, wrong
  zip), that's worth investigating and fixing at the source, not just excluding
  the one listing.

## 8. Revision history (major changes, most recent first)

- **Restructured this SOP for top-down reading (Juan-first):** bottom-line-up-
  front + profit-gate table + screenshot quick-reference card first, the
  before-you-offer checklist and the numbers-based methodology next, and all
  operator detail moved below an explicit "Operator Runbook — Juan does not need
  to read past here" divider. Added an owner/approver/status header. No factual
  content changed — same methodology, risk logic, and revision history.
- Documented the operational reality of the live pipeline: the published
  field-report **board/Artifact** and its additive update flow (§5b),
  **concurrent multi-session git handling** on the shared branch (§5c), the
  **stingray API fallback** as the normal fetch path (§5), the **manual-add**
  flow and fire-damage exclusion (§6c). Added `fully reimagined` /
  `reimagined residence` / `waterfall island` to the already-renovated filter
  after a "fully reimagined" luxury resale (3367 Holderman Dr, San Jose) slipped
  past the older keyword set.
- Added `MLS_ACQUISITION_TRAINING.md` — Twin Home Buyer's canonical playbook for
  the human acquisition process after a lead clears this pipeline (comp-analysis
  → MLS/Paragon remarks → ownership/liens → REI BlackBook → offer strategy →
  agent contact → follow-up to close). Referenced from §2. Reinforces the
  agent's existing behavior: report recurring exclusion patterns rather than
  silently deleting, treat model "profit" as a screen (equity ≠ profit), and
  attach a concrete next-action/verify note to every surfaced lead.
- Fixed a real bug behind "rejected leads keep coming back": the rejected-URL
  blacklist was stored as one JSON blob in a single Script Property (hard ~9KB
  limit), which silently failed to persist once the list grew past ~100–120 URLs
  — confirmed live when 102 rejected leads reappeared after a refresh despite
  being rejected. Moved storage to a dedicated hidden sheet tab ("Rejected (do
  not edit)", one URL per row), with an automatic one-time migration from the
  old Script Property.
- Added automated KPI tracking: a live "KPI" tab in the Google Sheet (currently
  kept / total added / total rejected, updates automatically — no need to ask
  for these numbers), plus `flip_scout/kpi_log.json` + `kpi_report.py` on the
  pipeline side for a daily generated-vs-excluded rollup (with a reason
  breakdown). Also fixed a real scraper bug caught along the way: a garbled
  $14,700 "price" for 642 Mississippi St, which had actually sold in 2014 for
  $1.23M and wasn't for sale — added `SANITY_MIN_PRICE` as a data-integrity
  floor (distinct from the deliberately-removed buy-box price floor) to catch
  this class of corruption automatically.
- Added a hard 45-day max-days-on-market exclusion and a tenant-occupied
  exclusion (`TENANT_OCCUPIED_FLAGS`), both per standing instruction. Added
  "Reject Selected Lead(s)" to the Apps Script menu so a manually-rejected lead
  is permanently blacklisted instead of just deleted (which used to silently
  reappear on the next refresh).
- Added `DEAL_HISTORY.md` — real 56-deal track record and empirical win/loss
  pattern, referenced from §2 as manual context for sanity-checking outliers.
- Removed the $400k price floor per standing instruction — a motivated seller
  can price well under that, and the profit gate/anomaly flag already screen out
  anything that doesn't pencil.
- Added Apps Script menu items for resync/clear-all to handle schema and
  methodology changes without manual sheet surgery.
- Added pagination + retry-on-transient-failure to the scraper (a zip's
  inventory or sold-comp count can exceed one page; a single empty response used
  to look identical to "no listings").
- Fixed a bug where un-enriched candidates from a full scan were permanently
  marked "seen," silently excluding anything past the top-6 cutoff before it was
  ever evaluated.
- Replaced flat zip-wide median ARV with size-matched comps (root-caused as "too
  optimistic" — a handful of large/luxury sold comps were setting the rate for
  much smaller subject properties).
- Removed construction-condition risk flags (seismic, pre-1940 wiring) per
  standing instruction; kept only non-construction risks.
- Replaced generic "DOM not verified" disclaimer with a real days-on-market /
  price-cut signal pulled from each listing's own Redfin sale history.
- Rebuilt the entire engine to the Twin Home Buyer methodology (size-matched
  ARV, Light/Heavy rehab, dollar profit gate) — replaced the original
  spread-percentage/ADU-potential model entirely.
