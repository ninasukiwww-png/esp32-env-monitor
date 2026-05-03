# app/config.py - 配置管理 (JSON 持久化)
import json
import os

CONFIG_FILE = 'config.json'
SD_CONFIG_FILE = '/sd/config.json'

DEFAULT_CONFIG = {
    "wifi": {"ssid": "901", "password": ""},
    "sensor": {"type": "DHT22", "interval": 2, "decimal": True},
    "log": {"enabled": True, "interval": 60, "retention_days": 30},
    "mqtt": {"broker": "", "port": 1883, "user": "", "password": "", "pub_topic": "sensor/data"},
    "ntp": {"server": "ntp.aliyun.com", "timezone": 8, "sync_interval": 86400},
    "display": {"brightness": 255},
    "web": {"enabled": False}
}

_config = None


def _resolve_path():
    try:
        os.stat('/sd')
        return SD_CONFIG_FILE
    except OSError:
        pass
    return CONFIG_FILE


def _deep_merge(default, override):
    result = dict(default)
    for key, value in override.items():
        if key in result and isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load():
    global _config
    path = _resolve_path()
    try:
        with open(path, 'r') as f:
            loaded = json.load(f)
    except (OSError, ValueError):
        loaded = {}
    _config = _deep_merge(DEFAULT_CONFIG, loaded)
    return _config


def save():
    global _config
    if _config is None:
        _config = dict(DEFAULT_CONFIG)
    path = _resolve_path()
    try:
        with open(path, 'w') as f:
            json.dump(_config, f)
        return True
    except OSError:
        return False


def get(key, default=None):
    global _config
    if _config is None:
        _config = load()
    keys = key.split('.')
    val = _config
    for k in keys:
        if isinstance(val, dict):
            val = val.get(k)
        else:
            return default
    return val if val is not None else default


def set(key, value):
    global _config
    if _config is None:
        _config = load()
    keys = key.split('.')
    d = _config
    for k in keys[:-1]:
        if k not in d:
            d[k] = {}
        d = d[k]
    d[keys[-1]] = value
    save()


def get_all():
    global _config
    if _config is None:
        _config = load()
    return _config


def reset():
    global _config
    _config = dict(DEFAULT_CONFIG)
    save()
    return _config
