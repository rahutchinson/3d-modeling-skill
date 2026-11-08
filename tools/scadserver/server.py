#!/usr/bin/env python3
"""openscad-server — run OpenSCAD CLI jobs for remote `rscad` clients.

A client bundles a project tree plus the openscad argv into a tar.gz and
POSTs it to /api/render with a shared token. The server unpacks it into a
scratch dir, runs the chosen OpenSCAD engine there, and streams back a
tar.gz with result.json (exit code, stdout, stderr, timing) and every
output file. Successful jobs are cached by the client-supplied content key
so re-rendering an unchanged part costs one round trip.

Stdlib only. Configure with ~/.config/openscad-server/config.json (see
DEFAULTS) or --config. Status page at /, JSON at /api/status.

Auth: every render request must carry the token from
~/.config/openscad-server/token (generated on first start). The installer
served at /install.sh takes the token as its argument.
"""
import argparse, collections, html, io, json, os, secrets, shutil, subprocess, sys
import tarfile, tempfile, threading, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULTS = {
    "bind": "0.0.0.0",
    "port": 8790,
    "workers": 4,            # concurrent openscad processes (Manifold is multi-threaded itself)
    "timeout": 1800,         # default per-job wall clock, seconds; the client may change it
    "max_timeout": 7200,
    "default_engine": "nightly",
    "engines": {             # name -> argv prefix; first entry is the binary
        "nightly": ["~/.local/bin/openscad-nightly", "--backend=manifold"],
        "2021":    ["~/.local/bin/openscad"],
    },
    "cache_dir": "~/.cache/openscad-server",
    "cache_max_mb": 2048,
    "max_upload_mb": 256,
    "history": 100,
}

CFG = {}
ENGINES = {}            # name -> {"argv": [...], "version": str}
TOKEN = ""
SEM = None
LOCK = threading.Lock()
STATE = {"started": time.time(), "running": {}, "queued": 0, "done": 0,
         "failed": 0, "cached": 0, "busy_seconds": 0.0}
HISTORY = collections.deque(maxlen=100)


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def load_config(path):
    cfg = json.loads(json.dumps(DEFAULTS))
    if path and os.path.exists(path):
        with open(path) as f:
            user = json.load(f)
        for k, v in user.items():
            cfg[k] = v           # an 'engines' entry replaces the default list entirely
    cfg["cache_dir"] = os.path.expanduser(cfg["cache_dir"])
    return cfg


def load_token(config_path):
    path = os.path.join(os.path.dirname(config_path), "token")
    try:
        with open(path) as f:
            tok = f.read().strip()
        if tok:
            return tok
    except OSError:
        pass
    tok = secrets.token_hex(16)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(tok + "\n")
    os.chmod(path, 0o600)
    log(f"generated a new token in {path}")
    return tok


def probe_engines(cfg):
    found = {}
    for name, argv in cfg["engines"].items():
        argv = [os.path.expanduser(a) for a in argv]
        exe = argv[0]
        if not (os.path.isfile(exe) and os.access(exe, os.X_OK)):
            log(f"engine {name}: {exe} not found, skipping")
            continue
        try:
            p = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60)
            text = (p.stdout + p.stderr).strip()
            ver = text.splitlines()[0] if text else "?"
        except Exception as e:  # noqa
            ver = f"? ({e})"
        found[name] = {"argv": argv, "version": ver}
        log(f"engine {name}: {ver}  [{' '.join(argv)}]")
    if not found:
        sys.exit("no usable OpenSCAD engine; check 'engines' in the config")
    if cfg["default_engine"] not in found:
        cfg["default_engine"] = next(iter(found))
        log(f"default engine -> {cfg['default_engine']}")
    return found


# ---------------------------------------------------------------- cache
def cache_path(key):
    return os.path.join(CFG["cache_dir"], key + ".tar.gz")


def cache_prune():
    limit = CFG["cache_max_mb"] * 1024 * 1024
    try:
        entries = []
        for f in os.listdir(CFG["cache_dir"]):
            p = os.path.join(CFG["cache_dir"], f)
            st = os.stat(p)
            entries.append((st.st_atime, st.st_size, p))
    except FileNotFoundError:
        return
    total = sum(e[1] for e in entries)
    for atime, size, p in sorted(entries):
        if total <= limit:
            break
        try:
            os.remove(p); total -= size
        except OSError:
            pass


