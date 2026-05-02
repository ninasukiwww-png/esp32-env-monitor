# main.py - 环境监测仪 (ESP32 + ILI9341)
# 屏幕：240x320 ILI9341，支持 DHT22/DHT11，SD 卡日志，DS1302 RTC
# 修复数码管刷新少段问题：数字变化时全清重绘，保证显示完整
# ============================================================================

import builtins
import json
import time
import network
import ntptime
import os
from machine import Pin, SPI, RTC, I2C
import ili9341
import dht

# ---------- 尝试导入 SDCard ----------
try:
    from sdcard import SDCard
    SD_AVAILABLE = True
except ImportError:
    SD_AVAILABLE = False
    print("警告: sdcard 模块未找到，SD 日志禁用")


# ===================== 用户配置 =====================
WIFI_SSID = '901'
WIFI_PASSWORD = '15212609205'

SENSOR_TYPE = 'DHT22'               # 仅用于实例化，不影响后续逻辑
LOG_MAX_SIZE = 1024 * 1024          # 日志文件最大 1MB

# 固定采样参数
SENSOR_READ_INTERVAL = 2.0          # 统一 2 秒采样间隔
USE_DECIMAL = True                  # 始终显示一位小数

MAIN_LOOP_DELAY = 0.2
MAX_READ_RETRIES = 3
ERROR_DISPLAY_THRESHOLD = 2
WIFI_RETRY_INTERVAL = 30            # Wi-Fi 重连冷却时间（秒）
NTP_SYNC_INTERVAL = 24 * 3600       # NTP 同步间隔（24小时）


# ===================== 硬件引脚定义 =====================
TFT_CLK  = 19
TFT_MOSI = 18
TFT_DC   = 17
TFT_CS   = 4
TFT_RST  = 5
TFT_BL   = 16

DHT_PIN  = 13

DS1302_CLK = 12
DS1302_DAT = 14
DS1302_RST = 27

SD_SCK  = 33
SD_MOSI = 25
SD_MISO = 26
SD_CS   = 32


