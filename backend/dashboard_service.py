from datetime import datetime

from database import SessionLocal
import models

from ml_load_forecast_service import get_ml_load_forecast
from battery_aware_ml_mpc import optimize_battery_aware_ml_mpc
from ai_recommendation_service import generate_energy_recommendations

from weather_service import get_weather_forecast
from solar_service import get_solar_forecast

from anomaly_detection_service import get_current_ai_status

from alert_engine import generate_alerts

from device_service import get_devices


def get_dashboard_status():

    db = SessionLocal()

    try:

        # =====================================================
        # Devices
        # =====================================================

        device_list = get_devices()

        sensor_devices = [
            device
            for device in device_list
            if device.get("source") == "sensor"
        ]

        online_sensor_devices = len(
            [
                device
                for device in sensor_devices
                if device.get("status") == "Online"
            ]
        )

        delayed_sensor_devices = len(
            [
                device
                for device in sensor_devices
                if device.get("status") == "Delayed"
            ]
        )

        offline_sensor_devices = len(
            [
                device
                for device in sensor_devices
                if device.get("status") == "Offline"
            ]
        )

        total_devices = len(device_list)

        online_devices = len(
            [
                device
                for device in device_list
                if device.get("status") == "Online"
            ]
        )

        delayed_devices = len(
            [
                device
                for device in device_list
                if device.get("status") == "Delayed"
            ]
        )

        offline_devices = len(
            [
                device
                for device in device_list
                if device.get("status") == "Offline"
            ]
        )

        # =====================================================
        # Latest Energy Reading
        # =====================================================

        latest_reading = (
            db.query(models.EnergyReading)
            .order_by(
                models.EnergyReading.id.desc()
            )
            .first()
        )

        current_energy = None

        if latest_reading:

           current_energy = {

                "reading_id":
                    latest_reading.id,

                "device_id":
                    latest_reading.device_id,

                "room_id":
                    latest_reading.room_id,

                "power_kw":
                    float(
                        latest_reading.power_kw
                        if latest_reading.power_kw is not None
                        else latest_reading.energy
                    ),

                "energy_kwh":
                    float(
                        latest_reading.energy_kwh
                    )
                    if latest_reading.energy_kwh is not None
                    else None,

                "source":
                    latest_reading.data_source,

                "timestamp":
                    (
                        latest_reading.timestamp.isoformat()
                        if latest_reading.timestamp
                        else None
                    )
            }

        # =====================================================
        # ML Forecast
        # =====================================================

        forecast = get_ml_load_forecast()

        # =====================================================
        # MPC Optimization
        # =====================================================

        optimization = (
            optimize_battery_aware_ml_mpc()
        )

        # =====================================================
        # AI Recommendations
        # =====================================================

        recommendations = (
            generate_energy_recommendations(
                optimization
            )
        )

        # =====================================================
        # Weather Forecast
        # =====================================================

        weather = get_weather_forecast(
            forecast_hours=6
        )

        # =====================================================
        # Solar Forecast
        # =====================================================

        solar = get_solar_forecast(
            hours=6
        )

        # =====================================================
        # AI Anomaly Detection
        # =====================================================

        ai_monitoring = (
            get_current_ai_status()
        )

        # =====================================================
        # Alerts
        # =====================================================

        alerts = generate_alerts(
            ai_monitoring,
            device_list
        )

        # =====================================================
        # System Status (Based on Real Sensors Only)
        # =====================================================

        if not sensor_devices:

            system_status = "Running"

        elif offline_sensor_devices == len(sensor_devices):

            system_status = "Warning"

        elif (
            offline_sensor_devices > 0
            or delayed_sensor_devices > 0
        ):

            system_status = "Degraded"

        else:

            system_status = "Running"

        # =====================================================
        # Response
        # =====================================================

        return {

            "generated_at":
                datetime.now().isoformat(),

            "system_status":
                system_status,

            "devices": {

                "total":
                    total_devices,

                "online":
                    online_devices,

                "delayed":
                    delayed_devices,

                "offline":
                    offline_devices,

                "sensors": {

                    "total":
                        len(sensor_devices),

                    "online":
                        online_sensor_devices,

                    "delayed":
                        delayed_sensor_devices,

                    "offline":
                        offline_sensor_devices
                },

                "items":
                    device_list
            },

            "current_energy":
                current_energy,

            "forecast": {

                "model":
                    forecast.get(
                        "model"
                    ),

                "hours":
                    forecast.get(
                        "hours",
                        []
                    )
            },

            "optimization": {

                "model":
                    optimization.get(
                        "optimization_model"
                    ),

                "saving_percent":
                    (
                        optimization
                        .get(
                            "summary",
                            {}
                        )
                        .get(
                            "cost_saving_percent"
                        )
                    ),

                "grid_reduction_percent":
                    (
                        optimization
                        .get(
                            "summary",
                            {}
                        )
                        .get(
                            "grid_reduction_percent"
                        )
                    )
            },

            "ai_recommendations":
                recommendations,

            "environment": {

                "weather":
                    weather,

                "solar":
                    solar
            },

            "ai_monitoring":
                ai_monitoring,

            "alerts":
                alerts
        }

    finally:

        try:

            db.close()

        except Exception as e:

            print(
                f"Database session close warning: {e}"
            )