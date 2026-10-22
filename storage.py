"""Load and save each authenticated user's family rewards state."""

import json
import logging

import httpx2 as httpx

from data import INITIAL_STATE

log = logging.getLogger(f"app.{__name__}")
STATE_KEY_PREFIX = "family_green_rewards_state_"
PROFILE_KEY_PREFIX = "family_green_rewards_profiles_"
SETTINGS_KEY_PREFIX = "family_green_rewards_settings_"
APP_THEME_KEY = "family_green_rewards_theme_mode"
DEFAULT_SETTINGS = {
    "theme_mode": "system",
    "notify_daily_limit": True,
    "notify_walking_milestones": True,
    "notify_solar_claim_results": True,
    "notify_bonus_events": True,
    "notify_household_redemptions": True,
    "consent_walking_data": False,
    "consent_solar_data": False,
}


def _initial_state():
    return json.loads(json.dumps(INITIAL_STATE))


def _new_member_state():
    return _initial_state()


def _remove_legacy_seed_activity(state):
    """Remove the old Greenfield demo activity without erasing real activity."""
    claims = state.get("solar_claims", [])
    seed_ids = {"seed-approved", "seed-rejected"}
    if not isinstance(claims, list) or not any(
        isinstance(claim, dict) and claim.get("id") in seed_ids
        for claim in claims
    ):
        return state

    state["solar_claims"] = [
        claim for claim in claims
        if not isinstance(claim, dict) or claim.get("id") not in seed_ids
    ]
    if (
        state.get("points") == 1280
        and state.get("points_earned") == 1500
        and state.get("points_spent") == 220
    ):
        state.update({"points": 0, "points_earned": 0, "points_spent": 0})
    if state.get("total_steps") == 48600:
        state["total_steps"] = 0
    if state.get("family_name") == "The Greenfield Family":
        state["family_name"] = "Household not linked"
    seed_redemptions = {
        ("Reusable Cup Coffee", "2026-09-21"),
        ("Market Tote", "2026-08-08"),
    }
    state["redemptions"] = [
        redemption for redemption in state.get("redemptions", [])
        if not isinstance(redemption, dict)
        or (redemption.get("reward"), redemption.get("date")) not in seed_redemptions
    ]
    return state


def _state_key(user_id, profile_id="owner"):
    suffix = str(user_id) if profile_id == "owner" else f"{user_id}_{profile_id}"
    return f"{STATE_KEY_PREFIX}{suffix}"


def _profiles_key(user_id):
    return f"{PROFILE_KEY_PREFIX}{user_id}"


def _settings_key(user_id, profile_id="owner"):
    return f"{SETTINGS_KEY_PREFIX}{user_id}_{profile_id}"


async def load_settings(preferences, user_id, profile_id="owner"):
    raw = await preferences.get(_settings_key(user_id, profile_id))
    if raw is None and profile_id == "owner":
        raw = await preferences.get(f"{SETTINGS_KEY_PREFIX}{user_id}")
    settings = dict(DEFAULT_SETTINGS)
    if raw:
        try:
            saved = json.loads(raw)
            if isinstance(saved, dict):
                settings.update(saved)
        except (TypeError, json.JSONDecodeError):
            log.warning("Saved app settings were invalid; using defaults")
    return settings


async def save_settings(preferences, user_id, settings, profile_id="owner"):
    await preferences.set(_settings_key(user_id, profile_id), json.dumps(settings))


async def delete_settings(preferences, user_id, profile_id):
    await preferences.remove(_settings_key(user_id, profile_id))


async def load_profiles(preferences, user_id, owner_name):
    raw = await preferences.get(_profiles_key(user_id))
    if raw:
        try:
            profiles = json.loads(raw)
            if isinstance(profiles, list) and profiles and profiles[0].get("id") == "owner":
                return profiles
        except (TypeError, json.JSONDecodeError, AttributeError):
            log.warning("Saved household profiles were invalid; creating an owner profile")

    profiles = [{"id": "owner", "name": owner_name or "Owner", "role": "owner"}]
    await preferences.set(_profiles_key(user_id), json.dumps(profiles))
    return profiles


async def save_profiles(preferences, user_id, profiles):
    await preferences.set(_profiles_key(user_id), json.dumps(profiles))


async def create_profile_state(preferences, user_id, profile_id):
    state = _new_member_state()
    await preferences.set(_state_key(user_id, profile_id), json.dumps(state))
    return state


async def delete_profile_state(preferences, user_id, profile_id):
    await preferences.remove(_state_key(user_id, profile_id))


async def load_state(preferences, database, user_id, access_token, profile_id="owner"):
    # The legacy JSON table is read-only after the secure relational schema is
    # applied. Prefer this device's state; only import a legacy row once when
    # there is no local copy. New activity is never written to that table.
    raw = await preferences.get(_state_key(user_id, profile_id))
    if raw:
        try:
            state = json.loads(raw)
            state = _remove_legacy_seed_activity(state)
            for key, value in INITIAL_STATE.items():
                state.setdefault(key, json.loads(json.dumps(value)))
            await preferences.set(_state_key(user_id, profile_id), json.dumps(state))
            return state, None
        except (TypeError, json.JSONDecodeError):
            log.warning("Saved local state was invalid; restoring seed state")

    if profile_id != "owner":
        state = _new_member_state()
        await preferences.set(_state_key(user_id, profile_id), json.dumps(state))
        return state, None

    try:
        state = await database.load_state(user_id, access_token)
        if state is None:
            state = _initial_state()
            log.info("No legacy state found; starting local prototype state")
        else:
            log.info("Imported read-only legacy state for this account")
            state = _remove_legacy_seed_activity(state)
            for key, value in INITIAL_STATE.items():
                state.setdefault(key, json.loads(json.dumps(value)))
    except httpx.HTTPError as error:
        log.info("Legacy state is not available; starting local prototype state: %s", error)
        state = _initial_state()

    await preferences.set(_state_key(user_id), json.dumps(state))
    return state, None


async def save_state(preferences, database, user_id, access_token, state, profile_id="owner"):
    # This screen still contains prototype activity logic. Keep it device-local
    # until its controls are migrated to the protected relational RPCs.
    await preferences.set(_state_key(user_id, profile_id), json.dumps(state))
    return None
