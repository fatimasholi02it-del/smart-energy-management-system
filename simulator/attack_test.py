import json
import os
import threading

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


# =====================================================
# Runtime State
# =====================================================

mqtt_connected = threading.Event()


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

    if not TOPIC:
        missing_variables.append(
            "MQTT_TOPIC"
        )

    if missing_variables:
        print(
            "Attack test configuration error."
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
            "before running this test."
        )

        return False

    if (
        BROKER_PORT <= 0
        or BROKER_PORT > 65535
    ):
        print(
            "Attack test configuration error: "
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
        f"MQTT connection result: "
        f"{reason_code}"
    )

    if reason_code == 0:
        mqtt_connected.set()

        print(
            "Connected to MQTT broker successfully."
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


# =====================================================
# Invalid Signature Payload
# =====================================================

def build_tampered_payload() -> dict:
    return {
        "device_id": "simulator_01",
        "room_id": "room_1",

        # Legacy simulator contract:
        # energy currently represents
        # instantaneous power in kW.
        "energy": 3.2,

        "timestamp":
            datetime.now().isoformat(),

        # Intentionally INVALID signature.
        # This is the purpose of this test.
        "signature":
            "fake-invalid-signature",
    }


# =====================================================
# Main
# =====================================================

def main():
    if not validate_environment():
        return

    mqtt_connected.clear()

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=(
            f"security-invalid-signature-test-"
            f"{os.getpid()}"
        ),
    )

    client.on_connect = (
        on_connect
    )

    client.on_disconnect = (
        on_disconnect
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

    print(
        "Invalid Signature Security Test"
    )

    print(
        "-" * 60
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
        # -----------------------------------------
        # Connect
        # -----------------------------------------

        client.connect(
            BROKER_HOST,
            BROKER_PORT,
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
        # Build tampered message
        # -----------------------------------------

        payload = (
            build_tampered_payload()
        )

        message = json.dumps(
            payload
        )

        print()
        print(
            "Publishing intentionally "
            "tampered message..."
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
            f"Energy: "
            f"{payload['energy']} kW"
        )

        print(
            "Signature: intentionally invalid"
        )

        # -----------------------------------------
        # Publish
        # -----------------------------------------

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
                f"Publish failed. "
                f"rc={result.rc}"
            )

            return

        result.wait_for_publish(
            timeout=5
        )

        if not result.is_published():
            print(
                "Broker did not confirm "
                "publication."
            )

            return

        print()
        print(
            "Tampered message published "
            "successfully."
        )

        print(
            "Expected backend behavior:"
        )

        print(
            "  1. Reject the energy reading."
        )

        print(
            "  2. Record an invalid-signature "
            "security event."
        )

        print(
            "  3. Do not treat the reading "
            "as trusted energy data."
        )

    except Exception as e:
        print(
            f"Attack test failed: {e}"
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
            "Invalid signature test finished."
        )


# =====================================================
# Entry Point
# =====================================================

if __name__ == "__main__":
    main()