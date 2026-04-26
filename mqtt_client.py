import paho.mqtt.client as mqtt
from data_models import sensor_state
import json

BROKER          = "localhost"
PORT            = 1883
LOCAL_TOPIC     = "pi/inbox"
REMOTE_TOPIC    = "esp32/inbox"

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        sensor_state["status"] = payload.get("status", "idle")
        sensor_state["temperature"] = payload.get("temperature", None)
        sensor_state["humidity"] = payload.get("humidity", None)
        sensor_state["soil"] = 0
    except json.JSONDecodeError:
        raise(f"[ESP32 - Payload]: {msg.payload.decode()}")

class MQTT_Client():
    client: mqtt.Client

    def __init__(self) -> mqtt.Client:
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_message = on_message
        self.client.connect(BROKER, PORT, 60)
        self.client.subscribe(LOCAL_TOPIC)
        self.client.loop_start()