import json
import hmac
import hashlib
import time
from datetime import datetime

import paho.mqtt.client as mqtt
from sqlalchemy.orm import Session

import models
from config import settings
from database import SessionLocal


# =====================================================
# Runtime State
# =====================================================

last_timestamp_by_stream = {}
last_seen_by_device = {}


# =====================================================
# Real Sensors
# =====================================================

REAL_SENSOR_DEVICES = {
    "esp32_01"
}


# Hard physical limits for instantaneous power.
# This is NOT the normal operating range.
# Unusual readings inside this range should reach the AI.
SENSOR_POWER_HARD_LIMITS = {
    "esp32_01": {
        "min": 0.0,
        "max": 20.0
    }
}


# =====================================================
# Device Helpers
# =====================================================

def is_simulator_device(device_id: str) -> bool:

    return (
        bool(device_id)
        and device_id.startswith("simulator_")
    )


def is_real_sensor_device(device_id: str) -> bool:

    return device_id in REAL_SENSOR_DEVICES


def get_data_source(device_id: str) -> str:

    if not device_id:
        return "unknown"

    if is_simulator_device(device_id):
        return "simulator"

    if is_real_sensor_device(device_id):
        return "sensor"

    return "sensor"


# =====================================================
# Security Events
# =====================================================

def save_security_event(
    event_type,
    reason,
    raw_payload=None,
    device_id=None,
    room_id=None
):

    db: Session = SessionLocal()

    try:

        event = models.SecurityEvent(
            device_id=device_id,
            room_id=room_id,
            event_type=event_type,
            reason=reason,
            raw_payload=raw_payload,
            timestamp=datetime.now()
        )

        db.add(event)
        db.commit()
        db.refresh(event)

        print(
            f"Security event saved: "
            f"{event.event_type} - "
            f"{event.reason}"
        )

    except Exception as e:

        db.rollback()

        print(
            f"Failed to save security event: {e}"
        )

    finally:

        try:
            db.close()

        except Exception as e:
            print(
                f"Security DB close warning: {e}"
            )


# =====================================================
# Signature
# =====================================================

def build_signing_string(
    reading_data: dict
) -> str:

    device_id = reading_data["device_id"]

    # -------------------------------------------------
    # Real ESP32 Sensor
    # -------------------------------------------------

    if is_real_sensor_device(device_id):

        return (
            f"{reading_data['device_id']}|"
            f"{reading_data['room_id']}|"
            f"{reading_data['power_kw']}|"
            f"{reading_data['energy_kwh']}|"
            f"{reading_data['timestamp']}"
        )

    # -------------------------------------------------
    # Simulator - keep existing format
    # -------------------------------------------------

    return (
        f"{reading_data['device_id']}|"
        f"{reading_data['room_id']}|"
        f"{reading_data['energy']}|"
        f"{reading_data['timestamp']}"
    )


def generate_expected_signature(
    reading_data: dict
) -> str:

    signing_string = build_signing_string(
        reading_data
    )

    return hmac.new(
        settings.message_secret.encode(),
        signing_string.encode(),
        hashlib.sha256
    ).hexdigest()


# =====================================================
# Replay Attack Protection
# =====================================================

def is_replay_attack(
    device_id,
    room_id,
    message_timestamp
):

    current_ts = datetime.fromisoformat(
        message_timestamp
    )

    stream_key = (
        device_id,
        room_id
    )

    last_ts = last_timestamp_by_stream.get(
        stream_key
    )

    if last_ts is not None:

        if current_ts <= last_ts:
            return True

    return False


def update_last_seen_timestamp(
    device_id,
    room_id,
    message_timestamp
):

    stream_key = (
        device_id,
        room_id
    )

    last_timestamp_by_stream[
        stream_key
    ] = datetime.fromisoformat(
        message_timestamp
    )


def update_device_last_seen(
    device_id
):

    last_seen_by_device[
        device_id
    ] = datetime.now()


# =====================================================
# Device Health
# =====================================================

