"""
Image gallery page for authenticated users.
"""
import reflex as rx
from poseidon.components.image_components import (
    image_card, pagination_controls, image_modal, search_bar, 
    COLORS, TYPOGRAPHY, SIZING, SPACING, content_variants,button_variants,card_variants
)
from poseidon.components_v2.core import button
from poseidon.components import (
    sidebar, app_header, authentication_required_component, page_container
)
from poseidon.state.auth import AuthState
from poseidon.state.images import ImageState, ImageDict


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
                    src=image.presigned_url,
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
        button(
            "← Previous",
            on_click=ImageState.prev_page,
            disabled=ImageState.current_page <= 1,
            variant="secondary",
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
        button(
            "Next →",
            on_click=ImageState.next_page,
            disabled=ImageState.current_page >= ImageState.total_pages,
            variant="secondary",
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
                    button(
                        "✕",
                        on_click=ImageState.close_modal,
                        variant="ghost",
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
                            src=ImageState.selected_image.presigned_url,
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
        button(
            "Search",
            on_click=lambda: ImageState.search_images(ImageState.search_query),
            variant="primary",
        ),
        button(
            "Clear",
            on_click=lambda: ImageState.search_images(""),
            variant="ghost",
        ),
        spacing="2",
        align="center",
    )

def image_gallery_content() -> rx.Component:
    """Image gallery content using unified Poseidon UI components."""
    return rx.box(
        # Main content using page_container
        page_container(
            # Page header
            rx.box(
                rx.heading("Image Viewer", **content_variants["page_title"]),
                rx.text("Browse and manage your image collection", **content_variants["page_subtitle"]),
                **content_variants["page_header"]
            ),
            
            # Search and filters
            search_bar(),
            
            # Image grid
            rx.cond(
                ImageState.is_loading,
                rx.box(
                    rx.spinner(size="3"),
                    rx.text("Loading images...", margin_left=SPACING["sm"], color=COLORS["text_muted"]),
                    display="flex",
                    align_items="center",
                    justify_content="center",
                    padding=SPACING["xl"],
                ),
                rx.cond(
                    ImageState.images.length() > 0,
                    rx.vstack(
                        rx.box(
                            rx.foreach(ImageState.images, image_card),
                            display="grid",
                            grid_template_columns="repeat(auto-fill, minmax(250px, 1fr))",
                            gap=SPACING["md"],
                            padding=SPACING["md"],
                            width="100%",
                        ),
                        pagination_controls(),
                        spacing="4",
                        width="100%",
                    ),
                    rx.box(
                        rx.text(
                            rx.cond(ImageState.search_query, "No images found", "No images available"),
                            color=COLORS["text_muted"],
                            font_size=TYPOGRAPHY["font_sizes"]["lg"],
                        ),
                        padding=SPACING["xl"],
                        text_align="center",
                    ),
                ),
            ),
            
            margin_top="60px",  # Account for header
        ),
        
        # Image modal
        image_modal(),
        
        width="100%",
        min_height="100vh",
        position="relative",
        
        # Load images on mount
        on_mount=lambda: ImageState.load_images(1),
    )


def images_page() -> rx.Component:
    """Image gallery page with authentication protection."""
    return rx.cond(
        AuthState.is_authenticated,
        image_gallery_content(),
        authentication_required_component(),
    )
