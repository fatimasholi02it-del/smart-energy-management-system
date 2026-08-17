import hashlib
import hmac
import json
import os
import threading

from datetime import datetime

import paho.mqtt.client as mqtt

from config import settings


# =====================================================
# ESP32 Test Configuration
# =====================================================

DEVICE_ID = "esp32_01"
ROOM_ID = "room_1"

# Normal valid test values.
POWER_KW = 3.0
ENERGY_KWH = 15.42


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
            "ESP32 MQTT test connected "
            "successfully."
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
# Payload
# =====================================================

def build_payload() -> dict:
    payload = {
        "device_id":
            DEVICE_ID,

        "room_id":
            ROOM_ID,

        "power_kw":
            POWER_KW,

        "energy_kwh":
            ENERGY_KWH,

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
# Main
# =====================================================

def main():
    mqtt_connected.clear()

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=(
            f"esp32-valid-message-test-"
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

    print(
        "ESP32 Valid MQTT Message Test"
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

        # -----------------------------------------
        # Build payload
        # -----------------------------------------

        payload = (
            build_payload()
        )

        message = json.dumps(
            payload
        )

        print()
        print(
            "Publishing valid ESP32 reading..."
        )

        print(
            f"Device: "
            f"{payload['device_id']}"
        )

        print(
            f"Room: "
            f"{payload['room_id']}"
        )

        print(
            f"Power: "
            f"{payload['power_kw']} kW"
        )

        print(
            f"Energy: "
            f"{payload['energy_kwh']} kWh"
        )

        print(
            f"Timestamp: "
            f"{payload['timestamp']}"
        )

        print(
            "Signature: valid HMAC "
            "(hidden from console)"
        )

        # -----------------------------------------
        # Publish
        # -----------------------------------------

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

            return

        result.wait_for_publish(
            timeout=5
        )

        if not result.is_published():
            print(
                "MQTT broker did not confirm "
                "publication."
            )

            return

        print()
        print(
            "ESP32 test message published "
            "successfully."
        )

        print()
        print(
            "Expected backend behavior:"
        )

        print(
            "  1. Validate the HMAC signature."
        )

        print(
            "  2. Recognize esp32_01 as "
            "a trusted sensor."
        )

        print(
            "  3. Accept the room mapping."
        )

        print(
            "  4. Store power_kw and "
            "energy_kwh."
        )

        print(
            "  5. Update device health."
        )

        print(
            "  6. Make the reading available "
            "to the mobile application."
        )

    except Exception as e:
        print(
            f"ESP32 MQTT test failed: {e}"
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
            "ESP32 MQTT test finished."
        )


# =====================================================
# Entry Point
# =====================================================

if __name__ == "__main__":
    main()