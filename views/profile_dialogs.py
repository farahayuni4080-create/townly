"""Profile picker and profile-removal dialogs."""

import flet as ft


def picker(page, profiles, active_profile_id, on_pick):
    choices = []
    for profile in profiles:
        profile_id = profile["id"]

        async def choose_profile(event, selected_id=profile_id):
            await on_pick(selected_id)

        choices.append(
            ft.ListTile(
                leading=ft.CircleAvatar(
                    foreground_image_src=profile.get("avatar", "avatar_leaf.svg"),
                    radius=18,
                ),
                title=ft.Text(profile["name"]),
                subtitle=ft.Text("Owner" if profile.get("role") == "owner" else "Family member"),
                trailing=ft.Icon(
                    ft.Icons.CHECK if profile_id == active_profile_id else ft.Icons.CHEVRON_RIGHT
                ),
                on_click=choose_profile,
            )
        )
    return ft.AlertDialog(
        title=ft.Text("Who's using the app?"),
        content=ft.Column(height=320, scroll=ft.ScrollMode.AUTO, controls=choices),
        actions=[ft.TextButton(content="Close", on_click=lambda e: page.pop_dialog())],
    )


def removal(profile, on_confirm, on_cancel):
    async def confirm_clicked(event):
        await on_confirm()

    return ft.AlertDialog(
        modal=True,
        title=ft.Text(f"Remove {profile['name']}?"),
        content=ft.Text(
            "Their profile and its points and redemption history will be removed from this device."
        ),
        actions=[
            ft.TextButton(content="Cancel", on_click=on_cancel),
            ft.TextButton(content="Remove", on_click=confirm_clicked),
        ],
    )
