from datetime import datetime

import pulp

from ml_energy_forecast_service import (
    get_ml_energy_forecast
)

from electricity_price_service import (
    get_electricity_price_forecast
)


# =========================================================
# Battery Configuration
# =========================================================

BATTERY_CAPACITY_KWH = 5.0

INITIAL_BATTERY_SOC_PERCENT = 50.0

# Hard physical limits
MIN_BATTERY_SOC_PERCENT = 20.0
MAX_BATTERY_SOC_PERCENT = 90.0

# Preferred reserve
PREFERRED_MIN_SOC_PERCENT = 35.0

# End-of-horizon protection
TERMINAL_SOC_PERCENT = 35.0

MAX_CHARGE_POWER_KW = 2.0
MAX_DISCHARGE_POWER_KW = 2.0

CHARGE_EFFICIENCY = 0.95
DISCHARGE_EFFICIENCY = 0.95

MAX_SHIFT_PERCENT = 0.25
MAX_SHIFT_DELAY_HOURS = 3


# =========================================================
# Objective Weights
# =========================================================

BATTERY_CYCLE_COST = 0.035

LOW_SOC_PENALTY = 0.20

LOAD_SHIFT_PENALTY = 0.01

UNUSED_SOLAR_PENALTY = 0.03

# Makes grid charging unattractive during Normal / Peak periods
GRID_CHARGING_NORMAL_PENALTY = 0.15
GRID_CHARGING_PEAK_PENALTY = 0.50


def percent_to_kwh(
    percent: float
) -> float:
    return (
        percent / 100.0
    ) * BATTERY_CAPACITY_KWH


def kwh_to_percent(
    value: float
) -> float:
    if BATTERY_CAPACITY_KWH <= 0:
        return 0.0

    return round(
        (
            value
            / BATTERY_CAPACITY_KWH
        )
        * 100.0,
        2
    )


