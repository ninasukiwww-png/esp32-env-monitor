# 温湿度监测仪 (ESP32 Environment Monitor)

基于 ESP32 + MicroPython 的温湿度监测系统，支持 DHT22/DHT11 传感器、ILI9341 TFT 彩屏显示、SD 卡数据记录、MQTT 发布和 Web 远程管理。

## 功能特点

- **实时显示** — ILI9341 彩色 TFT 屏幕，自定义 7 段数码管风格显示温湿度
- **Web 仪表盘** — Chart.js 图表、实时数据、历史曲线、WiFi 配置、文件管理
- **数据记录** — SD 卡 CSV 格式日志，支持按日分文件
- **MQTT 发布** — 可配置的 MQTT 推送
- **时间同步** — NTP 自动同步，DS1302 RTC 硬件时钟备份
- **WiFi 管理** — 自动重连，连接失败自动开启 AP 配网模式
- **模拟演示** — 无需硬件，Windows/Linux/macOS 可运行演示程序

## 快速开始

### 硬件接线

| 外设 | 接口 | GPIO |
|------|------|------|
| ILI9341 TFT | SPI(1) | CLK=19, MOSI=18, DC=17, CS=4, RST=5, BL=16 |
| DHT22/DHT11 | 单总线 | 13 |
| DS1302 RTC | GPIO | CLK=12, DAT=14, RST=27 |
| SD Card | SPI(2) | SCK=33, MOSI=25, MISO=26, CS=32 |

### 烧录与运行

1. 为 ESP32 刷入 MicroPython v1.23+
2. 将项目所有文件复制到 ESP32 文件系统
3. 上电自动运行 `main.py`
4. 浏览器打开 `http://<esp32-ip>` 访问 Web 仪表盘

### 模拟演示（无需硬件）

```bash
python 演示/main.py
```

自动打开模拟显示屏窗口和 Web 服务器 (http://127.0.0.1:8080)。

## 项目结构

```
├── main.py              # 主程序入口
├── app/                 # 应用逻辑
│   ├── config.py        # 配置管理
│   ├── display.py       # 屏幕渲染
│   ├── wifi.py          # WiFi/NTP/RTC
│   ├── web.py           # HTTP API 服务
│   ├── mqtt.py          # MQTT 发布
│   └── logger.py        # SD 卡日志
├── lib/                 # 第三方库
│   ├── microdot.py      # 异步 HTTP 框架
│   ├── ili9341.py       # TFT 显示驱动
│   └── sdcard.py        # SD 卡驱动
├── drivers/             # 硬件驱动
│   └── ds1302.py        # DS1302 RTC 驱动
├── www/                 # Web 前端静态文件
│   └── index.html
├── 演示/                # PC 模拟演示
│   ├── main.py
│   └── index.html
└── esp32_backup/        # 已验证的固件备份
```

## 技术栈

- **硬件**: ESP32, DHT22, ILI9341, DS1302, SD Card
- **运行时**: MicroPython v1.23+
- **Web 框架**: Microdot (异步 HTTP)
- **前端**: Chart.js, 原生 JavaScript, CSS3 暗色主题
- **通信**: MQTT, NTP, HTTP REST API

## 配置

首次启动使用默认配置，可通过 Web 界面修改所有参数，配置持久化到 `config.json`（优先使用 SD 卡 `/sd/config.json`）。

## License

MIT
