"""Authenticated Townly application shell."""

import asyncio
import base64
import json
import logging
import uuid
from datetime import date
from urllib.parse import unquote

import flet as ft
import httpx2 as httpx

from components import (
    apply_theme,
    brand_color,
    canvas_color,
    ink_color,
    panel,
    surface_color,
    surface_tint,
)

from rewards import (
    MAX_RUNNING_DISTANCE_KM,
    RUNNING_DAILY_IMAGE_LIMIT,
    is_valid_running_distance,
    redeem_offer,
)
from myrewards import (
    available_points,
    ensure_state as ensure_myrewards_state,
    load_catalog as load_myrewards_catalog,
    merge_cloud_vouchers,
    new_state as new_myrewards_state,
)
from solar_claims import has_successful_claim, is_suspicious, parse_solar_reading, validate_claim
from solar_ocr import extract_solar_reading
from walking_ocr import (
    OCR_HTML,
    make_recognition_script,
    parse_running_stats,
    recognize_in_browser,
)
from profile_manager import HouseholdProfiles
from storage import (
    APP_THEME_KEY,
    create_profile_state,
    delete_settings,
    load_settings,
    save_profiles,
    save_settings,
    save_state,
)
from views import dashboard, family_profiles, profile_dialogs, profile_settings, rewards as rewards_view, solar, walking

log = logging.getLogger(f"app.{__name__}")


