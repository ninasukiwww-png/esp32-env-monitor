# web_light.py - 极简非阻塞温湿度 Web 服务器，专为 ESP32 内存优化
import time
import network
import socket
from machine import Pin
import dht

# --- 配置 ---
WIFI_SSID = '901'
WIFI_PASSWORD = '15212609205'
DHT_PIN = 13
SENSOR_TYPE = dht.DHT22

# --- HTML 模板 (作为常量节省内存) ---
HTML_TPL = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ESP32环境</title><meta http-equiv="refresh" content="3">
<style>body{{font-family:Arial;background:#121c28;color:#eee;text-align:center;margin:0;padding:20px}}
h1{{color:#46b4c8}}.card{{background:#1c2636;border-radius:12px;padding:20px;margin:20px auto;max-width:400px}}
.value{{font-size:64px;font-weight:bold;margin:10px 0}}.temp{{color:#ffb464}}.hum{{color:#64d2ff}}
.unit{{font-size:24px;margin-left:5px}}.footer{{margin-top:30px;color:#788ca0;font-size:14px}}</style></head>
<body><h1>🌡️ ESP32 环境监测</h1>
<div class="card"><div>🌡️ 温度</div><div class="value temp">{temp}<span class="unit">°C</span></div></div>
<div class="card"><div>💧 湿度</div><div class="value hum">{hum}<span class="unit">%</span></div></div>
<div class="footer">更新时间: {time}</div></body></html>"""

# --- 连接 WiFi ---
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print('连接 WiFi...')
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        while not wlan.isconnected():
            time.sleep(0.5)
    ip = wlan.ifconfig()[0]
    print('IP:', ip)
    return ip

# --- 读取传感器（单例对象，避免重复创建）---
sensor = SENSOR_TYPE(Pin(DHT_PIN))
def read_sensor():
    try:
        sensor.measure()
        return sensor.temperature(), sensor.humidity()
    except:
        return None, None

# --- 主函数 ---
def main():
    ip = connect_wifi()
    # 创建 socket，设置非阻塞
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('', 80))
    s.listen(2)
    s.settimeout(0)          # 非阻塞
    print('Web 服务器已启动（非阻塞模式）')

    while True:
        # 处理客户端连接（不阻塞）
        try:
            conn, addr = s.accept()
            request = conn.recv(1024).decode()
            # 只处理 GET / 请求，其他忽略
            if request.startswith('GET / '):
                temp, hum = read_sensor()
                t = time.localtime()
                time_str = '{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}'.format(
                    t[0], t[1], t[2], t[3], t[4], t[5])
                temp_str = '{:.1f}'.format(temp) if temp is not None else '--'
                hum_str  = '{:.1f}'.format(hum) if hum is not None else '--'
                html = HTML_TPL.format(temp=temp_str, hum=hum_str, time=time_str)
                conn.send('HTTP/1.1 200 OK\nContent-Type: text/html\nConnection: close\n\n')
                conn.sendall(html.encode())
            conn.close()
        except OSError:
            # 没有连接请求，继续
            pass

        # 给其他任务留时间（实际上不需要额外延时，但可以稍作等待以降低 CPU 占用）
        time.sleep_ms(10)

if __name__ == '__main__':
    main()