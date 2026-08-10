from weather_service import get_weather_forecast
from database import SessionLocal
import models
from sqlalchemy import func
from datetime import datetime, timedelta


def get_current_consumption(minutes: int = 1440):
    db = SessionLocal()
    try:
        since_time = datetime.now() - timedelta(minutes=minutes)

        avg_energy = (
            db.query(func.avg(models.EnergyReading.energy))
            .filter(models.EnergyReading.timestamp >= since_time)
            .scalar()
        )

        return round(float(avg_energy or 0), 2)

    except Exception as e:
        print(f"Database error in get_current_consumption: {e}")
        return 3.0

    finally:
        db.close()


def get_top_consumer(minutes: int = 1440):
    db = SessionLocal()
    try:
        since_time = datetime.now() - timedelta(minutes=minutes)

        rows = (
            db.query(
                models.EnergyReading.room_id,
                func.avg(models.EnergyReading.energy).label("avg_energy"),
            )
            .filter(models.EnergyReading.timestamp >= since_time)
            .group_by(models.EnergyReading.room_id)
            .all()
        )

        if not rows:
            return {"room_id": "-", "average_energy": 0.0}

        top = max(rows, key=lambda r: float(r.avg_energy or 0))
        return {
            "room_id": top.room_id,
            "average_energy": round(float(top.avg_energy or 0), 2),
        }

    except Exception as e:
        print(f"Database error in get_top_consumer: {e}")
        return {"room_id": "room_1", "average_energy": 3.0}

    finally:
        db.close()


def get_room_consumptions(minutes: int = 1440):
    db = SessionLocal()
    try:
        since_time = datetime.now() - timedelta(minutes=minutes)

        rows = (
            db.query(
                models.EnergyReading.room_id,
                func.avg(models.EnergyReading.energy).label("avg_energy"),
            )
            .filter(models.EnergyReading.timestamp >= since_time)
            .group_by(models.EnergyReading.room_id)
            .all()
        )

        result = []
        for row in rows:
            result.append({
                "room_id": row.room_id,
                "average_energy": round(float(row.avg_energy or 0), 2)
            })

        return result

    except Exception as e:
        print(f"Database error in get_room_consumptions: {e}")
        return [
            {"room_id": "room_1", "average_energy": 3.0},
            {"room_id": "room_2", "average_energy": 2.6},
            {"room_id": "room_3", "average_energy": 4.1},
        ]

    finally:
        db.close()


def get_battery_state(current_consumption: float):
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
        "battery_percentage": battery_percentage,
        "battery_status": battery_status
    }


def compute_planning_score(avg_energy: float, battery_percentage: int, cloud_percent: int):
    score = 100

    if avg_energy >= 4.0:
        score -= 35
    elif avg_energy >= 3.0:
        score -= 20
    else:
        score -= 5

    if battery_percentage < 20:
        score -= 30
    elif battery_percentage < 30:
        score -= 15
    else:
        score -= 5

    if cloud_percent > 60:
        score -= 20
    elif cloud_percent > 40:
        score -= 10
    else:
        score -= 0

    if score < 0:
        score = 0
    return score


def compute_priority_level(score: int):
    if score < 40:
        return "High"
    elif score < 70:
        return "Medium"
    return "Low"


def build_decision_reasons(room_id: str, avg_energy: float, weather: dict, battery: dict):
    reasons = []

    cloud_percent = weather.get("cloud_percent", 0)
    battery_percentage = battery.get("battery_percentage", 0)
    weather_condition = weather.get("weather_condition", "Unknown")

    if battery_percentage < 30:
        reasons.append(f"Battery is relatively low at {battery_percentage}%.")

    if cloud_percent > 50:
        reasons.append(
            f"Tomorrow weather is {weather_condition} with cloud cover around {cloud_percent}%, which may reduce solar efficiency."
        )
    else:
        reasons.append(
            f"Tomorrow weather is {weather_condition} with low cloud cover ({cloud_percent}%), which supports better solar generation."
        )

    if avg_energy >= 4.0:
        reasons.append(f"{room_id} is currently operating at high energy usage ({avg_energy}).")
    elif avg_energy >= 3.0:
        reasons.append(f"{room_id} is operating at moderate energy usage ({avg_energy}).")
    else:
        reasons.append(f"{room_id} is within a comfortable energy range ({avg_energy}).")

    return reasons


