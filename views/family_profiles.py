"""Supabase household and invitation management."""

import flet as ft

from components import ink_color, input_field, muted_color, panel, title


def build(
    household=None,
    load_error="",
    invitation_error="",
    invitations=None,
    on_create_household=None,
    on_invite=None,
    on_respond_invitation=None,
    page=None,
    on_leave_family=None,
    on_remove_member=None,
):
    family_name_field = input_field(label="Family name", hint_text="e.g. The Green Family")
    invite_email_field = input_field(
        label="Invite an existing account by email",
        keyboard_type=ft.KeyboardType.EMAIL,
    )

    async def create_household_clicked(event):
        if on_create_household:
            await on_create_household(family_name_field.value)

    async def invite_clicked(event):
        if on_invite:
            await on_invite(invite_email_field.value)

    controls = [
        title(
            "Family",
            "Invite existing Townly accounts by email. No email is sent; pending invitations appear in the recipient's Family tab.",
        ),
        *([panel(ft.Text(invitation_error, color=muted_color()))] if invitation_error else []),
        ft.Text("Household members", size=17, weight=ft.FontWeight.BOLD, color=ink_color()),
    ]

    if household:
        members = list(household.get("members", []))
        members.sort(key=lambda member: 0 if member.get("role") == "owner" else 1)
        is_owner = household.get("member_role") == "owner"

        def confirm_family_action(action, member=None):
            if page is None:
                return
            person_name = (
                member.get("display_name") or member.get("full_name") or "this member"
                if member else "your family"
            )
            leaving = action == "leave"
            async def confirm_clicked(event):
                await confirm_and_apply(action, member)

            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Leave family?" if leaving else "Remove family member?"),
                content=ft.Text(
                    "Are you sure you want to leave this family?"
                    if leaving
                    else f"Are you sure you want to remove {person_name} from this family?"
                ),
                actions=[
                    ft.TextButton(content="Cancel", on_click=lambda event: page.pop_dialog()),
                    ft.Button(
                        content="Leave family" if leaving else "Remove member",
                        on_click=confirm_clicked,
                    ),
                ],
            )
            page.show_dialog(dialog)

        async def confirm_and_apply(action, member):
            page.pop_dialog()
            if action == "leave" and on_leave_family:
                await on_leave_family()
            elif action == "remove" and member and on_remove_member:
                await on_remove_member(member.get("id"))

        member_controls = []
        for member in members:
            tile = ft.ListTile(
                leading=ft.Icon(ft.Icons.PERSON_OUTLINE),
                title=member.get("display_name") or member.get("full_name") or "Household member",
                subtitle=(
                    "Owner · Supabase account"
                    if member.get("role") == "owner"
                    else "Member · Supabase account"
                ),
                trailing=(
                    ft.TextButton(
                        content="Remove",
                        icon=ft.Icons.GROUP_REMOVE,
                        on_click=lambda event, current_member=member: confirm_family_action(
                            "remove", current_member
                        ),
                    )
                    if is_owner and member.get("role") != "owner"
                    else None
                ),
            )
            member_controls.append(tile)
        if not members:
            member_controls.append(
                ft.Text("No account members are linked to this household.", color=muted_color())
            )
        controls.append(panel(ft.Column(spacing=8, controls=member_controls)))
        if not is_owner:
            controls.append(
                ft.Button(
                    content="Leave family",
                    icon=ft.Icons.GROUP_REMOVE,
                    on_click=lambda event: confirm_family_action("leave"),
                )
            )
    else:
        controls.append(
            panel(
                ft.Column(
                    spacing=10,
                    controls=[
                        ft.Text(
                            "Create your family (household)",
                            size=16,
                            weight=ft.FontWeight.BOLD,
                            color=ink_color(),
                        ),
                        ft.Text(
                            "Choose the family name that will appear in Supabase.",
                            color=muted_color(),
                        ),
                        family_name_field,
                        ft.Button(
                            content="Create family",
                            icon=ft.Icons.GROUP_ADD,
                            disabled=bool(load_error),
                            on_click=create_household_clicked,
                        ),
                        *(
                            [ft.Text(load_error, size=12, color=muted_color())]
                            if load_error
                            else []
                        ),
                    ],
                )
            )
        )

    if household and household.get("member_role") == "owner":
        controls.append(
            panel(
                ft.Column(
                    spacing=10,
                    controls=[
                        ft.Text("Invite a member", size=16, weight=ft.FontWeight.BOLD, color=ink_color()),
                        ft.Text(
                            "The email must match an existing account. If that account is already in a family, no invitation is created.",
                            size=12,
                            color=muted_color(),
                        ),
                        invite_email_field,
                        ft.Button(
                            content="Send invitation",
                            icon=ft.Icons.PERSON_ADD,
                            disabled=bool(invitation_error),
                            on_click=invite_clicked,
                        ),
                    ],
                )
            )
        )

    invitations = invitations or []
    received = [item for item in invitations if item.get("direction") == "received"]
    pending_received = [item for item in received if item.get("status") == "pending"]
    sent = [item for item in invitations if item.get("direction") == "sent"]

    if pending_received:
        controls.append(
            ft.Text("Invitations for you", size=17, weight=ft.FontWeight.BOLD, color=ink_color())
        )
        for invitation in pending_received:
            async def respond_clicked(event, item=invitation):
                if on_respond_invitation:
                    await on_respond_invitation(item.get("id"), True)

            async def reject_clicked(event, item=invitation):
                if on_respond_invitation:
                    await on_respond_invitation(item.get("id"), False)

            controls.append(
                panel(
                    ft.Column(
                        spacing=8,
                        controls=[
                            ft.Text(
                                f"{invitation.get('household_name', 'Family')} invited you",
                                weight=ft.FontWeight.BOLD,
                                color=ink_color(),
                            ),
                            ft.Text(
                                "Status: pending · Accept to join, or reject the invitation.",
                                size=12,
                                color=muted_color(),
                            ),
                            ft.Row(
                                wrap=True,
                                controls=[
                                    ft.Button(
                                        content="Accept",
                                        icon=ft.Icons.CHECK,
                                        on_click=respond_clicked,
                                    ),
                                    ft.TextButton(
                                        content="Reject",
                                        icon=ft.Icons.CLOSE,
                                        on_click=reject_clicked,
                                    ),
                                ],
                            ),
                        ],
                    )
                )
            )

    responded = [item for item in received if item.get("status") in {"approved", "rejected"}]
    if responded:
        controls.append(
            ft.Text("Invitation history", size=17, weight=ft.FontWeight.BOLD, color=ink_color())
        )
        for invitation in responded:
            controls.append(
                panel(
                    ft.Text(
                        f"{invitation.get('household_name', 'Family')} · {invitation.get('status', '').title()}",
                        color=muted_color(),
                    )
                )
            )

    if sent:
        controls.append(
            ft.Text("Sent invitations", size=17, weight=ft.FontWeight.BOLD, color=ink_color())
        )
        for invitation in sent:
            controls.append(
                panel(
                    ft.Text(
                        f"{invitation.get('invitee_email', '')} · {invitation.get('status', '').title()}",
                        color=muted_color(),
                    )
                )
            )

    return ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=14, controls=controls)
