import hmac
import hashlib

from datetime import datetime, timedelta
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session
from weather_service import get_weather_forecast
from solar_service import get_solar_forecast
from load_forecast_service import get_load_forecast
from energy_forecast_service import get_energy_forecast
from mpc_optimizer import optimize_energy_plan
from mpc_scenario_service import run_mpc_scenarios
from electricity_price_service import get_electricity_price_forecast
from alert_service import get_alerts
from device_service import get_devices
from energy_service import get_energy_history
from security_service import get_security_events
from alert_engine import generate_alerts
from live_power_service import get_live_power_summary
from energy_trading_service import build_energy_trading

from dashboard_service import (
    get_dashboard_status
)
from ai_recommendation_service import (
    generate_energy_recommendations
)
from battery_stress_scenario_service import (
    run_battery_stress_scenario
)
from fair_mpc_benchmark_service import (
    run_fair_mpc_benchmark
)
from battery_mpc_comparison_service import (
    compare_ml_battery_strategies
)
from battery_aware_ml_mpc import (
    optimize_battery_aware_ml_mpc
)
from ml_advanced_mpc_service import (
    optimize_ml_advanced_mpc
)
from ml_energy_forecast_service import (
    get_ml_energy_forecast
)
from ml_data_service import (
    get_ml_data_status
)
from ml_load_forecast_service import (
    get_ml_load_forecast
)
from anomaly_detection_service import (
    detect_energy_anomalies,
    get_current_ai_status
)
from economic_mpc_optimizer import (
    optimize_economic_energy_plan
)
from advanced_economic_mpc import (
    optimize_advanced_economic_mpc
)
from optimization_comparison_service import (
    compare_optimization_models
)
from smart_planner import (
    build_smart_plan,
    build_room_plans,
    build_planning_recommendations,
    build_planning_health,
)

import models
from config import settings
from database import SessionLocal, engine


from contextlib import asynccontextmanager
from mqtt_consumer import start_mqtt_consumer



models.Base.metadata.create_all(bind=engine)


mqtt_client = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global mqtt_client

    try:
        print("Starting MQTT consumer...")

        mqtt_client = start_mqtt_consumer()

        print("MQTT consumer started")

    except Exception as e:
        mqtt_client = None
        print(f"MQTT consumer startup failed: {e}")

    yield

    if mqtt_client is not None:
        try:
            mqtt_client.loop_stop()
            mqtt_client.disconnect()
            print("MQTT consumer stopped")
        except Exception as e:
            print(f"MQTT consumer shutdown warning: {e}")

