from datetime import datetime

from ml_load_forecast_service import (
    get_ml_load_forecast
)

from solar_service import (
    get_solar_forecast
)


def normalize_hour(timestamp: str):
    dt = datetime.fromisoformat(
        timestamp
    )

    return dt.replace(
        minute=0,
        second=0,
        microsecond=0
    )


def get_ml_energy_forecast(
    hours: int = 6,
    source: str = "auto"
):
    # =====================================================
    # ML Load Forecast
    # =====================================================

    load_result = get_ml_load_forecast(
        forecast_hours=hours,
        source=source
    )

    if load_result.get(
        "status"
    ) != "ok":
        return {
            "status":
                load_result.get(
                    "status",
                    "error"
                ),

            "source":
                "ml_load_forecast",

            "message":
                load_result.get(
                    "message",
                    "ML load forecast unavailable"
                ),

            "details":
                load_result
        }

    # =====================================================
    # Solar Forecast
    # =====================================================

    solar_result = get_solar_forecast(
        hours=hours
    )

    if solar_result.get(
        "status"
    ) != "ok":
        return {
            "status": "error",

            "source":
                "solar_forecast",

            "message":
                solar_result.get(
                    "message",
                    "Solar forecast unavailable"
                )
        }

    # =====================================================
    # Index both forecasts by hour
    # =====================================================

    load_by_hour = {}

    for item in load_result.get(
        "hours",
        []
    ):
        key = normalize_hour(
            item["forecast_time"]
        )

        load_by_hour[key] = item

    solar_by_hour = {}

    for item in solar_result.get(
        "hours",
        []
    ):
        key = normalize_hour(
            item["forecast_time"]
        )

        solar_by_hour[key] = item

    common_hours = sorted(
        set(
            load_by_hour.keys()
        )
        &
        set(
            solar_by_hour.keys()
        )
    )

    forecasts = []

    total_load = 0.0
    total_solar = 0.0

    # =====================================================
    # Merge Load + Solar
    # =====================================================

    for hour_key in common_hours:

        load_item = load_by_hour[
            hour_key
        ]

        solar_item = solar_by_hour[
            hour_key
        ]

        predicted_load = float(
            load_item.get(
                "predicted_load_kw",
                0.0
            )
        )

        solar_power = float(
            solar_item.get(
                "estimated_solar_power_kw",
                0.0
            )
        )

        energy_balance = round(
            solar_power
            - predicted_load,
            3
        )

        if energy_balance > 0.20:
            energy_state = "Surplus"

        elif energy_balance < -0.20:
            energy_state = "Deficit"

        else:
            energy_state = "Balanced"

        total_load += predicted_load
        total_solar += solar_power

        forecasts.append({
            "forecast_time":
                hour_key.isoformat(),

            "temperature":
                solar_item.get(
                    "temperature"
                ),

            "cloud_percent":
                solar_item.get(
                    "cloud_percent"
                ),

            "weather_condition":
                solar_item.get(
                    "weather_condition"
                ),

            "shortwave_radiation_wm2":
                solar_item.get(
                    "shortwave_radiation_wm2"
                ),

            "solar_power_kw":
                round(
                    solar_power,
                    3
                ),

            "predicted_load_kw":
                round(
                    predicted_load,
                    3
                ),

            "energy_balance_kw":
                energy_balance,

            "energy_state":
                energy_state
        })

    total_balance = round(
        total_solar
        - total_load,
        3
    )

    if total_balance > 0:
        overall_state = (
            "Expected Surplus"
        )

    elif total_balance < 0:
        overall_state = (
            "Expected Deficit"
        )

    else:
        overall_state = (
            "Balanced"
        )

    # =====================================================
    # Final Response
    # =====================================================

    return {
        "status":
            "ok",

        "forecast_model":
            (
                "Random Forest Load Forecast "
                "+ Weather-Based Solar Forecast"
            ),

        "requested_training_source":
            source,

        "selected_training_source":
            load_result.get(
                "selected_training_source"
            ),

        "real_sensor_training":
            load_result.get(
                "real_sensor_training",
                False
            ),

        "ml_evaluation":
            load_result.get(
                "evaluation",
                {}
            ),

        "generated_at":
            datetime.now().isoformat(),

        "forecast_hours":
            len(
                forecasts
            ),

        "summary": {
            "total_predicted_load_kwh":
                round(
                    total_load,
                    3
                ),

            "total_virtual_solar_kwh":
                round(
                    total_solar,
                    3
                ),

            "net_energy_balance_kwh":
                total_balance,

            "overall_state":
                overall_state
        },

        "hours":
            forecasts
    }