from datetime import datetime

from database import SessionLocal
import models


DELAYED_AFTER_SECONDS = 30
OFFLINE_AFTER_SECONDS = 90


def calculate_device_status(last_seen):

    if last_seen is None:
        return "Offline"

    now = datetime.now()

    age_seconds = (
        now - last_seen
    ).total_seconds()

    # حماية في حال اختلاف بسيط بالتوقيت
    age_seconds = max(
        0,
        age_seconds
    )

    if age_seconds <= DELAYED_AFTER_SECONDS:
        return "Online"

    if age_seconds <= OFFLINE_AFTER_SECONDS:
        return "Delayed"

    return "Offline"


def get_devices():

    db = SessionLocal()

    try:

        devices = (
            db.query(models.DeviceHealth)
            .order_by(
                models.DeviceHealth.device_id.asc()
            )
            .all()
        )

        result = []

        for device in devices:

            status = calculate_device_status(
                device.last_seen
            )

            age_seconds = None

            if device.last_seen:

                age_seconds = max(
                    0,
                    int(
                        (
                            datetime.now()
                            - device.last_seen
                        ).total_seconds()
                    )
                )

            total_readings = (
                db.query(models.EnergyReading)
                .filter(
                    models.EnergyReading.device_id
                    == device.device_id
                )
                .count()
            )

            result.append({
                "device_id":
                    device.device_id,

                "room_id":
                    device.room_id,

                "source":
                    device.source,

                "status":
                    status,

                "last_seen":
                    (
                        device.last_seen.isoformat()
                        if device.last_seen
                        else None
                    ),

                "seconds_since_last_seen":
                    age_seconds,

                "total_readings":
                    total_readings
            })

        return result

    finally:

        try:
            db.close()

        except Exception as e:

            print(
                f"Device DB close warning: {e}"
            )