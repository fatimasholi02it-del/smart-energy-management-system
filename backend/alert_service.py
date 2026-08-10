from datetime import datetime, timedelta

from database import SessionLocal
import models


def create_alert(
    alert_type: str,
    severity: str,
    message: str,
    device_id: str = None,
    room_id: str = None
):

    db = SessionLocal()

    try:

        alert = models.Alert(
            device_id=device_id,
            room_id=room_id,
            alert_type=alert_type,
            severity=severity,
            message=message,
            status="Open",
            created_at=datetime.now()
        )

        db.add(alert)
        db.commit()
        db.refresh(alert)

        return {
            "id": alert.id,
            "device_id": alert.device_id,
            "room_id": alert.room_id,
            "alert_type": alert.alert_type,
            "severity": alert.severity,
            "message": alert.message,
            "status": alert.status,
            "created_at": (
                alert.created_at.isoformat()
                if alert.created_at
                else None
            )
        }

    except Exception as e:

        db.rollback()

        print(
            f"Failed creating alert: {e}"
        )

        return None

    finally:

        db.close()


def get_alerts(
    limit: int = 100,
    status: str = None,
    severity: str = None,
    device_id: str = None
):

    db = SessionLocal()

    try:

        query = db.query(
            models.Alert
        )

        if status:

            query = query.filter(
                models.Alert.status == status
            )

        if severity:

            query = query.filter(
                models.Alert.severity == severity
            )

        if device_id:

            query = query.filter(
                models.Alert.device_id == device_id
            )

        alerts = (
            query
            .order_by(
                models.Alert.id.desc()
            )
            .limit(limit)
            .all()
        )

        return [
            {
                "id": alert.id,
                "device_id": alert.device_id,
                "room_id": alert.room_id,
                "alert_type": alert.alert_type,
                "severity": alert.severity,
                "message": alert.message,
                "status": alert.status,
                "created_at": (
                    alert.created_at.isoformat()
                    if alert.created_at
                    else None
                )
            }
            for alert in alerts
        ]

    finally:

        db.close()


def create_alert_if_not_duplicate(
    alert_type: str,
    severity: str,
    message: str,
    device_id: str = None,
    room_id: str = None,
    duplicate_window_minutes: int = 5
):

    db = SessionLocal()

    try:

        cutoff_time = (
            datetime.now()
            - timedelta(
                minutes=duplicate_window_minutes
            )
        )

        query = db.query(
            models.Alert
        ).filter(
            models.Alert.alert_type == alert_type,
            models.Alert.created_at >= cutoff_time
        )

        if device_id is not None:
            query = query.filter(
                models.Alert.device_id == device_id
            )

        if room_id is not None:
            query = query.filter(
                models.Alert.room_id == room_id
            )

        existing_alert = (
            query
            .order_by(
                models.Alert.id.desc()
            )
            .first()
        )

        if existing_alert:

            return {
                "created": False,
                "reason": "Duplicate alert suppressed",
                "alert_id": existing_alert.id
            }

        alert = models.Alert(
            device_id=device_id,
            room_id=room_id,
            alert_type=alert_type,
            severity=severity,
            message=message,
            status="Open",
            created_at=datetime.now()
        )

        db.add(alert)

        db.commit()

        db.refresh(alert)

        return {
            "created": True,
            "alert_id": alert.id
        }

    except Exception as e:

        db.rollback()

        print(
            f"Failed creating alert: {e}"
        )

        return {
            "created": False,
            "error": str(e)
        }

    finally:

        try:
            db.close()
        except Exception as e:
            print(
                f"Database close warning: {e}"
            )