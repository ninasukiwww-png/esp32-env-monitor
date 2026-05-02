# test_ds1302_fixed.py - DS1302 硬件测试脚本（修复小时偏移）
# 引脚定义与 main.py 保持一致

from machine import Pin
import time

# ========== 引脚配置（请根据实际接线修改）==========
DS1302_CLK = 12
DS1302_DAT = 14
DS1302_RST = 27

# ========== DS1302 驱动（修正版：强制24小时制）==========
class DS1302:
    REG_SECOND = 0x80
    REG_MINUTE = 0x82
    REG_HOUR   = 0x84
    REG_DATE   = 0x86
    REG_MONTH  = 0x88
    REG_DAY    = 0x8A
    REG_YEAR   = 0x8C
    REG_WP     = 0x8E

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
            self._write_reg(self.REG_WP, 0x00)          # 关闭写保护
            
            # 写入秒
            self._write_reg(self.REG_SECOND, self._dec_to_bcd(ss) & 0x7F)
            # 写入分
            self._write_reg(self.REG_MINUTE, self._dec_to_bcd(mm))
            # 写入小时：强制24小时制（bit7=0）
            hour_bcd = self._dec_to_bcd(hh) & 0x3F      # 清除高位，只保留低6位
            self._write_reg(self.REG_HOUR, hour_bcd)
            
            # 写入日、月、星期、年
            self._write_reg(self.REG_DATE,   self._dec_to_bcd(d))
            self._write_reg(self.REG_MONTH,  self._dec_to_bcd(m))
            self._write_reg(self.REG_DAY,    self._dec_to_bcd(wd + 1))
            self._write_reg(self.REG_YEAR,   self._dec_to_bcd(y % 100))
            
            self._write_reg(self.REG_WP, 0x80)          # 开启写保护
        else:
            ss  = self._bcd_to_dec(self._read_reg(self.REG_SECOND) & 0x7F)
            mm  = self._bcd_to_dec(self._read_reg(self.REG_MINUTE))
            hh  = self._bcd_to_dec(self._read_reg(self.REG_HOUR) & 0x3F)  # 忽略12/24标志
            d   = self._bcd_to_dec(self._read_reg(self.REG_DATE))
            m   = self._bcd_to_dec(self._read_reg(self.REG_MONTH))
            wd  = self._bcd_to_dec(self._read_reg(self.REG_DAY)) - 1
            y   = self._bcd_to_dec(self._read_reg(self.REG_YEAR)) + 2000
            return (y, m, d, wd, hh, mm, ss, 0)

# ========== 测试主程序 ==========
def test_ds1302():
    print("\n" + "="*40)
    print("DS1302 硬件测试开始 (修复小时偏移)")
    print("="*40)

    # 1. 初始化
    try:
        rtc = DS1302(DS1302_CLK, DS1302_DAT, DS1302_RST)
        print("[1] DS1302 驱动初始化成功")
    except Exception as e:
        print("[1] DS1302 驱动初始化失败:", e)
        return

    # 2. 读取当前时间
    try:
        y, m, d, wd, hh, mm, ss, _ = rtc.datetime()
        print(f"[2] 当前 DS1302 时间: {y}-{m:02d}-{d:02d} {hh:02d}:{mm:02d}:{ss:02d} (星期{wd})")
        if y < 2000 or y > 2100:
            print("    警告: 年份异常，可能芯片未初始化或电池失效")
        if (hh, mm, ss) == (0, 0, 0) and (y, m, d) == (2000, 1, 1):
            print("    提示: 时间全为初始值，可能 DS1302 从未被设置过")
    except Exception as e:
        print("[2] 读取 DS1302 时间失败:", e)
        return

    # 3. 写入测试时间（2025-01-01 12:00:00 星期三）
    test_time = (2026, 4, 18, 5, 19, 58, 0, 0)  # 星期2 = 星期三（0=周一）
    try:
        rtc.datetime(test_time)
        print("[3] 已写入测试时间: 2025-01-01 12:00:00 (强制24小时制)")
    except Exception as e:
        print("[3] 写入测试时间失败:", e)
        return

    # 4. 等待 1 秒后读回验证
    time.sleep(1)
    try:
        y, m, d, wd, hh, mm, ss, _ = rtc.datetime()
        expected = "2025-01-01 12:00:01"
        actual = f"{y}-{m:02d}-{d:02d} {hh:02d}:{mm:02d}:{ss:02d}"
        if y == 2025 and m == 1 and d == 1 and hh == 12 and mm == 0 and 0 <= ss <= 2:
            print(f"[4] 验证通过！读回时间: {actual} (误差允许范围内) ✅")
        else:
            print(f"[4] 验证失败！预期类似 {expected}，实际读回 {actual} ❌")
    except Exception as e:
        print("[4] 读回验证时出错:", e)
        return

    # 5. 额外检查：秒寄存器是否在走动
    try:
        _, _, _, _, _, _, ss1, _ = rtc.datetime()
        time.sleep(1.5)
        _, _, _, _, _, _, ss2, _ = rtc.datetime()
        if ss2 != ss1:
            print(f"[5] 秒寄存器变化检测: {ss1} -> {ss2}，时钟正在走动 ✅")
        else:
            print("[5] 秒寄存器未变化，可能振荡器停振或芯片损坏 ❌")
    except Exception as e:
        print("[5] 走动检测失败:", e)

    print("="*40)
    print("测试完成。若以上步骤均正常，DS1302 硬件工作正常。")
    print("若出现异常，请检查：")
    print("  - 电源/VCC 是否接妥（通常 3.3V）")
    print("  - 备用电池是否安装或电量充足")
    print("  - 数据/时钟/复位引脚接线是否正确")
    print("  - 芯片是否插反或损坏")
    print("="*40 + "\n")

# 执行测试
test_ds1302()