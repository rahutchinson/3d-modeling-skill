#!/usr/bin/env python3
"""printlog-server — shared print history for the 3d-modeling skill.

Keeps one SQLite database of what has been printed (and what failed, is
printing, or is planned), plus a catalog of every printable part each
project currently has, so any machine can ask "what's been printed, and
what hasn't?". Clients use the `printlog` CLI served at /printlog.

Stdlib only. Config: ~/.config/printlog/config.json (see DEFAULTS).
Data: ~/.local/share/printlog/prints.db.

Printers: list them in ~/.config/printlog/printers.json (see printers.py
and README) and the server watches them. A job that starts is logged as
`printing` against the project part its file name matches. When it ends,
the entry becomes `printed` (with hours) or `failed` (with where it
stopped). Jobs are keyed by the printer's job id, so restarts don't
duplicate them.

Auth: writes need the token in ~/.config/printlog/token (on first start it
reuses ~/.config/openscad-server/token if that exists, so one secret
covers both services; otherwise one is generated). Reads are open, like
the status page.

API (JSON):
  GET    /api/prints?project=&part=&status=&limit=   history, newest first
  POST   /api/prints                                 {project, part, status, ...}   (token)
  PATCH  /api/prints/<id>                            fields to change                (token)
  DELETE /api/prints/<id>                                                            (token)
  GET    /api/parts?project=&state=                  catalog + derived print state
  POST   /api/parts                                  {project, root, parts:[...]}    (token)
  GET    /api/printers                               live printer state
  GET    /api/status                                 counts
"""
import argparse, html, json, os, re, secrets, sqlite3, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import printers as printer_mod  # noqa: E402
DEFAULTS = {"bind": "0.0.0.0", "port": 8791, "db": "~/.local/share/printlog/prints.db"}
STATUSES = ("planned", "printing", "printed", "failed")
FIELDS = ("project", "part", "status", "file", "sha256", "qty", "material", "printer", "hours",
          "verdict", "notes", "params", "printed_at", "client", "job", "started_at", "ended_at")

CFG, TOKEN, DB, LOCK = {}, "", None, threading.RLock()
MONITORS = []
JOB_LOCK = threading.Lock()
STARTED = time.time()

SCHEMA = """
CREATE TABLE IF NOT EXISTS prints(
  id INTEGER PRIMARY KEY,
  project TEXT NOT NULL, part TEXT NOT NULL,
  status TEXT NOT NULL,
  file TEXT, sha256 TEXT,
  qty INTEGER NOT NULL DEFAULT 1,
  material TEXT, printer TEXT, hours REAL,
  verdict TEXT, notes TEXT, params TEXT,
  printed_at TEXT,
  client TEXT,
  created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS prints_part ON prints(project, part);
CREATE TABLE IF NOT EXISTS parts(
  project TEXT NOT NULL, part TEXT NOT NULL,
  path TEXT, sha256 TEXT, size INTEGER, mtime REAL,
  present INTEGER NOT NULL DEFAULT 1,
  seen_at REAL NOT NULL,
  PRIMARY KEY(project, part));
CREATE TABLE IF NOT EXISTS projects(
  project TEXT PRIMARY KEY, root TEXT, client TEXT, synced_at REAL);
"""
MIGRATIONS = {"prints": {"job": "TEXT", "started_at": "REAL", "ended_at": "REAL"}}


def migrate(db):
    for table, cols in MIGRATIONS.items():
        have = {r[1] for r in db.execute(f"PRAGMA table_info({table})")}
        for col, typ in cols.items():
            if col not in have:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
    db.execute("CREATE INDEX IF NOT EXISTS prints_job ON prints(printer, job)")
    db.commit()


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def load_token(cfg_dir):
    path = os.path.join(cfg_dir, "token")
    for p in (path, os.path.expanduser("~/.config/openscad-server/token")):
        try:
            with open(p) as f:
                tok = f.read().strip()
            if tok:
                if p != path:
                    log(f"reusing the openscad-server token from {p}")
                    _write_token(path, tok)
                return tok
        except OSError:
            pass
    tok = secrets.token_hex(16)
    _write_token(path, tok)
    log(f"generated a new token in {path}")
    return tok