# ---------------------------------------------------------------- jobs
def safe_extract(tar, dest):
    """Extract a client tar, refusing paths that escape dest and any links."""
    dest = os.path.realpath(dest)
    for m in tar.getmembers():
        target = os.path.realpath(os.path.join(dest, m.name))
        if not (target == dest or target.startswith(dest + os.sep)):
            raise ValueError(f"bad path in upload: {m.name}")
        if not (m.isfile() or m.isdir()):
            raise ValueError(f"only plain files allowed in upload: {m.name}")
    tar.extractall(dest)


def run_job(body, headers):
    """Return (status, response_bytes, cached) for a POST /api/render."""
    key = headers.get("X-Job-Key")
    engine_name = headers.get("X-Engine") or CFG["default_engine"]
    if engine_name not in ENGINES:
        return 400, json.dumps({"error": f"unknown engine {engine_name!r}; have {sorted(ENGINES)}"}).encode(), False
    engine = ENGINES[engine_name]
    if key:
        key = f"{key}-{engine_name}"
        cp = cache_path(key)
        if os.path.exists(cp):
            with open(cp, "rb") as f:
                data = f.read()
            os.utime(cp, None)
            with LOCK:
                STATE["cached"] += 1
            return 200, data, True

    job_id = uuid.uuid4().hex[:8]
    work = tempfile.mkdtemp(prefix=f"scad-{job_id}-")
    try:
        with tarfile.open(fileobj=io.BytesIO(body), mode="r:gz") as tar:
            safe_extract(tar, work)
        with open(os.path.join(work, "job.json")) as f:
            job = json.load(f)
        src = os.path.join(work, "src")
        out = os.path.join(work, "out")
        os.makedirs(src, exist_ok=True); os.makedirs(out, exist_ok=True)
        cwd = os.path.realpath(os.path.join(src, job.get("cwd", "")))
        if not cwd.startswith(os.path.realpath(src)):
            raise ValueError("cwd escapes src")
        os.makedirs(cwd, exist_ok=True)
        args = [a.replace("@OUT@", out).replace("@SRC@", src) for a in job["args"]]
        for a in args:
            if a.startswith(out + os.sep):
                os.makedirs(os.path.dirname(a), exist_ok=True)
        timeout = float(job.get("timeout") or CFG["timeout"])
        timeout = max(5.0, min(timeout, float(CFG["max_timeout"])))
        argv = engine["argv"] + args
        summary = " ".join(os.path.basename(a) if os.sep in a else a for a in args)[:160]

        t_q = time.time()
        with LOCK:
            STATE["queued"] += 1
        with SEM:
            with LOCK:
                STATE["queued"] -= 1
                STATE["running"][job_id] = {"engine": engine_name, "args": summary, "started": time.time(),
                                            "client": headers.get("X-Client", "?")}
            t0 = time.time()
            timed_out = False
            try:
                p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                                   env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
                rc, so, se = p.returncode, p.stdout, p.stderr
            except subprocess.TimeoutExpired as e:
                timed_out = True
                rc = 124
                so = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
                se = e.stderr.decode(errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
                se += f"\nrscad: server killed openscad after {timeout:.0f}s (timeout)\n"
            secs = time.time() - t0
            with LOCK:
                STATE["running"].pop(job_id, None)
                STATE["done"] += 1
                STATE["busy_seconds"] += secs
                if rc != 0:
                    STATE["failed"] += 1
                HISTORY.appendleft({"id": job_id, "engine": engine_name, "args": summary, "rc": rc,
                                    "seconds": round(secs, 2), "queue_seconds": round(t0 - t_q, 2),
                                    "at": time.time(), "client": headers.get("X-Client", "?")})
        log(f"job {job_id} {engine_name} rc={rc} {secs:.1f}s  {summary}")

        result = {"returncode": rc, "stdout": so, "stderr": se, "seconds": round(secs, 3),
                  "queue_seconds": round(t0 - t_q, 3), "engine": engine_name,
                  "engine_version": engine["version"], "timeout": timed_out,
                  "src_dir": src, "out_dir": out, "job_id": job_id}
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            rj = json.dumps(result).encode()
            ti = tarfile.TarInfo("result.json"); ti.size = len(rj); ti.mtime = int(time.time())
            tar.addfile(ti, io.BytesIO(rj))
            for root, _, files in os.walk(out):
                for fn in files:
                    full = os.path.join(root, fn)
                    tar.add(full, arcname=os.path.join("out", os.path.relpath(full, out)))
        data = buf.getvalue()
        if key and rc == 0 and not timed_out:
            os.makedirs(CFG["cache_dir"], exist_ok=True)
            tmp = cache_path(key) + ".tmp"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, cache_path(key))
            threading.Thread(target=cache_prune, daemon=True).start()
        return 200, data, False
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------- http
def status_json():
    with LOCK:
        cache_bytes = 0
        try:
            cache_bytes = sum(os.path.getsize(os.path.join(CFG["cache_dir"], f)) for f in os.listdir(CFG["cache_dir"]))
        except OSError:
            pass
        return {
            "uptime_seconds": round(time.time() - STATE["started"]),
            "engines": {k: v["version"] for k, v in ENGINES.items()},
            "default_engine": CFG["default_engine"],
            "workers": CFG["workers"],
            "running": [{"id": k, **v, "seconds": round(time.time() - v["started"], 1)} for k, v in STATE["running"].items()],
            "queued": STATE["queued"],
            "done": STATE["done"], "failed": STATE["failed"], "cache_hits": STATE["cached"],
            "busy_seconds": round(STATE["busy_seconds"]),
            "cache_mb": round(cache_bytes / 1048576, 1),
            "recent": list(HISTORY)[:20],
        }


