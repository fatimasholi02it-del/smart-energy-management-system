from datetime import datetime, timedelta


# Prototype Time-of-Use tariff
#
# الأسعار افتراضية للمشروع وليست تعرفة حقيقية لدولة معينة.
#
OFF_PEAK_PRICE = 0.12
NORMAL_PRICE = 0.20
PEAK_PRICE = 0.40


def get_price_for_hour(hour: int) -> float:

    # Peak evening period
    if 18 <= hour <= 21:
        return PEAK_PRICE

    # Off-peak night / early morning
    if hour >= 23 or hour <= 6:
        return OFF_PEAK_PRICE

    return NORMAL_PRICE


def get_electricity_price_forecast(hours: int = 6):

    now = datetime.now()

    result = []

    for i in range(1, hours + 1):

        target_time = (
            now.replace(
                minute=0,
                second=0,
                microsecond=0
            )
            + timedelta(hours=i)
        )

        price = get_price_for_hour(
            target_time.hour
        )

        if price >= PEAK_PRICE:
            price_level = "Peak"

        elif price <= OFF_PEAK_PRICE:
            price_level = "Off-Peak"

        else:
            price_level = "Normal"

        result.append({
            "forecast_time":
                target_time.isoformat(),

            "price_per_kwh":
                price,

            "price_level":
                price_level
        })

    return {
        "status": "ok",

        "pricing_model":
            "Prototype Time-of-Use Tariff",

        "currency":
            "Generic Unit",

        "note": (
            "Electricity prices are simulated "
            "for prototype optimization and do "
            "not represent an official tariff."
        ),

        "hours":
            result
    }