def _write_token(path, tok):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(tok + "\n")
    os.chmod(path, 0o600)


def q(sql, args=(), one=False):
    with LOCK:
        cur = DB.execute(sql, args)
        rows = [dict(r) for r in cur.fetchall()]
        DB.commit()
        if one:
            return rows[0] if rows else None
        return rows


def today():
    return time.strftime("%Y-%m-%d")


# ---------------------------------------------------------------- prints
def clean_print(d, partial=False):
    out = {}
    for k in FIELDS:
        if k in d:
            v = d[k]
            if isinstance(v, (dict, list)):
                v = json.dumps(v)
            out[k] = v
    if not partial:
        for k in ("project", "part"):
            if not out.get(k):
                raise ValueError(f"{k} is required")
        out.setdefault("status", "printed")
        out.setdefault("qty", 1)
        if out["status"] in ("printed", "failed") and not out.get("printed_at"):
            out["printed_at"] = today()
    if "status" in out and out["status"] not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    if "qty" in out:
        out["qty"] = int(out["qty"])
    if out.get("hours") not in (None, ""):
        out["hours"] = float(out["hours"])
    return out


def add_print(d):
    rec = clean_print(d)
    now = time.time()
    rec["created_at"] = rec["updated_at"] = now
    cols = ",".join(rec)
    with LOCK:
        cur = DB.execute(f"INSERT INTO prints({cols}) VALUES({','.join('?' * len(rec))})", list(rec.values()))
        DB.commit()
        rid = cur.lastrowid
    log(f"print #{rid} {rec['project']}/{rec['part']} {rec['status']}")
    return get_print(rid)


def get_print(rid):
    return q("SELECT * FROM prints WHERE id=?", (rid,), one=True)


def update_print(rid, d):
    rec = clean_print(d, partial=True)
    if not rec:
        raise ValueError("nothing to change")
    if rec.get("status") in ("printed", "failed") and "printed_at" not in rec:
        cur = get_print(rid)
        if cur and not cur.get("printed_at"):
            rec["printed_at"] = today()
    rec["updated_at"] = time.time()
    sets = ",".join(f"{k}=?" for k in rec)
    q(f"UPDATE prints SET {sets} WHERE id=?", list(rec.values()) + [rid])
    return get_print(rid)


def list_prints(project=None, part=None, status=None, limit=200):
    where, args = [], []
    for col, val in (("project", project), ("part", part), ("status", status)):
        if val:
            where.append(f"{col}=?"); args.append(val)
    sql = "SELECT * FROM prints" + (" WHERE " + " AND ".join(where) if where else "")
    sql += " ORDER BY COALESCE(printed_at, '') DESC, created_at DESC LIMIT ?"
    return q(sql, args + [int(limit)])


# ---------------------------------------------------------------- parts
def sync_parts(d, client):
    project = d.get("project")
    if not project:
        raise ValueError("project is required")
    now = time.time()
    names = []
    with LOCK:
        for p in d.get("parts", []):
            names.append(p["part"])
            DB.execute("""INSERT INTO parts(project,part,path,sha256,size,mtime,present,seen_at)
                          VALUES(?,?,?,?,?,?,1,?)
                          ON CONFLICT(project,part) DO UPDATE SET path=excluded.path, sha256=excluded.sha256,
                          size=excluded.size, mtime=excluded.mtime, present=1, seen_at=excluded.seen_at""",
                       (project, p["part"], p.get("path"), p.get("sha256"), p.get("size"), p.get("mtime"), now))
        marks = ",".join("?" * len(names))
        DB.execute(f"UPDATE parts SET present=0 WHERE project=? AND part NOT IN ({marks})" if names
                   else "UPDATE parts SET present=0 WHERE project=?", [project] + names)
        DB.execute("""INSERT INTO projects(project,root,client,synced_at) VALUES(?,?,?,?)
                      ON CONFLICT(project) DO UPDATE SET root=excluded.root, client=excluded.client,
                      synced_at=excluded.synced_at""", (project, d.get("root"), client, now))
        DB.commit()
    return part_states(project)


