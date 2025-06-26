"""Utility components for common UI patterns.

Provides small, reusable utility components:
- Loading states and spinners
- Empty states and placeholders
- Conditional content wrappers
- Status indicators and badges
"""

import reflex as rx


def loading_spinner(size="md", color="blue") -> rx.Component:
    """Animated loading spinner."""
    size_map = {
        "sm": "1rem",
        "md": "1.5rem", 
        "lg": "2rem",
        "xl": "3rem"
    }
    
    return rx.box(
        rx.box(
            width=size_map.get(size, "1.5rem"),
            height=size_map.get(size, "1.5rem"),
            border=f"2px solid {rx.color('gray', 6)}",
            border_top=f"2px solid {rx.color(color, 9)}",
            border_radius="50%",
            animation="spin 1s linear infinite",
        ),
        display="flex",
        justify_content="center",
        align_items="center",
        **{
            "@keyframes spin": {
                "0%": {"transform": "rotate(0deg)"},
                "100%": {"transform": "rotate(360deg)"}
            }
        }
    )


def loading_state(message="Loading...", size="md") -> rx.Component:
    """Loading state with spinner and message."""
    return rx.vstack(
        loading_spinner(size=size),
        rx.text(
            message,
            color=rx.color("gray", 11),
            font_size="0.9rem",
            margin_top="0.5rem",
        ),
        align_items="center",
        spacing="0.5rem",
    )


def empty_state(
    title="No data found",
    description="There's nothing here yet.",
    icon="📭",
    action_button=None
) -> rx.Component:
    """Empty state component with optional action button."""
    return rx.vstack(
        rx.text(
            icon,
            font_size="3rem",
            margin_bottom="1rem",
        ),
        rx.text(
            title,
            font_size="1.25rem",
            font_weight="600",
            color=rx.color("gray", 12),
            margin_bottom="0.5rem",
        ),
        rx.text(
            description,
            color=rx.color("gray", 11),
            text_align="center",
            margin_bottom="1.5rem" if action_button else "0",
        ),
        action_button if action_button else rx.fragment(),
        align_items="center",
        text_align="center",
        padding="3rem 2rem",
    )


def status_badge(
    status,
    variant="default",
    size="sm"
) -> rx.Component:
    """Status badge with different variants."""
    color_map = {
        "default": "gray",
        "success": "green", 
        "warning": "orange",
        "error": "red",
        "info": "blue",
    }
    
    size_map = {
        "sm": {"padding": "0.25rem 0.5rem", "font_size": "0.75rem"},
        "md": {"padding": "0.375rem 0.75rem", "font_size": "0.875rem"},
        "lg": {"padding": "0.5rem 1rem", "font_size": "1rem"},
    }
    
    color = color_map.get(variant, "gray")
    sizing = size_map.get(size, size_map["sm"])
    
    return rx.box(
        status,
        background=rx.color(color, 3),
        color=rx.color(color, 11),
        border=f"1px solid {rx.color(color, 6)}",
        border_radius="0.375rem",
        font_weight="500",
        display="inline-block",
        **sizing
    )


def role_badge(role) -> rx.Component:
    """Role-specific badge with appropriate colors."""
    role_colors = {
        "super_admin": "red",
        "admin": "orange", 
        "user": "blue",
    }
    
    color = role_colors.get(role.lower(), "gray")
    display_name = role.replace("_", " ").title()
    
    return status_badge(display_name, variant=color, size="sm")


def conditional_wrapper(condition, wrapper_func, content) -> rx.Component:
    """Conditionally wrap content with a wrapper function."""
    return rx.cond(
        condition,
        wrapper_func(content),
        content
    )


def tooltip_wrapper(content, tooltip_text, position="top") -> rx.Component:
    """Wrapper that adds tooltip functionality."""
    return rx.box(
        content,
        title=tooltip_text,
        position="relative",
        # Add hover styles for better UX
        **{
            "&:hover": {
                "cursor": "help"
            }
        }
    )


