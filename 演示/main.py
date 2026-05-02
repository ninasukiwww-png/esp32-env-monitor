import http.server
import json
import random
import time
import os
import threading
import webbrowser
import urllib.parse
import tkinter as tk

# ==================== 传感器模拟 ====================
class SensorSimulator:
    def __init__(self):
        self.temp = 25.0
        self.hum = 60.0
        self.target_temp = 25.0
        self.target_hum = 60.0
        self.uptime = 0
        self.led_state = 0
        self.wifi_connected = True
        self.wifi_ssid = "DemoWiFi"
        self.sensor_type = "DHT22"
        self.sample_interval = 2
        self.log_enabled = True
        self.log_interval = 60
        self.history = []
        self._last_update = 0
        self._lock = threading.Lock()

    def update(self):
        now = time.time()
        if now - self._last_update < 1.0:
            return
        with self._lock:
            self._last_update = now
            self.uptime += 1
            self.target_temp += random.uniform(-0.3, 0.3)
            self.target_temp = max(15, min(40, self.target_temp))
            self.target_hum += random.uniform(-2, 2)
            self.target_hum = max(20, min(95, self.target_hum))
            self.temp += (self.target_temp - self.temp) * 0.1 + random.uniform(-0.05, 0.05)
            self.hum += (self.target_hum - self.hum) * 0.1 + random.uniform(-0.3, 0.3)
            self.history.append((int(now), round(self.temp, 1), round(self.hum, 1)))
            if len(self.history) > 2000:
                self.history.pop(0)

    def get_readings(self):
        self.update()
        with self._lock:
            return {
                "temp": round(self.temp, 1),
                "hum": round(self.hum, 1),
                "rssi": -40 + random.randint(-15, 5),
                "uptime": self.uptime,
            }

    def get_history(self, hours=24):
        now = time.time()
        cutoff = now - hours * 3600
        with self._lock:
            pts = [(ts, t, h) for ts, t, h in self.history if ts >= cutoff]
        pts.sort(key=lambda x: x[0])
        MAX = 500
        if len(pts) > MAX:
            step = len(pts) // MAX
            pts = pts[::step]
        labels, t_vals, h_vals = [], [], []
        for ts, t, h in pts:
            lt = time.localtime(ts)
            labels.append("{:02d}:{:02d}".format(lt[3], lt[4]))
            t_vals.append(t)
            h_vals.append(h)
        return {"labels": labels, "t": t_vals, "h": h_vals}

    def get_history_range(self, start_ts, end_ts):
        with self._lock:
            pts = [(ts, t, h) for ts, t, h in self.history if start_ts <= ts <= end_ts]
        pts.sort(key=lambda x: x[0])
        MAX = 500
        if len(pts) > MAX:
            step = len(pts) // MAX
            pts = pts[::step]
        labels, t_vals, h_vals = [], [], []
        for ts, t, h in pts:
            lt = time.localtime(ts)
            labels.append("{:02d}:{:02d}".format(lt[3], lt[4]))
            t_vals.append(t)
            h_vals.append(h)
        return {"labels": labels, "t": t_vals, "h": h_vals}


sensor = SensorSimulator()
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