def part_states(project=None, state=None, include_gone=False):
    """Every catalogued part (and every part with history) with its print state.

    state: never     no history at all
           planned / printing   latest entry says so
           printed   latest entry printed, same STL as now (or no hash to compare)
           changed   latest entry printed, but the STL has changed since
           failed    latest entry failed
    """
    args = []
    cat_sql = "SELECT * FROM parts" + (" WHERE project=?" if project else "")
    if project:
        args.append(project)
    cat = {(r["project"], r["part"]): r for r in q(cat_sql, args)}
    hist_sql = "SELECT * FROM prints" + (" WHERE project=?" if project else "")
    hist_sql += " ORDER BY created_at"
    by_part = {}
    for r in q(hist_sql, [project] if project else []):
        by_part.setdefault((r["project"], r["part"]), []).append(r)
    out = []
    for key in sorted(set(cat) | set(by_part)):
        c = cat.get(key) or {}
        if c and not c.get("present") and not include_gone and key not in by_part:
            continue
        h = by_part.get(key, [])
        latest = h[-1] if h else None
        printed = [r for r in h if r["status"] == "printed"]
        last_ok = printed[-1] if printed else None
        if not latest:
            st = "never"
        elif latest["status"] == "printed":
            st = "changed" if (c.get("sha256") and latest.get("sha256") and c["sha256"] != latest["sha256"]) else "printed"
        else:
            st = latest["status"]
        out.append({
            "project": key[0], "part": key[1], "state": st,
            "in_catalog": bool(c.get("present")) if c else False,
            "path": c.get("path"), "sha256": c.get("sha256"),
            "times_printed": sum(r["qty"] or 1 for r in printed),
            "last_printed_at": last_ok["printed_at"] if last_ok else None,
            "last_verdict": (last_ok or {}).get("verdict"),
            "latest": latest,
        })
    if state:
        wanted = set(state.split(","))
        out = [p for p in out if p["state"] in wanted]
    return out


# ---------------------------------------------------------------- printers
def strip_job_name(name):
    base = os.path.basename(name or "")
    for _ in range(3):
        root, ext = os.path.splitext(base)
        if ext.lower() in (".gcode", ".3mf", ".bgcode", ".g", ".gco"):
            base = root
    return base


def match_job(file):
    """File name on the printer -> (project, part, sha, note).

    A part matches when the job name is the part name, or starts with it
    and continues with a separator (slicers append _PETG_52m47s, _plate_1
    ...). The longest matching name wins. If several projects have it, the
    most recently rendered STL wins and the note names the rest."""
    name = strip_job_name(file)
    low = name.lower()
    best, best_len = [], 0
    for r in q("SELECT * FROM parts WHERE present=1"):
        part = r["part"].lower()
        if low == part or (low.startswith(part) and low[len(part)] in "_- .("):
            if len(part) > best_len:
                best, best_len = [r], len(part)
            elif len(part) == best_len:
                best.append(r)
    if not best:
        projects = {r["project"].lower(): r["project"] for r in q("SELECT project FROM projects")}
        for proj_low, proj in projects.items():
            if low == proj_low or (low.startswith(proj_low) and low[len(proj_low)] in "_- .("):
                return proj, name, None, f"auto: job {file!r} named after the project, not a part"
        return "unmatched", name, None, f"auto: job {file!r} matched no part; fix with printlog edit"
    best.sort(key=lambda r: r.get("mtime") or 0, reverse=True)
    top = best[0]
    note = f"auto: {file}"
    if len(best) > 1:
        note += "; also matches " + ", ".join(f"{r['project']}/{r['part']}" for r in best[1:])
    return top["project"], top["part"], top.get("sha256"), note


