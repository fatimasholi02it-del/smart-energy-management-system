import json
import hmac
import hashlib
import random
import time
from datetime import datetime

import paho.mqtt.client as mqtt

from config import settings


# =====================================================
# Sensor Configuration
# =====================================================

DEVICE_ID = "esp32_01"
ROOM_ID = "room_1"

SEND_INTERVAL_SECONDS = 5

# Normal power range for the test sensor
MIN_POWER_KW = 2.5
MAX_POWER_KW = 3.2

# Starting cumulative energy
ENERGY_KWH = 15.42


# =====================================================
# MQTT
# =====================================================

client = mqtt.Client(
    mqtt.CallbackAPIVersion.VERSION2
)


def on_connect(
    client,
    userdata,
    flags,
    reason_code,
    properties=None
):

    print(
        f"MQTT connected: {reason_code}"
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


# =====================================================
# Connect
# =====================================================

print(
    "Connecting ESP32 simulator "
    "to MQTT broker..."
)

client.connect(
    settings.mqtt_broker_host,
    settings.mqtt_broker_port,
    60
)

client.loop_start()


# Give MQTT time to establish connection
time.sleep(2)


print()
print(
    "ESP32 simulator started."
)

print(
    f"Device: {DEVICE_ID}"
)

print(
    f"Room: {ROOM_ID}"
)

print(
    f"Interval: {SEND_INTERVAL_SECONDS} seconds"
)

print(
    "Press CTRL+C to stop."
)

print(
    "-" * 60
)


# =====================================================
# Main Loop
# =====================================================

try:

    while True:

        # -------------------------------------------------
        # Current Power
        # -------------------------------------------------

        power_kw = round(
            random.uniform(
                MIN_POWER_KW,
                MAX_POWER_KW
            ),
            2
        )

        # -------------------------------------------------
        # Update cumulative energy
        #
        # Energy = Power × Time
        #
        # 5 seconds converted to hours:
        # 5 / 3600
        # -------------------------------------------------

        interval_hours = (
            SEND_INTERVAL_SECONDS
            / 3600.0
        )

        ENERGY_KWH += (
            power_kw
            * interval_hours
        )

        ENERGY_KWH = round(
            ENERGY_KWH,
            5
        )

        # -------------------------------------------------
        # Timestamp
        # -------------------------------------------------

        timestamp = (
            datetime.now().isoformat()
        )

        # -------------------------------------------------
        # HMAC Signing String
        # -------------------------------------------------

        signing_string = (
            f"{DEVICE_ID}|"
            f"{ROOM_ID}|"
            f"{power_kw}|"
            f"{ENERGY_KWH}|"
            f"{timestamp}"
        )

        # -------------------------------------------------
        # Signature
        # -------------------------------------------------

        signature = hmac.new(
            settings.message_secret.encode(),
            signing_string.encode(),
            hashlib.sha256
        ).hexdigest()

        # -------------------------------------------------
        # Payload
        # -------------------------------------------------

        payload = {

            "device_id":
                DEVICE_ID,

            "room_id":
                ROOM_ID,

            "power_kw":
                power_kw,

            "energy_kwh":
                ENERGY_KWH,

            "timestamp":
                timestamp,

            "signature":
                signature
        }

        # -------------------------------------------------
        # Publish
        # -------------------------------------------------

        result = client.publish(
            settings.mqtt_topic,
            json.dumps(payload),
            qos=1
        )

        result.wait_for_publish()

        # -------------------------------------------------
        # Console
        # -------------------------------------------------

        print(
            f"{timestamp} | "
            f"{DEVICE_ID} | "
            f"Power: {power_kw} kW | "
            f"Energy: {ENERGY_KWH} kWh"
        )

        time.sleep(
            SEND_INTERVAL_SECONDS
        )


except KeyboardInterrupt:

    print()
    print(
        "Stopping ESP32 simulator..."
    )


finally:

    client.loop_stop()

    client.disconnect()

    print(
        "ESP32 simulator stopped."
    )