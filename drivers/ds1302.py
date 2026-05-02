# ds1302.py - DS1302 实时时钟驱动
from machine import Pin


class DS1302:
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
