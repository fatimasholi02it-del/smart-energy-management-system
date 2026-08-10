import csv
import os
from datetime import datetime

from sqlalchemy import func

from database import SessionLocal
import models


SYNTHETIC_FILE = "ml_training_data.csv"

# =========================================================
# Training readiness rules
# =========================================================

MIN_SYNTHETIC_RECORDS = 100
MIN_SIMULATOR_RECORDS = 100

MIN_REAL_SENSOR_RECORDS = 500

# البيانات الحقيقية لازم تغطي 3 أيام على الأقل
MIN_REAL_SENSOR_SPAN_DAYS = 3.0


# =========================================================
# Synthetic Dataset
# =========================================================

def count_synthetic_records():
    if not os.path.exists(
        SYNTHETIC_FILE
    ):
        return 0

    count = 0

    try:
        with open(
            SYNTHETIC_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            reader = csv.DictReader(
                file
            )

            for _ in reader:
                count += 1

    except Exception as e:
        print(
            f"Failed to count synthetic records: {e}"
        )

        return 0

    return count


# =========================================================
# Database Source Statistics
# =========================================================

def get_database_source_counts():
    db = SessionLocal()

    try:
        rows = (
            db.query(
                models.EnergyReading.data_source,

                func.count(
                    models.EnergyReading.id
                ).label("count"),

                func.min(
                    models.EnergyReading.timestamp
                ).label("first_seen"),

                func.max(
                    models.EnergyReading.timestamp
                ).label("last_seen")
            )
            .group_by(
                models.EnergyReading.data_source
            )
            .all()
        )

        result = {
            "legacy": {
                "count": 0,
                "first_seen": None,
                "last_seen": None
            },

            "simulator": {
                "count": 0,
                "first_seen": None,
                "last_seen": None
            },

            "sensor": {
                "count": 0,
                "first_seen": None,
                "last_seen": None
            },

            "unknown": {
                "count": 0,
                "first_seen": None,
                "last_seen": None
            }
        }

        for row in rows:

            source = (
                row.data_source
                or "unknown"
            )

            if source not in result:
                result[source] = {
                    "count": 0,
                    "first_seen": None,
                    "last_seen": None
                }

            result[source] = {
                "count":
                    int(
                        row.count or 0
                    ),

                "first_seen":
                    row.first_seen,

                "last_seen":
                    row.last_seen
            }

        return result

    finally:
        db.close()


# =========================================================
# Calculate Data Span
# =========================================================

def calculate_span_days(
    first_seen,
    last_seen
):
    if (
        first_seen is None
        or last_seen is None
    ):
        return 0.0

    span_seconds = (
        last_seen
        - first_seen
    ).total_seconds()

    span_days = (
        span_seconds
        / 86400.0
    )

    return round(
        max(
            span_days,
            0.0
        ),
        3
    )


# =========================================================
# Sensor Readiness
# =========================================================

def evaluate_sensor_readiness(
    sensor_info: dict
):
    records = sensor_info.get(
        "count",
        0
    )

    first_seen = sensor_info.get(
        "first_seen"
    )

    last_seen = sensor_info.get(
        "last_seen"
    )

    span_days = calculate_span_days(
        first_seen,
        last_seen
    )

    record_requirement_met = (
        records
        >= MIN_REAL_SENSOR_RECORDS
    )

    span_requirement_met = (
        span_days
        >= MIN_REAL_SENSOR_SPAN_DAYS
    )

    ready = (
        record_requirement_met
        and span_requirement_met
    )

    missing_records = max(
        MIN_REAL_SENSOR_RECORDS
        - records,
        0
    )

    missing_span_days = max(
        MIN_REAL_SENSOR_SPAN_DAYS
        - span_days,
        0.0
    )

    return {
        "ready":
            ready,

        "records":
            records,

        "minimum_records":
            MIN_REAL_SENSOR_RECORDS,

        "record_requirement_met":
            record_requirement_met,

        "first_seen":
            (
                first_seen.isoformat()
                if first_seen
                else None
            ),

        "last_seen":
            (
                last_seen.isoformat()
                if last_seen
                else None
            ),

        "data_span_days":
            span_days,

        "minimum_span_days":
            MIN_REAL_SENSOR_SPAN_DAYS,

        "span_requirement_met":
            span_requirement_met,

        "missing_records":
            missing_records,

        "missing_span_days":
            round(
                missing_span_days,
                3
            )
    }


# =========================================================
# Main ML Data Status
# =========================================================

def get_ml_data_status():

    synthetic_records = (
        count_synthetic_records()
    )

    source_stats = (
        get_database_source_counts()
    )

    simulator_info = source_stats.get(
        "simulator",
        {}
    )

    sensor_info = source_stats.get(
        "sensor",
        {}
    )

    legacy_info = source_stats.get(
        "legacy",
        {}
    )

    simulator_records = (
        simulator_info.get(
            "count",
            0
        )
    )

    legacy_records = (
        legacy_info.get(
            "count",
            0
        )
    )

    sensor_readiness = (
        evaluate_sensor_readiness(
            sensor_info
        )
    )

    real_data_ready = (
        sensor_readiness[
            "ready"
        ]
    )

    # =====================================================
    # Recommended Training Source
    # =====================================================

    if real_data_ready:

        recommended_source = (
            "sensor"
        )

        recommendation_reason = (
            "Enough real sensor readings are "
            "available and the dataset covers "
            "the minimum required time span."
        )

    elif (
        synthetic_records
        >= MIN_SYNTHETIC_RECORDS
    ):

        recommended_source = (
            "synthetic"
        )

        recommendation_reason = (
            "Real sensor data is not ready yet. "
            "Use the synthetic dataset for "
            "prototype model development."
        )

    elif (
        simulator_records
        >= MIN_SIMULATOR_RECORDS
    ):

        recommended_source = (
            "simulator"
        )

        recommendation_reason = (
            "Simulator data is available for "
            "temporary model development."
        )

    else:

        recommended_source = (
            "none"
        )

        recommendation_reason = (
            "No training source currently "
            "contains enough usable data."
        )

    return {
        "status":
            "ok",

        "sources": {

            "synthetic": {
                "records":
                    synthetic_records,

                "available":
                    synthetic_records > 0,

                "minimum_required":
                    MIN_SYNTHETIC_RECORDS,

                "ready":
                    synthetic_records
                    >= MIN_SYNTHETIC_RECORDS
            },

            "simulator": {
                "records":
                    simulator_records,

                "available":
                    simulator_records > 0,

                "minimum_required":
                    MIN_SIMULATOR_RECORDS,

                "ready":
                    simulator_records
                    >= MIN_SIMULATOR_RECORDS,

                "first_seen":
                    (
                        simulator_info[
                            "first_seen"
                        ].isoformat()
                        if simulator_info.get(
                            "first_seen"
                        )
                        else None
                    ),

                "last_seen":
                    (
                        simulator_info[
                            "last_seen"
                        ].isoformat()
                        if simulator_info.get(
                            "last_seen"
                        )
                        else None
                    ),

                "data_span_days":
                    calculate_span_days(
                        simulator_info.get(
                            "first_seen"
                        ),
                        simulator_info.get(
                            "last_seen"
                        )
                    )
            },

            "sensor":
                sensor_readiness,

            "legacy": {
                "records":
                    legacy_records,

                "use_for_final_training":
                    False
            }
        },

        "real_data_ready":
            real_data_ready,

        "recommended_training_source":
            recommended_source,

        "recommendation_reason":
            recommendation_reason
    }