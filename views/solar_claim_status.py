"""Selected-month solar claim status presentation."""

import calendar

import flet as ft

from components import border_color, ink_color, muted_color, success_color, surface_tint, warning_color


def _claim_status(claim):
    return str(
        claim.get("claim_status") or claim.get("status") or ""
    ).strip().lower()


def find_period_claim(history, month, year):
    """Find the best available claim record for a selected month."""
    try:
        target_month, target_year = int(month), int(year)
    except (TypeError, ValueError):
        return None

    matches = []
    for claim in history or []:
        try:
            is_period = (
                int(claim.get("claim_month", 0)) == target_month
                and int(claim.get("claim_year", 0)) == target_year
            )
        except (TypeError, ValueError):
            continue
        if is_period:
            matches.append(claim)

    if not matches:
        return None
    return next(
        (claim for claim in matches if _claim_status(claim) == "awarded"),
        matches[0],
    )


def build_period_status(claim, month, year):
    """Build a prominent selected-month claim status and return redeemed state."""
    try:
        month_number = int(month)
        year_number = int(year)
        period = f"{calendar.month_name[month_number]} {year_number}"
    except (TypeError, ValueError, IndexError):
        period = "Selected month"

    status = _claim_status(claim) if claim else ""
    try:
        kwh = float((claim or {}).get("solar_generation_kwh", (claim or {}).get("kwh", 0)) or 0)
        kwh_text = f"{kwh:g} kWh" if kwh else ""
    except (TypeError, ValueError):
        kwh_text = ""
    try:
        points = int((claim or {}).get("points_awarded", (claim or {}).get("points", 0)) or 0)
    except (TypeError, ValueError):
        points = 0

    if status == "awarded":
        icon = ft.Icons.CHECK_CIRCLE
        color = success_color()
        heading = "SOLAR CLAIM REDEEMED"
        detail = f"{period} · {kwh_text} · {points:,} points credited"
        note = "This month's points have already been added to your household."
        redeemed = True
    elif status == "flagged_review":
        icon = ft.Icons.SCHEDULE
        color = warning_color()
        heading = "SOLAR CLAIM UNDER REVIEW"
        detail = f"{period} · {kwh_text} · no points credited yet"
        note = "The claim is recorded and waiting for verification."
        redeemed = False
    elif claim:
        icon = ft.Icons.SCHEDULE
        color = warning_color()
        label = status.replace("_", " ").title() or "Submitted"
        heading = f"SOLAR CLAIM: {label.upper()}"
        detail = f"{period} · {kwh_text}".strip(" ·")
        note = "Check claim history for the latest status."
        redeemed = False
    else:
        icon = ft.Icons.SOLAR_POWER
        color = muted_color()
        heading = "NO SOLAR CLAIM FOR THIS MONTH"
        detail = f"{period} has not been submitted yet."
        note = "Upload this month's report to start a claim."
        redeemed = False

    panel = ft.Container(
        content=ft.Column(
            controls=[
                ft.Icon(icon, color=color, size=46),
                ft.Text(
                    heading,
                    size=22 if redeemed else 18,
                    weight=ft.FontWeight.BOLD,
                    color=color,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(detail, size=16, weight=ft.FontWeight.BOLD, color=ink_color(), text_align=ft.TextAlign.CENTER),
                ft.Text(note, size=13, color=muted_color(), text_align=ft.TextAlign.CENTER),
            ],
            spacing=8,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=22 if redeemed else 16,
        bgcolor=ft.Colors.with_opacity(0.18 if redeemed else 0.10, color) if status else surface_tint(),
        border=ft.Border.all(2 if redeemed else 1, color if status else border_color()),
        border_radius=18,
    )
    return panel, redeemed
