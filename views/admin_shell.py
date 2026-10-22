"""Separate, Supabase-backed administration console."""

import asyncio
import logging

import flet as ft
import httpx2 as httpx

from components import (
    apply_theme,
    brand_color,
    canvas_color,
    current_theme_mode,
    error_color,
    error_surface_color,
    ink_color,
    input_field,
    muted_color,
    panel,
    surface_color,
    surface_tint,
    title,
)

log = logging.getLogger(f"app.{__name__}")

NAV_ITEMS = [
    ("Overview", ft.Icons.HOME_OUTLINED),
    ("Users & households", ft.Icons.GROUP_OUTLINED),
    ("Rewards & redemptions", ft.Icons.CARD_GIFTCARD),
    ("Points & transactions", ft.Icons.INFO_OUTLINE),
    ("Reports", ft.Icons.GROUP_OUTLINED),
]


def _error_text(error):
    response = getattr(error, "response", None)
    if response is not None:
        try:
            payload = response.json()
            return str(payload.get("message") or payload.get("details") or payload.get("hint") or error)
        except (ValueError, TypeError):
            pass
    return str(error)


def _record_card(heading, lines, actions=None, extra=None):
    controls = [ft.Text(heading, size=16, weight=ft.FontWeight.BOLD, color=ink_color())]
    controls.extend(ft.Text(line, size=13, color=muted_color()) for line in lines if line)
    if extra is not None:
        controls.append(extra)
    if actions:
        controls.append(ft.Row(controls=actions, wrap=True, spacing=8))
    return panel(ft.Column(controls=controls, spacing=8, tight=True), padding=14)


