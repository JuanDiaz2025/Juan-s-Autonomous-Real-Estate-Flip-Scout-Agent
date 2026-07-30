#!/usr/bin/env python3
"""
Flip Scout control app - a small local web dashboard for Juan's Real Estate
Flip Scout Agent.

Zero external dependencies (Python 3.8+ stdlib only), so it runs with just:

    python3 flip_scout/app.py

then open http://127.0.0.1:8787 in a browser.

What it gives you:
  - A live dashboard: KPI funnel, qualified leads, and rejected leads, read
    from the same JSON the Google Sheet uses (leads_for_sheets.json,
    rejected_for_sheets.json, kpi_log.json).
  - PAUSE / PLAY for the hourly scanner. When Playing, a background thread
    runs flip_scout/hourly_check.py about once an hour. Pausing stops it -
    nothing scans until you press Play again. The state persists across
    restarts in scanner_state.json.
  - RUN CHECK NOW - trigger one hourly_check.py run on demand.
  - GENERATE REPORT - build a dated HTML report (KPI rollup + current leads +
    rejected breakdown) into flip_scout/reports/. Also produced automatically
    once a day while Playing.

This app only orchestrates the existing scripts - it does not re-implement
scanning or scoring. hourly_check.py remains the single source of truth for
what qualifies.
"""

import json
import os
import subprocess
import threading
import time
import html
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
LEADS_PATH = os.path.join(HERE, "leads_for_sheets.json")
REJECTED_PATH = os.path.join(HERE, "rejected_for_sheets.json")
KPI_LOG_PATH = os.path.join(HERE, "kpi_log.json")
STATE_PATH = os.path.join(HERE, "scanner_state.json")
REPORTS_DIR = os.path.join(HERE, "reports")
HOURLY_CHECK = os.path.join(HERE, "hourly_check.py")
BUILD_REJECTED = os.path.join(HERE, "build_rejected_feed.py")

HOST = os.environ.get("FLIP_SCOUT_HOST", "127.0.0.1")
PORT = int(os.environ.get("FLIP_SCOUT_PORT", "8787"))

CHECK_INTERVAL_SEC = 3600      # ~1 hour between auto checks while Playing
REPORT_HOUR_UTC = 15           # daily report generated on/after this UTC hour
SCHED_TICK_SEC = 30            # how often the scheduler wakes to decide

_state_lock = threading.Lock()
_run_lock = threading.Lock()   # only one scanner subprocess at a time


# --------------------------------------------------------------------------
# state
# --------------------------------------------------------------------------
def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_state():
    # Default to PAUSED so importing/launching the app never surprise-runs a
    # scan - the operator presses Play when they want scanning to begin.
    return {
        "paused": True,
        "last_check_started": None,
        "last_check_finished": None,
        "last_check_result": None,   # "new_leads:N" | "no_new_leads" | "error"
        "last_report": None,
        "last_report_date": None,
        "running_now": False,
    }


def load_state():
    if os.path.exists(STATE_PATH):
        try:
            s = default_state()
            s.update(json.load(open(STATE_PATH)))
            return s
        except (ValueError, OSError):
            pass
    return default_state()


def save_state(state):
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_PATH)


def update_state(**kw):
    with _state_lock:
        s = load_state()
        s.update(kw)
        save_state(s)
        return s


# --------------------------------------------------------------------------
# data loading
# --------------------------------------------------------------------------
def _read_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        return json.load(open(path))
    except (ValueError, OSError):
        return default


def load_leads():
    feed = _read_json(LEADS_PATH, {})
    return feed.get("generated_at"), feed.get("leads", [])


def load_rejected():
    feed = _read_json(REJECTED_PATH, {})
    return feed


def kpi_totals():
    log = _read_json(KPI_LOG_PATH, [])
    runs = [e for e in log if e.get("kind") == "run"]
    removals = [e for e in log if e.get("kind") == "manual_removal"]
    checked = sum(r.get("new_listings_checked", 0) for r in runs)
    qualified = sum(r.get("qualified", 0) for r in runs)
    excluded = sum(r.get("excluded_total", 0) for r in runs)
    return {
        "runs": len(runs),
        "checked": checked,
        "qualified_all_time": qualified,
        "excluded": excluded,
        "manual_removals": len(removals),
        "first": runs[0]["timestamp"][:10] if runs else None,
        "last": runs[-1]["timestamp"][:10] if runs else None,
    }