# ==================== HTTP 服务 ====================
class DemoHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path):
        try:
            with open(path, "rb") as f:
                content = f.read()
            ext = os.path.splitext(path)[1].lower()
            ct_map = {
                ".html": "text/html; charset=utf-8",
                ".css": "text/css",
                ".js": "application/javascript",
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".svg": "image/svg+xml",
                ".ico": "image/x-icon",
            }
            ct = ct_map.get(ext, "application/octet-stream")
            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", len(content))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self._send_json({"error": "not found"}, 404)

    def _get_post_data(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8", "ignore")
        return urllib.parse.parse_qs(raw)

    def _parse_path(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        params = urllib.parse.parse_qs(parsed.query)
        return path, {k: v[0] for k, v in params.items()}

    def _route(self):
        path, params = self._parse_path()

        if path == "/api/readings":
            return self._send_json(sensor.get_readings())

        elif path == "/api/status":
            r = sensor.get_readings()
            r["wifi"] = {"connected": sensor.wifi_connected, "ssid": sensor.wifi_ssid, "rssi": r["rssi"]}
            r["led"] = sensor.led_state
            r["sensor_type"] = sensor.sensor_type
            r["sample_interval"] = sensor.sample_interval
            return self._send_json(r)

        elif path == "/api/wifi/status":
            return self._send_json({
                "connected": sensor.wifi_connected,
                "ssid": sensor.wifi_ssid,
                "ip": "192.168.1.100",
                "rssi": -40 + random.randint(-15, 5),
            })

        elif path == "/api/wifi/scan":
            nets = [
                {"ssid": "HomeWiFi_2.4G", "rssi": -45},
                {"ssid": "TP-LINK_5G", "rssi": -70},
                {"ssid": "CMCC-AUTO", "rssi": -60},
                {"ssid": "Office_Guest", "rssi": -52},
                {"ssid": "ChinaNet-Link", "rssi": -78},
            ]
            return self._send_json({"networks": nets})

        elif path == "/api/wifi/connect" and self.command == "POST":
            data = self._get_post_data()
            ssid = data.get("ssid", [""])[0]
            sensor.wifi_connected = True
            sensor.wifi_ssid = ssid
            return self._send_json({"success": True, "ip": "192.168.1.100"})

        elif path == "/api/gpio":
            if self.command == "POST":
                data = self._get_post_data()
                st = data.get("state", params.get("state", "0"))
                sensor.led_state = int(st)
            return self._send_json({"state": sensor.led_state})

        elif path == "/api/history":
            hours = int(params.get("hours", 24))
            return self._send_json(sensor.get_history(hours))

        elif path == "/api/history/range":
            start = int(params.get("start", 0))
            end = int(params.get("end", 0))
            if start == 0:
                start = int(time.time()) - 86400
            if end == 0:
                end = int(time.time())
            return self._send_json(sensor.get_history_range(start, end))

        elif path == "/api/files/list":
            files = [
                {"name": "main.py", "size": 2048},
                {"name": "boot.py", "size": 512},
                {"name": "config.json", "size": 128},
                {"name": "sd/log_2026-04-30.csv", "size": 8500},
                {"name": "sd/log_2026-05-01.csv", "size": 7200},
            ]
            return self._send_json({"files": files})

        elif path == "/api/files/delete" and self.command == "POST":
            return self._send_json({"success": True})

        elif path == "/api/files/upload" and self.command == "POST":
            return self._send_json({"success": True, "name": "uploaded.bin"})

        elif path == "/api/config/sensor" and self.command == "POST":
            data = self._get_post_data()
            if "type" in data:
                sensor.sensor_type = data["type"][0]
            if "interval" in data:
                sensor.sample_interval = int(data["interval"][0])
            if "log_enabled" in data:
                sensor.log_enabled = data["log_enabled"][0] == "true"
            if "log_interval" in data:
                sensor.log_interval = int(data["log_interval"][0])
            return self._send_json({"success": True})

        elif path == "/api/mqtt/config" and self.command == "POST":
            return self._send_json({"success": True})

        elif path == "/api/ntp/sync" and self.command == "POST":
            return self._send_json({"success": True})

        elif path == "/api/reboot" and self.command == "POST":
            return self._send_json({"success": True, "message": "重启中..."})

        elif path == "/api/factory_reset" and self.command == "POST":
            return self._send_json({"success": True})

        elif path == "/api/logs/list":
            files = []
            for i in range(7):
                d = time.gmtime(time.time() - i * 86400)
                ds = "{:04d}-{:02d}-{:02d}".format(d[0], d[1], d[2])
                files.append({"name": ds + ".csv", "size": 6000 + random.randint(0, 3000), "date": ds})
            return self._send_json({"files": files})

        elif path == "/api/logs/download":
            return self._send_json({"error": "模拟模式无真实日志"}, 404)

        elif path == "/api/logs/stats":
            period = params.get("period", "today")
            days = {"today": 1, "week": 7, "month": 30}.get(period, 1)
            base = 24.0 + random.uniform(-1, 1)
            return self._send_json({
                "temp": {"min": round(base - 3, 1), "max": round(base + 3, 1), "avg": round(base, 1)},
                "hum": {"min": 45, "max": 70, "avg": 58},
                "data_points": days * 720,
                "days_covered": days,
            })

        elif path == "/":
            self._send_file(os.path.join(SCRIPT_DIR, "index.html"))

        else:
            file_path = os.path.join(SCRIPT_DIR, path.lstrip("/"))
            if os.path.exists(file_path) and os.path.isfile(file_path):
                self._send_file(file_path)
            else:
                self._send_json({"error": "not found"}, 404)

    def do_GET(self):
        self._route()

    def do_POST(self):
        self._route()


# ==================== 屏幕模拟 (Tkinter) ====================
COLOR_BG = "#121c28"
COLOR_CARD = "#1a2434"
COLOR_BORDER = "#2d4155"
COLOR_TEMP = "#ffbe6e"
COLOR_HUM = "#6edcff"
COLOR_LABEL = "#c8dcf0"
COLOR_STATUS = "#8296aa"
COLOR_ACCENT = "#00d2e6"
COLOR_ERROR = "#ff5a5a"
COLOR_TEMP_GHOST = "#463728"
COLOR_HUM_GHOST = "#143246"

SEG_POINTS = {
    'a': [(10,5),(30,5)], 'b': [(35,10),(35,30)], 'c': [(35,35),(35,55)],
    'd': [(10,60),(30,60)], 'e': [(5,35),(5,55)], 'f': [(5,10),(5,30)],
    'g': [(10,32),(30,32)],
}
SEG_THICK = 6
DIGIT_SEGS = {
    '0': 'abcdef', '1': 'bc', '2': 'abdeg', '3': 'abcdg',
    '4': 'bcfg', '5': 'acdfg', '6': 'acdefg', '7': 'abc',
    '8': 'abcdefg', '9': 'abcdfg', '-': 'g', ' ': ''
}
DIGIT_W = 42
DIGIT_H = 68
DIGIT_GAP = 3


class DigitDisplay(tk.Canvas):
    def __init__(self, parent, color, ghost_color, **kw):
        super().__init__(parent, **kw)
        self.color = color
        self.ghost_color = ghost_color

    def clear(self):
        self.delete("all")

    def draw_digit(self, x, y, ch, old_ch=None):
        if ch == old_ch:
            return
        bw = DIGIT_W
        bh = DIGIT_H
        self.create_rectangle(x-1, y-1, x+bw+1, y+bh+1, fill=COLOR_CARD, outline="")
        self._draw_ghost(x, y)
        segs = DIGIT_SEGS.get(ch, '')
        for s in segs:
            pts = SEG_POINTS[s]
            x1, y1 = pts[0]
            x2, y2 = pts[1]
            if x1 == x2:
                self.create_rectangle(x+x1-SEG_THICK//2, y+y1, SEG_THICK, y2-y1, fill=self.color, outline="")
            else:
                self.create_rectangle(x+x1, y+y1-SEG_THICK//2, x2-x1, SEG_THICK, fill=self.color, outline="")

    def _draw_ghost(self, x, y):
        for s in 'abcdefg':
            pts = SEG_POINTS[s]
            x1, y1 = pts[0]
            x2, y2 = pts[1]
            if x1 == x2:
                self.create_rectangle(x+x1-SEG_THICK//2, y+y1, SEG_THICK, y2-y1, fill=self.ghost_color, outline="")
            else:
                self.create_rectangle(x+x1, y+y1-SEG_THICK//2, x2-x1, SEG_THICK, fill=self.ghost_color, outline="")


class DisplayApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("温湿度监测仪 - 演示版")
        self.root.geometry("480x640")
        self.root.configure(bg=COLOR_BG)
        self.root.resizable(False, False)
        self._build_ui()
        self._tick()

    def _build_ui(self):
        sf = tk.Frame(self.root, bg=COLOR_BG)
        sf.pack(fill="x", padx=10, pady=(8, 0))
        self.clock_lbl = tk.Label(sf, font=("Consolas", 14), fg=COLOR_STATUS, bg=COLOR_BG, anchor="w")
        self.clock_lbl.pack(side="left")
        self.wifi_lbl = tk.Label(sf, font=("Consolas", 12), fg=COLOR_STATUS, bg=COLOR_BG)
        self.wifi_lbl.pack(side="right", padx=(0, 5))
        self.sd_lbl = tk.Label(sf, font=("Consolas", 12), fg=COLOR_STATUS, bg=COLOR_BG)
        self.sd_lbl.pack(side="right", padx=(5, 0))

        sep = tk.Frame(self.root, height=1, bg=COLOR_BORDER)
        sep.pack(fill="x", pady=(8, 0))

        self._build_card("TEMP", 0)
        self._build_card("HUM", 1)

        bt = tk.Frame(self.root, bg=COLOR_BG)
        bt.pack(side="bottom", fill="x", padx=10, pady=(0, 10))
        self.info_lbl = tk.Label(bt, font=("Consolas", 10), fg=COLOR_STATUS, bg=COLOR_BG)
        self.info_lbl.pack()

    def _build_card(self, title, idx):
        card = tk.Frame(self.root, bg=COLOR_CARD, highlightbackground=COLOR_BORDER, highlightthickness=1, padx=15, pady=10)
        card.pack(fill="x", padx=15, pady=(15, 0))

        hdr = tk.Frame(card, bg=COLOR_CARD)
        hdr.pack(fill="x")
        icon = "\u2603" if title == "TEMP" else "\u2601"
        color = COLOR_TEMP if title == "TEMP" else COLOR_HUM
        tk.Label(hdr, text=icon, font=("Segoe UI", 12), fg=COLOR_ACCENT, bg=COLOR_CARD).pack(side="left", padx=(0, 5))
        tk.Label(hdr, text=title, font=("Segoe UI", 10, "bold"), fg=COLOR_LABEL, bg=COLOR_CARD).pack(side="left")
        tk.Frame(hdr, height=1, bg=COLOR_ACCENT).pack(side="bottom", fill="x", pady=(4, 0))

        body = tk.Frame(card, bg=COLOR_CARD)
        body.pack(fill="x", pady=(10, 0))

        disp = DigitDisplay(body, color, {0: COLOR_TEMP_GHOST, 1: COLOR_HUM_GHOST}[idx], bg=COLOR_CARD, highlightthickness=0, width=260, height=75)
        disp.pack(side="left")
        disp.clear()

        unit = "\u00b0C" if title == "TEMP" else "%"
        tk.Label(body, text=unit, font=("Segoe UI", 24, "bold"), fg=color, bg=COLOR_CARD).pack(side="right", padx=(5, 0))

        if title == "TEMP":
            self.temp_disp = disp
        else:
            self.hum_disp = disp

    def _draw_number(self, display, num_str, color, ghost):
        display.color = color
        display.ghost_color = ghost
        display.clear()
        cur_x = 5
        for ch in num_str:
            if ch == '.':
                display.create_oval(cur_x - 3, 3 + 58, cur_x + 3, 3 + 64, fill=color, outline="")
                cur_x += 5
            else:
                display.draw_digit(cur_x, 3, ch)
                cur_x += DIGIT_W + DIGIT_GAP

    def _tick(self):
        r = sensor.get_readings()
        temp_str = f"{r['temp']:.1f}"
        hum_str = f"{r['hum']:.0f}"

        self._draw_number(self.temp_disp, temp_str, COLOR_TEMP, COLOR_TEMP_GHOST)
        self._draw_number(self.hum_disp, hum_str, COLOR_HUM, COLOR_HUM_GHOST)

        now = time.localtime()
        self.clock_lbl.config(text="  {:04d}-{:02d}-{:02d}   {:02d}:{:02d}:{:02d}".format(
            now[0], now[1], now[2], now[3], now[4], now[5]))

        wc = "#00c800"
        wt = "WiFi \u2713"
        if not sensor.wifi_connected:
            wc = "#c80000"
            wt = "WiFi \u2717"
        self.wifi_lbl.config(text=wt, fg=wc)
        self.sd_lbl.config(text="SD \u2713", fg="#00c800")

        self.info_lbl.config(text="演示模式 | Web 界面: http://127.0.0.1:8080")

        self.root.after(1000, self._tick)

    def run(self):
        self.root.mainloop()


# ==================== 启动 ====================
def start_web_server():
    server = http.server.HTTPServer(("0.0.0.0", 8080), DemoHandler)
    print("  Web 界面: http://127.0.0.1:8080\n")
    webbrowser.open("http://127.0.0.1:8080")
    server.serve_forever()


if __name__ == "__main__":
    print("=" * 48)
    print("  环境温湿度监测仪 - Windows 演示版")
    print("  传感器模拟运行中...")
    print("=" * 48)
    print()

    t = threading.Thread(target=start_web_server, daemon=True)
    t.start()

    app = DisplayApp()
    try:
        app.run()
    except KeyboardInterrupt:
        print("\n已退出")
