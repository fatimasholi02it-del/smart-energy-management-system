from datetime import datetime, timedelta

from sqlalchemy import func

from weather_service import get_weather_forecast
from solar_service import estimate_solar_power
from database import SessionLocal
import models


# ============================================================
# Weather / Solar Planning Context
# ============================================================

def get_planning_weather():
    weather_response = get_weather_forecast(
        forecast_hours=6
    )

    if (
        weather_response.get("status") != "ok"
        or not weather_response.get("hours")
    ):
        return {
            "forecast_time": None,
            "weather_condition": "Unknown",
            "cloud_percent": 0.0,
            "temperature": 0.0,
            "estimated_solar_generation": 0.0,
        }

    hours = weather_response.get(
        "hours",
        [],
    )

    first_hour = hours[0]

    estimated_solar_generation = round(
        sum(
            estimate_solar_power(
                float(
                    hour.get(
                        "shortwave_radiation_wm2"
                    )
                    or 0
                )
            )
            for hour in hours
        ),
        2,
    )

    return {
        "forecast_time": first_hour.get(
            "forecast_time"
        ),
        "weather_condition": first_hour.get(
            "weather_condition",
            "Unknown",
        ),
        "cloud_percent": float(
            first_hour.get("cloud_percent")
            or 0
        ),
        "temperature": float(
            first_hour.get("temperature")
            or 0
        ),
        "estimated_solar_generation":
            estimated_solar_generation,
    }


# ============================================================
# Current System Load
# ============================================================

def get_current_consumption(
    minutes: int = 1440,
):
    db = SessionLocal()

    try:
        since_time = (
            datetime.now()
            - timedelta(
                minutes=minutes
            )
        )

        avg_energy = (
            db.query(
                func.avg(
                    models.EnergyReading.energy
                )
            )
            .filter(
                models.EnergyReading.timestamp
                >= since_time
            )
            .scalar()
        )

        return round(
            float(
                avg_energy or 0
            ),
            2,
        )

    except Exception as e:
        print(
            "Database error in "
            f"get_current_consumption: {e}"
        )

        return 3.0

    finally:
        db.close()


# ============================================================
# Top Consumer
# ============================================================

def get_top_consumer(
    minutes: int = 1440,
):
    db = SessionLocal()

    try:
        since_time = (
            datetime.now()
            - timedelta(
                minutes=minutes
            )
        )

        rows = (
            db.query(
                models.EnergyReading.room_id,
                func.avg(
                    models.EnergyReading.energy
                ).label(
                    "avg_energy"
                ),
            )
            .filter(
                models.EnergyReading.timestamp
                >= since_time
            )
            .group_by(
                models.EnergyReading.room_id
            )
            .all()
        )

        if not rows:
            return {
                "room_id": "-",
                "average_energy": 0.0,
            }

        top = max(
            rows,
            key=lambda r: float(
                r.avg_energy or 0
            ),
        )

        return {
            "room_id": top.room_id,
            "average_energy": round(
                float(
                    top.avg_energy or 0
                ),
                2,
            ),
        }

    except Exception as e:
        print(
            "Database error in "
            f"get_top_consumer: {e}"
        )

        return {
            "room_id": "room_1",
            "average_energy": 3.0,
        }

    finally:
        db.close()


# ============================================================
# Room Load Data
# ============================================================

def get_room_consumptions(
    minutes: int = 1440,
):
    db = SessionLocal()

    try:
        since_time = (
            datetime.now()
            - timedelta(
                minutes=minutes
            )
        )

        rows = (
            db.query(
                models.EnergyReading.room_id,
                func.avg(
                    models.EnergyReading.energy
                ).label(
                    "avg_energy"
                ),
            )
            .filter(
                models.EnergyReading.timestamp
                >= since_time
            )
            .group_by(
                models.EnergyReading.room_id
            )
            .all()
        )

        result = []

        for row in rows:
            result.append(
                {
                    "room_id":
                        row.room_id,
                    "average_energy":
                        round(
                            float(
                                row.avg_energy
                                or 0
                            ),
                            2,
                        ),
                }
            )

        return result

    except Exception as e:
        print(
            "Database error in "
            f"get_room_consumptions: {e}"
        )

        return [
            {
                "room_id": "room_1",
                "average_energy": 3.0,
            },
            {
                "room_id": "room_2",
                "average_energy": 2.6,
            },
            {
                "room_id": "room_3",
                "average_energy": 4.1,
            },
        ]

    finally:
        db.close()