def on_printer(snap):
    st, job, name = snap.get("state"), snap.get("job"), snap["name"]
    if not job or st not in ("printing", "paused", "finished", "failed"):
        return
    with JOB_LOCK:
        rec = q("SELECT * FROM prints WHERE printer=? AND job=? ORDER BY id DESC LIMIT 1", (name, job), one=True)
        now = time.time()
        if rec is None:
            if st in ("printing", "paused"):
                # a new job supersedes any auto entry this printer left at 'printing'
                for old in q("SELECT * FROM prints WHERE printer=? AND status='printing' AND job IS NOT NULL", (name,)):
                    update_print(old["id"], {"status": "failed", "notes": (old.get("notes") or "") +
                                             "; printer started another job before this one reported an end — check"})
            project, part, sha, note = match_job(snap.get("file"))
            rec = add_print({"project": project, "part": part, "printer": name, "job": job, "sha256": sha,
                             "file": snap.get("file"), "material": snap.get("material"), "notes": note,
                             "started_at": snap.get("started_at") or now, "client": f"printer:{name}",
                             **({"hours": round(snap["elapsed_s"] / 3600, 2)} if st != "printing" and snap.get("elapsed_s") else {}),
                             "status": "printing" if st in ("printing", "paused") else
                                       ("printed" if st == "finished" else "failed"),
                             **({} if st in ("printing", "paused") else {"ended_at": now})})
            if st in ("printing", "paused"):
                return
            if st == "finished" and not snap.get("started_at"):
                return
        if rec["status"] != "printing" and rec.get("ended_at"):
            return          # already closed (or the user changed it): leave it alone
        if rec["status"] == "printing" and snap.get("material") and snap["material"] != rec.get("material"):
            # Bambu reports the spool piecemeal; the first reading at job start can be a default
            rec = update_print(rec["id"], {"material": snap["material"]})
        if st in ("finished", "failed") and rec["status"] in ("printing", "printed", "failed"):
            started = rec.get("started_at") or snap.get("started_at")
            hours = round((now - started) / 3600, 2) if started else None
            if snap.get("elapsed_s"):
                hours = round(snap["elapsed_s"] / 3600, 2)
            upd = {"status": "printed" if st == "finished" else "failed", "ended_at": now,
                   "printed_at": time.strftime("%Y-%m-%d", time.localtime(now))}
            if hours is not None and rec.get("hours") is None:
                upd["hours"] = hours
            if st == "failed":
                where = f"{'cancelled' if snap.get('ended') == 'cancelled' else 'stopped'} at {snap.get('progress')}%"
                if snap.get("layer") is not None:
                    where += f", layer {snap.get('layer')}/{snap.get('total_layers')}"
                if snap.get("error"):
                    where += f", error {snap.get('error')}"
                upd["notes"] = (rec.get("notes") or "") + "; " + where
            if rec["status"] == "printing":
                log(f"printer {name}: {rec['project']}/{rec['part']} -> {upd['status']}")
                update_print(rec["id"], upd)


def printers_json():
    out = []
    for m in MONITORS:
        s = m.snapshot()
        if s.get("job"):
            r = q("SELECT id, project, part, status FROM prints WHERE printer=? AND job=? ORDER BY id DESC LIMIT 1",
                  (s["name"], s["job"]), one=True)
            s["print"] = r
        out.append(s)
    return out


def load_printers(cfg_dir):
    path = os.path.join(cfg_dir, "printers.json")
    try:
        with open(path) as f:
            confs = json.load(f)
    except FileNotFoundError:
        return []
    if os.stat(path).st_mode & 0o077:
        os.chmod(path, 0o600)       # holds LAN access codes
    return confs


def status_json():
    states = {}
    for p in part_states():
        if p["in_catalog"]:
            states[p["state"]] = states.get(p["state"], 0) + 1
    tot = q("SELECT status, COUNT(*) n FROM prints GROUP BY status")
    return {"uptime_seconds": round(time.time() - STARTED), "db": CFG["db"],
            "prints": {r["status"]: r["n"] for r in tot},
            "catalog_states": states,
            "printers": {m.conf["name"]: m.snapshot().get("state") for m in MONITORS},
            "projects": q("SELECT * FROM projects ORDER BY project")}


