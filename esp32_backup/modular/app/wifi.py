# app/wifi.py - WiFi 连接管理 + 时间同步
import time
import network
import ntptime
import gc
from machine import RTC
from app import shared

sys_rtc = RTC()


def start_wifi_connection():
    if shared.wlan is None:
        return
    try:
        if not shared.wlan.active():
            gc.collect()
            shared.wlan.active(True)
            time.sleep(1)
    except Exception as e:
        print("WiFi 激活失败:", e)
        gc.collect()
        return
    if not shared.wlan.isconnected() and not shared.wifi_connecting:
        try:
            shared.wlan.connect(shared.wifi_ssid, shared.wifi_password)
        except Exception as e:
            print("WiFi connect 失败:", e)
            return
        shared.wifi_connecting = True
        shared.wifi_connect_start = time.time()
        shared.wifi_last_attempt = time.time()
        print("连接 Wi-Fi:", shared.wifi_ssid)


def check_wifi_status():
    if shared.wlan is None:
        return False
    if shared.wlan.isconnected():
        if not shared.wifi_connected:
            shared.wifi_connected = True
            shared.wifi_connecting = False
            shared.consec_wifi_fails = 0
            if shared.ap_active:
                stop_ap_mode()
            print("Wi-Fi 已连接, IP:", shared.wlan.ifconfig()[0])
        return True
    else:
        if shared.wifi_connected:
            shared.wifi_connected = False
            shared.wifi_connecting = False
            print("Wi-Fi 已断开")
        elif shared.wifi_connecting:
            if time.time() - shared.wifi_connect_start > 15:
                shared.wifi_connecting = False
                shared.consec_wifi_fails += 1
                print("Wi-Fi 连接超时 ({}次)".format(shared.consec_wifi_fails))
        if not shared.wifi_connecting and not shared.wifi_connected:
            if shared.wlan is None:
                return False
            if shared.consec_wifi_fails >= AP_MAX_FAILS and not shared.ap_active:
                start_ap_mode()
            elif time.time() - shared.wifi_last_attempt > 30:
                start_wifi_connection()
    return shared.wifi_connected


AP_MAX_FAILS = 4


def start_ap_mode():
    if shared.ap_active:
        return
    try:
        gc.collect()
        shared.wlan.active(True)
        ap = network.WLAN(network.AP_IF)
        ap.active(True)
        ap.config(essid=shared.ap_ssid, authmode=network.AUTH_OPEN)
        shared.ap_active = True
        print("AP 模式已启动, SSID:", shared.ap_ssid)
    except Exception as e:
        print("AP 模式启动失败:", e)


def stop_ap_mode():
    if not shared.ap_active:
        return
    try:
        ap = network.WLAN(network.AP_IF)
        ap.active(False)
    except Exception:
        pass
    shared.ap_active = False
    print("AP 模式已关闭")


def is_ap_active():
    try:
        ap = network.WLAN(network.AP_IF)
        return ap.active() and shared.ap_active
    except Exception:
        return False


def is_system_time_valid():
    t = time.localtime()
    return t[0] >= 2023


def sync_time_from_ntp():
    try:
        ntptime.host = shared.ntp_server
        ntptime.settime()
        shared.last_ntp_sync_time = time.time()
        print("NTP 同步成功")
        return True
    except Exception as e:
        print("NTP 同步失败:", e)
        return False


def set_system_time_from_ds1302():
    if shared.ds1302 is None:
        return False
    try:
        y, m, d, wd, hh, mm, ss, _ = shared.ds1302.datetime()
        if 2023 <= y <= 2099 and 1 <= m <= 12 and 1 <= d <= 31:
            local_sec = time.mktime((y, m, d, hh, mm, ss, 0, 0))
            utc_sec = local_sec - shared.timezone_offset * 3600
            utc_time = time.localtime(utc_sec)
            sys_rtc.datetime((
                utc_time[0], utc_time[1], utc_time[2], wd,
                utc_time[3], utc_time[4], utc_time[5], 0
            ))
            print("系统时间已从 DS1302 恢复")
            return True
    except Exception as e:
        print("DS1302 恢复时间失败:", e)
    return False


def get_datetime_fields():
    utc_sec = time.time()
    local_sec = utc_sec + shared.timezone_offset * 3600
    t = time.localtime(local_sec)
    return t[0], t[1], t[2], t[3], t[4], t[5]
