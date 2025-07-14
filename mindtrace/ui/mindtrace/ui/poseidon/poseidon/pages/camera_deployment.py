"""
Camera deployment page for managing inference servers.
"""
import reflex as rx
from poseidon.components.image_components import (
    COLORS, TYPOGRAPHY, SIZING, SPACING, content_variants, button_variants, card_variants
)
from poseidon.components import (
    sidebar, app_header, authentication_required_component, page_container
)
from poseidon.state.auth import AuthState
from poseidon.state.camera_deployment import (
    CameraDeploymentState, CameraDict, ModelDict, InferenceServerDict
)


def camera_card(camera: rx.Var[CameraDict]) -> rx.Component:
    """Camera selection card"""
    is_selected = CameraDeploymentState.selected_cameras.contains(camera.id)
    
    custom_styles = {
        "width": "100%",
        "max_width": "320px",
        "cursor": "pointer",
        "_hover": {
            "transform": "translateY(-2px)",
            "box_shadow": "0 8px 25px rgba(0, 0, 0, 0.15)",
        }
    }
    
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.checkbox(
                    checked=is_selected,
                    on_change=lambda: CameraDeploymentState.toggle_camera_selection(camera.id),
                ),
                rx.box(
                    width="8px",
                    height="8px", 
                    border_radius="50%",
                    background=rx.cond(
                        camera.status == "online",
                        COLORS["success"],
                        rx.cond(
                            camera.status == "offline", 
                            COLORS["error"],
                            COLORS["warning"]
                        )
                    ),
                ),
                spacing="2",
                align="center",
                justify="between",
                width="100%",
                margin_bottom=SPACING["sm"],
            ),
            rx.vstack(
                rx.text(
                    camera.name,
                    font_weight=TYPOGRAPHY["font_weights"]["semibold"],
                    font_size=TYPOGRAPHY["font_sizes"]["base"],
                    color=COLORS["text"],
                    text_align="center",
                ),
                rx.text(
                    camera.location,
                    font_size=TYPOGRAPHY["font_sizes"]["sm"],
                    color=COLORS["text_muted"],
                    text_align="center",
                ),
                rx.text(
                    camera.ip_address,
                    font_size=TYPOGRAPHY["font_sizes"]["xs"],
                    color=COLORS["text_muted"],
                    font_family="mono",
                ),
                rx.text(
                    f"Status: {camera.status.title()}",
                    font_size=TYPOGRAPHY["font_sizes"]["xs"],
                    color=rx.cond(
                        camera.status == "online",
                        COLORS["success"],
                        rx.cond(
                            camera.status == "offline",
                            COLORS["error"], 
                            COLORS["warning"]
                        )
                    ),
                ),
                spacing="1",
                align="center",
                width="100%",
            ),
            spacing="2",
            align="center", 
            width="100%",
        ),
        **{**card_variants["feature"], **custom_styles, "padding": SPACING["md"]},
        border=rx.cond(
            is_selected,
            f"2px solid {COLORS['primary']}",
            f"1px solid {COLORS['border']}"
        ),
        on_click=lambda: CameraDeploymentState.toggle_camera_selection(camera.id),
        
    )


def model_card(model: rx.Var[ModelDict]) -> rx.Component:
    """Model selection card"""
    is_selected = CameraDeploymentState.selected_model_id == model.id
    
    custom_styles = {
        "width": "100%",
        "max_width": "350px",
        "cursor": "pointer",
        "_hover": {
            "transform": "translateY(-2px)",
            "box_shadow": "0 8px 25px rgba(0, 0, 0, 0.15)",
        }
    }
    
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.box(
                    width="12px",
                    height="12px",
                    border_radius="50%",
                    background=rx.cond(
                        is_selected,
                        COLORS["primary"],
                        "transparent"
                    ),
                    border=f"2px solid {COLORS['primary']}",
                ),
                rx.box(
                    width="8px", 
                    height="8px",
                    border_radius="50%",
                    background=rx.cond(
                        model.status == "available",
                        COLORS["success"],
                        rx.cond(
                            model.status == "loading",
                            COLORS["warning"],
                            COLORS["error"]
                        )
                    ),
                ),
                spacing="2",
                align="center",
                justify="between",
                width="100%",
                margin_bottom=SPACING["sm"],
            ),
            rx.vstack(
                rx.text(
                    model.name,
                    font_weight=TYPOGRAPHY["font_weights"]["semibold"],
                    font_size=TYPOGRAPHY["font_sizes"]["base"],
                    color=COLORS["text"],
                    text_align="center",
                ),
                rx.text(
                    f"v{model.version} • {model.type.replace('_', ' ').title()}",
                    font_size=TYPOGRAPHY["font_sizes"]["sm"],
                    color=COLORS["text_muted"],
                    text_align="center",
                ),
                rx.text(
                    model.description,
                    font_size=TYPOGRAPHY["font_sizes"]["xs"],
                    color=COLORS["text_muted"],
                    text_align="center",
                    line_height="1.4",
                ),
                rx.hstack(
                    rx.text(
                        f"{model.size_mb}MB",
                        font_size=TYPOGRAPHY["font_sizes"]["xs"],
                        color=COLORS["text_muted"],
                    ),
                    rx.text(
                        f"{model.accuracy}% acc",
                        font_size=TYPOGRAPHY["font_sizes"]["xs"],
                        color=COLORS["success"],
                    ),
                    spacing="3",
                    justify="center",
                ),
                spacing="2",
                align="center",
                width="100%",
            ),
            spacing="2",
            align="center",
            width="100%",
        ),
        **{**card_variants["feature"], **custom_styles, "padding": SPACING["md"]},
        border=rx.cond(
            is_selected,
            f"2px solid {COLORS['primary']}",
            f"1px solid {COLORS['border']}"
        ),
        on_click=lambda: CameraDeploymentState.set_selected_model(model.id),
    )