# ---------------------------------------------------------------- page
STATE_CLASS = {"never": "never", "changed": "warn", "failed": "bad", "printed": "ok", "planned": "plan", "printing": "plan"}
PAGE = """<!doctype html><meta charset=utf-8><title>Print history</title>
<meta name=viewport content="width=device-width,initial-scale=1">
<style>
:root{--bg:#fafafa;--fg:#222;--mut:#666;--line:#e3e3e3;--ok:#2a7;--bad:#c33;--warn:#b7791f;--plan:#3a6fd8;--pre:#f0f0f0}
@media(prefers-color-scheme:dark){:root{--bg:#151515;--fg:#ddd;--mut:#999;--line:#333;--pre:#222}}
body{font:15px/1.45 system-ui,sans-serif;margin:0 auto;max-width:960px;padding:24px 16px;color:var(--fg);background:var(--bg)}
h1{font-size:20px;margin:0 0 4px}h2{font-size:16px;margin:24px 0 4px}small,.mut{color:var(--mut)}
table{border-collapse:collapse;width:100%%}td,th{text-align:left;padding:4px 8px;border-bottom:1px solid var(--line);font-size:13px;vertical-align:top}
th{color:var(--mut);font-weight:600}code,pre{font:12px/1.4 ui-monospace,monospace}pre{background:var(--pre);padding:10px;border-radius:6px;overflow:auto}
.st{font-weight:600}.ok{color:var(--ok)}.bad{color:var(--bad)}.warn{color:var(--warn)}.plan{color:var(--plan)}.never{color:var(--mut)}
.wrap{overflow-x:auto}
</style>
<h1>Print history</h1><small>%(host)s · %(summary)s</small>
%(printers)s
%(projects)s
<h2>Recent prints</h2><div class=wrap><table><tr><th>#</th><th>date</th><th>project / part</th><th>status</th><th>qty</th><th>material</th><th>verdict / notes</th></tr>%(recent)s</table></div>
<h2>Use it</h2><pre>curl -sf %(base)s/install.sh | sh -s -- TOKEN   # installs ~/.local/bin/printlog (TOKEN: ~/.config/printlog/token here)
printlog status                  # in a project: sync its stl/ catalog, show what's printed and what isn't
printlog todo                    # every project: never printed / changed since printed / failed
printlog log pinion --verdict "spins freely" --material PETG
printlog list --project cabinet-lock</pre>
"""


def esc(v):
    return html.escape("" if v is None else str(v))


def fmt_secs(s):
    if s in (None, ""):
        return ""
    s = int(s)
    return f"{s // 3600}h{(s % 3600) // 60:02d}m"


def render_printers():
    ps = printers_json()
    if not ps:
        return ""
    cls = {"printing": "plan", "paused": "warn", "finished": "ok", "failed": "bad", "offline": "never", "idle": "never"}
    rows = []
    for p in ps:
        job = ""
        if p.get("file") and p["state"] not in ("idle", "offline"):
            pr = p.get("print") or {}
            job = esc(p["file"]) + (f"<br><small>#{pr['id']} {esc(pr['project'])}/{esc(pr['part'])}</small>" if pr else "")
        prog = ""
        if p["state"] in ("printing", "paused"):
            prog = f"{p.get('progress') or 0}%"
            if p.get("layer") is not None:
                prog += f" · layer {p['layer']}/{p.get('total_layers')}"
            if p.get("remaining_s"):
                prog += f" · {fmt_secs(p['remaining_s'])} left"
        temps = ""
        if p.get("online") and p.get("nozzle") is not None:
            temps = f"{float(p['nozzle']):.0f}° / {float(p['bed'] or 0):.0f}°"
        rows.append(f"<tr><td><b>{esc(p['name'])}</b><br><small>{esc(p.get('model') or p['type'])} · {esc(p.get('host'))}</small></td>"
                    f"<td class='st {cls.get(p['state'], '')}'>{esc(p['state'])}</td><td>{job}</td><td>{esc(prog)}</td>"
                    f"<td>{esc(p.get('material') or '')}</td><td>{esc(temps)}</td></tr>")
    return ("<h2>Printers</h2><div class=wrap><table><tr><th>printer</th><th>state</th><th>job</th><th>progress</th>"
            "<th>material</th><th>nozzle / bed</th></tr>" + "".join(rows) + "</table></div>")


