/**
 * Flip Scout Agent -> Google Sheets sync.
 *
 * Pulls the latest leads from Juan's Flip Scout Agent repo (a public GitHub
 * repo) and APPENDS new ones into this spreadsheet - it never re-adds a
 * listing that's already a row here. Dedup key is the Redfin link (each
 * distinct listing has its own URL, so a relisting of the same address
 * later shows up as new, but the same still-active listing never repeats).
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
 *
 * If Juan's repo branch ever changes (e.g. after this work merges to
 * main), update FEED_URL below to match - swap "claude/python-code-goal-nn6zec"
 * for "main".
 */

var FEED_URL = 'https://raw.githubusercontent.com/JuanDiaz2025/Juan-s-Autonomous-Real-Estate-Flip-Scout-Agent/claude/python-code-goal-nn6zec/flip_scout/leads_for_sheets.json';
var SHEET_NAME = 'Flip Scout Leads';

var COLUMNS = [
  { key: 'score', header: 'Score', format: '0' },
  { key: 'address', header: 'Address', format: '@' },
  { key: 'city', header: 'City', format: '@' },
  { key: 'zip', header: 'Zip', format: '@' },
  { key: 'beds', header: 'Beds', format: '0.#' },
  { key: 'baths', header: 'Baths', format: '0.#' },
  { key: 'sqft', header: 'SqFt', format: '#,##0' },
  { key: 'lot_sqft', header: 'Lot SqFt', format: '#,##0' },
  { key: 'year_built', header: 'Year Built', format: '0' },
  { key: 'price', header: 'List Price', format: '$#,##0' },
  { key: 'arv', header: 'Est. ARV (comp-based)', format: '$#,##0' },
  { key: 'reno_budget', header: 'Reno Budget', format: '$#,##0' },
  { key: 'holding_costs', header: 'Holding Costs', format: '$#,##0' },
  { key: 'total_cost', header: 'Total Cost', format: '$#,##0' },
  { key: 'net_spread', header: 'Net Spread', format: '$#,##0' },
  { key: 'spread_percent', header: 'Spread %', format: '0.0%' },
  { key: 'adu_potential', header: 'ADU Potential', format: '@' },
  { key: 'risks', header: 'Risks', format: '@' },
  { key: 'url', header: 'Redfin Link', format: '@' },
  { key: 'first_added', header: 'First Added', format: '@' },
];

var URL_COL_INDEX = COLUMNS.findIndex(function (c) { return c.key === 'url'; }) + 1; // 1-based

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Flip Scout')
    .addItem('Refresh Now', 'refreshFlipScoutSheet')
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
  if (isNewSheet || sheet.getLastRow() === 0) {
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

  var newLeads = leads.filter(function (lead) { return !existingUrls[lead.url]; });

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
      if (c.key === 'adu_potential') return v ? 'Yes' : 'No';
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
