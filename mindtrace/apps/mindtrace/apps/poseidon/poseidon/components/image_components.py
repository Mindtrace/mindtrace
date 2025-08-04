"""
Image-related components for the Poseidon UI.
"""

import reflex as rx
from poseidon.state.images import ImageState, ImageDict

# Define common style constants directly within the component file
COLORS = {
    "primary": "#6366F1",  # Indigo 500
    "secondary": "#8B5CF6", # Violet 500
    "accent": "#EC4899",    # Pink 500
    "text": "#1F2937",      # Gray 900
    "text_muted": "#6B7280", # Gray 500
    "background": "#F9FAFB", # Gray 50
    "white": "#FFFFFF",
    "border": "#E5E7EB",    # Gray 200
    "success": "#10B981",   # Green 500
    "error": "#EF4444",     # Red 500
    "warning": "#F59E0B",   # Amber 500
    "info": "#3B82F6",      # Blue 500
}

TYPOGRAPHY = {
    "font_sizes": {
        "xs": "0.75rem",
        "sm": "0.875rem",
        "base": "1rem",
        "lg": "1.125rem",
        "xl": "1.25rem",
        "2xl": "1.5rem",
        "3xl": "1.875rem",
        "4xl": "2.25rem",
    },
    "font_weights": {
        "light": "300",
        "normal": "400",
        "medium": "500",
        "semibold": "600",
        "bold": "700",
        "extrabold": "800",
    },
}

SIZING = {
    "border_radius": "0.5rem",
    "max_width": "1200px",
}

SPACING = {
    "xs": "0.25rem",
    "sm": "0.5rem",
    "md": "1rem",
    "lg": "1.5rem",
    "xl": "2rem",
    "2xl": "3rem",
    "3xl": "4rem",
}

# Component variants (simplified for common use)
card_variants = {
    "base": {
        "background": COLORS["white"],
        "border_radius": SIZING["border_radius"],
        "box_shadow": "0 1px 3px rgba(0, 0, 0, 0.1), 0 1px 2px rgba(0, 0, 0, 0.06)",
        "padding": SPACING["md"],
    },
    "feature": {
        "background": COLORS["white"],
        "border_radius": SIZING["border_radius"],
        "box_shadow": "0 4px 6px rgba(0, 0, 0, 0.1), 0 1px 3px rgba(0, 0, 0, 0.08)",
        "padding": SPACING["md"],
        "transition": "all 0.2s ease-in-out",
    },
}

button_variants = {
    "primary": {
        "background": COLORS["primary"],
        "color": COLORS["white"],
        "border_radius": SIZING["border_radius"],
        "_hover": {"background": "#4F46E5"}, # Indigo 600
    },
    "secondary": {
        "background": COLORS["secondary"],
        "color": COLORS["white"],
        "border_radius": SIZING["border_radius"],
        "_hover": {"background": "#7C3AED"}, # Violet 600
    },
    "ghost": {
        "background": "transparent",
        "color": COLORS["text_muted"],
        "_hover": {"background": COLORS["background"]},
    },
}

content_variants = {
    "page_title": {
        "font_size": TYPOGRAPHY["font_sizes"]["3xl"],
        "font_weight": TYPOGRAPHY["font_weights"]["bold"],
        "color": COLORS["text"],
        "margin_bottom": SPACING["xs"],
    },
    "page_subtitle": {
        "font_size": TYPOGRAPHY["font_sizes"]["lg"],
        "color": COLORS["text_muted"],
        "margin_bottom": SPACING["lg"],
    },
    "page_header": {
        "padding_bottom": SPACING["md"],
        "border_bottom": f"1px solid {COLORS['border']}",
        "margin_bottom": SPACING["lg"],
    },
    "container": {
        "max_width": SIZING["max_width"],
        "width": "100%",
        "padding": SPACING["lg"],
        "margin_x": "auto",
        "min_height": "calc(100vh - 60px)", # Account for header height
    },
}