def render_page(host):
    parts = part_states()
    by_proj = {}
    for p in parts:
        by_proj.setdefault(p["project"], []).append(p)
    blocks = []
    order = {"failed": 0, "changed": 1, "never": 2, "planned": 3, "printing": 3, "printed": 4}
    for proj in sorted(by_proj):
        rows = sorted(by_proj[proj], key=lambda p: (order.get(p["state"], 9), p["part"]))
        counts = {}
        for p in rows:
            counts[p["state"]] = counts.get(p["state"], 0) + 1
        summ = " · ".join(f"{n} {s}" for s, n in sorted(counts.items(), key=lambda kv: order.get(kv[0], 9)))
        trs = "".join(
            f"<tr><td><code>{esc(p['part'])}</code>{'' if p['in_catalog'] else ' <small>(not in stl/)</small>'}</td>"
            f"<td class='st {STATE_CLASS.get(p['state'], '')}'>{esc(p['state'])}</td>"
            f"<td>{esc(p['times_printed'] or '')}</td><td>{esc(p['last_printed_at'] or '')}</td>"
            f"<td>{esc(p['last_verdict'] or '')}</td></tr>" for p in rows)
        blocks.append(f"<h2>{esc(proj)} <small>{esc(summ)}</small></h2><div class=wrap><table>"
                      f"<tr><th>part</th><th>state</th><th>printed</th><th>last</th><th>verdict</th></tr>{trs}</table></div>")
    recent = list_prints(limit=30)
    rec = "".join(
        f"<tr><td>{r['id']}</td><td>{esc(r['printed_at'] or '')}</td><td><code>{esc(r['project'])}/{esc(r['part'])}</code></td>"
        f"<td class='st {STATE_CLASS.get(r['status'], '')}'>{esc(r['status'])}</td><td>{r['qty']}</td><td>{esc(r['material'] or '')}</td>"
        f"<td>{esc(r['verdict'] or '')}{'<br><small>' + esc(r['notes']) + '</small>' if r['notes'] else ''}"
        f"{'<br><small>' + esc(r['printer']) + (' · ' + str(r['hours']) + ' h' if r['hours'] else '') + '</small>' if r['printer'] else ''}</td></tr>"
        for r in recent) or "<tr><td colspan=7><small>nothing logged yet</small></td></tr>"
    s = status_json()
    summary = ", ".join(f"{n} {k}" for k, n in s["prints"].items()) or "no prints logged"
    summary += f" · {len(s['projects'])} projects synced"
    return PAGE % {"host": esc(os.uname().nodename), "summary": esc(summary), "printers": render_printers(),
                   "projects": "".join(blocks) or "<p class=mut>No projects synced yet — run <code>printlog status</code> in one.</p>",
                   "recent": rec, "base": esc(f"http://{host}")}


