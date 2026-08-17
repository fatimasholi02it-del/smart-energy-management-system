import hashlib
import hmac
import json
import os
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
# Test Configuration
# =====================================================

TEST_DEVICE_ID = "simulator_02"
TEST_ROOM_ID = "room_2"

# simulator_02 normally generates approximately
# 1.8 - 3.5 kW.
#
# This test intentionally sends a lower reading
# so the message remains correctly signed and trusted,
# but its energy value is unusual compared with the
# device's normal learned behavior.
ANOMALY_ENERGY_KW = 1.5


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

    if not MESSAGE_SECRET:
        missing_variables.append(
            "MESSAGE_SECRET"
        )

    if not TOPIC:
        missing_variables.append(
            "MQTT_TOPIC"
        )

    if missing_variables:
        print(
            "Anomaly test configuration error."
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
            "Anomaly test configuration error: "
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
# Anomaly Payload
# =====================================================

def build_anomaly_payload() -> dict:
    payload = {
        "device_id":
            TEST_DEVICE_ID,

        "room_id":
            TEST_ROOM_ID,

        # Legacy simulator contract:
        # "energy" currently represents
        # instantaneous power in kW.
        "energy":
            ANOMALY_ENERGY_KW,

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
    if not validate_environment():
        return

    mqtt_connected.clear()

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=(
            f"anomaly-detection-test-"
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
        "AI Anomaly Detection Test"
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
        # Build valid unusual reading
        # -----------------------------------------

        payload = (
            build_anomaly_payload()
        )

        message = json.dumps(
            payload
        )

        print()
        print(
            "Publishing valid but unusual "
            "energy reading..."
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
            f"Timestamp: "
            f"{payload['timestamp']}"
        )

        print(
            "Signature: valid HMAC "
            "(hidden from console)"
        )

        print()
        print(
            "This message is intentionally "
            "different from a security attack:"
        )

        print(
            "  - Device is trusted."
        )

        print(
            "  - Room mapping is correct."
        )

        print(
            "  - Signature is valid."
        )

        print(
            "  - Energy value is intentionally "
            "unusual."
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
            "Unusual reading published "
            "successfully."
        )

        print()
        print(
            "Expected processing flow:"
        )

        print(
            "  1. HMAC validation succeeds."
        )

        print(
            "  2. Trusted-device validation succeeds."
        )

        print(
            "  3. Reading reaches the normal "
            "energy-processing pipeline."
        )

        print(
            "  4. AI anomaly detection evaluates "
            "the reading."
        )

        print(
            "  5. Isolation Forest may classify "
            "the reading as anomalous based on "
            "the learned device pattern."
        )

        print()
        print(
            "Important:"
        )

        print(
            "Anomaly detection is statistical, "
            "so classification must be verified "
            "from the AI endpoint or AI Center."
        )

        # Give the backend time to process
        # and persist the reading.
        time.sleep(
            3
        )

        print()
        print(
            "Anomaly detection test completed."
        )

    except Exception as e:
        print(
            f"Anomaly test failed: {e}"
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
            "Anomaly detection test finished."
        )


# =====================================================
# Entry Point
# =====================================================

if __name__ == "__main__":
    main()