def _metric_card(label, value, icon):
    return ft.Container(
        content=panel(
            ft.Row(
                controls=[
                    ft.Icon(icon, color=brand_color(), size=24),
                    ft.Column(
                        tight=True,
                        spacing=2,
                        controls=[
                            ft.Text(str(value), size=23, weight=ft.FontWeight.BOLD, color=ink_color()),
                            ft.Text(label, size=12, color=muted_color()),
                        ],
                    ),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=16,
        ),
    )


async def build(page, database, session, on_logout):
    access_token = session["access_token"]
    apply_theme(page, current_theme_mode(), page.platform_brightness)
    selected = {"screen": 0, "notice": "", "busy": True, "sidebar_collapsed": False}
    data = {
        "overview": {}, "users": [], "households": [],
        "rewards": [], "redemptions": [], "ledger": [], "adjustments": [], "reports": {},
    }
    mounted = {"value": False}
    root = ft.Container(expand=True, padding=18)
    search_field = input_field(label="Search by name, email or user ID", expand=True)
    member_user_id = input_field(label="User UUID", width=240)
    member_household_id = input_field(label="Household UUID", width=240)
    new_reward_title = input_field(label="Reward title", width=300)
    new_reward_description = input_field(label="Description", multiline=True, min_lines=2, max_lines=3)
    new_reward_cost = input_field(label="Points", keyboard_type=ft.KeyboardType.NUMBER, width=130)
    new_reward_stock = input_field(label="Stock", keyboard_type=ft.KeyboardType.NUMBER, width=130)
    adjust_user_id = input_field(label="User UUID", width=240)
    adjust_points_field = input_field(label="Points (+/-)", keyboard_type=ft.KeyboardType.NUMBER, width=150)
    adjust_reason = input_field(label="Reason for audited adjustment", width=300)

    def show_notice(message):
        selected["notice"] = message
        render()

    def user_name(user_id):
        match = next((u for u in data["users"] if u.get("user_id") == user_id), None)
        if match:
            return match.get("display_name") or match.get("email") or user_id
        return user_id

    async def refresh_data():
        selected["busy"] = True
        render()
        try:
            calls = [
                database.rpc("admin_overview", {}, access_token),
                database.rpc("admin_user_directory", {"p_search": (search_field.value or "").strip() or None}, access_token),
                database.rpc("admin_household_directory", {}, access_token),
                database.select_rows("rewards", {"select": "*", "order": "created_at.desc"}, access_token),
                database.select_rows("redemptions", {"select": "*", "order": "created_at.desc", "limit": "100"}, access_token),
                database.select_rows("points_ledger", {"select": "*", "order": "created_at.desc", "limit": "150"}, access_token),
                database.select_rows("admin_point_adjustments", {"select": "*", "order": "created_at.desc", "limit": "50"}, access_token),
                database.rpc("admin_sustainability_report", {}, access_token),
            ]
            results = await asyncio.gather(*calls, return_exceptions=True)
            keys = ["overview", "users", "households", "rewards", "redemptions", "ledger", "adjustments", "reports"]
            for key, result in zip(keys, results):
                if isinstance(result, Exception):
                    raise result
                data[key] = result or ({} if key in {"overview", "reports"} else [])
            selected["notice"] = ""
        except Exception as error:
            log.exception("Could not refresh admin data")
            selected["notice"] = f"Admin data could not be loaded: {_error_text(error)}. Confirm supabase_admin_dashboard.sql is installed and this account has the admin role."
        finally:
            selected["busy"] = False
            render()

    async def run_rpc(function_name, payload, success_message):
        try:
            await database.rpc(function_name, payload, access_token)
            await refresh_data()
            selected["notice"] = success_message
            render()
        except httpx.HTTPError as error:
            show_notice(f"Action failed: {_error_text(error)}")
        except Exception as error:
            show_notice(f"Action failed: {error}")

    async def search_users(e):
        await refresh_data()

    async def add_member(e):
        user_id = (member_user_id.value or "").strip()
        household_id = (member_household_id.value or "").strip()
        if not user_id or not household_id:
            show_notice("Enter both the user UUID and household UUID.")
            return
        await run_rpc(
            "admin_add_household_member",
            {"p_household_id": household_id, "p_user_id": user_id},
            "Member added to household.",
        )

    async def create_reward(e):
        try:
            cost = int((new_reward_cost.value or "").strip())
            stock = int((new_reward_stock.value or "").strip())
            name = (new_reward_title.value or "").strip()
            if not name or cost <= 0 or stock < 0:
                raise ValueError("Enter a title, positive points cost and non-negative stock.")
            await database.insert_row(
                "rewards",
                {"title": name, "description": (new_reward_description.value or "").strip(), "points_cost": cost, "stock": stock, "active": True},
                access_token,
            )
            new_reward_title.value = ""
            new_reward_description.value = ""
            new_reward_cost.value = ""
            new_reward_stock.value = ""
            await refresh_data()
            selected["notice"] = "Reward created."
            render()
        except ValueError as error:
            show_notice(str(error))
        except httpx.HTTPError as error:
            show_notice(f"Could not create reward: {_error_text(error)}")

    async def submit_adjustment(e):
        try:
            user_id = (adjust_user_id.value or "").strip()
            points = int((adjust_points_field.value or "").strip())
            reason = (adjust_reason.value or "").strip()
            if not user_id or points == 0 or len(reason) < 8:
                raise ValueError("Enter a user UUID, non-zero point amount, and reason of at least 8 characters.")
            await run_rpc(
                "admin_adjust_points",
                {"p_user_id": user_id, "p_points": points, "p_reason": reason},
                "Point adjustment recorded in the audit ledger.",
            )
        except ValueError as error:
            show_notice(str(error))

    async def patch_reward(reward_id, values, message):
        try:
            await database.patch_rows("rewards", {"id": f"eq.{reward_id}"}, values, access_token)
            await refresh_data()
            selected["notice"] = message
            render()
        except httpx.HTTPError as error:
            show_notice(f"Reward update failed: {_error_text(error)}")

    def overview_content():
        overview = data["overview"]
        metrics = [
            ("Registered users", overview.get("total_users", 0), ft.Icons.GROUP_OUTLINED),
            ("Households", overview.get("total_households", 0), ft.Icons.HOME_OUTLINED),
            ("Active users · 30 days", overview.get("active_users_30d", 0), ft.Icons.GROUP_OUTLINED),
            ("Walking points claimed", overview.get("walking_points_awarded", 0), ft.Icons.DIRECTIONS_WALK),
            ("Solar points claimed", overview.get("solar_points_awarded", 0), ft.Icons.SOLAR_POWER),
            ("Rewards redeemed", overview.get("rewards_redeemed", 0), ft.Icons.CARD_GIFTCARD),
        ]
        cards = [_metric_card(label, value, icon) for label, value, icon in metrics]
        return ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=14,
            controls=[
                title("Platform overview", "A live snapshot of sustainability activity and rewards."),
                ft.Row(controls=cards[:4], wrap=True, spacing=10, run_spacing=10),
                ft.Row(controls=cards[4:], wrap=True, spacing=10, run_spacing=10),
            ],
        )

    def users_content():
        user_rows = []
        for user in data["users"]:
            memberships = user.get("households") or []
            role_text = ", ".join(user.get("roles") or []) or "household user"
            status = user.get("account_status") or (
                "Email confirmed" if user.get("email_confirmed") else "Email not confirmed"
            )
            household_text = ", ".join(
                f"{membership.get('household_name', 'Household')} ({membership.get('member_role', 'member')})"
                for membership in memberships
            ) or "No household membership"
            actions = [
                ft.Button(
                    content=ft.Text(f"Remove from {membership.get('household_name', 'household')}"),
                    on_click=lambda e, household_id=membership.get("household_id"), user_id=user.get("user_id"): asyncio.create_task(
                        run_rpc(
                            "remove_household_member",
                            {"p_household_id": household_id, "p_user_id": user_id},
                            "Member removed from household.",
                        )
                    ),
                )
                for membership in memberships
                if membership.get("member_role") != "owner"
            ]
            user_rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(content=ft.Text(user.get("display_name") or "—")),
                        ft.DataCell(content=ft.Text(user.get("email") or "—")),
                        ft.DataCell(content=ft.Text(role_text)),
                        ft.DataCell(content=ft.Text(status)),
                        ft.DataCell(content=ft.Text(str(user.get("points_balance", 0)))),
                        ft.DataCell(content=ft.Text(household_text)),
                        ft.DataCell(content=ft.Text(str(user.get("user_id", "—")))),
                        ft.DataCell(
                            content=ft.Row(controls=actions, wrap=True, spacing=8)
                            if actions else ft.Text("—")
                        ),
                    ]
                )
            )
        users_table = ft.DataTable(
            columns=[
                ft.DataColumn(label=ft.Text("User")),
                ft.DataColumn(label=ft.Text("Email")),
                ft.DataColumn(label=ft.Text("Roles")),
                ft.DataColumn(label=ft.Text("Status")),
                ft.DataColumn(label=ft.Text("Points"), numeric=True),
                ft.DataColumn(label=ft.Text("Households")),
                ft.DataColumn(label=ft.Text("User UUID")),
                ft.DataColumn(label=ft.Text("Actions")),
            ],
            rows=user_rows,
        )

        household_rows = [
            ft.DataRow(
                cells=[
                    ft.DataCell(content=ft.Text(household.get("household_name", "Household"))),
                    ft.DataCell(content=ft.Text(household.get("owner_name") or "—")),
                    ft.DataCell(content=ft.Text(
                        f"{household.get('member_count', 0)} / {household.get('member_limit', '—')}"
                    )),
                    ft.DataCell(content=ft.Text(
                        "Active" if household.get("invite_active") else "Not available"
                    )),
                    ft.DataCell(content=ft.Text(str(household.get("created_at", ""))[:10] or "—")),
                    ft.DataCell(content=ft.Text(str(household.get("household_id", "—")))),
                ]
            )
            for household in data["households"]
        ]
        households_table = ft.DataTable(
            columns=[
                ft.DataColumn(label=ft.Text("Household")),
                ft.DataColumn(label=ft.Text("Owner")),
                ft.DataColumn(label=ft.Text("Members")),
                ft.DataColumn(label=ft.Text("Invite")),
                ft.DataColumn(label=ft.Text("Created")),
                ft.DataColumn(label=ft.Text("Household UUID")),
            ],
            rows=household_rows,
        )
        return ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=12,
            controls=[
                title("Users & households", "Search accounts, inspect roles and membership, and manage household membership."),
                ft.Row(controls=[search_field, ft.Button(content=ft.Text("Search"), on_click=search_users), ft.Button(content=ft.Text("Refresh"), on_click=lambda e: asyncio.create_task(refresh_data()))], spacing=8),
                panel(ft.Column(tight=True, spacing=8, controls=[
                    ft.Text("Add a member to a household", size=16, weight=ft.FontWeight.BOLD, color=ink_color()),
                    ft.Row(controls=[member_user_id, member_household_id, ft.Button(content=ft.Text("Add member"), on_click=add_member)], wrap=True, spacing=8),
                ])),
                ft.Text("Users", size=18, weight=ft.FontWeight.BOLD, color=ink_color()),
                ft.Row(scroll=ft.ScrollMode.AUTO, controls=[users_table]),
                *( [ft.Text("No accounts found.")] if not user_rows else [] ),
                ft.Text("Households", size=18, weight=ft.FontWeight.BOLD, color=ink_color()),
                ft.Row(scroll=ft.ScrollMode.AUTO, controls=[households_table]),
                *( [ft.Text("No households found.")] if not household_rows else [] ),
                panel(ft.Text("Account disable/reactivate requires a trusted Supabase Edge Function using the Auth admin API; it must not use a service-role key in this client app.", size=13, color=muted_color())),
            ],
        )

    def rewards_content():
        reward_cards = []
        for reward in data["rewards"]:
            rid = reward.get("id")
            active = bool(reward.get("active"))
            title_field = input_field(label="Title", value=reward.get("title", ""), width=300)
            description_field = input_field(label="Description", value=reward.get("description", ""), expand=True)
            points_field = input_field(label="Points", value=str(reward.get("points_cost", "")), width=110, keyboard_type=ft.KeyboardType.NUMBER)
            stock_field = input_field(label="Stock", value=str(reward.get("stock", "")), width=100, keyboard_type=ft.KeyboardType.NUMBER)

            async def save_reward(e, reward_id=rid, title_input=title_field, description_input=description_field, points_input=points_field, stock_input=stock_field):
                try:
                    await patch_reward(reward_id, {
                        "title": (title_input.value or "").strip(),
                        "description": (description_input.value or "").strip(),
                        "points_cost": int(points_input.value or "0"),
                        "stock": int(stock_input.value or "0"),
                    }, "Reward details updated.")
                except ValueError:
                    show_notice("Points and stock must be whole numbers.")

            reward_cards.append(_record_card(
                f"{reward.get('title')} · {'Available' if active else 'Unavailable'}",
                [f"Reward UUID: {rid}"],
                [
                    ft.Button(content=ft.Text("Save changes"), on_click=save_reward),
                    ft.Button(content=ft.Text("Make unavailable" if active else "Make available"), on_click=lambda e, reward_id=rid, current=active: asyncio.create_task(patch_reward(reward_id, {"active": not current}, "Reward availability updated."))),
                ],
                ft.Column(tight=True, spacing=8, controls=[
                    ft.Row(controls=[title_field, points_field, stock_field], wrap=True, spacing=8),
                    description_field,
                ]),
            ))
        redemption_cards = []
        reward_map = {item.get("id"): item.get("title", "Reward") for item in data["rewards"]}
        for redemption in data["redemptions"]:
            rid = redemption.get("id")
            status = redemption.get("status")
            actions = []
            if status == "requested":
                actions = [
                    ft.Button(content=ft.Text("Mark fulfilled"), on_click=lambda e, redemption_id=rid: asyncio.create_task(run_rpc("admin_update_redemption", {"p_redemption_id": redemption_id, "p_new_status": "fulfilled"}, "Redemption marked fulfilled."))),
                    ft.Button(content=ft.Text("Cancel + refund"), on_click=lambda e, redemption_id=rid: asyncio.create_task(run_rpc("admin_update_redemption", {"p_redemption_id": redemption_id, "p_new_status": "cancelled"}, "Redemption cancelled and points refunded."))),
                ]
            redemption_cards.append(_record_card(
                f"{reward_map.get(redemption.get('reward_id'), 'Reward')} · {str(status).title()}",
                [f"User: {user_name(redemption.get('user_id', ''))} · Points: {redemption.get('points_spent')}",
                 f"Created: {str(redemption.get('created_at', ''))[:19]} · Redemption UUID: {rid}"],
                actions,
            ))
        return ft.Column(
            expand=True, scroll=ft.ScrollMode.AUTO, spacing=12,
            controls=[title("Rewards & redemptions", "Manage reward availability, points cost and stock; fulfil or cancel redemption requests."),
                panel(ft.Column(tight=True, spacing=8, controls=[
                    ft.Text("Add reward", size=16, weight=ft.FontWeight.BOLD, color=ink_color()),
                    ft.Row(controls=[new_reward_title, new_reward_cost, new_reward_stock], wrap=True, spacing=8),
                    new_reward_description,
                    ft.Button(content=ft.Text("Create reward"), on_click=create_reward),
                ])),
                ft.Text("Reward catalogue", size=18, weight=ft.FontWeight.BOLD, color=ink_color()),
                *(reward_cards or [ft.Text("No rewards configured.")]),
                ft.Text("Redemption history", size=18, weight=ft.FontWeight.BOLD, color=ink_color()),
                *(redemption_cards or [ft.Text("No redemptions recorded.")]),
            ],
        )

    def points_content():
        ledger_cards = [
            _record_card(
                f"{entry.get('points', 0):+} points · {str(entry.get('entry_type', '')).replace('_', ' ').title()}",
                [f"User: {user_name(entry.get('user_id', ''))} · Date: {str(entry.get('created_at', ''))[:19]}",
                 f"Source: {entry.get('source_id')} · {entry.get('note') or '—'}"],
            ) for entry in data["ledger"]
        ]
        audit_cards = [
            _record_card(
                f"{item.get('points', 0):+} points · {item.get('reason')}",
                [f"User: {user_name(item.get('user_id', ''))} · Admin: {user_name(item.get('created_by', ''))}",
                 f"Audit record: {item.get('id')} · {str(item.get('created_at', ''))[:19]}"],
            ) for item in data["adjustments"]
        ]
        return ft.Column(
            expand=True, scroll=ft.ScrollMode.AUTO, spacing=12,
            controls=[title("Points & transactions", "Trace every award, redemption and correction to its source."),
                panel(ft.Column(tight=True, spacing=8, controls=[
                    ft.Text("Audited point correction", size=16, weight=ft.FontWeight.BOLD, color=ink_color()),
                    ft.Row(controls=[adjust_user_id, adjust_points_field, adjust_reason, ft.Button(content=ft.Text("Record adjustment"), on_click=submit_adjustment)], wrap=True, spacing=8),
                    ft.Text("Positive or negative values are recorded as an immutable ledger entry with the reason.", size=12, color=muted_color()),
                ])),
                ft.Text("Adjustment audit log", size=18, weight=ft.FontWeight.BOLD, color=ink_color()),
                *(audit_cards or [ft.Text("No manual corrections recorded.")]),
                ft.Text("Recent point transactions", size=18, weight=ft.FontWeight.BOLD, color=ink_color()),
                *(ledger_cards or [ft.Text("No point transactions recorded.")]),
            ],
        )

    def reports_content():
        report = data["reports"]
        overview = data["overview"]
        metrics = [
            ("Points spent on rewards", report.get("points_spent", 0), ft.Icons.CARD_GIFTCARD),
            ("Walking points claimed", overview.get("walking_points_awarded", report.get("walking_points_claimed", 0)), ft.Icons.DIRECTIONS_WALK),
            ("Solar points claimed", overview.get("solar_points_awarded", report.get("solar_points_claimed", 0)), ft.Icons.SOLAR_POWER),
        ]
        return ft.Column(
            expand=True, scroll=ft.ScrollMode.AUTO, spacing=12,
            controls=[
                title("Activity reports", "Live Supabase totals for points spent on rewards and claimed from walking and solar."),
                ft.Row(controls=[_metric_card(label, value, icon) for label, value, icon in metrics], wrap=True, spacing=10, run_spacing=10),
            ],
        )

    def screen_content():
        if selected["busy"]:
            return ft.Column(expand=True, alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, controls=[ft.ProgressRing(), ft.Text("Loading platform data...")])
        builders = [overview_content, users_content, rewards_content, points_content, reports_content]
        return builders[selected["screen"]]()

    def toggle_sidebar():
        selected["sidebar_collapsed"] = not selected["sidebar_collapsed"]
        render()

    def nav_button(index, label, icon):
        collapsed = selected["sidebar_collapsed"]
        nav_content = ft.Row(
            expand=True,
            alignment=ft.MainAxisAlignment.CENTER if collapsed else ft.MainAxisAlignment.START,
            controls=[ft.Icon(icon, size=20 if collapsed else 18)]
            if collapsed
            else [ft.Icon(icon, size=18), ft.Text(label)],
            spacing=10,
        )
        return ft.Button(
            content=nav_content,
            expand=True,
            tooltip=label,
            bgcolor=surface_tint() if selected["screen"] == index else ft.Colors.TRANSPARENT,
            color=ink_color(),
            on_click=lambda e, i=index: navigate(i),
        )

    def render():
        collapsed = selected["sidebar_collapsed"]
        header_controls = []
        if not collapsed:
            header_controls.append(
                ft.Column(
                    expand=True,
                    tight=True,
                    spacing=2,
                    controls=[
                        ft.Text("ADMIN CONSOLE", size=12, weight=ft.FontWeight.BOLD, color=brand_color()),
                        ft.Text("Platform management", size=16, weight=ft.FontWeight.BOLD, color=ink_color()),
                    ],
                )
            )
        header_controls.append(
            ft.IconButton(
                icon=ft.Icons.MENU if collapsed else ft.Icons.MENU_OPEN,
                tooltip="Expand sidebar" if collapsed else "Collapse sidebar",
                on_click=toggle_sidebar,
            )
        )
        sidebar_controls = [
            ft.Row(
                controls=header_controls,
                alignment=ft.MainAxisAlignment.CENTER if collapsed else ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Divider(),
            *(nav_button(i, label, icon) for i, (label, icon) in enumerate(NAV_ITEMS)),
            ft.Container(expand=True),
        ]
        if not collapsed:
            sidebar_controls.append(ft.Text("Role verified by Supabase", size=11, color=muted_color()))
        sidebar = ft.Container(
            width=72 if collapsed else 230,
            content=ft.Column(controls=sidebar_controls, expand=True, spacing=8),
            padding=8 if collapsed else 12,
            bgcolor=surface_color(),
            border_radius=16,
        )
        body_controls = []
        if selected["notice"]:
            body_controls.append(panel(ft.Text(selected["notice"], color=error_color(), size=13), bgcolor=error_surface_color(), padding=10))
        body_controls.append(ft.Container(expand=True, content=screen_content()))
        root.content = ft.Row(
            expand=True,
            spacing=14,
            controls=[sidebar, ft.Container(expand=True, content=ft.Column(expand=True, spacing=12, controls=body_controls))],
        )
        if mounted["value"]:
            root.update()

    def navigate(index):
        selected["screen"] = index
        selected["notice"] = ""
        render()

    def platform_brightness_changed(event):
        if current_theme_mode() == "system":
            apply_theme(page, "system", event.brightness)
            render()
            if mounted["value"]:
                page.update()

    page.on_platform_brightness_change = platform_brightness_changed
    page.bgcolor = canvas_color()
    page.appbar = ft.AppBar(
        title=ft.Text("Townly · Admin"),
        actions=[
            ft.IconButton(icon=ft.Icons.REFRESH, tooltip="Refresh data", on_click=lambda e: asyncio.create_task(refresh_data())),
            ft.TextButton(content=ft.Text("Sign out"), on_click=on_logout),
        ],
    )
    page.navigation_bar = None
    page.add(root)
    mounted["value"] = True
    render()
    await refresh_data()
