from datetime import timedelta

from sqlalchemy import func

from database import SessionLocal
from solar_service import get_solar_forecast
import models


# ============================================================
# Energy Trading Configuration
# ============================================================

ROOM_IDS = [
    "room_1",
    "room_2",
    "room_3",
]

LOAD_WINDOW_MINUTES = 60

PROJECTION_HOURS = 1.0

BALANCE_TOLERANCE_KWH = 0.05


# ============================================================
# Prototype Market Scenarios
#
# These prices are scenario assumptions for the university
# prototype. They are NOT live electricity market prices.
# ============================================================

MARKET_CURRENCY = "AED"

BASE_MARKET_PRICE = 0.60

PEAK_MARKET_PRICE = 0.80


# ============================================================
# Recent Load Profile
#
# Important:
# We use the latest reading timestamp in the database as the
# reference point instead of datetime.now().
#
# This makes the calculation resilient to differences between
# server timezone and device/simulator timezone.
# ============================================================

def get_recent_room_loads(
    window_minutes: int = LOAD_WINDOW_MINUTES,
):
    db = SessionLocal()

    try:
        latest_timestamp = (
            db.query(
                func.max(
                    models.EnergyReading.timestamp
                )
            )
            .scalar()
        )

        if latest_timestamp is None:
            return {
                "reference_time": None,
                "window_minutes": window_minutes,
                "rooms": [
                    {
                        "room_id": room_id,
                        "average_power_kw": 0.0,
                        "reading_count": 0,
                    }
                    for room_id in ROOM_IDS
                ],
            }

        since_time = (
            latest_timestamp
            - timedelta(
                minutes=window_minutes
            )
        )

        # ----------------------------------------------------
        # power_kw is the explicit field.
        #
        # energy is retained as a compatibility field for
        # simulator / older data and currently also represents
        # power-like readings.
        # ----------------------------------------------------

        effective_power = func.coalesce(
            models.EnergyReading.power_kw,
            models.EnergyReading.energy,
        )

        rows = (
            db.query(
                models.EnergyReading.room_id,
                func.avg(
                    effective_power
                ).label(
                    "average_power_kw"
                ),
                func.count(
                    models.EnergyReading.id
                ).label(
                    "reading_count"
                ),
            )
            .filter(
                models.EnergyReading.timestamp
                >= since_time
            )
            .filter(
                models.EnergyReading.timestamp
                <= latest_timestamp
            )
            .group_by(
                models.EnergyReading.room_id
            )
            .all()
        )

        values_by_room = {}

        for row in rows:
            values_by_room[
                row.room_id
            ] = {
                "room_id":
                    row.room_id,

                "average_power_kw":
                    round(
                        float(
                            row.average_power_kw
                            or 0
                        ),
                        3,
                    ),

                "reading_count":
                    int(
                        row.reading_count
                        or 0
                    ),
            }

        rooms = []

        for room_id in ROOM_IDS:
            rooms.append(
                values_by_room.get(
                    room_id,
                    {
                        "room_id":
                            room_id,

                        "average_power_kw":
                            0.0,

                        "reading_count":
                            0,
                    },
                )
            )

        return {
            "reference_time":
                latest_timestamp.isoformat(),

            "window_minutes":
                window_minutes,

            "rooms":
                rooms,
        }

    except Exception as e:
        print(
            "Energy trading load "
            f"calculation error: {e}"
        )

        return {
            "reference_time": None,
            "window_minutes": window_minutes,
            "rooms": [
                {
                    "room_id": room_id,
                    "average_power_kw": 0.0,
                    "reading_count": 0,
                }
                for room_id in ROOM_IDS
            ],
        }

    finally:
        try:
            db.close()

        except Exception as e:
            print(
                "Energy trading DB "
                f"close warning: {e}"
            )


# ============================================================
# Solar Projection
# ============================================================