def update_device_health(
    reading_data: dict
):

    db: Session = SessionLocal()

    try:

        device_id = reading_data.get(
            "device_id"
        )

        room_id = reading_data.get(
            "room_id"
        )

        source = get_data_source(
            device_id
        )

        device = (
            db.query(
                models.DeviceHealth
            )
            .filter(
                models.DeviceHealth.device_id
                == device_id
            )
            .first()
        )

        if device:

            device.room_id = room_id
            device.source = source
            device.last_seen = datetime.now()
            device.status = "Online"

        else:

            device = models.DeviceHealth(
                device_id=device_id,
                room_id=room_id,
                source=source,
                last_seen=datetime.now(),
                status="Online"
            )

            db.add(device)

        db.commit()

        print(
            f"Device health updated: "
            f"{device_id} ({source})"
        )

    except Exception as e:

        db.rollback()

        print(
            f"Failed updating device health: {e}"
        )

    finally:

        try:
            db.close()

        except Exception as e:

            print(
                f"Device health DB close warning: {e}"
            )


# =====================================================
# Simulator Energy Validation
# =====================================================

def validate_simulator_energy(
    room_id,
    energy
):

    if room_id not in settings.allowed_rooms:

        return (
            False,
            f"Unknown room_id: {room_id}"
        )

    min_energy, max_energy = (
        settings.allowed_rooms[
            room_id
        ]
    )

    if not (
        min_energy
        <= energy
        <= max_energy
    ):

        return (
            False,
            (
                f"Simulator energy {energy} "
                f"is outside allowed range "
                f"[{min_energy}, {max_energy}]"
            )
        )

    return True, None


# =====================================================
# Real Sensor Power Validation
# =====================================================

def validate_sensor_power(
    device_id,
    power_kw
):

    limits = SENSOR_POWER_HARD_LIMITS.get(
        device_id
    )

    if limits is None:

        return (
            False,
            f"No hard limits configured for {device_id}"
        )

    min_power = limits["min"]
    max_power = limits["max"]

    if not (
        min_power
        <= power_kw
        <= max_power
    ):

        return (
            False,
            (
                f"Sensor power {power_kw} kW "
                f"is outside hard limits "
                f"[{min_power}, {max_power}]"
            )
        )

    return True, None


# =====================================================
# Validate Reading
# =====================================================