def image_card(image: rx.Var[ImageDict]) -> rx.Component:
    """Create an image card component"""
    
    # Custom styles that don't conflict with card_variants
    custom_styles = {
        "width": "100%",
        "max_width": "280px",
        "_hover": {
            "transform": "translateY(-2px)",
            "box_shadow": "0 8px 25px rgba(0, 0, 0, 0.15)",
        }
    }
    
    return rx.box(
        rx.vstack(
            rx.box(
                rx.image(
                    src=image.gcp_path,
                    alt=image.filename,
                    width="100%",
                    height="200px",
                    object_fit="cover",
                    border_radius=f"{SIZING['border_radius']} {SIZING['border_radius']} 0 0",
                ),
                width="100%",
                height="200px",
                overflow="hidden",
            ),
            rx.box(
                rx.vstack(
                    rx.text(
                        image.filename,
                        font_weight=TYPOGRAPHY["font_weights"]["semibold"],
                        font_size=TYPOGRAPHY["font_sizes"]["sm"],
                        color=COLORS["text"],
                        white_space="nowrap",
                        overflow="hidden",
                        text_overflow="ellipsis",
                        width="100%",
                    ),
                    rx.text(
                        rx.cond(
                            image.created_at,
                            image.created_at[:10],
                            "No date"
                        ),
                        font_size=TYPOGRAPHY["font_sizes"]["xs"],
                        color=COLORS["text_muted"],
                    ),
                    spacing="1",
                    align="start",
                    width="100%",
                ),
                padding=SPACING["sm"],
                width="100%",
            ),
            spacing="0",
            align="stretch",
            width="100%",
        ),
        **{**card_variants["feature"], **custom_styles},
        on_click=lambda: ImageState.open_image_modal(image),
    )

def pagination_controls() -> rx.Component:
    """Create pagination controls"""
    return rx.hstack(
        rx.button(
            "← Previous",
            on_click=ImageState.prev_page,
            disabled=ImageState.current_page <= 1,
            **button_variants["secondary"],
        ),
        rx.hstack(
            rx.text(
                f"Page {ImageState.current_page} of {ImageState.total_pages}",
                color=COLORS["text"],
                font_size=TYPOGRAPHY["font_sizes"]["sm"],
            ),
            rx.text(
                f"({ImageState.total_count} total images)",
                color=COLORS["text_muted"],
                font_size=TYPOGRAPHY["font_sizes"]["xs"],
            ),
            spacing="2",
        ),
        rx.button(
            "Next →",
            on_click=ImageState.next_page,
            disabled=ImageState.current_page >= ImageState.total_pages,
            **button_variants["secondary"],
        ),
        justify="between",
        align="center",
        width="100%",
        margin_top=SPACING["lg"],
    )

