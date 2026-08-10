from datetime import datetime

from ml_advanced_mpc_service import (
    optimize_ml_advanced_mpc
)

from battery_aware_ml_mpc import (
    optimize_battery_aware_ml_mpc
)


def safe_float(
    value,
    default=0.0
):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def clean_number(
    value,
    digits=3
):
    value = safe_float(
        value,
        0.0
    )

    value = round(
        value,
        digits
    )

    if abs(value) < (
        10 ** (-digits)
    ):
        return 0.0

    return value


def extract_standard_ml_metrics(
    result: dict
):
    summary = result.get(
        "summary",
        {}
    )

    plan = result.get(
        "plan",
        []
    )

    battery_charge = sum(
        safe_float(
            item.get(
                "battery_charge_kw"
            )
        )
        for item in plan
    )

    battery_discharge = sum(
        safe_float(
            item.get(
                "battery_discharge_kw"
            )
        )
        for item in plan
    )

    hours_below_35 = sum(
        1
        for item in plan
        if safe_float(
            item.get(
                "battery_soc_after_percent"
            )
        ) < 35.0
    )

    minimum_soc = None

    soc_values = [
        safe_float(
            item.get(
                "battery_soc_after_percent"
            )
        )
        for item in plan
        if item.get(
            "battery_soc_after_percent"
        ) is not None
    ]

    if soc_values:
        minimum_soc = min(
            soc_values
        )

    return {
        "optimized_energy_cost":
            safe_float(
                summary.get(
                    "optimized_energy_cost"
                )
            ),

        "baseline_energy_cost":
            safe_float(
                summary.get(
                    "baseline_energy_cost"
                )
            ),

        "cost_saving_percent":
            safe_float(
                summary.get(
                    "cost_saving_percent"
                )
            ),

        "grid_after_optimization_kwh":
            safe_float(
                summary.get(
                    "grid_after_optimization_kwh"
                )
            ),

        "grid_reduction_percent":
            safe_float(
                summary.get(
                    "grid_reduction_percent"
                )
            ),

        "shifted_load_kwh":
            safe_float(
                summary.get(
                    "total_shifted_load_kwh",
                    summary.get(
                        "shifted_load_kwh"
                    )
                )
            ),

        "battery_charge_throughput_kwh":
            battery_charge,

        "battery_discharge_throughput_kwh":
            battery_discharge,

        "hours_below_preferred_soc":
            hours_below_35,

        "minimum_battery_soc_percent":
            minimum_soc,

        "final_battery_soc_percent":
            safe_float(
                summary.get(
                    "final_battery_soc_percent"
                )
            )
    }


def extract_battery_aware_metrics(
    result: dict
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
        safe_float(
            item.get(
                "battery_soc_after_percent"
            )
        )
        for item in plan
        if item.get(
            "battery_soc_after_percent"
        ) is not None
    ]

    minimum_soc = (
        min(soc_values)
        if soc_values
        else None
    )

    return {
        "optimized_energy_cost":
            safe_float(
                summary.get(
                    "optimized_energy_cost"
                )
            ),

        "baseline_energy_cost":
            safe_float(
                summary.get(
                    "baseline_energy_cost"
                )
            ),

        "cost_saving_percent":
            safe_float(
                summary.get(
                    "cost_saving_percent"
                )
            ),

        "grid_after_optimization_kwh":
            safe_float(
                summary.get(
                    "grid_after_optimization_kwh"
                )
            ),

        "grid_reduction_percent":
            safe_float(
                summary.get(
                    "grid_reduction_percent"
                )
            ),

        "shifted_load_kwh":
            safe_float(
                summary.get(
                    "total_shifted_load_kwh"
                )
            ),

        "battery_charge_throughput_kwh":
            safe_float(
                summary.get(
                    "battery_charge_throughput_kwh"
                )
            ),

        "battery_discharge_throughput_kwh":
            safe_float(
                summary.get(
                    "battery_discharge_throughput_kwh"
                )
            ),

        "hours_below_preferred_soc":
            int(
                summary.get(
                    "hours_below_preferred_soc",
                    0
                )
            ),

        "minimum_battery_soc_percent":
            minimum_soc,

        "final_battery_soc_percent":
            safe_float(
                summary.get(
                    "final_battery_soc_percent"
                )
            )
    }


