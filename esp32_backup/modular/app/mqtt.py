# app/mqtt.py - MQTT 数据上报模块
import time
import json

try:
    from umqtt.simple import MQTTClient
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False
    print("umqtt.simple 未安装, MQTT 不可用")


class MQTTPublisher:
    def __init__(self):
        self.client = None
        self.broker = ""
        self.port = 1883
        self.user = ""
        self.password = ""
        self.topic = "sensor/data"
        self.client_id = b"esp32_env_" + str(int(time.time() % 100000)).encode()
        self.connected = False
        self.last_attempt = 0
        self.retry_interval = 60
        self.publish_interval = 60
        self.last_publish = 0

    def configure(self, broker, port=1883, user="", password="", topic="sensor/data"):
        self.broker = broker
        self.port = int(port)
        self.user = user
        self.password = password
        self.topic = topic

    def connect(self):
        if not MQTT_AVAILABLE or not self.broker:
            return False
        now = time.time()
        if now - self.last_attempt < self.retry_interval:
            return self.connected
        self.last_attempt = now
        try:
            if self.client:
                try:
                    self.client.disconnect()
                except Exception:
                    pass
            self.client = MQTTClient(
                self.client_id, self.broker, port=self.port,
                user=self.user or None, password=self.password or None,
                keepalive=60
            )
            self.client.set_callback(lambda t, m: None)
            self.client.connect()
            self.connected = True
            print("MQTT 已连接:", self.broker)
            return True
        except Exception as e:
            self.connected = False
            print("MQTT 连接失败:", e)
            return False

    def publish(self, temp, hum):
        if not MQTT_AVAILABLE or not self.connected:
            return False
        try:
            data = {"temperature": round(temp, 1), "humidity": round(hum, 1), "timestamp": int(time.time())}
            self.client.publish(self.topic.encode(), json.dumps(data).encode())
            return True
        except Exception as e:
            print("MQTT 发布失败:", e)
            self.connected = False
            return False

    def disconnect(self):
        if self.client and self.connected:
            try:
                self.client.disconnect()
            except Exception:
                pass
            self.connected = False

    def loop(self, temp, hum):
        now = time.time()
        if self.connected:
            if now - self.last_publish >= self.publish_interval:
                self.publish(temp, hum)
                self.last_publish = now
        else:
            self.connect()