def image_modal() -> rx.Component:
    """Image detail modal"""
    return rx.cond(
        ImageState.show_modal & (ImageState.selected_image != None),
        rx.box(
            rx.box(
                rx.hstack(
                    rx.heading(
                        "Image Details",
                        font_size=TYPOGRAPHY["font_sizes"]["xl"],
                        color=COLORS["text"],
                    ),
                    rx.button(
                        "✕",
                        on_click=ImageState.close_modal,
                        **button_variants["ghost"],
                        font_size=TYPOGRAPHY["font_sizes"]["lg"],
                    ),
                    justify="between",
                    align="center",
                    width="100%",
                    margin_bottom=SPACING["lg"],
                ),
                rx.hstack(
                    rx.box(
                        rx.image(
                            src=ImageState.selected_image.gcp_path,
                            alt=ImageState.selected_image.filename,
                            max_width="600px",
                            max_height="500px",
                            object_fit="contain",
                            border_radius=SIZING["border_radius"],
                        ),
                        flex="2",
                        display="flex",
                        justify_content="center",
                        align_items="center",
                    ),
                    rx.box(
                        rx.vstack(
                            rx.vstack(
                                rx.text(
                                    "Filename",
                                    font_weight=TYPOGRAPHY["font_weights"]["semibold"],
                                    color=COLORS["text"],
                                    font_size=TYPOGRAPHY["font_sizes"]["sm"],
                                ),
                                rx.text(
                                    ImageState.selected_image.filename,
                                    color=COLORS["text_muted"],
                                    font_size=TYPOGRAPHY["font_sizes"]["sm"],
                                ),
                                spacing="1",
                                align="start",
                            ),
                            rx.vstack(
                                rx.text(
                                    "Upload Date",
                                    font_weight=TYPOGRAPHY["font_weights"]["semibold"],
                                    color=COLORS["text"],
                                    font_size=TYPOGRAPHY["font_sizes"]["sm"],
                                ),
                                rx.text(
                                    rx.cond(
                                        ImageState.selected_image.created_at,
                                        ImageState.selected_image.created_at[:10],
                                        "Unknown"
                                    ),
                                    color=COLORS["text_muted"],
                                    font_size=TYPOGRAPHY["font_sizes"]["sm"],
                                ),
                                spacing="1",
                                align="start",
                            ),
                            rx.vstack(
                                rx.text(
                                    "File Size",
                                    font_weight=TYPOGRAPHY["font_weights"]["semibold"],
                                    color=COLORS["text"],
                                    font_size=TYPOGRAPHY["font_sizes"]["sm"],
                                ),
                                rx.text(
                                    rx.cond(
                                        ImageState.selected_image.file_size,
                                        rx.text(ImageState.selected_image.file_size, " bytes"),
                                        "Unknown"
                                    ),
                                    color=COLORS["text_muted"],
                                    font_size=TYPOGRAPHY["font_sizes"]["sm"],
                                ),
                                spacing="1",
                                align="start",
                            ),
                            rx.vstack(
                                rx.text(
                                    "Dimensions",
                                    font_weight=TYPOGRAPHY["font_weights"]["semibold"],
                                    color=COLORS["text"],
                                    font_size=TYPOGRAPHY["font_sizes"]["sm"],
                                ),
                                rx.text(
                                    rx.cond(
                                        ImageState.selected_image.width & ImageState.selected_image.height,
                                        rx.text(ImageState.selected_image.width, " × ", ImageState.selected_image.height),
                                        "Unknown"
                                    ),
                                    color=COLORS["text_muted"],
                                    font_size=TYPOGRAPHY["font_sizes"]["sm"],
                                ),
                                spacing="1",
                                align="start",
                            ),
                            rx.vstack(
                                rx.text(
                                    "GCP Path",
                                    font_weight=TYPOGRAPHY["font_weights"]["semibold"],
                                    color=COLORS["text"],
                                    font_size=TYPOGRAPHY["font_sizes"]["sm"],
                                ),
                                rx.text(
                                    ImageState.selected_image.gcp_path,
                                    color=COLORS["text_muted"],
                                    font_size=TYPOGRAPHY["font_sizes"]["xs"],
                                    word_break="break-all",
                                ),
                                spacing="1",
                                align="start",
                            ),
                            spacing="4",
                            align="start",
                            width="100%",
                        ),
                        flex="1",
                        padding_left=SPACING["lg"],
                        max_width="300px",
                    ),
                    spacing="4",
                    align="start",
                    width="100%",
                ),
                background=COLORS["white"],
                border_radius=SIZING["border_radius"],
                padding=SPACING["lg"],
                max_width="900px",
                max_height="90vh",
                overflow="auto",
                box_shadow="0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)",
            ),
            position="fixed",
            top="0",
            left="0",
            width="100vw",
            height="100vh",
            background="rgba(0, 0, 0, 0.5)",
            display="flex",
            justify_content="center",
            align_items="center",
            z_index="1000",
            on_click=ImageState.close_modal,
        ),
    )

def search_bar() -> rx.Component:
    """Search bar component"""
    return rx.hstack(
        rx.input(
            placeholder="Search images by filename or tags...",
            value=ImageState.search_query,
            on_change=ImageState.set_search_query,
            width="300px",
        ),
        rx.button(
            "Search",
            on_click=lambda: ImageState.search_images(ImageState.search_query),
            **button_variants["primary"],
        ),
        rx.button(
            "Clear",
            on_click=lambda: ImageState.search_images(""),
            **button_variants["ghost"],
        ),
        spacing="2",
        align="center",
    )