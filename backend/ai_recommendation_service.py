from datetime import datetime


def generate_energy_recommendations(
    optimization_result: dict
):

    recommendations = []

    plan = optimization_result.get(
        "plan",
        []
    )

    summary = optimization_result.get(
        "summary",
        {}
    )


    # ===============================
    # Battery Analysis
    # ===============================

    final_soc = float(
        summary.get(
            "final_battery_soc_percent",
            0
        )
    )

    saving = float(
        summary.get(
            "cost_saving_percent",
            0
        )
    )


    minimum_soc = 100

    for item in plan:

        soc = float(
            item.get(
                "battery_soc_after_percent",
                100
            )
        )

        minimum_soc = min(
            minimum_soc,
            soc
        )


    if minimum_soc <= 25:

        recommendations.append({

            "type":
                "battery_warning",

            "priority":
                "high",

            "title":
                "Low Battery Reserve",

            "message":
                (
                    f"Battery reached "
                    f"{minimum_soc}% SOC. "
                    "Further discharge is "
                    "not recommended."
                ),

            "reason":
                (
                    "Battery protection policy "
                    "detected low reserve."
                )
        })


    elif minimum_soc <= 35:

        recommendations.append({

            "type":
                "battery_management",

            "priority":
                "medium",

            "title":
                "Battery Reserve Maintained",

            "message":
                (
                    "Battery usage was optimized "
                    "while maintaining the preferred "
                    "35% reserve level."
                ),

            "reason":
                (
                    "Battery-aware MPC constraint "
                    "was applied."
                )
        })


    else:

        recommendations.append({

            "type":
                "battery_status",

            "priority":
                "low",

            "title":
                "Battery Condition Stable",

            "message":
                (
                    "Battery reserve remained "
                    "within the safe operating range."
                ),

            "reason":
                (
                    "No battery protection action "
                    "was required."
                )
        })


    # ===============================
    # Cost Saving Analysis
    # ===============================


    if saving >= 15:

        recommendations.append({

            "type":
                "energy_saving",

            "priority":
                "high",

            "title":
                "High Optimization Benefit",

            "message":
                (
                    f"Optimization reduced "
                    f"energy cost by {saving:.2f}%."
                ),

            "reason":
                (
                    "Economic MPC selected lower "
                    "cost operating periods."
                )
        })


    elif saving >= 5:

        recommendations.append({

            "type":
                "energy_saving",

            "priority":
                "medium",

            "title":
                "Energy Cost Reduced",

            "message":
                (
                    f"System achieved "
                    f"{saving:.2f}% estimated saving."
                ),

            "reason":
                (
                    "Energy scheduling improved "
                    "grid usage."
                )
        })


    # ===============================
    # Hourly Decisions
    # ===============================


    for item in plan:

        action = item.get(
            "recommended_action"
        )

        if action == "Delay Flexible Load":

            recommendations.append({

                "type":
                    "load_management",

                "priority":
                    "medium",

                "title":
                    "Flexible Load Delayed",

                "message":
                    (
                        "Some flexible loads were "
                        "postponed to a better period."
                    ),

                "reason":
                    item.get(
                        "reason"
                    )
            })


        elif action == "Use Battery During Peak Price":

            recommendations.append({

                "type":
                    "peak_management",

                "priority":
                    "high",

                "title":
                    "Battery Used During Peak",

                "message":
                    (
                        "Stored energy was used "
                        "during expensive electricity "
                        "periods."
                    ),

                "reason":
                    item.get(
                        "reason"
                    )
            })


    return {

        "generated_at":
            datetime.now().isoformat(),


        "summary":

            {

            "total_recommendations":
                len(
                    recommendations
                ),

            "final_battery_soc":
                final_soc,

            "estimated_cost_saving_percent":
                saving

            },


        "recommendations":
            recommendations

    }