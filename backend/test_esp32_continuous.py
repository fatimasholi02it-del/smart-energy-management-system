import json
import time
import hmac
import hashlib
from datetime import datetime

import paho.mqtt.client as mqtt


MQTT_BROKER = "localhost"
MQTT_PORT = 1883
TOPIC = "energy/readings"

SECRET = "super-secret-key"


device_id = "esp32_01"
room_id = "room_1"


def generate_signature(
    device_id,
    room_id,
    power_kw,
    energy_kwh,
    timestamp
):

    message = (
        f"{device_id}|"
        f"{room_id}|"
        f"{power_kw}|"
        f"{energy_kwh}|"
        f"{timestamp}"
    )

    return hmac.new(
        SECRET.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()



client = mqtt.Client()

client.connect(
    MQTT_BROKER,
    MQTT_PORT,
    60
)


energy = 15.42


while True:

    power = 3.0 + (time.time() % 2)

    timestamp = datetime.now().isoformat()


    signature = generate_signature(
        device_id,
        room_id,
        round(power,2),
        energy,
        timestamp
    )


    payload = {

        "device_id": device_id,

        "room_id": room_id,

        "power_kw": round(power,2),

        "energy_kwh": energy,

        "timestamp": timestamp,

        "signature": signature
    }


    client.publish(
        TOPIC,
        json.dumps(payload)
    )


    print(
        "Sent:",
        payload
    )


    time.sleep(5)