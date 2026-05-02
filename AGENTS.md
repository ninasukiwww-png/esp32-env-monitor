# 项目备忘

## 仓库
- GitHub: https://github.com/ninasukiwww-png/esp32-env-monitor
- `gh` CLI 已登录（`git push` 直接用）

## ESP32 推送 (COM4)
- 串口: COM4
- 命令:
  ```
  python -m mpremote connect COM4 fs cp main.py :main.py
  python -m mpremote connect COM4 fs cp app/wifi.py :app/wifi.py
  ```
- 或完整运行: `python -m mpremote connect COM4 run main.py`

## 修复记录
- **NameError**: `from app import web` 导入 microdot 时 MemoryError → 改为懒加载
- **WiFi Out of Memory**: `gc.collect()` + try/except 保护
- **MQTT**: 包 try/except，默认 None
- **shared.wlan**: 使用前 `is not None` 检查
- **asyncio.sleep_ms**: 改用 `asyncio.sleep(0.05)`

## 传感器
- DHT22 (Pin 13)
- TFT ILI9341 (SPI)
- DS1302 RTC
- SD 卡日志

## 备份
- `esp32_backup/firmware/` — 旧版单文件（同步版）
- `esp32_backup/modular/` — 新版模块化（修复版）
