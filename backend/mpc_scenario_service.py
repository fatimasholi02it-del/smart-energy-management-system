from copy import deepcopy

from energy_forecast_service import get_energy_forecast
from mpc_optimizer import optimize_energy_plan


def build_scenario_forecast(
    base_hours,
    solar_values=None,
    load_multipliers=None,
    weather_condition=None
):
    result = deepcopy(base_hours)

    for index, hour in enumerate(result):

        if solar_values is not None:
            hour["solar_power_kw"] = round(
                float(solar_values[index]),
                2
            )

        if load_multipliers is not None:
            original_load = float(
                hour.get(
                    "predicted_load_kw",
                    0
                )
            )

            hour["predicted_load_kw"] = round(
                original_load
                * load_multipliers[index],
                2
            )

        if weather_condition is not None:
            hour["weather_condition"] = (
                weather_condition
            )

    return result


def extract_scenario_summary(
    scenario_name,
    description,
    result
):
    if result.get("status") != "ok":
        return {
            "scenario_name": scenario_name,
            "description": description,
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

    plan = result.get(
        "plan",
        []
    )

    shift_hours = []

    battery_hours = []

    grid_hours = []

    charge_hours = []

    for item in plan:

        if item.get(
            "load_shifted_out_kw",
            0
        ) > 0.05:
            shift_hours.append({
                "forecast_time":
                    item["forecast_time"],

                "shifted_kw":
                    item[
                        "load_shifted_out_kw"
                    ]
            })

        if item.get(
            "battery_discharge_kw",
            0
        ) > 0.05:
            battery_hours.append({
                "forecast_time":
                    item["forecast_time"],

                "battery_discharge_kw":
                    item[
                        "battery_discharge_kw"
                    ]
            })

        if item.get(
            "battery_charge_kw",
            0
        ) > 0.05:
            charge_hours.append({
                "forecast_time":
                    item["forecast_time"],

                "battery_charge_kw":
                    item[
                        "battery_charge_kw"
                    ]
            })

        if item.get(
            "grid_power_kw",
            0
        ) > 0.05:
            grid_hours.append({
                "forecast_time":
                    item["forecast_time"],

                "grid_power_kw":
                    item[
                        "grid_power_kw"
                    ]
            })

    return {
        "scenario_name":
            scenario_name,

        "description":
            description,

        "status":
            "ok",

        "summary": {
            "forecast_load_kwh":
                summary.get(
                    "forecast_load_kwh"
                ),

            "solar_available_kwh":
                summary.get(
                    "solar_available_kwh"
                ),

            "solar_used_kwh":
                summary.get(
                    "solar_used_kwh"
                ),

            "solar_utilization_percent":
                summary.get(
                    "solar_utilization_percent"
                ),

            "grid_without_optimization_kwh":
                summary.get(
                    "grid_without_optimization_kwh"
                ),

            "grid_after_optimization_kwh":
                summary.get(
                    "grid_after_optimization_kwh"
                ),

            "grid_reduction_percent":
                summary.get(
                    "grid_reduction_percent"
                ),

            "total_shifted_load_kwh":
                summary.get(
                    "total_shifted_load_kwh"
                ),

            "final_battery_soc_percent":
                summary.get(
                    "final_battery_soc_percent"
                )
        },

        "behavior": {
            "load_shifting_detected":
                len(shift_hours) > 0,

            "battery_discharge_detected":
                len(battery_hours) > 0,

            "battery_charging_detected":
                len(charge_hours) > 0,

            "grid_usage_detected":
                len(grid_hours) > 0
        },

        "shift_hours":
            shift_hours,

        "battery_discharge_hours":
            battery_hours,

        "battery_charge_hours":
            charge_hours,

        "grid_usage_hours":
            grid_hours,

        "plan":
            plan
    }


def run_mpc_scenarios():

    real_forecast = get_energy_forecast(
        hours=6
    )

    if real_forecast.get(
        "status"
    ) != "ok":
        return {
            "status": "error",
            "message": (
                "Base energy forecast "
                "is unavailable"
            )
        }

    base_hours = real_forecast.get(
        "hours",
        []
    )

    if len(base_hours) < 6:
        return {
            "status": "error",
            "message": (
                "At least 6 forecast "
                "hours are required"
            )
        }

    # =====================================================
    # Scenario 1
    # Current real forecast
    # =====================================================

    current_result = (
        optimize_energy_plan(
            hours=6,
            forecast_override=base_hours
        )
    )

    # =====================================================
    # Scenario 2
    # Solar becomes stronger later
    #
    # هدف السيناريو:
    # اختبار هل MPC يؤجل أحمال مرنة
    # من الساعات الضعيفة إلى ساعات solar أقوى.
    # =====================================================

    future_high_solar = [
        0.80,
        1.20,
        2.00,
        4.00,
        4.50,
        3.50
    ]

    high_solar_hours = (
        build_scenario_forecast(
            base_hours,
            solar_values=(
                future_high_solar
            ),
            weather_condition=(
                "Improving Solar"
            )
        )
    )

    high_solar_result = (
        optimize_energy_plan(
            hours=6,
            forecast_override=(
                high_solar_hours
            )
        )
    )

    # =====================================================
    # Scenario 3
    # Very cloudy / low solar
    #
    # هدف السيناريو:
    # اختبار battery protection + grid dependency.
    # =====================================================

    low_solar_values = [
        0.40,
        0.30,
        0.25,
        0.20,
        0.10,
        0.05
    ]

    cloudy_hours = (
        build_scenario_forecast(
            base_hours,
            solar_values=(
                low_solar_values
            ),
            weather_condition=(
                "Very Cloudy"
            )
        )
    )

    cloudy_result = (
        optimize_energy_plan(
            hours=6,
            forecast_override=(
                cloudy_hours
            )
        )
    )

    # =====================================================
    # Scenario 4
    # Peak-load event
    #
    # زيادة الحمل في منتصف الفترة.
    # =====================================================

    peak_load_multipliers = [
        1.00,
        1.00,
        1.60,
        1.70,
        1.20,
        1.00
    ]

    peak_hours = (
        build_scenario_forecast(
            base_hours,
            load_multipliers=(
                peak_load_multipliers
            )
        )
    )

    peak_result = (
        optimize_energy_plan(
            hours=6,
            forecast_override=(
                peak_hours
            )
        )
    )

    scenarios = [
        extract_scenario_summary(
            scenario_name=(
                "Current Forecast"
            ),
            description=(
                "Uses the current weather, "
                "solar and load forecasts."
            ),
            result=current_result
        ),

        extract_scenario_summary(
            scenario_name=(
                "High Solar Later"
            ),
            description=(
                "Solar availability is weak "
                "initially and becomes much "
                "stronger later. This scenario "
                "tests flexible load shifting."
            ),
            result=high_solar_result
        ),

        extract_scenario_summary(
            scenario_name=(
                "Very Low Solar"
            ),
            description=(
                "Simulates a heavily cloudy "
                "period with very low solar "
                "generation."
            ),
            result=cloudy_result
        ),

        extract_scenario_summary(
            scenario_name=(
                "Peak Load Event"
            ),
            description=(
                "Simulates a temporary increase "
                "in predicted energy demand."
            ),
            result=peak_result
        )
    ]

    return {
        "status": "ok",

        "test_type":
            "MPC Scenario Validation",

        "note": (
            "Scenario values are synthetic "
            "and are used only to validate "
            "optimizer behavior."
        ),

        "scenario_count":
            len(scenarios),

        "scenarios":
            scenarios
    }