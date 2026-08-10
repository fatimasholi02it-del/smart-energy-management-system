import json
import time
import hmac
import hashlib
import random
import os
from datetime import datetime

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()

BROKER_HOST = os.getenv("MQTT_BROKER_HOST", "localhost")
BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT", "1883"))
TOPIC = os.getenv("MQTT_TOPIC", "energy/readings")
MESSAGE_SECRET = os.getenv("MESSAGE_SECRET", "super-secret-key")


DEVICES = [
    {
        "device_id": "simulator_01",
        "building_id": "building_1",
        "room_id": "room_1",
        "energy_range": (2.2, 4.0),
        "base_factor": 1.00,
    },
    {
        "device_id": "simulator_02",
        "building_id": "building_1",
        "room_id": "room_2",
        "energy_range": (1.8, 3.5),
        "base_factor": 0.85,
    },
    {
        "device_id": "simulator_03",
        "building_id": "building_2",
        "room_id": "room_3",
        "energy_range": (3.0, 4.8),
        "base_factor": 1.20,
    },
]


def build_signing_string(payload: dict) -> str:
    return (
        f"{payload['device_id']}|"
        f"{payload['room_id']}|"
        f"{payload['energy']}|"
        f"{payload['timestamp']}"
    )


def generate_signature(payload: dict) -> str:
    signing_string = build_signing_string(payload)

    return hmac.new(
        MESSAGE_SECRET.encode(),
        signing_string.encode(),
        hashlib.sha256
    ).hexdigest()


def get_hourly_load_factor(hour: int) -> float:
    """
    نمط استهلاك واقعي مبسط حسب ساعة اليوم.

    00 - 05  : Low
    06 - 08  : Morning rise
    09 - 16  : Daytime high load
    17 - 20  : Evening peak
    21 - 23  : Medium
    """

    if 0 <= hour <= 5:
        return 0.55

    if 6 <= hour <= 8:
        return 0.75

    if 9 <= hour <= 12:
        return 0.95

    if 13 <= hour <= 16:
        return 1.05

    if 17 <= hour <= 20:
        return 1.15

    return 0.80


def generate_energy(device: dict) -> float:
    min_energy, max_energy = device["energy_range"]

    current_hour = datetime.now().hour

    hourly_factor = get_hourly_load_factor(
        current_hour
    )

    device_factor = device.get(
        "base_factor",
        1.0
    )

    middle_value = (
        min_energy + max_energy
    ) / 2.0

    base_value = (
        middle_value
        * hourly_factor
        * device_factor
    )

    # Noise بسيط بدل random كامل
    noise = random.uniform(
        -0.18,
        0.18
    )

    value = (
        base_value
        + noise
    )

    # Spike نادر لمحاكاة حمل مفاجئ
    if random.random() < 0.03:
        value += random.uniform(
            0.15,
            0.35
        )

    # المحافظة على الحدود المقبولة
    value = max(
        min_energy,
        min(
            value,
            max_energy
        )
    )

    return round(
        value,
        2
    )


def generate_payload(device: dict) -> dict:
    payload = {
        "device_id": device["device_id"],
        "room_id": device["room_id"],
        "energy": generate_energy(device),
        "timestamp": datetime.now().isoformat(),
    }

    payload["signature"] = generate_signature(
        payload
    )

    return payload


def main():
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2
    )

    mqtt_username = os.getenv(
        "MQTT_USERNAME"
    )

    mqtt_password = os.getenv(
        "MQTT_PASSWORD"
    )

    if mqtt_username and mqtt_password:
        client.username_pw_set(
            mqtt_username,
            mqtt_password
        )

        client.tls_set()

    client.connect(
        BROKER_HOST,
        BROKER_PORT,
        60
    )

    client.loop_start()

    print("Realistic simulator started.")
    print(
        f"Broker: "
        f"{BROKER_HOST}:{BROKER_PORT}"
    )
    print(
        f"Publishing to MQTT topic: "
        f"{TOPIC}"
    )
    print("-" * 60)

    try:
        while True:

            current_hour = datetime.now().hour

            print(
                f"Current simulated load period: "
                f"{current_hour}:00"
            )

            for device in DEVICES:

                payload = generate_payload(
                    device
                )

                message = json.dumps(
                    payload
                )

                result = client.publish(
                    TOPIC,
                    message
                )

                if result.rc == 0:
                    print(
                        f"{device['device_id']} "
                        f"-> {payload['energy']} kW"
                    )
                else:
                    print(
                        f"Failed to publish "
                        f"{device['device_id']}"
                    )

            print("-" * 60)

            time.sleep(5)

    except KeyboardInterrupt:
        print("Stopping simulator...")

    finally:
        client.loop_stop()
        client.disconnect()

        print("Simulator stopped.")


if __name__ == "__main__":
    main()