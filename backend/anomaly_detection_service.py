from datetime import datetime, timedelta

import numpy as np
from sklearn.ensemble import IsolationForest

from database import SessionLocal
import models


MIN_TRAINING_RECORDS = 20
LOOKBACK_DAYS = 30
CONTAMINATION = 0.08


# =========================================================
# Helpers
# =========================================================

def get_effective_power(row):
    """
    New records:
        use power_kw

    Old records:
        fallback to legacy energy field
    """

    if row.power_kw is not None:
        return float(row.power_kw)

    if row.energy is not None:
        return float(row.energy)

    return None


def determine_analysis_scope(
    latest_row
):
    """
    Train anomaly detection using the
    same physical/logical device only.

    This prevents rooms with different
    normal power ranges from being mixed
    into one Isolation Forest model.
    """

    return {
        "source":
            latest_row.data_source,

        "device_id":
            latest_row.device_id,

        "room_id":
            latest_row.room_id,

        "scope_type":
            "device",
    }
# =========================================================
# Get Latest Reading
# =========================================================

def get_latest_energy_reading():

    db = SessionLocal()

    try:

        row = (
            db.query(
                models.EnergyReading.id,
                models.EnergyReading.device_id,
                models.EnergyReading.room_id,
                models.EnergyReading.energy,
                models.EnergyReading.power_kw,
                models.EnergyReading.energy_kwh,
                models.EnergyReading.timestamp,
                models.EnergyReading.data_source
            )
            .order_by(
                models.EnergyReading.timestamp.desc()
            )
            .first()
        )

        return row

    finally:

        try:
            db.close()

        except Exception as e:

            print(
                f"Database close warning: {e}"
            )


# =========================================================
# Get Energy Readings For AI
# =========================================================

def get_energy_values(
    days: int = LOOKBACK_DAYS,
    source=None,
    device_id=None
):

    db = SessionLocal()

    try:

        since_time = (
            datetime.now()
            - timedelta(days=days)
        )

        query = (
            db.query(
                models.EnergyReading.id,
                models.EnergyReading.device_id,
                models.EnergyReading.room_id,
                models.EnergyReading.energy,
                models.EnergyReading.power_kw,
                models.EnergyReading.energy_kwh,
                models.EnergyReading.timestamp,
                models.EnergyReading.data_source
            )
            .filter(
                models.EnergyReading.timestamp >= since_time
            )
        )

        # -------------------------------------------------
        # Source separation
        # -------------------------------------------------

        if source:

            query = query.filter(
                models.EnergyReading.data_source
                == source
            )

        # -------------------------------------------------
        # Device separation
        # -------------------------------------------------

        if device_id:

            query = query.filter(
                models.EnergyReading.device_id
                == device_id
            )

        rows = (
            query
            .order_by(
                models.EnergyReading.timestamp.asc()
            )
            .all()
        )

        # -------------------------------------------------
        # Fallback
        # -------------------------------------------------

        if not rows:

            fallback_query = (
                db.query(
                    models.EnergyReading.id,
                    models.EnergyReading.device_id,
                    models.EnergyReading.room_id,
                    models.EnergyReading.energy,
                    models.EnergyReading.power_kw,
                    models.EnergyReading.energy_kwh,
                    models.EnergyReading.timestamp,
                    models.EnergyReading.data_source
                )
            )

            if source:

                fallback_query = (
                    fallback_query.filter(
                        models.EnergyReading.data_source
                        == source
                    )
                )

            if device_id:

                fallback_query = (
                    fallback_query.filter(
                        models.EnergyReading.device_id
                        == device_id
                    )
                )

            rows = (
                fallback_query
                .order_by(
                    models.EnergyReading.timestamp.desc()
                )
                .limit(1000)
                .all()
            )

            rows = list(
                reversed(rows)
            )

        return rows

    finally:

        try:
            db.close()

        except Exception as e:

            print(
                f"Database close warning: {e}"
            )


# =========================================================
# Classify Anomaly Severity
# =========================================================

def classify_severity(
    anomaly_score: float
):

    if anomaly_score <= -0.15:
        return "High"

    if anomaly_score <= -0.05:
        return "Medium"

    return "Low"


# =========================================================
# Build Insufficient Data Response
# =========================================================

