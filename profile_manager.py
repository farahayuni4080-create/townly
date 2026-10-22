"""Load and manage local household member profiles."""

import uuid

from storage import (
    create_profile_state,
    delete_profile_state,
    load_profiles,
    load_state,
    save_profiles,
)


class HouseholdProfiles:
    def __init__(self, preferences, user_id, profiles, states):
        self.preferences = preferences
        self.user_id = user_id
        self.profiles = profiles
        self.states = states

    @classmethod
    async def load(cls, preferences, database, user_id, access_token, owner_name):
        profiles = await load_profiles(preferences, user_id, owner_name)
        owner_state, _ = await load_state(
            preferences, database, user_id, access_token, profile_id="owner"
        )
        states = {"owner": owner_state}
        for profile in profiles:
            if profile["id"] != "owner":
                states[profile["id"]], _ = await load_state(
                    preferences,
                    database,
                    user_id,
                    access_token,
                    profile_id=profile["id"],
                )
        return cls(preferences, user_id, profiles, states)

    async def add(self, name, role="child"):
        profile_name = (name or "").strip()
        if not profile_name:
            return "Enter a name for the new family profile."
        if any(profile["name"].casefold() == profile_name.casefold() for profile in self.profiles):
            return "A family profile with that name already exists."
        if len(self.profiles) >= 10:
            return "This household has reached the 10-profile limit."

        profile = {
            "id": uuid.uuid4().hex,
            "name": profile_name,
            "full_name": profile_name,
            "birthday": "",
            "role": role if role in ("adult", "child") else "child",
            "avatar": "avatar_leaf.svg",
        }
        self.profiles.append(profile)
        self.states[profile["id"]] = await create_profile_state(
            self.preferences, self.user_id, profile["id"]
        )
        await save_profiles(self.preferences, self.user_id, self.profiles)
        return ""

    async def update_profile(self, profile_id, name=None, full_name=None, avatar=None, birthday=None):
        profile = next((item for item in self.profiles if item["id"] == profile_id), None)
        if not profile:
            return "Profile not found."
        if name is not None:
            profile_name = name.strip()
            if not profile_name:
                return "Profile name cannot be empty."
            if any(
                item["id"] != profile_id
                and item["name"].casefold() == profile_name.casefold()
                for item in self.profiles
            ):
                return "Another family profile already uses that name."
            profile["name"] = profile_name
        if full_name is not None:
            profile_full_name = full_name.strip()
            if not profile_full_name:
                return "Full name cannot be empty."
            profile["full_name"] = profile_full_name
        if avatar is not None:
            profile["avatar"] = avatar
        if birthday is not None:
            profile["birthday"] = birthday
        await save_profiles(self.preferences, self.user_id, self.profiles)
        return ""

    async def remove(self, profile_id):
        profile = next((item for item in self.profiles if item["id"] == profile_id), None)
        if not profile or profile.get("role") == "owner":
            return None
        self.profiles.remove(profile)
        self.states.pop(profile_id, None)
        await delete_profile_state(self.preferences, self.user_id, profile_id)
        await save_profiles(self.preferences, self.user_id, self.profiles)
        return profile
