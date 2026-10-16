"""
Daily needs from a shopper's profile: BMI, calories (Mifflin-St Jeor × activity, adjusted for the goal), protein, water.
General sports-nutrition guidance, not medical advice -- the answer always says so.
"""
from __future__ import annotations

from dataclasses import dataclass

ACTIVITY = {"low": 1.375, "medium": 1.55, "high": 1.725}
PROTEIN_G_PER_KG = {"muscle": (1.8, 2.2), "weight_loss": (2.0, 2.4), "endurance": (1.4, 1.7), "health": (1.2, 1.6)}
CALORIE_SHIFT = {"muscle": 1.10, "weight_loss": 0.80, "endurance": 1.05, "health": 1.0}
REQUIRED = ("height", "weight", "age", "goal")


@dataclass
class Needs:
    bmi: float
    bmi_band: str
    calories: int
    protein_low: int
    protein_high: int
    water_l: float
    creatine_g: int | None


def missing(profile: dict) -> list[str]:
    return [k for k in REQUIRED if not profile.get(k)]


def compute(profile: dict) -> Needs | None:
    if missing(profile):
        return None
    h, w, age, goal = profile["height"], float(profile["weight"]), int(profile["age"]), profile["goal"]
    sex_shift = -161 if profile.get("sex") == "f" else 5
    bmr = 10 * w + 6.25 * h - 5 * age + sex_shift
    tdee = bmr * ACTIVITY.get(profile.get("activity") or "medium", 1.55)
    bmi = round(w / (h / 100) ** 2, 1)
    band = "under" if bmi < 18.5 else "normal" if bmi < 25 else "over" if bmi < 30 else "obese"
    lo, hi = PROTEIN_G_PER_KG.get(goal, (1.4, 1.8))
    return Needs(
        bmi=bmi, bmi_band=band, calories=int(round(tdee * CALORIE_SHIFT.get(goal, 1.0), -1)),
        protein_low=int(round(w * lo)), protein_high=int(round(w * hi)), water_l=round(w * 0.035, 1),
        creatine_g=None if goal == "health" or age < 18 else (5 if w >= 80 else 3),
    )