# ---------------------------------------------------------------- http
class Handler(BaseHTTPRequestHandler):
    server_version = "printlog/1.0"

    def log_message(self, fmt, *a):
        if self.command != "GET" or not self.path.startswith("/api/"):
            log(self.address_string(), fmt % a)

    def _send(self, code, body, ctype="application/json"):
        if not isinstance(body, (bytes, str)):
            body = json.dumps(body, indent=1)
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authed(self):
        return secrets.compare_digest(self.headers.get("X-Token", ""), TOKEN)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 16 * 1024 * 1024:
            raise ValueError("body too large")
        return json.loads(self.rfile.read(n) or b"{}")

    def _route(self):
        u = urlparse(self.path)
        return u.path.rstrip("/") or "/", {k: v[-1] for k, v in parse_qs(u.query).items()}

    def do_GET(self):
        path, qs = self._route()
        host = self.headers.get("Host", "localhost")
        if path == "/":
            return self._send(200, render_page(host), "text/html; charset=utf-8")
        if path == "/api/status":
            return self._send(200, status_json())
        if path == "/api/printers":
            return self._send(200, printers_json())
        if path == "/api/prints":
            return self._send(200, list_prints(qs.get("project"), qs.get("part"), qs.get("status"), qs.get("limit", 200)))
        if path.startswith("/api/prints/"):
            r = get_print(path.rsplit("/", 1)[1])
            return self._send(200 if r else 404, r or {"error": "no such print"})
        if path == "/api/parts":
            return self._send(200, part_states(qs.get("project"), qs.get("state"), qs.get("gone") == "1"))
        if path in ("/printlog", "/install.sh"):
            fn = os.path.join(HERE, "printlog" if path == "/printlog" else "install.sh")
            try:
                with open(fn, "rb") as f:
                    data = f.read()
            except OSError:
                return self._send(404, "missing\n", "text/plain")
            data = data.replace(b"@BASE_URL@", f"http://{host}".encode())
            return self._send(200, data, "text/plain; charset=utf-8")
        self._send(404, {"error": "not found"})

    def _write(self, fn):
        if not self._authed():
            return self._send(401, {"error": "bad or missing X-Token"})
        try:
            code, body = fn()
        except (ValueError, KeyError, json.JSONDecodeError, sqlite3.Error) as e:
            return self._send(400, {"error": str(e)})
        self._send(code, body)

    def do_POST(self):
        path, _ = self._route()
        client = self.headers.get("X-Client", self.address_string())
        if path == "/api/prints":
            return self._write(lambda: (201, add_print({"client": client, **self._body()})))
        if path == "/api/parts":
            return self._write(lambda: (200, sync_parts(self._body(), client)))
        self._send(404, {"error": "not found"})

    def do_PATCH(self):
        path, _ = self._route()
        if path.startswith("/api/prints/"):
            rid = path.rsplit("/", 1)[1]
            def go():
                if not get_print(rid):
                    return 404, {"error": "no such print"}
                return 200, update_print(rid, self._body())
            return self._write(go)
        self._send(404, {"error": "not found"})

    def do_DELETE(self):
        path, _ = self._route()
        if path.startswith("/api/prints/"):
            rid = path.rsplit("/", 1)[1]
            def go():
                r = get_print(rid)
                if not r:
                    return 404, {"error": "no such print"}
                q("DELETE FROM prints WHERE id=?", (rid,))
                log(f"deleted print #{rid}")
                return 200, r
            return self._write(go)
        self._send(404, {"error": "not found"})


def main():
    global CFG, TOKEN, DB
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", default=os.path.expanduser("~/.config/printlog/config.json"))
    ap.add_argument("--port", type=int)
    ap.add_argument("--db")
    a = ap.parse_args()
    CFG = dict(DEFAULTS)
    if os.path.exists(a.config):
        with open(a.config) as f:
            CFG.update(json.load(f))
    if a.port: CFG["port"] = a.port
    if a.db: CFG["db"] = a.db
    CFG["db"] = os.path.expanduser(CFG["db"])
    TOKEN = load_token(os.path.dirname(a.config))
    os.makedirs(os.path.dirname(CFG["db"]), exist_ok=True)
    DB = sqlite3.connect(CFG["db"], check_same_thread=False)
    DB.row_factory = sqlite3.Row
    DB.executescript(SCHEMA)
    DB.execute("PRAGMA journal_mode=WAL")
    migrate(DB)
    MONITORS.extend(printer_mod.start_all(load_printers(os.path.dirname(a.config)), on_printer, log))
    srv = ThreadingHTTPServer((CFG["bind"], CFG["port"]), Handler)
    srv.daemon_threads = True
    log(f"printlog on http://{os.uname().nodename}:{CFG['port']}  db={CFG['db']}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
