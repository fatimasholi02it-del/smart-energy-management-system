from datetime import datetime

from mpc_optimizer import optimize_energy_plan
from economic_mpc_optimizer import optimize_economic_energy_plan
from advanced_economic_mpc import optimize_advanced_economic_mpc


def safe_number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_model_result(
    model_name: str,
    result: dict
):
    if result.get("status") != "ok":
        return {
            "model": model_name,
            "status": "error",
            "message": result.get(
                "message",
                "Optimization failed"
            )
        }

    summary = result.get(
        "summary",
        {}
    )

    return {
        "model": model_name,
        "status": "ok",

        "grid_after_optimization_kwh":
            safe_number(
                summary.get(
                    "grid_after_optimization_kwh"
                )
            ),

        "grid_without_optimization_kwh":
            safe_number(
                summary.get(
                    "grid_without_optimization_kwh"
                )
            ),

        "grid_reduction_kwh":
            safe_number(
                summary.get(
                    "grid_reduction_kwh"
                )
            ),

        "grid_reduction_percent":
            safe_number(
                summary.get(
                    "grid_reduction_percent"
                )
            ),

        "baseline_energy_cost":
            safe_number(
                summary.get(
                    "baseline_energy_cost"
                )
            ),

        "optimized_energy_cost":
            safe_number(
                summary.get(
                    "optimized_energy_cost"
                )
            ),

        "estimated_cost_saving":
            safe_number(
                summary.get(
                    "estimated_cost_saving"
                )
            ),

        "cost_saving_percent":
            safe_number(
                summary.get(
                    "cost_saving_percent"
                )
            ),

        "shifted_load_kwh":
            safe_number(
                summary.get(
                    "shifted_load_kwh",
                    summary.get(
                        "total_shifted_load_kwh"
                    )
                )
            ),

        "final_battery_soc_percent":
            safe_number(
                summary.get(
                    "final_battery_soc_percent"
                )
            ),

        "solar_utilization_percent":
            safe_number(
                summary.get(
                    "solar_utilization_percent"
                )
            )
    }


def compare_optimization_models(
    hours: int = 6
):
    standard_result = optimize_energy_plan(
        hours=hours
    )

    economic_result = (
        optimize_economic_energy_plan(
            hours=hours
        )
    )

    advanced_result = (
        optimize_advanced_economic_mpc(
            hours=hours
        )
    )

    models = [
        build_model_result(
            "Standard MPC",
            standard_result
        ),

        build_model_result(
            "Economic MPC",
            economic_result
        ),

        build_model_result(
            "Advanced Economic MPC",
            advanced_result
        )
    ]

    valid_models = [
        model
        for model in models
        if model["status"] == "ok"
    ]

    # -----------------------------------------
    # Best cost model
    # -----------------------------------------

    models_with_cost = [
        model
        for model in valid_models
        if model[
            "optimized_energy_cost"
        ] > 0
    ]

    best_cost_model = None

    if models_with_cost:
        best_cost_model = min(
            models_with_cost,
            key=lambda x:
                x["optimized_energy_cost"]
        )

    # -----------------------------------------
    # Best grid model
    # -----------------------------------------

    best_grid_model = None

    if valid_models:
        best_grid_model = min(
            valid_models,
            key=lambda x:
                x[
                    "grid_after_optimization_kwh"
                ]
        )

    # -----------------------------------------
    # Best realistic recommendation
    # -----------------------------------------

    recommended_model = (
        "Advanced Economic MPC"
    )

    recommendation_reason = (
        "It combines time-of-use pricing, "
        "battery scheduling and physically "
        "valid forward-only load shifting."
    )

    return {
        "status": "ok",

        "comparison_type":
            "Optimization Model Benchmark",

        "generated_at":
            datetime.now().isoformat(),

        "planning_horizon_hours":
            hours,

        "models":
            models,

        "best_cost_model": (
            {
                "model":
                    best_cost_model[
                        "model"
                    ],

                "optimized_energy_cost":
                    best_cost_model[
                        "optimized_energy_cost"
                    ],

                "cost_saving_percent":
                    best_cost_model[
                        "cost_saving_percent"
                    ]
            }
            if best_cost_model
            else None
        ),

        "best_grid_reduction_model": (
            {
                "model":
                    best_grid_model[
                        "model"
                    ],

                "grid_after_optimization_kwh":
                    best_grid_model[
                        "grid_after_optimization_kwh"
                    ],

                "grid_reduction_percent":
                    best_grid_model[
                        "grid_reduction_percent"
                    ]
            }
            if best_grid_model
            else None
        ),

        "recommended_prototype_model": {
            "model":
                recommended_model,

            "reason":
                recommendation_reason
        },

        "important_note": (
            "A model showing a larger saving "
            "is not automatically better if "
            "its scheduling assumptions are "
            "less realistic."
        )
    }