# ============================================================
# Estimated Battery Readiness
#
# Important:
# This is currently a planning estimate derived from the
# current load profile. It is NOT a physical battery SOC
# measurement.
# ============================================================

def get_battery_state(
    current_consumption: float,
):
    if current_consumption >= 4.5:
        battery_percentage = 18

    elif current_consumption >= 3.0:
        battery_percentage = 25

    else:
        battery_percentage = 35

    if battery_percentage < 20:
        battery_status = "Critical"

    elif battery_percentage < 30:
        battery_status = "Low"

    else:
        battery_status = "Acceptable"

    return {
        "battery_percentage":
            battery_percentage,
        "battery_status":
            battery_status,
    }


# ============================================================
# Planning Score
# ============================================================

def compute_planning_score(
    avg_energy: float,
    battery_percentage: int,
    cloud_percent: int,
):
    score = 100

    # Load impact
    if avg_energy >= 4.0:
        score -= 35

    elif avg_energy >= 3.0:
        score -= 20

    else:
        score -= 5

    # Estimated battery readiness impact
    if battery_percentage < 20:
        score -= 30

    elif battery_percentage < 30:
        score -= 15

    else:
        score -= 5

    # Weather / solar impact
    if cloud_percent > 60:
        score -= 20

    elif cloud_percent > 40:
        score -= 10

    if score < 0:
        score = 0

    return score


# ============================================================
# Priority
# ============================================================

def compute_priority_level(
    score: int,
):
    if score < 40:
        return "High"

    elif score < 70:
        return "Medium"

    return "Low"


# ============================================================
# Decision Reasons
# ============================================================

def build_decision_reasons(
    room_id: str,
    avg_energy: float,
    weather: dict,
    battery: dict,
):
    reasons = []

    cloud_percent = weather.get(
        "cloud_percent",
        0,
    )

    battery_percentage = battery.get(
        "battery_percentage",
        0,
    )

    weather_condition = weather.get(
        "weather_condition",
        "Unknown",
    )

    # --------------------------------------------------------
    # Estimated battery readiness
    # --------------------------------------------------------

    if battery_percentage < 30:
        reasons.append(
            "Estimated battery readiness "
            f"is relatively low at "
            f"{battery_percentage}%."
        )

    else:
        reasons.append(
            "Estimated battery readiness "
            f"is acceptable at "
            f"{battery_percentage}%."
        )

    # --------------------------------------------------------
    # Upcoming weather forecast
    # --------------------------------------------------------

    if cloud_percent > 50:
        reasons.append(
            "Upcoming forecast is "
            f"{weather_condition} with "
            "cloud cover around "
            f"{cloud_percent}%, which may "
            "reduce solar availability."
        )

    else:
        reasons.append(
            "Upcoming forecast is "
            f"{weather_condition} with "
            "low cloud cover "
            f"({cloud_percent}%), which "
            "supports stronger solar "
            "availability."
        )

    # --------------------------------------------------------
    # Current load
    # --------------------------------------------------------

    if avg_energy >= 4.0:
        reasons.append(
            f"{room_id} is currently "
            "operating at high power load "
            f"({avg_energy} kW)."
        )

    elif avg_energy >= 3.0:
        reasons.append(
            f"{room_id} is operating at "
            "moderate power load "
            f"({avg_energy} kW)."
        )

    else:
        reasons.append(
            f"{room_id} is currently "
            "within a comfortable power "
            f"load range ({avg_energy} kW)."
        )

    return reasons


# ============================================================
# Individual Room Planning
# ============================================================

