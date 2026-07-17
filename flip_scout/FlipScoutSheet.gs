/**
 * Flip Scout Agent -> Google Sheets sync.
 *
 * Pulls the latest leads from Juan's Flip Scout Agent repo (a public GitHub
 * repo) and writes them into this spreadsheet, either on demand (menu item)
 * or on a schedule (time-driven trigger you install once).
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
];

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
  if (!sheet) {
    sheet = ss.insertSheet(SHEET_NAME);
  }
  sheet.clear();

  // header row
  var headers = COLUMNS.map(function (c) { return c.header; });
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  sheet.getRange(1, 1, 1, headers.length).setFontWeight('bold');
  sheet.setFrozenRows(1);

  if (leads.length === 0) {
    sheet.getRange(2, 1).setValue('No qualifying leads in the feed right now.');
    writeTimestamp(sheet, feed.generated_at, headers.length);
    return;
  }

  var rows = leads.map(function (lead) {
    return COLUMNS.map(function (c) {
      var v = lead[c.key];
      if (c.key === 'adu_potential') return v ? 'Yes' : 'No';
      return v === undefined || v === null ? '' : v;
    });
  });
  sheet.getRange(2, 1, rows.length, headers.length).setValues(rows);

  // number formats per column
  COLUMNS.forEach(function (c, i) {
    sheet.getRange(2, i + 1, rows.length, 1).setNumberFormat(c.format);
  });

  sheet.autoResizeColumns(1, headers.length);
  writeTimestamp(sheet, feed.generated_at, headers.length);
}

function writeTimestamp(sheet, generatedAt, lastCol) {
  var noteRow = sheet.getLastRow() + 2;
  sheet.getRange(noteRow, 1).setValue('Feed generated: ' + generatedAt);
  sheet.getRange(noteRow + 1, 1).setValue('Sheet last refreshed: ' + new Date().toString());
}

var TRIGGER_HANDLER = 'refreshFlipScoutSheet';

function enableHourlyTrigger() {
  disableHourlyTrigger(); // avoid duplicates if clicked more than once
  ScriptApp.newTrigger(TRIGGER_HANDLER).timeBased().everyHours(1).create();
  SpreadsheetApp.getUi().alert('Hourly auto-refresh enabled. This sheet will pull fresh leads every hour.');
}

function disableHourlyTrigger() {
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === TRIGGER_HANDLER) {
      ScriptApp.deleteTrigger(triggers[i]);
    }
  }
}
