"""Shared editorial theme tokens and reusable Townly components."""

import flet as ft


# Exact brand palette requested for the Light and Dark themes.
THEME_VARIABLES = {
    "light": {
        "--bg": "#FBF1E6",
        "--card": "#F5DABF",
        "--text": "#2B0C10",
        "--muted": "#7A4A4F",
        "--primary": "#6C151E",
        "--on-primary": "#F5DABF",
        "--secondary": "#FFEDAB",
        "--on-secondary": "#2B0C10",
        "--border": "#E3C3A3",
        "--input": "#FFF9F2",
        "--input-border": "#E3C3A3",
    },
    "dark": {
        "--bg": "#082523",
        "--card": "#0F3D3A",
        "--text": "#F5DABF",
        "--muted": "#B9A58C",
        "--primary": "#F5DABF",
        "--on-primary": "#6C151E",
        "--secondary": "#6C151E",
        "--on-secondary": "#F5DABF",
        "--border": "#2A5F5A",
        "--input": "#0B312F",
        "--input-border": "#2A5F5A",
    },
}


def _make_palette(mode):
    variables = THEME_VARIABLES[mode]
    dark = mode == "dark"
    return {
        "background": variables["--bg"],
        "secondary_background": "#E3C3A3" if not dark else "#2A5F5A",
        "surface": variables["--card"],
        "elevated_surface": variables["--input"],
        "primary": variables["--primary"],
        "secondary": variables["--secondary"],
        "mint": "#FFEDAB" if not dark else "#2A5F5A",
        "brand_button_text": variables["--on-primary"],
        "on_secondary": variables["--on-secondary"],
        "on_accent_text": variables["--on-secondary"],
        "text": variables["--text"],
        "secondary_text": variables["--muted"],
        "muted_text": variables["--muted"],
        "border": variables["--border"],
        "input": variables["--input"],
        "input_border": variables["--input-border"],
        "success_text": "#2B0C10" if not dark else "#F5DABF",
        "warning_text": "#6C151E" if not dark else "#F5DABF",
        "error": "#6C151E" if not dark else "#F5DABF",
        "error_surface": "#F5DABF" if not dark else "#2A5F5A",
        "hero_background": "#F5DABF" if not dark else "#0F3D3A",
        "hero_text": "#2B0C10" if not dark else "#F5DABF",
        "hero_muted": "#7A4A4F" if not dark else "#B9A58C",
        "reward_accent": "#6C151E" if not dark else "#F5DABF",
        "reward_surface": "#F5DABF" if not dark else "#0F3D3A",
        "reward_button_text": "#F5DABF" if not dark else "#6C151E",
        "lavender": "#6C151E",
        "cream": "#F5DABF",
        "peach": "#E3C3A3" if not dark else "#2A5F5A",
    }


LIGHT = _make_palette("light")
DARK = _make_palette("dark")
_DARK_MODE = False
_THEME_MODE = "system"

# Historical names kept for existing view imports.
GREEN = LIGHT["secondary"]
INK = LIGHT["text"]
MUTED = LIGHT["secondary_text"]
SURFACE = LIGHT["surface"]
CANVAS = LIGHT["background"]


def theme_variables(mode=None):
    """Return the CSS-variable-compatible token mapping for a theme."""
    selected = mode or ("dark" if _DARK_MODE else "light")
    if selected == "system":
        selected = "dark" if _DARK_MODE else "light"
    return dict(THEME_VARIABLES[selected])


def set_dark_mode(enabled):
    global _DARK_MODE
    _DARK_MODE = bool(enabled)


def current_theme_mode():
    return _THEME_MODE


def palette():
    return DARK if _DARK_MODE else LIGHT


def color(name):
    return palette().get(name, LIGHT.get(name, DARK.get(name)))


def brand_color():
    return color("primary")


def brand_button_text_color():
    return color("brand_button_text")


def canvas_color():
    return color("background")


def secondary_background_color():
    return color("secondary_background")


def surface_color():
    return color("surface")


def elevated_surface_color():
    return color("elevated_surface")


def surface_tint():
    return color("secondary_background")


def mint_color():
    return color("mint")


def ink_color():
    return color("text")


def muted_color():
    return color("secondary_text")


def subdued_color():
    return color("muted_text")


