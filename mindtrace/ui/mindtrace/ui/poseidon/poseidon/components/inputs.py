"""Poseidon Input Components - Buridan UI Styling.

Renamed Buridan UI pantry inputs for Poseidon use cases
while keeping the exact styling patterns.
"""

import reflex as rx


def text_input_with_label(
    label: str, 
    placeholder: str = "", 
    input_type: str = "text",
    name: str = "",
    required: bool = False,
    value: str = "",
    on_change=None
):
    """Text input with label - keeps Buridan UI styling."""
    return rx.box(
        rx.text(label, class_name="text-xs font-semibold"),
        rx.el.input(
            placeholder=placeholder,
            type=input_type,
            name=name,
            required=required,
            value=value,
            on_change=on_change,
            class_name=(
                "p-2 w-full "
                + "text-sm "
                + "rounded-md bg-transparent border border-gray-500/40 "
                + "focus:outline-none focus:border-blue-500 shadow-sm"
            ),
        ),
        class_name="w-full max-w-[20em] flex flex-col gap-y-2",
    )


def email_input(
    label: str = "Email",
    placeholder: str = "example@company.com",
    name: str = "email",
    required: bool = True,
    value: str = "",
    on_change=None
):
    """Email input - keeps Buridan UI styling."""
    return rx.box(
        rx.text(label, class_name="text-xs font-semibold"),
        rx.el.input(
            placeholder=placeholder,
            type="email",
            name=name,
            required=required,
            value=value,
            on_change=on_change,
            class_name=(
                "p-2 w-full "
                + "text-sm "
                + "rounded-md bg-transparent border border-gray-500/40 "
                + "focus:outline-none focus:border-blue-500 shadow-sm"
            ),
        ),
        class_name="w-full max-w-[20em] flex flex-col gap-y-2",
    )


def password_input(
    label: str = "Password",
    placeholder: str = "Enter password",
    name: str = "password",
    required: bool = True,
    value: str = "",
    on_change=None
):
    """Password input - keeps Buridan UI styling."""
    return rx.box(
        rx.text(label, class_name="text-xs font-semibold"),
        rx.el.input(
            placeholder=placeholder,
            type="password",
            name=name,
            required=required,
            value=value,
            on_change=on_change,
            class_name=(
                "p-2 w-full "
                + "text-sm "
                + "rounded-md bg-transparent border border-gray-500/40 "
                + "focus:outline-none focus:border-blue-500 shadow-sm"
            ),
        ),
        class_name="w-full max-w-[20em] flex flex-col gap-y-2",
    )


def search_input(
    label: str = "Search",
    placeholder: str = "Search...",
    name: str = "search",
    value: str = "",
    on_change=None
):
    """Search input - keeps Buridan UI styling."""
    return rx.box(
        rx.text(label, class_name="text-xs font-semibold"),
        rx.el.input(
            placeholder=placeholder,
            type="search",
            name=name,
            value=value,
            on_change=on_change,
            class_name=(
                "p-2 w-full "
                + "text-sm "
                + "rounded-md bg-transparent border border-gray-500/40 "
                + "focus:outline-none focus:border-blue-500 shadow-sm"
            ),
        ),
        class_name="w-full max-w-[20em] flex flex-col gap-y-2",
    )


def textarea_with_label(
    label: str,
    placeholder: str = "",
    name: str = "",
    rows: int = 4,
    required: bool = False,
    value: str = "",
    on_change=None
):
    """Textarea with label - keeps Buridan UI styling."""
    return rx.box(
        rx.text(label, class_name="text-xs font-semibold"),
        rx.el.textarea(
            placeholder=placeholder,
            name=name,
            rows=rows,
            required=required,
            value=value,
            on_change=on_change,
            class_name=(
                "p-2 w-full "
                + "text-sm "
                + "rounded-md bg-transparent border border-gray-500/40 "
                + "focus:outline-none focus:border-blue-500 shadow-sm "
                + "resize-y"
            ),
        ),
        class_name="w-full max-w-[20em] flex flex-col gap-y-2",
    )


# Filter Components
def role_filter_select(value: str = "", on_change=None, roles: list = None):
    """Role filter select - keeps Buridan UI styling."""
    if roles is None:
        roles = ["all_roles", "user", "admin", "super_admin"]
    
    return rx.select(
        roles,
        placeholder="Filter by role",
        value=value,
        on_change=on_change,
        size="2",
    )


def status_filter_select(value: str = "", on_change=None):
    """Status filter select - keeps Buridan UI styling."""
    return rx.select(
        ["active", "inactive", "all"],
        placeholder="Filter by status", 
        value=value,
        on_change=on_change,
        size="2",
    )


def filter_bar(search_value: str = "", search_on_change=None, 
               role_value: str = "", role_on_change=None,
               status_value: str = "", status_on_change=None):
    """Complete filter bar - keeps Buridan UI styling."""
    return rx.box(
        rx.hstack(
            search_input(
                label="",
                placeholder="Search users by name or email...",
                value=search_value,
                on_change=search_on_change,
            ),
            role_filter_select(
                value=role_value,
                on_change=role_on_change,
            ),
            status_filter_select(
                value=status_value,
                on_change=status_on_change,
            ),
            spacing="4",
            align="center",
            width="100%",
        ),
        padding="1rem",
        background=rx.color("gray", 2),
        border_radius="8px",
        border=f"1px solid {rx.color('gray', 6)}",
        margin_bottom="2rem",
    )


# Message/Alert Components
def success_message(message: str):
    """Success message box - keeps Buridan UI styling."""
    return rx.box(
        rx.text(
            message,
            color=rx.color("green", 11),
            weight="medium",
        ),
        padding="1rem",
        background=rx.color("green", 2),
        border=f"1px solid {rx.color('green', 6)}",
        border_radius="8px",
        margin_bottom="1rem",
    )


def error_message(message: str):
    """Error message box - keeps Buridan UI styling."""
    return rx.box(
        rx.text(
            message,
            color=rx.color("red", 11),
            weight="medium",
        ),
        padding="1rem",
        background=rx.color("red", 2),
        border=f"1px solid {rx.color('red', 6)}",
        border_radius="8px",
        margin_bottom="1rem",
    )


def warning_message(message: str):
    """Warning message box - keeps Buridan UI styling."""
    return rx.box(
        rx.text(
            message,
            color=rx.color("orange", 11),
            weight="medium",
        ),
        padding="1rem",
        background=rx.color("orange", 2),
        border=f"1px solid {rx.color('orange', 6)}",
        border_radius="8px",
        margin_bottom="1rem",
    )


def info_message(message: str):
    """Info message box - keeps Buridan UI styling."""
    return rx.box(
        rx.text(
            message,
            color=rx.color("blue", 11),
            weight="medium",
        ),
        padding="1rem",
        background=rx.color("blue", 2),
        border=f"1px solid {rx.color('blue', 6)}",
        border_radius="8px",
        margin_bottom="1rem",
    )


# Keep original demo input for reference
def input_v1():
    """Original Buridan UI demo input - for reference."""
    return rx.box(
        rx.text("Email", class_name="text-xs font-semibold"),
        rx.el.input(
            placeholder="something@email.com",
            class_name=(
                "p-2 w-full "
                + "text-sm "
                + "rounded-md bg-transparent border border-gray-500/40 "
                + "focus:outline-none focus:border-blue-500 shadow-sm"
            ),
        ),
        class_name="w-full max-w-[20em] flex flex-col gap-y-2",
    )
