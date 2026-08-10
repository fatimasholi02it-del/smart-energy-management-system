from datetime import datetime

from alert_service import create_alert_if_not_duplicate


def generate_alerts(
    ai_monitoring,
    devices=None
):

    alerts = []

    # =====================================================
    # AI Energy Anomaly
    # =====================================================

    if ai_monitoring:

        ai_result = ai_monitoring.get(
            "ai_result",
            {}
        )
        if not ai_result:
         ai_result = {}

        if ai_result.get("is_anomaly"):

            current_reading = ai_monitoring.get(
                "current_reading",
                {}
            )

            device_id = current_reading.get(
                "device_id"
            )

            room_id = current_reading.get(
                "room_id"
            )

            severity = ai_result.get(
                "severity",
                "Medium"
            )

            message = ai_result.get(
                "message",
                "Abnormal energy consumption detected."
            )

            alert = {
                "type": "Energy Anomaly",
                "severity": severity,
                "device_id": device_id,
                "room_id": room_id,
                "energy": current_reading.get(
                    "energy"
                ),
                "timestamp": current_reading.get(
                    "timestamp"
                ),
                "message": message
            }

            alerts.append(alert)

            create_alert_if_not_duplicate(
                alert_type="Energy Anomaly",
                severity=severity,
                message=message,
                device_id=device_id,
                room_id=room_id,
                duplicate_window_minutes=5
            )

    # =====================================================
    # Device Offline
    # =====================================================

    if devices:

        for device in devices:

            # Simulator devices are for testing only.
            # Do not create production offline alerts for them.
            if device.get("source") != "sensor":
                continue

            if device.get("status") == "Offline":

                device_id = device.get(
                    "device_id"
                )

                room_id = device.get(
                    "room_id"
                )

                message = (
                    f"Device {device_id} is offline."
                )

                alert = {
                    "type":
                        "Device Offline",

                    "severity":
                        "High",

                    "device_id":
                        device_id,

                    "room_id":
                        room_id,

                    "message":
                        message
                }

                alerts.append(
                    alert
                )

                create_alert_if_not_duplicate(
                    alert_type="Device Offline",
                    severity="High",
                    message=message,
                    device_id=device_id,
                    room_id=room_id,
                    duplicate_window_minutes=5
                )

    return {
        "generated_at": datetime.now().isoformat(),
        "total_alerts": len(alerts),
        "items": alerts
    }