def compare_ml_battery_strategies(
    hours: int = 6,
    source: str = "auto"
):

    standard_ml_result = (
        optimize_ml_advanced_mpc(
            hours=hours,
            source=source
        )
    )

    battery_aware_result = (
        optimize_battery_aware_ml_mpc(
            hours=hours,
            source=source
        )
    )

    if (
        standard_ml_result.get(
            "status"
        )
        != "ok"
    ):
        return {
            "status": "error",
            "source":
                "ml_advanced_mpc",
            "details":
                standard_ml_result
        }

    if (
        battery_aware_result.get(
            "status"
        )
        != "ok"
    ):
        return {
            "status": "error",
            "source":
                "battery_aware_ml_mpc",
            "details":
                battery_aware_result
        }

    standard = (
        extract_standard_ml_metrics(
            standard_ml_result
        )
    )

    battery_aware = (
        extract_battery_aware_metrics(
            battery_aware_result
        )
    )

    # =====================================================
    # Differences
    # =====================================================

    additional_cost_for_battery_protection = (
        battery_aware[
            "optimized_energy_cost"
        ]
        -
        standard[
            "optimized_energy_cost"
        ]
    )

    cost_saving_difference = (
        standard[
            "cost_saving_percent"
        ]
        -
        battery_aware[
            "cost_saving_percent"
        ]
    )

    grid_difference = (
        battery_aware[
            "grid_after_optimization_kwh"
        ]
        -
        standard[
            "grid_after_optimization_kwh"
        ]
    )

    discharge_reduction = (
        standard[
            "battery_discharge_throughput_kwh"
        ]
        -
        battery_aware[
            "battery_discharge_throughput_kwh"
        ]
    )

    # =====================================================
    # Decision
    # =====================================================

    battery_aware_has_better_reserve = (
        battery_aware[
            "hours_below_preferred_soc"
        ]
        <
        standard[
            "hours_below_preferred_soc"
        ]
    )

    standard_is_cheaper = (
        standard[
            "optimized_energy_cost"
        ]
        <
        battery_aware[
            "optimized_energy_cost"
        ]
    )

    if battery_aware_has_better_reserve:

        recommended_model = (
            "Battery-Aware ML-Driven "
            "Advanced Economic MPC"
        )

        recommendation_reason = (
            "It provides a better balance "
            "between energy cost optimization "
            "and battery reserve protection."
        )

    elif standard_is_cheaper:

        recommended_model = (
            "ML-Driven Advanced Economic MPC"
        )

        recommendation_reason = (
            "Both strategies show similar "
            "battery reserve behavior, while "
            "the standard ML-driven strategy "
            "achieves a lower energy cost."
        )

    else:

        recommended_model = (
            "Battery-Aware ML-Driven "
            "Advanced Economic MPC"
        )

        recommendation_reason = (
            "The battery-aware strategy is "
            "preferred for realistic prototype "
            "operation and battery protection."
        )

    return {
        "status":
            "ok",

        "comparison_type":
            (
                "ML Economic MPC "
                "vs Battery-Aware ML MPC"
            ),

        "generated_at":
            datetime.now().isoformat(),

        "planning_horizon_hours":
            hours,

        "requested_training_source":
            source,

        "selected_training_source":
            battery_aware_result.get(
                "selected_training_source"
            ),

        "real_sensor_training":
            battery_aware_result.get(
                "real_sensor_training",
                False
            ),

        "ml_evaluation":
            battery_aware_result.get(
                "ml_evaluation",
                {}
            ),

        "models": {

            "ml_advanced_economic_mpc": {
                "model":
                    (
                        "ML-Driven Advanced "
                        "Economic MPC"
                    ),

                **{
                    key:
                        clean_number(
                            value
                        )
                        if isinstance(
                            value,
                            (int, float)
                        )
                        and key
                        != "hours_below_preferred_soc"
                        else value

                    for key, value
                    in standard.items()
                }
            },

            "battery_aware_ml_mpc": {
                "model":
                    (
                        "Battery-Aware ML-Driven "
                        "Advanced Economic MPC"
                    ),

                **{
                    key:
                        clean_number(
                            value
                        )
                        if isinstance(
                            value,
                            (int, float)
                        )
                        and key
                        != "hours_below_preferred_soc"
                        else value

                    for key, value
                    in battery_aware.items()
                }
            }
        },

        "trade_off": {
            "additional_cost_for_battery_protection":
                clean_number(
                    additional_cost_for_battery_protection
                ),

            "cost_saving_difference_percent":
                clean_number(
                    cost_saving_difference
                ),

            "additional_grid_energy_kwh":
                clean_number(
                    grid_difference
                ),

            "battery_discharge_reduction_kwh":
                clean_number(
                    discharge_reduction
                ),

            "battery_reserve_improved":
                battery_aware_has_better_reserve
        },

        "recommended_model": {
            "model":
                recommended_model,

            "reason":
                recommendation_reason
        },

        "interpretation": (
            "A higher cost saving is not "
            "automatically the best strategy. "
            "Battery reserve, cycling and "
            "operational realism must also "
            "be considered."
        )
    }