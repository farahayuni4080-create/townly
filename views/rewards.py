"""Mobile-first MyRewards catalogue, wallet, voucher detail, and QR screens."""

import asyncio
import logging
from datetime import date

import flet as ft
import qrcode

from components import (
    border_color,
    brand_color,
    canvas_color,
    ink_color,
    input_field,
    muted_color,
    reward_button_text_color,
    reward_color,
    reward_surface_color,
    surface_color,
    surface_tint,
)
from myrewards import (
    activate_qr,
    add_promo_voucher,
    available_points,
    has_redeemed_reward,
    mark_voucher_used,
    qr_seconds_remaining,
    redeem_reward,
    merge_cloud_vouchers,
    reward_for,
)

log = logging.getLogger(f"app.{__name__}")
BORDER = ft.Colors.GREY_200
DISABLED = ft.Colors.GREY_400
TERMS = [
    "Vouchers are not transferable.",
    "Vouchers are not exchangeable for cash and are non-refundable.",
    "Vouchers cannot be combined with other promotions unless stated.",
    "Misuse may result in voucher cancellation or account termination.",
]


def _card(content, padding=14):
    return ft.Container(
        content=content,
        padding=padding,
        bgcolor=surface_color(),
        border=ft.Border.all(1, border_color()),
        border_radius=10,
    )


def _brand_color(brand):
    palette = {
        "ZUS Coffee": ft.Colors.BLUE_700,
        "Tealive": ft.Colors.PURPLE_700,
        "Inside Scoop": ft.Colors.PINK_700,
        "MR DIY": ft.Colors.ORANGE_800,
        "Sime Darby Property": ft.Colors.TEAL_700,
        "Mee Hiris China Muslim": ft.Colors.DEEP_ORANGE_700,
        "Ali, Muthu & Ah Hock": ft.Colors.ORANGE_800,
        "Bayu Somerset": ft.Colors.DEEP_PURPLE_700,
        "Kenny Hills Bakers": ft.Colors.BROWN_700,
        "Watsons": ft.Colors.BLUE_700,
        "Golf & Country Club": ft.Colors.GREEN_700,
        "Parking Perk": ft.Colors.BLUE_GREY_700,
        "Touch ‘n Go eWallet": ft.Colors.TEAL_700,
    }
    return palette.get(brand, brand_color())


def _brand_mark(brand, logo_url):
    initials = "".join(word[0] for word in brand.split()[:2]).upper()
    if logo_url:
        mark = ft.Image(
            src=logo_url,
            width=20,
            height=20,
            fit=ft.BoxFit.CONTAIN,
            error_content=ft.Text(initials, size=8, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_800),
        )
    else:
        mark = ft.Text(initials, size=8, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_800)
    return ft.Container(
        width=23,
        height=23,
        padding=2,
        alignment=ft.Alignment.CENTER,
        bgcolor="#F5DABF",
        border_radius=12,
        content=mark,
    )


def _voucher_status(status):
    return {"active": "Active", "used": "Used", "expired": "Expired"}.get(
        status, str(status).title()
    )


def _short_date(value):
    try:
        return date.fromisoformat(value).strftime("%d %b %Y")
    except (TypeError, ValueError):
        return value or "—"