# --------------------------------------------------------------------------
# scanner + report actions
# --------------------------------------------------------------------------
def run_check_once():
    """Run hourly_check.py once (blocking). Returns a short result string.
    Guarded so two runs can't overlap."""
    if not _run_lock.acquire(blocking=False):
        return "busy"
    try:
        update_state(running_now=True, last_check_started=_now_iso())
        # clear any stale new_leads.json so its presence means THIS run found some
        nl = os.path.join(HERE, "new_leads.json")
        try:
            os.remove(nl)
        except OSError:
            pass
        try:
            proc = subprocess.run(
                ["python3", HOURLY_CHECK],
                cwd=os.path.dirname(HERE), capture_output=True, text=True, timeout=1500,
            )
            ok = proc.returncode == 0
        except (subprocess.TimeoutExpired, OSError) as e:
            update_state(running_now=False, last_check_finished=_now_iso(),
                         last_check_result="error: %s" % type(e).__name__)
            return "error"

        if not ok:
            result = "error"
        elif os.path.exists(nl):
            found = _read_json(nl, [])
            n = len(found) if isinstance(found, list) else found.get("count", 0)
            result = "new_leads:%d" % n
        else:
            result = "no_new_leads"
        update_state(running_now=False, last_check_finished=_now_iso(),
                     last_check_result=result)
        return result
    finally:
        _run_lock.release()


def generate_report():
    """Build a dated HTML report into reports/ and return its filename."""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    # refresh the rejected feed so the report reflects the latest removals
    try:
        subprocess.run(["python3", BUILD_REJECTED], cwd=os.path.dirname(HERE),
                       capture_output=True, text=True, timeout=120)
    except (subprocess.TimeoutExpired, OSError):
        pass

    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    fname = "report_%s.html" % day
    path = os.path.join(REPORTS_DIR, fname)
    _gen_at, leads = load_leads()
    rejected = load_rejected()
    k = kpi_totals()

    html_doc = _render_report(day, leads, rejected, k)
    with open(path, "w") as f:
        f.write(html_doc)
    update_state(last_report=fname, last_report_date=day)
    return fname


# --------------------------------------------------------------------------
# background scheduler
# --------------------------------------------------------------------------
_scheduler_stop = threading.Event()


def _seconds_since(iso):
    if not iso:
        return float("inf")
    try:
        t = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - t).total_seconds()
    except ValueError:
        return float("inf")


def scheduler_loop():
    while not _scheduler_stop.is_set():
        try:
            s = load_state()
            if not s.get("paused"):
                # hourly scan
                if _seconds_since(s.get("last_check_finished")) >= CHECK_INTERVAL_SEC \
                        and not s.get("running_now"):
                    run_check_once()
                # daily report
                now = datetime.now(timezone.utc)
                today = now.strftime("%Y-%m-%d")
                if now.hour >= REPORT_HOUR_UTC and s.get("last_report_date") != today:
                    generate_report()
        except Exception:
            pass  # scheduler must never die on a transient error
        _scheduler_stop.wait(SCHED_TICK_SEC)


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # quiet

    def _send(self, code, body, ctype="application/json"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj), "application/json")

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            self._send(200, render_dashboard(), "text/html; charset=utf-8")
        elif path == "/api/status":
            self._json(status_payload())
        elif path == "/api/data":
            gen, leads = load_leads()
            self._json({"generated_at": gen, "leads": leads,
                        "rejected": load_rejected()})
        elif path.startswith("/reports/"):
            fname = os.path.basename(path)
            fpath = os.path.join(REPORTS_DIR, fname)
            if os.path.isfile(fpath) and fname.endswith(".html"):
                self._send(200, open(fpath, "rb").read(), "text/html; charset=utf-8")
            else:
                self._send(404, "Not found", "text/plain")
        else:
            self._send(404, "Not found", "text/plain")

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/api/pause":
            self._json(status_payload(update_state(paused=True)))
        elif path == "/api/play":
            self._json(status_payload(update_state(paused=False)))
        elif path == "/api/run-check":
            # run in a thread so the request returns immediately
            threading.Thread(target=run_check_once, daemon=True).start()
            self._json({"started": True})
        elif path == "/api/run-report":
            fname = generate_report()
            self._json({"report": fname})
        else:
            self._send(404, "Not found", "text/plain")