def validate_reading(
    reading_data: dict
):

    errors = []

    # -------------------------------------------------
    # Basic required fields
    # -------------------------------------------------

    basic_required_fields = [
        "device_id",
        "room_id",
        "timestamp",
        "signature"
    ]

    for field in basic_required_fields:

        if field not in reading_data:

            errors.append({
                "event_type":
                    "missing_field",

                "reason":
                    f"Missing field: {field}"
            })

    if errors:
        return False, errors

    device_id = reading_data[
        "device_id"
    ]

    room_id = reading_data[
        "room_id"
    ]

    timestamp = reading_data[
        "timestamp"
    ]

    provided_signature = reading_data[
        "signature"
    ]

    # -------------------------------------------------
    # Device-specific required fields
    # -------------------------------------------------

    if is_real_sensor_device(device_id):

        sensor_required_fields = [
            "power_kw",
            "energy_kwh"
        ]

        for field in sensor_required_fields:

            if field not in reading_data:

                errors.append({
                    "event_type":
                        "missing_field",

                    "reason":
                        f"Missing sensor field: {field}"
                })

    else:

        if "energy" not in reading_data:

            errors.append({
                "event_type":
                    "missing_field",

                "reason":
                    "Missing field: energy"
            })

    if errors:
        return False, errors

    # -------------------------------------------------
    # Trusted Device
    # -------------------------------------------------

    if device_id not in settings.trusted_devices:

        errors.append({
            "event_type":
                "unknown_device",

            "reason":
                f"Unknown device_id: {device_id}"
        })

    # -------------------------------------------------
    # Room
    # -------------------------------------------------

    room_is_known = (
        room_id in settings.allowed_rooms
    )

    if not room_is_known:

        errors.append({
            "event_type":
                "unknown_room",

            "reason":
                f"Unknown room_id: {room_id}"
        })

    # -------------------------------------------------
    # Timestamp
    # -------------------------------------------------

    parsed_timestamp = None

    try:

        parsed_timestamp = datetime.fromisoformat(
            timestamp
        )

    except (
        ValueError,
        TypeError
    ):

        errors.append({
            "event_type":
                "invalid_timestamp",

            "reason":
                f"Invalid timestamp: {timestamp}"
        })

    # =================================================
    # REAL SENSOR VALIDATION
    # =================================================

    if is_real_sensor_device(device_id):

        power_kw = reading_data[
            "power_kw"
        ]

        energy_kwh = reading_data[
            "energy_kwh"
        ]

        # Power type

        if not isinstance(
            power_kw,
            (int, float)
        ):

            errors.append({
                "event_type":
                    "invalid_power_type",

                "reason":
                    "power_kw must be numeric"
            })

        else:

            power_valid, power_error = (
                validate_sensor_power(
                    device_id,
                    float(power_kw)
                )
            )

            if not power_valid:

                errors.append({
                    "event_type":
                        "out_of_range_power",

                    "reason":
                        power_error
                })

        # Energy type

        if not isinstance(
            energy_kwh,
            (int, float)
        ):

            errors.append({
                "event_type":
                    "invalid_energy_type",

                "reason":
                    "energy_kwh must be numeric"
            })

        elif float(energy_kwh) < 0:

            errors.append({
                "event_type":
                    "invalid_energy_value",

                "reason":
                    "energy_kwh cannot be negative"
            })

    # =================================================
    # SIMULATOR VALIDATION
    # =================================================

    else:

        energy = reading_data[
            "energy"
        ]

        if not isinstance(
            energy,
            (int, float)
        ):

            errors.append({
                "event_type":
                    "invalid_energy_type",

                "reason":
                    "Energy must be numeric"
            })

        elif room_is_known:

            energy_valid, energy_error = (
                validate_simulator_energy(
                    room_id,
                    float(energy)
                )
            )

            if not energy_valid:

                errors.append({
                    "event_type":
                        "out_of_range_energy",

                    "reason":
                        energy_error
                })

    # -------------------------------------------------
    # Signature
    # -------------------------------------------------

    try:

        expected_signature = (
            generate_expected_signature(
                reading_data
            )
        )

        if not hmac.compare_digest(
            str(provided_signature),
            expected_signature
        ):

            errors.append({
                "event_type":
                    "invalid_signature",

                "reason":
                    "Signature validation failed"
            })

    except Exception as e:

        errors.append({
            "event_type":
                "invalid_signature",

            "reason":
                f"Could not validate signature: {e}"
        })

    # -------------------------------------------------
    # Replay Attack
    # -------------------------------------------------

    if (
        parsed_timestamp is not None
        and
        device_id in settings.trusted_devices
        and
        room_is_known
    ):

        try:

            if is_replay_attack(
                device_id,
                room_id,
                timestamp
            ):

                errors.append({
                    "event_type":
                        "replay_attack",

                    "reason":
                        (
                            f"Replay attack detected "
                            f"for {device_id}"
                        )
                })

        except Exception as e:

            errors.append({
                "event_type":
                    "invalid_timestamp",

                "reason":
                    str(e)
            })

    # -------------------------------------------------
    # Final Result
    # -------------------------------------------------

    if errors:
        return False, errors

    return True, []


# =====================================================
# Save Reading
# =====================================================

def save_reading_to_db(
    reading_data: dict
):

    db: Session = SessionLocal()

    try:

        parsed_timestamp = (
            datetime.fromisoformat(
                reading_data[
                    "timestamp"
                ]
            )
        )

        device_id = reading_data[
            "device_id"
        ]

        room_id = reading_data[
            "room_id"
        ]

        data_source = get_data_source(
            device_id
        )

        # =================================================
        # Real ESP32
        # =================================================

        if is_real_sensor_device(
            device_id
        ):

            power_kw = float(
                reading_data[
                    "power_kw"
                ]
            )

            energy_kwh = float(
                reading_data[
                    "energy_kwh"
                ]
            )

            # Keep legacy "energy" populated with POWER
            # so existing AI / Forecast / MPC still work.
            legacy_energy = power_kw

        # =================================================
        # Simulator
        # =================================================

        else:

            legacy_energy = float(
                reading_data[
                    "energy"
                ]
            )

            power_kw = legacy_energy

            energy_kwh = None

        # =================================================
        # Save
        # =================================================

        db_reading = models.EnergyReading(
            device_id=device_id,
            room_id=room_id,

            # Current compatibility field
            energy=legacy_energy,

            # New explicit fields
            power_kw=power_kw,
            energy_kwh=energy_kwh,

            timestamp=parsed_timestamp,
            data_source=data_source
        )

        db.add(
            db_reading
        )

        db.commit()

        db.refresh(
            db_reading
        )

        print(
            f"Saved MQTT reading: "
            f"id={db_reading.id}, "
            f"device={device_id}, "
            f"source={data_source}, "
            f"power_kw={db_reading.power_kw}, "
            f"energy_kwh={db_reading.energy_kwh}"
        )

    except Exception as e:

        db.rollback()

        print(
            f"Failed saving reading: {e}"
        )

    finally:

        try:
            db.close()

        except Exception as e:

            print(
                f"Reading DB close warning: {e}"
            )