def evaluate_room_plan(room_id: str, avg_energy: float, weather: dict, battery: dict):
    cloud_percent = weather.get("cloud_percent", 0)
    battery_percentage = battery.get("battery_percentage", 0)

    planning_status = "Safe"
    battery_risk_level = "Low"
    risk_level = "Low"
    recommendation = "Normal usage is acceptable."
    suggested_action = "Maintain regular usage."
    recommended_device_action = "No special action needed"
    best_time_hint = "Any time is acceptable"

    if avg_energy >= 4.0:
        if battery_percentage < 30 and cloud_percent > 50:
            risk_level = "High"
            planning_status = "Attention Needed"
            battery_risk_level = "High"
            recommendation = (
                f"{room_id} is consuming heavily while battery is limited and tomorrow solar generation may be weaker."
            )
            suggested_action = "Reduce HVAC load and postpone any optional heavy devices."
            recommended_device_action = "Reduce HVAC and delay heavy loads"
            best_time_hint = "Use heavy devices after sunrise if possible"
        else:
            risk_level = "High"
            planning_status = "Monitor Usage"
            battery_risk_level = "Medium"
            recommendation = f"{room_id} has high consumption and should be monitored closely."
            suggested_action = "Avoid unnecessary high-load devices tonight."
            recommended_device_action = "Avoid high-load devices"
            best_time_hint = "Morning usage is more acceptable than late night"

    elif avg_energy >= 3.0:
        risk_level = "Medium"
        planning_status = "Monitor Usage"
        battery_risk_level = "Medium" if battery_percentage < 30 else "Low"
        recommendation = f"{room_id} is operating at moderate load. Controlled usage is recommended."
        suggested_action = "Keep only necessary devices active and avoid spikes."
        recommended_device_action = "Delay optional devices"
        best_time_hint = "Prefer medium-load usage during daylight hours"

    else:
        risk_level = "Low"
        planning_status = "Safe"
        battery_risk_level = "Low"
        recommendation = f"{room_id} is within a comfortable usage range."
        suggested_action = "Normal usage is acceptable."
        recommended_device_action = "No action needed"
        best_time_hint = "Usage timing is flexible"

    planning_score = compute_planning_score(avg_energy, battery_percentage, cloud_percent)
    priority_level = compute_priority_level(planning_score)
    decision_reasons = build_decision_reasons(room_id, avg_energy, weather, battery)

    return {
        "room_id": room_id,
        "average_energy": avg_energy,
        "risk_level": risk_level,
        "planning_status": planning_status,
        "battery_risk_level": battery_risk_level,
        "planning_score": planning_score,
        "priority_level": priority_level,
        "decision_reasons": decision_reasons,
        "recommendation": recommendation,
        "suggested_action": suggested_action,
        "recommended_device_action": recommended_device_action,
        "best_time_hint": best_time_hint,
    }


def build_room_plans():
    weather = get_weather_forecast()
    current_consumption = get_current_consumption()
    battery = get_battery_state(current_consumption)
    room_consumptions = get_room_consumptions()

    if not room_consumptions:
        room_consumptions = [
            {"room_id": "room_1", "average_energy": 3.0},
            {"room_id": "room_2", "average_energy": 2.6},
            {"room_id": "room_3", "average_energy": 4.1},
        ]

    room_plans = [
        evaluate_room_plan(
            room["room_id"],
            room["average_energy"],
            weather,
            battery
        )
        for room in room_consumptions
    ]

    room_plans = sorted(
        room_plans,
        key=lambda x: x["average_energy"],
        reverse=True
    )

    return {
        "status": "ok",
        "weather_condition": weather.get("weather_condition"),
        "cloud_percent": weather.get("cloud_percent"),
        "temperature": weather.get("temperature"),
        "estimated_solar_generation": weather.get("estimated_solar_generation"),
        "battery_percentage": battery.get("battery_percentage"),
        "battery_status": battery.get("battery_status"),
        "rooms": room_plans,
    }


