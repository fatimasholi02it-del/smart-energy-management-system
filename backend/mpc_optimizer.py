from datetime import datetime

import pulp

from energy_forecast_service import get_energy_forecast


# =========================================================
# Prototype MPC Configuration
# =========================================================

DEFAULT_HORIZON_HOURS = 6

# Virtual / simulated battery parameters
BATTERY_CAPACITY_KWH = 5.0
INITIAL_BATTERY_SOC_PERCENT = 50.0

MIN_BATTERY_SOC_PERCENT = 20.0
MAX_BATTERY_SOC_PERCENT = 90.0

MAX_CHARGE_POWER_KW = 2.0
MAX_DISCHARGE_POWER_KW = 2.0

CHARGE_EFFICIENCY = 0.95
DISCHARGE_EFFICIENCY = 0.95

# Maximum flexible load that can be shifted from an hour
MAX_SHIFT_PERCENT = 0.25


def soc_percent_to_kwh(percent: float) -> float:
    return (
        percent / 100.0
    ) * BATTERY_CAPACITY_KWH


def soc_kwh_to_percent(value: float) -> float:
    if BATTERY_CAPACITY_KWH <= 0:
        return 0.0

    return round(
        (value / BATTERY_CAPACITY_KWH) * 100.0,
        2
    )


