import hashlib
import hmac
import json
import os
import random
import threading
import time

from datetime import datetime

import paho.mqtt.client as mqtt
from dotenv import load_dotenv


# =====================================================
# Environment
# =====================================================

load_dotenv()


BROKER_HOST = os.getenv(
    "MQTT_BROKER_HOST",
    "",
).strip()

BROKER_PORT = int(
    os.getenv(
        "MQTT_BROKER_PORT",
        "8883",
    )
)

TOPIC = os.getenv(
    "MQTT_TOPIC",
    "energy/readings",
).strip()

MQTT_USERNAME = os.getenv(
    "MQTT_USERNAME",
    "",
).strip()

MQTT_PASSWORD = os.getenv(
    "MQTT_PASSWORD",
    "",
)

MESSAGE_SECRET = os.getenv(
    "MESSAGE_SECRET",
    "",
)


# =====================================================
# MQTT Runtime State
# =====================================================

mqtt_connected = threading.Event()


# =====================================================
# Simulated Devices
# =====================================================

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


# =====================================================
# Environment Validation
# =====================================================

def validate_environment() -> bool:
    missing_variables = []

    if not BROKER_HOST:
        missing_variables.append(
            "MQTT_BROKER_HOST"
        )

    if not MQTT_USERNAME:
        missing_variables.append(
            "MQTT_USERNAME"
        )

    if not MQTT_PASSWORD:
        missing_variables.append(
            "MQTT_PASSWORD"
        )

    if not MESSAGE_SECRET:
        missing_variables.append(
            "MESSAGE_SECRET"
        )

    if missing_variables:
        print(
            "Simulator configuration error."
        )

        print(
            "The following required environment "
            "variables are missing:"
        )

        for variable in missing_variables:
            print(
                f"  - {variable}"
            )

        print(
            "Configure them in simulator/.env "
            "before starting the simulator."
        )

        return False

    if not TOPIC:
        print(
            "Simulator configuration error: "
            "MQTT_TOPIC is empty."
        )

        return False

    if (
        BROKER_PORT <= 0
        or BROKER_PORT > 65535
    ):
        print(
            "Simulator configuration error: "
            "MQTT_BROKER_PORT is invalid."
        )

        return False

    return True


# =====================================================
# MQTT Callbacks
# =====================================================

def on_connect(
    client,
    userdata,
    flags,
    reason_code,
    properties,
):
    print(
        f"MQTT on_connect: "
        f"{reason_code}"
    )

    if reason_code == 0:
        mqtt_connected.set()

        print(
            "MQTT connected successfully."
        )

        print(
            f"Broker: "
            f"{BROKER_HOST}:{BROKER_PORT}"
        )

        print(
            f"Topic: {TOPIC}"
        )

    else:
        mqtt_connected.clear()

        print(
            f"MQTT connection failed: "
            f"{reason_code}"
        )


def on_disconnect(
    client,
    userdata,
    disconnect_flags,
    reason_code,
    properties,
):
    mqtt_connected.clear()

    print(
        f"MQTT disconnected: "
        f"{reason_code}"
    )


def on_connect_fail(
    client,
    userdata,
):
    mqtt_connected.clear()

    print(
        "MQTT connection attempt failed."
    )


# =====================================================
# Signature
# =====================================================

def build_signing_string(
    payload: dict,
) -> str:
    return (
        f"{payload['device_id']}|"
        f"{payload['room_id']}|"
        f"{payload['energy']}|"
        f"{payload['timestamp']}"
    )


def generate_signature(
    payload: dict,
) -> str:
    signing_string = (
        build_signing_string(
            payload
        )
    )

    return hmac.new(
        MESSAGE_SECRET.encode(),
        signing_string.encode(),
        hashlib.sha256,
    ).hexdigest()


# =====================================================
# Load Profile
# =====================================================

