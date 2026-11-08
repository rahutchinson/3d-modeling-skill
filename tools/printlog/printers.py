"""Printer monitors for printlog-server (stdlib only).

Each monitor keeps a live connection to one printer and reduces whatever
the printer reports to a common snapshot:

    {"name", "type", "online", "state", "file", "job", "progress",
     "layer", "total_layers", "elapsed_s", "remaining_s", "started_at",
     "material", "nozzle", "bed", "error", "updated"}

state is one of: offline, idle, printing, paused, finished, failed.
Each change goes to `on_update(snapshot)`, and the server turns job
transitions into print records.

Supported:
  creality  K1 / K1 SE / K1C / K1 Max on stock firmware: websocket on :9999,
            no auth.
  bambu     A1 / A1 mini / P1 / X1: MQTT over TLS on :8883, user "bblp",
            password = the LAN access code from the printer's screen.
"""
import base64, json, os, socket, ssl, struct, threading, time

MATERIALS = ("PETG", "PLA", "ABS", "ASA", "TPU", "PCTG", "PA", "PC", "PET", "HIPS", "PVA")


def material_from_name(name):
    for tok in name.replace("-", "_").replace(" ", "_").replace(".", "_").upper().split("_"):
        for m in MATERIALS:
            if tok == m or (tok.startswith(m) and tok[len(m):] in ("", "+", "CF", "HF")):
                return tok
    return None


class Monitor(threading.Thread):
    type = "?"

    def __init__(self, conf, on_update, log):
        super().__init__(daemon=True, name=f"printer-{conf['name']}")
        self.conf, self.on_update, self.log = conf, on_update, log
        self.snap = {"name": conf["name"], "type": self.type, "host": conf.get("host"),
                     "model": conf.get("model"), "online": False, "state": "offline", "updated": None}
        self.lock = threading.Lock()

    def snapshot(self):
        with self.lock:
            return dict(self.snap)

    def publish(self, **kw):
        with self.lock:
            self.snap.update(kw)
            self.snap["updated"] = time.time()
            snap = dict(self.snap)
        try:
            self.on_update(snap)
        except Exception as e:  # noqa
            self.log(f"printer {self.conf['name']}: update handler failed: {e!r}")

    def run(self):
        backoff = 5
        while True:
            try:
                self.session()
                backoff = 5
            except Exception as e:  # noqa
                if self.snap.get("online"):
                    self.log(f"printer {self.conf['name']}: disconnected ({e})")
                self.publish(online=False, state="offline")
            time.sleep(backoff)
            backoff = min(backoff * 2, 120)


