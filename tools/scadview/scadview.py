#!/usr/bin/env python3
"""scadview - local OpenSCAD live viewer. Stdlib only.

Run it from an OpenSCAD project root that has a scadview.json:

    python3 /path/to/scadview.py            # serves on the port in scadview.json
    python3 /path/to/scadview.py --port 8770

scadview.json:
    {
      "port": 8765,
      "params_file": "params.scad",
      "targets": [
        {"name": "tray", "file": "parts/tray.scad"},
        {"name": "lid",  "file": "parts/lid.scad", "defines": ["PART=\\"lid\\""], "slow": "~7 s"}
      ],
      "params": [
        {"name": "lid_clear", "min": 0.1, "max": 1.0, "step": 0.05,
         "tag": "UNVERIFIED", "note": "lid vs tray; the gauge decides"}
      ],
      "probe": ["outer_w", "outer_d", "outer_h"]
    }

targets  - what the Parts list offers. `defines` are extra -D flags; `slow`
           (a string like "~20 s", or true) means "never auto-render, show a
           button instead".
params   - sliders. Only these names are ever passed as -D overrides, and
           every value is coerced to float, so a stray LAN request can't
           inject a flag. A missing `default` is read from params_file.
probe    - variables (usually derived values) from params_file to show in
           the "derived values" panel with their delta from the defaults.
           Answers "what does this slider actually DO" in ~10 ms, which
           matters because most clearances are invisible at any zoom that
           keeps the part in frame.
"""
import argparse, hashlib, http.server, json, os, queue, re, socket, uuid
import subprocess, sys, threading, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "web")
OPENSCAD = os.environ.get("OPENSCAD", "openscad")

REPO = None      # set in main()
CACHE = None
CONFIG_PATH = None

# ---------------------------------------------------------------- config
_cfg = {"mtime": None, "data": None}
_cfg_lock = threading.Lock()

def cfg():
    """scadview.json, re-read whenever its mtime changes so adding a target
    or a slider does not need a server restart (reload the page)."""
    with _cfg_lock:
        try:
            m = os.stat(CONFIG_PATH).st_mtime_ns
        except OSError:
            if _cfg["data"] is None:
                sys.exit(f"scadview: no config at {CONFIG_PATH}")
            return _cfg["data"]
        if m != _cfg["mtime"]:
            with open(CONFIG_PATH) as f:
                raw = json.load(f)
            _cfg["data"] = normalize(raw)
            _cfg["mtime"] = m
        return _cfg["data"]

def normalize(raw):
    targets = []
    for t in raw.get("targets", []):
        slow = t.get("slow")
        if slow is True:
            slow = "slow"
        targets.append({"name": t["name"], "file": t["file"],
                        "defines": list(t.get("defines", [])), "slow": slow or None})
    params = []
    for p in raw.get("params", []):
        params.append({"name": p["name"], "min": p["min"], "max": p["max"],
                       "step": p.get("step", 0.1), "default": p.get("default"),
                       "tag": p.get("tag", ""), "note": p.get("note", "")})
    data = {
        "port": int(raw.get("port", 8765)),
        "params_file": raw.get("params_file", "params.scad"),
        "targets": targets,
        "by_name": {t["name"]: t for t in targets},
        "params": params,
        "whitelist": {p["name"] for p in params},
        "probe": list(raw.get("probe", [])),
    }
    fill_defaults(data)
    return data

def fill_defaults(data):
    """Slider defaults come from params.scad itself, so a slider never
    silently disagrees with the file it is exploring. A default given in
    the config is kept but warned about if the file says otherwise."""
    names = [p["name"] for p in data["params"]]
    if not names:
        return
    r = probe({}, names, data)
    vals = r.get("values", {}) if r.get("ok") else {}
    for p in data["params"]:
        v = vals.get(p["name"])
        if p["default"] is None:
            if v is None:
                print(f"scadview: param {p['name']} has no default and is not in "
                      f"{data['params_file']}; using min", file=sys.stderr)
                p["default"] = p["min"]
            else:
                p["default"] = v
        elif v is not None and abs(v - p["default"]) > 1e-9:
            print(f"scadview: param {p['name']} default {p['default']} disagrees "
                  f"with {data['params_file']} ({v}); the file wins", file=sys.stderr)
            p["default"] = v

# ---------------------------------------------------------------- sources
def scad_files():
    out = []
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in (".git", "stl", "viz", ".scadview-cache")]
        for f in files:
            if f.endswith(".scad"):
                out.append(os.path.join(root, f))
    return sorted(out)

def signature():
    h = hashlib.sha1()
    for p in scad_files():
        h.update(p.encode()); h.update(str(os.stat(p).st_mtime_ns).encode())
    return h.hexdigest()[:12]

