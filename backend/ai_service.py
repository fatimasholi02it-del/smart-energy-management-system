from datetime import datetime, timedelta

import pandas as pd
from sklearn.ensemble import IsolationForest

import models
from database import SessionLocal


def get_training_dataframe(minutes: int = 60) -> pd.DataFrame:
    db = SessionLocal()
    try:
        cutoff_time = datetime.now() - timedelta(minutes=minutes)

        rows = (
            db.query(models.EnergyReading)
            .filter(models.EnergyReading.timestamp >= cutoff_time)
            .order_by(models.EnergyReading.timestamp.asc())
            .all()
        )

        data = []
        for row in rows:
            ts = row.timestamp
            data.append({
                "room_id": row.room_id,
                "energy": float(row.energy),
                "hour": ts.hour,
                "minute": ts.minute,
                "day_of_week": ts.weekday()
            })

        return pd.DataFrame(data)

    finally:
        db.close()


def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    room_map = {
        "room_1": 1,
        "room_2": 2,
        "room_3": 3
    }

    prepared = df.copy()
    prepared["room_code"] = prepared["room_id"].map(room_map).fillna(0)

    return prepared[["energy", "hour", "minute", "day_of_week", "room_code"]]


def run_isolation_forest(minutes: int = 60):
    df = get_training_dataframe(minutes=minutes)

    if df.empty or len(df) < 10:
        return {
            "status": "no_data",
            "message": "Not enough recent data to train AI model."
        }

    feature_df = prepare_features(df)

    model = IsolationForest(
        n_estimators=100,
        contamination=0.05,
        random_state=42
    )

    model.fit(feature_df)

    predictions = model.predict(feature_df)
    scores = model.decision_function(feature_df)

    result_df = df.copy()
    result_df["prediction"] = predictions
    result_df["score"] = scores

    # prediction = -1 means anomaly
    anomalies = result_df[result_df["prediction"] == -1].copy()

    anomaly_results = []
    for _, row in anomalies.iterrows():
        anomaly_results.append({
            "room_id": row["room_id"],
            "energy": round(float(row["energy"]), 2),
            "hour": int(row["hour"]),
            "minute": int(row["minute"]),
            "score": round(float(row["score"]), 4),
            "anomaly_flag": True
        })

    return {
        "status": "ok",
        "model": "IsolationForest",
        "training_records": len(df),
        "anomaly_count": len(anomaly_results),
        "anomalies": anomaly_results
    }


def get_ai_room_summary(minutes: int = 60):
    df = get_training_dataframe(minutes=minutes)

    if df.empty or len(df) < 10:
        return {
            "status": "no_data",
            "message": "Not enough recent data to generate AI room summary."
        }

    feature_df = prepare_features(df)

    model = IsolationForest(
        n_estimators=100,
        contamination=0.05,
        random_state=42
    )

    model.fit(feature_df)

    predictions = model.predict(feature_df)
    scores = model.decision_function(feature_df)

    result_df = df.copy()
    result_df["prediction"] = predictions
    result_df["score"] = scores

    grouped = result_df.groupby("room_id")

    room_summaries = []
    for room_id, group in grouped:
        anomaly_count = int((group["prediction"] == -1).sum())
        total_count = int(len(group))
        anomaly_ratio = round((anomaly_count / total_count) * 100, 2) if total_count > 0 else 0

        if anomaly_ratio >= 40:
            risk_level = "High"
        elif anomaly_ratio >= 20:
            risk_level = "Medium"
        else:
            risk_level = "Low"

        avg_score = round(float(group["score"].mean()), 4)

        room_summaries.append({
            "room_id": room_id,
            "records_analyzed": total_count,
            "anomaly_count": anomaly_count,
            "anomaly_ratio_percent": anomaly_ratio,
            "average_ai_score": avg_score,
            "risk_level": risk_level
        })

    room_summaries.sort(key=lambda x: x["anomaly_ratio_percent"], reverse=True)

    return {
        "status": "ok",
        "model": "IsolationForest",
        "training_records": len(df),
        "rooms": room_summaries
    }