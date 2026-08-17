import hashlib
import hmac
import json
import os
import random
import threading
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

# Normal test range for esp32_01.
# This range stays within the backend validation
# range configured for room_1.
MIN_POWER_KW = 2.5
MAX_POWER_KW = 3.2

# Starting cumulative energy value used only
# for the ESP32 simulation.
INITIAL_ENERGY_KWH = 15.42


# =====================================================
# Runtime State
# =====================================================

mqtt_connected = threading.Event()


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
        f"MQTT connection result: "
        f"{reason_code}"
    )

    if reason_code == 0:
        mqtt_connected.set()

        print(
            "ESP32 simulator connected "
            "to MQTT broker successfully."
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
# HMAC Signature
# =====================================================

def build_signing_string(
    payload: dict,
) -> str:
    return (
        f"{payload['device_id']}|"
        f"{payload['room_id']}|"
        f"{payload['power_kw']}|"
        f"{payload['energy_kwh']}|"
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
        settings.message_secret.encode(),
        signing_string.encode(),
        hashlib.sha256,
    ).hexdigest()


# =====================================================
# Generate Sensor Reading
# =====================================================

def generate_power_kw() -> float:
    return round(
        random.uniform(
            MIN_POWER_KW,
            MAX_POWER_KW,
        ),
        2,
    )


def update_energy_kwh(
    current_energy_kwh: float,
    power_kw: float,
) -> float:
    interval_hours = (
        SEND_INTERVAL_SECONDS
        / 3600.0
    )

    updated_energy = (
        current_energy_kwh
        + (
            power_kw
            * interval_hours
        )
    )

    return round(
        updated_energy,
        5,
    )


# =====================================================
# Payload
# =====================================================

def build_payload(
    power_kw: float,
    energy_kwh: float,
) -> dict:
    payload = {
        "device_id":
            DEVICE_ID,

        "room_id":
            ROOM_ID,

        "power_kw":
            power_kw,

        "energy_kwh":
            energy_kwh,

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
    payload: dict,
) -> bool:
    if not client.is_connected():
        print(
            "MQTT is disconnected. "
            "Reading was not published."
        )

        return False

    message = json.dumps(
        payload
    )

    try:
        result = client.publish(
            settings.mqtt_topic,
            message,
            qos=1,
        )

        if (
            result.rc
            != mqtt.MQTT_ERR_SUCCESS
        ):
            print(
                f"Publish failed. "
                f"rc={result.rc}"
            )

            return False

        result.wait_for_publish(
            timeout=5
        )

        if not result.is_published():
            print(
                "MQTT broker did not confirm "
                "publication."
            )

            return False

        print(
            f"{payload['timestamp']} | "
            f"{payload['device_id']} | "
            f"Power: "
            f"{payload['power_kw']} kW | "
            f"Energy: "
            f"{payload['energy_kwh']} kWh "
            f"[published]"
        )

        return True

    except Exception as e:
        print(
            f"Publish error: {e}"
        )

        return False


# =====================================================
# Main
# =====================================================

def main():
    mqtt_connected.clear()

    energy_kwh = (
        INITIAL_ENERGY_KWH
    )

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=(
            f"esp32-simulator-"
            f"{os.getpid()}"
        ),
    )

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
    # Automatic Reconnect
    # ---------------------------------------------

    client.reconnect_delay_set(
        min_delay=1,
        max_delay=10,
    )

    # ---------------------------------------------
    # Authentication
    # ---------------------------------------------

    client.username_pw_set(
        settings.mqtt_username,
        settings.mqtt_password,
    )

    # ---------------------------------------------
    # TLS
    # ---------------------------------------------

    client.tls_set()

    # ---------------------------------------------
    # Connection Information
    # ---------------------------------------------

    print(
        "ESP32 Sensor Simulator"
    )

    print(
        "-" * 60
    )

    print(
        f"Device: {DEVICE_ID}"
    )

    print(
        f"Room: {ROOM_ID}"
    )

    print(
        f"Broker: "
        f"{settings.mqtt_broker_host}:"
        f"{settings.mqtt_broker_port}"
    )

    print(
        f"Topic: "
        f"{settings.mqtt_topic}"
    )

    print(
        "TLS: enabled"
    )

    print(
        f"Publishing interval: "
        f"{SEND_INTERVAL_SECONDS} seconds"
    )

    print(
        "-" * 60
    )

    try:
        # -----------------------------------------
        # Connect
        # -----------------------------------------

        client.connect(
            settings.mqtt_broker_host,
            settings.mqtt_broker_port,
            60,
        )

        client.loop_start()

        print(
            "Waiting for MQTT connection..."
        )

        if not mqtt_connected.wait(
            timeout=15
        ):
            print(
                "Could not establish MQTT "
                "connection within 15 seconds."
            )

            return

        print(
            "ESP32 simulator started."
        )

        print(
            "Press CTRL+C to stop."
        )

        print(
            "-" * 60
        )

        # -----------------------------------------
        # Main Sensor Loop
        # -----------------------------------------

        while True:
            if not mqtt_connected.is_set():
                print(
                    "Waiting for MQTT "
                    "reconnection..."
                )

                mqtt_connected.wait(
                    timeout=10
                )

                if not mqtt_connected.is_set():
                    print(
                        "MQTT still disconnected. "
                        "Skipping this interval."
                    )

                    time.sleep(
                        SEND_INTERVAL_SECONDS
                    )

                    continue

            power_kw = (
                generate_power_kw()
            )

            energy_kwh = (
                update_energy_kwh(
                    energy_kwh,
                    power_kw,
                )
            )

            payload = (
                build_payload(
                    power_kw,
                    energy_kwh,
                )
            )

            publish_reading(
                client,
                payload,
            )

            time.sleep(
                SEND_INTERVAL_SECONDS
            )

    except KeyboardInterrupt:
        print()

        print(
            "Stopping ESP32 simulator..."
        )

    except Exception as e:
        print(
            f"ESP32 simulator error: {e}"
        )

    finally:
        mqtt_connected.clear()

        if client.is_connected():
            try:
                client.disconnect()
            except Exception as e:
                print(
                    f"Disconnect warning: {e}"
                )

        try:
            client.loop_stop()
        except Exception:
            pass

        print(
            "ESP32 simulator stopped."
        )


# =====================================================
# Entry Point
# =====================================================

if __name__ == "__main__":
    main()