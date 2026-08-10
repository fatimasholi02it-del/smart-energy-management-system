from datetime import datetime, timedelta
from collections import defaultdict

from sqlalchemy import func

from database import SessionLocal
import models


DEFAULT_FORECAST_HOURS = 6
HISTORY_DAYS = 30


def get_recent_average(hours: int = 24):
    db = SessionLocal()

    try:
        since_time = datetime.now() - timedelta(hours=hours)

        avg_value = (
            db.query(func.avg(models.EnergyReading.energy))
            .filter(models.EnergyReading.timestamp >= since_time)
            .scalar()
        )

        if avg_value is not None:
            return round(float(avg_value), 2)

        # fallback:
        # إذا ما في بيانات حديثة، ناخد متوسط آخر 100 قراءة
        rows = (
            db.query(models.EnergyReading.energy)
            .order_by(models.EnergyReading.timestamp.desc())
            .limit(100)
            .all()
        )

        values = [
            float(row.energy)
            for row in rows
            if row.energy is not None
        ]

        if not values:
            return 0.0

        return round(sum(values) / len(values), 2)

    finally:
        db.close()


def get_historical_readings(days: int = HISTORY_DAYS):
    db = SessionLocal()

    try:
        since_time = datetime.now() - timedelta(days=days)

        rows = (
            db.query(
                models.EnergyReading.energy,
                models.EnergyReading.timestamp
            )
            .filter(
                models.EnergyReading.timestamp >= since_time
            )
            .order_by(
                models.EnergyReading.timestamp.asc()
            )
            .all()
        )

        # إذا ما لقينا ضمن آخر 30 يوم،
        # نستخدم آخر 1000 قراءة موجودة بالقاعدة
        if not rows:
            rows = (
                db.query(
                    models.EnergyReading.energy,
                    models.EnergyReading.timestamp
                )
                .order_by(
                    models.EnergyReading.timestamp.desc()
                )
                .limit(1000)
                .all()
            )

            rows = list(reversed(rows))

        return rows

    finally:
        db.close()


def calculate_hourly_profile(rows):
    hourly_values = defaultdict(list)

    for row in rows:

        if row.timestamp is None:
            continue

        try:
            energy_value = float(row.energy)
        except (TypeError, ValueError):
            continue

        hour = row.timestamp.hour

        hourly_values[hour].append(
            energy_value
        )

    hourly_profile = {}

    for hour, values in hourly_values.items():

        if values:
            hourly_profile[hour] = round(
                sum(values) / len(values),
                2
            )

    return hourly_profile


def calculate_trend(rows, recent_count: int = 30):
    if len(rows) < 4:
        return 0.0

    recent_rows = rows[-recent_count:]

    values = []

    for row in recent_rows:

        try:
            values.append(
                float(row.energy)
            )
        except (TypeError, ValueError):
            continue

    if len(values) < 4:
        return 0.0

    midpoint = len(values) // 2

    first_half = values[:midpoint]
    second_half = values[midpoint:]

    first_avg = sum(first_half) / len(first_half)
    second_avg = sum(second_half) / len(second_half)

    trend = second_avg - first_avg

    # منع توقعات شاذة
    trend = max(
        -0.5,
        min(0.5, trend)
    )

    return round(trend, 3)


def get_load_forecast(
    forecast_hours: int = DEFAULT_FORECAST_HOURS
):
    rows = get_historical_readings()

    if not rows:
        return {
            "status": "no_data",
            "message": (
                "No energy readings are available. "
                "Run the simulator first."
            ),
            "forecast_hours": 0,
            "hours": []
        }

    recent_average = get_recent_average()

    hourly_profile = calculate_hourly_profile(
        rows
    )

    trend = calculate_trend(
        rows
    )

    now = datetime.now()

    forecasts = []

    for i in range(1, forecast_hours + 1):

        target_time = (
            now.replace(
                minute=0,
                second=0,
                microsecond=0
            )
            + timedelta(hours=i)
        )

        target_hour = target_time.hour

        historical_value = hourly_profile.get(
            target_hour,
            recent_average
        )

        trend_weight = min(
            i * 0.15,
            0.6
        )

        predicted_load = (
            historical_value
            + trend * trend_weight
        )

        predicted_load = round(
            max(predicted_load, 0.0),
            2
        )

        samples_for_hour = sum(
            1
            for row in rows
            if row.timestamp
            and row.timestamp.hour == target_hour
        )

        if samples_for_hour >= 20:
            confidence = "High"

        elif samples_for_hour >= 5:
            confidence = "Medium"

        else:
            confidence = "Low"

        forecasts.append({
            "forecast_time":
                target_time.isoformat(),

            "predicted_load":
                predicted_load,

            "historical_hour_average":
                historical_value,

            "samples_used_for_hour":
                samples_for_hour,

            "confidence":
                confidence
        })

    return {
        "status": "ok",

        "data_source":
            "simulation_or_sensor",

        "model":
            "Historical Hourly Profile + Recent Trend",

        "generated_at":
            datetime.now().isoformat(),

        "historical_records":
            len(rows),

        "recent_average":
            recent_average,

        "detected_trend":
            trend,

        "forecast_hours":
            len(forecasts),

        "hours":
            forecasts
    }