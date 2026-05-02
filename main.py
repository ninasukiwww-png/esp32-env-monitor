# main.py - ESP32 环境监测仪 (入口)
# 硬件初始化 → 加载配置 → 启动 Web/MQTT → async 主循环
import asyncio
import time
import network
import gc
from machine import Pin, SPI
import dht
from lib import ili9341
from app import shared, config, display as ui, wifi, mqtt, logger

# ==================== 硬件引脚 ====================
TFT_CLK, TFT_MOSI, TFT_DC, TFT_CS, TFT_RST, TFT_BL = 19, 18, 17, 4, 5, 16
DHT_PIN = 13
DS1302_CLK, DS1302_DAT, DS1302_RST = 12, 14, 27
SD_SCK, SD_MOSI, SD_MISO, SD_CS = 33, 25, 26, 32


# ==================== 加载配置 ====================
cfg = config.load()

shared.wifi_ssid = cfg['wifi']['ssid']
shared.wifi_password = cfg['wifi']['password']
shared.sensor_type = cfg['sensor']['type']
shared.sensor_interval = float(cfg['sensor']['interval'])
shared.sensor_decimal = cfg.get('sensor', {}).get('decimal', True)
shared.log_enabled = cfg['log']['enabled']
shared.log_interval = cfg['log']['interval']
shared.ntp_server = cfg['ntp']['server']
shared.timezone_offset = cfg['ntp']['timezone']
shared.ntp_sync_interval = cfg['ntp']['sync_interval']

web_enabled = cfg.get('web', {}).get('enabled', False)


# ==================== 传感器 ====================
if shared.sensor_type == 'DHT22':
    shared.sensor = dht.DHT22(Pin(DHT_PIN))
else:
    shared.sensor = dht.DHT11(Pin(DHT_PIN))
time.sleep(1)


# ==================== DS1302 RTC ====================
try:
    from drivers.ds1302 import DS1302
    shared.ds1302 = DS1302(DS1302_CLK, DS1302_DAT, DS1302_RST)
    shared.ds1302.datetime()
    print("DS1302 初始化成功")
except Exception as e:
    print("DS1302 初始化失败:", e)


# ==================== WiFi (仅创建对象, active+connect 在 wifi.py 中) ====================
gc.collect()
try:
    shared.wlan = network.WLAN(network.STA_IF)
except Exception as e:
    print("WiFi 初始化失败:", e)
    shared.wlan = None
if shared.wlan is not None:
    try:
        wifi.start_wifi_connection()
    except Exception as e:
        print("WiFi 连接失败:", e)


# ==================== TFT 初始化 (WiFi 之后) ====================
def tft_hard_reset():
    rst = Pin(TFT_RST, Pin.OUT)
    rst.value(1)
    time.sleep_ms(10)
    rst.value(0)
    time.sleep_ms(10)
    rst.value(1)
    time.sleep_ms(120)

tft_hard_reset()

spi_tft = SPI(1, baudrate=10000000, polarity=0, phase=0,
              sck=Pin(TFT_CLK), mosi=Pin(TFT_MOSI), miso=None)
shared.tft = ili9341.Display(spi_tft, cs=Pin(TFT_CS), dc=Pin(TFT_DC),
                              rst=Pin(TFT_RST), width=240, height=320)
Pin(TFT_BL, Pin.OUT, value=1)


# ==================== 时间 ====================
if not wifi.is_system_time_valid():
    print("系统时间无效, 尝试 DS1302...")
    wifi.set_system_time_from_ds1302()


# ==================== SD 卡 ====================
logger.init_sd()


# ==================== 初始界面 ====================
ui.draw_static_background()
ui.update_time()
ui.update_wifi_status()
ui.update_sd_status()


# ==================== MQTT ====================
mqtt_pub = None
try:
    mqtt_pub = mqtt.MQTTPublisher()
    mqtt_cfg = cfg['mqtt']
    if mqtt_cfg.get('broker'):
        mqtt_pub.configure(
            broker=mqtt_cfg['broker'],
            port=mqtt_cfg['port'],
            user=mqtt_cfg.get('user', ''),
            password=mqtt_cfg.get('password', ''),
            topic=mqtt_cfg.get('pub_topic', 'sensor/data')
        )
except Exception as e:
    print("MQTT 初始化失败:", e)


# ==================== 异步主循环 ====================
shared.uptime_start = time.time()
last_sensor_read = 0
last_log_time = 0
last_temp_str = None
last_hum_str = None
consec_fails = 0
error_shown = False


async def main():
    global last_sensor_read, last_log_time, last_temp_str, last_hum_str
    global consec_fails, error_shown

    web_started = False
    web_mod = None
    if web_enabled:
        try:
            from app import web as web_mod
            asyncio.create_task(web_mod.start(port=80))
            web_started = True
        except Exception as e:
            print("Web 启动失败:", e)

    temp = 0.0
    hum = 0.0
    sensor_ok = False
    fmt = "{:.1f}" if shared.sensor_decimal else "{:.0f}"

    while True:
        now = time.time()

        if not web_started and shared.ap_active:
            try:
                if web_mod is None:
                    from app import web as web_mod
                asyncio.create_task(web_mod.start(port=80))
                web_started = True
            except Exception as e:
                print("Web 启动失败:", e)

        if now - last_sensor_read >= shared.sensor_interval:
            sensor_ok = False
            for _ in range(3):
                try:
                    shared.sensor.measure()
                    await asyncio.sleep(0.05)
                    temp = shared.sensor.temperature()
                    hum = shared.sensor.humidity()
                except Exception:
                    await asyncio.sleep(0.2)
                    continue
                if temp is not None and hum is not None:
                    sensor_ok = True
                    break
                await asyncio.sleep(0.2)

            if sensor_ok:
                shared.latest_temp = temp
                shared.latest_hum = hum
                if error_shown:
                    error_shown = False
                    ui.clear_error()
                    last_temp_str = last_hum_str = None

                last_temp_str = ui.draw_number(ui.TEMP_NUM_X, ui.TEMP_NUM_Y,
                                               fmt.format(temp), last_temp_str,
                                               ui.COLOR_TEMP, ui.COLOR_TEMP_GHOST)
                last_hum_str = ui.draw_number(ui.HUM_NUM_X, ui.HUM_NUM_Y,
                                               fmt.format(hum), last_hum_str,
                                               ui.COLOR_HUM, ui.COLOR_HUM_GHOST)
                if web_mod is not None:
                    web_mod.add_history(temp, hum)
                consec_fails = 0
            else:
                consec_fails += 1
                if consec_fails >= 2 and not error_shown:
                    error_shown = True
                    ui.show_temp_error()
                    ui.show_hum_error()
                    last_temp_str = last_hum_str = None

            last_sensor_read = now

        wifi.check_wifi_status()

        if shared.wlan is not None and shared.wlan.isconnected() and (
            now - shared.last_ntp_sync_time > shared.ntp_sync_interval
            or shared.last_ntp_sync_time == 0
        ):
            if wifi.sync_time_from_ntp():
                ui.reset_time_display()

        ui.update_time()
        ui.update_wifi_status()
        ui.update_sd_status()

        if sensor_ok and mqtt_pub is not None and mqtt_pub.broker:
            mqtt_pub.loop(temp, hum)

        if sensor_ok and now - last_log_time >= shared.log_interval:
            if wifi.is_system_time_valid():
                logger.log_data(temp, hum)
            last_log_time = now

        await asyncio.sleep(0.2)


if __name__ == "__main__":
    asyncio.run(main())
