from datetime import datetime

from database import SessionLocal
import models


LIVE_AFTER_SECONDS = 30


def get_live_power_summary():
    db = SessionLocal()

    try:
        room_ids = [
            "room_1",
            "room_2",
            "room_3",
        ]

        now = datetime.now()

        rooms = []

        total_power_kw = 0.0
        live_room_count = 0
        stale_room_count = 0

        for room_id in room_ids:
            reading = (
                db.query(models.EnergyReading)
                .filter(
                    models.EnergyReading.room_id
                    == room_id
                )
                .order_by(
                    models.EnergyReading.timestamp.desc(),
                    models.EnergyReading.id.desc(),
                )
                .first()
            )

            # -----------------------------------------
            # No data
            # -----------------------------------------

            if reading is None:
                rooms.append(
                    {
                        "room_id": room_id,
                        "device_id": None,
                        "source": None,
                        "power_kw": 0.0,
                        "energy_kwh": None,
                        "timestamp": None,
                        "age_seconds": None,
                        "is_live": False,
                        "status": "No Data",
                    }
                )

                continue

            # -----------------------------------------
            # Power
            # -----------------------------------------

            power_kw = (
                reading.power_kw
                if reading.power_kw is not None
                else reading.energy
            )

            power_kw = round(
                float(power_kw or 0),
                3,
            )

            # -----------------------------------------
            # Cumulative energy
            # -----------------------------------------

            energy_kwh = (
                round(
                    float(reading.energy_kwh),
                    3,
                )
                if reading.energy_kwh is not None
                else None
            )

            # -----------------------------------------
            # Reading freshness
            # -----------------------------------------

            if reading.timestamp:
                age_seconds = max(
                    0,
                    int(
                        (
                            now
                            - reading.timestamp
                        ).total_seconds()
                    ),
                )
            else:
                age_seconds = None

            is_live = (
                age_seconds is not None
                and
                age_seconds <= LIVE_AFTER_SECONDS
            )

            # -----------------------------------------
            # Only LIVE readings contribute
            # to Current Power
            # -----------------------------------------

            if is_live:
                total_power_kw += power_kw
                live_room_count += 1
                status = "Live"
            else:
                stale_room_count += 1
                status = "Stale"

            rooms.append(
                {
                    "room_id": room_id,
                    "device_id": reading.device_id,
                    "source": reading.data_source,
                    "power_kw": power_kw,
                    "energy_kwh": energy_kwh,
                    "timestamp": (
                        reading.timestamp.isoformat()
                        if reading.timestamp
                        else None
                    ),
                    "age_seconds": age_seconds,
                    "is_live": is_live,
                    "status": status,
                }
            )

        # ---------------------------------------------
        # Top LIVE power room only
        # ---------------------------------------------

        live_rooms = [
            room
            for room in rooms
            if room["is_live"]
        ]

        top_room = max(
            live_rooms,
            key=lambda item: item["power_kw"],
            default=None,
        )

        return {
            "status": "ok",

            "live_threshold_seconds":
                LIVE_AFTER_SECONDS,

            "total_power_kw": round(
                total_power_kw,
                3,
            ),

            "live_room_count":
                live_room_count,

            "stale_room_count":
                stale_room_count,

            "top_power_room": (
                {
                    "room_id":
                        top_room["room_id"],

                    "power_kw":
                        top_room["power_kw"],
                }
                if top_room
                else None
            ),

            "rooms": rooms,
        }

    finally:
        db.close()