# ---------------------------------------------------------------- creality
class Creality(Monitor):
    """Stock Creality OS (K1 family) status websocket on port 9999."""
    type = "creality"
    STATES = {0: "idle", 1: "printing", 2: "finished", 3: "failed", 4: "failed", 5: "paused"}

    def session(self):
        host, port = self.conf["host"], int(self.conf.get("port", 9999))
        s = socket.create_connection((host, port), timeout=10)
        try:
            key = base64.b64encode(os.urandom(16)).decode()
            s.sendall((f"GET / HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                       f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
            buf = b""
            while b"\r\n\r\n" not in buf:
                c = s.recv(4096)
                if not c:
                    raise ConnectionError("closed during handshake")
                buf += c
            head, buf = buf.split(b"\r\n\r\n", 1)
            if b" 101" not in head.split(b"\r\n", 1)[0]:
                raise ConnectionError("websocket upgrade refused")
            self.log(f"printer {self.conf['name']}: connected to {host}:{port}")
            s.settimeout(30)
            raw = {}
            last_beat = 0
            while True:
                if time.time() - last_beat > 10:
                    self._send(s, json.dumps({"ModeCode": "heart_beat", "msg": time.strftime("%Y-%m-%d %H:%M:%S")}))
                    last_beat = time.time()
                op, payload, buf = self._frame(s, buf)
                if op == 8:
                    raise ConnectionError("printer closed the websocket")
                if op == 9:
                    self._send(s, payload, opcode=10)
                    continue
                if op != 1:
                    continue
                try:
                    msg = json.loads(payload)
                except ValueError:
                    continue
                if not isinstance(msg, dict):
                    continue
                raw.update(msg)
                self.publish(**self._reduce(raw))
        finally:
            s.close()

    def _reduce(self, r):
        st = self.STATES.get(r.get("state"), "idle")
        f = r.get("printFileName") or ""
        base = os.path.basename(f)

        def num(k):
            try:
                return float(r[k])
            except (KeyError, TypeError, ValueError):
                return None
        start = num("printStartTime")
        return {"online": True, "state": st, "model": r.get("model") or self.conf.get("model"),
                "file": base or None, "job": r.get("printId") or (f"{base}@{int(start)}" if base and start else None),
                "progress": r.get("printProgress"), "layer": r.get("layer"), "total_layers": r.get("TotalLayer"),
                "elapsed_s": r.get("printJobTime"), "remaining_s": r.get("printLeftTime"),
                "started_at": start if start and start > 1e9 else None,
                "material": material_from_name(base) if base else None,
                "nozzle": num("nozzleTemp"), "bed": num("bedTemp0"),
                "error": (r.get("err") or {}).get("errcode") or None}

    @staticmethod
    def _send(s, text, opcode=1):
        data = text.encode() if isinstance(text, str) else text
        mask = os.urandom(4)
        n = len(data)
        head = bytes([0x80 | opcode])
        if n < 126:
            head += bytes([0x80 | n])
        elif n < 65536:
            head += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            head += bytes([0x80 | 127]) + struct.pack(">Q", n)
        s.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    @staticmethod
    def _frame(s, buf):
        def need(n):
            nonlocal buf
            while len(buf) < n:
                c = s.recv(65536)
                if not c:
                    raise ConnectionError("websocket closed")
                buf += c
        message, opcode = b"", None
        while True:
            need(2)
            fin, op = buf[0] & 0x80, buf[0] & 0x0F
            masked, n, o = buf[1] & 0x80, buf[1] & 0x7F, 2
            if n == 126:
                need(4); n = struct.unpack(">H", buf[2:4])[0]; o = 4
            elif n == 127:
                need(10); n = struct.unpack(">Q", buf[2:10])[0]; o = 10
            if masked:
                need(o + 4); m = buf[o:o + 4]; o += 4
            need(o + n)
            data = buf[o:o + n]
            if masked:
                data = bytes(b ^ m[i % 4] for i, b in enumerate(data))
            buf = buf[o + n:]
            if op >= 8:                       # control frames are never fragmented
                return op, data, buf
            if op:
                opcode = op
            message += data
            if fin:
                return opcode, message.decode(errors="replace") if opcode == 1 else message, buf


# ---------------------------------------------------------------- bambu
class Bambu(Monitor):
    """Bambu Lab local MQTT (TLS :8883, user bblp, password = LAN access code)."""
    type = "bambu"
    STATES = {"IDLE": "idle", "PREPARE": "printing", "SLICING": "printing", "RUNNING": "printing",
              "PAUSE": "paused", "FINISH": "finished", "FAILED": "failed"}

    def session(self):
        host, serial, code = self.conf["host"], self.conf["serial"], self.conf["access_code"]
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE           # printers use a self-signed per-device cert
        raw = socket.create_connection((host, int(self.conf.get("port", 8883))), timeout=15)
        s = ctx.wrap_socket(raw, server_hostname=host)
        try:
            cid = f"printlog-{os.getpid()}-{os.urandom(3).hex()}"
            payload = self._str(cid) + self._str("bblp") + self._str(code)
            var = self._str("MQTT") + bytes([4, 0xC2]) + struct.pack(">H", 60)
            s.sendall(self._packet(0x10, var + payload))
            pkt_type, body = self._read(s)
            if pkt_type != 2 or len(body) < 2 or body[1] != 0:
                rc = body[1] if len(body) > 1 else "?"
                raise ConnectionError(f"MQTT connect refused (rc={rc}; 4/5 = wrong access code)")
            s.sendall(self._packet(0x82, struct.pack(">H", 1) + self._str(f"device/{serial}/report") + b"\x00"))
            self._publish(s, f"device/{serial}/request",
                          json.dumps({"pushing": {"sequence_id": "0", "command": "pushall"}}))
            self.log(f"printer {self.conf['name']}: connected to {host} (serial {serial})")
            s.settimeout(20)
            state, last_ping, last_push = {}, time.time(), time.time()
            while True:
                now = time.time()
                if now - last_ping > 30:
                    s.sendall(b"\xC0\x00"); last_ping = now
                if now - last_push > 300:     # A1/P1 only send deltas; refresh the full state now and then
                    self._publish(s, f"device/{serial}/request",
                                  json.dumps({"pushing": {"sequence_id": "0", "command": "pushall"}}))
                    last_push = now
                try:
                    pkt_type, body = self._read(s)
                except socket.timeout:
                    continue
                if pkt_type != 3:
                    continue
                tl = struct.unpack(">H", body[:2])[0]
                try:
                    msg = json.loads(body[2 + tl:])
                except ValueError:
                    continue
                if isinstance(msg.get("print"), dict):
                    self._merge(state, msg["print"])
                    self.publish(**self._reduce(state))
        finally:
            s.close()

    @staticmethod
    def _merge(dst, src):
        for k, v in src.items():
            if isinstance(v, dict) and isinstance(dst.get(k), dict):
                Bambu._merge(dst[k], v)
            else:
                dst[k] = v

    def _reduce(self, p):
        gs = (p.get("gcode_state") or "").upper()
        st = self.STATES.get(gs, "idle")
        name = p.get("subtask_name") or os.path.basename(p.get("gcode_file") or "") or None
        job = p.get("task_id") or p.get("job_id")
        if job in ("0", 0, ""):
            job = None
        start = None
        try:
            start = float(p.get("gcode_start_time") or 0) or None
        except (TypeError, ValueError):
            pass
        rem = p.get("mc_remaining_time")
        material = None
        try:
            tray_now = (p.get("ams") or {}).get("tray_now")
            if tray_now not in (None, "255", "254"):
                for unit in (p.get("ams") or {}).get("ams", []):
                    for tr in unit.get("tray", []):
                        if str(int(unit["id"]) * 4 + int(tr["id"])) == str(tray_now):
                            material = tr.get("tray_type")
            if not material:
                material = (p.get("vt_tray") or {}).get("tray_type") or None
        except (KeyError, TypeError, ValueError):
            pass
        err = p.get("print_error") or None
        return {"online": True, "state": st, "model": self.conf.get("model"), "file": name,
                "job": f"{job}:{name}" if job else (f"{name}@{int(start)}" if name and start else None),
                "progress": p.get("mc_percent"), "layer": p.get("layer_num"), "total_layers": p.get("total_layer_num"),
                "elapsed_s": (time.time() - start) if (start and st in ("printing", "paused")) else None,
                "remaining_s": rem * 60 if isinstance(rem, (int, float)) else None,
                "started_at": start, "material": material or (material_from_name(name) if name else None),
                "nozzle": p.get("nozzle_temper"), "bed": p.get("bed_temper"),
                "error": err if err not in (0, "0") else None}

    # minimal MQTT 3.1.1 framing
    @staticmethod
    def _str(s):
        b = s.encode()
        return struct.pack(">H", len(b)) + b

    @staticmethod
    def _packet(first, body):
        n, enc = len(body), b""
        while True:
            d, n = n % 128, n // 128
            enc += bytes([d | (0x80 if n else 0)])
            if not n:
                break
        return bytes([first]) + enc + body

    def _publish(self, s, topic, payload):
        s.sendall(self._packet(0x30, self._str(topic) + payload.encode()))

    @staticmethod
    def _read(s):
        def exact(n):
            out = b""
            while len(out) < n:
                c = s.recv(n - len(out))
                if not c:
                    raise ConnectionError("MQTT connection closed")
                out += c
            return out
        first = exact(1)[0]
        mult, n = 1, 0
        while True:
            d = exact(1)[0]
            n += (d & 0x7F) * mult
            if not d & 0x80:
                break
            mult *= 128
        return first >> 4, exact(n) if n else b""


KINDS = {"creality": Creality, "bambu": Bambu}


def start_all(confs, on_update, log):
    mons = []
    for c in confs:
        cls = KINDS.get(c.get("type"))
        if not cls:
            log(f"printer {c.get('name')}: unknown type {c.get('type')!r}, skipping")
            continue
        if c.get("enabled") is False:
            continue
        missing = [k for k in ("name", "host") + (("serial", "access_code") if cls is Bambu else ()) if not c.get(k)]
        if missing:
            log(f"printer {c.get('name')}: missing {missing}, skipping")
            continue
        m = cls(c, on_update, log)
        m.start()
        mons.append(m)
    return mons
