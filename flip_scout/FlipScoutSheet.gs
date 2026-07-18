/**
 * Flip Scout Agent -> Google Sheets sync.
 *
 * Pulls the latest leads from Juan's Flip Scout Agent repo (a public GitHub
 * repo) and APPENDS new ones into this spreadsheet - it never re-adds a
 * listing that's already a row here. Dedup key is the Redfin link (each
 * distinct listing has its own URL, so a relisting of the same address
 * later shows up as new, but the same still-active listing never repeats).
 *
 * METHODOLOGY (Twin Home Buyer standard): ARV = median sold $/sqft for the
 * zip (last 6mo) x sqft. Rehab cost shown as two scenarios - Light ($70/sqft)
 * and Heavy ($140-150/sqft). Holding = 3 months. Minimum required gross
 * profit is a DOLLAR amount by ARV tier ($1M+ ARV: $100k, $500k-$1M: $70k,
 * under $500k: $50k), not a percentage. No ADU Potential column - removed
 * per standing instruction. Only leads clearing the minimum threshold under
 * the LIGHT (best-case) rehab scenario ever reach this feed at all.
 *
 * SETUP (one time):
 *   1. Open your Google Sheet -> Extensions -> Apps Script.
 *   2. Delete anything in Code.gs and paste this whole file in.
 *   3. Save (the disk icon or Ctrl/Cmd+S). Name the project anything.
 *   4. Reload the spreadsheet tab. A new "Flip Scout" menu appears.
 *   5. Flip Scout -> Refresh Now : does one manual pull immediately, and
 *      will prompt you to grant permissions the first time (this is
 *      Google's own consent screen - it's your script running under your
 *      account, not something Claude has access to).
 *   6. Flip Scout -> Enable Hourly Auto-Refresh : installs a trigger so
 *      this keeps happening on its own. Run this once; it's idempotent
 *      (safe to click again, won't create duplicate triggers).
 *   7. Flip Scout -> Remove Non-Profitable Leads : a one-time backstop if
 *      any rows are already in the sheet from before this profitability
 *      check existed. Not needed on an ongoing basis.
 *   8. Flip Scout -> Resync Existing Leads : Refresh Now only ever ADDS
 *      new rows - it never rewrites a row already in the sheet, even if
 *      that lead's risks/financials/recommendation have since changed
 *      upstream (e.g. a risk category getting removed from the analysis).
 *      Run this any time you want already-added rows brought current
 *      without re-adding or duplicating anything.
 *
 * If Juan's repo branch ever changes (e.g. after this work merges to
 * main), update FEED_URL below to match - swap "claude/python-code-goal-nn6zec"
 * for "main".
 */

var FEED_URL = 'https://raw.githubusercontent.com/JuanDiaz2025/Juan-s-Autonomous-Real-Estate-Flip-Scout-Agent/claude/python-code-goal-nn6zec/flip_scout/leads_for_sheets.json';
var SHEET_NAME = 'Flip Scout Leads';

var COLUMNS = [
  { key: 'score', header: 'Score', format: '0' },
  { key: 'recommendation', header: 'Recommendation', format: '@' },
  { key: 'address', header: 'Address', format: '@' },
  { key: 'city', header: 'City', format: '@' },
  { key: 'zip', header: 'Zip', format: '@' },
  { key: 'beds', header: 'Beds', format: '0.#' },
  { key: 'baths', header: 'Baths', format: '0.#' },
  { key: 'sqft', header: 'SqFt', format: '#,##0' },
  { key: 'lot_sqft', header: 'Lot SqFt', format: '#,##0' },
  { key: 'year_built', header: 'Year Built', format: '0' },
  { key: 'price', header: 'Purchase Price', format: '$#,##0' },
  { key: 'arv', header: 'Estimated ARV', format: '$#,##0' },
  { key: 'rehab_light', header: 'Rehab Cost (Light)', format: '$#,##0' },
  { key: 'rehab_heavy', header: 'Rehab Cost (Heavy)', format: '$#,##0' },
  { key: 'holding_costs', header: 'Holding Costs (3mo)', format: '$#,##0' },
  { key: 'total_cost_light', header: 'Total Cost (Light)', format: '$#,##0' },
  { key: 'total_cost_heavy', header: 'Total Cost (Heavy)', format: '$#,##0' },
  { key: 'gross_profit_light', header: 'Gross Profit (Light)', format: '$#,##0' },
  { key: 'gross_profit_heavy', header: 'Gross Profit (Heavy)', format: '$#,##0' },
  { key: 'risks', header: 'Risks', format: '@' },
  { key: 'url', header: 'Redfin Link', format: '@' },
  { key: 'first_added', header: 'First Added', format: '@' },
];

