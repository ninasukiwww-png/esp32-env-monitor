# app/logger.py - SD 卡日志记录 (按天切割 + 统计摘要)
import os
import time
from machine import Pin, SPI
from app import shared, wifi


def _get_today_str():
    y, m, d, _, _, _ = wifi.get_datetime_fields()
    return "{:04d}-{:02d}-{:02d}".format(y, m, d)


def _validate_date_str(s):
    if not s or '..' in s or '/' in s or '\\' in s:
        return False
    if len(s) != 10:
        return False
    return True


def init_sd():
    if not shared.log_enabled:
        print("SD 日志已禁用")
        return False
    try:
        from lib.sdcard import SDCard
    except ImportError:
        print("sdcard 模块未找到")
        return False

    try:
        try:
            os.stat('/sd')
            print("SD 卡已挂载")
            _ensure_log_dir()
            shared.SD_READY = True
            shared.LOG_FILE = shared.LOG_DIR + '/' + _get_today_str() + '.csv'
            return True
        except OSError:
            pass

        spi = SPI(2, baudrate=5000000, polarity=0, phase=0,
                  sck=Pin(33), mosi=Pin(25), miso=Pin(26))
        sd = SDCard(spi, Pin(32))
        os.mount(sd, '/sd')
        _ensure_log_dir()
        shared.SD_READY = True
        shared.LOG_FILE = shared.LOG_DIR + '/' + _get_today_str() + '.csv'
        print("SD 卡挂载成功")
        return True
    except Exception as e:
        print("SD 卡挂载失败:", e)
        shared.SD_READY = False
        shared.LOG_FILE = None
        return False


def _ensure_log_dir():
    try:
        os.mkdir(shared.LOG_DIR)
    except OSError:
        pass


def log_data(temp, hum):
    if not shared.log_enabled or not shared.SD_READY or not wifi.is_system_time_valid():
        return
    try:
        today = _get_today_str()
        filepath = shared.LOG_DIR + '/' + today + '.csv'

        try:
            os.stat(filepath)
        except OSError:
            with open(filepath, 'w') as f:
                f.write('timestamp,temperature,humidity\n')

        with open(filepath, 'a') as f:
            y, m, d, hh, mm, ss = wifi.get_datetime_fields()
            ts = "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(y, m, d, hh, mm, ss)
            f.write("{},{:.1f},{:.1f}\n".format(ts, temp, hum))

    except Exception as e:
        print("日志记录失败:", e)


def get_log_files():
    result = []
    try:
        for name in os.listdir(shared.LOG_DIR):
            if name.endswith('.csv'):
                path = shared.LOG_DIR + '/' + name
                try:
                    s = os.stat(path)
                    result.append({
                        'name': name,
                        'size': s[6],
                        'date': name.replace('.csv', '')
                    })
                except OSError:
                    pass
    except OSError:
        pass
    result.sort(key=lambda x: x['date'], reverse=True)
    return result


def get_log_path(date_str):
    if not _validate_date_str(date_str):
        return None
    return shared.LOG_DIR + '/' + date_str + '.csv'


def iter_log_rows(date_str):
    path = get_log_path(date_str)
    if path is None:
        return
    try:
        with open(path, 'r') as f:
            f.readline()
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(',')
                if len(parts) >= 3:
                    try:
                        yield (parts[0], float(parts[1]), float(parts[2]))
                    except ValueError:
                        pass
    except OSError:
        pass


def get_stats(period='today'):
    today_str = _get_today_str()

    if period == 'today':
        dates = [today_str]
    elif period == 'week':
        dates = _get_date_range(6)
    elif period == 'month':
        dates = _get_date_range(29)
    else:
        dates = [today_str]

    count = 0
    temp_min = 999.0
    temp_max = -999.0
    temp_sum = 0.0
    hum_min = 999.0
    hum_max = -999.0
    hum_sum = 0.0
    days_with_data = 0

    for date_str in dates:
        has_data = False
        for _, t, h in iter_log_rows(date_str):
            has_data = True
            count += 1
            if t < temp_min:
                temp_min = t
            if t > temp_max:
                temp_max = t
            temp_sum += t
            if h < hum_min:
                hum_min = h
            if h > hum_max:
                hum_max = h
            hum_sum += h
        if has_data:
            days_with_data += 1

    if count == 0:
        return {
            'temp': {'min': 0, 'max': 0, 'avg': 0},
            'hum': {'min': 0, 'max': 0, 'avg': 0},
            'data_points': 0,
            'days_covered': 0
        }

    return {
        'temp': {
            'min': round(temp_min, 1),
            'max': round(temp_max, 1),
            'avg': round(temp_sum / count, 1)
        },
        'hum': {
            'min': round(hum_min, 1),
            'max': round(hum_max, 1),
            'avg': round(hum_sum / count, 1)
        },
        'data_points': count,
        'days_covered': days_with_data
    }


def _get_date_range(days_back):
    now = time.time()
    if now < 1000000000:
        return [_get_today_str()]
    dates = []
    for i in range(days_back, -1, -1):
        lt = time.localtime(now - i * 86400)
        dates.append("{:04d}-{:02d}-{:02d}".format(lt[0], lt[1], lt[2]))
    return dates