def get_energy_trading_solar_projection():
    try:
        solar_forecast = (
            get_solar_forecast(
                hours=1
            )
        )

        solar_available = (
            solar_forecast.get(
                "status"
            )
            == "ok"
            and bool(
                solar_forecast.get(
                    "hours"
                )
            )
        )

        if not solar_available:
            return {
                "available": False,
                "forecast_time": None,
                "system_solar_power_kw": 0.0,
                "projected_solar_energy_kwh": 0.0,
                "panel_capacity_kw":
                    solar_forecast.get(
                        "panel_capacity_kw"
                    ),
                "system_efficiency":
                    solar_forecast.get(
                        "system_efficiency"
                    ),
            }

        first_hour = (
            solar_forecast[
                "hours"
            ][0]
        )

        system_solar_power_kw = float(
            first_hour.get(
                "estimated_solar_power_kw",
                0,
            )
            or 0
        )

        projected_solar_energy_kwh = (
            system_solar_power_kw
            * PROJECTION_HOURS
        )

        return {
            "available":
                True,

            "forecast_time":
                first_hour.get(
                    "forecast_time"
                ),

            "system_solar_power_kw":
                round(
                    system_solar_power_kw,
                    3,
                ),

            "projected_solar_energy_kwh":
                round(
                    projected_solar_energy_kwh,
                    3,
                ),

            "panel_capacity_kw":
                solar_forecast.get(
                    "panel_capacity_kw"
                ),

            "system_efficiency":
                solar_forecast.get(
                    "system_efficiency"
                ),
        }

    except Exception as e:
        print(
            "Energy trading solar "
            f"forecast error: {e}"
        )

        return {
            "available": False,
            "forecast_time": None,
            "system_solar_power_kw": 0.0,
            "projected_solar_energy_kwh": 0.0,
            "panel_capacity_kw": None,
            "system_efficiency": None,
        }


# ============================================================
# Trading Status
# ============================================================

def determine_trading_status(
    net_energy_kwh: float,
    solar_available: bool,
):
    if not solar_available:
        return "Forecast Unavailable"

    if (
        net_energy_kwh
        > BALANCE_TOLERANCE_KWH
    ):
        return "Surplus"

    if (
        net_energy_kwh
        < -BALANCE_TOLERANCE_KWH
    ):
        return "Deficit"

    return "Balanced"


# ============================================================
# Room Recommendation
# ============================================================

def build_room_recommendation(
    trading_status: str,
):
    if (
        trading_status
        == "Surplus"
    ):
        return (
            "Projected solar generation "
            "exceeds projected consumption. "
            "Potential export is available."
        )

    if (
        trading_status
        == "Balanced"
    ):
        return (
            "Projected generation and "
            "consumption are approximately "
            "balanced."
        )

    if (
        trading_status
        == "Deficit"
    ):
        return (
            "Projected consumption exceeds "
            "allocated solar generation. "
            "Reduce optional loads before "
            "considering export."
        )

    return (
        "Solar forecast is currently "
        "unavailable, so trading readiness "
        "cannot be evaluated reliably."
    )


# ============================================================
# Building Trading Recommendation
# ============================================================

def build_building_recommendation(
    building_state: str,
):
    if (
        building_state
        == "Export Ready"
    ):
        return (
            "Projected solar generation "
            "exceeds projected building "
            "consumption. Export may be "
            "considered under the configured "
            "prototype market scenario."
        )

    if (
        building_state
        == "Balanced"
    ):
        return (
            "Projected generation and "
            "consumption are nearly balanced. "
            "Additional surplus is needed "
            "before meaningful export."
        )

    if (
        building_state
        == "Deficit"
    ):
        return (
            "Projected building consumption "
            "exceeds projected solar "
            "generation. Reduce consumption "
            "before considering energy export."
        )

    return (
        "Solar forecast is unavailable, "
        "therefore trading readiness cannot "
        "currently be evaluated."
    )


# ============================================================
# Trading Readiness Score
#
# This is a planning heuristic, not a market or financial
# rating.
# ============================================================

