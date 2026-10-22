from datetime import date
import math

import flet as ft

from components import (
    color,
    hero_background_color,
    hero_muted_color,
    hero_text_color,
    muted_color,
    panel,
    metric,
    section_heading,
    success_color,
    title,
    warning_color,
)


def _total_awarded_kwh(claims):
    total = 0.0
    for claim in claims or []:
        status = str(claim.get("claim_status") or claim.get("status") or "").lower()
        if status not in {"awarded", "approved"}:
            continue
        try:
            value = float(
                claim.get("solar_generation_kwh", claim.get("kwh", 0)) or 0
            )
        except (TypeError, ValueError):
            continue
        if math.isfinite(value):
            total += value
    return total


def _total_distance_km(submissions):
    total = 0.0
    for item in submissions or []:
        try:
            distance = float(item.get("distance_km", 0) or 0)
        except (TypeError, ValueError):
            continue
        if math.isfinite(distance) and distance > 0:
            total += distance
    return total


def build(state, on_navigate, profile_name=None):
    total_kwh = _total_awarded_kwh(state.get("solar_claims", []))
    total_distance_km = _total_distance_km(state.get("running_submissions", []))
    today = date.today().isoformat()
    walking_points_today = sum(
        int(item.get("points", 0))
        for item in state.get("running_submissions", [])
        if item.get("date") == today
    )
    return ft.Column(
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        spacing=16,
        controls=[
            title(f"Welcome, {profile_name or 'Greenfields'} 🐰", "Small steps add up to a greener home."),
            ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Text(state["family_name"], size=16, color=hero_text_color()),
                        ft.Text("Level 3 · Earth Champions", size=13, color=hero_muted_color()),
                        ft.Row(
                            controls=[
                                ft.Text(f"{state['points']:,}", size=38, weight=ft.FontWeight.BOLD, color=hero_text_color()),
                                ft.Text("POINTS", size=12, weight=ft.FontWeight.BOLD, color=hero_muted_color()),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.END,
                            spacing=8,
                        ),
                        ft.Text("Available points balance", size=12, color=hero_muted_color()),
                    ],
                    spacing=5,
                ),
                padding=22,
                bgcolor=hero_background_color(),
                border=ft.Border.all(1, color("border")),
                border_radius=22,
            ),
            ft.ResponsiveRow(
                spacing=10,
                run_spacing=10,
                controls=[
                    ft.Container(
                        col={"xs": 12, "sm": 6},
                        content=metric("Walking points today", f"{walking_points_today:,}", ft.Icons.DIRECTIONS_WALK, color("mint")),
                    ),
                    ft.Container(
                        col={"xs": 12, "sm": 6},
                        content=metric("Total kWh", f"{total_kwh:.1f} kWh", ft.Icons.SOLAR_POWER, color("secondary")), 
                    ),
                    ft.Container(
                        col={"xs": 12, "sm": 6},
                        content=metric("Rewards redeemed", str(len(state["redemptions"])), ft.Icons.CARD_GIFTCARD, color("secondary")),
                    ),
                    ft.Container(
                        col={"xs": 12, "sm": 6},
                        content=metric("Total distance", f"{total_distance_km:.2f} km", ft.Icons.DIRECTIONS_WALK, color("mint")),  
                    ),
                ],
            ),
            panel(
                ft.Column(
                    controls=[
                        section_heading("Points activity"),
                        ft.Row(
                            controls=[
                                ft.Text("Earned", color=muted_color()),
                                ft.Text(f"+{state['points_earned']:,} pts", color=success_color(), weight=ft.FontWeight.BOLD),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        ft.Row(
                            controls=[
                                ft.Text("Spent", color=muted_color()),
                                ft.Text(f"−{state['points_spent']:,} pts", color=warning_color(), weight=ft.FontWeight.BOLD),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                    ],
                    spacing=12,
                )
            ),
            section_heading("Quick actions"),
            ft.Row(
                wrap=True,
                spacing=8,
                controls=[
                    ft.Button(content="Log a walk", icon=ft.Icons.DIRECTIONS_WALK, on_click=lambda e: on_navigate(1)),
                    ft.Button(content="Solar claim", icon=ft.Icons.SOLAR_POWER, on_click=lambda e: on_navigate(2)),
                    ft.Button(content="Browse rewards", icon=ft.Icons.REDEEM, on_click=lambda e: on_navigate(3)), 
                ],
            ),
            ft.Text("Total distance is synced from Supabase walking activity.", size=12, color=muted_color()),
        ],
    )