def optimize_battery_aware_ml_mpc(
    hours: int = 6,
    source: str = "auto",
    forecast_override=None,
    price_override=None
):

    # =====================================================
    # ML Energy Forecast
    # =====================================================

    if forecast_override is None:
        forecast_result = get_ml_energy_forecast(
            hours=hours,
            source=source
        )
    else:
        forecast_result = {
            "status": "ok",
            "hours": forecast_override,
            "selected_training_source": source,
            "real_sensor_training": source == "sensor",
            "ml_evaluation": {}
        }

    if forecast_result.get("status") != "ok":
        return {
            "status": forecast_result.get(
                "status",
                "error"
            ),
            "message": forecast_result.get(
                "message",
                "ML energy forecast unavailable"
            ),
            "forecast": forecast_result
        }

    # =====================================================
    # Electricity Prices
    # =====================================================

    if price_override is None:
        price_result = get_electricity_price_forecast(
            hours=hours
        )
    else:
        price_result = {
            "status": "ok",
            "hours": price_override
        }

    if price_result.get("status") != "ok":
        return {
            "status": "error",
            "message": (
                "Electricity price forecast unavailable"
            )
        }

    # =====================================================
    # Forecast / Price Data
    # =====================================================

    forecast = forecast_result.get(
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
            "message": (
                "No planning horizon available"
            )
        }

    forecast = forecast[:n]
    prices_data = prices_data[:n]

    # =====================================================
    # Input Arrays
    # =====================================================

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

    prices = [
        float(
            row.get(
                "price_per_kwh",
                0.0
            )
        )
        for row in prices_data
    ]

    price_levels = [
        row.get(
            "price_level",
            "Normal"
        )
        for row in prices_data
    ]
    # =====================================================
    # SOC Values
    # =====================================================

    initial_soc = percent_to_kwh(
        INITIAL_BATTERY_SOC_PERCENT
    )

    hard_min_soc = percent_to_kwh(
        MIN_BATTERY_SOC_PERCENT
    )

    max_soc = percent_to_kwh(
        MAX_BATTERY_SOC_PERCENT
    )

    preferred_min_soc = percent_to_kwh(
        PREFERRED_MIN_SOC_PERCENT
    )

    terminal_soc = percent_to_kwh(
        TERMINAL_SOC_PERCENT
    )

    # =====================================================
    # Optimization Model
    # =====================================================

    model = pulp.LpProblem(
        "Battery_Aware_ML_Economic_MPC",
        pulp.LpMinimize
    )

    # =====================================================
    # Main Variables
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
            lowBound=hard_min_soc,
            upBound=max_soc
        )
        for t in range(n + 1)
    ]

    # =====================================================
    # Low SOC violation variable
    #
    # preferred_min_soc - SOC, if SOC falls below preferred
    # =====================================================

    low_soc_violation = [
        pulp.LpVariable(
            f"low_soc_violation_{t}",
            lowBound=0
        )
        for t in range(n + 1)
    ]

    # =====================================================
    # Grid charging approximation
    #
    # Used to penalize charging during expensive periods.
    # =====================================================

    grid_charge = [
        pulp.LpVariable(
            f"grid_charge_{t}",
            lowBound=0,
            upBound=MAX_CHARGE_POWER_KW
        )
        for t in range(n)
    ]

    # =====================================================
    # Forward-Only Load Shifting
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

            shift[
                (from_t, to_t)
            ] = pulp.LpVariable(
                f"shift_{from_t}_{to_t}",
                lowBound=0
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
    # Preferred SOC Soft Constraint
    # =====================================================

    for t in range(n + 1):

        model += (
            low_soc_violation[t]
            >=
            preferred_min_soc
            - battery_soc[t]
        )

    # =====================================================
    # Load Shifting Limits
    # =====================================================

    for from_t in range(n):

        outgoing = [
            variable
            for (
                source_t,
                target_t
            ), variable in shift.items()
            if source_t == from_t
        ]

        if outgoing:
            model += (
                pulp.lpSum(
                    outgoing
                )
                <=
                load[from_t]
                * MAX_SHIFT_PERCENT
            )

    for to_t in range(n):

        incoming = [
            variable
            for (
                source_t,
                target_t
            ), variable in shift.items()
            if target_t == to_t
        ]

        if incoming:
            model += (
                pulp.lpSum(
                    incoming
                )
                <=
                max(
                    load[to_t] * 0.40,
                    0.5
                )
            )

    # =====================================================
    # Hourly Constraints
    # =====================================================

    for t in range(n):

        shifted_out = pulp.lpSum([
            variable
            for (
                source_t,
                target_t
            ), variable in shift.items()
            if source_t == t
        ])

        shifted_in = pulp.lpSum([
            variable
            for (
                source_t,
                target_t
            ), variable in shift.items()
            if target_t == t
        ])

        optimized_load = (
            load[t]
            - shifted_out
            + shifted_in
        )

        # ---------------------------------------------
        # Energy balance
        # ---------------------------------------------

        model += (
            solar_used[t]
            + battery_discharge[t]
            + grid[t]
            ==
            optimized_load
            + battery_charge[t]
        )

        # ---------------------------------------------
        # Battery SOC
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

        # ---------------------------------------------
        # Estimate amount of battery charging
        # that may effectively come from grid.
        #
        # grid_charge >= charge - unused solar supply
        # ---------------------------------------------

        model += (
            grid_charge[t]
            >=
            battery_charge[t]
            - (
                solar[t]
                - solar_used[t]
            )
        )

        model += (
            grid_charge[t]
            <= battery_charge[t]
        )

    # =====================================================
    # Terminal SOC
    # =====================================================

    model += (
        battery_soc[n]
        >= terminal_soc
    )

    # =====================================================
    # Objective Components
    # =====================================================

    electricity_cost = pulp.lpSum([
        grid[t]
        * prices[t]
        for t in range(n)
    ])

    battery_cycle_penalty = (
        BATTERY_CYCLE_COST
        * pulp.lpSum([
            battery_charge[t]
            + battery_discharge[t]
            for t in range(n)
        ])
    )

    low_soc_penalty = (
        LOW_SOC_PENALTY
        * pulp.lpSum(
            low_soc_violation
        )
    )

    unused_solar_penalty = (
        UNUSED_SOLAR_PENALTY
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
            LOAD_SHIFT_PENALTY
            * delay_hours
            * variable
        )

    grid_charging_penalty_terms = []

    for t in range(n):

        if price_levels[t] == "Peak":
            penalty = (
                GRID_CHARGING_PEAK_PENALTY
            )

        elif price_levels[t] == "Normal":
            penalty = (
                GRID_CHARGING_NORMAL_PENALTY
            )

        else:
            penalty = 0.0

        grid_charging_penalty_terms.append(
            penalty
            * grid_charge[t]
        )

    # =====================================================
    # Final Objective
    # =====================================================

    model += (
        electricity_cost
        + battery_cycle_penalty
        + low_soc_penalty
        + unused_solar_penalty
        + pulp.lpSum(
            shift_penalty_terms
        )
        + pulp.lpSum(
            grid_charging_penalty_terms
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
            "status":
                "error",

            "solver_status":
                solver_status,

            "message":
                (
                    "Battery-aware MPC could not "
                    "find an optimal solution."
                )
        }

    # =====================================================
    # Build Shift Schedule
    # =====================================================

    shift_schedule = []

    total_shifted = 0.0

    for (
        from_t,
        to_t
    ), variable in shift.items():

        value = float(
            variable.value()
            or 0.0
        )

        if value > 0.001:

            shift_schedule.append({
                "from_time":
                    forecast[
                        from_t
                    ][
                        "forecast_time"
                    ],

                "to_time":
                    forecast[
                        to_t
                    ][
                        "forecast_time"
                    ],

                "shifted_load_kwh":
                    round(
                        value,
                        3
                    ),

                "delay_hours":
                    to_t
                    - from_t
            })

            total_shifted += value

    # =====================================================
    # Plan + Metrics
    # =====================================================

    plan = []

    baseline_cost = 0.0
    optimized_cost = 0.0

    total_grid_baseline = 0.0
    total_grid_optimized = 0.0

    total_solar_available = sum(
        solar
    )

    total_solar_used = 0.0

    total_battery_charge = 0.0
    total_battery_discharge = 0.0

    total_low_soc_hours = 0

    for t in range(n):

        shifted_out_value = sum(
            float(
                variable.value()
                or 0.0
            )
            for (
                source_t,
                target_t
            ), variable in shift.items()
            if source_t == t
        )

        shifted_in_value = sum(
            float(
                variable.value()
                or 0.0
            )
            for (
                source_t,
                target_t
            ), variable in shift.items()
            if target_t == t
        )

        original_load = (
            load[t]
        )

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

        grid_charge_value = float(
            grid_charge[t].value()
            or 0.0
        )

        soc_before = float(
            battery_soc[t].value()
            or initial_soc
        )

        soc_after = float(
            battery_soc[
                t + 1
            ].value()
            or soc_before
        )

        soc_after_percent = (
            kwh_to_percent(
                soc_after
            )
        )

        baseline_grid = max(
            original_load
            - solar[t],
            0.0
        )

        baseline_hour_cost = (
            baseline_grid
            * prices[t]
        )

        optimized_hour_cost = (
            grid_value
            * prices[t]
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

        total_solar_used += (
            solar_used_value
        )

        total_battery_charge += (
            charge_value
        )

        total_battery_discharge += (
            discharge_value
        )

        if (
            soc_after_percent
            <
            PREFERRED_MIN_SOC_PERCENT
        ):
            total_low_soc_hours += 1

        # =================================================
        # Recommendation
        # =================================================

        if (
            shifted_out_value
            > 0.05
        ):

            recommended_action = (
                "Delay Flexible Load"
            )

            reason = (
                "Flexible demand is postponed "
                "to a later, more favorable period."
            )

        elif (
            shifted_in_value
            > 0.05
        ):

            recommended_action = (
                "Run Previously Delayed Load"
            )

            reason = (
                "This period was selected "
                "for previously delayed demand."
            )

        elif (
            discharge_value > 0.05
            and price_levels[t]
            == "Peak"
        ):

            recommended_action = (
                "Use Battery During Peak Price"
            )

            reason = (
                "Stored energy is used during "
                "an expensive tariff period."
            )

        elif (
            discharge_value > 0.05
        ):

            recommended_action = (
                "Use Battery"
            )

            reason = (
                "Battery energy is used while "
                "maintaining the preferred reserve "
                "when economically reasonable."
            )

        elif (
            charge_value > 0.05
        ):

            if (
                grid_charge_value
                > 0.05
            ):

                recommended_action = (
                    "Charge Battery From Grid"
                )

                reason = (
                    "Battery charging is scheduled "
                    "because the current tariff "
                    "makes future stored energy valuable."
                )

            else:

                recommended_action = (
                    "Charge Battery From Solar"
                )

                reason = (
                    "Available solar energy is used "
                    "to charge the battery."
                )

        elif (
            grid_value > 0.05
        ):

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
                "Current demand can be supplied "
                "without additional grid usage."
            )

        plan.append({
            "forecast_time":
                forecast[t][
                    "forecast_time"
                ],

            "price_per_kwh":
                round(
                    prices[t],
                    3
                ),

            "price_level":
                price_levels[t],

            "solar_available_kw":
                round(
                    solar[t],
                    3
                ),

            "solar_used_kw":
                round(
                    solar_used_value,
                    3
                ),

            "original_load_kw":
                round(
                    original_load,
                    3
                ),

            "optimized_load_kw":
                round(
                    optimized_load,
                    3
                ),

            "shifted_out_kw":
                round(
                    shifted_out_value,
                    3
                ),

            "shifted_in_kw":
                round(
                    shifted_in_value,
                    3
                ),

            "battery_charge_kw":
                round(
                    charge_value,
                    3
                ),

            "battery_discharge_kw":
                round(
                    discharge_value,
                    3
                ),

            "estimated_grid_charge_kw":
                round(
                    grid_charge_value,
                    3
                ),

            "battery_soc_before_percent":
                kwh_to_percent(
                    soc_before
                ),

            "battery_soc_after_percent":
                soc_after_percent,

            "preferred_min_soc_percent":
                PREFERRED_MIN_SOC_PERCENT,

            "below_preferred_soc":
                (
                    soc_after_percent
                    <
                    PREFERRED_MIN_SOC_PERCENT
                ),

            "grid_power_kw":
                round(
                    grid_value,
                    3
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
    # Summary
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

    if total_solar_available > 0:

        solar_utilization_percent = (
            total_solar_used
            / total_solar_available
            * 100.0
        )

    else:
        solar_utilization_percent = 0.0

    final_soc = float(
        battery_soc[n].value()
        or initial_soc
    )

    return {
        "status":
            "ok",

        "optimization_model":
            (
                "Battery-Aware ML-Driven "
                "Advanced Economic MPC"
            ),

        "control_mode":
            "Decision Support Only",

        "generated_at":
            datetime.now().isoformat(),

        "planning_horizon_hours":
            n,

        "load_forecast_model":
            "Random Forest Regressor",

        "requested_training_source":
            source,

        "selected_training_source":
            forecast_result.get(
                "selected_training_source"
            ),

        "real_sensor_training":
            forecast_result.get(
                "real_sensor_training",
                False
            ),

        "ml_evaluation":
            forecast_result.get(
                "ml_evaluation",
                {}
            ),

        "battery_policy": {
            "capacity_kwh":
                BATTERY_CAPACITY_KWH,

            "initial_soc_percent":
                INITIAL_BATTERY_SOC_PERCENT,

            "hard_min_soc_percent":
                MIN_BATTERY_SOC_PERCENT,

            "preferred_min_soc_percent":
                PREFERRED_MIN_SOC_PERCENT,

            "maximum_soc_percent":
                MAX_BATTERY_SOC_PERCENT,

            "terminal_soc_percent":
                TERMINAL_SOC_PERCENT,

            "charge_efficiency":
                CHARGE_EFFICIENCY,

            "discharge_efficiency":
                DISCHARGE_EFFICIENCY
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
                    3
                ),

            "grid_after_optimization_kwh":
                round(
                    total_grid_optimized,
                    3
                ),

            "grid_reduction_kwh":
                round(
                    grid_reduction,
                    3
                ),

            "grid_reduction_percent":
                round(
                    grid_reduction_percent,
                    2
                ),

            "solar_available_kwh":
                round(
                    total_solar_available,
                    3
                ),

            "solar_used_kwh":
                round(
                    total_solar_used,
                    3
                ),

            "solar_utilization_percent":
                round(
                    solar_utilization_percent,
                    2
                ),

            "total_shifted_load_kwh":
                round(
                    total_shifted,
                    3
                ),

            "battery_charge_throughput_kwh":
                round(
                    total_battery_charge,
                    3
                ),

            "battery_discharge_throughput_kwh":
                round(
                    total_battery_discharge,
                    3
                ),

            "hours_below_preferred_soc":
                total_low_soc_hours,

            "final_battery_soc_percent":
                kwh_to_percent(
                    final_soc
                )
        },

        "shift_schedule":
            shift_schedule,

        "plan":
            plan
    }