PAGE = """<!doctype html><meta charset=utf-8><title>OpenSCAD server</title>
<meta name=viewport content="width=device-width,initial-scale=1">
<style>body{font:15px/1.45 system-ui,sans-serif;margin:0 auto;max-width:860px;padding:24px 16px;color:#222;background:#fafafa}
h1{font-size:20px;margin:0 0 4px}small{color:#666}table{border-collapse:collapse;width:100%%;margin-top:8px}
td,th{text-align:left;padding:4px 8px;border-bottom:1px solid #e3e3e3;font-size:13px}th{color:#666;font-weight:600}
code,pre{font:12px/1.4 ui-monospace,monospace}pre{background:#f0f0f0;padding:10px;border-radius:6px;overflow:auto}
.ok{color:#2a7}.bad{color:#c33}@media(prefers-color-scheme:dark){body{background:#151515;color:#ddd}pre{background:#222}td,th{border-color:#333}small,th{color:#999}}</style>
<h1>OpenSCAD server</h1><small>%(host)s · up %(up)s · %(workers)d workers · %(done)d jobs (%(failed)d exited non-zero, which includes expected-empty interference checks; %(hits)d cache hits) · %(busy)s busy · cache %(cache)s MB</small>
<h3>Engines</h3><table>%(engines)s</table>
<h3>Running (%(nrun)d) · queued %(queued)d</h3><table><tr><th>id</th><th>engine</th><th>client</th><th>s</th><th>args</th></tr>%(running)s</table>
<h3>Recent</h3><table><tr><th>when</th><th>engine</th><th>client</th><th>rc</th><th>s</th><th>args</th></tr>%(recent)s</table>
<h3>Use it</h3><pre>curl -sf %(base)s/install.sh | sh -s -- TOKEN    # installs ~/.local/bin/rscad pointed here
                                                  # (TOKEN is in ~/.config/openscad-server/token on the server)
OPENSCAD=rscad make                               # any skill project; or symlink openscad -> rscad
rscad --rscad-status                              # what the server is doing
rscad --rscad-engine=2021 -o x.stl x.scad         # pick an engine per call</pre>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = "openscad-server/1.0"

    def log_message(self, fmt, *a):  # quieter: render requests log from run_job
        if not self.path.startswith("/api/render"):
            log(self.address_string(), fmt % a)

    def _send(self, code, body, ctype="application/json", extra=None):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _authed(self):
        return secrets.compare_digest(self.headers.get("X-Token", ""), TOKEN)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/status":
            return self._send(200, json.dumps(status_json(), indent=1))
        if path == "/api/jobs":
            if not self._authed():
                return self._send(401, json.dumps({"error": "bad or missing X-Token"}))
            with LOCK:
                return self._send(200, json.dumps(list(HISTORY), indent=1))
        if path in ("/rscad", "/install.sh"):
            fn = os.path.join(HERE, "rscad" if path == "/rscad" else "install.sh")
            try:
                with open(fn, "rb") as f:
                    data = f.read()
            except OSError:
                return self._send(404, "missing\n", "text/plain")
            if path == "/install.sh":
                base = f"http://{self.headers.get('Host', 'localhost')}"
                data = data.replace(b"@BASE_URL@", base.encode())
            return self._send(200, data, "text/plain; charset=utf-8")
        if path == "/":
            s = status_json()
            base = f"http://{self.headers.get('Host', 'localhost')}"
            eng = "".join(f"<tr><td><code>{html.escape(k)}</code>{' (default)' if k == s['default_engine'] else ''}</td><td>{html.escape(v)}</td></tr>" for k, v in s["engines"].items())
            run = "".join(f"<tr><td>{r['id']}</td><td>{r['engine']}</td><td>{html.escape(str(r['client']))}</td><td>{r['seconds']}</td><td><code>{html.escape(r['args'])}</code></td></tr>" for r in s["running"]) or "<tr><td colspan=5><small>idle</small></td></tr>"
            rec = "".join(f"<tr><td>{time.strftime('%H:%M:%S', time.localtime(r['at']))}</td><td>{r['engine']}</td><td>{html.escape(str(r['client']))}</td><td class={'ok' if r['rc']==0 else 'bad'}>{r['rc']}</td><td>{r['seconds']}</td><td><code>{html.escape(r['args'])}</code></td></tr>" for r in s["recent"]) or "<tr><td colspan=6><small>nothing yet</small></td></tr>"
            up = s["uptime_seconds"]; ups = f"{up//3600}h{(up%3600)//60:02d}m"
            busy = f"{s['busy_seconds']//60}m"
            page = PAGE % {"host": html.escape(os.uname().nodename), "up": ups, "workers": s["workers"], "done": s["done"],
                           "failed": s["failed"], "hits": s["cache_hits"], "busy": busy, "cache": s["cache_mb"],
                           "engines": eng, "nrun": len(s["running"]), "queued": s["queued"], "running": run,
                           "recent": rec, "base": base}
            return self._send(200, page, "text/html; charset=utf-8")
        self._send(404, "not found\n", "text/plain")

    def do_POST(self):
        if self.path.split("?")[0] != "/api/render":
            return self._send(404, "not found\n", "text/plain")
        n = int(self.headers.get("Content-Length") or 0)
        if not self._authed():
            self.rfile.read(min(n, 1 << 20))
            return self._send(401, json.dumps({"error": "bad or missing X-Token"}))
        if n > CFG["max_upload_mb"] * 1024 * 1024:
            return self._send(413, json.dumps({"error": f"upload over {CFG['max_upload_mb']} MB"}))
        body = self.rfile.read(n)
        try:
            code, data, cached = run_job(body, self.headers)
        except Exception as e:  # noqa
            log("job error:", repr(e))
            return self._send(400, json.dumps({"error": str(e)}))
        ctype = "application/gzip" if code == 200 else "application/json"
        self._send(code, data, ctype, {"X-Cached": "1" if cached else "0"})


def main():
    global CFG, ENGINES, SEM, HISTORY, TOKEN
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", default=os.path.expanduser("~/.config/openscad-server/config.json"))
    ap.add_argument("--port", type=int)
    ap.add_argument("--workers", type=int)
    a = ap.parse_args()
    CFG = load_config(a.config)
    if a.port: CFG["port"] = a.port
    if a.workers: CFG["workers"] = a.workers
    TOKEN = load_token(a.config)
    ENGINES = probe_engines(CFG)
    SEM = threading.Semaphore(CFG["workers"])
    HISTORY = collections.deque(maxlen=CFG["history"])
    os.makedirs(CFG["cache_dir"], exist_ok=True)
    srv = ThreadingHTTPServer((CFG["bind"], CFG["port"]), Handler)
    srv.daemon_threads = True
    log(f"openscad-server on http://{os.uname().nodename}:{CFG['port']}  workers={CFG['workers']} default={CFG['default_engine']} config={a.config}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
