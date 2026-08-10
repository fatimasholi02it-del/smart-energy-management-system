import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    app_name: str = "Smart Energy Monitoring API"

    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql://neondb_owner:npg_ej0GhTuDVcg9@ep-royal-queen-ahzglo4t-pooler.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    )

    api_key: str = os.getenv(
        "API_KEY",
        "super-secret-key"
    )

    mqtt_broker_host: str = os.getenv(
        "MQTT_BROKER_HOST",
        "localhost"
    )

    mqtt_broker_port: int = int(os.getenv("MQTT_BROKER_PORT", "1883"))

    mqtt_topic: str = os.getenv(
        "MQTT_TOPIC",
        "energy/readings"
    )

    mqtt_username: str = os.getenv(
        "MQTT_USERNAME",
        ""
    )

    mqtt_password: str = os.getenv(
        "MQTT_PASSWORD",
        ""
    )

    message_secret: str = os.getenv(
        "MESSAGE_SECRET",
        "super-secret-key"
    )

    trusted_devices = [
        "simulator_01",
        "simulator_02",
        "simulator_03",
        "esp32_01"
    ]

    allowed_rooms = {
        "room_1": (2.0, 4.0),
        "room_2": (1.5, 3.5),
        "room_3": (3.0, 5.0),
    }


settings = Settings()