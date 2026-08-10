import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    app_name: str = "Smart Energy Monitoring API"

    database_url: str = os.environ["DATABASE_URL"]

    api_key: str = os.environ["API_KEY"]

    mqtt_broker_host: str = os.getenv(
        "MQTT_BROKER_HOST",
        "localhost"
    )

    mqtt_broker_port: int = int(
        os.getenv("MQTT_BROKER_PORT", "1883")
    )

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

    message_secret: str = os.environ["MESSAGE_SECRET"]

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