# ===================== DS1302 驱动 =====================
class DS1302:
    """DS1302 实时时钟驱动"""
    REG_SECOND = 0x80
    REG_MINUTE = 0x82
    REG_HOUR   = 0x84
    REG_DATE   = 0x86
    REG_MONTH  = 0x88
    REG_DAY    = 0x8A
    REG_YEAR   = 0x8C
    REG_WP     = 0x8E
    REG_BURST  = 0xBE

    def __init__(self, clk_pin, dat_pin, rst_pin):
        self.clk = Pin(clk_pin, Pin.OUT)
        self.dat = Pin(dat_pin, Pin.OUT)
        self.rst = Pin(rst_pin, Pin.OUT)
        self.clk.value(0)
        self.rst.value(0)

    def _write_byte(self, data):
        for i in range(8):
            self.dat.value(data & 0x01)
            self.clk.value(1)
            data >>= 1
            self.clk.value(0)

    def _read_byte(self):
        self.dat.init(Pin.IN)
        data = 0
        for i in range(8):
            data |= (self.dat.value() << i)
            self.clk.value(1)
            self.clk.value(0)
        self.dat.init(Pin.OUT)
        return data

    def _write_reg(self, reg, value):
        self.rst.value(1)
        self._write_byte(reg)
        self._write_byte(value)
        self.rst.value(0)

    def _read_reg(self, reg):
        self.rst.value(1)
        self._write_byte(reg | 0x01)
        data = self._read_byte()
        self.rst.value(0)
        return data

    def _bcd_to_dec(self, bcd):
        return ((bcd >> 4) * 10) + (bcd & 0x0F)

    def _dec_to_bcd(self, dec):
        return ((dec // 10) << 4) | (dec % 10)

    def datetime(self, t=None):
        if t is not None:
            y, m, d, wd, hh, mm, ss, _ = t
            self._write_reg(self.REG_WP, 0x00)
            self._write_reg(self.REG_SECOND, self._dec_to_bcd(ss))
            self._write_reg(self.REG_MINUTE, self._dec_to_bcd(mm))
            self._write_reg(self.REG_HOUR,   self._dec_to_bcd(hh))
            self._write_reg(self.REG_DATE,   self._dec_to_bcd(d))
            self._write_reg(self.REG_MONTH,  self._dec_to_bcd(m))
            self._write_reg(self.REG_DAY,    self._dec_to_bcd(wd + 1))
            self._write_reg(self.REG_YEAR,   self._dec_to_bcd(y % 100))
            self._write_reg(self.REG_WP, 0x80)
        else:
            ss  = self._bcd_to_dec(self._read_reg(self.REG_SECOND) & 0x7F)
            mm  = self._bcd_to_dec(self._read_reg(self.REG_MINUTE))
            hh  = self._bcd_to_dec(self._read_reg(self.REG_HOUR) & 0x3F)
            d   = self._bcd_to_dec(self._read_reg(self.REG_DATE))
            m   = self._bcd_to_dec(self._read_reg(self.REG_MONTH))
            wd  = self._bcd_to_dec(self._read_reg(self.REG_DAY)) - 1
            y   = self._bcd_to_dec(self._read_reg(self.REG_YEAR)) + 2000
            return (y, m, d, wd, hh, mm, ss, 0)


# ===================== 屏幕初始化 =====================
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
tft = ili9341.Display(spi_tft, cs=Pin(TFT_CS), dc=Pin(TFT_DC),
                      rst=Pin(TFT_RST), width=240, height=320)
backlight = Pin(TFT_BL, Pin.OUT, value=1)

def rgb(r, g, b):
    return ili9341.color565(r, g, b)


# ===================== 七段数码管绘制（全清重绘版，杜绝少段）=====================
SEG_THICK = 6

SEGMENTS = {
    'a': (10, 5, 30, 5),
    'b': (35, 10, 35, 30),
    'c': (35, 35, 35, 55),
    'd': (10, 60, 30, 60),
    'e': (5, 35, 5, 55),
    'f': (5, 10, 5, 30),
    'g': (10, 32, 30, 32)
}

DIGIT_SEGS = {
    '0': 'abcdef',
    '1': 'bc',
    '2': 'abdeg',
    '3': 'abcdg',
    '4': 'bcfg',
    '5': 'acdfg',
    '6': 'acdefg',
    '7': 'abc',
    '8': 'abcdefg',
    '9': 'abcdfg',
    '-': 'g',
    ' ': ''
}

# ---------- 小字号定义（用于小数部分） ----------
SMALL_SCALE = 0.5
SMALL_THICK = max(2, int(SEG_THICK * SMALL_SCALE))

def _scale_segments(segments, scale, thick):
    """缩放段坐标并返回新字典，保证底部对齐"""
    new_segs = {}
    BIG_BOTTOM_Y = 60 + SEG_THICK // 2
    small_bottom_y = int(60 * scale) + thick // 2
    y_offset = BIG_BOTTOM_Y - small_bottom_y

    for name, (x1, y1, x2, y2) in segments.items():
        nx1 = int(x1 * scale)
        ny1 = int(y1 * scale) + y_offset
        nx2 = int(x2 * scale)
        ny2 = int(y2 * scale) + y_offset
        new_segs[name] = (nx1, ny1, nx2, ny2)
    return new_segs

SMALL_SEGMENTS = _scale_segments(SEGMENTS, SMALL_SCALE, SMALL_THICK)

def get_char_bbox(segments, thick):
    """计算当前字符集的包围盒（相对于左上角）"""
    min_x = 999
    max_x = 0
    min_y = 999
    max_y = 0
    for (x1, y1, x2, y2) in segments.values():
        if y1 == y2:  # 横线
            lx = min(x1, x2) - thick // 2
            rx = max(x1, x2) + thick // 2
            ly = y1 - thick // 2
            ry = y1 + thick // 2
        else:         # 竖线
            lx = x1 - thick // 2
            rx = x1 + thick // 2
            ly = min(y1, y2)
            ry = max(y1, y2)
        min_x = min(min_x, lx)
        max_x = max(max_x, rx)
        min_y = min(min_y, ly)
        max_y = max(max_y, ry)
    return (min_x - 1, min_y - 1, max_x - min_x + 2, max_y - min_y + 2)

BIG_BBOX = get_char_bbox(SEGMENTS, SEG_THICK)
SMALL_BBOX = get_char_bbox(SMALL_SEGMENTS, SMALL_THICK)

def clear_char_area(x, y, segments, thick, bg_color):
    """清除整个数字位区域（用背景色填充）"""
    if segments is SEGMENTS:
        off_x, off_y, w, h = BIG_BBOX
    else:
        off_x, off_y, w, h = SMALL_BBOX
    tft.fill_rectangle(x + off_x, y + off_y, w, h, bg_color)

def draw_seg_line_scaled(x, y, seg_name, color, segments, thick):
    """通用线段绘制"""
    if seg_name not in segments:
        return
    x1, y1, x2, y2 = segments[seg_name]
    if x1 == x2:  # 竖线
        tft.fill_rectangle(x + x1 - thick // 2, y + y1,
                           thick, y2 - y1, color)
    else:         # 横线
        tft.fill_rectangle(x + x1, y + y1 - thick // 2,
                           x2 - x1, thick, color)

def draw_digit_scaled(x, y, new_digit, old_digit, color, ghost_color, bg_color,
                      segments, thick):
    """
    绘制单个数字：
    - 首次绘制或数字变化时：全清重绘（背景色 -> 幽灵色全段 -> 亮色段）
    - 数字不变时：不做任何操作（保持之前显示）
    """
    if old_digit is None or old_digit == '':
        # 首次绘制
        clear_char_area(x, y, segments, thick, bg_color)
        if ghost_color:
            for seg in 'abcdefg':
                draw_seg_line_scaled(x, y, seg, ghost_color, segments, thick)
        for seg in DIGIT_SEGS.get(new_digit, ''):
            draw_seg_line_scaled(x, y, seg, color, segments, thick)
        return

    if new_digit != old_digit:
        # 数字变化：全清重绘
        clear_char_area(x, y, segments, thick, bg_color)
        if ghost_color:
            for seg in 'abcdefg':
                draw_seg_line_scaled(x, y, seg, ghost_color, segments, thick)
        for seg in DIGIT_SEGS.get(new_digit, ''):
            draw_seg_line_scaled(x, y, seg, color, segments, thick)
    # 数字不变：什么也不做


def draw_number(x, y, num_str, old_str, color, ghost_color):
    """绘制数字串：整数大号，小数小号，数字变化时全清重绘"""
    # 标准化前导零
    if num_str.startswith('.'):
        num_str = '0' + num_str
    if old_str and old_str.startswith('.'):
        old_str = '0' + old_str

    # 分离整数和小数部分
    if '.' in num_str:
        int_part, frac_part = num_str.split('.', 1)
    else:
        int_part, frac_part = num_str, ''
    if old_str and '.' in old_str:
        old_int, old_frac = old_str.split('.', 1)
    else:
        old_int, old_frac = (old_str or ''), ''

    # 绘制整数部分（大号）
    cur_x = x
    max_int_len = max(len(int_part), len(old_int))
    for i in range(max_int_len):
        new_d = int_part[i] if i < len(int_part) else None
        old_d = old_int[i] if i < len(old_int) else None

        if new_d is None and old_d is not None:
            # 位数减少：擦除整个数字位
            clear_char_area(cur_x, y, SEGMENTS, SEG_THICK, COLOR_CARD)
        elif new_d != old_d:
            # 数字变化：全清重绘
            clear_char_area(cur_x, y, SEGMENTS, SEG_THICK, COLOR_CARD)
            if ghost_color:
                for seg in 'abcdefg':
                    draw_seg_line_scaled(cur_x, y, seg, ghost_color, SEGMENTS, SEG_THICK)
            for seg in DIGIT_SEGS.get(new_d, ''):
                draw_seg_line_scaled(cur_x, y, seg, color, SEGMENTS, SEG_THICK)
        # 数字相同且未减少位数：跳过，保留现有显示
        cur_x += 45

    # 绘制小数点
    if frac_part:
        dot_x = cur_x - 3
        dot_y = y + 58
        tft.fill_circle(dot_x, dot_y, SEG_THICK // 2, color)
        if old_frac and not frac_part:
            tft.fill_circle(dot_x, dot_y, SEG_THICK // 2, COLOR_CARD)

    # 绘制小数部分（小号）
    if frac_part:
        cur_x += 5
        small_step = int(45 * SMALL_SCALE)
        max_frac_len = max(len(frac_part), len(old_frac))
        for i in range(max_frac_len):
            new_d = frac_part[i] if i < len(frac_part) else None
            old_d = old_frac[i] if i < len(old_frac) else None

            if new_d is None and old_d is not None:
                clear_char_area(cur_x, y, SMALL_SEGMENTS, SMALL_THICK, COLOR_CARD)
            elif new_d != old_d:
                clear_char_area(cur_x, y, SMALL_SEGMENTS, SMALL_THICK, COLOR_CARD)
                if ghost_color:
                    for seg in 'abcdefg':
                        draw_seg_line_scaled(cur_x, y, seg, ghost_color, SMALL_SEGMENTS, SMALL_THICK)
                for seg in DIGIT_SEGS.get(new_d, ''):
                    draw_seg_line_scaled(cur_x, y, seg, color, SMALL_SEGMENTS, SMALL_THICK)
            cur_x += small_step

    return num_str


# ===================== 单位位图 =====================
# （摄氏度和百分号位图数据保持不变，此处省略以节省篇幅，与之前代码完全相同）
CELSIUS_DATA = bytes([
    0x07, 0xf0, 0x00, 0x07, 0xff, 0xf0,
    0x1f, 0xfc, 0x00, 0x1f, 0xff, 0xfc,
    0x3f, 0xfc, 0x00, 0x7f, 0xff, 0xfc,
    0x3f, 0xfe, 0x00, 0xff, 0xff, 0xfc,
    0x3f, 0xfe, 0x01, 0xff, 0xff, 0xfc,
    0x7f, 0x7f, 0x03, 0xff, 0xff, 0xfc,
    0x7c, 0x1f, 0x07, 0xff, 0xff, 0xfc,
    0x7c, 0x1f, 0x0f, 0xff, 0x00, 0x3c,
    0x78, 0x1f, 0x0f, 0xfe, 0x00, 0x3c,
    0x78, 0x1f, 0x0f, 0xf8, 0x00, 0x00,
    0x7c, 0x1f, 0x1f, 0xf0, 0x00, 0x00,
    0x7c, 0x3f, 0x3f, 0xe0, 0x00, 0x00,
    0x7e, 0x3f, 0x3f, 0xe0, 0x00, 0x00,
    0x7f, 0xfe, 0x3f, 0xc0, 0x00, 0x00,
    0x3f, 0xfe, 0x3f, 0x80, 0x00, 0x00,
    0x3f, 0xfc, 0x7f, 0x00, 0x00, 0x00,
    0x1f, 0xfc, 0x7f, 0x00, 0x00, 0x00,
    0x0f, 0xf8, 0x7f, 0x00, 0x00, 0x00,
    0x07, 0xf0, 0x7f, 0x00, 0x00, 0x00,
    0x00, 0x00, 0xfe, 0x00, 0x00, 0x00,
    0x00, 0x00, 0xfe, 0x00, 0x00, 0x00,
    0x00, 0x00, 0xfe, 0x00, 0x00, 0x00,
    0x00, 0x00, 0xfe, 0x00, 0x00, 0x00,
    0x00, 0x00, 0xfe, 0x00, 0x00, 0x00,
    0x00, 0x00, 0xfe, 0x00, 0x00, 0x00,
    0x00, 0x00, 0xfe, 0x00, 0x00, 0x00,
    0x00, 0x00, 0xfe, 0x00, 0x00, 0x00,
    0x00, 0x00, 0xfe, 0x00, 0x00, 0x00,
    0x00, 0x00, 0xfe, 0x00, 0x00, 0x00,
    0x00, 0x00, 0xfe, 0x00, 0x00, 0x00,
    0x00, 0x00, 0xfe, 0x00, 0x00, 0x00,
    0x00, 0x00, 0xfe, 0x00, 0x00, 0x00,
    0x00, 0x00, 0xfe, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x7f, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x7f, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x7f, 0x80, 0x00, 0x00,
    0x00, 0x00, 0x7f, 0x80, 0x00, 0x00,
    0x00, 0x00, 0x3f, 0xc0, 0x00, 0x00,
    0x00, 0x00, 0x3f, 0xc0, 0x00, 0x00,
    0x00, 0x00, 0x3f, 0xf0, 0x00, 0x00,
    0x00, 0x00, 0x1f, 0xf0, 0x00, 0x00,
    0x00, 0x00, 0x1f, 0xf8, 0x00, 0x1c,
    0x00, 0x00, 0x0f, 0xff, 0x00, 0xfc,
    0x00, 0x00, 0x07, 0xff, 0xff, 0xfc,
    0x00, 0x00, 0x07, 0xff, 0xff, 0xfc,
    0x00, 0x00, 0x03, 0xff, 0xff, 0xfc,
    0x00, 0x00, 0x01, 0xff, 0xff, 0xfc,
    0x00, 0x00, 0x00, 0xff, 0xff, 0xfc,
    0x00, 0x00, 0x00, 0x7f, 0xff, 0xfc,
    0x00, 0x00, 0x00, 0x3f, 0xff, 0xf8,
    0x00, 0x00, 0x00, 0x07, 0xff, 0x80,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00
])

PERCENT_DATA = bytes([
    0x00, 0x7f, 0xc0, 0x00, 0x7c, 0x00,
    0x01, 0xff, 0xf0, 0x00, 0xfc, 0x00,
    0x03, 0xff, 0xf0, 0x00, 0xfc, 0x00,
    0x03, 0xff, 0xf8, 0x01, 0xf8, 0x00,
    0x07, 0xff, 0xf8, 0x01, 0xf8, 0x00,
    0x07, 0xff, 0xfc, 0x03, 0xf8, 0x00,
    0x07, 0xe1, 0xfc, 0x03, 0xf0, 0x00,
    0x0f, 0xc0, 0xfc, 0x07, 0xe0, 0x00,
    0x0f, 0xc0, 0xfc, 0x07, 0xe0, 0x00,
    0x0f, 0x80, 0x7c, 0x0f, 0xe0, 0x00,
    0x0f, 0x80, 0x7c, 0x0f, 0xc0, 0x00,
    0x0f, 0x80, 0x7c, 0x1f, 0x80, 0x00,
    0x0f, 0x80, 0x7c, 0x1f, 0x80, 0x00,
    0x0f, 0x80, 0x7c, 0x3f, 0x80, 0x00,
    0x0f, 0x80, 0x7c, 0x3f, 0x00, 0x00,
    0x0f, 0x80, 0x7c, 0x7f, 0x00, 0x00,
    0x0f, 0x80, 0x7c, 0x7e, 0x00, 0x00,
    0x0f, 0xc0, 0xfc, 0xfe, 0x00, 0x00,
    0x0f, 0xe0, 0xfc, 0xfc, 0x00, 0x00,
    0x07, 0xfb, 0xfd, 0xfc, 0x00, 0x00,
    0x07, 0xff, 0xf9, 0xfc, 0x00, 0x00,
    0x07, 0xff, 0xf9, 0xf8, 0x00, 0x00,
    0x03, 0xff, 0xf3, 0xf0, 0x00, 0x00,
    0x01, 0xff, 0xe7, 0xf0, 0x78, 0x00,
    0x01, 0xff, 0xe7, 0xf0, 0x78, 0x00,
    0x00, 0x7f, 0x87, 0xe3, 0xff, 0x00,
    0x00, 0x00, 0x0f, 0xc7, 0xff, 0x80,
    0x00, 0x00, 0x0f, 0xcf, 0xff, 0xc0,
    0x00, 0x00, 0x1f, 0xdf, 0xff, 0xc0,
    0x00, 0x00, 0x1f, 0x9f, 0xff, 0xe0,
    0x00, 0x00, 0x3f, 0xbf, 0xcf, 0xe0,
    0x00, 0x00, 0x3f, 0x3f, 0x07, 0xf0,
    0x00, 0x00, 0x3f, 0x3f, 0x03, 0xf0,
    0x00, 0x00, 0x7e, 0x3e, 0x03, 0xf0,
    0x00, 0x00, 0xfe, 0x3e, 0x01, 0xf0,
    0x00, 0x00, 0xfc, 0x7e, 0x01, 0xf0,
    0x00, 0x00, 0xfc, 0x7e, 0x01, 0xf0,
    0x00, 0x01, 0xf8, 0x7e, 0x01, 0xf0,
    0x00, 0x03, 0xf8, 0x7e, 0x01, 0xf0,
    0x00, 0x03, 0xf0, 0x7e, 0x01, 0xf0,
    0x00, 0x03, 0xf0, 0x7e, 0x01, 0xf0,
    0x00, 0x07, 0xe0, 0x3e, 0x03, 0xf0,
    0x00, 0x07, 0xe0, 0x3f, 0x03, 0xf0,
    0x00, 0x0f, 0xc0, 0x3f, 0x87, 0xe0,
    0x00, 0x0f, 0xc0, 0x3f, 0x87, 0xe0,
    0x00, 0x1f, 0x80, 0x3f, 0xff, 0xe0,
    0x00, 0x1f, 0x80, 0x1f, 0xff, 0xc0,
    0x00, 0x3f, 0x00, 0x0f, 0xff, 0xc0,
    0x00, 0x3f, 0x00, 0x0f, 0xff, 0x80,
    0x00, 0x3f, 0x00, 0x07, 0xff, 0x00,
    0x00, 0x00, 0x00, 0x01, 0xfc, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00
])

def draw_bitmap(x, y, data, width, height, color, bg_color=None):
    bytes_per_row = (width + 7) // 8
    for row in range(height):
        for col in range(width):
            byte_idx = row * bytes_per_row + col // 8
            bit_idx = 7 - (col % 8)
            if data[byte_idx] & (1 << bit_idx):
                tft.draw_pixel(x + col, y + row, color)
            elif bg_color:
                tft.draw_pixel(x + col, y + row, bg_color)

def draw_thermometer_icon(x, y, color):
    tft.fill_rectangle(x + 4, y + 2, 4, 8, color)
    tft.fill_circle(x + 6, y + 10, 3, color)

def draw_droplet_icon(x, y, color):
    for i in range(6):
        tft.fill_rectangle(x + 3 - i // 2, y + i, i + 1, 1, color)
    tft.fill_circle(x + 6, y + 6, 2, color)


# ===================== 传感器初始化 =====================
if SENSOR_TYPE == 'DHT22':
    sensor = dht.DHT22(Pin(DHT_PIN))
else:
    sensor = dht.DHT11(Pin(DHT_PIN))
time.sleep(1)


# ===================== 外部 RTC 初始化 =====================
ds1302 = None
try:
    ds1302 = DS1302(DS1302_CLK, DS1302_DAT, DS1302_RST)
    ds1302.datetime()  # 测试读取
    print("DS1302 初始化成功")
except Exception as e:
    print("DS1302 初始化失败:", e)


# ===================== WiFi 状态机 =====================
wlan = network.WLAN(network.STA_IF)
wifi_connected = False
wifi_connecting = False
wifi_connect_start = 0
wifi_last_attempt = 0

def start_wifi_connection():
    global wifi_connecting, wifi_connect_start, wifi_last_attempt
    if not wlan.active():
        wlan.active(True)
    if not wlan.isconnected() and not wifi_connecting:
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        wifi_connecting = True
        wifi_connect_start = time.time()
        wifi_last_attempt = time.time()
        update_wifi_status_ui()
        print("开始连接 Wi-Fi:", WIFI_SSID)

def check_wifi_status():
    global wifi_connected, wifi_connecting, wifi_last_attempt
    if wlan.isconnected():
        if not wifi_connected:
            wifi_connected = True
            wifi_connecting = False
            update_wifi_status_ui()
            print("Wi-Fi 已连接, IP:", wlan.ifconfig()[0])
            return True
    else:
        if wifi_connected:
            wifi_connected = False
            wifi_connecting = False
            update_wifi_status_ui()
            print("Wi-Fi 已断开")
        elif wifi_connecting:
            if time.time() - wifi_connect_start > 15:
                wifi_connecting = False
                update_wifi_status_ui()
                print("Wi-Fi 连接超时")
        if not wifi_connecting and not wifi_connected:
            if time.time() - wifi_last_attempt > WIFI_RETRY_INTERVAL:
                start_wifi_connection()
    return wifi_connected


# ===================== 时间管理 =====================
sys_rtc = RTC()

def is_system_time_valid():
    t = time.localtime()
    return t[0] >= 2023

def sync_time_from_ntp():
    global last_ntp_sync_time
    try:
        ntptime.host = 'ntp.aliyun.com'
        ntptime.settime()
        last_ntp_sync_time = time.time()
        print("NTP 同步成功")
        return True
    except Exception as e:
        print("NTP 同步失败:", e)
        return False

def set_system_time_from_ds1302():
    if ds1302 is None:
        return False
    try:
        y, m, d, wd, hh, mm, ss, _ = ds1302.datetime()
        if 2023 <= y <= 2099 and 1 <= m <= 12 and 1 <= d <= 31:
            local_sec = time.mktime((y, m, d, hh, mm, ss, 0, 0))
            utc_sec = local_sec - 8 * 3600
            utc_time = time.localtime(utc_sec)
            sys_rtc.datetime((utc_time[0], utc_time[1], utc_time[2], wd,
                              utc_time[3], utc_time[4], utc_time[5], 0))
            print("系统时间已从 DS1302 恢复")
            return True
    except Exception as e:
        print("从 DS1302 恢复时间失败:", e)
    return False

def get_datetime_fields():
    utc_sec = time.time()
    local_sec = utc_sec + 8 * 3600
    t = time.localtime(local_sec)
    return t[0], t[1], t[2], t[3], t[4], t[5]

def is_time_valid():
    return is_system_time_valid()

if not is_system_time_valid():
    print("系统时间无效，尝试从 DS1302 恢复...")
    set_system_time_from_ds1302()


# ===================== SD 卡日志 =====================
LOG_FILE = None
log_file_initialized = False

def check_log_rotate():
    global LOG_FILE, log_file_initialized
    if LOG_FILE is None:
        return
    try:
        size = os.stat(LOG_FILE)[6]
        if size > LOG_MAX_SIZE:
            backup_name = '/sd/env_data_old.csv'
            try:
                os.remove(backup_name)
            except:
                pass
            os.rename(LOG_FILE, backup_name)
            log_file_initialized = False
            print("日志文件已轮转")
    except:
        pass

def init_sd():
    global SD_AVAILABLE, LOG_FILE, log_file_initialized
    if SD_AVAILABLE:
        try:
            try:
                os.stat('/sd')
                print("SD卡已挂载，跳过初始化")
                return True
            except OSError:
                pass
            spi_sd = SPI(2, baudrate=5000000, polarity=0, phase=0,
                         sck=Pin(SD_SCK), mosi=Pin(SD_MOSI), miso=Pin(SD_MISO))
            sd = SDCard(spi_sd, Pin(SD_CS))
            os.mount(sd, '/sd')
            LOG_FILE = '/sd/env_data.csv'
            check_log_rotate()
            log_file_initialized = False
            update_sd_status_ui()
            print("SD卡挂载成功, 日志文件:", LOG_FILE)
            return True
        except Exception as e:
            print("SD卡挂载失败:", e)
            SD_AVAILABLE = False
            LOG_FILE = None
            update_sd_status_ui()
            return False
    else:
        update_sd_status_ui()
        return False

def log_data(temp, hum):
    global LOG_FILE, log_file_initialized
    if LOG_FILE is None:
        return
    if not is_time_valid():
        return
    try:
        check_log_rotate()
        with open(LOG_FILE, 'a') as f:
            if not log_file_initialized:
                try:
                    f.seek(0)
                    if f.read(1):
                        f.seek(0)
                except:
                    pass
                f.write('timestamp,temperature,humidity\n')
                log_file_initialized = True
            y, m, d, hh, mm, ss = get_datetime_fields()
            ts = f"{y:04d}-{m:02d}-{d:02d} {hh:02d}:{mm:02d}:{ss:02d}"
            f.write(f"{ts},{temp:.1f},{hum:.1f}\n")
    except Exception as e:
        print("日志记录失败:", e)

#配色
COLOR_BG     = rgb(18, 28, 40)    # 保持不变，深邃感很好
COLOR_CARD   = rgb(26, 36, 52)    # 微提 2 点亮，与 BG 拉开细微层次
COLOR_BORDER = rgb(45, 65, 85)    # 降低饱和度，更融合
COLOR_TEMP   = rgb(255, 190, 110) # 微调让橙色更通透
COLOR_HUM    = rgb(110, 220, 255) # 保持
COLOR_LABEL  = rgb(200, 220, 240) # 提升可读性
COLOR_STATUS = rgb(130, 150, 170) # 稍微提亮
COLOR_ACCENT = rgb(0, 210, 230)   # 更跳脱的科技青
COLOR_ERROR  = rgb(255, 90, 90)   # 保持
COLOR_TEMP_GHOST = rgb(70, 55, 40)
COLOR_HUM_GHOST  = rgb(20, 50, 70)
# 幽灵色不变，完美用于背景柱状图


# ===================== 静态背景绘制 =====================
tft.clear(COLOR_BG)

def draw_rounded_rect_fill(x, y, w, h, r, color):
    tft.fill_rectangle(x + r, y, w - 2 * r, h, color)
    tft.fill_rectangle(x, y + r, w, h - 2 * r, color)
    tft.fill_circle(x + r, y + r, r, color)
    tft.fill_circle(x + w - r - 1, y + r, r, color)
    tft.fill_circle(x + r, y + h - r - 1, r, color)
    tft.fill_circle(x + w - r - 1, y + h - r - 1, r, color)

draw_rounded_rect_fill(10, 45, 220, 110, 4, COLOR_CARD)
tft.draw_line(10, 45, 230, 45, COLOR_ACCENT)
tft.draw_line(10, 155, 230, 155, COLOR_BORDER)
tft.draw_line(12, 46, 228, 46, rgb(60, 70, 85))
tft.draw_line(12, 47, 228, 47, rgb(40, 50, 65))

draw_rounded_rect_fill(10, 165, 220, 110, 4, COLOR_CARD)
tft.draw_line(10, 165, 230, 165, COLOR_ACCENT)
tft.draw_line(10, 275, 230, 275, COLOR_BORDER)
tft.draw_line(12, 166, 228, 166, rgb(60, 70, 85))
tft.draw_line(12, 167, 228, 167, rgb(40, 50, 65))

draw_thermometer_icon(12, 54, COLOR_ACCENT)
tft.draw_text8x8(24, 55, "TEMP", COLOR_LABEL)
tft.draw_line(20, 66, 70, 66, COLOR_ACCENT)
tft.draw_line(20, 67, 50, 67, rgb(100, 100, 120))
tft.draw_line(20, 68, 219, 68, COLOR_ACCENT)

draw_droplet_icon(12, 174, COLOR_ACCENT)
tft.draw_text8x8(24, 175, "HUM", COLOR_LABEL)
tft.draw_line(20, 186, 70, 186, COLOR_ACCENT)
tft.draw_line(20, 187, 50, 187, rgb(100, 100, 120))
tft.draw_line(20, 188, 219, 188, COLOR_ACCENT)

TEMP_UNIT_X, TEMP_UNIT_Y = 178, 78
HUM_UNIT_X, HUM_UNIT_Y   = 178, 198
draw_bitmap(TEMP_UNIT_X, TEMP_UNIT_Y, CELSIUS_DATA, 48, 64, COLOR_TEMP)
draw_bitmap(HUM_UNIT_X, HUM_UNIT_Y, PERCENT_DATA, 48, 64, COLOR_HUM)

TEMP_NUM_X, TEMP_NUM_Y = 18, 78
HUM_NUM_X, HUM_NUM_Y   = 18, 198


# ===================== 状态栏 =====================
last_year = last_month = last_day = -1
last_hour = last_min = last_sec = -1

def reset_time_display_state():
    global last_year, last_month, last_day, last_hour, last_min, last_sec
    last_year = last_month = last_day = -1
    last_hour = last_min = last_sec = -1

def update_time_fields():
    global last_year, last_month, last_day, last_hour, last_min, last_sec
    y, m, d, hh, mm, ss = get_datetime_fields()

    if (y, m, d) != (last_year, last_month, last_day):
        tft.fill_rectangle(5, 5, 88, 8, COLOR_BG)
        tft.draw_text8x8(5, 5, f"{y:04d}-{m:02d}-{d:02d}", COLOR_STATUS)
        last_year, last_month, last_day = y, m, d

    if hh != last_hour:
        tft.fill_rectangle(93, 5, 16, 8, COLOR_BG)
        tft.draw_text8x8(93, 5, f"{hh:02d}", COLOR_STATUS)
        last_hour = hh

    if mm != last_min:
        tft.fill_rectangle(117, 5, 16, 8, COLOR_BG)
        tft.draw_text8x8(117, 5, f"{mm:02d}", COLOR_STATUS)
        last_min = mm

    if ss != last_sec:
        tft.fill_rectangle(141, 5, 16, 8, COLOR_BG)
        tft.draw_text8x8(141, 5, f"{ss:02d}", COLOR_STATUS)
        last_sec = ss

    if hh != last_hour or mm != last_min:
        tft.draw_text8x8(109, 5, ":", COLOR_STATUS)
        tft.draw_text8x8(133, 5, ":", COLOR_STATUS)

tft.fill_rectangle(0, 0, 240, 35, COLOR_BG)
tft.draw_text8x8(109, 5, ":", COLOR_STATUS)
tft.draw_text8x8(133, 5, ":", COLOR_STATUS)
update_time_fields()


# ===================== WiFi / SD 状态指示 =====================
last_wifi_state = None
last_wifi_anim_toggle = time.ticks_ms()
wifi_anim_state = False

def update_wifi_status_ui():
    global last_wifi_state, last_wifi_anim_toggle, wifi_anim_state

    if wifi_connected:
        state = 'connected'
        color = rgb(0, 200, 0)
    elif wifi_connecting:
        state = 'connecting'
        now = time.ticks_ms()
        if time.ticks_diff(now, last_wifi_anim_toggle) > 500:
            wifi_anim_state = not wifi_anim_state
            last_wifi_anim_toggle = now
        color = rgb(200, 200, 0) if wifi_anim_state else rgb(80, 80, 0)
    else:
        state = 'disconn'
        color = rgb(200, 0, 0)

    if state == last_wifi_state and not wifi_connecting:
        return

    tft.fill_rectangle(190, 2, 50, 14, COLOR_BG)

    if wifi_connecting and not wifi_anim_state:
        tft.fill_circle(195, 8, 4, COLOR_BG)
        tft.fill_circle(195, 8, 3, color)
    else:
        tft.fill_circle(195, 8, 4, color)

    tft.draw_text8x8(203, 5, "WiFi", COLOR_STATUS)
    last_wifi_state = state

last_sd_state = None

def update_sd_status_ui():
    global last_sd_state
    state = 'ok' if LOG_FILE else 'fail'
    if state == last_sd_state:
        return
    tft.fill_rectangle(190, 16, 50, 14, COLOR_BG)
    color = rgb(0, 200, 0) if LOG_FILE else rgb(200, 0, 0)
    tft.fill_circle(195, 22, 4, color)
    tft.draw_text8x8(203, 19, "SD", COLOR_STATUS)
    last_sd_state = state

tft.draw_line(0, 32, 239, 32, COLOR_BORDER)

start_wifi_connection()
init_sd()
update_wifi_status_ui()
update_sd_status_ui()


# ===================== 传感器错误处理 =====================
def clear_error_display():
    draw_rounded_rect_fill(10, 45, 220, 110, 4, COLOR_CARD)
    draw_rounded_rect_fill(10, 165, 220, 110, 4, COLOR_CARD)
    tft.draw_line(10, 45, 230, 45, COLOR_ACCENT)
    tft.draw_line(10, 155, 230, 155, COLOR_BORDER)
    tft.draw_line(10, 165, 230, 165, COLOR_ACCENT)
    tft.draw_line(10, 275, 230, 275, COLOR_BORDER)
    draw_thermometer_icon(12, 54, COLOR_ACCENT)
    tft.draw_text8x8(24, 55, "TEMP", COLOR_LABEL)
    draw_droplet_icon(12, 174, COLOR_ACCENT)
    tft.draw_text8x8(24, 175, "HUM", COLOR_LABEL)
    draw_bitmap(TEMP_UNIT_X, TEMP_UNIT_Y, CELSIUS_DATA, 48, 64, COLOR_TEMP)
    draw_bitmap(HUM_UNIT_X, HUM_UNIT_Y, PERCENT_DATA, 48, 64, COLOR_HUM)

def show_temp_error():
    tft.fill_rectangle(TEMP_NUM_X, TEMP_NUM_Y, 140, 70, COLOR_CARD)
    tft.draw_text8x8(TEMP_NUM_X + 10, TEMP_NUM_Y + 30, "ERROR", COLOR_ERROR)

def show_hum_error():
    tft.fill_rectangle(HUM_NUM_X, HUM_NUM_Y, 140, 70, COLOR_CARD)
    tft.draw_text8x8(HUM_NUM_X + 10, HUM_NUM_Y + 30, "ERROR", COLOR_ERROR)


# ===================== 全局变量 =====================
latest_temp = 0.0
latest_hum = 0.0
uptime_start = time.time()
last_ntp_sync_time = 0


# ===================== 主循环 =====================
last_sensor_read = 0
last_log_time = 0
last_temp_str = None
last_hum_str = None
consec_fails = 0
error_displayed = False

def main():
    global last_sensor_read, last_log_time, last_temp_str, last_hum_str
    global consec_fails, error_displayed, last_ntp_sync_time
    global latest_temp, latest_hum

    temp = 0.0
    hum = 0.0
    sensor_ok = False

    while True:
        now = time.time()

        if now - last_sensor_read >= SENSOR_READ_INTERVAL:
            sensor_ok = False
            for attempt in range(MAX_READ_RETRIES):
                try:
                    sensor.measure()
                    time.sleep_ms(50)
                    temp = sensor.temperature()
                    hum = sensor.humidity()
                    if temp is not None and hum is not None:
                        sensor_ok = True
                        break
                except OSError:
                    pass
                time.sleep_ms(200)

            if sensor_ok:
                latest_temp = temp
                latest_hum = hum
                if error_displayed:
                    error_displayed = False
                    clear_error_display()
                    last_temp_str = None
                    last_hum_str = None

                temp_str = f"{temp:.1f}"
                hum_str = f"{hum:.1f}"

                last_temp_str = draw_number(TEMP_NUM_X, TEMP_NUM_Y, temp_str, last_temp_str,
                                            COLOR_TEMP, COLOR_TEMP_GHOST)
                last_hum_str = draw_number(HUM_NUM_X, HUM_NUM_Y, hum_str, last_hum_str,
                                           COLOR_HUM, COLOR_HUM_GHOST)

                consec_fails = 0
            else:
                consec_fails += 1
                if consec_fails >= ERROR_DISPLAY_THRESHOLD and not error_displayed:
                    error_displayed = True
                    show_temp_error()
                    show_hum_error()
                    last_temp_str = last_hum_str = None

            last_sensor_read = now

        check_wifi_status()

        if wifi_connected and (now - last_ntp_sync_time > NTP_SYNC_INTERVAL or last_ntp_sync_time == 0):
            if sync_time_from_ntp():
                last_ntp_sync_time = now
                reset_time_display_state()
                update_time_fields()

        update_time_fields()
        update_wifi_status_ui()
        update_sd_status_ui()

        if sensor_ok and (now - last_log_time >= 60):
            if is_time_valid():
                log_data(temp, hum)
            last_log_time = now

        time.sleep(MAIN_LOOP_DELAY)

if __name__ == "__main__":
    main()