def inference_server_card(server: rx.Var[InferenceServerDict]) -> rx.Component:
    """Inference server status card"""
    custom_styles = {
        "width": "100%",
        "max_width": "400px",
        "cursor": "pointer",
        "_hover": {
            "transform": "translateY(-2px)",
            "box_shadow": "0 8px 25px rgba(0, 0, 0, 0.15)",
        }
    }
    
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.text(
                    server.name,
                    font_weight=TYPOGRAPHY["font_weights"]["semibold"],
                    font_size=TYPOGRAPHY["font_sizes"]["base"],
                    color=COLORS["text"],
                ),
                rx.box(
                    width="10px",
                    height="10px",
                    border_radius="50%",
                    background=rx.cond(
                        server.status == "running",
                        COLORS["success"],
                        rx.cond(
                            server.status == "stopped",
                            COLORS["error"],
                            COLORS["warning"]
                        )
                    ),
                ),
                spacing="2",
                align="center",
                justify="between",
                width="100%",
            ),
            rx.vstack(
                rx.text(
                    f"Status: {server.status.title()}",
                    font_size=TYPOGRAPHY["font_sizes"]["sm"],
                    color=rx.cond(
                        server.status == "running",
                        COLORS["success"],
                        rx.cond(
                            server.status == "stopped",
                            COLORS["error"],
                            COLORS["warning"]
                        )
                    ),
                ),
                rx.text(
                    f"Cameras: {server.cameras.length()}",
                    font_size=TYPOGRAPHY["font_sizes"]["sm"],
                    color=COLORS["text_muted"],
                ),
                rx.text(
                    f"Model: {server.model_id}",
                    font_size=TYPOGRAPHY["font_sizes"]["xs"],
                    color=COLORS["text_muted"],
                ),
                rx.text(
                    server.endpoint,
                    font_size=TYPOGRAPHY["font_sizes"]["xs"],
                    color=COLORS["text_muted"],
                    font_family="mono",
                ),
                spacing="1",
                align="start",
                width="100%",
            ),
            spacing="3",
            align="start",
            width="100%",
        ),
        **{**card_variants["feature"], **custom_styles,},
        on_click=lambda: CameraDeploymentState.open_server_details(server),
    )


