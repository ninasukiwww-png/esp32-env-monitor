# ESP32-mpy-env

基于 ESP32 + MicroPython 的温湿度环境监测系统。

支持 DHT22/DHT11 传感器、ILI9341 TFT 彩屏 7 段数码管显示、DS1302 RTC 硬件时钟、SD 卡 CSV 数据记录、MQTT 发布、Web 仪表盘远程管理（Chart.js 图表）、WiFi 自动重连与 AP 配网。

## 功能

- **ILI9341 TFT 彩屏** — 240×320 分辨率，自制 7 段数码管风格温湿度数值
- **DS1302 RTC** — 硬件实时时钟，NTP 同步备用，断电时间不丢失
- **SD 卡日志** — 按天分文件 CSV 格式，Web 端可浏览/下载/统计
- **Web 仪表盘** — Chart.js 实时曲线、历史数据查询、WiFi 扫描/配置、文件管理、远程重启
- **MQTT 发布** — 可选配置，自动重连
- **WiFi 自动管理** — 启动自动连接，失败后定期重试，多次失败自动开启 AP 配网模式
- **懒加载架构** — Web/MQTT 可选功能按需导入，不占用 ESP32 宝贵内存

## 快速开始

### 硬件接线

| 外设 | 接口 | GPIO Pin |
|------|------|----------|
| ILI9341 TFT | SPI(1) | CLK=19, MOSI=18, DC=17, CS=4, RST=5, BL=16 |
| DHT22/DHT11 | 单总线 | 13 |
| DS1302 RTC | GPIO | CLK=12, DAT=14, RST=27 |
| SD Card | SPI(2) | SCK=33, MOSI=25, MISO=26, CS=32 |

### 烧录

```bash
# 安装 MicroPython v1.23+ 到 ESP32 (推荐 esptool.py)
# 上传文件
python -m mpremote connect COM4 fs cp main.py :main.py
python -m mpremote connect COM4 fs cp app/wifi.py :app/wifi.py

# 或直接运行
python -m mpremote connect COM4 run main.py
```

### 首次启动

1. 上电后 TFT 显示温湿度数值，DS1302 自动初始化
2. SD 卡自动挂载并开始记录日志
3. 若 WiFi 可连则自动连接；若开启配置 `web.enabled: true` 则启动 Web 服务
4. 浏览 `http://<esp32-ip>` 访问 Web 仪表盘

### Web 仪表盘

- `/` — 仪表盘首页（Chart.js 实时曲线）
- `/api/readings` — 最新温湿度 JSON
- `/api/history` — 历史数据
- `/api/wifi/scan` — WiFi 扫描
- `/api/wifi/connect` — 配网
- `/api/logs/list` — SD 卡日志文件列表
- `/api/logs/download` — 下载日志
- `/api/files/list` — 文件管理

## 项目结构

```
├── main.py               # 入口：硬件初始化 → async 主循环
├── config.json           # 本地配置文件（首次自动生成）
├── AGENTS.md             # 开发备忘
├── .gitignore
├── app/                  # 应用模块
│   ├── __init__.py
│   ├── shared.py         # 全局共享状态
│   ├── config.py         # JSON 配置读写
│   ├── display.py        # TFT 数码管渲染 + 状态栏
│   ├── wifi.py           # WiFi 连接/重连/NTP/DS1302 时间同步
│   ├── web.py            # Microdot HTTP API + 静态文件服务
│   ├── mqtt.py           # MQTT 发布客户端
│   └── logger.py         # SD 卡 CSV 日志
├── drivers/              # 硬件驱动
│   └── ds1302.py         # DS1302 RTC 驱动
├── lib/                  # 第三方库
│   ├── microdot.py       # 异步 HTTP Web 框架
│   ├── ili9341.py        # ILI9341 TFT 显示驱动
│   └── sdcard.py         # SD 卡 SPI 驱动
├── www/                  # Web 前端
│   └── index.html        # Chart.js 仪表盘（暗色主题）
└── esp32_backup/         # 本地备份（git 忽略）
    └── modular/          # 当前最新版快照
```

## 模块说明

### app/shared.py
所有模块共享的运行时状态：TFT 对象、WiFi 连接状态、最新温湿度、时间戳等。

### app/config.py
JSON 持久化配置，支持本地/SD 卡自动切换，`config.json` 或 `/sd/config.json`。

### app/display.py
ILI9341 屏幕渲染，自实现 7 段数码管绘制（整数大号、小数小号），带幽灵色余晖效果、温度/湿度的℃/% 位图、WiFi/SD 状态指示灯、错误显示。

### app/wifi.py
WiFi 状态机管理：连接/重连/超时重试/AP 模式切换；NTP 时间同步；DS1302 时间恢复。

### app/web.py
基于 Microdot 的异步 HTTP API 服务：实时数据、历史曲线、WiFi 扫描/配网、文件管理、日志下载、MQTT 配置、系统重启。

### app/mqtt.py
MQTT 发布客户端，自动重连，支持配置 broker/port/user/password。

### app/logger.py
SD 卡按天分文件 CSV 日志，含文件管理、统计查询、日志轮转。

## 修复记录

| 问题 | 原因 | 修复 |
|------|------|------|
| NameError | `from app import web` 导入 microdot 时 MemoryError | lazy import，try/except 保护 |
| WiFi Out of Memory | ESP32 堆内存不足 | `gc.collect()` 预清理 + try/except |
| MQTT 崩溃 | 未安装 umqtt.simple | `mqtt_pub = None` 默认 + 使用前检查 |
| wlan None | WiFi 初始化失败后继续调用 | 使用前 `is not None` 判断 |
| asyncio.sleep_ms | 部分 MicroPython 版本不支持 | 改用 `asyncio.sleep(0.05)` |

## 技术栈

- **硬件**: ESP32, DHT22, ILI9341, DS1302, Micro SD
- **运行时**: MicroPython v1.23+
- **Web 框架**: [Microdot](https://github.com/miguelgrinberg/microdot) (纯异步 HTTP)
- **前端**: Chart.js, 原生 JavaScript, CSS3 暗色主题
- **通信**: HTTP REST API, MQTT, NTP

## License

MIT