def evaluate_room_plan(
    room_id: str,
    avg_energy: float,
    weather: dict,
    battery: dict,
):
    cloud_percent = weather.get(
        "cloud_percent",
        0,
    )

    battery_percentage = battery.get(
        "battery_percentage",
        0,
    )

    planning_status = "Safe"
    battery_risk_level = "Low"
    risk_level = "Low"

    recommendation = (
        "Normal usage is acceptable."
    )

    suggested_action = (
        "Maintain regular usage."
    )

    recommended_device_action = (
        "No special action needed"
    )

    best_time_hint = (
        "Usage timing is flexible"
    )

    # ========================================================
    # High Load
    # ========================================================

    if avg_energy >= 4.0:
        if (
            battery_percentage < 30
            and cloud_percent > 50
        ):
            risk_level = "High"

            planning_status = (
                "Attention Needed"
            )

            battery_risk_level = "High"

            recommendation = (
                f"{room_id} is operating "
                "at high load while "
                "estimated battery readiness "
                "is limited and upcoming "
                "solar availability may be "
                "reduced."
            )

            suggested_action = (
                "Reduce HVAC load and "
                "postpone optional heavy "
                "devices where possible."
            )

            recommended_device_action = (
                "Reduce HVAC and delay "
                "heavy loads"
            )

            best_time_hint = (
                "Prefer heavy loads during "
                "periods with stronger "
                "solar availability"
            )

        else:
            risk_level = "High"

            planning_status = (
                "Monitor Usage"
            )

            battery_risk_level = "Medium"

            recommendation = (
                f"{room_id} has high power "
                "load and should be "
                "monitored closely."
            )

            suggested_action = (
                "Avoid unnecessary "
                "high-load devices."
            )

            recommended_device_action = (
                "Avoid high-load devices"
            )

            best_time_hint = (
                "Prefer heavy loads when "
                "solar availability is "
                "stronger"
            )

    # ========================================================
    # Moderate Load
    # ========================================================

    elif avg_energy >= 3.0:
        risk_level = "Medium"

        planning_status = (
            "Monitor Usage"
        )

        battery_risk_level = (
            "Medium"
            if battery_percentage < 30
            else "Low"
        )

        recommendation = (
            f"{room_id} is operating at "
            "moderate power load. "
            "Controlled usage is "
            "recommended."
        )

        suggested_action = (
            "Keep only necessary devices "
            "active and avoid sudden "
            "load spikes."
        )

        recommended_device_action = (
            "Delay optional devices"
        )

        best_time_hint = (
            "Prefer optional loads during "
            "periods with better solar "
            "availability"
        )

    # ========================================================
    # Low Load
    # ========================================================

    else:
        risk_level = "Low"

        planning_status = "Safe"

        battery_risk_level = "Low"

        recommendation = (
            f"{room_id} is within a "
            "comfortable power load range."
        )

        suggested_action = (
            "Normal usage is acceptable."
        )

        recommended_device_action = (
            "No action needed"
        )

        best_time_hint = (
            "Usage timing is flexible"
        )

    planning_score = compute_planning_score(
        avg_energy,
        battery_percentage,
        cloud_percent,
    )

    priority_level = (
        compute_priority_level(
            planning_score
        )
    )

    decision_reasons = (
        build_decision_reasons(
            room_id,
            avg_energy,
            weather,
            battery,
        )
    )

    return {
        "room_id":
            room_id,
        "average_energy":
            avg_energy,
        "risk_level":
            risk_level,
        "planning_status":
            planning_status,
        "battery_risk_level":
            battery_risk_level,
        "planning_score":
            planning_score,
        "priority_level":
            priority_level,
        "decision_reasons":
            decision_reasons,
        "recommendation":
            recommendation,
        "suggested_action":
            suggested_action,
        "recommended_device_action":
            recommended_device_action,
        "best_time_hint":
            best_time_hint,
    }


# ============================================================
# Room Planning Collection
# ============================================================

def build_room_plans():
    weather = get_planning_weather()

    current_consumption = (
        get_current_consumption()
    )

    battery = get_battery_state(
        current_consumption
    )

    room_consumptions = (
        get_room_consumptions()
    )

    if not room_consumptions:
        room_consumptions = [
            {
                "room_id": "room_1",
                "average_energy": 3.0,
            },
            {
                "room_id": "room_2",
                "average_energy": 2.6,
            },
            {
                "room_id": "room_3",
                "average_energy": 4.1,
            },
        ]

    room_plans = [
        evaluate_room_plan(
            room["room_id"],
            room["average_energy"],
            weather,
            battery,
        )
        for room in room_consumptions
    ]

    room_plans = sorted(
        room_plans,
        key=lambda x: x[
            "average_energy"
        ],
        reverse=True,
    )

    return {
        "status": "ok",
        "weather_condition":
            weather.get(
                "weather_condition"
            ),
        "cloud_percent":
            weather.get(
                "cloud_percent"
            ),
        "temperature":
            weather.get(
                "temperature"
            ),
        "estimated_solar_generation":
            weather.get(
                "estimated_solar_generation"
            ),
        "battery_percentage":
            battery.get(
                "battery_percentage"
            ),
        "battery_status":
            battery.get(
                "battery_status"
            ),
        "battery_estimate": True,
        "rooms":
            room_plans,
    }


