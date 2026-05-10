import os
import json
from paho import mqtt
import paho.mqtt.client as paho
from dotenv import load_dotenv
from data_models import update_sensor_state

load_dotenv()

HIVEMQ_HOST         = os.getenv("HIVEMQ_HOST")
HIVEMQ_PORT         = int(os.getenv("HIVEMQ_PORT"))
HIVEMQ_USERNAME     = os.getenv("HIVEMQ_USERNAME")
HIVEMQ_PASSWORD     = os.getenv("HIVEMQ_PASSWORD")
HIVEMQ_SUBSCRIPTION = os.getenv("HIVEMQ_SUBSCRIPTION")
HIVEMQ_PUBLICATION  = os.getenv("HIVEMQ_PUBLICATION")

# setting callbacks for different events to see if it works, print the message etc.
def on_connect(client, userdata, flags, rc, properties=None):
    print("CONNACK received with code %s." % rc)

# print which topic was subscribed to
def on_subscribe(client, userdata, mid, granted_qos, properties=None):
    print("Subscribed: " + str(mid) + " " + str(granted_qos))

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
    client: paho.Client

    def __init__(self) -> None:
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
