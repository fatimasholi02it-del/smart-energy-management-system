import os

from dotenv import load_dotenv


# =====================================================
# Environment
# =====================================================

load_dotenv()


# =====================================================
# Settings
# =====================================================

class Settings:
    # -------------------------------------------------
    # Application
    # -------------------------------------------------

    app_name: str = (
        "Smart Energy Management API"
    )

    # -------------------------------------------------
    # Database
    # -------------------------------------------------

    database_url: str = os.environ[
        "DATABASE_URL"
    ]

    # -------------------------------------------------
    # API Security
    # -------------------------------------------------

    api_key: str = os.environ[
        "API_KEY"
    ]

    # -------------------------------------------------
    # MQTT
    # -------------------------------------------------

    mqtt_broker_host: str = os.environ[
        "MQTT_BROKER_HOST"
    ]

    mqtt_broker_port: int = int(
        os.getenv(
            "MQTT_BROKER_PORT",
            "8883",
        )
    )

    mqtt_topic: str = os.getenv(
        "MQTT_TOPIC",
        "energy/readings",
    )

    mqtt_username: str = os.environ[
        "MQTT_USERNAME"
    ]

    mqtt_password: str = os.environ[
        "MQTT_PASSWORD"
    ]

    # -------------------------------------------------
    # Message Authentication
    # -------------------------------------------------

    message_secret: str = os.environ[
        "MESSAGE_SECRET"
    ]

    # -------------------------------------------------
    # Trusted Devices
    # -------------------------------------------------

    trusted_devices = [
        "simulator_01",
        "simulator_02",
        "simulator_03",
        "esp32_01",
    ]

    # -------------------------------------------------
    # Allowed Room Power Ranges
    #
    # These ranges are used for basic validation.
    # They are separate from AI anomaly detection.
    # -------------------------------------------------

    allowed_rooms = {
        "room_1": (
            2.0,
            4.0,
        ),
        "room_2": (
            1.5,
            3.5,
        ),
        "room_3": (
            3.0,
            5.0,
        ),
    }


# =====================================================
# Global Settings Instance
# =====================================================

settings = Settings()