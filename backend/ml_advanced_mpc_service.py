from datetime import datetime

from ml_energy_forecast_service import (
    get_ml_energy_forecast
)

from advanced_economic_mpc import (
    optimize_advanced_economic_mpc
)


def optimize_ml_advanced_mpc(
    hours: int = 6,
    source: str = "auto"
):
    # =====================================================
    # Get ML-based energy forecast
    # =====================================================

    forecast_result = (
        get_ml_energy_forecast(
            hours=hours,
            source=source
        )
    )

    if forecast_result.get(
        "status"
    ) != "ok":
        return {
            "status":
                forecast_result.get(
                    "status",
                    "error"
                ),

            "message":
                forecast_result.get(
                    "message",
                    "ML energy forecast unavailable"
                ),

            "forecast":
                forecast_result
        }

    forecast_hours = (
        forecast_result.get(
            "hours",
            []
        )
    )

    if not forecast_hours:
        return {
            "status": "error",
            "message": (
                "No ML forecast hours "
                "are available."
            )
        }

    # =====================================================
    # Run Advanced Economic MPC
    # =====================================================

    optimization_result = (
        optimize_advanced_economic_mpc(
            hours=len(
                forecast_hours
            ),
            forecast_override=(
                forecast_hours
            )
        )
    )

    if optimization_result.get(
        "status"
    ) != "ok":
        return optimization_result

    # =====================================================
    # Add ML metadata
    # =====================================================

    optimization_result[
        "optimization_model"
    ] = (
        "ML-Driven Advanced Economic MPC "
        "- Forward-Only Load Shifting"
    )

    optimization_result[
        "load_forecast_model"
    ] = (
        "Random Forest Regressor"
    )

    optimization_result[
        "requested_training_source"
    ] = source

    optimization_result[
        "selected_training_source"
    ] = forecast_result.get(
        "selected_training_source"
    )

    optimization_result[
        "real_sensor_training"
    ] = forecast_result.get(
        "real_sensor_training",
        False
    )

    optimization_result[
        "ml_evaluation"
    ] = forecast_result.get(
        "ml_evaluation",
        {}
    )

    optimization_result[
        "ml_forecast_summary"
    ] = forecast_result.get(
        "summary",
        {}
    )

    optimization_result[
        "ml_generated_at"
    ] = datetime.now().isoformat()

    return optimization_result