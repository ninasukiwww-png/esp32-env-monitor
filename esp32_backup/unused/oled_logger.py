"""
OLED 屏幕日志模块 - 导入即生效版
用法：
    import oled_logger   # 只需这一行，print 自动同步到屏幕
"""

from machine import Pin, I2C
import ssd1306
import ufont
import sys

# ========== 配置参数（可按需修改） ==========
I2C_SCL = 21
I2C_SDA = 22
FONT_FILE = "unifont-14-12888-16.v3.bmf"
LINE_HEIGHT = 16
MAX_LINES = 4

# ========== 内部实现 ==========
class _OLEDOutput:
    def __init__(self, original_stdout, oled, font):
        self.original_stdout = original_stdout
        self.oled = oled
        self.font = font
        self.line_height = LINE_HEIGHT
        self.lines = []
        self.max_lines = MAX_LINES
        self._current_line = ''

    def write(self, text):
        self.original_stdout.write(text)
        if text == '\n':
            self._add_newline()
        else:
            for ch in text:
                if ch == '\n':
                    self._add_newline()
                else:
                    self._current_line += ch
        self._update_display()

    def _add_newline(self):
        if self._current_line or (self.lines and self.lines[-1] == ''):
            self.lines.append(self._current_line)
        else:
            self.lines.append('')
        self._current_line = ''
        if len(self.lines) > self.max_lines:
            self.lines.pop(0)

    def _update_display(self):
        self.oled.fill(0)
        y = 0
        for line in self.lines:
            self.font.text(self.oled, line, 0, y, font_size=LINE_HEIGHT, show=False)
            y += self.line_height
        if self._current_line:
            self.font.text(self.oled, self._current_line, 0, y, font_size=LINE_HEIGHT, show=False)
        self.oled.show()

    def flush(self):
        pass

# ========== 模块导入时自动初始化并启用 ==========
def _init():
    # 1. 获取原始 stdout（如果存在）
    original = None
    try:
        original = sys.stdout
    except AttributeError:
        # 如果 sys.stdout 不存在，我们就不能用重定向，直接返回失败
        print("OLED: sys.stdout 不可用")
        return False

    # 2. 初始化硬件
    try:
        i2c = I2C(scl=Pin(I2C_SCL), sda=Pin(I2C_SDA))
        oled = ssd1306.SSD1306_I2C(128, 64, i2c)
        font = ufont.BMFont(FONT_FILE)
    except Exception as e:
        print("OLED 初始化失败: {}".format(e))
        return False

    # 3. 重定向 stdout
    sys.stdout = _OLEDOutput(original, oled, font)
    print("OLED 日志模块已启用")
    return True

# 执行初始化，但不捕获异常（因为 _init 内部已经处理并打印错误）
_init()