"""Energy needs, daily grade and tips."""

ACTIVITY_LEVELS = {
    "Sedentary (desk job)":          1.2,
    "Lightly active (1-3x/week)":    1.375,
    "Moderately active (3-5x/week)": 1.55,
    "Very active (6-7x/week)":       1.725,
    "Extra active (physical job)":   1.9,
}


def calc_tdee(gender, age, weight_kg, height_cm, activity):
    """Mifflin-St Jeor BMR times an activity multiplier."""
    bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + (5 if gender == "Male" else -161)
    return round(bmr * ACTIVITY_LEVELS.get(activity, 1.55))


def nutrition_grade(consumed, goal, protein, fiber, carbs, fat):
    if consumed == 0:
        return None, None, None
    score = 0
    if goal > 0:
        d = abs(consumed - goal) / goal
        score += 40 if d <= 0.05 else 32 if d <= 0.10 else 22 if d <= 0.20 else 12 if d <= 0.35 else 4
    score += 20 if protein >= 50 else 15 if protein >= 35 else 10 if protein >= 20 else 5 if protein >= 10 else 0
    score += 20 if fiber >= 25 else 15 if fiber >= 18 else 10 if fiber >= 12 else 5 if fiber >= 6 else 0
    tm = carbs * 4 + protein * 4 + fat * 9
    if tm > 0:
        cp = carbs * 4 / tm * 100
        pp = protein * 4 / tm * 100
        fp = fat * 9 / tm * 100
        score += 20 if (45 <= cp <= 65 and 15 <= pp <= 35 and 20 <= fp <= 35) else \
                 12 if (40 <= cp <= 70 and 12 <= pp <= 40) else 5
    if score >= 85:
        return "A", "#2e7d32", "Excellent! Your nutrition is very well balanced."
    elif score >= 70:
        return "B", "#558b2f", "Good work! Small improvements could round it out."
    elif score >= 55:
        return "C", "#f57f17", "Decent. Try to improve protein and fiber intake."
    elif score >= 40:
        return "D", "#e65100", "Needs improvement — focus on balance and fiber."
    else:
        return "F", "#c62828", "Keep logging — you need more food or better balance."


def smart_tips(protein, fiber, cal, goal_cal, water_ml, meals_used):
    tips = []
    if protein < 30 and cal > 200:
        tips.append(("💪", "Low protein", "Try chicken, eggs, Greek yogurt, or lentils."))
    if fiber < 10 and cal > 200:
        tips.append(("🌿", "Low fiber", "Add vegetables, beans, or whole grains."))
    if water_ml < 1000:
        tips.append(("💧", "Low hydration", "Aim for at least 8 glasses (2 L) of water today."))
    if len(meals_used) < 2 and cal > 100:
        tips.append(("🍽️", "Log more meals", "Track all meals for accurate daily totals."))
    if goal_cal > 0 and cal > goal_cal * 1.1:
        tips.append(("⚠️", f"{round(cal - goal_cal)} kcal over goal", "Consider a lighter option next meal."))
    if not tips:
        tips.append(("✅", "On track!" if cal > 0 else "Start logging",
                     "Your nutrition looks balanced today!" if cal > 0 else "Search for a food above to get started."))
    return tips