async def build(page, preferences, database, session, on_logout, role_check_note=None):
    user = session["user"]
    user_id = user["id"]
    access_token = session["access_token"]
    user_metadata = user.get("user_metadata") or {}
    auth_display_name = (
        user_metadata.get("display_name") or user_metadata.get("full_name") or ""
    ).strip()
    try:
        account_profile = await database.load_profile(user_id, access_token) or {}
    except httpx.HTTPError as error:
        log.info("Could not load the signed-in account display name: %s", error)
        account_profile = {}
    owner_name = (
        (account_profile.get("display_name") or auth_display_name or "Owner").strip()
    )
    household = await HouseholdProfiles.load(
        preferences, database, user_id, access_token, owner_name or "Owner"
    )
    profiles = household.profiles
    states_by_profile = household.states
    owner_profile = next((item for item in profiles if item.get("id") == "owner"), None)
    if owner_profile is not None:
        owner_profile["name"] = owner_name
        owner_profile["full_name"] = (
            user_metadata.get("full_name") or owner_profile.get("full_name") or owner_name
        )
    profile_settings_rows = []
    profile_settings_error = ""
    profile_settings_table_available = False
    try:
        profile_settings_rows = await database.load_account_profile_settings(access_token)
        profile_settings_table_available = True
    except httpx.HTTPError as error:
        log.info("Cloud profile settings unavailable: %s", error)
        profile_settings_error = "Cloud profile settings need the profile-settings SQL migration; local settings remain available."

    settings_by_profile = {}
    for profile in profiles:
        profile_id = profile["id"]
        settings_by_profile[profile_id] = await load_settings(
            preferences, user_id, profile_id
        )
    for row in profile_settings_rows:
        profile_id = row.get("profile_key")
        profile = next((item for item in profiles if item["id"] == profile_id), None)
        if profile is None and profile_id and profile_id != "owner":
            profile = {
                "id": profile_id,
                "name": row.get("display_name") or "Family member",
                "full_name": row.get("full_name") or row.get("display_name") or "Family member",
                "role": row.get("member_role", "child"),
                "avatar": row.get("avatar_key", "avatar_leaf.svg"),
            }
            profiles.append(profile)
            states_by_profile[profile_id] = await create_profile_state(
                preferences, user_id, profile_id
            )
            settings_by_profile[profile_id] = await load_settings(
                preferences, user_id, profile_id
            )
        if profile is None:
            continue
        profile["name"] = row.get("display_name") or profile.get("name", "Member")
        profile["full_name"] = row.get("full_name") or profile.get("full_name", profile["name"])
        profile["avatar"] = row.get("avatar_key") or profile.get("avatar", "avatar_leaf.svg")
        profile["birthday"] = row.get("birthday") or profile.get("birthday", "")
        profile["role"] = row.get("member_role") or profile.get("role", "child")
        if isinstance(row.get("settings"), dict):
            settings_by_profile[profile_id].update(row["settings"])
    await save_profiles(preferences, user_id, profiles)
    try:
        family_households = await database.load_family_information(user_id, access_token)
        family_load_error = ""
    except httpx.HTTPError as error:
        log.info("Household directory unavailable: %s", error)
        family_households = []
        family_load_error = "Run the supplied Supabase profile-settings migration to load household addresses."
    current_household = family_households[0] if family_households else None
    try:
        family_invitations = await database.load_family_invitations(access_token)
        invitation_load_error = ""
    except httpx.HTTPError as error:
        log.info("Family invitations unavailable: %s", error)
        family_invitations = []
        invitation_load_error = "Supabase does not have the invitation RPCs yet. Run supabase_family_invitations_migration.sql in the SQL Editor for this same project, then reload the Family tab. Invitations cannot be sent or received until that migration is applied."
    account_role = (
        current_household.get("member_role", "owner") if current_household else "owner"
    )
    family_context = {
        "households": family_households,
        "household": current_household,
        "local_profiles": profiles,
        "family_name": (
            current_household.get("name") if current_household else "Household not linked"
        ),
        "account_role": account_role,
        "load_error": family_load_error,
        "invitations": family_invitations,
        "invitation_load_error": invitation_load_error,
        "account_email": user.get("email", ""),
    }
    settings = settings_by_profile["owner"]
    theme_mode = apply_theme(
        page, settings.get("theme_mode", "system"), page.platform_brightness
    )
    await preferences.set(APP_THEME_KEY, theme_mode)
    state = states_by_profile["owner"]
    owner_state = state
    owner_state["points"] = 0
    owner_state["points_earned"] = 0
    owner_state["points_spent"] = 0
    owner_state["running_submissions"] = []
    owner_state["redemptions"] = []
    owner_state["stocks"] = {}

    myrewards_catalog = load_myrewards_catalog()
    myrewards_storage_key = f"myrewards_state_{user_id}"
    saved_myrewards_state = await preferences.get(myrewards_storage_key)
    try:
        myrewards_state = json.loads(saved_myrewards_state) if saved_myrewards_state else None
    except (TypeError, json.JSONDecodeError):
        log.warning("Saved MyRewards wallet was invalid; restoring a fresh wallet")
        myrewards_state = None
    if not isinstance(myrewards_state, dict):
        myrewards_state = new_myrewards_state(user_id, owner_name, 0)
    ensure_myrewards_state(myrewards_state, user_id, owner_name, 0)
    selected_myrewards = {"cloud_ready": False, "cloud_error": ""}
    active_profile = {"id": "owner"}
    selected = {
        "screen": 0,
        "filter": "All",
        "notice": role_check_note or "",
        "running_ocr_status": "",
        "running_ocr_counter": 0,
        "running_ocr_job_id": None,
        "running_ocr_timeout_task": None,
        "ocr_pending": None,
        "solar_claims": [],
        "solar_form": {
            "month": date.today().month,
            "year": date.today().year,
            "image_bytes": None,
            "image_name": "",
            "mime_type": "",
            "kwh": None,
            "points": 0,
            "detected_month": None,
            "detected_year": None,
            "detected_period": "",
            "message": "",
            "message_kind": "",
            "busy": False,
            "suspicious": False,
        },
        "walking_chart_period": "week",
        "cloud_loaded": False,
        "cloud_error": "",
        "cloud_offers": [],
        "cloud_busy": False,
        "running_quota_ready": False,
        "running_quota_error": "",
        "myrewards_view": {},
    }
    mounted = {"value": False}
    root = ft.Container(expand=True, padding=18)
    is_android = not page.web and page.platform == ft.PagePlatform.ANDROID
    # Web OCR uses the browser worker APIs; Android uses the native WebView.
    ocr_supported = is_android or page.web
    file_picker = ft.FilePicker()
    ocr_webview = None
    ocr_ready = {"value": False, "failed": False}

    def show_notice(message):
        selected["notice"] = message
        render()

    def read_selected_image(image_file):
        """Return usable JPG/PNG bytes and MIME type on web and native clients."""
        image_bytes = image_file.bytes
        if not image_bytes and image_file.path and not page.web:
            try:
                with open(image_file.path, "rb") as selected_image:
                    image_bytes = selected_image.read()
            except OSError:
                log.exception("Could not read selected image from native file path")
                return None, None, "Could not read that photo. Please choose it again."
        if not image_bytes:
            return None, None, "The selected photo could not be read. Please choose it again."
        if len(image_bytes) > 15 * 1024 * 1024:
            return None, None, "Choose an image smaller than 15 MB."

        name_extension = (
            image_file.name.rsplit(".", 1)[-1].lower()
            if "." in image_file.name else ""
        )
        if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return image_bytes, "image/png", ""
        if image_bytes.startswith(b"\xff\xd8\xff"):
            return image_bytes, "image/jpeg", ""
        if name_extension == "png":
            return image_bytes, "image/png", ""
        if name_extension in {"jpg", "jpeg"}:
            return image_bytes, "image/jpeg", ""
        return None, None, "Choose a JPG or PNG photo."

    def supabase_error_detail(error):
        response = getattr(error, "response", None)
        if response is None:
            return str(error) or "Network request failed"
        try:
            body = response.json()
        except Exception:
            body = None
        if isinstance(body, dict):
            message = body.get("message") or body.get("error_description") or body.get("error")
            details = body.get("details")
            hint = body.get("hint")
            parts = [str(item) for item in (message, details, hint) if item]
            if parts:
                return " — ".join(parts)[:360]
        try:
            return (response.text or str(error))[:360]
        except Exception:
            return str(error)[:360]

    def dismiss_notice():
        selected["notice"] = ""
        render()

    async def refresh_cloud_rewards():
        try:
            payload = await database.load_running_rewards(access_token)
            if not isinstance(payload, dict):
                raise ValueError("Supabase returned an invalid running rewards response")
            runs = payload.get("running_submissions") or []
            offers = payload.get("rewards") or []
            redemptions = payload.get("redemptions") or []
            owner_state["points"] = int(payload.get("points_balance", 0))
            owner_state["points_earned"] = int(payload.get("points_earned", 0))
            owner_state["points_spent"] = int(payload.get("points_spent", 0))
            quota_ready = "running_uploads_today" in payload and "running_upload_date" in payload
            selected["running_quota_ready"] = quota_ready
            owner_state["running_quota_ready"] = quota_ready
            if quota_ready:
                owner_state["running_uploads_today"] = int(payload.get("running_uploads_today", 0))
                owner_state["running_upload_date"] = str(payload.get("running_upload_date", ""))
                selected["running_quota_error"] = ""
            else:
                selected["running_quota_error"] = (
                    "Apply supabase_running_upload_timezone_limit_migration.sql in Supabase "
                    "to enable the Malaysia-time upload limit."
                )
            owner_state["running_quota_error"] = selected["running_quota_error"]
            owner_state["running_submissions"] = [
                {
                    "id": item.get("id"),
                    "date": str(item.get("date", "")),
                    "upload_date": str(item.get("upload_date", item.get("date", ""))),
                    "distance_km": float(item.get("distance_km", 0)),
                    "duration": item.get("duration", ""),
                    "points": int(item.get("points", 0)),
                }
                for item in runs
            ]
            owner_state["redemptions"] = [
                {
                    "reward": item.get("reward", "Reward"),
                    "merchant": item.get("merchant", "Townly"),
                    "points": int(item.get("points", 0)),
                    "date": str(item.get("date", "")),
                    "status": item.get("status", "requested"),
                }
                for item in redemptions
            ]
            owner_state["stocks"] = {
                str(item.get("id")): int(item.get("stock", 0)) for item in offers
            }
            selected["cloud_offers"] = [
                {
                    "id": str(item.get("id")),
                    "name": item.get("name", "Reward"),
                    "merchant": item.get("merchant", "Townly"),
                    "description": item.get("description", ""),
                    "points": int(item.get("points", 0)),
                    "stock": int(item.get("stock", 0)),
                    "category": item.get("category", "Rewards"),
                    "active": bool(item.get("active", True)),
                }
                for item in offers
            ]
            selected["cloud_loaded"] = True
            selected["cloud_error"] = ""
            try:
                cloud_vouchers = await database.get_myrewards_vouchers(access_token)
                if myrewards_state.get("vouchers"):
                    # Merge this device's prior wallet into the shared wallet.
                    cloud_vouchers = await database.sync_myrewards_vouchers(
                        myrewards_state.get("vouchers", []),
                        myrewards_state.get("pointsTransactions", []),
                        access_token,
                    )
                myrewards_state["vouchers"] = []
                myrewards_state["pointsTransactions"] = []
                myrewards_state["localPointsSpent"] = 0
                merge_cloud_vouchers(myrewards_state, cloud_vouchers)
                selected_myrewards["cloud_ready"] = True
                selected_myrewards["cloud_error"] = ""
                await preferences.set(myrewards_storage_key, json.dumps(myrewards_state))
            except httpx.HTTPError as wallet_error:
                selected_myrewards["cloud_ready"] = False
                selected_myrewards["cloud_error"] = supabase_error_detail(wallet_error)
                log.warning("MyRewards wallet could not load from Supabase: %s", selected_myrewards["cloud_error"])
            myrewards_state["user"]["pointsBalance"] = int(owner_state.get("points", 0))
            return True
        except (httpx.HTTPError, ValueError, TypeError) as error:
            status_code = getattr(getattr(error, "response", None), "status_code", None)
            detail = supabase_error_detail(error)
            log.warning(
                "Could not load Supabase running rewards (status=%s): %s",
                status_code,
                detail,
            )
            if status_code == 404:
                selected["cloud_error"] = (
                    "Supabase is missing the running rewards migration. Apply "
                    "supabase_running_rewards_migration.sql in the SQL Editor, then reload."
                )
            else:
                selected["cloud_error"] = "Could not load points and rewards from Supabase. Check the database setup and connection."
            return False
        finally:
            if mounted["value"]:
                render()
                page.update()

    def new_running_ocr_request():
        selected["running_ocr_counter"] += 1
        request_id = selected["running_ocr_counter"]
        selected["running_ocr_job_id"] = request_id
        return request_id

    def finish_running_ocr(request_id):
        if request_id is None or selected.get("running_ocr_job_id") != request_id:
            return False
        timeout_task = selected.get("running_ocr_timeout_task")
        selected["running_ocr_timeout_task"] = None
        selected["running_ocr_job_id"] = None
        if timeout_task is not None:
            timeout_task.cancel()
        return True

    async def expire_running_ocr(request_id):
        await asyncio.sleep(60)
        if selected.get("running_ocr_job_id") != request_id:
            return
        selected["running_ocr_job_id"] = None
        selected["running_ocr_timeout_task"] = None
        pending = selected.get("ocr_pending")
        if pending and len(pending) == 4 and pending[3] == request_id:
            selected["ocr_pending"] = None
        selected["running_ocr_status"] = ""
        log.warning("Running screenshot OCR timed out after 60 seconds")
        show_notice("Could not read the screenshot within 60 seconds. Check your connection and try a clearer or smaller JPG/PNG.")
        if is_android and ocr_webview:
            # Discard any hung JavaScript/Tesseract work so a retry can start cleanly.
            ocr_ready["value"] = False
            ocr_ready["failed"] = False
            try:
                await ocr_webview.load_html(
                    OCR_HTML,
                    base_url="https://cdn.jsdelivr.net/",
                )
            except Exception:
                log.exception("Could not reset Android OCR after its timeout")
                ocr_ready["failed"] = True

    async def dispatch_pending_ocr():
        pending = selected.get("ocr_pending")
        if not pending or not ocr_webview:
            return
        image_bytes, mime_type, mode = pending[:3]
        request_id = pending[3] if len(pending) > 3 else None
        if ocr_ready["failed"]:
            selected["ocr_pending"] = None
            if mode == "solar":
                form = selected["solar_form"]
                form.update({
                    "message": "Solar OCR could not initialize. Check your connection and try again.",
                    "message_kind": "error",
                })
                render()
            else:
                finish_running_ocr(request_id)
                selected["running_ocr_status"] = ""
                show_notice("OCR could not initialize on this device. Check your internet connection and restart the app.")
            return
        if not ocr_ready["value"]:
            return
        selected["ocr_pending"] = None
        try:
            image_base64 = base64.b64encode(image_bytes).decode("ascii")
            await ocr_webview.run_javascript(
                make_recognition_script(image_base64, mime_type, mode, request_id)
            )
        except Exception:
            log.exception("Could not start %s OCR on this Android device", mode)
            if mode == "solar":
                form = selected["solar_form"]
                form.update({
                    "message": "Solar OCR could not start. Please try again.",
                    "message_kind": "error",
                })
                render()
            else:
                finish_running_ocr(request_id)
                selected["running_ocr_status"] = ""
                show_notice("Could not start running OCR on this Android device. Please try again.")

    async def submit_running_submission(distance, duration):
        if selected["cloud_busy"]:
            return
        if active_profile["id"] != "owner":
            selected["running_ocr_status"] = ""
            show_notice("Switch to the account owner profile to save running points to Supabase.")
            return
        selected["cloud_busy"] = True
        selected["running_ocr_status"] = "Saving your points…"
        render()
        if mounted["value"]:
            page.update()
        try:
            saved = await database.submit_running_run(
                distance,
                duration,
                date.today().isoformat(),
                access_token,
            )
            if not isinstance(saved, dict):
                raise ValueError("Supabase returned an invalid running submission")
            saved_distance = float(saved.get("distance_km", distance))
            saved_points = int(saved.get("points", 0))
            refreshed = await refresh_cloud_rewards()
            if not refreshed:
                # The points RPC already succeeded. Keep the just-confirmed
                # balance visible even if the separate read/refresh RPC fails.
                saved_run = {
                    "id": saved.get("id"),
                    "date": str(saved.get("date", date.today().isoformat())),
                    "upload_date": str(saved.get("upload_date", date.today().isoformat())),
                    "distance_km": saved_distance,
                    "duration": str(saved.get("duration", duration)),
                    "points": saved_points,
                }
                owner_state["points"] = int(owner_state.get("points", 0)) + saved_points
                owner_state["points_earned"] = int(owner_state.get("points_earned", 0)) + saved_points
                owner_state["running_uploads_today"] = int(
                    saved.get("uploads_today", owner_state.get("running_uploads_today", 0) + 1)
                )
                owner_state["running_upload_date"] = str(saved.get("upload_date", date.today().isoformat()))
                current_runs = owner_state.setdefault("running_submissions", [])
                if not any(item.get("id") == saved_run["id"] for item in current_runs):
                    current_runs.insert(0, saved_run)
            selected["running_ocr_status"] = ""
            notice = (
                f"Run saved to Supabase · {saved_distance:.2f} km · "
                f"{saved_points} points added to your account."
            )
            if not refreshed:
                notice += " The balance refresh failed, but the saved points will load next time."
            show_notice(notice)
        except httpx.HTTPError as error:
            status_code = getattr(getattr(error, "response", None), "status_code", None)
            detail = supabase_error_detail(error)
            log.warning(
                "Could not save running points in Supabase (status=%s): %s",
                status_code,
                detail,
            )
            if "Daily running screenshot limit reached" in detail:
                message = "You have used both running screenshot uploads for today (Malaysia time). Try again after midnight."
            elif "points_ledger_entry_type_check" in detail:
                message = (
                    "Supabase's points ledger is not yet configured to accept running awards. "
                    "Run the updated supabase_running_rewards_migration.sql in the SQL Editor, "
                    "then retry; this rejected run was not added."
                )
            elif status_code == 404:
                message = (
                    "Supabase could not find the running-points function. Run the latest "
                    "supabase_running_rewards_migration.sql in the SQL Editor."
                )
            elif status_code in (401, 403):
                message = f"Supabase rejected this account's points write: {detail}"
            elif status_code in (400, 422):
                message = f"Supabase rejected the run data or ledger write: {detail}"
            elif status_code is not None:
                message = f"Supabase points write failed (HTTP {status_code}): {detail}"
            else:
                message = (
                    "Could not confirm the Supabase points write. Check the connection "
                    f"and retry. Details: {detail}"
                )
            selected["running_ocr_status"] = ""
            show_notice(message)
        except (TypeError, ValueError) as error:
            log.warning("Invalid Supabase running submission response: %s", error)
            selected["running_ocr_status"] = ""
            show_notice("Supabase returned an invalid response; points were not confirmed as saved.")
        finally:
            selected["cloud_busy"] = False
            if mounted["value"]:
                render()
                page.update()

    def on_ocr_page_ended(event):
        # Page load completion does not guarantee the external Tesseract script
        # has finished loading. Wait for the explicit JS-ready console signal.
        log.info("Android OCR WebView page loaded; waiting for OCR engine readiness")

    def on_ocr_resource_error(event):
        detail = str(getattr(event, "data", "") or "OCR WebView resource could not be loaded")
        log.warning("Android OCR WebView resource failed: %s", detail)
        if not ocr_ready["value"]:
            ocr_ready["failed"] = True
            if selected.get("ocr_pending"):
                asyncio.create_task(dispatch_pending_ocr())

    def on_ocr_console(event):
        message = event.message or ""
        if message == "FGR_OCR_READY":
            ocr_ready["value"] = True
            ocr_ready["failed"] = False
            log.info("Android Tesseract OCR engine is ready")
            if selected.get("ocr_pending"):
                asyncio.create_task(dispatch_pending_ocr())
            return
        if message.startswith("FGR_OCR_INIT_ERROR:"):
            detail = unquote(message.split(":", 1)[1])
            ocr_ready["failed"] = True
            ocr_ready["value"] = False
            log.error("Android Tesseract OCR initialization failed: %s", detail)
            return
        prefix = "FGR_OCR_RESULT:"
        if not message.startswith(prefix):
            return
        try:
            result = json.loads(unquote(message[len(prefix):]))
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            log.warning("Could not decode OCR result: %s", error)
            active_request_id = selected.get("running_ocr_job_id")
            if active_request_id is not None:
                finish_running_ocr(active_request_id)
                selected["running_ocr_status"] = ""
                show_notice("OCR returned unreadable data. Please try a clearer screenshot.")
            return
        if result.get("mode") == "solar":
            handle_solar_ocr_result(result)
        else:
            request_id = result.get("request_id")
            if not finish_running_ocr(request_id):
                log.info("Ignoring a late running OCR result for request %r", request_id)
                return
            handle_ocr_result(result)

    def handle_ocr_result(result):
        if result.get("error"):
            error_text = str(result["error"])
            log.warning("Running screenshot OCR failed: %s", error_text)
            selected["running_ocr_status"] = ""
            if any(
                marker in error_text.lower()
                for marker in ("failed to fetch", "network", "load failed", "download")
            ):
                show_notice("Could not download the OCR engine or English data. Check your connection and retry.")
            else:
                show_notice("The OCR engine could not process this image. Try selecting the screenshot again.")
            return
        raw_text = str(result.get("text", "")) if "text" in result else ""
        raw_time_text = str(result.get("time_text", ""))
        raw_distance_text = str(result.get("distance_text", ""))
        if "text" in result:
            result = parse_running_stats(
                raw_text,
                distance_text=raw_distance_text,
                time_text=raw_time_text,
            )
        distance = result.get("distance_km")
        duration = result.get("duration")
        log.debug("OCR parsed running stats: distance=%r, duration=%r", distance, duration)
        if distance is not None and not is_valid_running_distance(distance):
            log.warning(
                "Rejected implausible OCR distance %.3f km (maximum %.1f km)",
                distance,
                MAX_RUNNING_DISTANCE_KM,
            )
            selected["running_ocr_status"] = ""
            show_notice(
                f"OCR read {distance:g} km, which is above the {MAX_RUNNING_DISTANCE_KM:g} km per-run safety limit. "
                "No points were added. Please upload a clearer screenshot; check the decimal point."
            )
            return
        if distance is None or not duration:
            log.warning(
                "OCR found incomplete run stats (text length=%d, Time label=%s, km unit=%s)",
                len(raw_text),
                "time" in raw_text.lower(),
                "km" in raw_text.lower(),
            )
            log.debug(
                "Targeted OCR crop output lengths: time=%d, distance=%d",
                len(raw_time_text),
                len(raw_distance_text),
            )
            selected["running_ocr_status"] = ""
            show_notice("Could not read both the distance and run time. No points were added; use a clear screenshot showing the Time and Distance values.")
            return
        selected["running_ocr_status"] = "Calculating points…"
        render()
        asyncio.create_task(submit_running_submission(distance, duration))

    def handle_solar_ocr_result(result):
        form = selected["solar_form"]
        if result.get("error"):
            form.update({"kwh": None, "points": 0, "message": str(result["error"]), "message_kind": "error"})
            render()
            return
        if "kwh" not in result:
            result = parse_solar_reading(str(result.get("text", "")))
            if result.get("error"):
                form.update({"kwh": None, "points": 0, "message": result["error"], "message_kind": "error"})
                render()
                return
        amount, points, issue = validate_claim(
            result.get("kwh"), form.get("month"), form.get("year")
        )
        if issue:
            form.update({"kwh": None, "points": 0, "message": issue, "message_kind": "error"})
            render()
            return
        detected_month = result.get("month")
        detected_year = result.get("year")
        if detected_month and detected_year:
            form["month"] = detected_month
            form["year"] = detected_year
        form.update({
            "kwh": str(amount),
            "points": points,
            "detected_month": detected_month,
            "detected_year": detected_year,
            "detected_period": (
                f"{date(detected_year, detected_month, 1):%B %Y}"
                if detected_month and detected_year else ""
            ),
            "suspicious": is_suspicious(amount),
            "message": "Reading extracted. Saving the claim and points to Supabase…",
            "message_kind": "success",
        })
        render()
        asyncio.create_task(submit_solar_claim())

    if is_android:
        from flet_webview import WebView

        ocr_webview = WebView(
            width=1,
            height=1,
            on_page_ended=on_ocr_page_ended,
            on_web_resource_error=on_ocr_resource_error,
            on_console_message=on_ocr_console,
        )

    async def choose_run_screenshot():
        if active_profile["id"] != "owner":
            show_notice("Switch to the account owner profile to save running points to Supabase.")
            return
        if not selected["cloud_loaded"]:
            show_notice(selected["cloud_error"] or "Connecting to Supabase points and rewards. Please wait and try again.")
            return
        if not await refresh_cloud_rewards():
            show_notice("Could not check your upload allowance. Check your connection and try again.")
            return
        if not selected.get("running_quota_ready"):
            show_notice(selected.get("running_quota_error") or "Update the Supabase running rewards migration before uploading.")
            return
        uploads_today = int(owner_state.get("running_uploads_today", 0))
        if uploads_today >= RUNNING_DAILY_IMAGE_LIMIT:
            show_notice("You have used both running screenshot uploads for today (Malaysia time). Try again after midnight.")
            return
        if not ocr_supported:
            show_notice("Screenshot OCR is not available on this platform.")
            return
        if is_android and not ocr_webview:
            show_notice("The Android image picker is not ready. Restart the app and try again.")
            return
        try:
            files = await file_picker.pick_files(
                dialog_title="Choose a running screenshot",
                file_type=ft.FilePickerFileType.IMAGE,
                allowed_extensions=["jpg", "jpeg", "png"],
                allow_multiple=False,
                with_data=True,
            )
        except Exception as error:
            log.exception("Could not open running screenshot picker")
            show_notice(f"Could not open the image picker: {str(error)[:180]}")
            return
        if not files:
            log.info("Running screenshot selection cancelled")
            return
        image_file = files[0]
        image_bytes, mime_type, image_error = read_selected_image(image_file)
        if image_error:
            show_notice(image_error)
            return
        log.info(
            "Selected running screenshot (%s, %d bytes, %s)",
            image_file.name,
            len(image_bytes),
            mime_type,
        )
        if page.web:
            selected["ocr_pending"] = None
            request_id = new_running_ocr_request()
            selected["running_ocr_status"] = "Extracting run details and calculating points…"
            render()
            if mounted["value"]:
                page.update()
            try:
                image_base64 = base64.b64encode(image_bytes).decode("ascii")
                result = await asyncio.wait_for(
                    recognize_in_browser(image_base64, mime_type), timeout=60
                )
                if finish_running_ocr(request_id):
                    handle_ocr_result(result)
            except asyncio.TimeoutError:
                finish_running_ocr(request_id)
                selected["running_ocr_status"] = ""
                show_notice("Could not read the screenshot within 60 seconds. Check your connection and try a clearer or smaller JPG/PNG.")
            except Exception:
                log.exception("Browser running screenshot OCR failed")
                finish_running_ocr(request_id)
                selected["running_ocr_status"] = ""
                show_notice("Browser OCR could not start. Check your connection and try again.")
            return

        request_id = new_running_ocr_request()
        selected["ocr_pending"] = (image_bytes, mime_type, "running", request_id)
        selected["running_ocr_timeout_task"] = asyncio.create_task(
            expire_running_ocr(request_id)
        )
        selected["running_ocr_status"] = "Extracting run details and calculating points…"
        render()
        if mounted["value"]:
            page.update()
        await dispatch_pending_ocr()

    if is_android:
        async def initialize_ocr_webview():
            if ocr_ready["value"] or ocr_ready["failed"]:
                return
            try:
                log.info("Initializing Android Tesseract OCR WebView")
                await ocr_webview.load_html(
                    OCR_HTML,
                    base_url="https://cdn.jsdelivr.net/",
                )
            except Exception:
                log.exception("Could not initialize Android OCR WebView")
                ocr_ready["failed"] = True
                selected["running_ocr_status"] = ""
                show_notice("Could not initialize on-device OCR on this Android device.")

    async def switch_profile(profile_id):
        nonlocal state, settings
        if profile_id not in states_by_profile:
            return
        active_profile["id"] = profile_id
        state = states_by_profile[profile_id]
        settings = settings_by_profile.get(profile_id, {})
        theme_mode = apply_theme(
            page, settings.get("theme_mode", "system"), page.platform_brightness
        )
        await preferences.set(APP_THEME_KEY, theme_mode)
        current_profile = next(item for item in profiles if item["id"] == profile_id)
        profile_button.content = ft.Text(current_profile["name"])
        selected["screen"] = 0
        selected["notice"] = ""
        render()
        if mounted["value"]:
            page.update()

    async def add_profile(name, role="child"):
        message = await household.add(name, role)
        if message:
            show_notice(message)
            return
        added_profile = profiles[-1]
        settings_by_profile[added_profile["id"]] = await load_settings(
            preferences, user_id, added_profile["id"]
        )
        family_context["local_profiles"] = profiles
        selected["notice"] = f"{(name or '').strip()}'s profile was added."
        render()

    async def refresh_family_data():
        nonlocal family_households, current_household
        family_households = await database.load_family_information(user_id, access_token)
        current_household = family_households[0] if family_households else None
        family_invitations = await database.load_family_invitations(access_token)
        family_context.update(
            {
                "households": family_households,
                "household": current_household,
                "family_name": current_household.get("name") if current_household else "Household not linked",
                "account_role": current_household.get("member_role", "owner") if current_household else "owner",
                "invitations": family_invitations,
                "invitation_load_error": "",
            }
        )

    async def create_family(name):
        family_name = (name or "").strip()
        if not family_name:
            show_notice("Enter a family name first.")
            return
        try:
            await database.create_household(family_name, access_token)
            await refresh_family_data()
        except httpx.HTTPError as error:
            detail = error.response.text.lower() if error.response else ""
            log.warning("Family creation failed: %s", error)
            if "duplicate key" in detail or "unique constraint" in detail:
                show_notice("Your account already belongs to a family.")
            else:
                show_notice("Could not create the family. Check the Supabase migration and try again.")
            return
        show_notice(f"{family_name} created in Supabase.")

    async def invite_family_member(email):
        household_data = family_context.get("household")
        if not household_data:
            show_notice("Create a family before inviting a member.")
            return
        recipient_email = (email or "").strip()
        if "@" not in recipient_email or "." not in recipient_email.rsplit("@", 1)[-1]:
            show_notice("Enter a valid email address for an existing account.")
            return
        try:
            await database.invite_family_member(
                household_data["id"], recipient_email, access_token
            )
        except httpx.HTTPError as error:
            detail = supabase_error_detail(error)
            normalized_detail = detail.lower()
            if "already in a family" in normalized_detail:
                show_notice("That user is already in a family, so no invitation was created.")
            elif "no registered account" in normalized_detail or "no account matches" in normalized_detail:
                show_notice("No existing account matches that email address.")
            elif "already pending" in normalized_detail:
                show_notice("An invitation is already pending for that account.")
            elif error.response and error.response.status_code == 404:
                show_notice("Supabase is missing the invitation function. Run supabase_family_invitations_migration.sql in the SQL Editor for this project.")
            else:
                log.warning("Family invitation failed: %s", detail)
                show_notice(f"Invitation failed: {detail}")
            return
        try:
            family_context["invitations"] = await database.load_family_invitations(access_token)
        except httpx.HTTPError as error:
            log.warning("Invitation was created but the list did not refresh: %s", error)
            family_context["invitation_load_error"] = "Invitation was created, but Supabase could not reload the invitation list. Check the migration, then reopen this tab."
            show_notice("Invitation created in Supabase and is pending, but the invitation list could not refresh.")
            return
        show_notice("Invitation is pending in Supabase. The recipient can accept or reject it in their Family tab.")

    async def respond_to_invitation(invitation_id, accept):
        try:
            await database.respond_to_family_invitation(invitation_id, accept, access_token)
            await refresh_family_data()
        except httpx.HTTPError as error:
            detail = error.response.text.lower() if error.response else ""
            if "already in a family" in detail:
                show_notice("You are already in a family, so this invitation was not accepted.")
            else:
                log.warning("Family invitation response failed: %s", error)
                show_notice("Could not update the invitation in Supabase. Please try again.")
            return
        show_notice("Invitation accepted; you joined the family." if accept else "Invitation rejected.")

    async def leave_family():
        household_data = family_context.get("household")
        if not household_data or household_data.get("member_role") == "owner":
            return
        try:
            await database.leave_household(household_data["id"], access_token)
            await refresh_family_data()
        except httpx.HTTPError as error:
            detail = supabase_error_detail(error)
            log.warning("Could not leave family: %s", detail)
            if "leave_household" in detail.lower() or "could not find the function" in detail.lower():
                show_notice("Run supabase_family_member_management_migration.sql in your Supabase project's SQL Editor, then try again.")
            else:
                show_notice(f"Could not leave the family: {detail}")
            return
        show_notice("You left the family.")

    async def remove_family_member(member_id):
        household_data = family_context.get("household")
        if (
            not household_data
            or household_data.get("member_role") != "owner"
            or not member_id
            or member_id == user_id
        ):
            return
        try:
            await database.remove_household_member(
                household_data["id"], member_id, access_token
            )
            await refresh_family_data()
        except httpx.HTTPError as error:
            detail = supabase_error_detail(error)
            log.warning("Could not remove family member: %s", detail)
            if "remove_family_member_by_owner" in detail.lower() or "could not find the function" in detail.lower():
                show_notice("Run supabase_family_member_management_migration.sql in your Supabase project's SQL Editor, then try again.")
            else:
                show_notice(f"Could not remove that family member: {detail}")
            return
        show_notice("Family member removed.")

    async def remove_profile(profile_id):
        if profile_settings_table_available:
            try:
                await database.delete_account_profile_settings(profile_id, access_token)
            except httpx.HTTPError as error:
                log.warning("Could not remove cloud profile settings: %s", error)
                show_notice("Profile was not removed because its cloud settings could not be deleted.")
                return
        profile = await household.remove(profile_id)
        if not profile:
            return
        settings_by_profile.pop(profile_id, None)
        await delete_settings(preferences, user_id, profile_id)
        family_context["local_profiles"] = profiles
        if active_profile["id"] == profile_id:
            await switch_profile("owner")
        selected["notice"] = f"{profile['name']}'s profile was removed."
        render()

    def confirm_remove_profile(profile_id):
        profile = next((item for item in profiles if item["id"] == profile_id), None)
        if not profile:
            return

        async def remove_confirmed():
            page.pop_dialog()
            await remove_profile(profile_id)

        page.show_dialog(
            profile_dialogs.removal(
                profile,
                remove_confirmed,
                lambda e: page.pop_dialog(),
            )
        )

    async def pick_profile(profile_id):
        page.pop_dialog()
        await switch_profile(profile_id)

    def show_profile_picker():
        page.show_dialog(
            profile_dialogs.picker(
                page, profiles, active_profile["id"], pick_profile
            )
        )

    def notice_control():
        message = selected["notice"]
        if not message:
            return None
        return panel(
            ft.Row(
                controls=[
                    ft.Icon(ft.Icons.INFO_OUTLINE, color=brand_color(), size=19),
                    ft.Text(message, expand=True, size=13, color=ink_color()),
                    ft.IconButton(
                        icon=ft.Icons.CLOSE,
                        icon_size=17,
                        on_click=lambda e: dismiss_notice(),
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
            ),
            bgcolor=surface_tint(),
            padding=8,
        )

    async def save_profile_changes(changes):
        nonlocal settings
        profile_id = active_profile["id"]
        display_name = changes.get("display_name", "").strip()
        full_name = changes.get("full_name", "").strip()
        if not display_name or not full_name:
            show_notice("Enter both a full name and a display name.")
            return False
        message = await household.update_profile(
            profile_id,
            name=display_name,
            full_name=full_name,
            avatar=changes.get("avatar_key"),
        )
        if message:
            show_notice(message)
            return False
        saved_settings = changes.get("settings", {})
        settings_by_profile[profile_id] = dict(saved_settings)
        settings = settings_by_profile[profile_id]
        await save_settings(preferences, user_id, settings, profile_id)
        current_profile = next(item for item in profiles if item["id"] == profile_id)
        family_context["local_profiles"] = profiles
        theme_mode = apply_theme(
            page, settings.get("theme_mode", "system"), page.platform_brightness
        )
        await preferences.set(APP_THEME_KEY, theme_mode)
        values = {
            "display_name": display_name,
            "full_name": full_name,
            "avatar_key": current_profile.get("avatar", "avatar_leaf.svg"),
            "birthday": current_profile.get("birthday") or None,
            "member_role": current_profile.get("role", "child"),
            "settings": settings,
        }
        try:
            await database.save_account_profile_settings(
                user_id, profile_id, values, access_token
            )
            if profile_id == "owner":
                await database.update_auth_profile(
                    user_id,
                    {
                        "display_name": display_name,
                        "full_name": full_name,
                        "avatar_key": values["avatar_key"],
                    },
                    access_token,
                )
            selected["notice"] = "Profile changes saved to your account."
        except httpx.HTTPError as error:
            log.warning("Profile settings database save failed: %s", error)
            selected["notice"] = "Saved on this device. Run supabase_profile_settings_migration.sql to enable database saves."
        profile_button.content = ft.Text(current_profile["name"])
        render()
        if mounted["value"]:
            page.update()
        return True

    async def update_theme_mode(mode):
        nonlocal settings
        if mode not in {"light", "dark", "system"}:
            return
        profile_id = active_profile["id"]
        settings = dict(settings)
        settings["theme_mode"] = mode
        settings_by_profile[profile_id] = settings
        normalized_mode = apply_theme(page, mode, page.platform_brightness)
        await save_settings(preferences, user_id, settings, profile_id)
        await preferences.set(APP_THEME_KEY, normalized_mode)
        render()
        if mounted["value"]:
            page.update()

    async def change_password(new_password, validation_error):
        if validation_error:
            show_notice(validation_error)
            return False
        try:
            await database.update_password(access_token, new_password)
        except httpx.HTTPError as error:
            log.warning("Password update failed: %s", error)
            show_notice("Password change failed. Check the password policy and try again.")
            return False
        show_notice("Password changed successfully.")
        return True

    async def sign_out_all_sessions():
        try:
            await database.sign_out_all(access_token)
        except httpx.HTTPError as error:
            log.warning("Sign-out-all request failed: %s", error)
            show_notice("Could not revoke all sessions. Please try again.")
            return
        await on_logout()

    async def redeem_myrewards_reward(reward):
        if not selected_myrewards["cloud_ready"]:
            return None, selected_myrewards["cloud_error"] or "MyRewards is not connected to Supabase yet."
        try:
            cloud_voucher = await database.redeem_myrewards_reward(
                reward["id"], access_token
            )
            spent = int(cloud_voucher.get("pointsSpent", reward["pointsCost"]))
            owner_state["points"] = max(0, int(owner_state.get("points", 0)) - spent)
            owner_state["points_spent"] = int(owner_state.get("points_spent", 0)) + spent
            merge_cloud_vouchers(myrewards_state, [cloud_voucher])
            selected_myrewards["cloud_error"] = ""
            return cloud_voucher, ""
        except httpx.HTTPError as error:
            detail = supabase_error_detail(error)
            selected_myrewards["cloud_error"] = detail
            log.warning("MyRewards redemption failed in Supabase: %s", detail)
            return None, detail

    async def persist_myrewards():
        if not selected_myrewards["cloud_ready"]:
            raise RuntimeError(
                selected_myrewards["cloud_error"]
                or "MyRewards is not connected to Supabase yet. Reload and try again."
            )
        try:
            cloud_vouchers = await database.sync_myrewards_vouchers(
                myrewards_state.get("vouchers", []),
                myrewards_state.get("pointsTransactions", []),
                access_token,
            )
            myrewards_state["vouchers"] = []
            myrewards_state["pointsTransactions"] = []
            myrewards_state["localPointsSpent"] = 0
            merge_cloud_vouchers(myrewards_state, cloud_vouchers)
            await preferences.set(myrewards_storage_key, json.dumps(myrewards_state))
        except httpx.HTTPError as error:
            selected_myrewards["cloud_error"] = supabase_error_detail(error)
            raise

    def dashboard_state():
        data = dict(state)
        account_balance = int(owner_state.get("points", 0))
        data["points"] = available_points(myrewards_state, account_balance)
        data["points_spent"] = int(state.get("points_spent", 0))
        data["redemptions"] = [
            *state.get("redemptions", []),
            *myrewards_state.get("vouchers", []),
        ]
        data["solar_claims"] = selected["solar_claims"]
        return data

    def screen_content():
        index = selected["screen"]
        if index == 0:
            profile_name = next(item["name"] for item in profiles if item["id"] == active_profile["id"])
            return dashboard.build(dashboard_state(), navigate, profile_name)
        if index == 1:
            return walking.build(
                state,
                choose_run_screenshot,
                selected.get("running_ocr_status", ""),
                active_profile["id"] == "owner",
                ocr_supported,
                selected.get("walking_chart_period", "week"),
                change_walking_chart_period,
            )
        if index == 2:
            is_household_owner = active_profile["id"] == "owner"
            return solar.build(
                household_name=family_context.get("family_name"),
                household_id=(family_context.get("household") or {}).get("id"),
                history=selected["solar_claims"],
                form_state=selected["solar_form"],
                can_submit=is_household_owner,
                on_month_change=change_solar_month,
                on_year_change=change_solar_year,
                ocr_supported=ocr_supported,
                on_upload=choose_solar_image,
            )
        if index == 3:
            account_balance = int(owner_state.get("points", 0))
            ensure_myrewards_state(
                myrewards_state, user_id, owner_name, account_balance
            )
            return rewards_view.build(
                page=page,
                catalog=myrewards_catalog,
                feature_state=myrewards_state,
                account_balance=account_balance,
                view_state=selected["myrewards_view"],
                on_persist=persist_myrewards,
                on_redeem=redeem_myrewards_reward,
                cloud_ready=selected_myrewards["cloud_ready"],
                on_render=render,
                on_back=lambda: navigate(0),
            )
        if index == 4:
            return family_profiles.build(
                household=family_context.get("household"),
                load_error=family_context.get("load_error", ""),
                invitation_error=family_context.get("invitation_load_error", ""),
                invitations=family_context.get("invitations", []),
                on_create_household=create_family,
                on_invite=invite_family_member,
                on_respond_invitation=respond_to_invitation,
                page=page,
                on_leave_family=leave_family,
                on_remove_member=remove_family_member,
            )
        current_profile = next(item for item in profiles if item["id"] == active_profile["id"])
        return profile_settings.build(
            current_profile,
            settings,
            family_context,
            {
                "display_name": next(
                    (item.get("name") for item in profiles if item.get("id") == "owner"),
                    owner_name,
                ),
                "email": user.get("email", ""),
                "expires_at": session.get("expires_at"),
            },
            save_profile_changes,
            change_password,
            on_logout,
            sign_out_all_sessions,
            update_theme_mode,
        )

    def render():
        is_myrewards = selected["screen"] == 3
        if page.appbar is not None:
            page.appbar.visible = not is_myrewards
        if page.navigation_bar is not None:
            page.navigation_bar.visible = True
        controls = []
        notice = notice_control()
        if notice is not None:
            controls.append(notice)
        controls.append(screen_content())
        if ocr_webview is not None:
            controls.append(ocr_webview)
        root.content = ft.Column(expand=True, spacing=14, controls=controls)
        if mounted["value"]:
            root.update()

    async def persist_and_refresh(message, notification_key=None):
        database_error = await save_state(
            preferences,
            database,
            user_id,
            access_token,
            state,
            profile_id=active_profile["id"],
        )
        log.debug("Saved app state after action")
        if database_error:
            message += " (Saved on this device; Supabase sync failed.)"
        else:
            message += " Saved on this device only."
        if notification_key and not settings.get(notification_key, True):
            selected["notice"] = ""
            render()
            return
        show_notice(message)

    def navigate(index):
        selected["screen"] = index
        selected["notice"] = ""
        render()

    async def change_navigation(event):
        index = event.control.selected_index
        if index == 2:
            await refresh_solar_claims()
        if index == 4:
            try:
                await refresh_family_data()
                family_context["invitation_load_error"] = ""
            except httpx.HTTPError as error:
                log.info("Could not refresh family invitations: %s", error)
                if error.response and error.response.status_code == 404:
                    family_context["invitation_load_error"] = "Supabase is missing the invitation RPCs. Run supabase_family_invitations_migration.sql in the SQL Editor for this same project. Invitations are not available until then."
                else:
                    family_context["invitation_load_error"] = "Could not refresh family data from Supabase. Check your connection and the invitation migration."
        navigate(index)

    def change_filter(event):
        selected["filter"] = event.control.value or "All"
        render()

    def change_walking_chart_period(event):
        period = event.control.value
        if period in {"week", "month", "year"}:
            selected["walking_chart_period"] = period
            render()

    async def refresh_solar_claims():
        household_id = (family_context.get("household") or {}).get("id")
        if not household_id:
            selected["solar_claims"] = []
            return False
        try:
            selected["solar_claims"] = await database.load_household_solar_claims(
                household_id, access_token
            )
            return True
        except httpx.HTTPError as error:
            log.warning("Solar claim history could not load: %s", supabase_error_detail(error))
            form = selected["solar_form"]
            response = getattr(error, "response", None)
            if getattr(response, "status_code", None) == 404:
                form["message"] = "Solar claims are not configured yet. Run supabase_solar_claims_migration.sql in the connected Supabase project."
            else:
                form["message"] = "Could not load solar claim history. Check the database connection and migration."
            form["message_kind"] = "error"
            return False

    async def refresh_dashboard_solar_claims():
        if await refresh_solar_claims() and mounted["value"]:
            render()

    def change_solar_month(event):
        form = selected["solar_form"]
        form["month"] = int(event.control.value)
        form["message"] = ""
        render()

    def change_solar_year(event):
        form = selected["solar_form"]
        form["year"] = int(event.control.value)
        form["message"] = ""
        render()

    async def choose_solar_image():
        if active_profile["id"] != "owner":
            selected["solar_form"].update({"message": "Only the household owner can submit a solar claim.", "message_kind": "error"})
            render()
            return
        try:
            files = await file_picker.pick_files(
                dialog_title="Choose a solar energy report",
                file_type=ft.FilePickerFileType.IMAGE,
                allowed_extensions=["jpg", "jpeg", "png"],
                allow_multiple=False,
                with_data=True,
            )
        except Exception as error:
            log.warning("Could not open solar report picker: %s", error)
            selected["solar_form"].update({"message": "Could not open the image picker. Please try again.", "message_kind": "error"})
            render()
            return
        if not files:
            return
        image_file = files[0]
        image_bytes, mime_type, image_error = read_selected_image(image_file)
        if image_error:
            selected["solar_form"].update({
                "message": image_error,
                "message_kind": "error",
            })
            render()
            return
        selected["solar_form"].update({
            "image_bytes": image_bytes,
            "image_name": image_file.name,
            "mime_type": mime_type,
            "kwh": None,
            "points": 0,
            "detected_month": None,
            "detected_year": None,
            "detected_period": "",
            "suspicious": False,
            "message": "Report uploaded. Extracting its monthly solar reading…",
            "message_kind": "success",
        })
        render()
        await extract_solar_reading_clicked()

    async def extract_solar_reading_clicked():
        form = selected["solar_form"]
        if not form.get("image_bytes"):
            form.update({"message": "Upload a solar monitoring screenshot or monthly report first.", "message_kind": "error"})
            render()
            return
        if not ocr_supported:
            form.update({
                "message": "Automatic OCR is unavailable on this device. Enter the monthly kWh shown on your uploaded report below.",
                "message_kind": "error",
            })
            render()
            return
        form.update({"message": "Reading the report with Tesseract OCR…", "message_kind": "success"})
        render()
        if page.web:
            try:
                result = await extract_solar_reading(form["image_bytes"], form["mime_type"])
                handle_solar_ocr_result(result)
            except Exception as error:
                log.exception("Solar OCR failed")
                form.update({"message": "Solar OCR could not start. Check your connection and try again.", "message_kind": "error"})
                render()
            return
        if not ocr_webview or ocr_ready["failed"] or not ocr_ready["value"]:
            form.update({"message": "The on-device OCR engine is still starting or unavailable. Try again shortly.", "message_kind": "error"})
            render()
            return
        selected["ocr_pending"] = (form["image_bytes"], form["mime_type"], "solar")
        form.update({
            "message": "Reading the solar report on this device…",
            "message_kind": "success",
        })
        render()
        await dispatch_pending_ocr()

    async def submit_solar_claim():
        form = selected["solar_form"]
        if form.get("busy"):
            return
        household_id = (family_context.get("household") or {}).get("id")
        if active_profile["id"] != "owner" or not household_id:
            form.update({"message": "A linked household owner account is required to submit solar claims.", "message_kind": "error"})
            render()
            return
        if not form.get("image_bytes") or not form.get("kwh"):
            form.update({"message": "Upload a report and successfully extract its monthly kWh reading before claiming.", "message_kind": "error"})
            render()
            return
        amount, points, issue = validate_claim(form["kwh"], form.get("month"), form.get("year"))
        if issue:
            form.update({"message": issue, "message_kind": "error"})
            render()
            return
        detected_month, detected_year = form.get("detected_month"), form.get("detected_year")
        if detected_month and detected_year and (int(form["month"]), int(form["year"])) != (int(detected_month), int(detected_year)):
            form.update({"message": "The selected claim month does not match the month/year read from the report.", "message_kind": "error"})
            render()
            return
        month, year = int(form["month"]), int(form["year"])
        if has_successful_claim(selected["solar_claims"], month, year):
            form.update({"message": "A successful claim already exists for this household and month.", "message_kind": "error"})
            render()
            return

        form["busy"] = True
        form["message"] = "Saving the reading and awarding points in Supabase…"
        form["message_kind"] = "success"
        render()
        extension = "png" if form["mime_type"] == "image/png" else "jpg"
        file_name = f"{uuid.uuid4().hex}.{extension}"
        try:
            evidence_path = await database.upload_solar_evidence(
                household_id,
                file_name,
                form["image_bytes"],
                form["mime_type"],
                access_token,
            )
            result = await database.submit_solar_claim(
                household_id,
                month,
                year,
                str(amount),
                evidence_path,
                access_token,
            )
            if not isinstance(result, dict) or not result.get("claim_id"):
                raise ValueError("Supabase returned an invalid solar claim response")
            status = result.get("claim_status")
            if status == "awarded":
                message = f"SOLAR CLAIM REDEEMED · {float(result.get('solar_generation_kwh', amount)):g} kWh · {int(result.get('points_awarded', points)):,} points added."
                if not await refresh_cloud_rewards():
                    message += " The ledger award was saved; the balance will refresh when the points service is available."
            elif status == "flagged_review":
                message = "Claim recorded for review because the reading is unusually high. No points were awarded."
            else:
                raise ValueError("Supabase returned an unknown solar claim status")
            if not await refresh_solar_claims():
                selected["solar_claims"].insert(0, result)
            form.update({
                "message": message,
                "message_kind": "success",
            })
            if status == "awarded":
                show_notice(message)
        except (httpx.HTTPError, ValueError, TypeError) as error:
            detail = supabase_error_detail(error) if isinstance(error, httpx.HTTPError) else str(error)
            if any(
                marker in detail.lower()
                for marker in (
                    "bucket not found",
                    "get_household_solar_claims",
                    "submit_solar_claim",
                    "schema cache",
                    "solar-evidence",
                )
            ):
                detail = (
                    "Solar setup is incomplete in Supabase. Run "
                    "supabase_solar_claims_migration.sql in the connected project's "
                    "SQL Editor, then reload."
                )
            history_loaded = await refresh_solar_claims()
            if history_loaded and has_successful_claim(selected["solar_claims"], month, year):
                await refresh_cloud_rewards()
                form.update({
                    "message": "A successful claim for this household and month is already recorded. This retry did not award points again.",
                    "message_kind": "success",
                })
            else:
                form.update({"message": f"Claim could not be confirmed. No new points were awarded. {detail}", "message_kind": "error"})
            log.warning("Solar claim could not be committed or confirmed: %s", detail)
        finally:
            form["busy"] = False
            render()


    async def redeem(offer):
        if active_profile["id"] == "owner":
            if not selected["cloud_loaded"]:
                show_notice(selected["cloud_error"] or "Supabase rewards are still loading.")
                return
            try:
                await database.redeem_reward(offer["id"], access_token)
                refreshed = await refresh_cloud_rewards()
                if refreshed:
                    show_notice(f"Reward claimed from Supabase: {offer['name']} for {offer['points']} points.")
                else:
                    show_notice("Reward claim was saved in Supabase, but the latest balance could not be refreshed.")
            except httpx.HTTPError as error:
                log.warning("Supabase reward redemption failed: %s", error)
                response = getattr(error, "response", None)
                detail = ""
                if response is not None:
                    try:
                        detail = response.json().get("message", "")
                    except (TypeError, ValueError):
                        detail = ""
                if "points_ledger_entry_type_check" in detail:
                    detail = (
                        "The points ledger is missing the reward_redemption entry type. "
                        "Run supabase_points_ledger_entry_types_migration.sql in the "
                        "connected Supabase project's SQL Editor, then retry."
                    )
                show_notice(detail or "Reward could not be claimed. Check your points balance and reward stock.")
            return

        message = redeem_offer(state, offer)
        if message.startswith("Redeemed "):
            profile_name = next(
                item["name"] for item in profiles if item["id"] == active_profile["id"]
            )
            await persist_and_refresh(
                f"{profile_name} redeemed {offer['name']} for {offer['points']} points."
            )
        else:
            show_notice(message)

    current_profile = next(item for item in profiles if item["id"] == active_profile["id"])
    profile_button = ft.TextButton(
        content=ft.Text(
            current_profile["name"],
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
        ),
        icon=ft.Icons.ACCOUNT_CIRCLE,
        on_click=show_profile_picker,
    )

    def appbar_actions(compact):
        if compact:
            return [
                ft.IconButton(
                    icon=ft.Icons.ACCOUNT_CIRCLE,
                    tooltip="Switch profile",
                    on_click=show_profile_picker,
                ),
                ft.IconButton(
                    icon=ft.Icons.LOGOUT,
                    tooltip="Sign out",
                    on_click=on_logout,
                ),
            ]
        return [
            profile_button,
            ft.TextButton(content=ft.Text("Sign out"), on_click=on_logout),
        ]

    def platform_brightness_changed(event):
        if settings.get("theme_mode", "system") == "system":
            apply_theme(page, "system", event.brightness)
            render()
            if mounted["value"]:
                page.update()

    page.on_platform_brightness_change = platform_brightness_changed

    def handle_resize(event):
        compact = event.width < 600
        root.padding = 10 if compact else 18
        if page.navigation_bar is not None:
            page.navigation_bar.label_behavior = (
                ft.NavigationBarLabelBehavior.ONLY_SHOW_SELECTED
                if compact
                else ft.NavigationBarLabelBehavior.ALWAYS_SHOW
            )
        if page.appbar is not None:
            page.appbar.actions = appbar_actions(compact)
        if mounted["value"]:
            page.update()

    page.on_resize = handle_resize
    page.bgcolor = canvas_color()
    page.appbar = ft.AppBar(
        title=ft.Text("Townly"),
        actions=appbar_actions((page.width or 800) < 600),
    )
    destinations = [
        ft.NavigationBarDestination(icon=ft.Icons.HOME_OUTLINED, selected_icon=ft.Icons.HOME, label="Home"),
        ft.NavigationBarDestination(icon=ft.Icons.DIRECTIONS_WALK, label="Walk"),
        ft.NavigationBarDestination(icon=ft.Icons.SOLAR_POWER, label="Solar"),
        ft.NavigationBarDestination(icon=ft.Icons.CARD_GIFTCARD, label="Rewards"),
        ft.NavigationBarDestination(icon=ft.Icons.PEOPLE_OUTLINE, label="Family"),
        ft.NavigationBarDestination(icon=ft.Icons.PERSON_OUTLINE, label="Profile"),
    ]
    page.navigation_bar = ft.NavigationBar(
        destinations=destinations,
        selected_index=0,
        on_change=change_navigation,
        bgcolor=surface_color(),
        indicator_color=surface_tint(),
        label_behavior=(
            ft.NavigationBarLabelBehavior.ONLY_SHOW_SELECTED
            if (page.width or 800) < 600
            else ft.NavigationBarLabelBehavior.ALWAYS_SHOW
        ),
    )
    render()
    page.add(root)
    mounted["value"] = True
    page.update()
    asyncio.create_task(refresh_cloud_rewards())
    asyncio.create_task(refresh_dashboard_solar_claims())
    if is_android and ocr_webview is not None:
        asyncio.create_task(initialize_ocr_webview())
    log.info("Townly ready; loading cloud rewards")
