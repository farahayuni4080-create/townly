"""Email/password authentication and Supabase password recovery."""

import httpx2 as httpx
import flet as ft

from components import brand_color, input_field, panel, primary_button


def _error_message(error):
    response = getattr(error, "response", None)
    if response is not None:
        try:
            payload = response.json()
            detail = (
                payload.get("msg")
                or payload.get("message")
                or payload.get("error_description")
                or payload.get("error")
            )
            if detail:
                return str(detail)
        except (ValueError, TypeError):
            pass
    return str(error)


def build(page, authenticate, on_authenticated, send_password_recovery, complete_password_recovery):
    mode = {"value": "login"}

    def set_mode(value):
        mode["value"] = value
        display_name.visible = value == "signup"
        password.visible = value in ("login", "signup")
        recovery_code.visible = value == "recovery"
        new_password.visible = value == "recovery"
        confirm_new_password.visible = value == "recovery"
        forgot_button.visible = value in ("login", "recovery")
        forgot_button.content = ft.Text(
            "Resend recovery email" if value == "recovery" else "Forgot password?"
        )

        if value == "signup":
            heading.value = "Create your account"
            subtitle.value = "Choose a display name and sign up to save your family's rewards securely."
            submit_button.content = ft.Text("Create account")
            switch_button.content = ft.Text("Already have an account? Sign in")
        elif value == "recovery":
            heading.value = "Reset your password"
            subtitle.value = "Enter the recovery code from your email and choose a new password."
            submit_button.content = ft.Text("Set new password")
            switch_button.content = ft.Text("Back to sign in")
        else:
            heading.value = "Welcome back"
            subtitle.value = "Sign in to your Townly account."
            submit_button.content = ft.Text("Sign in")
            switch_button.content = ft.Text("Create an account")

    def switch_mode(event):
        if mode["value"] == "signup":
            set_mode("login")
        elif mode["value"] == "recovery":
            recovery_code.value = ""
            new_password.value = ""
            confirm_new_password.value = ""
            set_mode("login")
        else:
            set_mode("signup")
        status.value = ""
        page.update()

    async def begin_password_recovery(event):
        address = (email.value or "").strip()
        if not address:
            status.value = "Enter your account email first."
            page.update()
            return

        forgot_button.disabled = True
        switch_button.disabled = True
        submit_button.disabled = True
        status.value = "Requesting a recovery code from Supabase..."
        page.update()
        try:
            await send_password_recovery(address)
            set_mode("recovery")
            status.value = "If the account exists, Supabase has sent a recovery email. Enter its code below."
        except httpx.HTTPError as error:
            status.value = _error_message(error)
        except Exception as error:
            status.value = str(error)
        finally:
            forgot_button.disabled = False
            switch_button.disabled = False
            submit_button.disabled = False
            page.update()

    async def submit(event):
        address = (email.value or "").strip()
        current_mode = mode["value"]
        if not address:
            status.value = "Enter your account email."
            page.update()
            return

        if current_mode in ("login", "signup") and not (password.value or ""):
            status.value = "Enter your password."
            page.update()
            return
        if current_mode == "signup" and not (display_name.value or "").strip():
            status.value = "Enter the display name you'd like your family to see."
            page.update()
            return
        if current_mode == "recovery":
            code = (recovery_code.value or "").strip()
            proposed_password = new_password.value or ""
            if not code:
                status.value = "Enter the recovery code from your email."
                page.update()
                return
            if len(proposed_password) < 8:
                status.value = "Use a new password with at least 8 characters."
                page.update()
                return
            if proposed_password != (confirm_new_password.value or ""):
                status.value = "The new passwords do not match."
                page.update()
                return

        submit_button.disabled = True
        switch_button.disabled = True
        forgot_button.disabled = True
        status.value = "Connecting to Supabase..."
        page.update()
        try:
            if current_mode == "recovery":
                session = await complete_password_recovery(
                    address,
                    (recovery_code.value or "").strip(),
                    new_password.value or "",
                )
                await on_authenticated(session)
                return

            session, message = await authenticate(
                current_mode == "signup",
                address,
                password.value or "",
                (display_name.value or "").strip() if current_mode == "signup" else "",
            )
            if session:
                await on_authenticated(session)
                return
            status.value = message
        except httpx.HTTPError as error:
            status.value = _error_message(error)
        except Exception as error:
            status.value = str(error)
        finally:
            submit_button.disabled = False
            switch_button.disabled = False
            forgot_button.disabled = False
            page.update()

    display_name = input_field(
        label="Display name",
        visible=False,
        max_length=80,
        on_submit=submit,
    )
    email = input_field(
        label="Email",
        keyboard_type=ft.KeyboardType.EMAIL,
        autocorrect=False,
        on_submit=submit,
    )
    password = input_field(
        label="Password",
        password=True,
        can_reveal_password=True,
        on_submit=submit,
    )
    recovery_code = input_field(
        label="Email recovery code",
        visible=False,
        keyboard_type=ft.KeyboardType.NUMBER,
        on_submit=submit,
    )
    new_password = input_field(
        label="New password",
        visible=False,
        password=True,
        can_reveal_password=True,
        on_submit=submit,
    )
    confirm_new_password = input_field(
        label="Confirm new password",
        visible=False,
        password=True,
        can_reveal_password=True,
        on_submit=submit,
    )
    heading = ft.Text(
        "Welcome back",
        size=25,
        weight=ft.FontWeight.BOLD,
        text_align=ft.TextAlign.CENTER,
    )
    subtitle = ft.Text(
        "Sign in to your Townly account.",
        text_align=ft.TextAlign.CENTER,
    )
    status = ft.Text("")
    submit_button = primary_button(ft.Text("Sign in"), on_click=submit)
    switch_button = ft.TextButton(
        content=ft.Text("Create an account"),
        on_click=switch_mode,
    )
    forgot_button = ft.TextButton(
        content=ft.Text("Forgot password?"),
        on_click=begin_password_recovery,
    )

    return ft.Container(
        expand=True,
        alignment=ft.Alignment.CENTER,
        content=ft.ResponsiveRow(
            expand=True,
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Container(
                    col={"xs": 12, "sm": 10, "md": 6, "lg": 4},
                    content=panel(
                        ft.Column(
                            tight=True,
                            spacing=14,
                            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                            controls=[
                                ft.Icon(ft.Icons.CRUELTY_FREE, size=42, color=brand_color()),
                                heading,
                                subtitle,
                                display_name,
                                email,
                                password,
                                recovery_code,
                                new_password,
                                confirm_new_password,
                                submit_button,
                                forgot_button,
                                switch_button,
                                status,
                            ],
                        ),
                        padding=24,
                    ),
                )
            ],
        ),
    )
