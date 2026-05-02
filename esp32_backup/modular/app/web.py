# app/web.py - HTTP API 服务 (Microdot)
import asyncio
import time
import os
import json
from machine import reset, Pin
import network
import ntptime
from lib.microdot import Microdot, Response
from app import shared, config, logger

app = Microdot()

MAX_HISTORY = 2000
history_buffer = []


def add_history(temp, hum):
    history_buffer.append((time.time(), temp, hum))
    if len(history_buffer) > MAX_HISTORY:
        history_buffer.pop(0)


def _get_history(period=None, start_ts=None, end_ts=None):
    now = time.time()
    if start_ts is not None and end_ts is not None:
        cutoff, end = start_ts, end_ts
    elif period == 'all':
        cutoff, end = 0, now
    elif period == '1h':
        cutoff, end = now - 3600, now
    elif period == '6h':
        cutoff, end = now - 6 * 3600, now
    elif period == '1w':
        cutoff, end = now - 7 * 86400, now
    elif period == '1m':
        cutoff, end = now - 30 * 86400, now
    else:
        cutoff, end = now - 86400, now

    pts = [(ts, t, h) for ts, t, h in history_buffer if cutoff <= ts <= end]
    pts.sort(key=lambda x: x[0])

    if not pts:
        return [], [], []

    MAX = 500
    if len(pts) <= MAX:
        sampled = pts
    else:
        step = len(pts) // MAX
        sampled = pts[::step]

    labels, t_vals, h_vals = [], [], []
    for ts, t, h in sampled:
        lt = time.localtime(ts + shared.timezone_offset * 3600)
        labels.append("{:02d}:{:02d}".format(lt[3], lt[4]))
        t_vals.append(t)
        h_vals.append(h)
    return labels, t_vals, h_vals


# ==================== 路由 ====================

@app.route('/')
async def index(request):
    try:
        return Response.send_file('www/index.html', content_type='text/html')
    except OSError:
        return Response.send_file('index.html', content_type='text/html')


@app.route('/api/readings')
async def api_readings(request):
    rssi = 0
    if shared.wlan and shared.wlan.isconnected():
        try:
            rssi = shared.wlan.status('rssi')
        except Exception:
            pass
    return {
        "temp": round(shared.latest_temp, 1),
        "hum": round(shared.latest_hum, 1),
        "rssi": rssi,
        "uptime": int(time.time() - shared.uptime_start),
    }


@app.route('/api/history')
async def api_history(request):
    period = request.args.get('period', '1d')
    labels, t, h = _get_history(period=period)
    return {"labels": labels, "t": t, "h": h}


@app.route('/api/history/range')
async def api_history_range(request):
    try:
        start = request.args.get('start', '')
        end = request.args.get('end', '')
        st = time.mktime(time.strptime(start, '%Y-%m-%d'))
        et = time.mktime(time.strptime(end, '%Y-%m-%d')) + 86400
        labels, t, h = _get_history(start_ts=st, end_ts=et)
        return {"labels": labels, "t": t, "h": h}
    except Exception as e:
        return {"error": str(e)}, 400


@app.route('/api/wifi/connect', methods=['POST'])
async def api_wifi_connect(request):
    ssid = request.form.get('ssid', '')
    pwd = request.form.get('pwd', '')
    if not shared.wlan.active():
        shared.wlan.active(True)
    shared.wlan.connect(ssid, pwd)
    config.set('wifi.ssid', ssid)
    config.set('wifi.password', pwd)
    return {"success": True, "message": "连接中..."}


@app.route('/api/wifi/scan')
async def api_wifi_scan(request):
    if not shared.wlan.active():
        shared.wlan.active(True)
    try:
        nets = shared.wlan.scan()
        result = [{"ssid": n[0].decode() if isinstance(n[0], bytes) else n[0], "rssi": n[3]} for n in nets]
        return {"networks": result}
    except Exception as e:
        return {"error": str(e)}, 500


@app.route('/api/wifi/status')
async def api_wifi_status(request):
    connected = shared.wlan.isconnected() if shared.wlan else False
    ssid, ip, rssi = "", "", 0
    if connected:
        cfg = shared.wlan.ifconfig()
        ip = cfg[0]
        ssid = shared.wlan.config('essid')
        if isinstance(ssid, bytes):
            ssid = ssid.decode()
        rssi = shared.wlan.status('rssi')
    return {"connected": connected, "ssid": ssid, "ip": ip, "rssi": rssi}


@app.route('/api/gpio')
@app.route('/api/gpio', methods=['POST'])
async def api_gpio(request):
    try:
        led = Pin(2, Pin.OUT)
    except Exception:
        return {"state": 0}
    if request.method == 'POST':
        state_val = request.form.get('state', request.args.get('state', '0'))
        try:
            led.value(int(state_val))
        except Exception:
            pass
    return {"state": led.value()}


