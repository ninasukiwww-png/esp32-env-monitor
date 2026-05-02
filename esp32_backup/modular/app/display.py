# app/display.py - TFT 屏幕绘制模块 (ILI9341 240x320)
import time
from lib.ili9341 import color565
from app import shared
from app import wifi as wifi_mod

# ==================== 配色 ====================
COLOR_BG = COLOR_CARD = COLOR_BORDER = None
COLOR_TEMP = COLOR_HUM = COLOR_LABEL = COLOR_STATUS = COLOR_ACCENT = None
COLOR_ERROR = COLOR_TEMP_GHOST = COLOR_HUM_GHOST = None

def _init_colors():
    global COLOR_BG, COLOR_CARD, COLOR_BORDER
    global COLOR_TEMP, COLOR_HUM, COLOR_LABEL, COLOR_STATUS, COLOR_ACCENT
    global COLOR_ERROR, COLOR_TEMP_GHOST, COLOR_HUM_GHOST
    if COLOR_BG is not None:
        return
    COLOR_BG     = color565(18, 28, 40)
    COLOR_CARD   = color565(26, 36, 52)
    COLOR_BORDER = color565(45, 65, 85)
    COLOR_TEMP   = color565(255, 190, 110)
    COLOR_HUM    = color565(110, 220, 255)
    COLOR_LABEL  = color565(200, 220, 240)
    COLOR_STATUS = color565(130, 150, 170)
    COLOR_ACCENT = color565(0, 210, 230)
    COLOR_ERROR  = color565(255, 90, 90)
    COLOR_TEMP_GHOST = color565(70, 55, 40)
    COLOR_HUM_GHOST  = color565(20, 50, 70)

# ==================== 七段数码管定义 ====================
SEG_THICK = 6

SEGMENTS = {
    'a': (10, 5, 30, 5), 'b': (35, 10, 35, 30), 'c': (35, 35, 35, 55),
    'd': (10, 60, 30, 60), 'e': (5, 35, 5, 55), 'f': (5, 10, 5, 30),
    'g': (10, 32, 30, 32)
}

DIGIT_SEGS = {
    '0': 'abcdef', '1': 'bc', '2': 'abdeg', '3': 'abcdg',
    '4': 'bcfg', '5': 'acdfg', '6': 'acdefg', '7': 'abc',
    '8': 'abcdefg', '9': 'abcdfg', '-': 'g', ' ': ''
}

SMALL_SCALE = 0.5
SMALL_THICK = max(2, int(SEG_THICK * SMALL_SCALE))


def _scale_segments(segments, scale, thick):
    new_segs = {}
    bottom_y = 60 + SEG_THICK // 2
    sb = int(60 * scale) + thick // 2
    offset = bottom_y - sb
    for name, (x1, y1, x2, y2) in segments.items():
        new_segs[name] = (int(x1 * scale), int(y1 * scale) + offset,
                          int(x2 * scale), int(y2 * scale) + offset)
    return new_segs

SMALL_SEGMENTS = _scale_segments(SEGMENTS, SMALL_SCALE, SMALL_THICK)


def _get_char_bbox(segments, thick):
    min_x = min_y = 999
    max_x = max_y = 0
    for x1, y1, x2, y2 in segments.values():
        if y1 == y2:
            lx = min(x1, x2) - thick // 2
            rx = max(x1, x2) + thick // 2
            ly = y1 - thick // 2
            ry = y1 + thick // 2
        else:
            lx = x1 - thick // 2
            rx = x1 + thick // 2
            ly = min(y1, y2)
            ry = max(y1, y2)
        min_x = min(min_x, lx)
        max_x = max(max_x, rx)
        min_y = min(min_y, ly)
        max_y = max(max_y, ry)
    return (min_x - 1, min_y - 1, max_x - min_x + 2, max_y - min_y + 2)

