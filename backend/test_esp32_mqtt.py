import json
import hmac
import hashlib
import time
import threading
from datetime import datetime

import paho.mqtt.client as mqtt

from config import settings


DEVICE_ID = "esp32_01"
ROOM_ID = "room_1"

POWER_KW = 20.0
ENERGY_KWH = 15.42


connected_event = threading.Event()


def on_connect(
    client,
    userdata,
    flags,
    reason_code,
    properties=None
):

    print(
        f"Publisher connected: {reason_code}"
    )

    if reason_code == 0:
        connected_event.set()


# =====================================================
# Build payload
# =====================================================

timestamp = datetime.now().isoformat()

signing_string = (
    f"{DEVICE_ID}|"
    f"{ROOM_ID}|"
    f"{POWER_KW}|"
    f"{ENERGY_KWH}|"
    f"{timestamp}"
)

signature = hmac.new(
    settings.message_secret.encode(),
    signing_string.encode(),
    hashlib.sha256
).hexdigest()

payload = {
    "device_id": DEVICE_ID,
    "room_id": ROOM_ID,
    "power_kw": POWER_KW,
    "energy_kwh": ENERGY_KWH,
    "timestamp": timestamp,
    "signature": signature
}


print()
print("Signing string:")
print(signing_string)

print()
print("Payload:")
print(
    json.dumps(
        payload,
        indent=2
    )
)


# =====================================================
# MQTT
# =====================================================

client = mqtt.Client(
    mqtt.CallbackAPIVersion.VERSION2
)

client.on_connect = on_connect


if (
    settings.mqtt_username
    and settings.mqtt_password
):

    client.username_pw_set(
        settings.mqtt_username,
        settings.mqtt_password
    )

    client.tls_set()


print()
print("Connecting to MQTT broker...")


client.connect(
    settings.mqtt_broker_host,
    settings.mqtt_broker_port,
    60
)


client.loop_start()


# =====================================================
# Wait until broker connection is confirmed
# =====================================================

if not connected_event.wait(timeout=10):

    print(
        "ERROR: Could not connect to MQTT broker."
    )

    client.loop_stop()
    client.disconnect()

    raise SystemExit(1)


# =====================================================
# Publish
# =====================================================

print(
    f"Publishing to topic: "
    f"{settings.mqtt_topic}"
)


result = client.publish(
    settings.mqtt_topic,
    json.dumps(payload),
    qos=1
)


result.wait_for_publish(
    timeout=10
)


if result.is_published():

    print()
    print(
        "ESP32 test message published successfully."
    )

else:

    print()
    print(
        "ERROR: ESP32 test message was not published."
    )


# Give broker/client a moment to finish QoS handshake
time.sleep(2)


client.loop_stop()
client.disconnect()


print(
    "Publisher disconnected."
)