@app.route('/api/files/list')
async def api_files_list(request):
    result = []
    for name in os.listdir():
        try:
            s = os.stat(name)
            result.append({"name": name, "size": s[6] if len(s) > 6 else 0})
        except Exception:
            pass
    try:
        for name in os.listdir('/sd'):
            s = os.stat('/sd/' + name)
            result.append({"name": "sd/" + name, "size": s[6] if len(s) > 6 else 0})
    except Exception:
        pass
    return {"files": result}


@app.route('/api/files/delete', methods=['POST'])
async def api_files_delete(request):
    name = request.form.get('name', request.args.get('name', ''))
    if not name or name.startswith('/') or '..' in name:
        return {"error": "无效文件名"}, 400
    try:
        os.remove(name)
        return {"success": True}
    except OSError as e:
        return {"error": str(e)}, 404


@app.route('/api/files/upload', methods=['POST'])
async def api_files_upload(request):
    ct = request.content_type or ''
    if 'multipart/form-data' not in ct:
        return {"error": "需要 multipart/form-data"}, 400
    boundary = None
    for part in ct.split(';'):
        part = part.strip()
        if part.startswith('boundary='):
            boundary = part[9:].strip('"')
            break
    if not boundary:
        return {"error": "缺少 boundary"}, 400
    raw = request.body
    parts = raw.split(('--' + boundary).encode())
    for part in parts[1:]:
        if part.startswith(b'--'):
            break
        idx = part.find(b'\r\n\r\n')
        if idx < 0:
            continue
        body = part[idx + 4:]
        if body.endswith(b'\r\n'):
            body = body[:-2]
        fname = ''
        for line in part[:idx].decode('utf-8', 'ignore').split('\r\n'):
            if 'filename="' in line:
                s = line.find('filename="') + 10
                e = line.find('"', s)
                fname = line[s:e]
                break
        if fname and body:
            try:
                with open(fname, 'wb') as f:
                    f.write(body)
                return {"success": True, "name": fname}
            except OSError as e:
                return {"error": str(e)}, 500
    return {"error": "未解析到文件"}, 400


@app.route('/api/config/sensor', methods=['POST'])
async def api_config_sensor(request):
    config.set('sensor.type', request.form.get('type', 'DHT22'))
    config.set('sensor.interval', int(request.form.get('interval', '2')))
    config.set('log.enabled', request.form.get('log_enabled', 'true') == 'true')
    config.set('log.interval', int(request.form.get('log_interval', '60')))
    config.save()
    return {"success": True}


@app.route('/api/mqtt/config', methods=['POST'])
async def api_mqtt_config(request):
    config.set('mqtt.broker', request.form.get('broker', ''))
    config.set('mqtt.port', int(request.form.get('port', '1883')))
    config.set('mqtt.user', request.form.get('user', ''))
    config.set('mqtt.password', request.form.get('pass', ''))
    config.set('mqtt.pub_topic', request.form.get('pub_topic', 'sensor/data'))
    config.save()
    return {"success": True}


@app.route('/api/ntp/sync', methods=['POST'])
async def api_ntp_sync(request):
    try:
        ntptime.host = shared.ntp_server
        ntptime.settime()
        shared.last_ntp_sync_time = time.time()
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}, 500


@app.route('/api/reboot', methods=['POST'])
async def api_reboot(request):
    asyncio.get_event_loop().call_later(1, reset)
    return {"success": True, "message": "重启中..."}


@app.route('/api/factory_reset', methods=['POST'])
async def api_factory_reset(request):
    config.reset()
    return {"success": True}


@app.route('/api/status')
async def api_status(request):
    connected = shared.wlan.isconnected() if shared.wlan else False
    ssid, rssi = "", 0
    if connected:
        essid = shared.wlan.config('essid')
        ssid = essid.decode() if isinstance(essid, bytes) else essid
        rssi = shared.wlan.status('rssi')
    return {
        "temp": round(shared.latest_temp, 1),
        "hum": round(shared.latest_hum, 1),
        "uptime": int(time.time() - shared.uptime_start),
        "wifi": {"connected": connected, "ssid": ssid, "rssi": rssi},
        "led": Pin(2, Pin.OUT).value(),
        "sensor_type": shared.sensor_type,
        "sample_interval": shared.sensor_interval,
    }



# ==================== 日志管理 ====================

@app.route('/api/logs/list')
async def api_logs_list(request):
    return {"files": logger.get_log_files()}


@app.route('/api/logs/download')
async def api_logs_download(request):
    date = request.args.get('date', '')
    path = logger.get_log_path(date)
    if path is None:
        return {"error": "无效日期"}, 400
    try:
        return Response.send_file(path, content_type='application/octet-stream')
    except OSError:
        return {"error": "文件不存在"}, 404


@app.route('/api/logs/stats')
async def api_logs_stats(request):
    period = request.args.get('period', 'today')
    return logger.get_stats(period)


async def start(host='0.0.0.0', port=80):
    print("Web 服务: http://{}:{}".format(host, port))
    await app.start_server(host=host, port=port, debug=False)