# ============================================================
# Main Smart Planning Result
# ============================================================

def build_smart_plan():
    weather = get_planning_weather()

    current_consumption = (
        get_current_consumption()
    )

    top_consumer = (
        get_top_consumer()
    )

    battery = get_battery_state(
        current_consumption
    )

    cloud_percent = weather.get(
        "cloud_percent",
        0,
    )

    battery_percentage = battery.get(
        "battery_percentage",
        0,
    )

    planning_status = "Safe"

    battery_risk_level = "Low"

    recommended_device_action = (
        "Keep normal usage"
    )

    best_time_hint = (
        "Usage timing is flexible"
    )

    # ========================================================
    # Very Low Battery Readiness + Heavy Cloud
    # ========================================================

    if (
        battery_percentage < 20
        and cloud_percent > 60
    ):
        risk_level = "High"

        planning_status = (
            "Critical Planning Needed"
        )

        battery_risk_level = "High"

        recommendation = (
            "Estimated battery readiness "
            "is very low and the upcoming "
            "forecast indicates weaker "
            "solar availability. "
            "Consumption should be reduced."
        )

        suggested_action = (
            "Use only essential devices "
            "and avoid non-essential "
            "heavy loads."
        )

        recommended_device_action = (
            "Turn off non-essential devices"
        )

        best_time_hint = (
            "Delay heavy loads until solar "
            "availability improves"
        )

    # ========================================================
    # Low Battery Readiness + Cloudy Forecast
    # ========================================================

    elif (
        battery_percentage < 30
        and cloud_percent > 50
    ):
        risk_level = "Medium"

        planning_status = (
            "Attention Needed"
        )

        battery_risk_level = "Medium"

        recommendation = (
            "Estimated battery readiness "
            "is low and the upcoming "
            "forecast may reduce solar "
            "availability. Moderate "
            "consumption is recommended."
        )

        suggested_action = (
            "Delay non-essential devices "
            "and reduce cooling or heating "
            "loads where possible."
        )

        recommended_device_action = (
            "Delay non-essential devices"
        )

        best_time_hint = (
            "Prefer heavier loads during "
            "periods with stronger solar "
            "availability"
        )

    # ========================================================
    # Low Battery Readiness + Favorable Weather
    # ========================================================

    elif (
        battery_percentage < 30
        and cloud_percent <= 50
    ):
        risk_level = "Medium"

        planning_status = (
            "Monitor Usage"
        )

        battery_risk_level = "Medium"

        recommendation = (
            "Estimated battery readiness "
            "is low, but upcoming weather "
            "conditions support useful "
            "solar generation. Moderate "
            "consumption is recommended."
        )

        suggested_action = (
            "Use only necessary devices "
            "and avoid unnecessary "
            "high-load appliances."
        )

        recommended_device_action = (
            "Avoid high-load devices"
        )

        best_time_hint = (
            "Prefer heavier loads during "
            "periods with stronger solar "
            "availability"
        )

    # ========================================================
    # Acceptable Battery Readiness + Cloudy Forecast
    # ========================================================

    elif (
        battery_percentage >= 30
        and cloud_percent > 60
    ):
        risk_level = "Medium"

        planning_status = (
            "Watch Forecast"
        )

        battery_risk_level = "Low"

        recommendation = (
            "Estimated battery readiness "
            "is acceptable, but the "
            "upcoming forecast indicates "
            "reduced solar availability. "
            "Energy use should be "
            "optimized."
        )

        suggested_action = (
            "Keep essential loads active "
            "and postpone optional "
            "high-energy devices."
        )

        recommended_device_action = (
            "Postpone optional heavy loads"
        )

        best_time_hint = (
            "Prefer optional loads when "
            "solar availability improves"
        )

    # ========================================================
    # Favorable Conditions
    # ========================================================

    else:
        risk_level = "Low"

        planning_status = "Safe"

        battery_risk_level = "Low"

        recommendation = (
            "Estimated battery readiness "
            "and upcoming weather "
            "conditions are favorable. "
            "The current consumption "
            "pattern is acceptable."
        )

        suggested_action = (
            "Maintain normal usage while "
            "continuing to monitor major "
            "loads."
        )

        recommended_device_action = (
            "Normal usage is acceptable"
        )

        best_time_hint = (
            "Current forecast conditions "
            "support flexible usage"
        )

    planning_score = (
        compute_planning_score(
            current_consumption,
            battery_percentage,
            cloud_percent,
        )
    )

    priority_level = (
        compute_priority_level(
            planning_score
        )
    )

    decision_reasons = (
        build_decision_reasons(
            top_consumer.get(
                "room_id",
                "system",
            ),
            float(
                top_consumer.get(
                    "average_energy",
                    current_consumption,
                )
                or current_consumption
            ),
            weather,
            battery,
        )
    )

    return {
        "status":
            "ok",

        "forecast_time":
            weather.get(
                "forecast_time"
            ),

        "forecast_horizon_hours":
            6,

        "weather_condition":
            weather.get(
                "weather_condition"
            ),

        "cloud_percent":
            weather.get(
                "cloud_percent"
            ),

        "temperature":
            weather.get(
                "temperature"
            ),

        "estimated_solar_generation":
            weather.get(
                "estimated_solar_generation"
            ),

        # ----------------------------------------------------
        # Compatibility fields used by current Flutter app.
        # This value is a planning estimate, not measured SOC.
        # ----------------------------------------------------

        "battery_percentage":
            battery_percentage,

        "battery_status":
            battery.get(
                "battery_status"
            ),

        "battery_estimate":
            True,

        "battery_estimate_note":
            (
                "Planning estimate derived "
                "from the current load "
                "profile; not a physical "
                "battery measurement."
            ),

        "battery_risk_level":
            battery_risk_level,

        "planning_status":
            planning_status,

        "planning_score":
            planning_score,

        "priority_level":
            priority_level,

        "decision_reasons":
            decision_reasons,

        "current_consumption":
            current_consumption,

        "top_consumer":
            top_consumer,

        "risk_level":
            risk_level,

        "recommendation":
            recommendation,

        "suggested_action":
            suggested_action,

        "recommended_device_action":
            recommended_device_action,

        "best_time_hint":
            best_time_hint,
    }


