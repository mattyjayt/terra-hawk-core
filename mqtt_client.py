import paho.mqtt.client as mqtt
from data_models import update_sensor_state
from systems import get_systems_with_sensors
import json

BROKER = "localhost"
PORT = 1883


def on_message(client, userdata, msg):
    """Route incoming MQTT messages to the correct system's sensor state."""
    try:
        payload = json.loads(msg.payload.decode())
        # Extract system_id from topic: terrahawk/{system_id}/sensors
        parts = msg.topic.split("/")
        if len(parts) >= 3 and parts[0] == "terrahawk" and parts[2] == "sensors":
            system_id = parts[1]
            update_sensor_state(system_id, {
                "status": payload.get("status", "idle"),
                "temperature": payload.get("temperature", None),
                "humidity": payload.get("humidity", None),
                "soil": payload.get("soil", 0),
            })
        else:
            # Legacy topic support: pi/inbox → default system
            from systems import get_default_system_id
            default_id = get_default_system_id()
            if default_id:
                update_sensor_state(default_id, {
                    "status": payload.get("status", "idle"),
                    "temperature": payload.get("temperature", None),
                    "humidity": payload.get("humidity", None),
                    "soil": payload.get("soil", 0),
                })
    except json.JSONDecodeError:
        print(f"[MQTT] Invalid JSON: {msg.payload.decode()}")


class MQTT_Client:
    client: mqtt.Client

    def __init__(self) -> None:
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_message = on_message
        self.client.connect(BROKER, PORT, 60)

        # Subscribe to namespaced topics (wildcard)
        self.client.subscribe("terrahawk/+/sensors")

        # Also keep legacy topic for backwards compatibility
        self.client.subscribe("pi/inbox")

        self.client.loop_start()