def build_insufficient_response(
    training_records,
    source=None,
    device_id=None,
    message=None
):

    if message is None:

        message = (
            f"At least "
            f"{MIN_TRAINING_RECORDS} "
            f"readings are required "
            f"before anomaly detection "
            f"can be performed."
        )

    return {
        "status":
            "insufficient_data",

        "model":
            "Isolation Forest",

        "model_type":
            "Unsupervised Anomaly Detection",

        "generated_at":
            datetime.now().isoformat(),

        "analysis_scope": {
            "source":
                source,

            "device_id":
                device_id
        },

        "message":
            message,

        "minimum_training_records":
            MIN_TRAINING_RECORDS,

        "training_records":
            training_records,

        "current_reading":
            None,

        "ai_result":
            None,

        "learned_normal_pattern":
            None
    }


# =========================================================
# Detect Historical Energy Anomalies
# =========================================================

def detect_energy_anomalies(
    source=None,
    device_id=None
):

    # -----------------------------------------------------
    # If scope is not supplied, determine from latest data
    # -----------------------------------------------------

    if source is None:

        latest_row = (
            get_latest_energy_reading()
        )

        if latest_row is None:

            return {
                "status":
                    "insufficient_data",

                "model":
                    "Isolation Forest",

                "message":
                    "No energy readings are available.",

                "training_records":
                    0,

                "anomalies":
                    []
            }

        scope = determine_analysis_scope(
            latest_row
        )

        source = scope[
            "source"
        ]

        device_id = scope[
            "device_id"
        ]

    # -----------------------------------------------------
    # Load isolated training dataset
    # -----------------------------------------------------

    rows = get_energy_values(
        source=source,
        device_id=device_id
    )

    valid_rows = []

    for row in rows:

        power = get_effective_power(
            row
        )

        if power is not None:

            valid_rows.append(
                (
                    row,
                    power
                )
            )

    # -----------------------------------------------------
    # Validate Training Data
    # -----------------------------------------------------

    if len(valid_rows) < MIN_TRAINING_RECORDS:

        return {
            "status":
                "insufficient_data",

            "model":
                "Isolation Forest",

            "model_type":
                "Unsupervised Anomaly Detection",

            "generated_at":
                datetime.now().isoformat(),

            "analysis_scope": {
                "source":
                    source,

                "device_id":
                    device_id
            },

            "message":
                (
                    f"Only "
                    f"{len(valid_rows)} "
                    f"readings are available. "
                    f"At least "
                    f"{MIN_TRAINING_RECORDS} "
                    f"readings are required."
                ),

            "training_records":
                len(valid_rows),

            "anomalies":
                []
        }

    # -----------------------------------------------------
    # Prepare Training Data
    # -----------------------------------------------------

    values = np.array(
        [
            [power]
            for row, power
            in valid_rows
        ]
    )

    # -----------------------------------------------------
    # Train Isolation Forest
    # -----------------------------------------------------

    model = IsolationForest(
        n_estimators=200,
        contamination=CONTAMINATION,
        random_state=42
    )

    model.fit(
        values
    )

    predictions = model.predict(
        values
    )

    scores = model.decision_function(
        values
    )

    anomaly_rows = []
    normal_values = []

    # -----------------------------------------------------
    # Build Results
    # -----------------------------------------------------

    for (
        row,
        power_value
    ), prediction, score in zip(
        valid_rows,
        predictions,
        scores
    ):

        if prediction == -1:

            anomaly_rows.append({

                "reading_id":
                    row.id,

                "device_id":
                    row.device_id,

                "room_id":
                    row.room_id,

                "source":
                    row.data_source,

                "power_kw":
                    round(
                        power_value,
                        3
                    ),

                "energy_kwh":
                    (
                        float(
                            row.energy_kwh
                        )
                        if row.energy_kwh
                        is not None
                        else None
                    ),

                # Compatibility
                "energy":
                    round(
                        power_value,
                        3
                    ),

                "timestamp":
                    (
                        row.timestamp.isoformat()
                        if row.timestamp
                        else None
                    ),

                "anomaly_score":
                    round(
                        float(score),
                        4
                    ),

                "severity":
                    classify_severity(
                        float(score)
                    )
            })

        else:

            normal_values.append(
                power_value
            )

    # -----------------------------------------------------
    # Statistics
    # -----------------------------------------------------

    anomaly_count = len(
        anomaly_rows
    )

    total_records = len(
        valid_rows
    )

    anomaly_ratio = (
        (
            anomaly_count
            / total_records
        )
        * 100.0
        if total_records
        else 0.0
    )

    if normal_values:

        normal_min = min(
            normal_values
        )

        normal_max = max(
            normal_values
        )

        normal_average = (
            sum(normal_values)
            / len(normal_values)
        )

    else:

        normal_min = 0.0
        normal_max = 0.0
        normal_average = 0.0

    anomaly_rows = sorted(
        anomaly_rows,
        key=lambda x:
            x["anomaly_score"]
    )

    # -----------------------------------------------------
    # Result
    # -----------------------------------------------------

    return {

        "status":
            "ok",

        "model":
            "Isolation Forest",

        "model_type":
            "Unsupervised Anomaly Detection",

        "generated_at":
            datetime.now().isoformat(),

        "analysis_scope": {

            "source":
                source,

            "device_id":
                device_id
        },

        "training_records":
            total_records,

        "contamination":
            CONTAMINATION,

        "summary": {

            "anomaly_count":
                anomaly_count,

            "anomaly_ratio_percent":
                round(
                    anomaly_ratio,
                    2
                ),

            "normal_power_range_kw": {

                "minimum":
                    round(
                        normal_min,
                        3
                    ),

                "maximum":
                    round(
                        normal_max,
                        3
                    ),

                "average":
                    round(
                        normal_average,
                        3
                    )
            }
        },

        "anomalies":
            anomaly_rows
    }