app = FastAPI(
    title="Smart Energy API",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class IngestReadingRequest(BaseModel):
    device_id: str
    room_id: str
    energy: float
    timestamp: str
    signature: str


def build_signing_string(payload: dict) -> str:
    return f"{payload['device_id']}|{payload['room_id']}|{payload['energy']}|{payload['timestamp']}"


def generate_expected_signature(payload: dict) -> str:
    signing_string = build_signing_string(payload)
    return hmac.new(
        settings.message_secret.encode(),
        signing_string.encode(),
        hashlib.sha256
    ).hexdigest()


def validate_http_reading(payload: dict):
    device_id = payload["device_id"]
    room_id = payload["room_id"]
    energy = payload["energy"]
    timestamp = payload["timestamp"]
    provided_signature = payload["signature"]

    if device_id not in settings.trusted_devices:
        raise HTTPException(status_code=400, detail=f"Unknown device_id: {device_id}")

    if room_id not in settings.allowed_rooms:
        raise HTTPException(status_code=400, detail=f"Unknown room_id: {room_id}")

    try:
        datetime.fromisoformat(timestamp)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid timestamp format: {timestamp}")

    min_energy, max_energy = settings.allowed_rooms[room_id]
    if not (min_energy <= energy <= max_energy):
        raise HTTPException(
            status_code=400,
            detail=f"Energy out of allowed range for {room_id}: {energy} not in [{min_energy}, {max_energy}]"
        )

    expected_signature = generate_expected_signature(payload)
    if not hmac.compare_digest(provided_signature, expected_signature):
        raise HTTPException(status_code=401, detail="Invalid message signature")


@app.post("/ingest/reading")
def ingest_reading(
    reading: IngestReadingRequest,
    x_api_key: str = Header(default="")
):
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    payload = reading.model_dump()
    validate_http_reading(payload)

    db: Session = SessionLocal()
    try:
        parsed_timestamp = datetime.fromisoformat(reading.timestamp)


        data_source = (
            "simulator"
            if reading.device_id.startswith(
                "simulator_"
            )
            else "sensor"
        )

        db_reading = models.EnergyReading(
            device_id=reading.device_id,
            room_id=reading.room_id,
            energy=reading.energy,
            timestamp=parsed_timestamp,
            data_source=data_source
        )
        db.add(db_reading)
        db.commit()
        db.refresh(db_reading)

        return {
            "status": "ok",
            "message": "Reading saved successfully",
            "id": db_reading.id,
            "room_id": db_reading.room_id,
            "energy": db_reading.energy,
            "timestamp": db_reading.timestamp.isoformat()
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


BUILDING_ROOM_MAP = {
    "building_1": {
        "name": "Main Tower",
        "rooms": ["room_1", "room_2"],
    },
    "building_2": {
        "name": "Smart Annex",
        "rooms": ["room_3"],
    },
}



@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "Smart Energy backend is running - render v2"
    }



def get_room_stats(minutes: int = 60):
    db = SessionLocal()

    try:
        since_time = (
            datetime.now()
            - timedelta(minutes=minutes)
        )

        rows = (
            db.query(models.EnergyReading)
            .filter(
                models.EnergyReading.timestamp
                >= since_time
            )
            .order_by(
                models.EnergyReading.room_id.asc(),
                models.EnergyReading.timestamp.asc(),
                models.EnergyReading.id.asc(),
            )
            .all()
        )

        readings_by_room = {}

        for row in rows:
            readings_by_room.setdefault(
                row.room_id,
                [],
            ).append(row)

        room_stats = {}

        tariff_per_kwh = 0.45

        # Do not integrate across long communication gaps.
        max_gap_seconds = 30

        for room_id, room_readings in (
            readings_by_room.items()
        ):
            power_values = []

            for reading in room_readings:
                power_kw = (
                    reading.power_kw
                    if reading.power_kw is not None
                    else reading.energy
                )

                power_values.append(
                    float(power_kw or 0)
                )

            reading_count = len(
                room_readings
            )

            average_power_kw = (
                sum(power_values)
                / reading_count
                if reading_count
                else 0
            )

            # =========================================
            # TRUE ENERGY CALCULATION
            #
            # kWh = kW × hours
            # Using trapezoidal integration
            # between consecutive readings.
            # =========================================

            total_energy_kwh = 0.0

            for index in range(
                1,
                reading_count,
            ):
                previous = (
                    room_readings[
                        index - 1
                    ]
                )

                current = (
                    room_readings[
                        index
                    ]
                )

                previous_time = (
                    previous.timestamp
                )

                current_time = (
                    current.timestamp
                )

                if (
                    previous_time is None
                    or current_time is None
                ):
                    continue

                delta_seconds = (
                    current_time
                    - previous_time
                ).total_seconds()

                if delta_seconds <= 0:
                    continue

                # Don't integrate across
                # long communication gaps.
                if (
                    delta_seconds
                    > max_gap_seconds
                ):
                    continue

                previous_power = (
                    previous.power_kw
                    if previous.power_kw
                    is not None
                    else previous.energy
                )

                current_power = (
                    current.power_kw
                    if current.power_kw
                    is not None
                    else current.energy
                )

                previous_power = float(
                    previous_power or 0
                )

                current_power = float(
                    current_power or 0
                )

                average_interval_power = (
                    previous_power
                    + current_power
                ) / 2.0

                delta_hours = (
                    delta_seconds
                    / 3600.0
                )

                total_energy_kwh += (
                    average_interval_power
                    * delta_hours
                )

            average_power_kw = round(
                average_power_kw,
                2,
            )

            total_energy_kwh = round(
                total_energy_kwh,
                6,
            )

            if average_power_kw >= 3.5:
                status_level = "High"

            elif average_power_kw >= 2.3:
                status_level = "Medium"

            else:
                status_level = "Low"

            estimated_cost = round(
                total_energy_kwh
                * tariff_per_kwh,
                4,
            )

            utilization_percent = min(
                100,
                round(
                    (
                        average_power_kw
                        / 5.0
                    )
                    * 100,
                    2,
                ),
            )

            last_seen = (
                room_readings[-1].timestamp
                if room_readings
                else None
            )

            room_stats[
                room_id
            ] = {
                "room_id":
                    room_id,

                # Compatibility with
                # existing Flutter / AI code.
                "average_energy":
                    average_power_kw,

                # Correct semantic field.
                "average_power_kw":
                    average_power_kw,

                "reading_count":
                    reading_count,

                # Keep existing key so
                # current Flutter screens work.
                "total_energy":
                    total_energy_kwh,

                "total_energy_kwh":
                    total_energy_kwh,

                "last_seen":
                    (
                        last_seen.isoformat()
                        if last_seen
                        else None
                    ),

                "status_level":
                    status_level,

                "estimated_cost":
                    estimated_cost,

                "utilization_percent":
                    utilization_percent,

                "window_minutes":
                    minutes,

                "tariff_per_kwh":
                    tariff_per_kwh,
            }

        # =============================================
        # Fill missing rooms
        # =============================================

        all_rooms = sorted(
            {
                room
                for building
                in BUILDING_ROOM_MAP.values()
                for room
                in building["rooms"]
            }
        )

        for room_id in all_rooms:
            room_stats.setdefault(
                room_id,
                {
                    "room_id":
                        room_id,

                    "average_energy":
                        0.0,

                    "average_power_kw":
                        0.0,

                    "reading_count":
                        0,

                    "total_energy":
                        0.0,

                    "total_energy_kwh":
                        0.0,

                    "last_seen":
                        None,

                    "status_level":
                        "No Data",

                    "estimated_cost":
                        0.0,

                    "utilization_percent":
                        0.0,

                    "window_minutes":
                        minutes,

                    "tariff_per_kwh":
                        tariff_per_kwh,
                },
            )

        return room_stats

    finally:
        db.close()

def build_buildings_summary(minutes: int = 60):
    room_stats = get_room_stats(minutes)
    buildings = []

    for building_id, info in BUILDING_ROOM_MAP.items():
        rooms = [room_stats[rid] for rid in info["rooms"]]
        room_count = len(rooms)
        total_energy = round(sum(r["total_energy"] for r in rooms), 2)
        avg_energy = round(
            sum(r["average_energy"] for r in rooms) / room_count if room_count else 0,
            2,
        )

        if avg_energy >= 3.5:
            status = "High Load"
        elif avg_energy >= 2.3:
            status = "Balanced"
        else:
            status = "Efficient"

        buildings.append(
            {
                "building_id": building_id,
                "name": info["name"],
                "room_count": room_count,
                "total_energy": total_energy,
                "average_energy": avg_energy,
                "status": status,
                "rooms": rooms,
            }
        )

    return buildings


@app.get("/mobile/home")
def mobile_home():
    room_stats = get_room_stats(minutes=60)
    rooms = list(room_stats.values())

    top_consumer = max(rooms, key=lambda r: r["average_energy"], default=None)
    total_cost = round(sum(r["estimated_cost"] for r in rooms), 4)

    high_risk_count = len([r for r in rooms if r["average_energy"] >= 3.5])
    medium_risk_count = len([r for r in rooms if 2.3 <= r["average_energy"] < 3.5])

    total_alerts = high_risk_count + medium_risk_count

    system_status = "Healthy"
    if high_risk_count > 0:
        system_status = "Warning"
    elif medium_risk_count > 0:
        system_status = "Attention"

    return {
        "system_status": system_status,
        "summary": {
            "total_cost": total_cost,
            "total_alerts": total_alerts,
            "medium_risk_count": medium_risk_count,
            "high_risk_count": high_risk_count,
            "top_consumer": {
                "room_id": top_consumer["room_id"] if top_consumer else "-",
                "average_energy": top_consumer["average_energy"] if top_consumer else 0,
            },
        },
    }




@app.get("/mobile/live-power")
def mobile_live_power():
    return get_live_power_summary()



@app.get("/mobile/rooms")
def mobile_rooms():
    room_stats = get_room_stats(minutes=60)
    return {
        "rooms": list(room_stats.values())
    }


@app.get("/mobile/buildings")
def mobile_buildings():
    return {
        "status": "ok",
        "generated_at": datetime.now().isoformat(),
        "buildings": build_buildings_summary(minutes=60),
    }


@app.get("/mobile/buildings/{building_id}/digital-twin")
def building_digital_twin(
    building_id: str
):
    buildings = build_buildings_summary(
        minutes=60
    )

    target = next(
        (
            building
            for building in buildings
            if building["building_id"]
            == building_id
        ),
        None,
    )

    if not target:
        return {
            "status": "error",
            "message": "Building not found",
        }

    # =============================================
    # Solar forecast for the NEXT 1 HOUR
    # =============================================

    solar_forecast = get_solar_forecast(
        hours=1
    )

    solar_available = (
        solar_forecast.get("status")
        == "ok"
        and bool(
            solar_forecast.get("hours")
        )
    )

    system_solar_power_kw = 0.0
    solar_forecast_time = None

    if solar_available:
        first_hour = (
            solar_forecast["hours"][0]
        )

        system_solar_power_kw = float(
            first_hour.get(
                "estimated_solar_power_kw",
                0,
            )
            or 0
        )

        solar_forecast_time = (
            first_hour.get(
                "forecast_time"
            )
        )

    # =============================================
    # Divide system solar capacity between rooms
    #
    # Current system:
    # building_1 -> room_1, room_2
    # building_2 -> room_3
    #
    # Therefore every room receives an equal
    # share of the total system solar generation.
    # =============================================

    total_system_rooms = sum(
        len(info["rooms"])
        for info
        in BUILDING_ROOM_MAP.values()
    )

    room_solar_power_kw = (
        system_solar_power_kw
        / total_system_rooms
        if total_system_rooms
        else 0
    )

    # Projection horizon
    projection_hours = 1.0

    rooms = []
    high_risk_rooms = []

    building_projected_consumption = 0.0
    building_projected_solar = 0.0

    for room in target["rooms"]:
        average_power_kw = float(
            room.get(
                "average_power_kw",
                room.get(
                    "average_energy",
                    0,
                ),
            )
            or 0
        )

        # =========================================
        # AI Risk
        # =========================================

        if average_power_kw >= 3.7:
            ai_risk = "High"

        elif average_power_kw >= 2.5:
            ai_risk = "Medium"

        else:
            ai_risk = "Low"

        # =========================================
        # Projected consumption for next hour
        #
        # kWh = average kW × hours
        # =========================================

        projected_consumption_kwh = round(
            average_power_kw
            * projection_hours,
            3,
        )

        # =========================================
        # Projected solar energy for next hour
        # =========================================

        projected_solar_kwh = round(
            room_solar_power_kw
            * projection_hours,
            3,
        )

        # =========================================
        # Net energy balance
        #
        # positive  -> surplus
        # negative  -> deficit
        # near zero -> balanced
        # =========================================

        net_energy_kwh = round(
            projected_solar_kwh
            - projected_consumption_kwh,
            3,
        )

        balance_tolerance_kwh = 0.05

        if (
            net_energy_kwh
            > balance_tolerance_kwh
        ):
            trading_status = "Surplus"

        elif (
            net_energy_kwh
            < -balance_tolerance_kwh
        ):
            trading_status = "Deficit"

        else:
            trading_status = "Balanced"

        building_projected_consumption += (
            projected_consumption_kwh
        )

        building_projected_solar += (
            projected_solar_kwh
        )

        enriched = {
            **room,

            "ai_risk":
                ai_risk,

            # -------------------------------------
            # Compatibility keys used by Flutter
            # -------------------------------------

            "generated_energy":
                projected_solar_kwh,

            "surplus_energy":
                net_energy_kwh,

            "trading_status":
                trading_status,

            # -------------------------------------
            # Clear semantic fields
            # -------------------------------------

            "projection_hours":
                projection_hours,

            "projected_consumption_kwh":
                projected_consumption_kwh,

            "projected_solar_energy_kwh":
                projected_solar_kwh,

            "projected_net_energy_kwh":
                net_energy_kwh,

            "solar_forecast_time":
                solar_forecast_time,

            "solar_forecast_available":
                solar_available,
        }

        rooms.append(
            enriched
        )

        if ai_risk == "High":
            high_risk_rooms.append(
                room["room_id"]
            )

    # =============================================
    # Building-level projected balance
    # =============================================

    building_projected_consumption = round(
        building_projected_consumption,
        3,
    )

    building_projected_solar = round(
        building_projected_solar,
        3,
    )

    building_net_energy = round(
        building_projected_solar
        - building_projected_consumption,
        3,
    )

    if building_net_energy > 0.05:
        building_trading_status = (
            "Surplus"
        )

    elif building_net_energy < -0.05:
        building_trading_status = (
            "Deficit"
        )

    else:
        building_trading_status = (
            "Balanced"
        )

    return {
        "status": "ok",

        "projection": {
            "hours":
                projection_hours,

            "solar_forecast_available":
                solar_available,

            "solar_forecast_time":
                solar_forecast_time,

            "system_solar_power_kw":
                round(
                    system_solar_power_kw,
                    3,
                ),

            "projected_consumption_kwh":
                building_projected_consumption,

            "projected_solar_energy_kwh":
                building_projected_solar,

            "projected_net_energy_kwh":
                building_net_energy,

            "trading_status":
                building_trading_status,
        },

        "building": {
            "building_id":
                target["building_id"],

            "name":
                target["name"],

            "room_count":
                target["room_count"],

            "total_energy":
                target["total_energy"],

            "average_energy":
                target["average_energy"],

            "status":
                target["status"],

            "high_risk_rooms":
                high_risk_rooms,

            "rooms":
                rooms,
        },
    }

@app.get("/mobile/alerts")
def mobile_alerts():
    room_stats = get_room_stats(
        minutes=60
    )

    alerts = []

    for room in room_stats.values():
        average_power_kw = float(
            room.get(
                "average_power_kw",
                room.get(
                    "average_energy",
                    0,
                ),
            )
            or 0
        )

        room_id = room["room_id"]

        if average_power_kw >= 3.7:
            alerts.append(
                {
                    "room_id":
                        room_id,

                    "category":
                        "Energy",

                    "severity":
                        "High",

                    "title":
                        f"{room_id} high power load",

                    "message":
                        (
                            f"{room_id} is operating at a high "
                            f"power load with an average power "
                            f"of {average_power_kw:.2f} kW "
                            f"during the last 60 minutes."
                        ),

                    "average_power_kw":
                        round(
                            average_power_kw,
                            2,
                        ),

                    "window_minutes":
                        60,
                }
            )

        elif average_power_kw >= 2.5:
            alerts.append(
                {
                    "room_id":
                        room_id,

                    "category":
                        "Energy",

                    "severity":
                        "Medium",

                    "title":
                        f"{room_id} moderate power load",

                    "message":
                        (
                            f"{room_id} is showing an elevated "
                            f"power load with an average power "
                            f"of {average_power_kw:.2f} kW "
                            f"during the last 60 minutes."
                        ),

                    "average_power_kw":
                        round(
                            average_power_kw,
                            2,
                        ),

                    "window_minutes":
                        60,
                }
            )

    return {
        "alerts": alerts,
    }



@app.get("/mobile/energy-trading")
def mobile_energy_trading():
    return build_energy_trading()





@app.get("/weather/forecast")
def weather_forecast():
    return get_weather_forecast()

@app.get("/smart-planning")
def smart_planning():
    return build_smart_plan()


@app.get("/smart-planning/rooms")
def smart_planning_rooms():
    return build_room_plans()


@app.get("/mobile/recommendations-smart")
def mobile_recommendations_smart():
    return build_planning_recommendations()


@app.get("/smart-planning/health")
def smart_planning_health():
    return build_planning_health()



@app.get("/forecast/solar")
def solar_forecast():
    return get_solar_forecast(hours=6)


@app.get("/forecast/load")
def load_forecast(hours: int = 6):

    if hours < 1:
        hours = 1

    if hours > 24:
        hours = 24

    return get_load_forecast(
        forecast_hours=hours
    )

@app.get("/forecast/energy")
def energy_forecast():
    return get_energy_forecast(
        hours=6
    )


@app.get("/optimization/mpc")
def mpc_optimization():
    return optimize_energy_plan(
        hours=6
    )

@app.get("/optimization/mpc/scenarios")
def mpc_scenarios():
    return run_mpc_scenarios()


@app.get("/forecast/electricity-prices")
def electricity_prices():
    return get_electricity_price_forecast(
        hours=6
    )


@app.get("/optimization/economic-mpc")
def economic_mpc():
    return optimize_economic_energy_plan(
        hours=6
    )

@app.get("/optimization/advanced-economic-mpc")
def advanced_economic_mpc():
    return optimize_advanced_economic_mpc(
        hours=6
    )

@app.get("/optimization/comparison")
def optimization_comparison():
    return compare_optimization_models(
        hours=6
    )

@app.get("/ai/anomalies")
def ai_anomalies(
    source: str | None = None,
    device_id: str | None = None,
):
    return detect_energy_anomalies(
        source=source,
        device_id=device_id,
    )

@app.get("/ai/current-status")
def ai_current_status():
    return get_current_ai_status()

@app.get("/alerts/current")
def current_alerts():

    ai_monitoring = (
        get_current_ai_status()
    )

    devices = (
        get_devices()
    )

    return generate_alerts(
        ai_monitoring,
        devices
    )


@app.get("/forecast/load/ml")
def ml_load_forecast(
    source: str = "auto"
):
    return get_ml_load_forecast(
        forecast_hours=6,
        source=source
    )


@app.get("/data/source-stats")
def data_source_stats():
    db = SessionLocal()

    try:
        rows = (
            db.query(
                models.EnergyReading.data_source,
                func.count(
                    models.EnergyReading.id
                ).label("count"),
                func.max(
                    models.EnergyReading.timestamp
                ).label("last_seen")
            )
            .group_by(
                models.EnergyReading.data_source
            )
            .all()
        )

        sources = []

        for row in rows:
            sources.append({
                "data_source":
                    row.data_source
                    or "unknown",

                "reading_count":
                    int(row.count or 0),

                "last_seen":
                    (
                        row.last_seen.isoformat()
                        if row.last_seen
                        else None
                    )
            })

        return {
            "status": "ok",
            "sources": sources
        }

    finally:
        db.close()


@app.get("/ml/data-status")
def ml_data_status():
    return get_ml_data_status()

@app.get("/forecast/energy/ml")
def ml_energy_forecast(
    source: str = "auto"
):
    return get_ml_energy_forecast(
        hours=6,
        source=source
    )

@app.get(
    "/optimization/advanced-economic-mpc/ml"
)
def advanced_economic_mpc_ml(
    source: str = "auto"
):
    return optimize_ml_advanced_mpc(
        hours=6,
        source=source
    )


@app.get(
    "/optimization/battery-aware-ml-mpc"
)
def battery_aware_ml_mpc(
    source: str = "auto"
):
    return optimize_battery_aware_ml_mpc(
        hours=6,
        source=source
    )


@app.get(
    "/optimization/ml-battery-comparison"
)
def ml_battery_comparison(
    source: str = "auto"
):
    return compare_ml_battery_strategies(
        hours=6,
        source=source
    )

@app.get(
    "/optimization/fair-mpc-benchmark"
)
def fair_mpc_benchmark(
    source: str = "auto"
):
    return run_fair_mpc_benchmark(
        hours=6,
        source=source
    )


@app.get(
    "/optimization/battery-stress-scenario"
)
def battery_stress_scenario():
    return run_battery_stress_scenario()


@app.post(
    "/ai/recommendations"
)
def ai_recommendations(
    optimization_result: dict
):

    return generate_energy_recommendations(
        optimization_result
    )

@app.get("/dashboard/status")
def dashboard_status():

    return get_dashboard_status()



@app.get("/devices")
def devices():

    data = get_devices()

    return {
        "total": len(data),
        "online": len(
            [
                d for d in data
                if d["status"] == "Online"
            ]
        ),
        "delayed": len(
            [
                d for d in data
                if d["status"] == "Delayed"
            ]
        ),
        "offline": len(
            [
                d for d in data
                if d["status"] == "Offline"
            ]
        ),
        "items": data
    }

@app.get("/energy/readings")
def energy_readings(
    device_id:str=None,
    room_id:str=None,
    limit:int=100
):

    data = get_energy_history(
        device_id,
        room_id,
        limit
    )

    return {
        "count": len(data),
        "items": data
    }



@app.get("/security/events")
def security_events(limit: int = 100):

    data = get_security_events(limit)

    return {
        "total": len(data),
        "items": data
    }


@app.get("/alerts")
def alerts(
    limit: int = 100,
    status: str = None,
    severity: str = None,
    device_id: str = None
):

    data = get_alerts(
        limit=limit,
        status=status,
        severity=severity,
        device_id=device_id
    )

    return {
        "total": len(data),
        "items": data
    }