def parse_params(q, data):
    """Pull whitelisted -D overrides out of repeated ?p=key=value query args.
    Anything not whitelisted, or that doesn't parse as a float, is dropped
    rather than rejected: a stale query string degrades to defaults."""
    out = {}
    for raw in q.get("p", []):
        k, sep, v = raw.partition("=")
        if not sep or k not in data["whitelist"]:
            continue
        try:
            out[k] = float(v)
        except ValueError:
            continue
    return out

def quality_flags(quality):
    # $preview does NOT flip a `$fa = $preview ? 12 : 2` ternary when set
    # with -D on OpenSCAD 2021.01, so override $fa/$fs directly.
    if quality == "draft":
        return ["-D", "$fa=8", "-D", "$fs=1.2"]
    return []

# ---------------------------------------------------------------- render
LOCKS = {}
LOCKS_GUARD = threading.Lock()
LAST = {}   # (name, sig, phash) -> record

def render(name, params, quality, data):
    tgt = data["by_name"][name]
    # Cache key is two parts: sig (source mtimes) and phash (params +
    # quality). Keeping them separate lets the stale sweep purge only files
    # from a PRIOR signature while every slider/quality variant of the
    # current source survives, so revisiting a slider value hits the cache.
    sig = signature()
    phash = hashlib.sha1((repr(sorted(params.items())) + quality).encode()).hexdigest()[:12]
    cache_key = (name, sig, phash)
    with LOCKS_GUARD:
        lock = LOCKS.setdefault(cache_key, threading.Lock())
    with lock:
        prev = LAST.get(cache_key)
        if prev and os.path.exists(prev["path"]):
            return prev
        os.makedirs(CACHE, exist_ok=True)
        out = os.path.join(CACHE, f"{name}.{sig}.{phash}.stl")
        argv = [OPENSCAD, "--export-format", "binstl"]
        for d in tgt["defines"]:
            argv += ["-D", d]
        for k, v in sorted(params.items()):
            argv += ["-D", f"{k}={v}"]
        argv += quality_flags(quality)
        argv += ["-o", out, tgt["file"]]
        t0 = time.time()
        p = subprocess.run(argv, cwd=REPO, capture_output=True, text=True)
        ms = int((time.time() - t0) * 1000)
        err = p.stderr
        echo = [l[6:] for l in err.splitlines() if l.startswith("ECHO: ")]
        bad = [l for l in err.splitlines() if l.startswith(("ERROR", "WARNING", "TRACE"))]
        ok = p.returncode == 0 and os.path.exists(out)
        rec = {"key": f"{sig}.{phash}", "ok": ok, "ms": ms, "echo": echo,
               "error": "\n".join(bad) if bad else ("exit %d" % p.returncode if not ok else ""),
               "path": out, "name": name}
        LAST[cache_key] = rec
        stale_prefix = f"{name}."
        keep_prefix = f"{name}.{sig}."
        for f in os.listdir(CACHE):
            if f.startswith(stale_prefix) and f.endswith(".stl") and not f.startswith(keep_prefix):
                try: os.remove(os.path.join(CACHE, f))
                except OSError: pass
        return rec

# ---------------------------------------------------------------- probe
PROBE_LINE = re.compile(r'"(\w+)",\s*(-?[0-9.eE+-]+)\]')

def probe(params, names, data):
    """Evaluate params_file with the given overrides and read back the
    named variables, with no geometry evaluated (~10 ms)."""
    if not names:
        return {"ok": True, "values": {}}
    os.makedirs(CACHE, exist_ok=True)
    tag = uuid.uuid4().hex[:8]
    scad = os.path.join(CACHE, f"probe-{tag}.scad")
    tmp = os.path.join(CACHE, f"probe-{tag}.echo")
    inc = os.path.relpath(os.path.join(REPO, data["params_file"]), CACHE).replace(os.sep, "/")
    pairs = ",".join(f'["{n}",{n}]' for n in names)
    with open(scad, "w") as f:
        f.write(f"include <{inc}>\n")
        f.write(f'echo(str("PROBE ",[{pairs}]));\n')
    argv = [OPENSCAD]
    for k, v in sorted(params.items()):
        argv += ["-D", f"{k}={v}"]
    argv += ["-o", tmp, os.path.relpath(scad, REPO)]
    try:
        subprocess.run(argv, cwd=REPO, capture_output=True, text=True)
        # Exit code is not trustworthy: on an assert failure the .echo path
        # still exits 0 and writes "ERROR: Assertion ..." INTO the output
        # file instead of stderr, so read the file either way.
        if not os.path.exists(tmp):
            return {"ok": False, "error": "openscad produced no output"}
        with open(tmp) as f:
            text = f.read()
        err_line = next((l for l in text.splitlines() if l.startswith("ERROR:")), None)
        if err_line:
            return {"ok": False, "error": err_line}
        vals = {m.group(1): float(m.group(2)) for m in PROBE_LINE.finditer(text)}
        if not vals:
            return {"ok": False, "error": "no PROBE line in openscad output"}
        return {"ok": True, "values": vals}
    finally:
        for p in (scad, tmp):
            try: os.remove(p)
            except OSError: pass