def optimize_energy_plan(
    hours: int = DEFAULT_HORIZON_HOURS,
    forecast_override=None
):
    """
    Deterministic MPC prototype.

    Inputs:
    - Solar forecast
    - Load forecast
    - Simulated battery
    - Flexible load shifting

    Objective:
    - Reduce grid dependency
    - Maximize solar utilization
    - Shift flexible loads toward better solar periods
    - Protect battery SOC
    """
    if forecast_override is None:
        forecast_result = get_energy_forecast(
            hours=hours
        )
    else:
        forecast_result = {
            "status": "ok",
            "hours": forecast_override
        }

    if forecast_result.get("status") != "ok":
        return {
            "status": "error",
            "message": (
                "Energy forecast is unavailable"
            ),
            "forecast_result": forecast_result
        }

    forecast_hours = forecast_result.get(
        "hours",
        []
    )

    if not forecast_hours:
        return {
            "status": "error",
            "message": (
                "No forecast hours are available "
                "for optimization"
            )
        }

    n = len(forecast_hours)

    # =====================================================
    # Extract input data
    # =====================================================

    solar = [
        float(
            item.get(
                "solar_power_kw",
                0.0
            )
        )
        for item in forecast_hours
    ]

    load = [
        float(
            item.get(
                "predicted_load_kw",
                0.0
            )
        )
        for item in forecast_hours
    ]

    # =====================================================
    # Battery boundaries
    # =====================================================

    initial_soc_kwh = soc_percent_to_kwh(
        INITIAL_BATTERY_SOC_PERCENT
    )

    min_soc_kwh = soc_percent_to_kwh(
        MIN_BATTERY_SOC_PERCENT
    )

    max_soc_kwh = soc_percent_to_kwh(
        MAX_BATTERY_SOC_PERCENT
    )

    # =====================================================
    # Create optimization model
    # =====================================================

    model = pulp.LpProblem(
        "Smart_Energy_MPC",
        pulp.LpMinimize
    )

    # =====================================================
    # Decision variables
    # =====================================================

    grid_power = [
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

    #
    # Flexible load shifted OUT of current hour
    #
    shift_out = [
        pulp.LpVariable(
            f"shift_out_{t}",
            lowBound=0,
            upBound=load[t] * MAX_SHIFT_PERCENT
        )
        for t in range(n)
    ]

    #
    # Flexible load shifted INTO another hour
    #
    shift_in = [
        pulp.LpVariable(
            f"shift_in_{t}",
            lowBound=0,
            upBound=max(
                load[t] * 0.35,
                0.5
            )
        )
        for t in range(n)
    ]

    #
    # Battery SOC:
    # n + 1 states because:
    #
    # SOC[0]     = initial state
    # SOC[1]     = after first hour
    # ...
    # SOC[n]
    #
    battery_soc = [
        pulp.LpVariable(
            f"battery_soc_{t}",
            lowBound=min_soc_kwh,
            upBound=max_soc_kwh
        )
        for t in range(n + 1)
    ]

    # =====================================================
    # Initial battery SOC
    # =====================================================

    model += (
        battery_soc[0]
        == initial_soc_kwh
    )

    # =====================================================
    # Load shifting conservation
    # =====================================================
    #
    # Energy shifted OUT must appear somewhere else
    # in the planning horizon.
    #
    # Therefore MPC cannot simply "delete" load.
    #

    model += (
        pulp.lpSum(shift_out)
        ==
        pulp.lpSum(shift_in)
    )

    # =====================================================
    # Hour-by-hour constraints
    # =====================================================

    for t in range(n):

        optimized_load = (
            load[t]
            - shift_out[t]
            + shift_in[t]
        )

        # ---------------------------------------------
        # Energy balance
        # ---------------------------------------------
        #
        # Solar
        # + Battery discharge
        # + Grid
        #
        # must supply:
        #
        # Optimized load
        # + Battery charging
        #

        model += (
            solar_used[t]
            + battery_discharge[t]
            + grid_power[t]
            ==
            optimized_load
            + battery_charge[t]
        )

        # ---------------------------------------------
        # Battery SOC evolution
        # ---------------------------------------------

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
    # Protect end-of-horizon battery
    # =====================================================
    #
    # We don't want optimizer to empty the whole battery
    # just to make the result look good.
    #

    minimum_terminal_soc = soc_percent_to_kwh(
        35.0
    )

    model += (
        battery_soc[n]
        >= minimum_terminal_soc
    )

    # =====================================================
    # Objective Function
    # =====================================================

    GRID_WEIGHT = 1.0

    LOAD_SHIFT_WEIGHT = 0.08

    BATTERY_CYCLE_WEIGHT = 0.03

    UNUSED_SOLAR_WEIGHT = 0.20

    objective = []

    for t in range(n):

        unused_solar = (
            solar[t]
            - solar_used[t]
        )

        objective.append(
            GRID_WEIGHT
            * grid_power[t]
        )

        objective.append(
            LOAD_SHIFT_WEIGHT
            * shift_out[t]
        )

        objective.append(
            BATTERY_CYCLE_WEIGHT
            * (
                battery_charge[t]
                + battery_discharge[t]
            )
        )

        objective.append(
            UNUSED_SOLAR_WEIGHT
            * unused_solar
        )

    model += pulp.lpSum(
        objective
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
            "message": (
                "MPC optimization could not "
                "find an optimal solution"
            ),
            "solver_status": solver_status
        }

    # =====================================================
    # Build output plan
    # =====================================================

    plan = []

    total_original_load = 0.0
    total_optimized_load = 0.0

    total_solar_available = 0.0
    total_solar_used = 0.0

    total_grid = 0.0

    total_shifted_load = 0.0

    for t in range(n):

        original_load = load[t]

        shifted_out_value = float(
            shift_out[t].value() or 0.0
        )

        shifted_in_value = float(
            shift_in[t].value() or 0.0
        )

        optimized_load = (
            original_load
            - shifted_out_value
            + shifted_in_value
        )

        grid_value = float(
            grid_power[t].value() or 0.0
        )

        solar_used_value = float(
            solar_used[t].value() or 0.0
        )

        charge_value = float(
            battery_charge[t].value() or 0.0
        )

        discharge_value = float(
            battery_discharge[t].value() or 0.0
        )

        soc_before = float(
            battery_soc[t].value()
            or initial_soc_kwh
        )

        soc_after = float(
            battery_soc[t + 1].value()
            or soc_before
        )

        #
        # Human-readable action
        #

        actions = []

        if shifted_out_value > 0.05:
            actions.append(
                "Shift flexible load to another hour"
            )

        if shifted_in_value > 0.05:
            actions.append(
                "Run previously shifted load"
            )

        if charge_value > 0.05:
            actions.append(
                "Charge battery"
            )

        if discharge_value > 0.05:
            actions.append(
                "Use battery"
            )

        if solar_used_value > 0.05:
            actions.append(
                "Use available solar energy"
            )

        if grid_value > 0.05:
            actions.append(
                "Use grid energy"
            )

        if not actions:
            actions.append(
                "Maintain normal operation"
            )

        #
        # Main recommendation
        #

        if shifted_out_value > 0.05:
            recommended_action = (
                "Shift Load"
            )

        elif charge_value > 0.05:
            recommended_action = (
                "Charge Battery"
            )

        elif discharge_value > 0.05:
            recommended_action = (
                "Use Battery"
            )

        elif grid_value > 0.05:
            recommended_action = (
                "Use Grid"
            )

        else:
            recommended_action = (
                "Normal Operation"
            )

        #
        # Reason
        #

        solar_value = solar[t]

        if solar_value >= original_load:
            reason = (
                "Solar availability is favorable "
                "relative to expected load."
            )

        elif discharge_value > 0.05:
            reason = (
                "Expected load exceeds solar generation, "
                "so stored battery energy can reduce "
                "grid dependency."
            )

        elif shifted_out_value > 0.05:
            reason = (
                "Expected energy deficit is high, "
                "so flexible consumption is shifted "
                "to a more favorable period."
            )

        else:
            reason = (
                "Forecast demand cannot be fully covered "
                "by available solar energy."
            )

        plan.append({
            "forecast_time":
                forecast_hours[t][
                    "forecast_time"
                ],

            "weather_condition":
                forecast_hours[t].get(
                    "weather_condition"
                ),

            "temperature":
                forecast_hours[t].get(
                    "temperature"
                ),

            "solar_available_kw":
                round(
                    solar_value,
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

            "load_shifted_out_kw":
                round(
                    shifted_out_value,
                    2
                ),

            "load_shifted_in_kw":
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
                soc_kwh_to_percent(
                    soc_before
                ),

            "battery_soc_after_percent":
                soc_kwh_to_percent(
                    soc_after
                ),

            "grid_power_kw":
                round(
                    grid_value,
                    2
                ),

            "recommended_action":
                recommended_action,

            "actions":
                actions,

            "reason":
                reason
        })

        total_original_load += (
            original_load
        )

        total_optimized_load += (
            optimized_load
        )

        total_solar_available += (
            solar_value
        )

        total_solar_used += (
            solar_used_value
        )

        total_grid += (
            grid_value
        )

        total_shifted_load += (
            shifted_out_value
        )

    # =====================================================
    # Summary metrics
    # =====================================================

    solar_utilization_percent = 0.0

    if total_solar_available > 0:
        solar_utilization_percent = (
            total_solar_used
            / total_solar_available
        ) * 100.0

    grid_without_optimization = sum(
        max(
            load[t] - solar[t],
            0.0
        )
        for t in range(n)
    )

    grid_reduction = (
        grid_without_optimization
        - total_grid
    )

    if grid_without_optimization > 0:
        grid_reduction_percent = (
            grid_reduction
            / grid_without_optimization
        ) * 100.0
    else:
        grid_reduction_percent = 0.0

    return {
        "status": "ok",

        "optimization_model":
            "Deterministic MPC - Receding Horizon Prototype",

        "control_mode":
            "Decision Support Only",

        "generated_at":
            datetime.now().isoformat(),

        "planning_horizon_hours":
            n,

        "assumptions": {
            "solar_source":
                "Virtual PV model based on weather forecast",

            "battery_source":
                "Simulated battery model",

            "load_source":
                "Simulation now / real sensor later",

            "battery_capacity_kwh":
                BATTERY_CAPACITY_KWH,

            "initial_battery_soc_percent":
                INITIAL_BATTERY_SOC_PERCENT,

            "minimum_battery_soc_percent":
                MIN_BATTERY_SOC_PERCENT,

            "maximum_battery_soc_percent":
                MAX_BATTERY_SOC_PERCENT,

            "max_shift_percent":
                MAX_SHIFT_PERCENT * 100
        },

        "summary": {
            "forecast_load_kwh":
                round(
                    total_original_load,
                    2
                ),

            "optimized_load_kwh":
                round(
                    total_optimized_load,
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

            "grid_without_optimization_kwh":
                round(
                    grid_without_optimization,
                    2
                ),

            "grid_after_optimization_kwh":
                round(
                    total_grid,
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
                    total_shifted_load,
                    2
                ),

            "final_battery_soc_percent":
                soc_kwh_to_percent(
                    float(
                        battery_soc[n].value()
                        or initial_soc_kwh
                    )
                )
        },

        "plan":
            plan
    }