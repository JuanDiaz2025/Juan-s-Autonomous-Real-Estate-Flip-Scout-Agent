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