BIG_BBOX = _get_char_bbox(SEGMENTS, SEG_THICK)
SMALL_BBOX = _get_char_bbox(SMALL_SEGMENTS, SMALL_THICK)

TEMP_NUM_X, TEMP_NUM_Y = 18, 78
HUM_NUM_X, HUM_NUM_Y = 18, 198
TEMP_UNIT_X, TEMP_UNIT_Y = 178, 78
HUM_UNIT_X, HUM_UNIT_Y = 178, 198


# ==================== 数码管绘制函数 ====================

def _clear_char(x, y, segments, thick):
    bbox = BIG_BBOX if segments is SEGMENTS else SMALL_BBOX
    shared.tft.fill_rectangle(x + bbox[0], y + bbox[1], bbox[2], bbox[3], COLOR_CARD)


def _draw_seg(x, y, name, color, segments, thick):
    if name not in segments:
        return
    x1, y1, x2, y2 = segments[name]
    if x1 == x2:
        shared.tft.fill_rectangle(x + x1 - thick // 2, y + y1, thick, y2 - y1, color)
    else:
        shared.tft.fill_rectangle(x + x1, y + y1 - thick // 2, x2 - x1, thick, color)


def draw_number(x, y, num_str, old_str, color, ghost_color):
    if num_str.startswith('.'):
        num_str = '0' + num_str
    if old_str and old_str.startswith('.'):
        old_str = '0' + old_str

    int_part, frac_part = (num_str.split('.', 1) if '.' in num_str else (num_str, ''))
    old_int, old_frac = (
        (old_str.split('.', 1) if '.' in old_str else (old_str or '', ''))
        if old_str else ('', '')
    )

    cur_x = x
    for i in range(max(len(int_part), len(old_int))):
        nd = int_part[i] if i < len(int_part) else None
        od = old_int[i] if i < len(old_int) else None
        if nd is None and od is not None:
            _clear_char(cur_x, y, SEGMENTS, SEG_THICK)
        elif nd != od:
            _clear_char(cur_x, y, SEGMENTS, SEG_THICK)
            if ghost_color:
                for seg in 'abcdefg':
                    _draw_seg(cur_x, y, seg, ghost_color, SEGMENTS, SEG_THICK)
            for seg in DIGIT_SEGS.get(nd, ''):
                _draw_seg(cur_x, y, seg, color, SEGMENTS, SEG_THICK)
        cur_x += 45

    if frac_part:
        shared.tft.fill_circle(cur_x - 3, y + 58, SEG_THICK // 2, color)
        cur_x += 5
        step = int(45 * SMALL_SCALE)
        for i in range(max(len(frac_part), len(old_frac))):
            nd = frac_part[i] if i < len(frac_part) else None
            od = old_frac[i] if i < len(old_frac) else None
            if nd is None and od is not None:
                _clear_char(cur_x, y, SMALL_SEGMENTS, SMALL_THICK)
            elif nd != od:
                _clear_char(cur_x, y, SMALL_SEGMENTS, SMALL_THICK)
                if ghost_color:
                    for seg in 'abcdefg':
                        _draw_seg(cur_x, y, seg, ghost_color, SMALL_SEGMENTS, SMALL_THICK)
                for seg in DIGIT_SEGS.get(nd, ''):
                    _draw_seg(cur_x, y, seg, color, SMALL_SEGMENTS, SMALL_THICK)
            cur_x += step
    return num_str


# ==================== 单位位图数据 ====================
CELSIUS_DATA = bytes([
    0x07, 0xf0, 0x00, 0x07, 0xff, 0xf0, 0x1f, 0xfc, 0x00, 0x1f, 0xff, 0xfc,
    0x3f, 0xfc, 0x00, 0x7f, 0xff, 0xfc, 0x3f, 0xfe, 0x00, 0xff, 0xff, 0xfc,
    0x3f, 0xfe, 0x01, 0xff, 0xff, 0xfc, 0x7f, 0x7f, 0x03, 0xff, 0xff, 0xfc,
    0x7c, 0x1f, 0x07, 0xff, 0xff, 0xfc, 0x7c, 0x1f, 0x0f, 0xff, 0x00, 0x3c,
    0x78, 0x1f, 0x0f, 0xfe, 0x00, 0x3c, 0x78, 0x1f, 0x0f, 0xf8, 0x00, 0x00,
    0x7c, 0x1f, 0x1f, 0xf0, 0x00, 0x00, 0x7c, 0x3f, 0x3f, 0xe0, 0x00, 0x00,
    0x7e, 0x3f, 0x3f, 0xe0, 0x00, 0x00, 0x7f, 0xfe, 0x3f, 0xc0, 0x00, 0x00,
    0x3f, 0xfe, 0x3f, 0x80, 0x00, 0x00, 0x3f, 0xfc, 0x7f, 0x00, 0x00, 0x00,
    0x1f, 0xfc, 0x7f, 0x00, 0x00, 0x00, 0x0f, 0xf8, 0x7f, 0x00, 0x00, 0x00,
    0x07, 0xf0, 0x7f, 0x00, 0x00, 0x00, 0x00, 0x00, 0xfe, 0x00, 0x00, 0x00,
    0x00, 0x00, 0xfe, 0x00, 0x00, 0x00, 0x00, 0x00, 0xfe, 0x00, 0x00, 0x00,
    0x00, 0x00, 0xfe, 0x00, 0x00, 0x00, 0x00, 0x00, 0xfe, 0x00, 0x00, 0x00,
    0x00, 0x00, 0xfe, 0x00, 0x00, 0x00, 0x00, 0x00, 0xfe, 0x00, 0x00, 0x00,
    0x00, 0x00, 0xfe, 0x00, 0x00, 0x00, 0x00, 0x00, 0xfe, 0x00, 0x00, 0x00,
    0x00, 0x00, 0xfe, 0x00, 0x00, 0x00, 0x00, 0x00, 0xfe, 0x00, 0x00, 0x00,
    0x00, 0x00, 0xfe, 0x00, 0x00, 0x00, 0x00, 0x00, 0xfe, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x7f, 0x00, 0x00, 0x00, 0x00, 0x00, 0x7f, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x7f, 0x80, 0x00, 0x00, 0x00, 0x00, 0x7f, 0x80, 0x00, 0x00,
    0x00, 0x00, 0x3f, 0xc0, 0x00, 0x00, 0x00, 0x00, 0x3f, 0xc0, 0x00, 0x00,
    0x00, 0x00, 0x3f, 0xf0, 0x00, 0x00, 0x00, 0x00, 0x1f, 0xf0, 0x00, 0x00,
    0x00, 0x00, 0x1f, 0xf8, 0x00, 0x1c, 0x00, 0x00, 0x0f, 0xff, 0x00, 0xfc,
    0x00, 0x00, 0x07, 0xff, 0xff, 0xfc, 0x00, 0x00, 0x07, 0xff, 0xff, 0xfc,
    0x00, 0x00, 0x03, 0xff, 0xff, 0xfc, 0x00, 0x00, 0x01, 0xff, 0xff, 0xfc,
    0x00, 0x00, 0x00, 0xff, 0xff, 0xfc, 0x00, 0x00, 0x00, 0x7f, 0xff, 0xfc,
    0x00, 0x00, 0x00, 0x3f, 0xff, 0xf8, 0x00, 0x00, 0x00, 0x07, 0xff, 0x80,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
])

PERCENT_DATA = bytes([
    0x00, 0x7f, 0xc0, 0x00, 0x7c, 0x00, 0x01, 0xff, 0xf0, 0x00, 0xfc, 0x00,
    0x03, 0xff, 0xf0, 0x00, 0xfc, 0x00, 0x03, 0xff, 0xf8, 0x01, 0xf8, 0x00,
    0x07, 0xff, 0xf8, 0x01, 0xf8, 0x00, 0x07, 0xff, 0xfc, 0x03, 0xf8, 0x00,
    0x07, 0xe1, 0xfc, 0x03, 0xf0, 0x00, 0x0f, 0xc0, 0xfc, 0x07, 0xe0, 0x00,
    0x0f, 0xc0, 0xfc, 0x07, 0xe0, 0x00, 0x0f, 0x80, 0x7c, 0x0f, 0xe0, 0x00,
    0x0f, 0x80, 0x7c, 0x0f, 0xc0, 0x00, 0x0f, 0x80, 0x7c, 0x1f, 0x80, 0x00,
    0x0f, 0x80, 0x7c, 0x1f, 0x80, 0x00, 0x0f, 0x80, 0x7c, 0x3f, 0x80, 0x00,
    0x0f, 0x80, 0x7c, 0x3f, 0x00, 0x00, 0x0f, 0x80, 0x7c, 0x7f, 0x00, 0x00,
    0x0f, 0x80, 0x7c, 0x7e, 0x00, 0x00, 0x0f, 0xc0, 0xfc, 0xfe, 0x00, 0x00,
    0x0f, 0xe0, 0xfc, 0xfc, 0x00, 0x00, 0x07, 0xfb, 0xfd, 0xfc, 0x00, 0x00,
    0x07, 0xff, 0xf9, 0xfc, 0x00, 0x00, 0x07, 0xff, 0xf9, 0xf8, 0x00, 0x00,
    0x03, 0xff, 0xf3, 0xf0, 0x00, 0x00, 0x01, 0xff, 0xe7, 0xf0, 0x78, 0x00,
    0x01, 0xff, 0xe7, 0xf0, 0x78, 0x00, 0x00, 0x7f, 0x87, 0xe3, 0xff, 0x00,
    0x00, 0x00, 0x0f, 0xc7, 0xff, 0x80, 0x00, 0x00, 0x0f, 0xcf, 0xff, 0xc0,
    0x00, 0x00, 0x1f, 0xdf, 0xff, 0xc0, 0x00, 0x00, 0x1f, 0x9f, 0xff, 0xe0,
    0x00, 0x00, 0x3f, 0xbf, 0xcf, 0xe0, 0x00, 0x00, 0x3f, 0x3f, 0x07, 0xf0,
    0x00, 0x00, 0x3f, 0x3f, 0x03, 0xf0, 0x00, 0x00, 0x7e, 0x3e, 0x03, 0xf0,
    0x00, 0x00, 0xfe, 0x3e, 0x01, 0xf0, 0x00, 0x00, 0xfc, 0x7e, 0x01, 0xf0,
    0x00, 0x00, 0xfc, 0x7e, 0x01, 0xf0, 0x00, 0x01, 0xf8, 0x7e, 0x01, 0xf0,
    0x00, 0x03, 0xf8, 0x7e, 0x01, 0xf0, 0x00, 0x03, 0xf0, 0x7e, 0x01, 0xf0,
    0x00, 0x03, 0xf0, 0x7e, 0x01, 0xf0, 0x00, 0x07, 0xe0, 0x3e, 0x03, 0xf0,
    0x00, 0x07, 0xe0, 0x3f, 0x03, 0xf0, 0x00, 0x0f, 0xc0, 0x3f, 0x87, 0xe0,
    0x00, 0x0f, 0xc0, 0x3f, 0x87, 0xe0, 0x00, 0x1f, 0x80, 0x3f, 0xff, 0xe0,
    0x00, 0x1f, 0x80, 0x1f, 0xff, 0xc0, 0x00, 0x3f, 0x00, 0x0f, 0xff, 0xc0,
    0x00, 0x3f, 0x00, 0x0f, 0xff, 0x80, 0x00, 0x3f, 0x00, 0x07, 0xff, 0x00,
    0x00, 0x00, 0x00, 0x01, 0xfc, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
])


# ==================== 通用绘制 ====================

def draw_bitmap(x, y, data, width, height, color, bg_color=None):
    bpr = (width + 7) // 8
    for row in range(height):
        for col in range(width):
            idx = row * bpr + col // 8
            if data[idx] & (1 << (7 - col % 8)):
                shared.tft.draw_pixel(x + col, y + row, color)
            elif bg_color:
                shared.tft.draw_pixel(x + col, y + row, bg_color)


def draw_thermometer_icon(x, y, color):
    shared.tft.fill_rectangle(x + 4, y + 2, 4, 8, color)
    shared.tft.fill_circle(x + 6, y + 10, 3, color)


def draw_droplet_icon(x, y, color):
    for i in range(6):
        shared.tft.fill_rectangle(x + 3 - i // 2, y + i, i + 1, 1, color)
    shared.tft.fill_circle(x + 6, y + 6, 2, color)


def draw_rounded_rect(x, y, w, h, r, color):
    shared.tft.fill_rectangle(x + r, y, w - 2 * r, h, color)
    shared.tft.fill_rectangle(x, y + r, w, h - 2 * r, color)
    shared.tft.fill_circle(x + r, y + r, r, color)
    shared.tft.fill_circle(x + w - r - 1, y + r, r, color)
    shared.tft.fill_circle(x + r, y + h - r - 1, r, color)
    shared.tft.fill_circle(x + w - r - 1, y + h - r - 1, r, color)


# ==================== 初始背景 ====================

def draw_static_background():
    _init_colors()
    t = shared.tft
    t.clear(COLOR_BG)
    tc = lambda: color565(60, 70, 85)
    tc2 = lambda: color565(40, 50, 65)
    ac = COLOR_ACCENT
    bc = COLOR_BORDER
    label = COLOR_LABEL

    draw_rounded_rect(10, 45, 220, 110, 4, COLOR_CARD)
    t.draw_line(10, 45, 230, 45, ac)
    t.draw_line(10, 155, 230, 155, bc)
    t.draw_line(12, 46, 228, 46, tc())
    t.draw_line(12, 47, 228, 47, tc2())

    draw_rounded_rect(10, 165, 220, 110, 4, COLOR_CARD)
    t.draw_line(10, 165, 230, 165, ac)
    t.draw_line(10, 275, 230, 275, bc)
    t.draw_line(12, 166, 228, 166, tc())
    t.draw_line(12, 167, 228, 167, tc2())

    draw_thermometer_icon(12, 54, ac)
    t.draw_text8x8(24, 55, "TEMP", label)
    t.draw_line(20, 66, 70, 66, ac)
    t.draw_line(20, 67, 50, 67, color565(100, 100, 120))
    t.draw_line(20, 68, 219, 68, ac)

    draw_droplet_icon(12, 174, ac)
    t.draw_text8x8(24, 175, "HUM", label)
    t.draw_line(20, 186, 70, 186, ac)
    t.draw_line(20, 187, 50, 187, color565(100, 100, 120))
    t.draw_line(20, 188, 219, 188, ac)

    draw_bitmap(TEMP_UNIT_X, TEMP_UNIT_Y, CELSIUS_DATA, 48, 64, COLOR_TEMP)
    draw_bitmap(HUM_UNIT_X, HUM_UNIT_Y, PERCENT_DATA, 48, 64, COLOR_HUM)

    t.draw_line(0, 32, 239, 32, bc)

    t.fill_rectangle(0, 0, 240, 35, COLOR_BG)
    t.draw_text8x8(109, 5, ":", COLOR_STATUS)
    t.draw_text8x8(133, 5, ":", COLOR_STATUS)


# ==================== 状态栏更新时间 ====================
_last_year = _last_month = _last_day = -1
_last_hour = _last_min = _last_sec = -1


def reset_time_display():
    global _last_year, _last_month, _last_day, _last_hour, _last_min, _last_sec
    _last_year = _last_month = _last_day = -1
    _last_hour = _last_min = _last_sec = -1


def update_time():
    global _last_year, _last_month, _last_day, _last_hour, _last_min, _last_sec
    y, m, d, hh, mm, ss = wifi_mod.get_datetime_fields()
    t = shared.tft
    bg = COLOR_BG

    if (y, m, d) != (_last_year, _last_month, _last_day):
        t.fill_rectangle(5, 5, 88, 8, bg)
        t.draw_text8x8(5, 5, "{:04d}-{:02d}-{:02d}".format(y, m, d), COLOR_STATUS)
        _last_year, _last_month, _last_day = y, m, d
    if hh != _last_hour:
        t.fill_rectangle(93, 5, 16, 8, bg)
        t.draw_text8x8(93, 5, "{:02d}".format(hh), COLOR_STATUS)
        _last_hour = hh
    if mm != _last_min:
        t.fill_rectangle(117, 5, 16, 8, bg)
        t.draw_text8x8(117, 5, "{:02d}".format(mm), COLOR_STATUS)
        _last_min = mm
    if ss != _last_sec:
        t.fill_rectangle(141, 5, 16, 8, bg)
        t.draw_text8x8(141, 5, "{:02d}".format(ss), COLOR_STATUS)
        _last_sec = ss
    if hh != _last_hour or mm != _last_min:
        t.draw_text8x8(109, 5, ":", COLOR_STATUS)
        t.draw_text8x8(133, 5, ":", COLOR_STATUS)


# ==================== WiFi / SD 状态指示 ====================
_last_wifi_state = None
_last_wifi_anim = 0
_wifi_anim = False
_last_sd_state = None


def update_wifi_status():
    global _last_wifi_state, _last_wifi_anim, _wifi_anim, _last_sd_state
    t = shared.tft

    if shared.wifi_connected:
        state = 'connected'
        color = color565(0, 200, 0)
    elif shared.wifi_connecting:
        state = 'connecting'
        now = time.ticks_ms()
        if time.ticks_diff(now, _last_wifi_anim) > 500:
            _wifi_anim = not _wifi_anim
            _last_wifi_anim = now
        color = color565(200, 200, 0) if _wifi_anim else color565(80, 80, 0)
    else:
        state = 'disconn'
        color = color565(200, 0, 0)

    if state == _last_wifi_state and not shared.wifi_connecting:
        return

    t.fill_rectangle(190, 2, 50, 14, COLOR_BG)
    if shared.wifi_connecting and not _wifi_anim:
        t.fill_circle(195, 8, 4, COLOR_BG)
        t.fill_circle(195, 8, 3, color)
    else:
        t.fill_circle(195, 8, 4, color)
    t.draw_text8x8(203, 5, "WiFi", COLOR_STATUS)
    _last_wifi_state = state


def update_sd_status():
    global _last_sd_state
    state = 'ok' if shared.SD_READY else 'fail'
    if state == _last_sd_state:
        return
    t = shared.tft
    t.fill_rectangle(190, 16, 50, 14, COLOR_BG)
    color = color565(0, 200, 0) if shared.SD_READY else color565(200, 0, 0)
    t.fill_circle(195, 22, 4, color)
    t.draw_text8x8(203, 19, "SD", COLOR_STATUS)
    _last_sd_state = state


# ==================== 错误显示 ====================

def clear_error():
    draw_static_background()


def show_temp_error():
    shared.tft.fill_rectangle(TEMP_NUM_X, TEMP_NUM_Y, 140, 70, COLOR_CARD)
    shared.tft.draw_text8x8(TEMP_NUM_X + 10, TEMP_NUM_Y + 30, "ERROR", COLOR_ERROR)


def show_hum_error():
    shared.tft.fill_rectangle(HUM_NUM_X, HUM_NUM_Y, 140, 70, COLOR_CARD)
    shared.tft.draw_text8x8(HUM_NUM_X + 10, HUM_NUM_Y + 30, "ERROR", COLOR_ERROR)
