"""Poseidon Card Components - Buridan UI Styling.

Renamed Buridan UI pantry cards for Poseidon use cases
while keeping the exact styling patterns.
"""

import reflex as rx


def admin_feature_card(title: str, description: str, icon: str):
    """Admin dashboard feature card - keeps Buridan UI styling."""
    return rx.box(
        rx.vstack(
            rx.text(icon, font_size="2rem"),
            rx.heading(title, size="4", weight="bold"),
            rx.text(description, size="2", color=rx.color("slate", 11)),
            spacing="3",
            align="center",
        ),
        class_name=(
            "w-full h-72 max-w-[35em] "
            + "p-4 "
            + "rounded-md border border-dashed border-gray-600 "
        ),
    )


def profile_info_card(title: str, content_items: list):
    """Profile page info card - modern, clean styling."""
    return rx.box(
        rx.vstack(
            # Card header
            rx.box(
                rx.heading(
                    title, 
                    size="4", 
                    weight="bold",
                    color=rx.color("slate", 12),
                ),
                padding_bottom="1rem",
                border_bottom=f"1px solid {rx.color('slate', 6)}",
                margin_bottom="1.5rem",
                width="100%",
            ),
            # Content items with better spacing and typography
            *[
                rx.box(
                rx.hstack(
                        rx.text(
                            item["label"], 
                            size="2", 
                            weight="medium",
                            color=rx.color("slate", 12),
                            min_width="160px",
                        ),
                        rx.text(
                            item["value"], 
                            size="2", 
                            color=rx.color("slate", 11),
                            word_break="break-all",
                        ),
                        spacing="3",
                    align="start",
                        width="100%",
                    ),
                    padding="0.75rem 0",
                    border_bottom=f"1px solid {rx.color('slate', 4)}"
                    if i < len(content_items) - 1 else "none",
                )
                for i, item in enumerate(content_items)
            ],
            spacing="0",
            align="start",
            width="100%",
        ),
        # Modern card styling
        width="100%",
        padding="2rem",
        border_radius="12px",
        background=rx.color("slate", 1),
        border=f"1px solid {rx.color('slate', 6)}",
        box_shadow="0 2px 12px rgba(0, 0, 0, 0.05)",
    )


def navigation_action_card(title: str, description: str, icon: str):
    """Home page navigation card - clean, modern styling without problematic background patterns."""
    return rx.box(
        rx.vstack(
            # Icon with proper styling
        rx.box(
                rx.text(icon, font_size="2.5rem"),
                display="flex",
                align_items="center",
                justify_content="center",
                width="4rem",
                height="4rem",
                border_radius="12px",
                background=rx.color("blue", 3),
                color=rx.color("blue", 11),
                margin_bottom="1rem",
        ),
            # Title
            rx.heading(
                title, 
                size="4", 
                weight="bold",
                color=rx.color("slate", 12),
                margin_bottom="0.5rem",
                text_align="center",
            ),
            # Description
            rx.text(
                description, 
                size="2", 
                color=rx.color("slate", 11),
                text_align="center",
                line_height="1.5",
            ),
            spacing="2",
            align="center",
            justify="center",
            height="100%",
        ),
        # Modern card styling
        width="100%",
        min_height="200px",
        max_width="320px",
        padding="2rem",
        border_radius="12px",
        background=rx.color("slate", 2),
        border=f"1px solid {rx.color('slate', 6)}",
        box_shadow="0 2px 8px rgba(0, 0, 0, 0.04)",
        cursor="pointer",
        transition="all 0.2s ease",
        # Hover effects
        _hover={
            "transform": "translateY(-2px)",
            "box_shadow": "0 4px 16px rgba(0, 0, 0, 0.08)",
            "border_color": rx.color("blue", 7),
        },
        # Focus effects for accessibility
        _focus={
            "outline": f"2px solid {rx.color('blue', 8)}",
            "outline_offset": "2px",
        }
    )


def user_management_card(username: str, email: str, status: str):
    """User management list card - keeps Buridan UI styling."""
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.text(username, weight="bold"),
                rx.text(status, size="1", color=rx.color("green", 9)),
                justify="between",
                width="100%",
            ),
            rx.text(email, size="2", color=rx.color("slate", 11)),
            spacing="2",
            align="start",
        ),
        class_name=(
            "w-full "
            + "p-4 "
            + "rounded-md border border-dashed border-gray-600 "
        ),
    )


# Keep original for reference
def dashboard_card(title: str, description: str, icon: str, href: str):
    """Create a card for dashboard functions (admin/super admin) - keeps exact styling from super_admin.py."""
    return rx.link(
        rx.card(
            rx.vstack(
                rx.icon(
                    tag=icon,
                    size=48,
                    color=rx.color("blue", 9),
                ),
                rx.heading(
                    title,
                    size="6",
                    weight="bold",
                    text_align="center",
                ),
                rx.text(
                    description,
                    size="3",
                    color=rx.color("gray", 11),
                    text_align="center",
                ),
                spacing="4",
                align="center",
            ),
            width="300px",
            height="200px",
            padding="6",
            _hover={
                "transform": "translateY(-2px)",
                "box_shadow": "0 10px 25px rgba(0, 0, 0, 0.1)",
                "cursor": "pointer",
            },
            transition="all 0.2s ease-in-out",
        ),
        href=href,
        text_decoration="none",
    )


def card_v1():
    """Original Buridan UI demo card - for reference."""
    return rx.box(
        rx.box(
            color=rx.color("gray", 4),
            class_name=(
                "w-full h-full "
                + "col-start-2 row-span-full row-start-1 bg-[size:10px_10px] bg-fixed bg-[image:repeating-linear-gradient(315deg,currentColor_0,currentColor_1px,_transparent_0,_transparent_50%)]"
            ),
        ),
        class_name=(
            "w-full h-72 max-w-[35em] "
            + "p-4 "
            + "rounded-md border border-dashed border-gray-600 "
        ),
    )
