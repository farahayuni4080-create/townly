"""Catalog content and an empty starting state for the Townly rewards app."""

OFFERS = [
    {"id": "coffee", "name": "Reusable Cup Coffee", "merchant": "Grounded Café", "points": 180, "stock": 12, "category": "Local", "icon": "Icons.LOCAL_CAFE"},
    {"id": "market", "name": "$5 Market Voucher", "merchant": "Harvest Corner Market", "points": 420, "stock": 8, "category": "Local", "icon": "Icons.ECO"},
    {"id": "bike", "name": "Bike Tune-up", "merchant": "Pedal & Path", "points": 650, "stock": 4, "category": "Local", "icon": "Icons.DIRECTIONS_BIKE"},
    {"id": "bottle", "name": "Eco Bottle", "merchant": "Terra Goods", "points": 300, "stock": 16, "category": "Local", "icon": "Icons.WATER_DROP"},
    {"id": "transit", "name": "Transit Pass Credit", "merchant": "CityGo", "points": 500, "stock": 20, "category": "Big Brand", "icon": "Icons.DIRECTIONS_TRANSIT"},
    {"id": "plant", "name": "Plant-Based Meal", "merchant": "GreenBite", "points": 350, "stock": 10, "category": "Big Brand", "icon": "Icons.RESTAURANT"},
]

INITIAL_STATE = {
    "family_name": "Household not linked",
    "points": 0,
    "points_earned": 0,
    "points_spent": 0,
    "total_steps": 0,
    "daily_steps": {},
    "daily_points": {},
    "running_submissions": [],
    "solar_claims": [],
    "redemptions": [],
    "stocks": {offer["id"]: offer["stock"] for offer in OFFERS},
}
