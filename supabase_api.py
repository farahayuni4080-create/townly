"""Supabase Auth and REST/RPC access for household and admin screens."""

from urllib.parse import quote

import httpx2 as httpx

SUPABASE_URL = "https://ntxyecwqplictlctczyo.supabase.co"
SUPABASE_PUBLISHABLE_KEY = "sb_publishable_ch8LGcPAAH4S-NSsyL0VGA_gDzn70Tl"
AUTH_URL = f"{SUPABASE_URL}/auth/v1"
REST_URL = f"{SUPABASE_URL}/rest/v1"
STATE_TABLE_URL = f"{REST_URL}/family_green_rewards_user_state"


class SupabaseDatabase:
    def __init__(self):
        self.headers = {
            "apikey": SUPABASE_PUBLISHABLE_KEY,
            "Content-Type": "application/json",
        }

    async def sign_up(self, email, password, display_name):
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{AUTH_URL}/signup",
                headers=self.headers,
                json={
                    "email": email,
                    "password": password,
                    "data": {
                        "display_name": display_name,
                        "full_name": display_name,
                    },
                },
            )
            response.raise_for_status()
            return response.json()

    async def sign_in(self, email, password):
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{AUTH_URL}/token",
                params={"grant_type": "password"},
                headers=self.headers,
                json={"email": email, "password": password},
            )
            response.raise_for_status()
            return response.json()

    async def send_password_recovery(self, email):
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{AUTH_URL}/recover",
                headers=self.headers,
                json={"email": email},
            )
            response.raise_for_status()

    async def verify_password_recovery(self, email, code):
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{AUTH_URL}/verify",
                headers=self.headers,
                json={"type": "recovery", "email": email, "token": code},
            )
            response.raise_for_status()
            return response.json()

    async def sign_out(self, access_token):
        headers = {
            **self.headers,
            "Authorization": f"Bearer {access_token}",
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{AUTH_URL}/logout",
                headers=headers,
            )
            response.raise_for_status()

    async def sign_out_all(self, access_token):
        headers = {
            **self.headers,
            "Authorization": f"Bearer {access_token}",
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{AUTH_URL}/logout",
                params={"scope": "global"},
                headers=headers,
            )
            response.raise_for_status()

    async def update_password(self, access_token, new_password):
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.put(
                f"{AUTH_URL}/user",
                headers=self._user_headers(access_token),
                json={"password": new_password},
            )
            response.raise_for_status()
            return response.json()

    def _user_headers(self, access_token):
        return {
            **self.headers,
            "Authorization": f"Bearer {access_token}",
        }

    async def load_profile(self, user_id, access_token):
        rows = await self.select_rows(
            "profiles",
            {
                "select": "id,display_name",
                "id": f"eq.{user_id}",
                "limit": "1",
            },
            access_token,
        )
        return rows[0] if rows else None

    async def load_state(self, user_id, access_token):
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                STATE_TABLE_URL,
                params={"select": "state", "user_id": f"eq.{user_id}"},
                headers=self._user_headers(access_token),
            )
            response.raise_for_status()
            rows = response.json()
        return rows[0]["state"] if rows else None

    async def save_state(self, user_id, access_token, state):
        headers = {
            **self._user_headers(access_token),
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                STATE_TABLE_URL,
                params={"on_conflict": "user_id"},
                headers=headers,
                json={"user_id": user_id, "state": state},
            )
            response.raise_for_status()

    async def rpc(self, function_name, payload, access_token):
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.post(
                f"{REST_URL}/rpc/{function_name}",
                headers=self._user_headers(access_token),
                json=payload,
            )
            response.raise_for_status()
            if not response.content:
                return None
            try:
                return response.json()
            except ValueError:
                return None

    async def load_running_rewards(self, access_token):
        return await self.rpc("get_my_running_rewards", {}, access_token)

    async def submit_running_run(self, distance_km, duration, activity_date, access_token):
        return await self.rpc(
            "submit_running_run",
            {
                "p_distance_km": distance_km,
                "p_duration": duration,
                "p_activity_date": activity_date,
            },
            access_token,
        )

    async def redeem_reward(self, reward_id, access_token):
        return await self.rpc(
            "redeem_reward",
            {"p_reward_id": reward_id},
            access_token,
        )

    async def get_myrewards_vouchers(self, access_token):
        result = await self.rpc("get_myrewards_vouchers", {}, access_token)
        return result if isinstance(result, list) else []

    async def sync_myrewards_vouchers(self, vouchers, transactions, access_token):
        result = await self.rpc(
            "sync_myrewards_vouchers",
            {"p_vouchers": vouchers, "p_transactions": transactions},
            access_token,
        )
        return result if isinstance(result, list) else []

    async def redeem_myrewards_reward(self, reward_id, access_token):
        return await self.rpc(
            "redeem_myrewards_reward",
            {"p_reward_id": reward_id},
            access_token,
        )

    async def load_household_solar_claims(self, household_id, access_token):
        result = await self.rpc(
            "get_household_solar_claims",
            {"p_household_id": household_id},
            access_token,
        )
        if isinstance(result, dict):
            return result.get("claims", [])
        return result if isinstance(result, list) else []

    async def upload_solar_evidence(self, household_id, file_name, image_bytes, mime_type, access_token):
        safe_name = quote(file_name, safe="")
        object_path = f"{household_id}/{safe_name}"
        headers = {
            **self._user_headers(access_token),
            "Content-Type": mime_type,
            "x-upsert": "false",
        }
        async with httpx.AsyncClient(timeout=40) as client:
            response = await client.post(
                f"{SUPABASE_URL}/storage/v1/object/solar-evidence/{quote(object_path, safe='/')}",
                headers=headers,
                content=image_bytes,
            )
            response.raise_for_status()
        return object_path

    async def submit_solar_claim(
        self, household_id, claim_month, claim_year, solar_generation_kwh,
        evidence_image_path, access_token,
    ):
        return await self.rpc(
            "submit_solar_claim",
            {
                "p_household_id": household_id,
                "p_claim_month": claim_month,
                "p_claim_year": claim_year,
                "p_solar_generation_kwh": solar_generation_kwh,
                "p_evidence_image_path": evidence_image_path,
            },
            access_token,
        )

    async def is_current_admin(self, access_token):
        return bool(await self.rpc("is_current_admin", {}, access_token))

    async def select_rows(self, table, params, access_token):
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.get(
                f"{REST_URL}/{table}",
                params=params,
                headers=self._user_headers(access_token),
            )
            response.raise_for_status()
            return response.json()

    async def load_account_profile_settings(self, access_token, profile_key=None):
        params = {"select": "*", "order": "updated_at.asc"}
        if profile_key is not None:
            params["profile_key"] = f"eq.{profile_key}"
        return await self.select_rows("account_profile_settings", params, access_token)

    async def save_account_profile_settings(self, account_id, profile_key, values, access_token):
        row = {
            "account_id": account_id,
            "profile_key": profile_key,
            **values,
        }
        headers = {
            **self._user_headers(access_token),
            "Prefer": "resolution=merge-duplicates,return=representation",
        }
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.post(
                f"{REST_URL}/account_profile_settings",
                params={"on_conflict": "account_id,profile_key"},
                headers=headers,
                json=row,
            )
            response.raise_for_status()
            return response.json()

    async def update_auth_profile(self, user_id, values, access_token):
        return await self.patch_rows(
            "profiles", {"id": f"eq.{user_id}"}, values, access_token
        )

    async def delete_account_profile_settings(self, profile_key, access_token):
        await self.delete_rows(
            "account_profile_settings", {"profile_key": f"eq.{profile_key}"}, access_token
        )

    async def create_household(self, name, access_token):
        return await self.rpc(
            "create_household",
            {"p_name": name, "p_member_limit": 5},
            access_token,
        )

    async def invite_family_member(self, household_id, email, access_token):
        return await self.rpc(
            "invite_family_member",
            {"p_household_id": household_id, "p_email": email},
            access_token,
        )

    async def leave_household(self, household_id, access_token):
        return await self.rpc(
            "leave_household",
            {"p_household_id": household_id},
            access_token,
        )

    async def remove_household_member(self, household_id, user_id, access_token):
        return await self.rpc(
            "remove_family_member_by_owner",
            {"p_household_id": household_id, "p_user_id": user_id},
            access_token,
        )

    async def load_family_invitations(self, access_token):
        invitations = await self.rpc("list_family_invitations", {}, access_token)
        if isinstance(invitations, list):
            return invitations
        if isinstance(invitations, dict):
            return invitations.get("invitations", [])
        return []

    async def respond_to_family_invitation(self, invitation_id, accept, access_token):
        return await self.rpc(
            "respond_to_family_invitation",
            {"p_invitation_id": invitation_id, "p_accept": accept},
            access_token,
        )

    async def load_family_information(self, user_id, access_token):
        memberships = await self.select_rows(
            "household_members",
            {
                "select": "household_id,user_id,member_role,joined_at",
                "user_id": f"eq.{user_id}",
                "order": "joined_at.asc",
            },
            access_token,
        )
        households = []
        for membership in memberships:
            household_params = {
                "select": "id,name,address,owner_id",
                "id": f"eq.{membership['household_id']}",
                "limit": "1",
            }
            try:
                household_rows = await self.select_rows(
                    "households", household_params, access_token
                )
            except httpx.HTTPError:
                household_params["select"] = "id,name,owner_id"
                household_rows = await self.select_rows(
                    "households", household_params, access_token
                )
            if not household_rows:
                continue
            household = household_rows[0]
            household_members = await self.select_rows(
                "household_members",
                {
                    "select": "household_id,user_id,member_role,joined_at",
                    "household_id": f"eq.{household['id']}",
                    "order": "joined_at.asc",
                },
                access_token,
            )
            user_ids = list(dict.fromkeys(item["user_id"] for item in household_members))
            related_profiles = []
            if user_ids:
                ids = ",".join(user_ids)
                profile_params = {
                    "select": "id,display_name,full_name,avatar_key",
                    "id": f"in.({ids})",
                }
                try:
                    related_profiles = await self.select_rows(
                        "profiles", profile_params, access_token
                    )
                except httpx.HTTPError:
                    profile_params["select"] = "id,display_name"
                    related_profiles = await self.select_rows(
                        "profiles", profile_params, access_token
                    )
            profile_by_id = {item["id"]: item for item in related_profiles}
            household["member_role"] = membership.get("member_role", "member")
            household["members"] = [
                {
                    **profile_by_id.get(item["user_id"], {}),
                    "id": item["user_id"],
                    "role": item.get("member_role", "member"),
                }
                for item in household_members
            ]
            households.append(household)
        return households

    async def insert_row(self, table, row, access_token):
        headers = {**self._user_headers(access_token), "Prefer": "return=representation"}
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.post(
                f"{REST_URL}/{table}", headers=headers, json=row
            )
            response.raise_for_status()
            return response.json()

    async def patch_rows(self, table, filters, values, access_token):
        headers = {**self._user_headers(access_token), "Prefer": "return=representation"}
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.patch(
                f"{REST_URL}/{table}",
                params=filters,
                headers=headers,
                json=values,
            )
            response.raise_for_status()
            return response.json()

    async def delete_rows(self, table, filters, access_token):
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.delete(
                f"{REST_URL}/{table}",
                params=filters,
                headers=self._user_headers(access_token),
            )
            response.raise_for_status()

    async def signed_evidence_url(self, object_path, access_token):
        encoded_path = quote(object_path, safe="/")
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.post(
                f"{SUPABASE_URL}/storage/v1/object/sign/activity-evidence/{encoded_path}",
                headers=self._user_headers(access_token),
                json={"expiresIn": 600},
            )
            response.raise_for_status()
            signed_path = response.json().get("signedURL", "")
        if signed_path.startswith("http"):
            return signed_path
        if signed_path.startswith("/storage/v1/"):
            return f"{SUPABASE_URL}{signed_path}"
        return f"{SUPABASE_URL}/storage/v1{signed_path}"
