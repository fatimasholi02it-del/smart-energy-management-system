from weather_service import get_weather_forecast


DEFAULT_PANEL_CAPACITY_KW = 5.0
SYSTEM_EFFICIENCY = 0.85


def estimate_solar_power(
    radiation_wm2: float,
    panel_capacity_kw: float = DEFAULT_PANEL_CAPACITY_KW,
    system_efficiency: float = SYSTEM_EFFICIENCY
):
    if radiation_wm2 <= 0:
        return 0.0

    irradiance_ratio = min(radiation_wm2 / 1000.0, 1.0)

    estimated_power = (
        panel_capacity_kw
        * irradiance_ratio
        * system_efficiency
    )

    return round(max(estimated_power, 0.0), 2)


def get_solar_forecast(hours: int = 6):
    weather = get_weather_forecast(forecast_hours=hours)

    if weather.get("status") != "ok":
        return {
            "status": "error",
            "message": weather.get(
                "message",
                "Weather forecast unavailable"
            )
        }

    forecasts = []

    for hour in weather["hours"]:
        radiation = hour["shortwave_radiation_wm2"]

        estimated_power = estimate_solar_power(
            radiation_wm2=radiation
        )

        forecasts.append({
            **hour,
            "estimated_solar_power_kw": estimated_power
        })

    total_estimated_energy = round(
        sum(
            forecast["estimated_solar_power_kw"]
            for forecast in forecasts
        ),
        2
    )

    return {
        "status": "ok",
        "panel_capacity_kw": DEFAULT_PANEL_CAPACITY_KW,
        "system_efficiency": SYSTEM_EFFICIENCY,
        "forecast_hours": len(forecasts),
        "estimated_solar_energy_kwh": total_estimated_energy,
        "hours": forecasts
    }