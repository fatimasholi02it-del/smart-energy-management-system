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

MAX_SHIFT_DELAY_HOURS = 3


def percent_to_kwh(percent: float) -> float:
    return (
        percent / 100.0
    ) * BATTERY_CAPACITY_KWH


def kwh_to_percent(value: float) -> float:
    if BATTERY_CAPACITY_KWH <= 0:
        return 0.0

    return round(
        value / BATTERY_CAPACITY_KWH * 100.0,
        2
    )


def optimize_advanced_economic_mpc(
    hours: int = 6,
    forecast_override=None,
    price_override=None
):
    
    if forecast_override is None:

        energy_result = (
            get_energy_forecast(
                hours=hours
            )
    )

    else:

        energy_result = {
            "status": "ok",
            "hours": forecast_override
        }

        if price_override is None:
            price_result = get_electricity_price_forecast(
                hours=hours
            )
        else:
            price_result = {
                "status": "ok",
                "hours": price_override
            }

    if energy_result.get("status") != "ok":
        return {
            "status": "error",
            "message": "Energy forecast unavailable"
        }

    if price_result.get("status") != "ok":
        return {
            "status": "error",
            "message": "Electricity price forecast unavailable"
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
            "message": "No planning horizon available"
        }

    forecast = forecast[:n]
    prices_data = prices_data[:n]

    solar = [
        float(
            row.get(
                "solar_power_kw",
                0.0
            )
        )
        for row in forecast
    ]

    load = [
        float(
            row.get(
                "predicted_load_kw",
                0.0
            )
        )
        for row in forecast
    ]

    price = [
        float(
            row.get(
                "price_per_kwh",
                0.0
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
        "Advanced_Economic_MPC",
        pulp.LpMinimize
    )

    # =====================================================
    # Decision variables
    # =====================================================

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

    battery_charge = [
        pulp.LpVariable(
            f"battery_charge_{t}",
            lowBound=0,
            upBound=MAX_CHARGE_POWER_KW
        )
        for t in range(n)
    ]

    battery_discharge = [
        pulp.LpVariable(
            f"battery_discharge_{t}",
            lowBound=0,
            upBound=MAX_DISCHARGE_POWER_KW
        )
        for t in range(n)
    ]

    battery_soc = [
        pulp.LpVariable(
            f"battery_soc_{t}",
            lowBound=min_soc,
            upBound=max_soc
        )
        for t in range(n + 1)
    ]

    # =====================================================
    # Forward-only shift matrix
    # =====================================================

    shift = {}

    for from_t in range(n):
        for to_t in range(n):

            if to_t <= from_t:
                continue

            if (
                to_t - from_t
                > MAX_SHIFT_DELAY_HOURS
            ):
                continue

            shift[(from_t, to_t)] = (
                pulp.LpVariable(
                    f"shift_{from_t}_{to_t}",
                    lowBound=0
                )
            )

    # =====================================================
    # Initial SOC
    # =====================================================

    model += (
        battery_soc[0]
        ==
        initial_soc
    )

    # =====================================================
    # Limit total shift OUT from each hour
    # =====================================================

    for from_t in range(n):

        outgoing = [
            variable
            for (
                source,
                target
            ), variable in shift.items()
            if source == from_t
        ]

        if outgoing:
            model += (
                pulp.lpSum(outgoing)
                <=
                load[from_t]
                * MAX_SHIFT_PERCENT
            )

    # =====================================================
    # Limit total shift IN to each hour
    # =====================================================

    for to_t in range(n):

        incoming = [
            variable
            for (
                source,
                target
            ), variable in shift.items()
            if target == to_t
        ]

        if incoming:
            model += (
                pulp.lpSum(incoming)
                <=
                max(
                    load[to_t] * 0.40,
                    0.5
                )
            )

    # =====================================================
    # Hourly energy constraints
    # =====================================================

    for t in range(n):

        shifted_out = pulp.lpSum([
            variable
            for (
                source,
                target
            ), variable in shift.items()
            if source == t
        ])

        shifted_in = pulp.lpSum([
            variable
            for (
                source,
                target
            ), variable in shift.items()
            if target == t
        ])

        optimized_load = (
            load[t]
            - shifted_out
            + shifted_in
        )

        model += (
            solar_used[t]
            + battery_discharge[t]
            + grid[t]
            ==
            optimized_load
            + battery_charge[t]
        )

        model += (
            battery_soc[t + 1]
            ==
            battery_soc[t]
            + (
                battery_charge[t]
                * CHARGE_EFFICIENCY
            )
            - (
                battery_discharge[t]
                / DISCHARGE_EFFICIENCY
            )
        )

    # =====================================================
    # Terminal SOC
    # =====================================================

    model += (
        battery_soc[n]
        >= terminal_soc
    )

    # =====================================================
    # Objective Function
    # =====================================================

    energy_cost = pulp.lpSum([
        grid[t]
        * price[t]
        for t in range(n)
    ])

    battery_penalty = (
        0.015
        * pulp.lpSum([
            battery_charge[t]
            + battery_discharge[t]
            for t in range(n)
        ])
    )

    unused_solar_penalty = (
        0.03
        * pulp.lpSum([
            solar[t]
            - solar_used[t]
            for t in range(n)
        ])
    )

    shift_penalty_terms = []

    for (
        from_t,
        to_t
    ), variable in shift.items():

        delay_hours = (
            to_t - from_t
        )

        shift_penalty_terms.append(
            0.01
            * delay_hours
            * variable
        )

    model += (
        energy_cost
        + battery_penalty
        + unused_solar_penalty
        + pulp.lpSum(
            shift_penalty_terms
        )
    )

    # =====================================================
    # Solve
    # =====================================================

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
            "solver_status": solver_status,
            "message": (
                "Advanced Economic MPC "
                "could not find optimal solution"
            )
        }

    # =====================================================
    # Build plan
    # =====================================================

    plan = []

    baseline_cost = 0.0
    optimized_cost = 0.0

    total_grid_baseline = 0.0
    total_grid_optimized = 0.0

    total_shifted = 0.0

    shift_schedule = []

    for (
        from_t,
        to_t
    ), variable in shift.items():

        value = float(
            variable.value() or 0.0
        )

        if value > 0.001:

            shift_schedule.append({
                "from_time":
                    forecast[from_t][
                        "forecast_time"
                    ],

                "to_time":
                    forecast[to_t][
                        "forecast_time"
                    ],

                "shifted_load_kwh":
                    round(
                        value,
                        3
                    ),

                "delay_hours":
                    to_t - from_t
            })

            total_shifted += value

    for t in range(n):

        shifted_out_value = sum(
            float(
                variable.value()
                or 0.0
            )
            for (
                source,
                target
            ), variable in shift.items()
            if source == t
        )

        shifted_in_value = sum(
            float(
                variable.value()
                or 0.0
            )
            for (
                source,
                target
            ), variable in shift.items()
            if target == t
        )

        original_load = load[t]

        optimized_load = (
            original_load
            - shifted_out_value
            + shifted_in_value
        )

        grid_value = float(
            grid[t].value()
            or 0.0
        )

        solar_used_value = float(
            solar_used[t].value()
            or 0.0
        )

        charge_value = float(
            battery_charge[t].value()
            or 0.0
        )

        discharge_value = float(
            battery_discharge[t].value()
            or 0.0
        )

        soc_before = float(
            battery_soc[t].value()
            or initial_soc
        )

        soc_after = float(
            battery_soc[t + 1].value()
            or soc_before
        )

        baseline_grid = max(
            original_load
            - solar[t],
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

        # =================================================
        # Human-readable decision
        # =================================================

        if shifted_out_value > 0.05:

            recommended_action = (
                "Delay Flexible Load"
            )

            reason = (
                "Part of the flexible demand "
                "is postponed to a later, "
                "more favorable period."
            )

        elif shifted_in_value > 0.05:

            recommended_action = (
                "Run Previously Delayed Load"
            )

            reason = (
                "This period was selected "
                "for previously postponed demand."
            )

        elif (
            discharge_value > 0.05
            and prices_data[t][
                "price_level"
            ] == "Peak"
        ):

            recommended_action = (
                "Use Battery During Peak Price"
            )

            reason = (
                "Stored energy is used during "
                "the expensive tariff period."
            )

        elif charge_value > 0.05:

            recommended_action = (
                "Charge Battery"
            )

            reason = (
                "Energy is stored for "
                "a later, more valuable period."
            )

        elif grid_value > 0.05:

            recommended_action = (
                "Use Grid"
            )

            reason = (
                "Remaining demand requires "
                "grid energy."
            )

        else:

            recommended_action = (
                "Normal Operation"
            )

            reason = (
                "Available solar energy "
                "is sufficient for current demand."
            )

        plan.append({
            "forecast_time":
                forecast[t][
                    "forecast_time"
                ],

            "price_per_kwh":
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
                    original_load,
                    2
                ),

            "optimized_load_kw":
                round(
                    optimized_load,
                    2
                ),

            "shifted_out_kw":
                round(
                    shifted_out_value,
                    2
                ),

            "shifted_in_kw":
                round(
                    shifted_in_value,
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
                recommended_action,

            "reason":
                reason
        })

    # =====================================================
    # Metrics
    # =====================================================

    cost_saving = (
        baseline_cost
        - optimized_cost
    )

    if baseline_cost > 0:

        cost_saving_percent = (
            cost_saving
            / baseline_cost
            * 100.0
        )

    else:
        cost_saving_percent = 0.0

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
            (
                "Advanced Economic MPC "
                "- Forward-Only Load Shifting"
            ),

        "control_mode":
            "Decision Support Only",

        "generated_at":
            datetime.now().isoformat(),

        "planning_horizon_hours":
            n,

        "assumptions": {
            "battery":
                "Simulated battery",

            "solar":
                "Virtual PV model",

            "load":
                "Simulation now / real sensor later",

            "pricing":
                "Prototype Time-of-Use tariff",

            "forward_only_load_shifting":
                True,

            "maximum_shift_delay_hours":
                MAX_SHIFT_DELAY_HOURS
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
                    cost_saving_percent,
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

            "total_shifted_load_kwh":
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
                        battery_soc[n].value()
                        or initial_soc
                    )
                )
        },

        "shift_schedule":
            shift_schedule,

        "plan":
            plan
    }