def calculate_trading_readiness_score(
    projected_consumption_kwh: float,
    projected_solar_kwh: float,
    projected_net_kwh: float,
    solar_available: bool,
):
    if not solar_available:
        return 0

    if (
        projected_consumption_kwh
        <= 0
    ):
        if projected_solar_kwh > 0:
            return 100

        return 0

    solar_coverage_ratio = (
        projected_solar_kwh
        / projected_consumption_kwh
    )

    # --------------------------------------------------------
    # Export-ready
    # --------------------------------------------------------

    if (
        projected_net_kwh
        > BALANCE_TOLERANCE_KWH
    ):
        surplus_ratio = (
            projected_net_kwh
            / projected_consumption_kwh
        )

        score = (
            70
            + min(
                surplus_ratio,
                1.0,
            )
            * 30
        )

        return min(
            100,
            round(
                score
            ),
        )

    # --------------------------------------------------------
    # Balanced
    # --------------------------------------------------------

    if (
        abs(
            projected_net_kwh
        )
        <= BALANCE_TOLERANCE_KWH
    ):
        return 65

    # --------------------------------------------------------
    # Deficit
    #
    # Higher solar coverage gives a better readiness score,
    # but deficit state remains below export-ready range.
    # --------------------------------------------------------

    score = (
        solar_coverage_ratio
        * 60
    )

    return max(
        0,
        min(
            59,
            round(
                score
            ),
        ),
    )


# ============================================================
# Trading Readiness Level
# ============================================================

def get_trading_readiness_level(
    building_state: str,
):
    if (
        building_state
        == "Export Ready"
    ):
        return "High"

    if (
        building_state
        == "Balanced"
    ):
        return "Medium"

    if (
        building_state
        == "Deficit"
    ):
        return "Low"

    return "Unavailable"


# ============================================================
# Build Market Scenarios
# ============================================================

def build_market_scenarios(
    exportable_surplus_kwh: float,
):
    scenarios = [
        {
            "scenario_name":
                "Base Market",

            "sell_price_per_kwh":
                BASE_MARKET_PRICE,

            # Compatibility field.
            "sell_price":
                BASE_MARKET_PRICE,

            "currency":
                MARKET_CURRENCY,

            "price_type":
                "prototype_scenario",

            "is_live_market_price":
                False,

            "total_surplus_energy":
                round(
                    exportable_surplus_kwh,
                    3,
                ),

            "estimated_revenue":
                round(
                    exportable_surplus_kwh
                    * BASE_MARKET_PRICE,
                    2,
                ),
        },
        {
            "scenario_name":
                "Peak Pricing",

            "sell_price_per_kwh":
                PEAK_MARKET_PRICE,

            # Compatibility field.
            "sell_price":
                PEAK_MARKET_PRICE,

            "currency":
                MARKET_CURRENCY,

            "price_type":
                "prototype_scenario",

            "is_live_market_price":
                False,

            "total_surplus_energy":
                round(
                    exportable_surplus_kwh,
                    3,
                ),

            "estimated_revenue":
                round(
                    exportable_surplus_kwh
                    * PEAK_MARKET_PRICE,
                    2,
                ),
        },
    ]

    return scenarios


# ============================================================
# Main Energy Trading Result
# ============================================================