def build(
    page,
    catalog,
    feature_state,
    account_balance,
    view_state,
    on_persist,
    on_redeem,
    cloud_ready,
    on_render,
    on_back,
):
    """Build the current rewards sub-screen from shared local state."""
    view_state.setdefault("tab", "Rewards")
    view_state.setdefault("screen", "catalog")
    view_state.setdefault("walletFilter", "active")
    view_state.setdefault("promoCode", "")
    view_state.setdefault("promoMessage", "")
    view_state.setdefault("selectedVoucherId", None)
    view_state.setdefault("qrVoucherId", None)
    from myrewards import expire_vouchers

    expire_vouchers(feature_state)

    def balance():
        amount = available_points(feature_state, account_balance)
        feature_state["user"]["pointsBalance"] = amount
        return amount

    def refresh():
        on_render()

    async def persist_state():
        try:
            await on_persist()
            return True
        except Exception as error:
            log.warning("Could not sync MyRewards wallet to Supabase: %s", error)
            page.show_dialog(
                ft.AlertDialog(
                    modal=True,
                    title=ft.Text("Wallet sync failed"),
                    content=ft.Text("The shared wallet could not be updated. Check your connection and try again."),
                    actions=[ft.TextButton(content="OK", on_click=lambda _: page.pop_dialog())],
                )
            )
            return False

    async def persist_refresh():
        await persist_state()
        refresh()

    def find_voucher(voucher_id):
        return next(
            (voucher for voucher in feature_state.get("vouchers", []) if voucher.get("id") == voucher_id),
            None,
        )

    def open_voucher(voucher_id):
        view_state["selectedVoucherId"] = voucher_id
        view_state["screen"] = "detail"
        refresh()

    def back_to_wallet():
        view_state["screen"] = "catalog"
        view_state["tab"] = "My Vouchers"
        refresh()

    def back_from_qr():
        view_state["screen"] = "detail"
        view_state["qrVoucherId"] = None
        refresh()

    async def confirm_reward(reward):
        page.pop_dialog()
        if not cloud_ready:
            page.show_dialog(
                ft.AlertDialog(
                    modal=True,
                    title=ft.Text("Wallet unavailable"),
                    content=ft.Text("Could not connect to the shared Supabase wallet. Try again when online."),
                    actions=[ft.TextButton(content="OK", on_click=lambda _: page.pop_dialog())],
                )
            )
            return
        if not reward or not reward.get("active"):
            issue = "This reward is no longer available."
            voucher = None
        elif has_redeemed_reward(feature_state, reward.get("id")):
            issue = "You have already redeemed this reward."
            voucher = None
        elif balance() < int(reward["pointsCost"]):
            issue = f"You need {int(reward['pointsCost']) - balance()} more points to redeem this reward."
            voucher = None
        else:
            voucher, issue = await on_redeem(reward)
        if issue or not voucher:
            page.show_dialog(
                ft.AlertDialog(
                    modal=True,
                    title=ft.Text("Redemption failed"),
                    content=ft.Text(issue or "Supabase could not confirm this redemption."),
                    actions=[ft.TextButton(content="OK", on_click=lambda _: page.pop_dialog())],
                )
            )
            return
        view_state["tab"] = "My Vouchers"
        view_state["screen"] = "catalog"
        await persist_state()
        refresh()
        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Voucher added"),
                content=ft.Text("Your reward is now in My Vouchers."),
                actions=[ft.TextButton(content="Great", on_click=lambda _: page.pop_dialog())],
            )
        )

    def ask_redeem(reward):
        if has_redeemed_reward(feature_state, reward["id"]):
            page.show_dialog(
                ft.AlertDialog(
                    modal=True,
                    title=ft.Text("Already redeemed"),
                    content=ft.Text("You can redeem each reward only once."),
                    actions=[ft.TextButton(content="OK", on_click=lambda _: page.pop_dialog())],
                )
            )
            return
        if balance() < int(reward["pointsCost"]):
            page.show_dialog(
                ft.AlertDialog(
                    modal=True,
                    title=ft.Text("Not enough points"),
                    content=ft.Text(
                        f"You have {balance():,} points. This reward needs {reward['pointsCost']:,}."
                    ),
                    actions=[ft.TextButton(content="OK", on_click=lambda _: page.pop_dialog())],
                )
            )
            return
        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                barrier_color=ft.Colors.with_opacity(0.58, "#082523"),
                title=ft.Text("Confirm redemption"),
                content=ft.Text(f"Use {reward['pointsCost']:,} points for this reward?"),
                actions=[
                    ft.TextButton(content="No", on_click=lambda _: page.pop_dialog()),
                    ft.Button(
                        content="Yes",
                        bgcolor=reward_color(),
                        color=reward_button_text_color(),
                        on_click=lambda _: asyncio.create_task(confirm_reward(reward)),
                    ),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
        )

    def apply_promo():
        voucher, message = add_promo_voucher(
            feature_state, catalog, view_state.get("promoCode", "")
        )
        view_state["promoMessage"] = message
        if voucher:
            view_state["promoCode"] = ""
            view_state["tab"] = "My Vouchers"
            view_state["walletFilter"] = "active"
            asyncio.create_task(persist_refresh())
        else:
            refresh()

    async def activate(voucher):
        page.pop_dialog()
        token, issue = activate_qr(voucher)
        if issue:
            page.show_dialog(
                ft.AlertDialog(
                    modal=True,
                    title=ft.Text("Voucher unavailable"),
                    content=ft.Text(issue),
                    actions=[ft.TextButton(content="OK", on_click=lambda _: page.pop_dialog())],
                )
            )
            return
        view_state["qrVoucherId"] = voucher["id"]
        view_state["screen"] = "qr"
        await on_persist()
        refresh()
        asyncio.create_task(countdown(voucher["id"]))

    async def countdown(voucher_id):
        while view_state.get("screen") == "qr" and view_state.get("qrVoucherId") == voucher_id:
            voucher = find_voucher(voucher_id)
            remaining = qr_seconds_remaining(voucher)
            if remaining <= 0:
                view_state["screen"] = "detail"
                view_state["qrVoucherId"] = None
                await on_persist()
                refresh()
                page.show_dialog(
                    ft.AlertDialog(
                        modal=True,
                        title=ft.Text("QR code expired"),
                        content=ft.Text("Your voucher is still active. Generate a fresh QR code when you are ready to redeem it."),
                        actions=[ft.TextButton(content="OK", on_click=lambda _: page.pop_dialog())],
                    )
                )
                return
            view_state["secondsRemaining"] = remaining
            timer_control = view_state.get("timerControl")
            if timer_control is not None:
                timer_control.value = f"{remaining // 60}:{remaining % 60:02d}"
                timer_control.update()
            await asyncio.sleep(1)

    async def mark_used_now(voucher):
        if mark_voucher_used(feature_state, voucher):
            view_state["screen"] = "catalog"
            view_state["tab"] = "My Vouchers"
            view_state["walletFilter"] = "used"
            view_state["qrVoucherId"] = None
            await persist_refresh()
            page.show_dialog(
                ft.AlertDialog(
                    modal=True,
                    title=ft.Text("Voucher redeemed"),
                    content=ft.Text("This voucher has been marked as used and cannot be redeemed again."),
                    actions=[ft.TextButton(content="Done", on_click=lambda _: page.pop_dialog())],
                )
            )
        else:
            page.show_dialog(
                ft.AlertDialog(
                    modal=True,
                    title=ft.Text("QR code expired"),
                    content=ft.Text("Activate the voucher again to get a fresh QR code."),
                    actions=[ft.TextButton(content="OK", on_click=lambda _: page.pop_dialog())],
                )
            )

    def tab_button(label):
        selected = view_state.get("tab") == label
        return ft.Container(
            content=ft.Column(
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=7,
                controls=[
                    ft.Text(
                        label,
                        size=13,
                        weight=ft.FontWeight.BOLD if selected else ft.FontWeight.NORMAL,
                        color=reward_color() if selected else muted_color(),
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Container(height=3, bgcolor=reward_color() if selected else ft.Colors.TRANSPARENT, border_radius=4),
                ],
            ),
            expand=True,
            padding=ft.Padding.symmetric(vertical=10),
            on_click=lambda _, label=label: switch_tab(label),
        )

    def switch_tab(label):
        view_state["tab"] = label
        view_state["screen"] = "catalog"
        refresh()

    def catalogue_card(reward):
        redeemed = has_redeemed_reward(feature_state, reward["id"])
        affordable = balance() >= int(reward["pointsCost"]) and not redeemed
        brand = reward["brand"]
        image_height = 72 if (page.width or 800) < 600 else 88
        return ft.Container(
            padding=9,
            bgcolor=surface_color(),
            border=ft.Border.all(1, border_color()),
            border_radius=10,
            content=ft.Column(
                spacing=6,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[
                    ft.Container(
                        height=30,
                        alignment=ft.Alignment.CENTER_LEFT,
                        content=ft.Row(
                            tight=True,
                            controls=[
                                ft.Container(
                                    content=ft.Row(
                                        tight=True,
                                        spacing=5,
                                        controls=[
                                            _brand_mark(brand, reward.get("logoUrl")),
                                            ft.Text(
                                                brand,
                                                size=9,
                                                weight=ft.FontWeight.BOLD,
                                                color="#F5DABF",
                                                max_lines=1,
                                                overflow=ft.TextOverflow.ELLIPSIS,
                                            ),
                                        ],
                                    ),
                                    bgcolor=_brand_color(brand),
                                    padding=ft.Padding.symmetric(horizontal=5, vertical=4),
                                    border_radius=14,
                                )
                            ],
                        ),
                    ),
                    ft.Image(src=reward["imageUrl"], height=image_height, fit=ft.BoxFit.CONTAIN, border_radius=12),
                    ft.Text(reward["title"], size=13, weight=ft.FontWeight.BOLD, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS, color=ink_color()),
                    ft.Text(reward["description"], size=10, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS, color=muted_color()),
                    ft.Text(reward["valueLabel"], size=10, weight=ft.FontWeight.W_600, color=muted_color()),
                    ft.Container(
                        padding=ft.Padding.symmetric(horizontal=9, vertical=5),
                        bgcolor=reward_surface_color(),
                        border_radius=12,
                        content=ft.Text(
                            f"{int(reward['pointsCost']):,} points",
                            size=12,
                            weight=ft.FontWeight.BOLD,
                            color=reward_color(),
                            max_lines=1,
                            no_wrap=True,
                        ),
                    ),
                    ft.Container(expand=True),
                    ft.Button(
                        content="REDEEMED" if redeemed else "REDEEM",
                        bgcolor=DISABLED if redeemed else (reward_color() if affordable else DISABLED),
                        color=reward_button_text_color(),
                        disabled=not affordable,
                        on_click=lambda _, reward=reward: ask_redeem(reward),
                    ),
                ],
            ),
        )

    def points_screen():
        active_rewards = [reward for reward in catalog["rewards"] if reward.get("active", True)]
        cards = [catalogue_card(reward) for reward in active_rewards]
        screen_width = page.width or 800
        if screen_width < 430:
            max_extent, tile_aspect_ratio = 190, 0.52
        elif screen_width < 700:
            max_extent, tile_aspect_ratio = 260, 0.62
        else:
            max_extent, tile_aspect_ratio = 160, 0.45
        grid = ft.GridView(
            expand=True,
            max_extent=max_extent,
            spacing=10,
            run_spacing=10,
            child_aspect_ratio=tile_aspect_ratio,
            padding=ft.Padding.only(left=2, right=2, top=4, bottom=16),
            controls=cards,
        )
        return grid

    def wallet_screen():
        promo_field = input_field(
            value=view_state.get("promoCode", ""),
            hint_text="ENTER PROMO CODE",
            text_size=13,
            border_radius=10,
            on_change=lambda event: view_state.update({"promoCode": event.control.value}),
            col={"xs": 12, "sm": 9},
        )
        available = [
            voucher
            for voucher in feature_state.get("vouchers", [])
            if view_state.get("walletFilter", "active") == "all"
            or voucher.get("status") == view_state.get("walletFilter", "active")
        ]
        rows = []
        for voucher in available:
            reward = reward_for(catalog, voucher.get("rewardId"))
            if reward is None:
                continue
            state_label = _voucher_status(voucher.get("status"))
            state_color = reward_color() if state_label == "Active" else muted_color()
            rows.append(
                _card(
                    ft.Row(
                        spacing=11,
                        controls=[
                            ft.Image(src=reward["imageUrl"], width=94, height=95, fit=ft.BoxFit.COVER, border_radius=12),
                            ft.Column(
                                expand=True,
                                spacing=5,
                                controls=[
                                    ft.Text(reward["title"], size=14, weight=ft.FontWeight.BOLD, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                                    ft.Text("Redeem in store", size=11, color=muted_color()),
                                    ft.Text(f"Valid till {_short_date(voucher.get('validTill'))}", size=11, color=muted_color()),
                                    ft.Text("1/1 voucher left" if state_label == "Active" else state_label, size=11, color=state_color, weight=ft.FontWeight.BOLD),
                                    *(
                                        [
                                            ft.Button(
                                                content="REDEEM",
                                                bgcolor=reward_color(),
                                                color=reward_button_text_color(),
                                                on_click=lambda _, voucher_id=voucher["id"]: open_voucher(voucher_id),
                                            )
                                        ]
                                        if state_label == "Active"
                                        else []
                                    ),
                                ],
                            ),
                        ],
                    ),
                    padding=10,
                )
            )
        if not rows:
            rows.append(
                ft.Container(
                    expand=True,
                    alignment=ft.Alignment.CENTER,
                    padding=24,
                    content=ft.Column(
                        tight=True,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                        controls=[
                            ft.Icon(ft.Icons.CONFIRMATION_NUMBER, size=42, color=muted_color()),
                            ft.Text("No vouchers here yet", size=16, weight=ft.FontWeight.BOLD),
                            ft.Text("Redeemed rewards and promo vouchers will appear in your wallet.", size=12, color=muted_color(), text_align=ft.TextAlign.CENTER),
                        ],
                    ),
                )
            )
        filters = ft.Row(
            spacing=8,
            controls=[filter_button("Active", "active"), filter_button("Used", "used"), filter_button("Expired", "expired"), filter_button("All", "all")],
        )
        return ft.Column(
            expand=True,
            spacing=12,
            controls=[
                ft.ResponsiveRow(
                    spacing=8,
                    run_spacing=8,
                    controls=[
                        promo_field,
                        ft.Button(
                            content="APPLY",
                            bgcolor=reward_color(),
                            color=reward_button_text_color(),
                            on_click=lambda _: apply_promo(),
                            col={"xs": 12, "sm": 3},
                        ),
                    ],
                ),
                ft.Text(view_state.get("promoMessage", ""), size=12, color=reward_color() if "added" in view_state.get("promoMessage", "").lower() else ft.Colors.RED_600),
                filters,
                ft.ListView(expand=True, spacing=12, padding=ft.Padding.only(bottom=4), controls=rows),
            ],
        )

    def filter_button(label, value):
        selected = view_state.get("walletFilter", "active") == value
        return ft.TextButton(
            content=label,
            style=ft.ButtonStyle(
                color=reward_button_text_color() if selected else muted_color(),
                
                bgcolor=reward_color() if selected else surface_tint(),
                shape=ft.RoundedRectangleBorder(radius=18),
                padding=ft.Padding.symmetric(horizontal=12, vertical=7),
            ),
            on_click=lambda _, value=value: set_filter(value),
        )

    def set_filter(value):
        view_state["walletFilter"] = value
        refresh()

    def detail_screen():
        voucher = find_voucher(view_state.get("selectedVoucherId"))
        reward = reward_for(catalog, voucher.get("rewardId")) if voucher else None
        if not voucher or not reward:
            view_state["screen"] = "catalog"
            view_state["tab"] = "My Vouchers"
            return wallet_screen()
        active = voucher.get("status") == "active"
        terms = [*reward.get("termsList", []), *catalog.get("standardTerms", TERMS)]
        terms_panel = ft.Container(
            expand=True,
            padding=18,
            bgcolor=surface_color(),
            border=ft.Border.only(top=ft.BorderSide(width=1, color=border_color())),
            border_radius=ft.BorderRadius.only(top_left=12, top_right=12),
            content=ft.Column(
                expand=True,
                spacing=10,
                controls=[
                    ft.Container(width=38, height=4, bgcolor=muted_color(), border_radius=5, alignment=ft.Alignment.CENTER),
                    ft.Text(reward["title"], size=19, weight=ft.FontWeight.BOLD),
                    ft.Text(reward["description"], size=13, color=muted_color()),
                    ft.Text(f"{reward['valueLabel']} · Valid till {_short_date(voucher['validTill'])}", size=12, color=reward_color(), weight=ft.FontWeight.BOLD),
                    ft.Text("TERMS & CONDITIONS", size=13, weight=ft.FontWeight.BOLD),
                    ft.ListView(
                        expand=True,
                        spacing=9,
                        controls=[ft.Text(f"• {term}", size=12, color=muted_color()) for term in terms],
                    ),
                ],
            ),
        )
        return ft.Column(
            expand=True,
            spacing=0,
            controls=[
                ft.Image(src=reward["imageUrl"], height=185, fit=ft.BoxFit.COVER),
                terms_panel,
                ft.Container(
                    padding=ft.Padding.only(left=18, right=18, top=10, bottom=12),
                    bgcolor=surface_color(),
                    content=ft.Button(
                        content="REDEEM" if active else _voucher_status(voucher.get("status")).upper(),
                        bgcolor=reward_color() if active else DISABLED,
                        color=reward_button_text_color(),
                        disabled=not active,
                        on_click=lambda _: ask_activate(voucher),
                    ),
                ),
            ],
        )

    def ask_activate(voucher):
        if voucher.get("status") != "active":
            return
        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                icon=ft.Icon(ft.Icons.INFO, color=reward_color(), size=38),
                title=ft.Text("QR Code will only be valid for 5 minutes", size=16, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
                content=ft.Text("Please only activate this reward when you are at the cashier. Do you want to proceed?", size=13, text_align=ft.TextAlign.CENTER),
                actions=[
                    ft.OutlinedButton(content="No", on_click=lambda _: page.pop_dialog()),
                    ft.Button(content="Yes", bgcolor=reward_color(), color=reward_button_text_color(), on_click=lambda _: asyncio.create_task(activate(voucher))),
                ],
                actions_alignment=ft.MainAxisAlignment.CENTER,
            )
        )

    def qr_screen():
        voucher = find_voucher(view_state.get("qrVoucherId"))
        reward = reward_for(catalog, voucher.get("rewardId")) if voucher else None
        if not voucher or not reward:
            view_state["screen"] = "detail"
            return detail_screen()
        remaining = qr_seconds_remaining(voucher)
        if remaining <= 0:
            view_state["screen"] = "detail"
            view_state["qrVoucherId"] = None
            return detail_screen()
        qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=1, border=4)
        qr.add_data(voucher["qrToken"])
        qr.make(fit=True)
        matrix = qr.get_matrix()
        qr_rows = [
            ft.Row(
                tight=True,
                spacing=0,
                controls=[
                    ft.Container(width=5, height=5, bgcolor="#2B0C10" if module else "#F5DABF")
                    for module in row
                ],
            )
            for row in matrix
        ]
        seconds = int(remaining)
        timer_text = f"{seconds // 60}:{seconds % 60:02d}"
        timer_control = ft.Text(timer_text, size=32, weight=ft.FontWeight.BOLD, color=reward_color())
        view_state["timerControl"] = timer_control
        return ft.Column(
            expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=12,
            controls=[
                ft.Row(
                    controls=[
                        ft.IconButton(icon=ft.Icons.ARROW_BACK, icon_color=reward_color(), on_click=lambda _: back_from_qr()),
                        ft.Text("MY VOUCHERS", size=16, weight=ft.FontWeight.BOLD, color=reward_color()),
                        ft.Container(width=40),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Text("Show this QR code at the cashier", size=14, color=muted_color(), text_align=ft.TextAlign.CENTER),
                ft.Container(
                    padding=12,
                    bgcolor="#F5DABF",
                    border=ft.Border.all(1, border_color()),
                    border_radius=10,
                    content=ft.Column(tight=True, spacing=0, controls=qr_rows),
                ),
                timer_control,
                ft.Text(reward["title"], size=16, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
                ft.Text(f"Voucher code: {voucher['qrToken']}", size=12, color=muted_color(), text_align=ft.TextAlign.CENTER),
                ft.Text("For this demo, confirm the cashier scan below.", size=11, color=muted_color(), text_align=ft.TextAlign.CENTER),
                ft.Button(content="CONFIRM SCAN · MARK USED", bgcolor=reward_color(), color=reward_button_text_color(), on_click=lambda _: asyncio.create_task(mark_used_now(voucher))),
            ],
        )

    if view_state.get("screen") == "qr":
        return ft.Container(expand=True, padding=12, bgcolor=canvas_color(), content=qr_screen())
    if view_state.get("screen") == "detail":
        return ft.Container(expand=True, padding=ft.Padding.only(left=10, right=10, top=8), bgcolor=canvas_color(), content=ft.Column(expand=True, spacing=8, controls=[
            ft.Row(controls=[ft.IconButton(icon=ft.Icons.ARROW_BACK, icon_color=reward_color(), on_click=lambda _: back_to_wallet()), ft.Text("VOUCHER DETAILS", size=14, weight=ft.FontWeight.BOLD, color=reward_color())]),
            detail_screen(),
        ]))

    header = ft.Row(
        controls=[
            ft.IconButton(icon=ft.Icons.ARROW_BACK, icon_color=reward_color(), tooltip="Back to app", on_click=lambda _: on_back()),
            ft.Text("MYREWARDS", size=17, weight=ft.FontWeight.BOLD, color=reward_color()),
            ft.Container(width=42),
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
    )
    if view_state.get("tab") not in {"My Vouchers", "Rewards"}:
        view_state["tab"] = "Rewards"
    tabs = ft.Row(spacing=0, controls=[tab_button(label) for label in ("My Vouchers", "Rewards")])
    if view_state.get("tab") == "My Vouchers":
        body = wallet_screen()
    else:
        body = points_screen()
    return ft.Container(
        expand=True,
        padding=ft.Padding.only(left=12, right=12, top=8, bottom=8),
        bgcolor=canvas_color(),
        content=ft.Column(expand=True, spacing=8, controls=[header, tabs, body]),
    )