# =====================================================
# MQTT Connect
# =====================================================

def on_connect(
    client,
    userdata,
    flags,
    reason_code,
    properties=None
):

    print(
        f"MQTT on_connect rc={reason_code}"
    )

    if reason_code == 0:

        print(
            "Connected successfully"
        )

        client.subscribe(
            settings.mqtt_topic,
            qos=1
        )

        print(
            f"Subscribed: "
            f"{settings.mqtt_topic}"
        )


# =====================================================
# MQTT Message
# =====================================================

def on_message(
    client,
    userdata,
    msg
):

    payload = None

    try:

        print(
            f"RAW MQTT topic: "
            f"{msg.topic}"
        )

        payload = msg.payload.decode(
            "utf-8"
        )

        print(
            f"Received MQTT: "
            f"{payload}"
        )

        reading_data = json.loads(
            payload
        )

        if not isinstance(
            reading_data,
            dict
        ):

            raise ValueError(
                "MQTT payload must be a JSON object"
            )

        # -------------------------------------------------
        # Validation
        # -------------------------------------------------

        is_valid, errors = (
            validate_reading(
                reading_data
            )
        )

        if not is_valid:

            for error in errors:

                save_security_event(
                    event_type=
                        error["event_type"],

                    reason=
                        error["reason"],

                    raw_payload=
                        payload,

                    device_id=
                        reading_data.get(
                            "device_id"
                        ),

                    room_id=
                        reading_data.get(
                            "room_id"
                        )
                )

            return

        # -------------------------------------------------
        # Valid Message
        # -------------------------------------------------

        update_last_seen_timestamp(
            reading_data[
                "device_id"
            ],
            reading_data[
                "room_id"
            ],
            reading_data[
                "timestamp"
            ]
        )

        update_device_last_seen(
            reading_data[
                "device_id"
            ]
        )

        update_device_health(
            reading_data
        )

        save_reading_to_db(
            reading_data
        )

    except Exception as e:

        save_security_event(
            event_type=
                "malformed_payload",

            reason=
                str(e),

            raw_payload=
                payload
        )

        print(
            f"MQTT processing error: {e}"
        )


# =====================================================
# Start MQTT Consumer
# =====================================================

def start_mqtt_consumer():

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2
    )

    client.on_connect = on_connect
    client.on_message = on_message

    # -------------------------------------------------
    # Authentication + TLS
    # -------------------------------------------------

    if (
        settings.mqtt_username
        and
        settings.mqtt_password
    ):

        client.username_pw_set(
            settings.mqtt_username,
            settings.mqtt_password
        )

        client.tls_set()

    # -------------------------------------------------
    # Connect
    # -------------------------------------------------

    client.connect(
        settings.mqtt_broker_host,
        settings.mqtt_broker_port,
        60
    )

    client.loop_start()

    return client


# =====================================================
# Main
# =====================================================

if __name__ == "__main__":

    print(
        "Starting MQTT consumer..."
    )

    client = start_mqtt_consumer()

    print(
        "MQTT consumer started"
    )

    try:

        while True:
            time.sleep(1)

    except KeyboardInterrupt:

        print(
            "Stopping MQTT consumer..."
        )

        client.loop_stop()

        client.disconnect()