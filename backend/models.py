from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from database import Base
from datetime import datetime


class EnergyReading(Base):
    __tablename__ = "energy_readings"

    id = Column(Integer, primary_key=True, index=True)

    device_id = Column(
        String,
        index=True,
        nullable=True
    )

    room_id = Column(
        String,
        index=True,
        nullable=False
    )

    # Compatibility field used by current AI / Forecast / MPC.
    # For real sensors, this will store the same value as power_kw.
    energy = Column(
        Float,
        nullable=False
    )

    # Instantaneous power from the real sensor.
    power_kw = Column(
        Float,
        nullable=True
    )

    # Cumulative energy from the real sensor.
    energy_kwh = Column(
        Float,
        nullable=True
    )

    timestamp = Column(
        DateTime,
        nullable=False
    )

    data_source = Column(
        String,
        index=True,
        nullable=True
    )
class SecurityEvent(Base):
    __tablename__ = "security_events"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    device_id = Column(
        String,
        nullable=True
    )

    room_id = Column(
        String,
        nullable=True
    )

    event_type = Column(
        String,
        nullable=False
    )

    reason = Column(
        Text,
        nullable=False
    )

    raw_payload = Column(
        Text,
        nullable=True
    )

    timestamp = Column(
        DateTime,
        nullable=False
    )


class DeviceHealth(Base):
    __tablename__ = "device_health"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    device_id = Column(
        String,
        nullable=False,
        unique=True
    )

    room_id = Column(
        String,
        nullable=False
    )

    source = Column(
        String,
        nullable=False,
        default="simulator"
    )

    last_seen = Column(
        DateTime,
        nullable=False,
        default=datetime.now
    )

    status = Column(
        String,
        nullable=False,
        default="Online"
    )


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    device_id = Column(
        String,
        nullable=True
    )

    room_id = Column(
        String,
        nullable=True
    )

    alert_type = Column(
        String,
        nullable=False
    )

    severity = Column(
        String,
        nullable=False
    )

    message = Column(
        Text,
        nullable=False
    )

    status = Column(
        String,
        nullable=False,
        default="Open"
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.now
    )