# app/shared.py - 全局共享状态
# 所有模块通过此模块共享运行时对象和变量

tft = None
wlan = None
ds1302 = None
sensor = None
sensor_type = "DHT22"
sensor_interval = 2.0
sensor_decimal = True
wifi_ssid = ""
wifi_password = ""
wifi_connected = False
wifi_connecting = False
wifi_connect_start = 0
wifi_last_attempt = 0
LOG_FILE = None
LOG_DIR = '/sd/logs'
SD_READY = False
log_enabled = False
log_interval = 60
last_ntp_sync_time = 0
ntp_server = "ntp.aliyun.com"
timezone_offset = 8
ntp_sync_interval = 86400
uptime_start = 0
latest_temp = 0.0
latest_hum = 0.0
ap_active = False
ap_ssid = "ESP32-Config"
consec_wifi_fails = 0
