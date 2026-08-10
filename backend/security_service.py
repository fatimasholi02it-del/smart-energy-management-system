from database import SessionLocal
import models


def get_security_events(limit: int = 100):

    db = SessionLocal()

    try:

        events = (
            db.query(models.SecurityEvent)
            .order_by(
                models.SecurityEvent.id.desc()
            )
            .limit(limit)
            .all()
        )

        result = []

        for e in events:

            result.append({
                "id": e.id,
                "event_type": e.event_type,
                "reason": e.reason,
                "device_id": e.device_id,
                "room_id": e.room_id,
                "raw_payload": e.raw_payload,
                "timestamp": (
                    e.timestamp.isoformat()
                    if e.timestamp
                    else None
                )
            })

        return result

    finally:

        db.close()