# ============================================================
# Compact Recommendations API
# ============================================================

def build_planning_recommendations():
    room_plans = build_room_plans()

    rooms = room_plans.get(
        "rooms",
        [],
    )

    recommendations = []

    for room in rooms:
        recommendations.append(
            {
                "room_id":
                    room["room_id"],

                "recommendation":
                    room[
                        "recommended_device_action"
                    ],

                "status_level":
                    room[
                        "risk_level"
                    ],

                "reason":
                    room[
                        "planning_status"
                    ],

                "best_time_hint":
                    room[
                        "best_time_hint"
                    ],
            }
        )

    return {
        "status": "ok",
        "recommendations":
            recommendations,
    }


# ============================================================
# Smart Planning Health
# ============================================================

def build_planning_health():
    room_plans = build_room_plans()

    smart_plan = build_smart_plan()

    return {
        "status":
            "ok",

        "smart_planning_available":
            True,

        "room_planning_count":
            len(
                room_plans.get(
                    "rooms",
                    [],
                )
            ),

        "weather_available":
            smart_plan.get(
                "weather_condition"
            )
            is not None,

        "forecast_horizon_hours":
            smart_plan.get(
                "forecast_horizon_hours"
            ),

        "battery_status":
            smart_plan.get(
                "battery_status"
            ),

        "battery_estimate":
            True,

        "top_consumer":
            smart_plan.get(
                "top_consumer",
                {},
            ).get(
                "room_id"
            ),

        "planning_score":
            smart_plan.get(
                "planning_score"
            ),

        "priority_level":
            smart_plan.get(
                "priority_level"
            ),
    }