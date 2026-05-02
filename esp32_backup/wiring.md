# 接线定义 (ESP32 环境监测仪)

> 来源: main.py (备份中已验证的参考点)

## TFT 显示屏 (ILI9341, SPI)

| 引脚 | ESP32 GPIO |
|------|------------|
| TFT_CLK  (SCK)  | GPIO 19 |
| TFT_MOSI (SDA)  | GPIO 18 |
| TFT_DC   (DC)   | GPIO 17 |
| TFT_CS   (CS)   | GPIO 4  |
| TFT_RST  (RST)  | GPIO 5  |
| TFT_BL   (BL)   | GPIO 16 |

- SPI 总线: SPI(1), 波特率 10MHz

## 温湿度传感器 (DHT22/DHT11)

| 引脚 | ESP32 GPIO |
|------|------------|
| DHT_DATA | GPIO 13 |

## 外部 RTC (DS1302)

| 引脚 | ESP32 GPIO |
|------|------------|
| DS1302_CLK | GPIO 12 |
| DS1302_DAT | GPIO 14 |
| DS1302_RST | GPIO 27 |

## SD 卡模块 (SPI)

| 引脚 | ESP32 GPIO |
|------|------------|
| SD_SCK  | GPIO 33 |
| SD_MOSI | GPIO 25 |
| SD_MISO | GPIO 26 |
| SD_CS   | GPIO 32 |

- SPI 总线: SPI(2), 波特率 5MHz
