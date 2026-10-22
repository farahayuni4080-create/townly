"""Solar claim form and household claim history."""

import calendar
from datetime import date

import flet as ft

from components import (
    border_color,
    brand_color,
    brand_button_text_color,
    error_color,
    error_surface_color,
    ink_color,
    muted_color,
    panel,
    section_heading,
    success_color,
    surface_color,
    surface_tint,
    title,
    warning_color,
)
from views.solar_claim_status import build_period_status, find_period_claim

def _styled_card(content, *, bgcolor=None, padding=18, border=None, border_radius=16):
    return ft.Container(
        content=content,
        padding=padding,
        bgcolor=surface_color() if bgcolor is None else bgcolor,
        border=border or ft.Border.all(1, border_color()),
        border_radius=border_radius,
    )


def build(
    *,
    household_name,
    household_id,
    history,
    form_state,
    can_submit,
    on_month_change,
    on_year_change,
    ocr_supported,
    on_upload,
):
    today = date.today()
    current_month = str(form_state.get("month", today.month))
    current_year = str(form_state.get("year", today.year))
    month_options = [
        ft.DropdownOption(key=str(number), text=calendar.month_name[number])
        for number in range(1, 13)
    ]
    year_options = [
        ft.DropdownOption(key=str(year), text=str(year))
        for year in range(today.year, 1999, -1)
    ]
    controls = [
        title(
            "Claim Solar Points",
            "Submit your monthly solar generation report to earn family points.",
        ),
    ]

    household_card = _styled_card(
        ft.Row(
            controls=[
                ft.Icon(ft.Icons.HOME, color=success_color(), size=24),
                ft.Column(
                    controls=[
                        ft.Text("Household", size=12, color=muted_color()),
                        ft.Text(household_name or "Household not linked", size=16, weight=ft.FontWeight.BOLD, color=ink_color()),
                    ],
                    spacing=2,
                    expand=True,
                ),
            ],
        ),
        padding=16,
        bgcolor=surface_tint(),
        border=ft.Border.all(1, border_color()),
        border_radius=16,
    )
    controls.append(household_card)

    period_claim = find_period_claim(history, current_month, current_year)
    period_status, period_redeemed = build_period_status(
        period_claim, current_month, current_year
    )
    if household_id and not can_submit:
        controls.append(period_status)

    if not household_id:
        controls.append(
            panel(
                ft.Text(
                    "Link this account to a household in the Family tab before submitting solar claims.",
                    color=ink_color(),
                ),
                bgcolor=surface_tint(),
            )
        )

    if can_submit:
        month_year = ft.Column(
            controls=[
                ft.Dropdown(
                    label="Claim month",
                    value=current_month,
                    options=month_options,
                    on_select=on_month_change,
                ),
                ft.Dropdown(
                    label="Claim year",
                    value=current_year,
                    options=year_options,
                    on_select=on_year_change,
                ),
            ],
            spacing=10,
        )
        controls.append(
            _styled_card(
                ft.Column(
                    controls=[ft.Text("Claim period", size=16, weight=ft.FontWeight.BOLD, color=ink_color()), month_year],
                    spacing=10,
                ),
                padding=14,
            )
        )

        preview = form_state.get("image_bytes")
        preview_area = (
            ft.Image(
                src=preview,
                width=240,
                height=200,
                fit=ft.BoxFit.CONTAIN,
                semantics_label="Selected monthly solar energy report",
            )
            if preview
            else ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Icon(ft.Icons.IMAGE, size=34, color=success_color()),
                        ft.Text("Upload a monitoring screenshot or monthly report", color=muted_color(), text_align=ft.TextAlign.CENTER),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                ),
                alignment=ft.Alignment.CENTER,
                height=118,
                border=ft.Border.all(1, border_color()),
                border_radius=12,
                bgcolor=surface_tint(),
            )
        )
        report_card = _styled_card(
            ft.Column(
                controls=[
                    ft.Text("Monthly report", size=18, weight=ft.FontWeight.BOLD, color=success_color()),
                        ft.Text(
                            "Choose the month shown on your report. Review the OCR-detected period when available.",
                            size=13,
                            color=muted_color(),
                        ),
                        ft.Text(
                            "Automatic OCR is unavailable on this platform."
                            if not ocr_supported else
                            "Upload a clear monthly report. Points are awarded automatically after the reading is saved to Supabase.",
                            size=12,
                            color=muted_color(),
                        ),
                        preview_area,
                        ft.Text(form_state.get("image_name", ""), size=12, color=muted_color()),
                        ft.Button(
                            content=(
                                "Already redeemed for this month"
                                if period_redeemed
                                else "Upload solar report"
                                if ocr_supported
                                else "Upload solar report"
                            ),
                            icon=ft.Icons.UPLOAD_FILE,
                            bgcolor=brand_color(),
                            color=brand_button_text_color(),
                            disabled=period_redeemed,
                            on_click=on_upload,
                        ),
                        _reading_summary(form_state),
                        _form_message(form_state),
                    ],
                spacing=12,
            ),
            padding=18,
            border=ft.Border.all(1, border_color()),
            border_radius=18,
        )
        controls.append(period_status if period_redeemed else report_card)

    controls.extend([section_heading("Solar claim history")])
    ordered_history = sorted(
        history or [],
        key=lambda claim: (int(claim.get("claim_year", 0)), int(claim.get("claim_month", 0))),
        reverse=True,
    )
    if not ordered_history:
        controls.append(
            panel(
                ft.Column(
                    controls=[
                        ft.Icon(ft.Icons.SOLAR_POWER, size=30, color=success_color()),
                        ft.Text("No solar claims yet", size=16, weight=ft.FontWeight.BOLD, color=ink_color()),
                        ft.Text("Your submitted monthly reports will appear here.", color=muted_color()),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=6,
                ),
                bgcolor=surface_tint(),
            )
        )
    else:
        for claim in ordered_history:
            month = int(claim.get("claim_month", 1))
            year = int(claim.get("claim_year", 0))
            period = f"{calendar.month_name[month]} {year}" if 1 <= month <= 12 else "Solar claim"
            kwh = float(claim.get("solar_generation_kwh", claim.get("kwh", 0)))
            points = int(claim.get("points_awarded", claim.get("points", 0)))
            submitted = str(claim.get("submitted_at", claim.get("date", ""))).replace("T", " ")[:16]
            raw_status = str(claim.get("claim_status", claim.get("status", "Submitted")))
            display_status = {
                "awarded": "Awarded",
                "flagged_review": "Flagged for review",
            }.get(raw_status, raw_status.replace("_", " ").title())
            controls.append(
                panel(
                    ft.Column(
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Text(period, size=16, weight=ft.FontWeight.BOLD, color=ink_color()),
                                    _claim_status_chip(display_status, raw_status),
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                wrap=True,
                            ),
                            ft.Text(f"{kwh:g} kWh  ·  {points:,} points", color=success_color()),
                            ft.Text(f"Submitted {submitted}" if submitted else "Submission date unavailable", size=12, color=muted_color()),
                        ],
                        spacing=7,
                    ),
                    padding=14,
                )
            )

    return ft.Column(
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        spacing=14,
        controls=controls,
    )


