import calendar
import math
from datetime import date, datetime, timedelta

import flet as ft
import flet_charts as charts

from components import (
    brand_color,
    color,
    ink_color,
    mint_color,
    muted_color,
    panel,
    success_color,
    surface_tint,
    title,
    warning_color,
)
from rewards import RUNNING_DAILY_IMAGE_LIMIT, RUNNING_POINTS_PER_KM


def _period_data(submissions, period, today):
    daily = {}
    for run in submissions:
        try:
            run_day = date.fromisoformat(run.get("date", ""))
            distance = float(run.get("distance_km", 0))
            points = int(run.get("points", 0))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(distance) or distance < 0:
            continue
        totals = daily.setdefault(run_day, {"distance": 0.0, "points": 0})
        totals["distance"] += distance
        totals["points"] += points

    if period == "week":
        start = today - timedelta(days=today.weekday())
        days = [start + timedelta(days=index) for index in range(7)]
        labels = [day.strftime("%a") for day in days]
        values = [daily.get(day, {}).get("distance", 0.0) for day in days]
        matching_days = set(days)
        heading = "This week"
    elif period == "month":
        days_in_month = calendar.monthrange(today.year, today.month)[1]
        bucket_count = (days_in_month + 6) // 7
        labels = []
        values = [0.0] * bucket_count
        for bucket in range(bucket_count):
            start_day = bucket * 7 + 1
            end_day = min(start_day + 6, days_in_month)
            labels.append(f"{start_day}–{end_day}")
        matching_days = set()
        for run_day, totals in daily.items():
            if run_day.year == today.year and run_day.month == today.month:
                matching_days.add(run_day)
                values[(run_day.day - 1) // 7] += totals["distance"]
        heading = today.strftime("%B")
    else:
        labels = [calendar.month_abbr[index] for index in range(1, 13)]
        values = [0.0] * 12
        matching_days = set()
        for run_day, totals in daily.items():
            if run_day.year == today.year:
                matching_days.add(run_day)
                values[run_day.month - 1] += totals["distance"]
        heading = str(today.year)

    period_points = sum(
        daily.get(run_day, {}).get("points", 0) for run_day in matching_days
    )
    period_distance = sum(values)
    return labels, values, period_distance, period_points, heading


def _achievement_chart(labels, values):
    max_value = max(values, default=0.0)
    max_y = max(1, math.ceil(max_value * 1.2))
    # High-contrast, color-vision-deficiency-friendly RGB palette (Okabe–Ito inspired).
    chart_colors = [
        "#0072B2",  # blue
        "#D55E00",  # vermilion
        "#009E73",  # bluish green
        "#CC79A7",  # reddish purple
        "#56B4E9",  # sky blue
        "#E69F00",  # orange
        "#332288",  # indigo
    ]
    groups = [
        charts.BarChartGroup(
            x=index,
            rods=[
                charts.BarChartRod(
                    to_y=value,
                    width=20,
                    color=chart_colors[index % len(chart_colors)],
                    border_side=ft.BorderSide(width=1.5, color=color("text")),
                    border_radius=ft.BorderRadius.all(7),
                    tooltip=charts.BarChartRodTooltip(
                        text=f"{labels[index].upper()}  |  {value:.2f} KM"
                    ),
                )
            ],
        )
        for index, value in enumerate(values)
    ]
    return charts.BarChart(
        height=250,
        groups=groups,
        group_spacing=10,
        group_alignment=ft.MainAxisAlignment.SPACE_EVENLY,
        interactive=True,
        tooltip=charts.BarChartTooltip(
            bgcolor=color("surface"),
            border_side=ft.BorderSide(width=2, color=color("text")),
            border_radius=8,
            padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            fit_inside_horizontally=True,
            fit_inside_vertically=True,
        ),
        min_y=0,
        max_y=max_y,
        horizontal_grid_lines=charts.ChartGridLines(
            interval=max_y / 4,
            color=muted_color(),
            width=1,
        ),
        left_axis=charts.ChartAxis(
            title=ft.Text("km"),
            title_size=30,
            label_size=38,
        ),
        bottom_axis=charts.ChartAxis(
            labels=[
                charts.ChartAxisLabel(value=index, label=label)
                for index, label in enumerate(labels)
            ],
            label_size=38,
            show_min=False,
            show_max=False,
        ),
    )


def build(
    state,
    on_upload,
    ocr_status,
    can_submit,
    ocr_supported,
    chart_period,
    on_chart_period_change,
):
    today = date.today()
    today_key = today.isoformat()
    submissions = state.get("running_submissions", [])
    quota_day_key = str(state.get("running_upload_date") or today_key)
    today_runs = [item for item in submissions if item.get("date") == quota_day_key]
    local_upload_count = sum(
        item.get("upload_date", item.get("date")) == quota_day_key for item in submissions
    )
    today_count = int(state.get("running_uploads_today", local_upload_count))
    today_points = sum(int(item.get("points", 0)) for item in today_runs)
    total_run_points = sum(int(item.get("points", 0)) for item in submissions)
    labels, values, period_distance, period_points, heading = _period_data(
        submissions, chart_period, today
    )
    best_index = max(range(len(values)), key=values.__getitem__, default=0)
    best_bucket = labels[best_index] if labels else "—"
    best_distance = values[best_index] if values else 0.0
    best_unit = {"week": "day", "month": "week", "year": "month"}.get(chart_period, "period")
    best_summary = (
        f"Top {best_unit}: {best_bucket} · {best_distance:.2f} km"
        if period_distance > 0
        else "Your first run will light up this chart."
    )

    entry_controls = []
    if can_submit:
        entry_controls = [
            panel(
                ft.Column(
                    spacing=8,
                    controls=[
                        ft.Text("Submit a run screenshot", size=16, weight=ft.FontWeight.BOLD, color=ink_color()),
                        ft.Text("Upload a clear JPG or PNG at any time. Up to 2 photos are allowed per Malaysia calendar day; points are added after the run details are read.", size=13, color=muted_color()),
                        ft.Text(f"{max(0, RUNNING_DAILY_IMAGE_LIMIT - today_count)} photo upload(s) left today", size=12, color=muted_color()),
                        ft.Text(
                            state.get("running_quota_error", ""),
                            size=12,
                            color=warning_color(),
                        ) if not state.get("running_quota_ready", False) and state.get("running_quota_error") else ft.Container(),
                        ft.Button(
                            content="Add screenshot",
                            icon=ft.Icons.ADD_A_PHOTO,
                            on_click=on_upload,
                            disabled=(
                                not state.get("running_quota_ready", False)
                                or today_count >= RUNNING_DAILY_IMAGE_LIMIT
                                or bool(ocr_status)
                            ), 
                        ),
                        ft.Text(
                            ocr_status or "",
                            size=12,
                            color=warning_color() if ocr_status and "could not" in ocr_status.lower() else muted_color(),
                        ) if ocr_status else ft.Container(),
                    ],
                )
            )
        ]

    chart_period_dropdown = ft.Dropdown(
        width=145,
        value=chart_period,
        options=[
            ft.DropdownOption(key="week", text="Weekly"),
            ft.DropdownOption(key="month", text="Monthly"),
            ft.DropdownOption(key="year", text="Yearly"),
        ],
        on_select=on_chart_period_change,
    )

    return ft.Column(
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        spacing=16,
        controls=[
            title("Running rewards", "Track your weekly, monthly, and yearly achievements."),
            panel(
                ft.Column(
                    spacing=14,
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Icon(ft.Icons.DIRECTIONS_RUN, color=brand_color(), size=28),
                                ft.Column(
                                    spacing=3,
                                    tight=True,
                                    controls=[
                                        ft.Text("Today's run submissions", size=14, color=muted_color()),
                                        ft.Text(f"{today_count} / {RUNNING_DAILY_IMAGE_LIMIT}", size=23, weight=ft.FontWeight.BOLD, color=ink_color()),
                                    ],
                                ),
                            ],
                            spacing=14,
                        ),
                        ft.ProgressBar(
                            value=min(today_count / RUNNING_DAILY_IMAGE_LIMIT, 1),
                            color=brand_color(),
                            bgcolor=mint_color(),
                            bar_height=9,
                            border_radius=9,
                        ),
                        ft.Row(
                            controls=[
                                ft.Text(f"{today_points} points earned today", color=success_color(), weight=ft.FontWeight.BOLD),
                                ft.Text(f"{max(0, RUNNING_DAILY_IMAGE_LIMIT - today_count)} remaining today", size=12, color=muted_color()),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                    ],
                )
            ),
            panel(
                ft.Row(
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Icon(ft.Icons.EMOJI_EVENTS, color=ft.Colors.AMBER_700, size=24),
                        ft.Column(
                            expand=True,
                            spacing=3,
                            tight=True,
                            controls=[
                                ft.Text("How points work", size=15, weight=ft.FontWeight.BOLD, color=ink_color()),
                                ft.Text(
                                    "Earn 10 points for each full kilometre. Upload up to 2 run screenshots per day.",
                                    size=13,
                                    color=muted_color(),
                                ),
                            ],
                        ),
                    ],
                ),
                bgcolor=surface_tint(),
            ),
            *entry_controls,
            panel(
                ft.Column(
                    spacing=12,
                    controls=[
                        ft.ResponsiveRow(
                            spacing=8,
                            run_spacing=8,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                ft.Container(
                                    col={"xs": 12, "sm": 8},
                                    content=ft.Column(
                                        spacing=2,
                                        tight=True,
                                        controls=[
                                            ft.Text("Run achievement", size=16, weight=ft.FontWeight.BOLD, color=ink_color()),
                                            ft.Text(f"{heading} · {period_distance:.2f} km · {period_points} points", size=13, color=muted_color()),
                                        ],
                                    ),
                                ),
                                ft.Container(
                                    col={"xs": 12, "sm": 4},
                                    content=chart_period_dropdown,
                                ),
                            ],
                        ),
                        _achievement_chart(labels, values),
                        ft.Row(
                            spacing=8,
                            controls=[
                                ft.Icon(ft.Icons.EMOJI_EVENTS, color=ft.Colors.AMBER_700, size=18),
                                ft.Text(best_summary, size=12, color=muted_color()),
                            ],
                        ),
                    ],
                )
            ),
            panel(
                ft.Row(
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Icon(ft.Icons.EMOJI_EVENTS, color=ft.Colors.AMBER_700, size=28),
                        ft.Column(
                            spacing=3,
                            tight=True,
                            controls=[
                                ft.Text("Points gathered", size=14, color=muted_color()),
                                ft.Text(f"{total_run_points:,}", size=24, weight=ft.FontWeight.BOLD, color=ink_color()),
                                ft.Text("Total points earned from running", size=12, color=muted_color()),
                            ],
                        ),
                    ],
                )
            ),
        ],
    )
