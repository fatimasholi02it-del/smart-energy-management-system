from database import SessionLocal
import models


def get_energy_history(
    device_id=None,
    room_id=None,
    limit=100,
    source=None
):

    db = SessionLocal()

    try:

        query = db.query(
            models.EnergyReading
        )

        # ---------------------------------
        # Filters
        # ---------------------------------

        if device_id:

            query = query.filter(
                models.EnergyReading.device_id
                == device_id
            )

        if room_id:

            query = query.filter(
                models.EnergyReading.room_id
                == room_id
            )

        if source:

            query = query.filter(
                models.EnergyReading.data_source
                == source
            )

        # ---------------------------------
        # Get rows
        # ---------------------------------

        rows = (
            query
            .order_by(
                models.EnergyReading.timestamp.desc()
            )
            .limit(limit)
            .all()
        )

        # ---------------------------------
        # Response
        # ---------------------------------

        result = []

        for r in rows:

            power_kw = (
                r.power_kw
                if r.power_kw is not None
                else r.energy
            )

            result.append(
                {
                    "id":
                        r.id,

                    "device_id":
                        r.device_id,

                    "room_id":
                        r.room_id,

                    "source":
                        r.data_source,

                    "power_kw":
                        power_kw,

                    "energy_kwh":
                        r.energy_kwh,

                    # Temporary compatibility field
                    "energy":
                        r.energy,

                    "timestamp":
                        (
                            r.timestamp.isoformat()
                            if r.timestamp
                            else None
                        )
                }
            )

        return result

    finally:

        try:
            db.close()

        except Exception as e:

            print(
                f"Energy history DB close warning: {e}"
            )