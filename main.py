import logging

import flet as ft
import httpx2 as httpx

from components import apply_theme, current_theme_mode
from storage import APP_THEME_KEY
from supabase_api import SupabaseDatabase
from views import admin_shell, app_shell, auth

LOG_LEVEL = logging.INFO
logging.basicConfig(format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("app").setLevel(LOG_LEVEL)
log = logging.getLogger("app.main")


async def main(page: ft.Page):
    page.title = "Townly"
    page.padding = 0
    page.spacing = 0

    preferences = ft.SharedPreferences()
    saved_theme = await preferences.get(APP_THEME_KEY)
    theme_mode = saved_theme if saved_theme in {"light", "dark", "system"} else "system"
    apply_theme(page, theme_mode, page.platform_brightness)

    database = SupabaseDatabase()
    active_session = {"value": None}

    def platform_brightness_changed(event):
        apply_theme(page, current_theme_mode(), event.brightness)
        if active_session["value"] is None:
            show_login()
        else:
            page.update()

    page.on_platform_brightness_change = platform_brightness_changed

    async def authenticate(sign_up, email, password, display_name):
        if sign_up:
            response = await database.sign_up(email, password, display_name)
            if response.get("access_token") and response.get("user"):
                return response, ""
            return None, "Account created. Check your email for a confirmation link, then sign in."
        session = await database.sign_in(email, password)
        if not session.get("access_token") or not session.get("user"):
            raise ValueError("Supabase did not return a valid sign-in session.")
        return session, ""

    async def send_password_recovery(email):
        await database.send_password_recovery(email)

    async def complete_password_recovery(email, code, new_password):
        session = await database.verify_password_recovery(email, code)
        access_token = session.get("access_token")
        if not access_token or not session.get("user"):
            raise ValueError("The recovery code did not produce a valid session.")
        await database.update_password(access_token, new_password)
        return session

    def show_login():
        log.debug("Building sign-in view")
        active_session["value"] = None
        apply_theme(page, current_theme_mode(), page.platform_brightness)
        page.on_platform_brightness_change = platform_brightness_changed
        page.appbar = None
        page.navigation_bar = None
        page.clean()
        login_view = auth.build(
            page,
            authenticate,
            show_authenticated,
            send_password_recovery,
            complete_password_recovery,
        )
        page.add(login_view)
        log.debug("Mounted sign-in view: %s controls", len(page.controls))
        page.update()

    async def log_out():
        session = active_session["value"]
        if session:
            try:
                await database.sign_out(session["access_token"])
            except httpx.HTTPError as error:
                log.warning("Supabase sign-out request failed: %s", error)
        show_login()

    async def show_authenticated(session):
        user = session.get("user") or {}
        if not user.get("id") or not session.get("access_token"):
            raise ValueError("Supabase returned an incomplete sign-in session.")
        active_session["value"] = session
        page.appbar = None
        page.navigation_bar = None
        page.clean()
        role_check_note = None
        try:
            is_admin = await database.is_current_admin(session["access_token"])
        except httpx.HTTPError as error:
            log.warning("Admin role check failed; using household interface only: %s", error)
            is_admin = False
            role_check_note = "Admin role could not be verified, so the household interface is shown. Run supabase_admin_dashboard.sql and confirm this account has the admin role."

        if is_admin:
            await admin_shell.build(page, database, session, log_out)
        else:
            await app_shell.build(
                page,
                preferences,
                database,
                session,
                log_out,
                role_check_note=role_check_note,
            )

    show_login()


ft.run(main)