def build_smart_plan():
    weather = get_weather_forecast()
    current_consumption = get_current_consumption()
    top_consumer = get_top_consumer()
    battery = get_battery_state(current_consumption)

    cloud_percent = weather.get("cloud_percent", 0)
    battery_percentage = battery.get("battery_percentage", 0)

    planning_status = "Safe"
    battery_risk_level = "Low"
    recommended_device_action = "Keep normal usage"
    best_time_hint = "Any time is acceptable"

    if battery_percentage < 20 and cloud_percent > 60:
        risk_level = "High"
        planning_status = "Critical Planning Needed"
        battery_risk_level = "High"
        recommendation = (
            "Battery is very low and tomorrow solar generation is expected to be weak. "
            "You should reduce night consumption immediately."
        )
        suggested_action = (
            "Use only essential devices and avoid all non-essential heavy loads tonight."
        )
        recommended_device_action = "Turn off non-essential devices"
        best_time_hint = "Delay heavy loads until solar conditions improve"

    elif battery_percentage < 30 and cloud_percent > 50:
        risk_level = "Medium"
        planning_status = "Attention Needed"
        battery_risk_level = "Medium"
        recommendation = (
            "Battery is low and tomorrow weather may reduce solar generation. "
            "Moderate consumption is recommended."
        )
        suggested_action = (
            "Delay non-essential devices and reduce cooling or heating loads where possible."
        )
        recommended_device_action = "Delay non-essential devices"
        best_time_hint = "Use heavier loads after sunrise if weather improves"

    elif battery_percentage < 30 and cloud_percent <= 50:
        risk_level = "Medium"
        planning_status = "Monitor Usage"
        battery_risk_level = "Medium"
        recommendation = (
            "Battery is low, but tomorrow weather is acceptable. "
            "Moderate night consumption is recommended."
        )
        suggested_action = (
            "Use only necessary devices tonight and avoid high-load appliances."
        )
        recommended_device_action = "Avoid high-load devices"
        best_time_hint = "Morning usage is more acceptable than late night"

    elif battery_percentage >= 30 and cloud_percent > 60:
        risk_level = "Medium"
        planning_status = "Watch Forecast"
        battery_risk_level = "Low"
        recommendation = (
            "Battery level is acceptable, but tomorrow may be cloudy. "
            "It is better to optimize energy use tonight."
        )
        suggested_action = (
            "Keep essential loads active and postpone optional high-energy devices."
        )
        recommended_device_action = "Postpone optional heavy loads"
        best_time_hint = "Prefer device usage after weather stabilizes"

    else:
        risk_level = "Low"
        planning_status = "Safe"
        battery_risk_level = "Low"
        recommendation = (
            "Battery level and weather forecast are favorable. "
            "Current consumption pattern is acceptable."
        )
        suggested_action = (
            "Maintain normal usage while continuing to monitor major loads."
        )
        recommended_device_action = "Normal usage is acceptable"
        best_time_hint = "Today and tomorrow usage conditions look good"

    planning_score = compute_planning_score(current_consumption, battery_percentage, cloud_percent)
    priority_level = compute_priority_level(planning_score)
    decision_reasons = build_decision_reasons(
        top_consumer.get("room_id", "system"),
        current_consumption,
        weather,
        battery
    )

    return {
        "status": "ok",
        "forecast_time": weather.get("forecast_time"),
        "weather_condition": weather.get("weather_condition"),
        "cloud_percent": weather.get("cloud_percent"),
        "temperature": weather.get("temperature"),
        "estimated_solar_generation": weather.get("estimated_solar_generation"),
        "battery_percentage": battery_percentage,
        "battery_status": battery.get("battery_status"),
        "battery_risk_level": battery_risk_level,
        "planning_status": planning_status,
        "planning_score": planning_score,
        "priority_level": priority_level,
        "decision_reasons": decision_reasons,
        "current_consumption": current_consumption,
        "top_consumer": top_consumer,
        "risk_level": risk_level,
        "recommendation": recommendation,
        "suggested_action": suggested_action,
        "recommended_device_action": recommended_device_action,
        "best_time_hint": best_time_hint,
    }


def build_planning_recommendations():
    room_plans = build_room_plans()
    rooms = room_plans.get("rooms", [])

    recommendations = []
    for room in rooms:
        recommendations.append({
            "room_id": room["room_id"],
            "recommendation": room["recommended_device_action"],
            "status_level": room["risk_level"],
            "reason": room["planning_status"],
            "best_time_hint": room["best_time_hint"],
        })

    return {
        "status": "ok",
        "recommendations": recommendations
    }


def build_planning_health():
    room_plans = build_room_plans()
    smart_plan = build_smart_plan()

    return {
        "status": "ok",
        "smart_planning_available": True,
        "room_planning_count": len(room_plans.get("rooms", [])),
        "weather_available": smart_plan.get("weather_condition") is not None,
        "battery_status": smart_plan.get("battery_status"),
        "top_consumer": smart_plan.get("top_consumer", {}).get("room_id"),
        "planning_score": smart_plan.get("planning_score"),
        "priority_level": smart_plan.get("priority_level"),
    }