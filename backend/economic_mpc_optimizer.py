from datetime import datetime

import pulp

from energy_forecast_service import get_energy_forecast
from electricity_price_service import (
    get_electricity_price_forecast
)


BATTERY_CAPACITY_KWH = 5.0

INITIAL_BATTERY_SOC_PERCENT = 50.0
MIN_BATTERY_SOC_PERCENT = 20.0
MAX_BATTERY_SOC_PERCENT = 90.0

TERMINAL_SOC_PERCENT = 35.0

MAX_CHARGE_POWER_KW = 2.0
MAX_DISCHARGE_POWER_KW = 2.0

CHARGE_EFFICIENCY = 0.95
DISCHARGE_EFFICIENCY = 0.95

MAX_SHIFT_PERCENT = 0.25


def percent_to_kwh(percent: float) -> float:
    return (
        percent / 100.0
    ) * BATTERY_CAPACITY_KWH


def kwh_to_percent(value: float) -> float:

    if BATTERY_CAPACITY_KWH <= 0:
        return 0.0

    return round(
        value
        / BATTERY_CAPACITY_KWH
        * 100,
        2
    )


def optimize_economic_energy_plan(
    hours: int = 6
):

    energy_result = get_energy_forecast(
        hours=hours
    )

    price_result = (
        get_electricity_price_forecast(
            hours=hours
        )
    )

    if energy_result.get("status") != "ok":
        return {
            "status": "error",
            "message":
                "Energy forecast unavailable"
        }

    if price_result.get("status") != "ok":
        return {
            "status": "error",
            "message":
                "Electricity pricing unavailable"
        }

    forecast = energy_result.get(
        "hours",
        []
    )

    prices_data = price_result.get(
        "hours",
        []
    )

    n = min(
        len(forecast),
        len(prices_data)
    )

    if n == 0:
        return {
            "status": "error",
            "message":
                "No optimization horizon available"
        }

    forecast = forecast[:n]
    prices_data = prices_data[:n]

    solar = [
        float(
            row.get(
                "solar_power_kw",
                0
            )
        )
        for row in forecast
    ]

    load = [
        float(
            row.get(
                "predicted_load_kw",
                0
            )
        )
        for row in forecast
    ]

    price = [
        float(
            row.get(
                "price_per_kwh",
                0
            )
        )
        for row in prices_data
    ]

    initial_soc = percent_to_kwh(
        INITIAL_BATTERY_SOC_PERCENT
    )

    min_soc = percent_to_kwh(
        MIN_BATTERY_SOC_PERCENT
    )

    max_soc = percent_to_kwh(
        MAX_BATTERY_SOC_PERCENT
    )

    terminal_soc = percent_to_kwh(
        TERMINAL_SOC_PERCENT
    )

    model = pulp.LpProblem(
        "Economic_MPC",
        pulp.LpMinimize
    )

    # ==========================================
    # Decision Variables
    # ==========================================

    grid = [
        pulp.LpVariable(
            f"grid_{t}",
            lowBound=0
        )
        for t in range(n)
    ]

    solar_used = [
        pulp.LpVariable(
            f"solar_used_{t}",
            lowBound=0,
            upBound=solar[t]
        )
        for t in range(n)
    ]

    charge = [
        pulp.LpVariable(
            f"charge_{t}",
            lowBound=0,
            upBound=MAX_CHARGE_POWER_KW
        )
        for t in range(n)
    ]

    discharge = [
        pulp.LpVariable(
            f"discharge_{t}",
            lowBound=0,
            upBound=MAX_DISCHARGE_POWER_KW
        )
        for t in range(n)
    ]

    shift_out = [
        pulp.LpVariable(
            f"shift_out_{t}",
            lowBound=0,
            upBound=(
                load[t]
                * MAX_SHIFT_PERCENT
            )
        )
        for t in range(n)
    ]

    shift_in = [
        pulp.LpVariable(
            f"shift_in_{t}",
            lowBound=0
        )
        for t in range(n)
    ]

    soc = [
        pulp.LpVariable(
            f"soc_{t}",
            lowBound=min_soc,
            upBound=max_soc
        )
        for t in range(n + 1)
    ]

    # ==========================================
    # Initial SOC
    # ==========================================

    model += (
        soc[0]
        ==
        initial_soc
    )

    # ==========================================
    # Preserve shifted energy
    # ==========================================

    model += (
        pulp.lpSum(
            shift_out
        )
        ==
        pulp.lpSum(
            shift_in
        )
    )

    for t in range(n):

        model += (
            shift_in[t]
            <= max(
                load[t] * 0.40,
                0.5
            )
        )

    # ==========================================
    # Energy Constraints
    # ==========================================

    for t in range(n):

        optimized_load = (
            load[t]
            - shift_out[t]
            + shift_in[t]
        )

        model += (
            solar_used[t]
            + discharge[t]
            + grid[t]
            ==
            optimized_load
            + charge[t]
        )

        model += (
            soc[t + 1]
            ==
            soc[t]
            + (
                charge[t]
                * CHARGE_EFFICIENCY
            )
            - (
                discharge[t]
                / DISCHARGE_EFFICIENCY
            )
        )

    # ==========================================
    # Terminal battery protection
    # ==========================================

    model += (
        soc[n]
        >= terminal_soc
    )

    # ==========================================
    # Objective Function
    # ==========================================

    total_cost = pulp.lpSum([
        grid[t] * price[t]
        for t in range(n)
    ])

    battery_cycle_penalty = (
        0.015
        * pulp.lpSum([
            charge[t]
            + discharge[t]
            for t in range(n)
        ])
    )

    load_shift_penalty = (
        0.01
        * pulp.lpSum(
            shift_out
        )
    )

    unused_solar_penalty = (
        0.03
        * pulp.lpSum([
            solar[t]
            - solar_used[t]
            for t in range(n)
        ])
    )

    model += (
        total_cost
        + battery_cycle_penalty
        + load_shift_penalty
        + unused_solar_penalty
    )

    # ==========================================
    # Solve
    # ==========================================

    solver = pulp.PULP_CBC_CMD(
        msg=False
    )

    model.solve(
        solver
    )

    solver_status = pulp.LpStatus[
        model.status
    ]

    if solver_status != "Optimal":
        return {
            "status": "error",
            "solver_status":
                solver_status
        }

    # ==========================================
    # Output
    # ==========================================

    plan = []

    baseline_cost = 0.0
    optimized_cost = 0.0

    total_grid_baseline = 0.0
    total_grid_optimized = 0.0

    total_shifted = 0.0

    for t in range(n):

        grid_value = float(
            grid[t].value() or 0
        )

        charge_value = float(
            charge[t].value() or 0
        )

        discharge_value = float(
            discharge[t].value() or 0
        )

        solar_used_value = float(
            solar_used[t].value() or 0
        )

        shift_out_value = float(
            shift_out[t].value() or 0
        )

        shift_in_value = float(
            shift_in[t].value() or 0
        )

        soc_before = float(
            soc[t].value()
            or initial_soc
        )

        soc_after = float(
            soc[t + 1].value()
            or soc_before
        )

        optimized_load = (
            load[t]
            - shift_out_value
            + shift_in_value
        )

        baseline_grid = max(
            load[t] - solar[t],
            0.0
        )

        baseline_hour_cost = (
            baseline_grid
            * price[t]
        )

        optimized_hour_cost = (
            grid_value
            * price[t]
        )

        baseline_cost += (
            baseline_hour_cost
        )

        optimized_cost += (
            optimized_hour_cost
        )

        total_grid_baseline += (
            baseline_grid
        )

        total_grid_optimized += (
            grid_value
        )

        total_shifted += (
            shift_out_value
        )

        # ======================================
        # Recommendation
        # ======================================

        if (
            discharge_value > 0.05
            and prices_data[t][
                "price_level"
            ] == "Peak"
        ):
            recommendation = (
                "Use Battery During Peak Price"
            )

            reason = (
                "Electricity price is high, "
                "so stored energy is used "
                "to reduce cost."
            )

        elif charge_value > 0.05:

            recommendation = (
                "Charge Battery"
            )

            reason = (
                "Available energy can be "
                "stored for a later period."
            )

        elif shift_out_value > 0.05:

            recommendation = (
                "Shift Flexible Load"
            )

            reason = (
                "Flexible demand is moved "
                "away from an unfavorable "
                "energy or price period."
            )

        elif shift_in_value > 0.05:

            recommendation = (
                "Run Shifted Load"
            )

            reason = (
                "This period is more favorable "
                "for previously delayed demand."
            )

        elif grid_value > 0.05:

            recommendation = (
                "Use Grid"
            )

            reason = (
                "Grid energy is required "
                "to satisfy remaining demand."
            )

        else:

            recommendation = (
                "Normal Operation"
            )

            reason = (
                "Available solar energy "
                "is sufficient for demand."
            )

        plan.append({
            "forecast_time":
                forecast[t][
                    "forecast_time"
                ],

            "electricity_price":
                round(
                    price[t],
                    3
                ),

            "price_level":
                prices_data[t][
                    "price_level"
                ],

            "solar_available_kw":
                round(
                    solar[t],
                    2
                ),

            "solar_used_kw":
                round(
                    solar_used_value,
                    2
                ),

            "original_load_kw":
                round(
                    load[t],
                    2
                ),

            "optimized_load_kw":
                round(
                    optimized_load,
                    2
                ),

            "load_shifted_out_kw":
                round(
                    shift_out_value,
                    2
                ),

            "load_shifted_in_kw":
                round(
                    shift_in_value,
                    2
                ),

            "battery_charge_kw":
                round(
                    charge_value,
                    2
                ),

            "battery_discharge_kw":
                round(
                    discharge_value,
                    2
                ),

            "battery_soc_before_percent":
                kwh_to_percent(
                    soc_before
                ),

            "battery_soc_after_percent":
                kwh_to_percent(
                    soc_after
                ),

            "grid_power_kw":
                round(
                    grid_value,
                    2
                ),

            "baseline_hour_cost":
                round(
                    baseline_hour_cost,
                    3
                ),

            "optimized_hour_cost":
                round(
                    optimized_hour_cost,
                    3
                ),

            "recommended_action":
                recommendation,

            "reason":
                reason
        })

    # ==========================================
    # Improvement Metrics
    # ==========================================

    cost_saving = (
        baseline_cost
        - optimized_cost
    )

    if baseline_cost > 0:

        saving_percent = (
            cost_saving
            / baseline_cost
            * 100
        )

    else:
        saving_percent = 0.0

    grid_reduction = (
        total_grid_baseline
        - total_grid_optimized
    )

    if total_grid_baseline > 0:
        grid_reduction_percent = (
            grid_reduction
            / total_grid_baseline
            * 100.0
        )
    else:
        grid_reduction_percent = 0.0

    total_solar_available = sum(
        solar
    )

    total_solar_used = sum(
        float(
            solar_used[t].value()
            or 0.0
        )
        for t in range(n)
    )

    if total_solar_available > 0:
        solar_utilization_percent = (
            total_solar_used
            / total_solar_available
            * 100.0
        )
    else:
        solar_utilization_percent = 0.0

    return {
        "status":
            "ok",

        "optimization_model":
            "Economic MPC - Time-of-Use Prototype",

        "control_mode":
            "Decision Support Only",

        "generated_at":
            datetime.now().isoformat(),

        "planning_horizon_hours":
            n,

        "pricing": {
            "model":
                "Time-of-Use",

            "currency":
                "Generic Unit",

            "note":
                "Prototype simulated tariff"
        },

        "summary": {
            "baseline_energy_cost":
                round(
                    baseline_cost,
                    3
                ),

            "optimized_energy_cost":
                round(
                    optimized_cost,
                    3
                ),

            "estimated_cost_saving":
                round(
                    cost_saving,
                    3
                ),

            "cost_saving_percent":
                round(
                    saving_percent,
                    2
                ),

            "grid_without_optimization_kwh":
                round(
                    total_grid_baseline,
                    2
                ),

            "grid_after_optimization_kwh":
                round(
                    total_grid_optimized,
                    2
                ),

            "grid_reduction_kwh":
                round(
                    grid_reduction,
                    2
                ),

            "grid_reduction_percent":
                round(
                    grid_reduction_percent,
                    2
                ),

            "shifted_load_kwh":
                round(
                    total_shifted,
                    2
                ),

            "solar_available_kwh":
                round(
                    total_solar_available,
                    2
                ),

            "solar_used_kwh":
                round(
                    total_solar_used,
                    2
                ),

            "solar_utilization_percent":
                round(
                    solar_utilization_percent,
                    2
                ),

            "final_battery_soc_percent":
                kwh_to_percent(
                    float(
                        soc[n].value()
                        or initial_soc
                    )
                )
        },

        "plan":
            plan
    }