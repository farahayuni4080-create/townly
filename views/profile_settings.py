"""Profile identity, family details, privacy and account preferences."""

import flet as ft

from components import brand_color, ink_color, input_field, muted_color, panel, surface_tint, title

AVATARS = [
    ("avatar_leaf.svg", "Leaf"),
    ("avatar_sun.svg", "Sun"),
    ("avatar_ocean.svg", "Ocean"),
    ("avatar_berry.svg", "Berry"),
]


def _role_label(role):
    return {"owner": "Owner", "adult": "Adult", "member": "Adult", "child": "Child"}.get(
        role, str(role or "Member").title()
    )


def build(
    profile,
    settings,
    family_context,
    account,
    on_save,
    on_change_password,
    on_sign_out,
    on_sign_out_all,
    on_theme_change,
):
    draft_settings = dict(settings)
    name_field = input_field(label="Display name", value=profile.get("name", ""))
    full_name_field = input_field(
        label="Full name", value=profile.get("full_name") or profile.get("name", "")
    )
    password_field = input_field(
        label="New password", password=True, can_reveal_password=True
    )
    confirm_password_field = input_field(
        label="Confirm new password", password=True, can_reveal_password=True
    )
    selected_avatar = {"value": profile.get("avatar", "avatar_leaf.svg")}
    avatar_preview = ft.Container(
        width=72,
        height=72,
        border_radius=36,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        content=ft.Image(
            src=selected_avatar["value"],
            width=72,
            height=72,
            fit=ft.BoxFit.COVER,
        ),
    )
    avatar_cards = []

    def choose_avatar(event, avatar_file):
        selected_avatar["value"] = avatar_file
        avatar_preview.content.src = avatar_file
        avatar_preview.update()
        for filename, card in avatar_cards:
            card.border = ft.Border.all(
                2, brand_color() if filename == avatar_file else ft.Colors.TRANSPARENT
            )
            card.update()

    for avatar_file, label in AVATARS:
        card = ft.Container(
            on_click=lambda event, filename=avatar_file: choose_avatar(event, filename),
            padding=8,
            border=ft.Border.all(
                2,
                brand_color() if avatar_file == selected_avatar["value"] else ft.Colors.TRANSPARENT,
            ),
            border_radius=14,
            content=ft.Column(
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=5,
                controls=[
                    ft.Container(
                        width=58,
                        height=58,
                        border_radius=29,
                        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                        content=ft.Image(
                            src=avatar_file,
                            width=58,
                            height=58,
                            fit=ft.BoxFit.COVER,
                        ),
                    ),
                    ft.Text(label, size=11, color=muted_color()),
                ],
            ),
        )
        avatar_cards.append((avatar_file, card))

    notification_switches = []
    for key, label in [
        ("notify_daily_limit", "When the daily step limit is reached"),
        ("notify_walking_milestones", "Walking milestones"),
        ("notify_solar_claim_results", "Solar claim results"),
        ("notify_bonus_events", "New bonus events"),
        ("notify_household_redemptions", "Household reward redemptions"),
    ]:
        notification_switches.append(
            ft.Switch(
                label=label,
                value=bool(draft_settings.get(key, True)),
                inactive_thumb_color=ink_color(),
                inactive_track_color=surface_tint(),
                track_outline_color=ink_color(),
                track_outline_width=1.5,
                on_change=lambda event, setting_key=key: draft_settings.__setitem__(
                    setting_key, bool(event.control.value)
                ),
            )
        )

    authorized_adult = family_context.get("account_role", "owner") in (
        "owner", "adult", "member"
    )
    consent_switches = []
    for key, label in [
        ("consent_walking_data", "Allow walking data collection"),
        ("consent_solar_data", "Allow solar data collection"),
    ]:
        consent_switches.append(
            ft.Switch(
                label=label,
                value=bool(draft_settings.get(key, False)),
                inactive_thumb_color=ink_color(),
                inactive_track_color=surface_tint(),
                track_outline_color=ink_color(),
                track_outline_width=1.5,
                disabled=not authorized_adult,
                on_change=lambda event, setting_key=key: draft_settings.__setitem__(
                    setting_key, bool(event.control.value)
                ),
            )
        )

    households = family_context.get("households", [])
    local_profiles = family_context.get("local_profiles", [])
    active_role = _role_label(profile.get("role", "child"))
    current_household = family_context.get("household")
    if current_household is None and households:
        current_household = households[0]
    family_name = (
        current_household.get("name") if current_household else "Household not linked"
    )
    address = (current_household or {}).get("address", "") or "Not provided"
    family_controls = [
        ft.Text(f"Family name: {family_name}", color=ink_color()),
        ft.Text(f"Household address: {address}", color=muted_color()),
        ft.Text(
            f"Signed-in account role: {_role_label(family_context.get('account_role', 'owner'))}",
            color=ink_color(),
        ),
        ft.Text(f"Selected profile role: {active_role}", color=muted_color()),
    ]
    if current_household:
        family_controls.extend(
            [
                ft.Text("Household accounts", size=14, weight=ft.FontWeight.BOLD, color=ink_color()),
                *[
                    ft.ListTile(
                        title=member.get("display_name") or member.get("full_name") or "Member",
                        subtitle=_role_label(member.get("role", "member")),
                        leading=ft.Icon(ft.Icons.PERSON_OUTLINE),
                    )
                    for member in current_household.get("members", [])
                ],
            ]
        )
    family_controls.extend(
        [
            ft.Text("Family profiles", size=14, weight=ft.FontWeight.BOLD, color=ink_color()),
            *[
                ft.ListTile(
                    title=member.get("name", "Member"),
                    subtitle=_role_label(member.get("role", "child")),
                    leading=ft.CircleAvatar(
                        foreground_image_src=member.get("avatar", "avatar_leaf.svg"),
                        radius=18,
                    ),
                )
                for member in local_profiles
            ],
        ]
    )
    if family_context.get("load_error"):
        family_controls.append(
            ft.Text(family_context["load_error"], size=12, color=muted_color())
        )

    session_label = f"Signed in as {account.get('display_name') or 'account'}"
    if account.get("expires_at"):
        session_label += f" · session expiry: {account['expires_at']}"
    email_label = f"Email: {account['email']}" if account.get("email") else ""

    async def save_clicked():
        await on_save(
            {
                "display_name": (name_field.value or "").strip(),
                "full_name": (full_name_field.value or "").strip(),
                "avatar_key": selected_avatar["value"],
                "settings": dict(draft_settings),
            }
        )

    async def password_clicked():
        new_password = password_field.value or ""
        if len(new_password) < 8:
            return await on_change_password("", "Use a password with at least 8 characters.")
        if new_password != (confirm_password_field.value or ""):
            return await on_change_password("", "The passwords do not match.")
        changed = await on_change_password(new_password, "")
        if changed:
            password_field.value = ""
            confirm_password_field.value = ""

    async def theme_changed(event):
        mode = event.control.value
        if mode not in {"light", "dark", "system"}:
            return
        draft_settings["theme_mode"] = mode
        await on_theme_change(mode)

    def section(content):
        return ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=12,
            controls=[content],
        )

    profile_section = section(
        panel(
            ft.Column(
                spacing=12,
                controls=[
                    ft.Container(
                        padding=12,
                        bgcolor=surface_tint(),
                        border_radius=12,
                        content=ft.Row(
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                avatar_preview,
                            ft.Column(
                                tight=True,
                                spacing=3,
                                controls=[
                                    ft.Text(profile.get("name", "Member"), size=18, weight=ft.FontWeight.BOLD, color=ink_color()),
                                    ft.Text(f"{active_role} household profile", size=12, color=muted_color()),
                                ],
                            ),
                            ],
                            spacing=14,
                        ),
                    ),
                    ft.Text("Profile picture", size=15, weight=ft.FontWeight.BOLD, color=ink_color()),
                    ft.Row(wrap=True, spacing=8, controls=[card for _, card in avatar_cards]),
                    full_name_field,
                    name_field,
                ],
            )
        )
    )
    family_section = section(
        panel(ft.Column(spacing=8, controls=family_controls), bgcolor=surface_tint())
    )
    display_section = section(
        panel(
            ft.Column(
                spacing=8,
                controls=[
                    ft.Text("Display preferences", size=16, weight=ft.FontWeight.BOLD, color=ink_color()),
                    ft.RadioGroup(
                        value=draft_settings.get("theme_mode", "system"),
                        on_change=theme_changed,
                        content=ft.Column(
                            spacing=4,
                            controls=[
                                ft.Radio(value="light", label="Light Mode · sunny and cheerful"),
                                ft.Radio(value="dark", label="Dark Mode · cozy nighttime colors"),
                                ft.Radio(value="system", label="System · follow device appearance"),
                            ],
                        ),
                    ),
                    ft.Text("Applies throughout the app and saves immediately on this device.", size=12, color=muted_color()),
                ],
            )
        )
    )
    notification_section = section(
        panel(
            ft.Column(
                spacing=7,
                controls=[
                    ft.Text("Notification preferences", size=16, weight=ft.FontWeight.BOLD, color=ink_color()),
                    *notification_switches,
                    ft.Text("Alerts appear in the app while it is open.", size=12, color=muted_color()),
                ],
            )
        )
    )
    privacy_section = section(
        panel(
            ft.Column(
                spacing=8,
                controls=[
                    ft.Text("Privacy & data permissions", size=16, weight=ft.FontWeight.BOLD, color=ink_color()),
                    ft.Text(
                        "An authorised household adult manages walking and solar data consent for child profiles.",
                        size=12,
                        color=muted_color(),
                    ),
                    *consent_switches,
                ],
            ),
            bgcolor=surface_tint(),
        )
    )
    security_section = section(
        panel(
            ft.Column(
                spacing=9,
                controls=[
                    ft.Text("Account security", size=16, weight=ft.FontWeight.BOLD, color=ink_color()),
                    ft.Text(session_label, size=12, color=muted_color()),
                    *([ft.Text(email_label, size=12, color=muted_color())] if email_label else []),
                    password_field,
                    confirm_password_field,
                    ft.Button(content="Change password", icon=ft.Icons.LOCK_RESET, on_click=password_clicked),
                    ft.Row(
                        wrap=True,
                        spacing=8,
                        controls=[
                            ft.OutlinedButton(content="Sign out all sessions", icon=ft.Icons.LOGOUT, on_click=on_sign_out_all),
                            ft.TextButton(content="Sign out", icon=ft.Icons.EXIT_TO_APP, on_click=on_sign_out),
                        ],
                    ),
                    ft.Text(
                        "You can revoke all sessions; remote device-by-device session lists are not available here.",
                        size=12,
                        color=muted_color(),
                    ),
                ],
            )
        )
    )

    return ft.Column(
        expand=True,
        spacing=10,
        controls=[
            title("Profile & settings", "Personal details and preferences for the selected family profile."),
            ft.Row(
                wrap=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text("Changes apply to this profile only.", size=12, color=muted_color()),
                    ft.Button(content="Save changes", icon=ft.Icons.SAVE_OUTLINED, on_click=save_clicked),
                ],
                spacing=12,
            ),
            ft.Tabs(
                length=6,
                selected_index=0,
                expand=True,
                content=ft.Column(
                    expand=True,
                    spacing=8,
                    controls=[
                        ft.TabBar(
                            scrollable=True,
                            tabs=[
                                ft.Tab(label="My Profile"),
                                ft.Tab(label="Family"),
                                ft.Tab(label="Display"),
                                ft.Tab(label="Notifications"),
                                ft.Tab(label="Privacy"),
                                ft.Tab(label="Security"),
                            ],
                        ),
                        ft.TabBarView(
                            expand=True,
                            controls=[
                                profile_section,
                                family_section,
                                display_section,
                                notification_section,
                                privacy_section,
                                security_section,
                            ],
                        ),
                    ],
                ),
            ),
        ],
    )