def divider(orientation="horizontal", margin="1rem") -> rx.Component:
    """Divider line for separating content."""
    if orientation == "horizontal":
        return rx.box(
            height="1px",
            background=rx.color("gray", 6),
            margin=f"{margin} 0",
            width="100%",
        )
    else:  # vertical
        return rx.box(
            width="1px",
            background=rx.color("gray", 6),
            margin=f"0 {margin}",
            height="100%",
        )


def skeleton_loader(width="100%", height="1rem", border_radius="0.25rem") -> rx.Component:
    """Skeleton loader for content placeholders."""
    return rx.box(
        width=width,
        height=height,
        background=rx.color("gray", 4),
        border_radius=border_radius,
        animation="pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        **{
            "@keyframes pulse": {
                "0%, 100%": {"opacity": "1"},
                "50%": {"opacity": "0.5"}
            }
        }
    )


def skeleton_card() -> rx.Component:
    """Skeleton placeholder for card content."""
    return rx.vstack(
        skeleton_loader(height="1.5rem", width="70%"),
        skeleton_loader(height="1rem", width="100%"),
        skeleton_loader(height="1rem", width="90%"),
        skeleton_loader(height="1rem", width="60%"),
        spacing="0.75rem",
        padding="1.5rem",
        border_radius="0.75rem",
        background=rx.color("gray", 2),
        border=f"1px solid {rx.color('gray', 6)}",
    )


def progress_bar(value, max_value=100, color="blue", height="0.5rem") -> rx.Component:
    """Progress bar component."""
    percentage = (value / max_value) * 100 if max_value > 0 else 0
    
    return rx.box(
        rx.box(
            width=f"{percentage}%",
            height="100%",
            background=rx.color(color, 9),
            border_radius="inherit",
            transition="width 0.3s ease",
        ),
        width="100%",
        height=height,
        background=rx.color("gray", 4),
        border_radius="0.25rem",
        overflow="hidden",
    )


def access_denied_component(message: str = "You don't have permission to access this page.") -> rx.Component:
    """Access denied component - keeps exact styling from admin.py and user_management.py."""
    return rx.center(
        rx.vstack(
            rx.text(
                "Access Denied",
                size="6",
                weight="bold",
                color=rx.color("red", 11),
            ),
            rx.text(
                message,
                color=rx.color("gray", 11),
                text_align="center",
            ),
            rx.link(
                "Return to Dashboard",
                href="/",
                color=rx.color("blue", 11),
                weight="medium",
            ),
            spacing="4",
            align="center",
        ),
        min_height="100vh",
        padding="2rem",
    )


def authentication_required_component() -> rx.Component:
    """Authentication required component - keeps exact styling from admin.py and user_management.py."""
    return rx.center(
        rx.vstack(
            rx.text(
                "Authentication Required",
                size="6",
                weight="bold",
                color=rx.color("red", 11),
            ),
            rx.text(
                "Please sign in to access this page.",
                color=rx.color("gray", 11),
                text_align="center",
            ),
            rx.link(
                "Sign In",
                href="/login",
                color=rx.color("blue", 11),
                weight="medium",
            ),
            spacing="4",
            align="center",
        ),
        min_height="100vh",
        padding="2rem",
    )


def avatar(
    name="",
    src=None,
    size="md",
    fallback_color="blue"
) -> rx.Component:
    """Avatar component with fallback to initials."""
    size_map = {
        "sm": "2rem",
        "md": "2.5rem", 
        "lg": "3rem",
        "xl": "4rem"
    }
    
    avatar_size = size_map.get(size, "2.5rem")
    initials = "".join([n[0].upper() for n in name.split()[:2]]) if name else "?"
    
    if src:
        return rx.image(
            src=src,
            alt=name,
            width=avatar_size,
            height=avatar_size,
            border_radius="50%",
            object_fit="cover",
        )
    else:
        return rx.box(
            initials,
            width=avatar_size,
            height=avatar_size,
            border_radius="50%",
            background=rx.color(fallback_color, 9),
            color="white",
            display="flex",
            align_items="center",
            justify_content="center",
            font_weight="600",
            font_size="0.875rem",
        ) 