import random
import statistics
import numpy as np


def monte_carlo_prediction(values, simulations=1000):
    """
    Professional Monte Carlo Energy Prediction Model
    """

    if not values:
        return None

    # =========================
    # 1. BASIC STATISTICS
    # =========================
    mean = statistics.mean(values)
    stdev = statistics.stdev(values) if len(values) > 1 else 0.1

    # =========================
    # 2. TREND DETECTION
    # =========================
    if len(values) >= 5:
        recent_trend = (values[-1] - values[0]) / len(values)
    else:
        recent_trend = 0

    # =========================
    # 3. MONTE CARLO SIMULATION
    # =========================
    results = []

    for _ in range(simulations):
        noise = random.gauss(0, stdev)
        trend_effect = recent_trend * random.uniform(0.8, 1.2)

        simulated_value = mean + noise + trend_effect
        results.append(max(0, simulated_value))  # no negative energy

    # =========================
    # 4. CONFIDENCE INTERVALS
    # =========================
    results.sort()

    min_val = results[int(simulations * 0.05)]
    max_val = results[int(simulations * 0.95)]
    expected = statistics.mean(results)

    # =========================
    # 5. RISK ANALYSIS
    # =========================
    high_threshold = mean * 1.3

    high_risk_prob = len([r for r in results if r > high_threshold]) / simulations

    if high_risk_prob > 0.6:
        risk_level = "High"
    elif high_risk_prob > 0.3:
        risk_level = "Medium"
    else:
        risk_level = "Low"

    # =========================
    # 6. OUTPUT STRUCTURE
    # =========================
    return {
        "expected_energy": round(expected, 2),
        "min": round(min_val, 2),
        "max": round(max_val, 2),
        "risk_level": risk_level,
        "confidence": round(1 - (stdev / (mean + 0.01)), 2),
        "simulations": simulations
    }