def border_color():
    return color("border")


def success_color():
    return color("success_text")


def warning_color():
    return color("warning_text")


def error_color():
    return color("error")


def error_surface_color():
    return color("error_surface")


def reward_color():
    return color("reward_accent")


def reward_surface_color():
    return color("reward_surface")


def reward_button_text_color():
    return color("reward_button_text")


def hero_background_color():
    return color("hero_background")


def hero_text_color():
    return color("hero_text")


def hero_muted_color():
    return color("hero_muted")


def _material_theme(dark):
    colors = DARK if dark else LIGHT
    scheme = ft.ColorScheme(
        primary=colors["primary"],
        on_primary=colors["brand_button_text"],
        primary_container=colors["surface"],
        on_primary_container=colors["text"],
        secondary=colors["secondary"],
        on_secondary=colors["on_secondary"],
        secondary_container=colors["secondary_background"],
        on_secondary_container=colors["text"],
        tertiary=colors["mint"],
        on_tertiary=colors["brand_button_text"],
        error=colors["error"],
        on_error=colors["brand_button_text"],
        surface=colors["surface"],
        on_surface=colors["text"],
        on_surface_variant=colors["secondary_text"],
        outline=colors["border"],
        outline_variant=colors["border"],
        surface_container=colors["surface"],
        surface_container_high=colors["secondary_background"],
        surface_container_highest=colors["secondary_background"],
        surface_container_low=colors["surface"],
        surface_container_lowest=colors["background"],
    )
    heading = ft.TextStyle(
        font_family="Roboto Condensed",
        font_family_fallback=["Arial", "sans-serif"],
        weight=ft.FontWeight.BOLD,
        color=colors["text"],
    )
    body = ft.TextStyle(
        font_family="Roboto",
        font_family_fallback=["Arial", "sans-serif"],
        color=colors["text"],
    )
    return ft.Theme(
        color_scheme=scheme,
        canvas_color=colors["background"],
        scaffold_bgcolor=colors["background"],
        card_bgcolor=colors["surface"],
        divider_color=colors["border"],
        hint_color=colors["secondary_text"],
        text_theme=ft.TextTheme(
            headline_large=heading,
            headline_medium=heading,
            headline_small=heading,
            title_large=heading,
            title_medium=heading,
            title_small=heading,
            body_large=body,
            body_medium=body,
            body_small=body,
        ),
        button_theme=ft.ButtonTheme(
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=10),
                elevation=0,
                text_style=ft.TextStyle(weight=ft.FontWeight.W_600),
            )
        ),
        outlined_button_theme=ft.OutlinedButtonTheme(
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=10),
                side=ft.BorderSide(width=1, color=colors["text"]),
                color=colors["text"],
                elevation=0,
            )
        ),
        text_button_theme=ft.TextButtonTheme(
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=10),
                color=colors["text"],
            )
        ),
        navigation_bar_theme=ft.NavigationBarTheme(
            bgcolor=colors["surface"],
            indicator_color=colors["secondary_background"],
            label_text_style=ft.TextStyle(color=colors["text"]),
        ),
    )


def apply_theme(page, mode="system", brightness=None):
    """Apply the shared Light, Dark, or System editorial palette."""
    global _THEME_MODE
    normalized = mode if mode in {"light", "dark", "system"} else "system"
    _THEME_MODE = normalized
    effective_dark = normalized == "dark" or (
        normalized == "system" and brightness == ft.Brightness.DARK
    )
    set_dark_mode(effective_dark)
    page.theme = _material_theme(False)
    page.dark_theme = _material_theme(True)
    page.theme_mode = {
        "light": ft.ThemeMode.LIGHT,
        "dark": ft.ThemeMode.DARK,
        "system": ft.ThemeMode.SYSTEM,
    }[normalized]
    page.bgcolor = canvas_color()
    if page.navigation_bar is not None:
        page.navigation_bar.bgcolor = surface_color()
        page.navigation_bar.indicator_color = surface_tint()
        page.navigation_bar.shadow_color = border_color()
    return normalized