# =========================================================
# Current AI Monitoring Status
# =========================================================

def get_current_ai_status():

    # -----------------------------------------------------
    # Latest reading determines analysis scope
    # -----------------------------------------------------

    latest_row = (
        get_latest_energy_reading()
    )

    if latest_row is None:

        return build_insufficient_response(
            training_records=0,
            message=(
                "No energy readings "
                "are available."
            )
        )

    latest_power = get_effective_power(
        latest_row
    )

    if latest_power is None:

        return build_insufficient_response(
            training_records=0,
            source=latest_row.data_source,
            device_id=latest_row.device_id,
            message=(
                "The latest reading "
                "does not contain "
                "a usable power value."
            )
        )

    # -----------------------------------------------------
    # Determine Sensor / Simulator Scope
    # -----------------------------------------------------

    scope = determine_analysis_scope(
        latest_row
    )

    source = scope[
        "source"
    ]

    device_id = scope[
        "device_id"
    ]

    # -----------------------------------------------------
    # Load isolated training data
    # -----------------------------------------------------

    rows = get_energy_values(
        source=source,
        device_id=device_id
    )

    valid_rows = []

    for row in rows:

        power = get_effective_power(
            row
        )

        if power is not None:

            valid_rows.append(
                (
                    row,
                    power
                )
            )

    # -----------------------------------------------------
    # Not enough sensor data
    # -----------------------------------------------------

    if len(valid_rows) < MIN_TRAINING_RECORDS:

        return {

            "status":
                "insufficient_data",

            "model":
                "Isolation Forest",

            "model_type":
                "Unsupervised Anomaly Detection",

            "generated_at":
                datetime.now().isoformat(),

            "analysis_scope": {

                "source":
                    source,

                "device_id":
                    device_id
            },

            "minimum_training_records":
                MIN_TRAINING_RECORDS,

            "training_records":
                len(valid_rows),

            "message":
                (
                    f"Only "
                    f"{len(valid_rows)} "
                    f"readings are available for "
                    f"{device_id or source}. "
                    f"At least "
                    f"{MIN_TRAINING_RECORDS} "
                    f"readings are required "
                    f"before AI anomaly detection "
                    f"is activated."
                ),

            "current_reading": {

                "reading_id":
                    latest_row.id,

                "device_id":
                    latest_row.device_id,

                "room_id":
                    latest_row.room_id,

                "source":
                    latest_row.data_source,

                "power_kw":
                    latest_power,

                "energy_kwh":
                    (
                        float(
                            latest_row.energy_kwh
                        )
                        if latest_row.energy_kwh
                        is not None
                        else None
                    ),

                # Compatibility
                "energy":
                    latest_power,

                "timestamp":
                    (
                        latest_row.timestamp.isoformat()
                        if latest_row.timestamp
                        else None
                    )
            },

            "ai_result":
                None,

            "learned_normal_pattern":
                None
        }

    # -----------------------------------------------------
    # Prepare Model Data
    # -----------------------------------------------------

    values = np.array(
        [
            [power]
            for row, power
            in valid_rows
        ]
    )

    # -----------------------------------------------------
    # Train Isolation Forest
    # -----------------------------------------------------

    model = IsolationForest(
        n_estimators=200,
        contamination=CONTAMINATION,
        random_state=42
    )

    model.fit(
        values
    )

    # -----------------------------------------------------
    # Latest Reading
    # -----------------------------------------------------

    latest_value = np.array(
        [
            [
                latest_power
            ]
        ]
    )

    # -----------------------------------------------------
    # AI Prediction
    # -----------------------------------------------------

    prediction = int(
        model.predict(
            latest_value
        )[0]
    )

    anomaly_score = float(
        model.decision_function(
            latest_value
        )[0]
    )

    is_anomaly = (
        prediction == -1
    )

    # -----------------------------------------------------
    # Classify Result
    # -----------------------------------------------------

    if is_anomaly:

        severity = classify_severity(
            anomaly_score
        )

        if severity == "High":

            ai_status = "Critical"

            message = (
                "A significant abnormal "
                "power consumption pattern "
                "has been detected."
            )

        elif severity == "Medium":

            ai_status = "Warning"

            message = (
                "Unusual power consumption "
                "has been detected."
            )

        else:

            ai_status = "Attention"

            message = (
                "The latest power reading "
                "slightly differs from the "
                "learned normal pattern."
            )

    else:

        severity = "None"

        ai_status = "Normal"

        message = (
            "Current power consumption "
            "is within the learned "
            "normal pattern."
        )

    # -----------------------------------------------------
    # Learned Normal Pattern
    # -----------------------------------------------------

    normal_predictions = (
        model.predict(
            values
        )
    )

    normal_values = [
        power
        for (
            row,
            power
        ), prediction_value
        in zip(
            valid_rows,
            normal_predictions
        )
        if prediction_value == 1
    ]

    if normal_values:

        normal_min = min(
            normal_values
        )

        normal_max = max(
            normal_values
        )

        normal_avg = (
            sum(normal_values)
            / len(normal_values)
        )

    else:

        normal_min = 0.0
        normal_max = 0.0
        normal_avg = 0.0

    # -----------------------------------------------------
    # Result
    # -----------------------------------------------------

    return {

        "status":
            "ok",

        "model":
            "Isolation Forest",

        "model_type":
            "Unsupervised Anomaly Detection",

        "generated_at":
            datetime.now().isoformat(),

        "analysis_scope": {

            "source":
                source,

            "device_id":
                device_id
        },

        "training_records":
            len(valid_rows),

        "current_reading": {

            "reading_id":
                latest_row.id,

            "device_id":
                latest_row.device_id,

            "room_id":
                latest_row.room_id,

            "source":
                latest_row.data_source,

            "power_kw":
                latest_power,

            "energy_kwh":
                (
                    float(
                        latest_row.energy_kwh
                    )
                    if latest_row.energy_kwh
                    is not None
                    else None
                ),

            # Keep this temporarily so alert_engine
            # and older code remain compatible.
            "energy":
                latest_power,

            "timestamp":
                (
                    latest_row.timestamp.isoformat()
                    if latest_row.timestamp
                    else None
                )
        },

        "ai_result": {

            "is_anomaly":
                is_anomaly,

            "anomaly_score":
                round(
                    anomaly_score,
                    4
                ),

            "severity":
                severity,

            "status":
                ai_status,

            "message":
                message
        },

        "learned_normal_pattern": {

            "unit":
                "kW",

            "minimum":
                round(
                    normal_min,
                    3
                ),

            "maximum":
                round(
                    normal_max,
                    3
                ),

            "average":
                round(
                    normal_avg,
                    3
                )
        }
    }