var URL_COL_INDEX = COLUMNS.findIndex(function (c) { return c.key === 'url'; }) + 1; // 1-based
var PROFIT_COL_INDEX = COLUMNS.findIndex(function (c) { return c.key === 'gross_profit_light'; }) + 1; // 1-based

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Flip Scout')
    .addItem('Refresh Now', 'refreshFlipScoutSheet')
    .addItem('Resync Existing Leads', 'resyncExistingLeads')
    .addItem('Clear All Leads', 'clearAllLeads')
    .addItem('Remove Non-Profitable Leads', 'removeNonProfitableLeads')
    .addItem('Enable Hourly Auto-Refresh', 'enableHourlyTrigger')
    .addItem('Disable Auto-Refresh', 'disableHourlyTrigger')
    .addToUi();
}

function refreshFlipScoutSheet() {
  var response = UrlFetchApp.fetch(FEED_URL, { muteHttpExceptions: true });
  if (response.getResponseCode() !== 200) {
    throw new Error('Could not fetch leads feed (HTTP ' + response.getResponseCode() + '). ' +
      'Check FEED_URL still points at a real branch/file in the repo.');
  }

  var feed = JSON.parse(response.getContentText());
  var leads = feed.leads || [];

  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(SHEET_NAME);
  var isNewSheet = !sheet;
  if (isNewSheet) {
    sheet = ss.insertSheet(SHEET_NAME);
  }

  var headers = COLUMNS.map(function (c) { return c.header; });

  // Detect a stale header row from an earlier methodology (e.g. Spread %,
  // Reno Budget, ADU Potential) - those columns don't map onto the current
  // ones at all, so there's nothing to preserve. Clear the sheet and
  // rebuild fresh under the current schema rather than appending new-schema
  // rows after an old-schema header, which is what silently left "ADU
  // Potential"/"Reno Budget" showing even after this script was updated.
  var hasStaleHeader = false;
  if (!isNewSheet && sheet.getLastRow() > 0) {
    var existingHeaderRow = sheet.getRange(1, 1, 1, Math.max(sheet.getLastColumn(), 1)).getValues()[0];
    hasStaleHeader = !headers.every(function (h, i) { return existingHeaderRow[i] === h; });
  }

  if (isNewSheet || sheet.getLastRow() === 0 || hasStaleHeader) {
    if (hasStaleHeader) {
      sheet.clear();
    }
    sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
    sheet.getRange(1, 1, 1, headers.length).setFontWeight('bold');
    sheet.setFrozenRows(1);
  }

  // build the set of listings already in the sheet (by Redfin link), so a
  // still-active listing is never appended twice
  var existingUrls = {};
  var lastRow = sheet.getLastRow();
  if (lastRow > 1) {
    var existing = sheet.getRange(2, URL_COL_INDEX, lastRow - 1, 1).getValues();
    existing.forEach(function (row) {
      if (row[0]) existingUrls[row[0]] = true;
    });
  }

  // gross_profit_light > 0 is a belt-and-suspenders check - the feed itself
  // should only ever contain leads clearing the minimum profit threshold,
  // but never let a negative-profit row reach the sheet regardless.
  var newLeads = leads.filter(function (lead) {
    return !existingUrls[lead.url] && lead.gross_profit_light > 0;
  });

  ss.toast(newLeads.length + ' new lead(s) found, ' + Object.keys(existingUrls).length + ' already in sheet.', 'Flip Scout', 5);

  if (newLeads.length === 0) {
    sheet.getRange(1, 1).setNote('Last checked: ' + new Date().toString() +
      '\nFeed generated: ' + feed.generated_at + '\nNo new leads this check.');
    return;
  }

  var now = new Date().toString();
  var rows = newLeads.map(function (lead) {
    return COLUMNS.map(function (c) {
      if (c.key === 'first_added') return now;
      var v = lead[c.key];
      return v === undefined || v === null ? '' : v;
    });
  });

  var startRow = sheet.getLastRow() + 1;
  sheet.getRange(startRow, 1, rows.length, headers.length).setValues(rows);

  COLUMNS.forEach(function (c, i) {
    sheet.getRange(startRow, i + 1, rows.length, 1).setNumberFormat(c.format);
  });

  sheet.autoResizeColumns(1, headers.length);
  sheet.getRange(1, 1).setNote('Last checked: ' + now +
    '\nFeed generated: ' + feed.generated_at +
    '\n' + newLeads.length + ' new lead(s) added this check.');
}

/**
 * Refresh Now only APPENDS brand-new leads (dedup by URL) - it never
 * touches a row already in the sheet, even if that lead's data (risks,
 * financials, recommendation) has since changed upstream, e.g. a risk
 * criterion getting removed from the analysis. Run this whenever you want
 * already-added rows brought up to date with the current feed, without
 * re-adding or duplicating anything.
 *
 * Matches existing rows to the feed by Redfin link. Overwrites every
 * column EXCEPT "First Added" (that date is preserved as-is). Any row
 * whose URL isn't in the feed anymore (e.g. the listing sold or was
 * pulled) is left untouched, not deleted - this only updates, never removes.
 */
