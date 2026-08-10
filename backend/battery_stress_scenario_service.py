from datetime import datetime, timedelta

from advanced_economic_mpc import (
    optimize_advanced_economic_mpc
)

from battery_aware_ml_mpc import (
    optimize_battery_aware_ml_mpc
)


def build_stress_forecast():
    now = datetime.now().replace(
        minute=0,
        second=0,
        microsecond=0
    )

    loads = [
        4.8,
        4.6,
        4.4,
        4.1,
        3.8,
        3.5
    ]

    solar = [
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0
    ]

    forecast = []

    for i in range(6):
        forecast_time = (
            now
            + timedelta(hours=i + 1)
        )

        forecast.append({
            "forecast_time":
                forecast_time.isoformat(),

            "predicted_load_kw":
                loads[i],

            "solar_power_kw":
                solar[i],

            "energy_balance_kw":
                round(
                    solar[i] - loads[i],
                    3
                ),

            "energy_state":
                "Deficit"
        })

    return forecast


def build_stress_prices():
    now = datetime.now().replace(
        minute=0,
        second=0,
        microsecond=0
    )

    prices = [
        {
            "price_per_kwh": 0.40,
            "price_level": "Peak"
        },
        {
            "price_per_kwh": 0.40,
            "price_level": "Peak"
        },
        {
            "price_per_kwh": 0.40,
            "price_level": "Peak"
        },
        {
            "price_per_kwh": 0.20,
            "price_level": "Normal"
        },
        {
            "price_per_kwh": 0.12,
            "price_level": "Off-Peak"
        },
        {
            "price_per_kwh": 0.12,
            "price_level": "Off-Peak"
        }
    ]

    result = []

    for i, price in enumerate(prices):
        forecast_time = (
            now
            + timedelta(hours=i + 1)
        )

        result.append({
            "forecast_time":
                forecast_time.isoformat(),

            "price_per_kwh":
                price["price_per_kwh"],

            "price_level":
                price["price_level"]
        })

    return result


def extract_metrics(
    result,
    preferred_soc=35.0
):
    summary = result.get(
        "summary",
        {}
    )

    plan = result.get(
        "plan",
        []
    )

    soc_values = [
        float(
            row.get(
                "battery_soc_after_percent",
                0.0
            )
        )
        for row in plan
    ]

    minimum_soc = (
        min(soc_values)
        if soc_values
        else None
    )

    hours_below_preferred = sum(
        1
        for soc in soc_values
        if soc < preferred_soc
    )

    discharge = sum(
        float(
            row.get(
                "battery_discharge_kw",
                0.0
            )
        )
        for row in plan
    )

    charge = sum(
        float(
            row.get(
                "battery_charge_kw",
                0.0
            )
        )
        for row in plan
    )

    return {
        "optimized_energy_cost":
            round(
                float(
                    summary.get(
                        "optimized_energy_cost",
                        0.0
                    )
                ),
                3
            ),

        "cost_saving_percent":
            round(
                float(
                    summary.get(
                        "cost_saving_percent",
                        0.0
                    )
                ),
                2
            ),

        "grid_after_optimization_kwh":
            round(
                float(
                    summary.get(
                        "grid_after_optimization_kwh",
                        0.0
                    )
                ),
                3
            ),

        "minimum_battery_soc_percent":
            (
                round(
                    minimum_soc,
                    2
                )
                if minimum_soc is not None
                else None
            ),

        "hours_below_35_percent":
            hours_below_preferred,

        "final_battery_soc_percent":
            round(
                float(
                    summary.get(
                        "final_battery_soc_percent",
                        0.0
                    )
                ),
                2
            ),

        "battery_discharge_kwh":
            round(
                discharge,
                3
            ),

        "battery_charge_kwh":
            round(
                charge,
                3
            )
    }


def run_battery_stress_scenario():

    shared_forecast = (
        build_stress_forecast()
    )

    shared_prices = (
        build_stress_prices()
    )

    standard_result = (
        optimize_advanced_economic_mpc(
            hours=6,
            forecast_override=shared_forecast,
            price_override=shared_prices
        )
    )

    battery_result = (
        optimize_battery_aware_ml_mpc(
            hours=6,
            source="synthetic",
            forecast_override=shared_forecast,
            price_override=shared_prices
        )
    )

    if (
        standard_result.get(
            "status"
        )
        != "ok"
    ):
        return {
            "status": "error",
            "model": "standard",
            "details": standard_result
        }

    if (
        battery_result.get(
            "status"
        )
        != "ok"
    ):
        return {
            "status": "error",
            "model": "battery_aware",
            "details": battery_result
        }

    standard_metrics = (
        extract_metrics(
            standard_result
        )
    )

    battery_metrics = (
        extract_metrics(
            battery_result
        )
    )

    return {
        "status":
            "ok",

        "scenario":
            "Battery Stress Scenario",

        "description":
            (
                "High load, zero solar and "
                "multiple peak-price hours are "
                "used to stress battery behavior."
            ),

        "shared_inputs": {
            "forecast":
                shared_forecast,

            "prices":
                shared_prices
        },

        "models": {
            "ml_advanced_economic_mpc":
                standard_metrics,

            "battery_aware_ml_mpc":
                battery_metrics
        },

        "comparison": {
            "minimum_soc_improvement_percent":
                round(
                    (
                        battery_metrics[
                            "minimum_battery_soc_percent"
                        ]
                        -
                        standard_metrics[
                            "minimum_battery_soc_percent"
                        ]
                    ),
                    2
                ),

            "hours_below_35_reduction":
                (
                    standard_metrics[
                        "hours_below_35_percent"
                    ]
                    -
                    battery_metrics[
                        "hours_below_35_percent"
                    ]
                ),

            "battery_discharge_reduction_kwh":
                round(
                    (
                        standard_metrics[
                            "battery_discharge_kwh"
                        ]
                        -
                        battery_metrics[
                            "battery_discharge_kwh"
                        ]
                    ),
                    3
                ),

            "additional_energy_cost":
                round(
                    (
                        battery_metrics[
                            "optimized_energy_cost"
                        ]
                        -
                        standard_metrics[
                            "optimized_energy_cost"
                        ]
                    ),
                    3
                )
        }
    }