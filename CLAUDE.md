# Flip Scout Agent — working notes & standing preferences

## Lead selection preference — cosmetic renovation candidates (Bryan, 2026-07-26)

Bryan wants **cosmetic renovation candidates on his list even when the strict
fix-and-flip profit gate is thin or negative.** The point of the list, for him,
is "something we can renovate" — not only deals that clear the dollar profit
threshold.

When reviewing a listing (a manual add, or a lead where photos are available):

- If the **photos** show a genuine cosmetic fixer — dated but structurally
  sound (old kitchens/baths, old carpet/flooring, dated finishes) and **NOT
  already renovated** — **add it to his list** as a **"Renovation candidate"**,
  with the honest deal math attached.
- Do **not** silently drop such a home just because the size-matched ARV leaves
  a thin or negative spread at ask. Surface it **with the caveat** (state the
  real profit/loss and the purchase price it would need to pencil) and let Bryan
  decide.
- Keep excluding genuinely **already-renovated** homes, **multi-unit/fourplex**
  (unless Bryan explicitly asks — e.g. 445 Lawton St, added as a flagged
  multifamily exception), and **vacant land / entitlement** listings.

## Exclude fire-damaged listings (Bryan, 2026-07-27)

**Never put a fire-damaged home on the list.** Fire remediation (structural,
smoke/soot, possible rebuild) isn't priced by the per-sqft rehab model, so the
profit math is unreliable — and Bryan doesn't want them regardless. The scanner
now detects this via `FIRE_DAMAGE_FLAGS` in `flip_scout_redfin.py`
(sets `is_fire_damaged`), and both `hourly_check.py` and the full scan exclude
it. Flags are worded specifically so they never match "fireplace"/"fire pit".
If one is ever spotted on the list (manual add or older lead), remove it from
`leads_for_sheets.json` and the published board.

## ARV methodology preference — 1-mile-radius comps (Bryan, 2026-07-27)

Bryan wants the **After-Repair Value (ARV)** — "how much the property is worth
after repair" — estimated from **comparable sold homes within a ~1-mile radius**
of the subject (true nearby comps, ~4–8 recent sold, similar size/beds/baths),
**not** the current zip-wide size-matched median $/sqft proxy.

- **Current state:** `flip_scout_redfin.py` derives ARV from a zip-wide,
  size-matched median $/sqft (`build_arv_benchmarks` / `calculate_arv`). It is a
  zip-level proxy, not radius-based — the report footer already says as much.
- **Desired:** geocode the subject, pull sold comps within ~1 mile over the
  lookback window, size/bed/bath match, derive ARV from those. This is a real
  rework of the ARV engine and adds per-property geo/comp queries, so it must be
  scoped for rate limits before running on the hourly cadence (don't hammer
  Redfin every hour). Until implemented, keep labeling ARV as a zip-wide
  estimate so it's never mistaken for hand-picked radius comps.
- Always surface ARV clearly as **the estimated worth after renovation**.

## How manual adds reach Bryan's live spreadsheet

- Bryan's Google Sheet runs `flip_scout/FlipScoutSheet.gs`, which fetches
  `flip_scout/leads_for_sheets.json` from the GitHub raw URL on branch
  `claude/python-code-goal-nn6zec` and **appends** new rows (deduped by URL,
  never rewrites an existing row) on **Flip Scout → Refresh Now**.
- To put a listing on his sheet: add a row to `leads_for_sheets.json` matching
  the schema in `FlipScoutSheet.gs` `COLUMNS`, put a `MANUAL ADD (Bryan)` note
  in `risks`, then **commit + push** to that branch. Bryan then hits Refresh.
- For a non-flip asset (e.g. a fourplex) leave ARV/rehab/profit **blank** rather
  than fabricating single-family flip numbers.
- I do **not** have direct cell-write access to the Sheet — the JSON feed is the
  only path.