function resyncExistingLeads() {
  var response = UrlFetchApp.fetch(FEED_URL, { muteHttpExceptions: true });
  if (response.getResponseCode() !== 200) {
    throw new Error('Could not fetch leads feed (HTTP ' + response.getResponseCode() + '). ' +
      'Check FEED_URL still points at a real branch/file in the repo.');
  }

  var feed = JSON.parse(response.getContentText());
  var leadsByUrl = {};
  (feed.leads || []).forEach(function (lead) { leadsByUrl[lead.url] = lead; });

  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) {
    SpreadsheetApp.getUi().alert('No "' + SHEET_NAME + '" sheet found yet - run Refresh Now first.');
    return;
  }

  var lastRow = sheet.getLastRow();
  if (lastRow <= 1) {
    SpreadsheetApp.getUi().alert('No leads to resync.');
    return;
  }

  var firstAddedColIdx = COLUMNS.findIndex(function (c) { return c.key === 'first_added'; });
  var urlColIdx = URL_COL_INDEX - 1;

  var range = sheet.getRange(2, 1, lastRow - 1, COLUMNS.length);
  var rows = range.getValues();
  var updated = 0;

  for (var i = 0; i < rows.length; i++) {
    var lead = leadsByUrl[rows[i][urlColIdx]];
    if (!lead) continue; // no longer in the feed - leave this row alone

    var firstAdded = rows[i][firstAddedColIdx];
    rows[i] = COLUMNS.map(function (c) {
      if (c.key === 'first_added') return firstAdded;
      var v = lead[c.key];
      return v === undefined || v === null ? '' : v;
    });
    updated++;
  }

  range.setValues(rows);
  COLUMNS.forEach(function (c, i) {
    sheet.getRange(2, i + 1, rows.length, 1).setNumberFormat(c.format);
  });

  SpreadsheetApp.getUi().alert(updated + ' existing lead(s) refreshed with the latest feed data ' +
    '(risks, financials, recommendation). Rows no longer in the feed were left untouched.');
}

/**
 * Wipes every lead row (keeps the header) so the next Refresh Now
 * repopulates from scratch under the current feed/methodology - use this
 * when the underlying analysis changed enough that you want a clean slate
 * rather than a row-by-row resync (e.g. a re-scan with a different ARV
 * basis). Asks for confirmation first since this can't be undone from
 * inside the script.
 */
function clearAllLeads() {
  var ui = SpreadsheetApp.getUi();
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) {
    ui.alert('No "' + SHEET_NAME + '" sheet found - nothing to clear.');
    return;
  }

  var lastRow = sheet.getLastRow();
  if (lastRow <= 1) {
    ui.alert('No leads to clear.');
    return;
  }

  var response = ui.alert('Clear All Leads',
    'This deletes all ' + (lastRow - 1) + ' lead row(s) below the header. This cannot be undone. Continue?',
    ui.ButtonSet.YES_NO);
  if (response !== ui.Button.YES) return;

  sheet.deleteRows(2, lastRow - 1);
  ui.alert('Cleared. Run Refresh Now to repopulate from the current feed.');
}

/**
 * One-time cleanup: deletes any row already in the sheet with Gross Profit
 * (Light) at or below zero. Only needed if rows were added before this
 * profitability check existed (e.g. from an earlier CSV import, or a feed
 * built under the old methodology) - refreshFlipScoutSheet now filters
 * these out before they're ever added, so this is a backstop, not
 * something you need to run regularly.
 */
function removeNonProfitableLeads() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) {
    SpreadsheetApp.getUi().alert('No "' + SHEET_NAME + '" sheet found yet - run Refresh Now first.');
    return;
  }

  var lastRow = sheet.getLastRow();
  if (lastRow <= 1) {
    SpreadsheetApp.getUi().alert('No leads to check.');
    return;
  }

  var profitValues = sheet.getRange(2, PROFIT_COL_INDEX, lastRow - 1, 1).getValues();
  var rowsToDelete = [];
  for (var i = 0; i < profitValues.length; i++) {
    var v = profitValues[i][0];
    if (typeof v === 'number' && v <= 0) {
      rowsToDelete.push(i + 2); // +2: 1-based, plus header row
    }
  }

  // delete bottom-up so row indices above don't shift as we go
  rowsToDelete.sort(function (a, b) { return b - a; });
  rowsToDelete.forEach(function (rowIndex) {
    sheet.deleteRow(rowIndex);
  });

  SpreadsheetApp.getUi().alert(rowsToDelete.length + ' non-profitable lead(s) removed.');
}

var TRIGGER_HANDLER = 'refreshFlipScoutSheet';

function enableHourlyTrigger() {
  disableHourlyTrigger(); // avoid duplicates if clicked more than once
  ScriptApp.newTrigger(TRIGGER_HANDLER).timeBased().everyHours(1).create();
  SpreadsheetApp.getUi().alert('Hourly auto-refresh enabled. New leads will be appended every hour - existing rows are never touched or duplicated.');
}

function disableHourlyTrigger() {
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === TRIGGER_HANDLER) {
      ScriptApp.deleteTrigger(triggers[i]);
    }
  }
}