def status_payload(state=None):
    s = state or load_state()
    gen, leads = load_leads()
    rejected = load_rejected()
    return {
        "paused": s.get("paused", True),
        "running_now": s.get("running_now", False),
        "last_check_started": s.get("last_check_started"),
        "last_check_finished": s.get("last_check_finished"),
        "last_check_result": s.get("last_check_result"),
        "last_report": s.get("last_report"),
        "last_report_date": s.get("last_report_date"),
        "leads_generated_at": gen,
        "kpi": kpi_totals(),
        "counts": {
            "qualified_current": len(leads),
            "rejected": rejected.get("count", len(rejected.get("rejected", []))),
        },
        "rejected_categories": rejected.get("category_counts", {}),
        "reports": sorted(os.listdir(REPORTS_DIR), reverse=True)
        if os.path.isdir(REPORTS_DIR) else [],
    }


# --------------------------------------------------------------------------
# HTML rendering
# --------------------------------------------------------------------------
def _money(v):
    try:
        return "${:,.0f}".format(float(v))
    except (TypeError, ValueError):
        return "" if v in (None, "") else str(v)


def _render_report(day, leads, rejected, k):
    rows = "".join(
        "<tr><td>%s</td><td>%s</td><td>%s, %s</td><td class='n'>%s</td>"
        "<td class='n'>%s</td><td class='n'>%s</td></tr>" % (
            html.escape(str(l.get("score", ""))),
            html.escape(str(l.get("recommendation", ""))),
            html.escape(str(l.get("address", ""))), html.escape(str(l.get("city", ""))),
            _money(l.get("price")), _money(l.get("arv")),
            _money(l.get("gross_profit_light")),
        ) for l in sorted(leads, key=lambda x: -(x.get("score") or 0))
    )
    cats = rejected.get("category_counts", {})
    catrows = "".join("<tr><td>%s</td><td class='n'>%d</td></tr>" % (html.escape(c), n)
                      for c, n in cats.items())
    return """<!doctype html><html><head><meta charset="utf-8">
<title>Flip Scout Report %s</title>
<style>body{font-family:system-ui,sans-serif;max-width:960px;margin:32px auto;padding:0 20px;color:#17202e}
h1{margin:0 0 4px}h2{margin-top:32px;border-bottom:2px solid #2f6699;padding-bottom:4px}
.sub{color:#5b6675}table{border-collapse:collapse;width:100%%;margin-top:10px}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid #e0e5ec;font-size:14px}
th{background:#f5f7fa;text-transform:uppercase;font-size:11px;letter-spacing:.06em;color:#5b6675}
.n{text-align:right;font-variant-numeric:tabular-nums}
.kpi{display:flex;gap:24px;margin:16px 0}.kpi div{background:#f5f7fa;border-radius:8px;padding:12px 18px}
.kpi b{display:block;font-size:22px}</style></head><body>
<h1>Flip Scout Daily Report</h1><div class="sub">%s (UTC) &middot; generated by app.py</div>
<div class="kpi">
<div><b>%d</b>qualified now</div>
<div><b>%d</b>rejected (manual)</div>
<div><b>%d</b>checked all-time</div>
<div><b>%d</b>runs</div></div>
<h2>Qualified leads (%d)</h2>
<table><thead><tr><th>Score</th><th>Rec</th><th>Address</th><th>Price</th><th>ARV</th><th>Profit (Light)</th></tr></thead>
<tbody>%s</tbody></table>
<h2>Rejected leads by category (%d total)</h2>
<table><thead><tr><th>Category</th><th>Count</th></tr></thead><tbody>%s</tbody></table>
</body></html>""" % (
        html.escape(day), html.escape(day),
        len(leads),
        rejected.get("count", 0), k["checked"], k["runs"],
        len(leads), rows, rejected.get("count", 0), catrows,
    )


def render_dashboard():
    # The dashboard is a single self-contained page; live data comes from
    # /api/status and /api/data via fetch, so Pause/Play/Run reflect instantly.
    return DASHBOARD_HTML