def deployment_modal() -> rx.Component:
    """Deployment confirmation modal"""
    return rx.cond(
        CameraDeploymentState.show_deployment_modal,
        rx.box(
            rx.box(
                rx.vstack(
                    rx.hstack(
                        rx.heading(
                            "Deploy Inference Server",
                            font_size=TYPOGRAPHY["font_sizes"]["xl"],
                            color=COLORS["text"],
                        ),
                        rx.button(
                            "✕",
                            on_click=CameraDeploymentState.close_deployment_modal,
                            **button_variants["ghost"],
                            font_size=TYPOGRAPHY["font_sizes"]["lg"],
                        ),
                        justify="between",
                        align="center",
                        width="100%",
                    ),
                    rx.form(
                        rx.vstack(
                            rx.vstack(
                                rx.text(
                                    "Server Name",
                                    font_weight=TYPOGRAPHY["font_weights"]["semibold"],
                                    color=COLORS["text"],
                                ),
                                rx.input(
                                    placeholder="Enter inference server name...",
                                    name="server_name",
                                    required=True,
                                    width="100%",
                                ),
                                spacing="1",
                                align="start",
                                width="100%",
                            ),
                            rx.vstack(
                                rx.text(
                                    f"Selected Cameras: {CameraDeploymentState.selected_cameras.length()}",
                                    font_size=TYPOGRAPHY["font_sizes"]["sm"],
                                    color=COLORS["text_muted"],
                                ),
                                rx.text(
                                    f"Selected Model: {CameraDeploymentState.selected_model_id}",
                                    font_size=TYPOGRAPHY["font_sizes"]["sm"],
                                    color=COLORS["text_muted"],
                                ),
                                spacing="1",
                                align="start",
                                width="100%",
                            ),
                            rx.cond(
                                CameraDeploymentState.deployment_error,
                                rx.text(
                                    CameraDeploymentState.deployment_error,
                                    color=COLORS["error"],
                                    font_size=TYPOGRAPHY["font_sizes"]["sm"],
                                ),
                            ),
                            rx.cond(
                                CameraDeploymentState.is_deploying,
                                rx.vstack(
                                    rx.spinner(size="3"),
                                    rx.text(
                                        CameraDeploymentState.deployment_status,
                                        color=COLORS["text_muted"],
                                        font_size=TYPOGRAPHY["font_sizes"]["sm"],
                                    ),
                                    spacing="2",
                                    align="center",
                                ),
                                rx.hstack(
                                    rx.button(
                                        "Cancel",
                                        on_click=CameraDeploymentState.close_deployment_modal,
                                        **button_variants["secondary"],
                                    ),
                                    rx.button(
                                        "Deploy",
                                        type="submit",
                                        **button_variants["primary"],
                                    ),
                                    spacing="2",
                                    justify="end",
                                    width="100%",
                                ),
                            ),
                            spacing="4",
                            width="100%",
                        ),
                        on_submit=CameraDeploymentState.deploy_inference_server,
                        width="100%",
                    ),
                    spacing="4",
                    width="100%",
                ),
                background=COLORS["white"],
                border_radius=SIZING["border_radius"],
                padding=SPACING["lg"],
                max_width="500px",
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
        ),
    )


def server_details_modal() -> rx.Component:
    """Server details modal"""
    return rx.cond(
        CameraDeploymentState.show_server_details_modal & (CameraDeploymentState.selected_server != None),
        rx.box(
            rx.box(
                rx.vstack(
                    rx.hstack(
                        rx.heading(
                            "Inference Server Details",
                            font_size=TYPOGRAPHY["font_sizes"]["xl"],
                            color=COLORS["text"],
                        ),
                        rx.button(
                            "✕",
                            on_click=CameraDeploymentState.close_server_details_modal,
                            **button_variants["ghost"],
                            font_size=TYPOGRAPHY["font_sizes"]["lg"],
                        ),
                        justify="between",
                        align="center",
                        width="100%",
                    ),
                    rx.vstack(
                        rx.hstack(
                            rx.text("Name:", font_weight=TYPOGRAPHY["font_weights"]["semibold"]),
                            rx.text(CameraDeploymentState.selected_server.name),
                            spacing="2",
                        ),
                        rx.hstack(
                            rx.text("Status:", font_weight=TYPOGRAPHY["font_weights"]["semibold"]),
                            rx.text(
                                CameraDeploymentState.selected_server.status.title(),
                                color=rx.cond(
                                    CameraDeploymentState.selected_server.status == "running",
                                    COLORS["success"],
                                    COLORS["error"]
                                ),
                            ),
                            spacing="2",
                        ),
                        rx.hstack(
                            rx.text("Endpoint:", font_weight=TYPOGRAPHY["font_weights"]["semibold"]),
                            rx.text(
                                CameraDeploymentState.selected_server.endpoint,
                                font_family="mono",
                                font_size=TYPOGRAPHY["font_sizes"]["sm"],
                            ),
                            spacing="2",
                        ),
                        rx.hstack(
                            rx.text("Model:", font_weight=TYPOGRAPHY["font_weights"]["semibold"]),
                            rx.text(CameraDeploymentState.selected_server.model_id),
                            spacing="2",
                        ),
                        spacing="3",
                        align="start",
                        width="100%",
                    ),
                    rx.hstack(
                        rx.cond(
                            CameraDeploymentState.selected_server.status == "running",
                            rx.button(
                                "Stop Server",
                                on_click=lambda: CameraDeploymentState.stop_inference_server(
                                    CameraDeploymentState.selected_server.id
                                ),
                                **button_variants["secondary"],
                            ),
                            rx.button(
                                "Start Server",
                                on_click=lambda: CameraDeploymentState.start_inference_server(
                                    CameraDeploymentState.selected_server.id
                                ),
                                **button_variants["primary"],
                            ),
                        ),
                        rx.button(
                            "Delete Server",
                            on_click=lambda: CameraDeploymentState.delete_inference_server(
                                CameraDeploymentState.selected_server.id
                            ),
                            background=COLORS["error"],
                            color=COLORS["white"],
                            _hover={"opacity": "0.8"},
                        ),
                        spacing="2",
                        justify="end",
                        width="100%",
                    ),
                    spacing="4",
                    width="100%",
                ),
                background=COLORS["white"],
                border_radius=SIZING["border_radius"],
                padding=SPACING["lg"],
                max_width="600px",
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
        ),
    )


def camera_deployment_content() -> rx.Component:
    """Camera deployment page content"""
    return rx.box(
        # Sidebar navigation (fixed position)
        rx.box(
            sidebar(),
            position="fixed",
            left="0",
            top="0",
            width="240px",
            height="100vh",
            z_index="1000",
        ),
        
        # Header (fixed position)
        rx.box(
            app_header(),
            position="fixed",
            top="0",
            left="240px",
            right="0",
            height="60px",
            z_index="999",
        ),
        
        # Main content using page_container
        page_container(
            # Page header
            rx.box(
                rx.heading("Camera Deployment", **content_variants["page_title"]),
                rx.text("Deploy inference servers with cameras and AI models", **content_variants["page_subtitle"]),
                **content_variants["page_header"]
            ),
            
            # Cameras section
            rx.vstack(
                rx.heading(
                    "Select Cameras",
                    font_size=TYPOGRAPHY["font_sizes"]["lg"],
                    color=COLORS["text"],
                    margin_bottom=SPACING["md"],
                ),
                rx.box(
                    rx.foreach(CameraDeploymentState.cameras, camera_card),
                    display="grid",
                    grid_template_columns="repeat(auto-fill, minmax(300px, 1fr))",
                    gap=SPACING["md"],
                    width="100%",
                ),
                spacing="4",
                width="100%",
                margin_bottom=SPACING["xl"],
            ),
            
            # Models section
            rx.vstack(
                rx.heading(
                    "Select Model",
                    font_size=TYPOGRAPHY["font_sizes"]["lg"],
                    color=COLORS["text"],
                    margin_bottom=SPACING["md"],
                ),
                rx.box(
                    rx.foreach(CameraDeploymentState.models, model_card),
                    display="grid",
                    grid_template_columns="repeat(auto-fill, minmax(240px, 1fr))",
                    gap=SPACING["md"],
                    width="100%",
                ),
                spacing="4",
                width="100%",
                margin_bottom=SPACING["xl"],
            ),
            
            # Deploy button
            rx.hstack(
                rx.button(
                    "Deploy Inference Server",
                    on_click=CameraDeploymentState.open_deployment_modal,
                    **button_variants["primary"],
                    size="3",
                ),
                rx.cond(
                    CameraDeploymentState.deployment_error,
                    rx.text(
                        CameraDeploymentState.deployment_error,
                        color=COLORS["error"],
                        font_size=TYPOGRAPHY["font_sizes"]["sm"],
                    ),
                ),
                spacing="3",
                align="center",
                margin_bottom=SPACING["xl"],
            ),
            
            # Active inference servers
            rx.vstack(
                rx.heading(
                    "Active Inference Servers",
                    font_size=TYPOGRAPHY["font_sizes"]["lg"],
                    color=COLORS["text"],
                    margin_bottom=SPACING["md"],
                ),
                rx.cond(
                    CameraDeploymentState.inference_servers.length() > 0,
                    rx.box(
                        rx.foreach(CameraDeploymentState.inference_servers, inference_server_card),
                        display="grid",
                        grid_template_columns="repeat(auto-fill, minmax(380px, 1fr))",
                        gap=SPACING["md"],
                        width="100%",
                    ),
                    rx.box(
                        rx.text(
                            "No inference servers deployed yet",
                            color=COLORS["text_muted"],
                            font_size=TYPOGRAPHY["font_sizes"]["lg"],
                        ),
                        padding=SPACING["xl"],
                        text_align="center",
                    ),
                ),
                spacing="4",
                width="100%",
            ),
            
            margin_top="60px",  # Account for header
        ),
        
        # Modals
        deployment_modal(),
        server_details_modal(),
        
        width="100%",
        min_height="100vh",
        position="relative",
        
        # Load mock data on mount
        on_mount=CameraDeploymentState.load_mock_data,
    )


def camera_deployment_page() -> rx.Component:
    """Camera deployment page with authentication protection"""
    return rx.cond(
        AuthState.is_authenticated,
        camera_deployment_content(),
        authentication_required_component(),
    ) 