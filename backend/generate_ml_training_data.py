import csv
import math
import random

from datetime import datetime, timedelta


# =====================================================
# Dataset Configuration
# =====================================================

OUTPUT_FILE = "ml_training_data.csv"

DAYS_TO_GENERATE = 30

START_DATE = (
    datetime.now()
    - timedelta(
        days=DAYS_TO_GENERATE
    )
)


# =====================================================
# Daily Load Profile
# =====================================================

def get_base_load(
    hour: int,
) -> float:
    """
    Simplified realistic daily load profile.

    00-05 : Low
    06-08 : Morning rise
    09-12 : High
    13-16 : High
    17-20 : Peak
    21-23 : Medium
    """

    if 0 <= hour <= 5:
        return 1.8

    if 6 <= hour <= 8:
        return 2.5

    if 9 <= hour <= 12:
        return 3.2

    if 13 <= hour <= 16:
        return 3.5

    if 17 <= hour <= 20:
        return 4.1

    return 2.7


# =====================================================
# Generate Synthetic Reading
# =====================================================

def generate_energy(
    timestamp: datetime,
    previous_energy: float,
) -> float:
    hour = timestamp.hour

    base_load = (
        get_base_load(
            hour
        )
    )

    # ---------------------------------------------
    # Weekend influence
    # ---------------------------------------------

    weekday = (
        timestamp.weekday()
    )

    if weekday >= 5:
        base_load *= 0.85

    # ---------------------------------------------
    # Smooth hourly pattern
    # ---------------------------------------------

    sinusoidal_component = (
        0.15
        * math.sin(
            (hour / 24.0)
            * 2
            * math.pi
        )
    )

    # ---------------------------------------------
    # Temperature-like daytime influence
    # ---------------------------------------------

    if 12 <= hour <= 18:
        temperature_effect = 0.20
    else:
        temperature_effect = 0.0

    # ---------------------------------------------
    # Previous-reading dependency
    # ---------------------------------------------

    previous_effect = (
        previous_energy
        * 0.15
    )

    # ---------------------------------------------
    # Random variation
    # ---------------------------------------------

    noise = random.gauss(
        0,
        0.12,
    )

    value = (
        base_load
        + sinusoidal_component
        + temperature_effect
        + previous_effect
        + noise
    )

    # ---------------------------------------------
    # Rare realistic spike
    # ---------------------------------------------

    if random.random() < 0.015:
        value += random.uniform(
            0.3,
            0.7,
        )

    return round(
        max(
            value,
            0.5,
        ),
        3,
    )


# =====================================================
# Generate Dataset
# =====================================================

def generate_dataset():
    rows = []

    current_time = (
        START_DATE.replace(
            minute=0,
            second=0,
            microsecond=0,
        )
    )

    previous_energy = 2.0

    total_hours = (
        DAYS_TO_GENERATE
        * 24
    )

    for _ in range(
        total_hours
    ):
        energy = (
            generate_energy(
                current_time,
                previous_energy,
            )
        )

        rows.append(
            {
                "timestamp":
                    current_time.isoformat(),

                "energy":
                    energy,

                "hour":
                    current_time.hour,

                "weekday":
                    current_time.weekday(),
            }
        )

        previous_energy = (
            energy
        )

        current_time += timedelta(
            hours=1
        )

    # ---------------------------------------------
    # Save CSV
    # ---------------------------------------------

    with open(
        OUTPUT_FILE,
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "timestamp",
                "energy",
                "hour",
                "weekday",
            ],
        )

        writer.writeheader()

        writer.writerows(
            rows
        )

    print(
        f"Generated {len(rows)} "
        f"training records."
    )

    print(
        f"Saved to: "
        f"{OUTPUT_FILE}"
    )


# =====================================================
# Entry Point
# =====================================================

if __name__ == "__main__":
    generate_dataset()