def build_energy_trading():
    load_profile = (
        get_recent_room_loads(
            window_minutes=
                LOAD_WINDOW_MINUTES
        )
    )

    solar = (
        get_energy_trading_solar_projection()
    )

    solar_available = bool(
        solar.get(
            "available",
            False,
        )
    )

    room_loads = (
        load_profile.get(
            "rooms",
            [],
        )
    )

    total_rooms = len(
        room_loads
    )

    total_system_solar_kwh = float(
        solar.get(
            "projected_solar_energy_kwh",
            0,
        )
        or 0
    )

    # ========================================================
    # Solar Allocation
    #
    # The project currently has one system-level solar model,
    # not individual room-level solar meters.
    #
    # For room-level analytical presentation, projected system
    # solar generation is distributed equally across rooms.
    # ========================================================

    solar_per_room_kwh = (
        total_system_solar_kwh
        / total_rooms
        if total_rooms
        else 0.0
    )

    rooms = []

    total_projected_consumption_kwh = 0.0

    for room in room_loads:
        room_id = (
            room.get(
                "room_id"
            )
        )

        average_power_kw = float(
            room.get(
                "average_power_kw",
                0,
            )
            or 0
        )

        reading_count = int(
            room.get(
                "reading_count",
                0,
            )
            or 0
        )

        # ----------------------------------------------------
        # Projected consumption for the next hour
        #
        # kWh = average power (kW) × hours
        # ----------------------------------------------------

        projected_consumption_kwh = (
            average_power_kw
            * PROJECTION_HOURS
        )

        projected_consumption_kwh = round(
            projected_consumption_kwh,
            3,
        )

        projected_solar_kwh = round(
            solar_per_room_kwh,
            3,
        )

        projected_net_kwh = round(
            projected_solar_kwh
            - projected_consumption_kwh,
            3,
        )

        trading_status = (
            determine_trading_status(
                projected_net_kwh,
                solar_available,
            )
        )

        exportable_room_surplus_kwh = (
            max(
                projected_net_kwh,
                0,
            )
            if solar_available
            else 0
        )

        room_estimated_revenue = round(
            exportable_room_surplus_kwh
            * BASE_MARKET_PRICE,
            2,
        )

        total_projected_consumption_kwh += (
            projected_consumption_kwh
        )

        rooms.append(
            {
                "room_id":
                    room_id,

                "average_power_kw":
                    round(
                        average_power_kw,
                        3,
                    ),

                "reading_count":
                    reading_count,

                "projection_hours":
                    PROJECTION_HOURS,

                "projected_consumption_kwh":
                    projected_consumption_kwh,

                "projected_solar_energy_kwh":
                    projected_solar_kwh,

                "projected_net_energy_kwh":
                    projected_net_kwh,

                # --------------------------------------------
                # Compatibility fields for the existing
                # mobile Energy Trading response.
                # --------------------------------------------

                "consumed_energy":
                    projected_consumption_kwh,

                "generated_energy":
                    projected_solar_kwh,

                "surplus_energy":
                    projected_net_kwh,

                "estimated_revenue":
                    room_estimated_revenue,

                "currency":
                    MARKET_CURRENCY,

                "revenue_price_basis":
                    "Base Market prototype scenario",

                "trading_status":
                    trading_status,

                "recommendation":
                    build_room_recommendation(
                        trading_status
                    ),

                "solar_allocation_type":
                    (
                        "estimated_equal_share"
                        if solar_available
                        else "unavailable"
                    ),
            }
        )

    # ========================================================
    # Building Totals
    # ========================================================

    total_projected_consumption_kwh = round(
        total_projected_consumption_kwh,
        3,
    )

    total_projected_solar_kwh = round(
        total_system_solar_kwh,
        3,
    )

    total_net_kwh = round(
        total_projected_solar_kwh
        - total_projected_consumption_kwh,
        3,
    )

    # ========================================================
    # Building State
    # ========================================================

    if not solar_available:
        building_energy_state = (
            "Forecast Unavailable"
        )

    elif (
        total_net_kwh
        > BALANCE_TOLERANCE_KWH
    ):
        building_energy_state = (
            "Export Ready"
        )

    elif (
        total_net_kwh
        < -BALANCE_TOLERANCE_KWH
    ):
        building_energy_state = (
            "Deficit"
        )

    else:
        building_energy_state = (
            "Balanced"
        )

    trading_readiness_level = (
        get_trading_readiness_level(
            building_energy_state
        )
    )

    trading_readiness_score = (
        calculate_trading_readiness_score(
            projected_consumption_kwh=
                total_projected_consumption_kwh,

            projected_solar_kwh=
                total_projected_solar_kwh,

            projected_net_kwh=
                total_net_kwh,

            solar_available=
                solar_available,
        )
    )

    exportable_surplus_kwh = (
        max(
            total_net_kwh,
            0,
        )
        if solar_available
        else 0
    )

    exportable_surplus_kwh = round(
        exportable_surplus_kwh,
        3,
    )

    estimated_revenue = round(
        exportable_surplus_kwh
        * BASE_MARKET_PRICE,
        2,
    )

    # ========================================================
    # Solar Coverage
    # ========================================================

    if (
        total_projected_consumption_kwh
        > 0
    ):
        solar_coverage_percent = round(
            (
                total_projected_solar_kwh
                / total_projected_consumption_kwh
            )
            * 100,
            1,
        )

    elif (
        total_projected_solar_kwh
        > 0
    ):
        solar_coverage_percent = 100.0

    else:
        solar_coverage_percent = 0.0

    # ========================================================
    # Market Scenarios
    # ========================================================

    scenarios = (
        build_market_scenarios(
            exportable_surplus_kwh
        )
    )

    # ========================================================
    # Response
    # ========================================================

    return {
        "status":
            "ok",

        "summary": {
            "building_energy_state":
                building_energy_state,

            "trading_readiness_level":
                trading_readiness_level,

            "trading_readiness_score":
                trading_readiness_score,

            "trading_readiness_score_type":
                "planning_heuristic",

            "recommendation":
                build_building_recommendation(
                    building_energy_state
                ),

            # --------------------------------------------
            # Projection context
            # --------------------------------------------

            "projection_hours":
                PROJECTION_HOURS,

            "load_window_minutes":
                load_profile.get(
                    "window_minutes"
                ),

            "load_reference_time":
                load_profile.get(
                    "reference_time"
                ),

            # --------------------------------------------
            # Solar context
            # --------------------------------------------

            "solar_forecast_available":
                solar_available,

            "solar_forecast_time":
                solar.get(
                    "forecast_time"
                ),

            "system_solar_power_kw":
                solar.get(
                    "system_solar_power_kw",
                    0,
                ),

            "panel_capacity_kw":
                solar.get(
                    "panel_capacity_kw"
                ),

            "system_efficiency":
                solar.get(
                    "system_efficiency"
                ),

            "solar_allocation_method":
                (
                    "equal_share_across_rooms"
                    if solar_available
                    else "unavailable"
                ),

            "solar_coverage_percent":
                solar_coverage_percent,

            # --------------------------------------------
            # Clear semantic fields
            # --------------------------------------------

            "total_average_power_kw":
                round(
                    sum(
                        float(
                            room.get(
                                "average_power_kw",
                                0,
                            )
                            or 0
                        )
                        for room in room_loads
                    ),
                    3,
                ),

            "projected_consumption_kwh":
                total_projected_consumption_kwh,

            "projected_solar_energy_kwh":
                total_projected_solar_kwh,

            "projected_net_energy_kwh":
                total_net_kwh,

            # --------------------------------------------
            # Compatibility fields
            # --------------------------------------------

            "total_consumed_energy":
                total_projected_consumption_kwh,

            "total_generated_energy":
                total_projected_solar_kwh,

            "total_net_surplus_energy":
                total_net_kwh,

            "exportable_surplus_energy":
                exportable_surplus_kwh,

            # --------------------------------------------
            # Revenue
            # --------------------------------------------

            "estimated_revenue":
                estimated_revenue,

            "currency":
                MARKET_CURRENCY,

            "revenue_price_per_kwh":
                BASE_MARKET_PRICE,

            "revenue_price_basis":
                "Base Market prototype scenario",

            "market_price_type":
                "prototype_scenario",

            "is_live_market_price":
                False,
        },

        "rooms":
            rooms,

        "scenarios":
            scenarios,

        "disclaimer": {
            "solar_generation":
                (
                    "Solar generation is a forecast "
                    "estimate derived from weather "
                    "radiation and the configured "
                    "prototype solar system."
                ),

            "room_solar_allocation":
                (
                    "Room-level solar values are "
                    "analytical estimates created by "
                    "equally allocating system-level "
                    "solar generation across rooms."
                ),

            "market_prices":
                (
                    "Market prices are prototype "
                    "scenario values and are not "
                    "live electricity market prices."
                ),

            "financial_use":
                (
                    "Estimated revenue is for "
                    "simulation and educational "
                    "planning only."
                ),
        },
    }