def input_field(**kwargs):
    """Build a consistently themed, softly rounded form field."""
    kwargs.setdefault("filled", True)
    kwargs.setdefault("fill_color", color("input"))
    kwargs.setdefault("color", ink_color())
    kwargs.setdefault("hint_style", ft.TextStyle(color=muted_color()))
    kwargs.setdefault("label_style", ft.TextStyle(color=muted_color()))
    kwargs.setdefault("cursor_color", brand_color())
    kwargs.setdefault(
        "border",
        {
            ft.ControlState.DEFAULT: ft.OutlineInputBorder(
                border_radius=10,
                side=ft.BorderSide(width=1, color=color("input_border")),
            ),
            ft.ControlState.FOCUSED: ft.OutlineInputBorder(
                border_radius=10,
                side=ft.BorderSide(width=1.5, color=brand_color()),
            ),
        },
    )
    return ft.TextField(**kwargs)


def primary_button(content, **kwargs):
    kwargs.setdefault("bgcolor", brand_color())
    kwargs.setdefault("color", brand_button_text_color())
    kwargs.setdefault("style", ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10), elevation=0))
    return ft.Button(content=content, **kwargs)


def secondary_button(content, **kwargs):
    kwargs.setdefault("bgcolor", color("secondary"))
    kwargs.setdefault("color", color("on_secondary"))
    kwargs.setdefault("style", ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10), elevation=0))
    return ft.Button(content=content, **kwargs)


def ghost_button(content, **kwargs):
    kwargs.setdefault("color", ink_color())
    kwargs.setdefault(
        "style",
        ft.ButtonStyle(
            bgcolor=ft.Colors.TRANSPARENT,
            color=ink_color(),
            side=ft.BorderSide(width=1, color=ink_color()),
            shape=ft.RoundedRectangleBorder(radius=10),
            elevation=0,
        ),
    )
    return ft.OutlinedButton(content=content, **kwargs)


def panel(content, *, bgcolor=None, padding=18):
    return ft.Container(
        content=content,
        padding=padding,
        bgcolor=surface_color() if bgcolor is None else bgcolor,
        border=ft.Border.all(1, border_color()),
        border_radius=10,
    )


def title(text, subtitle=None):
    controls = [
        ft.Text(
            text,
            size=24,
            weight=ft.FontWeight.BOLD,
            font_family="Roboto Condensed",
            font_family_fallback=["Arial", "sans-serif"],
            color=ink_color(),
        )
    ]
    if subtitle:
        controls.append(ft.Text(subtitle, size=13, color=muted_color()))
    return ft.Column(controls=controls, spacing=4, tight=True)


def section_heading(text, trailing=None):
    controls = [
        ft.Text(
            text,
            size=17,
            weight=ft.FontWeight.BOLD,
            font_family="Roboto Condensed",
            font_family_fallback=["Arial", "sans-serif"],
            color=ink_color(),
        )
    ]
    if trailing is not None:
        controls.append(trailing)
    return ft.Row(controls=controls, alignment=ft.MainAxisAlignment.SPACE_BETWEEN)


def metric(label, value, icon, tint=None):
    icon_tint = surface_tint() if tint is None else tint
    icon_color = brand_color()
    if label == "Solar approved":
        icon_tint = ft.Colors.RED_900 if _DARK_MODE else "#FFEDAB"
        icon_color = ft.Colors.WHITE if _DARK_MODE else brand_color()
    return panel(
        ft.Row(
            controls=[
                ft.Container(
                    content=ft.Icon(icon, color=icon_color, size=21),
                    bgcolor=icon_tint,
                    padding=10,
                    border_radius=10,
                ),
                ft.Column(
                    controls=[
                        ft.Text(value, size=19, weight=ft.FontWeight.BOLD, color=ink_color()),
                        ft.Text(label, size=12, color=muted_color()),
                    ],
                    spacing=2,
                    tight=True,
                ),
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=14,
    )


def status_chip(status):
    status_color = {
        "Approved": success_color(),
        "Pending": warning_color(),
        "Rejected": error_color(),
    }.get(status, muted_color())
    return ft.Container(
        content=ft.Text(status, size=11, weight=ft.FontWeight.BOLD, color=status_color),
        bgcolor=ft.Colors.with_opacity(0.12, status_color),
        padding=ft.Padding.symmetric(horizontal=10, vertical=5),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.22, status_color)),
        border_radius=8,
    )