def main():
    os.makedirs(REPORTS_DIR, exist_ok=True)
    if not os.path.exists(STATE_PATH):
        save_state(default_state())
    threading.Thread(target=scheduler_loop, daemon=True).start()
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print("Flip Scout app running at http://%s:%d  (Ctrl+C to stop)" % (HOST, PORT))
    print("Scanner starts PAUSED - press Play in the UI to begin hourly scanning.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        _scheduler_stop.set()
        httpd.shutdown()


DASHBOARD_HTML = r"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Flip Scout Console</title>
<style>
:root{--ground:#eef1f5;--surface:#fff;--surface2:#f5f7fa;--ink:#17202e;--muted:#5b6675;
--faint:#8791a0;--hair:#e0e5ec;--hairs:#cdd4de;--accent:#2f6699;--good:#2d7d74;
--warn:#a9772f;--reject:#b0503b;--shadow:0 1px 2px rgba(20,32,50,.05),0 4px 16px rgba(20,32,50,.06)}
@media(prefers-color-scheme:dark){:root{--ground:#0c121d;--surface:#141c29;--surface2:#101825;
--ink:#e7ecf3;--muted:#93a0b2;--faint:#69768a;--hair:#222d3d;--hairs:#2e3a4c;--accent:#6ea8dd;
--good:#5bb3a7;--warn:#d0a35c;--reject:#d47a64;--shadow:0 1px 2px rgba(0,0,0,.3),0 6px 20px rgba(0,0,0,.35)}}
*{box-sizing:border-box}body{margin:0;font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
background:var(--ground);color:var(--ink);line-height:1.5}
.mono{font-family:ui-monospace,Menlo,Consolas,monospace;font-variant-numeric:tabular-nums}
.wrap{max-width:1180px;margin:0 auto;padding:clamp(16px,3vw,36px)}
header{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap}
h1{font-size:1.5rem;margin:0;letter-spacing:-.02em}
.eyebrow{font-size:.7rem;letter-spacing:.16em;text-transform:uppercase;color:var(--accent);font-weight:700}
.statuschip{display:inline-flex;align-items:center;gap:8px;padding:7px 14px;border-radius:999px;
font-size:.82rem;font-weight:600;border:1px solid var(--hairs);background:var(--surface)}
.statuschip .led{width:9px;height:9px;border-radius:50%;background:var(--faint)}
.statuschip.playing .led{background:var(--good);box-shadow:0 0 0 3px color-mix(in srgb,var(--good) 25%,transparent)}
.statuschip.paused .led{background:var(--warn)}
.statuschip.running .led{background:var(--accent);animation:pulse 1s infinite}
@keyframes pulse{50%{opacity:.35}}
.controls{display:flex;gap:10px;flex-wrap:wrap;margin:22px 0}
button{font:inherit;font-weight:600;cursor:pointer;border-radius:10px;padding:10px 18px;border:1px solid var(--hairs);
background:var(--surface);color:var(--ink);box-shadow:var(--shadow);display:inline-flex;align-items:center;gap:8px;transition:.15s}
button:hover{border-color:var(--accent)}button:disabled{opacity:.45;cursor:not-allowed}
button.primary{background:var(--accent);color:#fff;border-color:var(--accent)}
button.play{background:var(--good);color:#fff;border-color:var(--good)}
button.pause{background:var(--warn);color:#fff;border-color:var(--warn)}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin:8px 0 26px}
.kpi{background:var(--surface);border:1px solid var(--hair);border-radius:12px;padding:15px 18px;box-shadow:var(--shadow);position:relative;overflow:hidden}
.kpi::after{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--hairs)}
.kpi.a::after{background:var(--accent)}.kpi.g::after{background:var(--good)}.kpi.r::after{background:var(--reject)}
.kpi .n{font-size:1.7rem;font-weight:700;letter-spacing:-.02em;line-height:1}
.kpi .l{font-size:.72rem;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);margin-top:7px}
.meta{font-size:.8rem;color:var(--faint);margin:-14px 0 24px}
.tabs{display:flex;gap:4px;border-bottom:1px solid var(--hair);margin-bottom:0}
.tab{padding:10px 16px;border:0;background:none;box-shadow:none;border-bottom:2px solid transparent;color:var(--muted);border-radius:0}
.tab[aria-selected=true]{color:var(--ink);border-bottom-color:var(--accent)}
.panel{background:var(--surface);border:1px solid var(--hair);border-top:0;border-radius:0 0 12px 12px;box-shadow:var(--shadow);overflow-x:auto}
table{border-collapse:collapse;width:100%;min-width:640px}
th{position:sticky;top:0;background:var(--surface2);text-align:left;font-size:.68rem;letter-spacing:.07em;
text-transform:uppercase;color:var(--muted);font-weight:700;padding:11px 14px;border-bottom:1px solid var(--hairs);white-space:nowrap}
td{padding:11px 14px;border-bottom:1px solid var(--hair);font-size:.87rem;vertical-align:top}
tr:last-child td{border-bottom:0}tbody tr:hover{background:var(--surface2)}
.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.pos{color:var(--good);font-weight:600}.neg{color:var(--reject);font-weight:600}
a{color:var(--accent)}.addr{font-weight:600;white-space:nowrap}
.pill{display:inline-block;font-size:.72rem;font-weight:600;padding:2px 9px;border-radius:999px;background:var(--surface2);border:1px solid var(--hairs)}
.reason{color:var(--muted);max-width:44ch;min-width:220px}
.report-list{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}
.report-list a{font-size:.82rem;padding:6px 12px;border:1px solid var(--hairs);border-radius:8px;text-decoration:none;background:var(--surface)}
.toast{position:fixed;bottom:20px;left:50%;transform:translateX(-50%) translateY(120%);background:var(--ink);color:var(--ground);
padding:11px 20px;border-radius:10px;font-size:.87rem;font-weight:600;box-shadow:var(--shadow);transition:.3s;z-index:9}
.toast.show{transform:translateX(-50%) translateY(0)}
h2{font-size:1rem;margin:30px 0 6px}
</style></head><body>
<div class="wrap">
  <header>
    <div><div class="eyebrow">Juan &middot; Real Estate Flip Scout</div><h1>Scanner Console</h1></div>
    <div id="statuschip" class="statuschip paused"><span class="led"></span><span id="statustext">Loading…</span></div>
  </header>

  <div class="controls">
    <button id="btnPlay" class="play">▶ Play</button>
    <button id="btnPause" class="pause">⏸ Pause</button>
    <button id="btnCheck" class="primary">⟳ Run check now</button>
    <button id="btnReport">🖨 Generate report</button>
    <button id="btnRefresh">↻ Refresh view</button>
  </div>

  <div class="kpis" id="kpis"></div>
  <div class="meta" id="meta"></div>

  <div class="tabs" role="tablist">
    <button class="tab" role="tab" aria-selected="true" data-tab="leads">Qualified leads</button>
    <button class="tab" role="tab" aria-selected="false" data-tab="rejected">Rejected leads</button>
  </div>
  <div class="panel"><div id="tab-leads"></div><div id="tab-rejected" hidden></div></div>

  <h2>Reports</h2>
  <div class="report-list" id="reports"></div>
</div>
<div class="toast" id="toast"></div>

<script>
const $=s=>document.querySelector(s);
const money=v=>{const n=Number(v);return isFinite(n)&&v!==""&&v!=null?"$"+n.toLocaleString(undefined,{maximumFractionDigits:0}):(v==null||v===""?"":v)};
const esc=s=>String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
let DATA={leads:[],rejected:{rejected:[],category_counts:{}}};

function toast(m){const t=$("#toast");t.textContent=m;t.classList.add("show");setTimeout(()=>t.classList.remove("show"),2600);}

async function api(path,method){const r=await fetch(path,{method:method||"GET"});return r.json();}

function renderStatus(s){
  const chip=$("#statuschip"),txt=$("#statustext");
  chip.className="statuschip "+(s.running_now?"running":(s.paused?"paused":"playing"));
  txt.textContent=s.running_now?"Scanning…":(s.paused?"Paused":"Playing — hourly");
  $("#btnPlay").disabled=!s.paused; $("#btnPause").disabled=s.paused;
  $("#btnCheck").disabled=s.running_now;
  const k=s.kpi||{}, c=s.counts||{};
  $("#kpis").innerHTML=[
    ["g",c.qualified_current,"Qualified now"],
    ["r",c.rejected,"Rejected (manual)"],
    ["a",k.checked,"Checked all-time"],
    ["","",""].length&&["",k.runs,"Hourly runs"],
    ["",k.excluded,"Auto-excluded"],
  ].filter(Boolean).map(([cls,n,l])=>`<div class="kpi ${cls}"><div class="n mono">${(n||0).toLocaleString()}</div><div class="l">${l}</div></div>`).join("");
  const lc=s.last_check_finished?`Last check ${s.last_check_finished} → ${esc(s.last_check_result||"?")}`:"No check run yet";
  const fg=s.leads_generated_at?` · Feed generated ${esc(s.leads_generated_at)}`:"";
  const rp=s.last_report?` · Last report ${esc(s.last_report)}`:"";
  $("#meta").textContent=lc+fg+rp;
  $("#reports").innerHTML=(s.reports||[]).length?s.reports.map(f=>`<a href="/reports/${encodeURIComponent(f)}" target="_blank">${esc(f)}</a>`).join(""):'<span style="color:var(--faint);font-size:.82rem">No reports yet — press Generate report.</span>';
}

function renderLeads(){
  const rows=(DATA.leads||[]).slice().sort((a,b)=>(b.score||0)-(a.score||0)).map(l=>{
    const p=Number(l.gross_profit_light);
    const pc=isFinite(p)?(p>=0?"pos":"neg"):"";
    return `<tr><td class="n mono">${esc(l.score)}</td><td><span class="pill">${esc(l.recommendation)}</span></td>
    <td class="addr">${l.url?`<a href="${esc(l.url)}" target="_blank">${esc(l.address)}</a>`:esc(l.address)}</td>
    <td>${esc(l.city)} ${esc(l.zip)}</td><td class="n mono">${money(l.price)}</td>
    <td class="n mono">${money(l.arv)}</td><td class="n mono ${pc}">${money(l.gross_profit_light)}</td></tr>`;
  }).join("");
  $("#tab-leads").innerHTML=`<table><thead><tr><th>Score</th><th>Rec</th><th>Address</th><th>City / Zip</th><th>Price</th><th>Est. ARV</th><th>Profit (Light)</th></tr></thead><tbody>${rows||'<tr><td colspan=7 style="padding:32px;text-align:center;color:var(--faint)">No leads in feed.</td></tr>'}</tbody></table>`;
}
function renderRejected(){
  const rows=(DATA.rejected.rejected||[]).slice().reverse().map(r=>
    `<tr><td class="mono" style="white-space:nowrap;color:var(--faint)">${esc(r.date)}</td>
    <td class="addr">${r.url?`<a href="${esc(r.url)}" target="_blank">${esc(r.address)}</a>`:esc(r.address)}</td>
    <td><span class="pill">${esc(r.category)}</span></td><td class="reason">${esc(r.reason)}</td></tr>`).join("");
  $("#tab-rejected").innerHTML=`<table><thead><tr><th>Date</th><th>Address</th><th>Category</th><th>Reason cut</th></tr></thead><tbody>${rows||'<tr><td colspan=4 style="padding:32px;text-align:center;color:var(--faint)">No rejected leads.</td></tr>'}</tbody></table>`;
}

document.querySelectorAll(".tab").forEach(t=>t.onclick=()=>{
  document.querySelectorAll(".tab").forEach(x=>x.setAttribute("aria-selected",x===t));
  $("#tab-leads").hidden=t.dataset.tab!=="leads";
  $("#tab-rejected").hidden=t.dataset.tab!=="rejected";
});

async function refreshStatus(){renderStatus(await api("/api/status"));}
async function refreshData(){DATA=await api("/api/data");renderLeads();renderRejected();}

$("#btnPlay").onclick=async()=>{renderStatus(await api("/api/play","POST"));toast("Scanner playing — hourly checks on.");};
$("#btnPause").onclick=async()=>{renderStatus(await api("/api/pause","POST"));toast("Scanner paused.");};
$("#btnCheck").onclick=async()=>{await api("/api/run-check","POST");toast("Check started…");setTimeout(refreshStatus,800);};
$("#btnReport").onclick=async()=>{const r=await api("/api/run-report","POST");toast("Report generated: "+r.report);refreshStatus();};
$("#btnRefresh").onclick=async()=>{await refreshData();await refreshStatus();toast("View refreshed.");};

refreshData();refreshStatus();
setInterval(refreshStatus,5000);  // keep status/led live
</script></body></html>"""


if __name__ == "__main__":
    main()
