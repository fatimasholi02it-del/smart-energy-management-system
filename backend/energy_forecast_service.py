from datetime import datetime

from load_forecast_service import get_load_forecast
from solar_service import get_solar_forecast


def normalize_hour(timestamp: str):
    dt = datetime.fromisoformat(timestamp)

    return dt.replace(
        minute=0,
        second=0,
        microsecond=0
    )


def get_energy_forecast(hours: int = 6):

    solar_result = get_solar_forecast(
        hours=hours
    )

    load_result = get_load_forecast(
        forecast_hours=hours
    )

    if solar_result.get("status") != "ok":
        return {
            "status": "error",
            "source": "solar_forecast",
            "message": solar_result.get(
                "message",
                "Solar forecast unavailable"
            )
        }

    if load_result.get("status") != "ok":
        return {
            "status": "error",
            "source": "load_forecast",
            "message": load_result.get(
                "message",
                "Load forecast unavailable"
            )
        }

    solar_by_hour = {}

    for item in solar_result.get("hours", []):
        hour_key = normalize_hour(
            item["forecast_time"]
        )

        solar_by_hour[hour_key] = item

    load_by_hour = {}

    for item in load_result.get("hours", []):
        hour_key = normalize_hour(
            item["forecast_time"]
        )

        load_by_hour[hour_key] = item

    common_hours = sorted(
        set(solar_by_hour.keys())
        & set(load_by_hour.keys())
    )

    forecasts = []

    total_solar = 0.0
    total_load = 0.0

    for hour_key in common_hours:

        solar = solar_by_hour[hour_key]
        load = load_by_hour[hour_key]

        solar_power = float(
            solar.get(
                "estimated_solar_power_kw",
                0
            )
        )

        predicted_load = float(
            load.get(
                "predicted_load",
                0
            )
        )

        balance = round(
            solar_power - predicted_load,
            2
        )

        if balance > 0.20:
            energy_state = "Surplus"

        elif balance < -0.20:
            energy_state = "Deficit"

        else:
            energy_state = "Balanced"

        if energy_state == "Surplus":
            recommendation = (
                "Solar production is expected to exceed load. "
                "This is a favorable period for flexible loads."
            )

        elif energy_state == "Deficit":
            recommendation = (
                "Expected load exceeds solar production. "
                "Consider reducing or shifting flexible loads."
            )

        else:
            recommendation = (
                "Expected solar production and load are approximately balanced."
            )

        total_solar += solar_power
        total_load += predicted_load

        forecasts.append({
            "forecast_time": hour_key.isoformat(),

            "temperature": solar.get(
                "temperature"
            ),

            "cloud_percent": solar.get(
                "cloud_percent"
            ),

            "weather_condition": solar.get(
                "weather_condition"
            ),

            "solar_power_kw": round(
                solar_power,
                2
            ),

            "predicted_load_kw": round(
                predicted_load,
                2
            ),

            "energy_balance_kw": balance,

            "energy_state": energy_state,

            "load_forecast_confidence":
                load.get("confidence"),

            "recommendation":
                recommendation
        })

    total_balance = round(
        total_solar - total_load,
        2
    )

    if total_balance > 0:
        overall_state = "Expected Surplus"

    elif total_balance < 0:
        overall_state = "Expected Deficit"

    else:
        overall_state = "Balanced"

    return {
        "status": "ok",

        "mode": "prototype",

        "load_unit_assumption": "kW",

        "generated_at":
            datetime.now().isoformat(),

        "forecast_hours":
            len(forecasts),

        "summary": {
            "total_forecast_solar_kwh": round(
                total_solar,
                2
            ),

            "total_forecast_load_kwh": round(
                total_load,
                2
            ),

            "net_energy_balance_kwh":
                total_balance,

            "overall_state":
                overall_state
        },

        "hours": forecasts
    }