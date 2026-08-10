import csv
import os
from datetime import datetime, timedelta

import numpy as np

from sklearn.ensemble import (
    RandomForestRegressor
)

from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score
)

from database import SessionLocal

import models

from ml_data_service import (
    get_ml_data_status
)


SYNTHETIC_FILE = (
    "ml_training_data.csv"
)

MIN_TRAINING_RECORDS = 100
MIN_REAL_SENSOR_RECORDS = 500

FORECAST_HOURS = 6


# =========================================================
# Synthetic Training Data
# =========================================================

def load_synthetic_training_data():

    if not os.path.exists(
        SYNTHETIC_FILE
    ):
        return []

    rows = []

    with open(
        SYNTHETIC_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        reader = csv.DictReader(
            file
        )

        for row in reader:

            try:

                timestamp = (
                    datetime.fromisoformat(
                        row["timestamp"]
                    )
                )

                energy = float(
                    row["energy"]
                )

                rows.append({
                    "timestamp":
                        timestamp,

                    "energy":
                        energy
                })

            except Exception:
                continue

    return sorted(
        rows,
        key=lambda x:
            x["timestamp"]
    )


# =========================================================
# Database Training Data
# =========================================================

def load_database_training_data(
    source: str
):

    db = SessionLocal()

    try:

        rows = (
            db.query(
                models.EnergyReading.energy,
                models.EnergyReading.timestamp
            )
            .filter(
                models.EnergyReading.data_source
                == source,

                models.EnergyReading.energy.isnot(
                    None
                ),

                models.EnergyReading.timestamp.isnot(
                    None
                )
            )
            .order_by(
                models.EnergyReading.timestamp.asc()
            )
            .all()
        )

        result = []

        for row in rows:

            result.append({
                "timestamp":
                    row.timestamp,

                "energy":
                    float(
                        row.energy
                    )
            })

        return result

    finally:
        db.close()


# =========================================================
# Training Source Selection
# =========================================================

def choose_training_source(
    requested_source: str
):

    requested_source = (
        requested_source
        or "auto"
    ).lower()

    allowed_sources = {
        "auto",
        "synthetic",
        "simulator",
        "sensor"
    }

    if (
        requested_source
        not in allowed_sources
    ):

        return {
            "status":
                "error",

            "message":
                (
                    "Invalid source. Use "
                    "auto, synthetic, "
                    "simulator, or sensor."
                )
        }

    # =====================================================
    # Auto mode
    # =====================================================

    if requested_source == "auto":

        data_status = (
            get_ml_data_status()
        )

        recommended_source = (
            data_status.get(
                "recommended_training_source"
            )
        )

        if (
            recommended_source
            in [
                None,
                "none"
            ]
        ):

            return {
                "status":
                    "insufficient_data",

                "requested_source":
                    "auto",

                "message":
                    (
                        "No training source "
                        "is currently ready."
                    )
            }

        selected_source = (
            recommended_source
        )

    else:

        selected_source = (
            requested_source
        )

    # =====================================================
    # Load selected data
    # =====================================================

    if selected_source == "synthetic":

        rows = (
            load_synthetic_training_data()
        )

        minimum_required = (
            MIN_TRAINING_RECORDS
        )

    elif selected_source == "simulator":

        rows = (
            load_database_training_data(
                "simulator"
            )
        )

        minimum_required = (
            MIN_TRAINING_RECORDS
        )

    else:

        rows = (
            load_database_training_data(
                "sensor"
            )
        )

        minimum_required = (
            MIN_REAL_SENSOR_RECORDS
        )

        # =================================================
        # Sensor data requires count + time span
        # =================================================

        data_status = (
            get_ml_data_status()
        )

        sensor_status = (
            data_status
            .get(
                "sources",
                {}
            )
            .get(
                "sensor",
                {}
            )
        )

        if not sensor_status.get(
            "ready",
            False
        ):

            return {
                "status":
                    "insufficient_data",

                "requested_source":
                    requested_source,

                "selected_source":
                    "sensor",

                "training_records":
                    sensor_status.get(
                        "records",
                        len(rows)
                    ),

                "minimum_required":
                    sensor_status.get(
                        "minimum_records",
                        MIN_REAL_SENSOR_RECORDS
                    ),

                "data_span_days":
                    sensor_status.get(
                        "data_span_days",
                        0.0
                    ),

                "minimum_span_days":
                    sensor_status.get(
                        "minimum_span_days",
                        3.0
                    ),

                "record_requirement_met":
                    sensor_status.get(
                        "record_requirement_met",
                        False
                    ),

                "span_requirement_met":
                    sensor_status.get(
                        "span_requirement_met",
                        False
                    ),

                "message":
                    (
                        "Real sensor data is "
                        "not ready for model "
                        "training yet."
                    )
            }

    # =====================================================
    # General record-count validation
    # =====================================================

    if len(rows) < minimum_required:

        return {
            "status":
                "insufficient_data",

            "requested_source":
                requested_source,

            "selected_source":
                selected_source,

            "training_records":
                len(rows),

            "minimum_required":
                minimum_required,

            "message":
                (
                    f"Not enough "
                    f"{selected_source} "
                    f"training data."
                )
        }

    return {
        "status":
            "ok",

        "selected_source":
            selected_source,

        "rows":
            rows
    }


# =========================================================
# Feature Engineering
# =========================================================

def build_features(
    rows
):

    X = []
    y = []

    energy_values = [
        row["energy"]
        for row in rows
    ]

    for index in range(
        5,
        len(rows)
    ):

        current = (
            rows[index]
        )

        timestamp = (
            current[
                "timestamp"
            ]
        )

        previous_energy = (
            energy_values[
                index - 1
            ]
        )

        recent_values = (
            energy_values[
                index - 5:index
            ]
        )

        rolling_average = (
            sum(
                recent_values
            )
            / len(
                recent_values
            )
        )

        rolling_min = min(
            recent_values
        )

        rolling_max = max(
            recent_values
        )

        X.append([
            timestamp.hour,

            timestamp.weekday(),

            previous_energy,

            rolling_average,

            rolling_min,

            rolling_max
        ])

        y.append(
            current[
                "energy"
            ]
        )

    return (
        np.array(
            X,
            dtype=float
        ),

        np.array(
            y,
            dtype=float
        )
    )


# =========================================================
# Train Model
# =========================================================

def train_ml_model(
    source: str = "auto"
):

    source_result = (
        choose_training_source(
            source
        )
    )

    if (
        source_result.get(
            "status"
        )
        != "ok"
    ):

        return source_result

    selected_source = (
        source_result[
            "selected_source"
        ]
    )

    rows = (
        source_result[
            "rows"
        ]
    )

    X, y = build_features(
        rows
    )

    if len(X) < 20:

        return {
            "status":
                "insufficient_data",

            "selected_source":
                selected_source,

            "training_records":
                len(rows),

            "message":
                (
                    "Not enough usable "
                    "samples after "
                    "feature engineering."
                )
        }

    split_index = int(
        len(X)
        * 0.80
    )

    X_train = (
        X[:split_index]
    )

    y_train = (
        y[:split_index]
    )

    X_test = (
        X[split_index:]
    )

    y_test = (
        y[split_index:]
    )

    model = (
        RandomForestRegressor(
            n_estimators=300,

            max_depth=12,

            min_samples_leaf=2,

            random_state=42,

            n_jobs=-1
        )
    )

    model.fit(
        X_train,
        y_train
    )

    predictions = (
        model.predict(
            X_test
        )
    )

    mae = (
        mean_absolute_error(
            y_test,
            predictions
        )
    )

    mse = (
        mean_squared_error(
            y_test,
            predictions
        )
    )

    rmse = (
        mse ** 0.5
    )

    r2 = (
        r2_score(
            y_test,
            predictions
        )
    )

    return {
        "status":
            "ok",

        "selected_source":
            selected_source,

        "model":
            model,

        "rows":
            rows,

        "training_samples":
            len(
                X_train
            ),

        "testing_samples":
            len(
                X_test
            ),

        "metrics": {
            "mae":
                round(
                    float(
                        mae
                    ),
                    4
                ),

            "rmse":
                round(
                    float(
                        rmse
                    ),
                    4
                ),

            "r2":
                round(
                    float(
                        r2
                    ),
                    4
                )
        }
    }


# =========================================================
# Generate Future Forecast
# =========================================================

def get_ml_load_forecast(
    forecast_hours: int =
        FORECAST_HOURS,

    source: str =
        "auto"
):

    training_result = (
        train_ml_model(
            source=source
        )
    )

    if (
        training_result.get(
            "status"
        )
        != "ok"
    ):

        return training_result

    model = (
        training_result[
            "model"
        ]
    )

    rows = (
        training_result[
            "rows"
        ]
    )

    selected_source = (
        training_result[
            "selected_source"
        ]
    )

    latest_values = [
        row["energy"]
        for row in rows[
            -5:
        ]
    ]

    previous_value = (
        latest_values[-1]
    )

    rolling_values = list(
        latest_values
    )

    now = datetime.now()

    forecasts = []

    for i in range(
        1,
        forecast_hours + 1
    ):

        target_time = (
            now.replace(
                minute=0,
                second=0,
                microsecond=0
            )
            + timedelta(
                hours=i
            )
        )

        recent_window = (
            rolling_values[
                -5:
            ]
        )

        rolling_average = (
            sum(
                recent_window
            )
            / len(
                recent_window
            )
        )

        rolling_min = min(
            recent_window
        )

        rolling_max = max(
            recent_window
        )

        features = np.array([
            [
                target_time.hour,

                target_time.weekday(),

                previous_value,

                rolling_average,

                rolling_min,

                rolling_max
            ]
        ])

        prediction = float(
            model.predict(
                features
            )[0]
        )

        prediction = round(
            max(
                prediction,
                0.0
            ),
            3
        )

        forecasts.append({
            "forecast_time":
                target_time.isoformat(),

            "predicted_load_kw":
                prediction
        })

        previous_value = (
            prediction
        )

        rolling_values.append(
            prediction
        )

    return {
        "status":
            "ok",

        "model":
            "Random Forest Regressor",

        "model_type":
            "Supervised Machine Learning",

        "requested_source":
            source,

        "selected_training_source":
            selected_source,

        "real_sensor_training":
            selected_source
            == "sensor",

        "generated_at":
            datetime.now().isoformat(),

        "training_records":
            len(
                rows
            ),

        "training_samples":
            training_result[
                "training_samples"
            ],

        "testing_samples":
            training_result[
                "testing_samples"
            ],

        "evaluation":
            training_result[
                "metrics"
            ],

        "forecast_hours":
            len(
                forecasts
            ),

        "hours":
            forecasts
    }