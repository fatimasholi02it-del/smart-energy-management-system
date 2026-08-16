import requests

from datetime import (
    datetime,
    timedelta,
    timezone,
)


DEFAULT_LATITUDE = 33.5138
DEFAULT_LONGITUDE = 36.2765


def get_weather_forecast(
    latitude: float = DEFAULT_LATITUDE,
    longitude: float = DEFAULT_LONGITUDE,
    forecast_hours: int = 6,
):
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={latitude}"
        f"&longitude={longitude}"
        "&hourly="
        "temperature_2m,"
        "cloud_cover,"
        "shortwave_radiation"
        "&forecast_days=2"
        "&timezone=auto"
    )

    try:
        response = requests.get(
            url,
            timeout=20,
        )

        response.raise_for_status()

        data = response.json()

        hourly = data.get(
            "hourly",
            {},
        )

        times = hourly.get(
            "time",
            [],
        )

        temperatures = hourly.get(
            "temperature_2m",
            [],
        )

        cloud_cover = hourly.get(
            "cloud_cover",
            [],
        )

        radiation = hourly.get(
            "shortwave_radiation",
            [],
        )

        if not times:
            return {
                "status": "error",
                "message":
                    "Weather forecast is unavailable",
            }

        # ====================================================
        # Open-Meteo timezone context
        # ====================================================
        #
        # Because timezone=auto is used, Open-Meteo returns
        # hourly timestamps in the local timezone of the
        # requested location.
        #
        # Render normally runs in UTC, while a developer
        # computer may use local time.
        #
        # Therefore datetime.now() must NOT be compared
        # directly with Open-Meteo local timestamps.
        #
        # We use Open-Meteo's utc_offset_seconds to calculate
        # the current local time for the forecast location.
        # ====================================================

        utc_offset_seconds = int(
            data.get(
                "utc_offset_seconds",
                0,
            )
            or 0
        )

        timezone_name = data.get(
            "timezone",
            "UTC",
        )

        timezone_abbreviation = data.get(
            "timezone_abbreviation",
            "",
        )

        now_utc = datetime.now(
            timezone.utc
        )

        now_local = (
            now_utc
            + timedelta(
                seconds=utc_offset_seconds
            )
        ).replace(
            tzinfo=None
        )

        future_forecasts = []

        for index, time_value in enumerate(
            times
        ):
            try:
                forecast_time = (
                    datetime.fromisoformat(
                        time_value
                    )
                )

            except ValueError:
                continue

            # ------------------------------------------------
            # Ignore weather hours that already passed in the
            # forecast location's local timezone.
            # ------------------------------------------------

            if forecast_time < now_local:
                continue

            cloud = float(
                cloud_cover[index]
                or 0
            )

            temp = float(
                temperatures[index]
                or 0
            )

            solar_radiation = float(
                radiation[index]
                or 0
            )

            if cloud >= 70:
                condition = "Cloudy"

            elif cloud >= 40:
                condition = "Partly Cloudy"

            else:
                condition = "Sunny"

            future_forecasts.append(
                {
                    "forecast_time":
                        time_value,

                    "temperature":
                        round(
                            temp,
                            1,
                        ),

                    "cloud_percent":
                        round(
                            cloud,
                            1,
                        ),

                    "shortwave_radiation_wm2":
                        round(
                            solar_radiation,
                            2,
                        ),

                    "weather_condition":
                        condition,
                }
            )

            if (
                len(
                    future_forecasts
                )
                >= forecast_hours
            ):
                break

        if not future_forecasts:
            return {
                "status": "error",
                "message":
                    "No future forecast available",
            }

        # ====================================================
        # Generated timestamp
        #
        # UTC is explicit here to avoid ambiguous server-local
        # timestamps.
        # ====================================================

        generated_at_utc = (
            datetime.now(
                timezone.utc
            )
            .isoformat()
        )

        generated_at_local = (
            now_local.isoformat()
        )

        return {
            "status":
                "ok",

            "generated_at":
                generated_at_utc,

            "generated_at_utc":
                generated_at_utc,

            "generated_at_local":
                generated_at_local,

            "timezone":
                timezone_name,

            "timezone_abbreviation":
                timezone_abbreviation,

            "utc_offset_seconds":
                utc_offset_seconds,

            "forecast_hours":
                len(
                    future_forecasts
                ),

            "hours":
                future_forecasts,
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
        }