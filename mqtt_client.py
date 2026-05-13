import os
import json
from paho import mqtt
import paho.mqtt.client as paho
from dotenv import load_dotenv
from data_models import update_sensor_state
from systems import get_systems_with_sensors, get_default_system_id

load_dotenv()

HIVEMQ_HOST         = os.getenv("HIVEMQ_HOST")
HIVEMQ_PORT         = int(os.getenv("HIVEMQ_PORT"))
HIVEMQ_USERNAME     = os.getenv("HIVEMQ_USERNAME")
HIVEMQ_PASSWORD     = os.getenv("HIVEMQ_PASSWORD")
HIVEMQ_SUBSCRIPTION = os.getenv("HIVEMQ_SUBSCRIPTION")
HIVEMQ_PUBLICATION  = os.getenv("HIVEMQ_PUBLICATION")

# ── Topic → system_id reverse lookup ────────────────────────────────────────
_topic_to_systems: dict[str, list[str]] = {}


def build_topic_map():
    """Build a reverse map: mqtt_topic_in → [system_id, ...] from systems.json."""
    _topic_to_systems.clear()
    for s in get_systems_with_sensors():
        topic = s.get("components", {}).get("sensors", {}).get("mqtt_topic_in")
        if topic:
            _topic_to_systems.setdefault(topic, []).append(s["id"])
    print(f"[MQTT] Topic map: {_topic_to_systems}")


# setting callbacks for different events to see if it works, print the message etc.
def on_connect(client, userdata, flags, rc, properties=None):
    print("CONNACK received with code %s." % rc)

# print which topic was subscribed to
def on_subscribe(client, userdata, mid, granted_qos, properties=None):
    print("Subscribed: " + str(mid) + " " + str(granted_qos))

def on_message(client, userdata, msg):
    """Route incoming MQTT messages to the correct system(s) via systems.json topic map."""
    try:
        payload = json.loads(msg.payload.decode())
        sensor_data = {
            "status": payload.get("status", "idle"),
            "temperature": payload.get("temperature", None),
            "humidity": payload.get("humidity", None),
            "soil": payload.get("soil", 0),
        }

        # Look up which systems subscribe to this topic
        target_systems = _topic_to_systems.get(msg.topic)

        if target_systems:
            for system_id in target_systems:
                update_sensor_state(system_id, sensor_data)
        else:
            # Fallback: legacy topic or unmapped — route to default system
            default_id = get_default_system_id()
            if default_id:
                update_sensor_state(default_id, sensor_data)
                print(f"[MQTT] Unmapped topic '{msg.topic}', routed to default '{default_id}'")

    except json.JSONDecodeError:
        print(f"[MQTT] Invalid JSON: {msg.payload.decode()}")


class MQTT_Client:
    client: paho.Client

    def __init__(self) -> None:
        # Build topic map from systems.json before connecting
        build_topic_map()

        self.client = paho.Client(client_id="", userdata=None, protocol=paho.MQTTv5)
        self.client.on_connect = on_connect
        # enable TLS for secure connection
        self.client.tls_set(tls_version=mqtt.client.ssl.PROTOCOL_TLS)
        # set username and password
        self.client.username_pw_set(HIVEMQ_USERNAME, HIVEMQ_PASSWORD)
        self.client.connect(HIVEMQ_HOST, HIVEMQ_PORT, 60)

        self.client.on_subscribe = on_subscribe
        self.client.on_message = on_message

        # Subscribe to namespaced topics (wildcard)
        self.client.subscribe(HIVEMQ_SUBSCRIPTION)
        self.client.loop_start()