def get_hourly_load_factor(
    hour: int,
) -> float:
    """
    Simplified realistic energy consumption profile.

    00 - 05 : Low
    06 - 08 : Morning rise
    09 - 16 : Daytime high load
    17 - 20 : Evening peak
    21 - 23 : Medium
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


# =====================================================
# Generate Energy
# =====================================================

def generate_energy(
    device: dict,
) -> float:
    min_energy, max_energy = (
        device["energy_range"]
    )

    current_hour = (
        datetime.now().hour
    )

    hourly_factor = (
        get_hourly_load_factor(
            current_hour
        )
    )

    device_factor = (
        device.get(
            "base_factor",
            1.0,
        )
    )

    middle_value = (
        min_energy
        + max_energy
    ) / 2.0

    base_value = (
        middle_value
        * hourly_factor
        * device_factor
    )

    # Small realistic noise.
    noise = random.uniform(
        -0.18,
        0.18,
    )

    value = (
        base_value
        + noise
    )

    # Rare load spike.
    if random.random() < 0.03:
        value += random.uniform(
            0.15,
            0.35,
        )

    # Keep value inside the configured
    # valid range for this device.
    value = max(
        min_energy,
        min(
            value,
            max_energy,
        ),
    )

    return round(
        value,
        2,
    )


# =====================================================
# Payload
# =====================================================

def generate_payload(
    device: dict,
) -> dict:
    payload = {
        "device_id":
            device["device_id"],

        "room_id":
            device["room_id"],

        # Legacy simulator contract:
        # "energy" currently represents
        # instantaneous power in kW.
        "energy":
            generate_energy(
                device
            ),

        "timestamp":
            datetime.now().isoformat(),
    }

    payload["signature"] = (
        generate_signature(
            payload
        )
    )

    return payload


# =====================================================
# Publish
# =====================================================

def publish_reading(
    client,
    device,
) -> bool:
    if not client.is_connected():
        print(
            f"MQTT disconnected - "
            f"skipping {device['device_id']}"
        )

        return False

    payload = generate_payload(
        device
    )

    message = json.dumps(
        payload
    )

    try:
        result = client.publish(
            TOPIC,
            message,
            qos=1,
        )

        if (
            result.rc
            != mqtt.MQTT_ERR_SUCCESS
        ):
            print(
                f"Failed to publish "
                f"{device['device_id']} "
                f"(rc={result.rc})"
            )

            return False

        # Wait until the broker acknowledges
        # the QoS 1 publication.
        result.wait_for_publish(
            timeout=5
        )

        if result.is_published():
            print(
                f"{device['device_id']} "
                f"-> "
                f"{payload['energy']} kW "
                f"[published]"
            )

            return True

        print(
            f"Publish was not confirmed "
            f"for {device['device_id']}"
        )

        return False

    except Exception as e:
        print(
            f"Publish error for "
            f"{device['device_id']}: "
            f"{e}"
        )

        return False


# =====================================================
# Main
# =====================================================

def main():
    if not validate_environment():
        return

    mqtt_connected.clear()

    client_id = (
        f"energy-simulator-"
        f"{os.getpid()}"
    )

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=client_id,
    )

    # ---------------------------------------------
    # Callbacks
    # ---------------------------------------------

    client.on_connect = (
        on_connect
    )

    client.on_disconnect = (
        on_disconnect
    )

    client.on_connect_fail = (
        on_connect_fail
    )

    # ---------------------------------------------
    # Automatic reconnect
    # ---------------------------------------------

    client.reconnect_delay_set(
        min_delay=1,
        max_delay=10,
    )

    # ---------------------------------------------
    # Authentication
    # ---------------------------------------------

    client.username_pw_set(
        MQTT_USERNAME,
        MQTT_PASSWORD,
    )

    # ---------------------------------------------
    # TLS
    # ---------------------------------------------

    client.tls_set()

    # ---------------------------------------------
    # Connect
    # ---------------------------------------------

    print(
        "Connecting to MQTT broker..."
    )

    print(
        f"Broker: "
        f"{BROKER_HOST}:{BROKER_PORT}"
    )

    print(
        f"Topic: {TOPIC}"
    )

    print(
        "TLS: enabled"
    )

    try:
        client.connect(
            BROKER_HOST,
            BROKER_PORT,
            60,
        )

    except Exception as e:
        print(
            f"Initial MQTT connection "
            f"failed: {e}"
        )

        return

    # Start network loop.
    client.loop_start()

    print(
        "Waiting for MQTT connection..."
    )

    # Wait for actual CONNACK.
    if not mqtt_connected.wait(
        timeout=15
    ):
        print(
            "Could not establish MQTT "
            "connection within 15 seconds."
        )

        client.loop_stop()

        try:
            client.disconnect()
        except Exception:
            pass

        return

    print(
        "Realistic simulator started."
    )

    print(
        f"Publishing to MQTT topic: "
        f"{TOPIC}"
    )

    print(
        "-" * 60
    )

    # ---------------------------------------------
    # Simulation Loop
    # ---------------------------------------------

    try:
        while True:
            current_hour = (
                datetime.now().hour
            )

            print(
                f"Current simulated "
                f"load period: "
                f"{current_hour}:00"
            )

            # If disconnected, wait for the
            # MQTT client's automatic reconnect.
            if not mqtt_connected.is_set():
                print(
                    "Waiting for MQTT "
                    "reconnection..."
                )

                mqtt_connected.wait(
                    timeout=10
                )

            for device in DEVICES:
                publish_reading(
                    client,
                    device,
                )

            print(
                "-" * 60
            )

            time.sleep(
                5
            )

    except KeyboardInterrupt:
        print(
            "\nStopping simulator..."
        )

    finally:
        mqtt_connected.clear()

        try:
            client.disconnect()

        except Exception as e:
            print(
                f"Disconnect warning: "
                f"{e}"
            )

        client.loop_stop()

        print(
            "Simulator stopped."
        )


# =====================================================
# Entry Point
# =====================================================

if __name__ == "__main__":
    main()