def _claim_status_chip(label, raw_status):
    color = success_color() if raw_status == "awarded" else (
        warning_color() if raw_status == "flagged_review" else muted_color()
    )
    return ft.Container(
        content=ft.Text(label, size=11, weight=ft.FontWeight.BOLD, color=color),
        bgcolor=ft.Colors.with_opacity(0.10, color),
        padding=ft.Padding.symmetric(horizontal=10, vertical=5),
        border_radius=20,
    )


def _reading_summary(form_state):
    kwh = form_state.get("kwh")
    if not kwh:
        return ft.Text(
            "Upload a solar report to read its monthly generation.",
            size=13,
            color=muted_color(),
        )
    detected = form_state.get("detected_period") or "Selected claim period"
    return _styled_card(
        ft.Column(
            controls=[
                ft.Text("Extracted solar generation", size=14, color=muted_color()),
                ft.Text(f"{float(kwh):g} kWh", size=25, weight=ft.FontWeight.BOLD, color=success_color()),
                ft.Text(f"Report period: {detected}", size=12, color=muted_color()),
            ],
            spacing=5,
        ),
        bgcolor=surface_tint(),
        border=ft.Border.all(1, border_color()),
        border_radius=14,
    )


def _form_message(form_state):
    if form_state.get("message_kind") != "error":
        return ft.Container()
    message = form_state.get("message", "")
    if not message:
        return ft.Container()
    return ft.Container(
        content=ft.Text(message, color=error_color()),
        padding=12,
        bgcolor=error_surface_color(),
        border_radius=10,
    )
