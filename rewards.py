"""Business rules for walking rewards and offer redemption."""

import math
from datetime import date, datetime

DAILY_STEP_LIMIT = 10_000
POINTS_PER_100_STEPS = 1
RUNNING_DAILY_IMAGE_LIMIT = 2
RUNNING_POINTS_PER_KM = 10
# A hard safety bound against decimal-point OCR errors such as 4.16 -> 416.40.
MAX_RUNNING_DISTANCE_KM = 100


def is_valid_running_distance(distance_km):
    """Reject non-finite, non-positive, or implausible per-submission distances."""
    try:
        return math.isfinite(float(distance_km)) and 0 < float(distance_km) <= MAX_RUNNING_DISTANCE_KM
    except (TypeError, ValueError):
        return False


def award_running_run(state, distance_km, duration, run_date):
    """Record a confirmed run and award points for each complete kilometre."""
    submissions = state.setdefault("running_submissions", [])
    if sum(item.get("upload_date", item.get("date")) == run_date for item in submissions) >= RUNNING_DAILY_IMAGE_LIMIT:
        return None
    if not is_valid_running_distance(distance_km):
        return None
    distance_km = float(distance_km)

    points = math.floor(distance_km) * RUNNING_POINTS_PER_KM
    record = {
        "id": f"run-{datetime.now().timestamp()}",
        "date": run_date,
        "upload_date": run_date,
        "distance_km": round(distance_km, 3),
        "duration": duration.strip(),
        "points": points,
    }
    submissions.insert(0, record)
    state["points"] += points
    state["points_earned"] += points
    daily_points = state.setdefault("daily_points", {})
    daily_points[run_date] = int(daily_points.get(run_date, 0)) + points
    return record



def redeem_offer(state, offer):
    stock = state["stocks"].get(offer["id"], offer["stock"])
    if stock <= 0:
        return "This reward is out of stock."
    if state["points"] < offer["points"]:
        return "You need more points to redeem this reward."
    state["points"] -= offer["points"]
    state["points_spent"] += offer["points"]
    state["stocks"][offer["id"]] = stock - 1
    state["redemptions"].insert(0, {
        "reward": offer["name"],
        "merchant": offer["merchant"],
        "points": offer["points"],
        "date": date.today().isoformat(),
    })
    return f"Redeemed {offer['name']}!"