# ---------------------------------------------------------------- watch / http
WATCHERS = []
def watch_loop():
    last = signature()
    while True:
        time.sleep(0.4)
        try: cur = signature()
        except OSError: continue
        if cur != last:
            last = cur
            for q in list(WATCHERS):
                q.put(cur)

class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass

    def send(self, code, body, ctype, extra=()):
        if isinstance(body, str): body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in extra: self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        data = cfg()
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        path = u.path
        if path == "/":
            path = "/index.html"
        if path == "/api/targets":
            return self.send(200, json.dumps([{"name": t["name"], "slow": t["slow"]}
                                              for t in data["targets"]]), "application/json")
        if path == "/api/params":
            return self.send(200, json.dumps(data["params"]), "application/json")
        if path in ("/api/render", "/api/stl"):
            name = q.get("t", [""])[0]
            if name not in data["by_name"]: return self.send(404, "no such target", "text/plain")
            quality = q.get("q", ["fine"])[0]
            if quality not in ("draft", "fine"): quality = "fine"
            r = render(name, parse_params(q, data), quality, data)
            if path == "/api/render":
                r = dict(r); r.pop("path")
                return self.send(200, json.dumps(r), "application/json")
            if not r["ok"]: return self.send(409, r["error"], "text/plain")
            with open(r["path"], "rb") as f: body = f.read()
            return self.send(200, body, "model/stl")
        if path == "/api/probe":
            r = probe(parse_params(q, data), data["probe"], data)
            return self.send(200, json.dumps(r), "application/json")
        if path == "/api/events":
            qq = queue.Queue(); WATCHERS.append(qq)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                while True:
                    try: sig = qq.get(timeout=15)
                    except queue.Empty: self.wfile.write(b": ping\n\n")
                    else: self.wfile.write(("event: change\ndata: %s\n\n" % sig).encode())
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                if qq in WATCHERS: WATCHERS.remove(qq)
            return
        # static
        safe = os.path.normpath(path).lstrip("/")
        full = os.path.join(WEB, safe)
        if os.path.isfile(full) and full.startswith(WEB):
            ctype = {"html": "text/html", "js": "text/javascript", "css": "text/css"}.get(
                safe.rsplit(".", 1)[-1], "application/octet-stream")
            with open(full, "rb") as f: return self.send(200, f.read(), ctype + "; charset=utf-8")
        self.send(404, "not found", "text/plain")

VENDOR = {
 "three.module.min.js": "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.min.js",
 "OrbitControls.js":    "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/controls/OrbitControls.js",
 "STLLoader.js":        "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/loaders/STLLoader.js",
}
def ensure_vendor():
    # The three files are committed under web/vendor/; this only fires if
    # one goes missing, so scadview never needs the network in normal use.
    d = os.path.join(WEB, "vendor"); os.makedirs(d, exist_ok=True)
    for fn, url in VENDOR.items():
        p = os.path.join(d, fn)
        if not os.path.exists(p):
            print("fetching", url, file=sys.stderr)
            with urllib.request.urlopen(url, timeout=30) as r, open(p, "wb") as f:
                f.write(r.read())

def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try: s.connect(("192.168.0.1", 1)); return s.getsockname()[0]
    except OSError: return "127.0.0.1"
    finally: s.close()

def main():
    global REPO, CACHE, CONFIG_PATH
    ap = argparse.ArgumentParser(description="OpenSCAD live viewer")
    ap.add_argument("--repo", default=os.environ.get("SCADVIEW_REPO", os.getcwd()),
                    help="project root (default: cwd)")
    ap.add_argument("--config", default=None, help="default: <repo>/scadview.json")
    ap.add_argument("--port", type=int, default=None, help="overrides scadview.json")
    ap.add_argument("--host", default="0.0.0.0",
                    help="0.0.0.0 so a phone on the LAN can open it; use 127.0.0.1 to keep it local")
    a = ap.parse_args()
    REPO = os.path.abspath(a.repo)
    CACHE = os.path.join(REPO, ".scadview-cache")
    CONFIG_PATH = os.path.abspath(a.config) if a.config else os.path.join(REPO, "scadview.json")
    data = cfg()
    port = a.port or data["port"]
    ensure_vendor()
    threading.Thread(target=watch_loop, daemon=True).start()
    srv = http.server.ThreadingHTTPServer((a.host, port), H)
    srv.daemon_threads = True
    hostname = socket.gethostname().lower()
    print(f"scadview  http://localhost:{port}   ({len(data['targets'])} targets from {os.path.relpath(CONFIG_PATH, REPO)})", flush=True)
    print(f"phone     http://{hostname}:{port}   (or http://{lan_ip()}:{port})", flush=True)
    srv.serve_forever()

if __name__ == "__main__":
    main()
