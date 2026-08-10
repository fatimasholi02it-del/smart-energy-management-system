from datetime import datetime

from ml_energy_forecast_service import (
    get_ml_energy_forecast
)

from electricity_price_service import (
    get_electricity_price_forecast
)

from advanced_economic_mpc import (
    optimize_advanced_economic_mpc
)

from battery_aware_ml_mpc import (
    optimize_battery_aware_ml_mpc
)


def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def clean(value, digits=3):
    value = round(
        safe_float(value),
        digits
    )

    if abs(value) < 0.001:
        return 0.0

    return value


def get_min_soc(plan):
    values = [
        safe_float(
            row.get(
                "battery_soc_after_percent"
            )
        )
        for row in plan
        if row.get(
            "battery_soc_after_percent"
        ) is not None
    ]

    if not values:
        return None

    return min(values)


def get_hours_below_soc(
    plan,
    threshold=35.0
):
    return sum(
        1
        for row in plan
        if safe_float(
            row.get(
                "battery_soc_after_percent"
            )
        ) < threshold
    )


def run_fair_mpc_benchmark(
    hours: int = 6,
    source: str = "auto"
):

    # =====================================================
    # ONE shared ML forecast snapshot
    # =====================================================

    forecast_snapshot = (
        get_ml_energy_forecast(
            hours=hours,
            source=source
        )
    )

    if (
        forecast_snapshot.get(
            "status"
        )
        != "ok"
    ):
        return {
            "status": "error",
            "message": (
                "Unable to generate shared "
                "ML forecast snapshot."
            ),
            "details": forecast_snapshot
        }

    shared_forecast = (
        forecast_snapshot.get(
            "hours",
            []
        )
    )

    # =====================================================
    # ONE shared electricity price snapshot
    # =====================================================

    price_snapshot = (
        get_electricity_price_forecast(
            hours=hours
        )
    )

    if (
        price_snapshot.get(
            "status"
        )
        != "ok"
    ):
        return {
            "status": "error",
            "message": (
                "Unable to generate shared "
                "electricity-price snapshot."
            )
        }

    shared_prices = (
        price_snapshot.get(
            "hours",
            []
        )
    )

    # =====================================================
    # Model A
    # =====================================================

    standard_result = (
        optimize_advanced_economic_mpc(
            hours=len(
                shared_forecast
            ),
            forecast_override=(
                shared_forecast
            ),
            price_override=(
                shared_prices
            )
        )
    )

    # =====================================================
    # Model B
    # =====================================================

    battery_result = (
        optimize_battery_aware_ml_mpc(
            hours=len(
                shared_forecast
            ),
            source=source,
            forecast_override=(
                shared_forecast
            ),
            price_override=(
                shared_prices
            )
        )
    )

    if standard_result.get("status") != "ok":
        return standard_result

    if battery_result.get("status") != "ok":
        return battery_result

    standard_summary = standard_result.get(
        "summary",
        {}
    )

    battery_summary = battery_result.get(
        "summary",
        {}
    )

    standard_plan = standard_result.get(
        "plan",
        []
    )

    battery_plan = battery_result.get(
        "plan",
        []
    )

    standard_min_soc = get_min_soc(
        standard_plan
    )

    battery_min_soc = get_min_soc(
        battery_plan
    )

    standard_low_hours = (
        get_hours_below_soc(
            standard_plan,
            35.0
        )
    )

    battery_low_hours = (
        get_hours_below_soc(
            battery_plan,
            35.0
        )
    )

    # =====================================================
    # Comparison
    # =====================================================

    standard_cost = safe_float(
        standard_summary.get(
            "optimized_energy_cost"
        )
    )

    battery_cost = safe_float(
        battery_summary.get(
            "optimized_energy_cost"
        )
    )

    cost_difference = (
        battery_cost
        - standard_cost
    )

    standard_grid = safe_float(
        standard_summary.get(
            "grid_after_optimization_kwh"
        )
    )

    battery_grid = safe_float(
        battery_summary.get(
            "grid_after_optimization_kwh"
        )
    )

    grid_difference = (
        battery_grid
        - standard_grid
    )

    battery_reserve_improvement = (
        (
            battery_min_soc is not None
            and standard_min_soc is not None
            and battery_min_soc
            > standard_min_soc
        )
        or
        (
            battery_low_hours
            < standard_low_hours
        )
    )

    if battery_reserve_improvement:
        recommended = (
            "Battery-Aware ML MPC"
        )

        reason = (
            "It maintains a stronger battery "
            "reserve under exactly the same "
            "forecast and electricity-price inputs."
        )

    elif battery_cost <= standard_cost:
        recommended = (
            "Battery-Aware ML MPC"
        )

        reason = (
            "Battery protection is achieved "
            "without increasing energy cost."
        )

    else:
        recommended = (
            "ML Advanced Economic MPC"
        )

        reason = (
            "For this specific snapshot, both "
            "strategies provide similar battery "
            "behavior while the standard model "
            "has a lower optimized cost."
        )

    return {
        "status": "ok",

        "benchmark_type":
            "Fair MPC Benchmark",

        "generated_at":
            datetime.now().isoformat(),

        "fair_comparison":
            True,

        "shared_snapshot": {
            "forecast_generated_once":
                True,

            "prices_generated_once":
                True,

            "forecast_hours":
                len(
                    shared_forecast
                ),

            "selected_training_source":
                forecast_snapshot.get(
                    "selected_training_source"
                ),

            "real_sensor_training":
                forecast_snapshot.get(
                    "real_sensor_training",
                    False
                ),

            "ml_evaluation":
                forecast_snapshot.get(
                    "ml_evaluation",
                    {}
                )
        },

        "models": {
            "ml_advanced_economic_mpc": {
                "optimized_energy_cost":
                    clean(
                        standard_cost
                    ),

                "cost_saving_percent":
                    clean(
                        standard_summary.get(
                            "cost_saving_percent"
                        )
                    ),

                "grid_after_optimization_kwh":
                    clean(
                        standard_grid
                    ),

                "grid_reduction_percent":
                    clean(
                        standard_summary.get(
                            "grid_reduction_percent"
                        )
                    ),

                "minimum_battery_soc_percent":
                    clean(
                        standard_min_soc
                    )
                    if standard_min_soc
                    is not None
                    else None,

                "hours_below_35_percent":
                    standard_low_hours,

                "final_battery_soc_percent":
                    clean(
                        standard_summary.get(
                            "final_battery_soc_percent"
                        )
                    )
            },

            "battery_aware_ml_mpc": {
                "optimized_energy_cost":
                    clean(
                        battery_cost
                    ),

                "cost_saving_percent":
                    clean(
                        battery_summary.get(
                            "cost_saving_percent"
                        )
                    ),

                "grid_after_optimization_kwh":
                    clean(
                        battery_grid
                    ),

                "grid_reduction_percent":
                    clean(
                        battery_summary.get(
                            "grid_reduction_percent"
                        )
                    ),

                "minimum_battery_soc_percent":
                    clean(
                        battery_min_soc
                    )
                    if battery_min_soc
                    is not None
                    else None,

                "hours_below_35_percent":
                    battery_low_hours,

                "final_battery_soc_percent":
                    clean(
                        battery_summary.get(
                            "final_battery_soc_percent"
                        )
                    )
            }
        },

        "difference": {
            "additional_cost_for_battery_aware":
                clean(
                    cost_difference
                ),

            "additional_grid_energy_kwh":
                clean(
                    grid_difference
                ),

            "battery_reserve_improved":
                battery_reserve_improvement
        },

        "recommended_model": {
            "model":
                recommended,

            "reason":
                reason
        }
    }