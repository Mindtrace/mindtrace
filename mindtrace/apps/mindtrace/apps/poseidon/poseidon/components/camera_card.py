import reflex as rx
from poseidon.state.camera import CameraState
from poseidon.components.mindtrace_cards import card_mindtrace


def camera_card(camera: str) -> rx.Component:
    """Camera card with scoped access control and project-aware functionality."""
    
    def camera_header() -> rx.Component:
        """Camera header with icon, name, and status."""
        return rx.hstack(
            rx.box(
                "📷",
                font_size="2rem",
                padding="0.75rem",
                background="#F9FAFB",
                border_radius="8px",
                border="1px solid #E5E7EB",
            ),
            rx.vstack(
                rx.text(
                    rx.cond(
                        camera.contains(":"),
                        camera.split(":")[1],
                        camera
                    ),
                    font_weight="600",
                    font_size="1.1rem",
                    color="#111827",
                ),
                rx.text(
                    rx.cond(
                        camera.contains(":"),
                        camera.split(":")[0],
                        "Unknown"
                    ),
                    font_size="0.875rem",
                    color="#6B7280",
                ),
                # Status badge
                rx.box(
                    rx.text(
                        CameraState.camera_status_badges[camera],
                        font_size="0.75rem",
                        font_weight="500",
                        color="white",
                    ),
                    background=CameraState.camera_status_colors[camera],
                    padding="0.25rem 0.5rem",
                    border_radius="4px",
                    margin_top="0.5rem",
                ),
                # Project assignment info
                rx.text(
                    f"Assigned to: {CameraState.camera_project_assignments.get(camera, 'Unassigned')}",
                    font_size="0.75rem",
                    color=rx.cond(
                        CameraState.camera_project_assignments.get(camera, "Unassigned") != "Unassigned",
                        "#059669",  # Green for assigned
                        "#DC2626"   # Red for unassigned
                    ),
                    font_style="italic",
                ),
                spacing="1",
                align="start",
            ),
            spacing="3",
            align="center",
            width="100%",
        )
    
    def action_buttons() -> rx.Component:
        """Action buttons with access control for camera operations."""
        return rx.vstack(
            # Initialize/Deinitialize button (conditional based on status and permissions)
            rx.cond(
                CameraState.cameras.contains(camera),
            rx.cond(
                CameraState.camera_statuses.get(camera, "not_initialized") == "available",
                # Camera is available - show Deinitialize button (red)
                rx.button(
                    "Deinitialize",
                    variant="solid",
                    color_scheme="red",
                    size="2",
                    on_click=lambda name=camera: CameraState.close_camera(name),
                    width="100%",
                    _hover={"transform": "translateY(-1px)", "box_shadow": "0 4px 8px rgba(0, 0, 0, 0.15)"},
                    transition="all 0.2s ease",
                ),
                # Camera is not available - show Initialize button (blue)
                rx.button(
                    "Initialize",
                    variant="solid",
                    color_scheme="blue",
                    size="2",
                    on_click=lambda name=camera: CameraState.initialize_camera(name),
                    width="100%",
                    _hover={"transform": "translateY(-1px)", "box_shadow": "0 4px 8px rgba(0, 0, 0, 0.15)"},
                    transition="all 0.2s ease",
                ),
            ),
                # Camera not in scope - show disabled button
                rx.button(
                    "Not in Project Scope",
                    variant="outline",
                    color_scheme="gray",
                    size="2",
                    disabled=True,
                    width="100%",
                ),
            ),
            
            # Configure button (only if available and in scope)
            rx.cond(
                CameraState.cameras.contains(camera) & (CameraState.camera_statuses.get(camera, "not_initialized") == "available"),
                rx.button(
                    "Configure",
                    variant="solid",
                    color_scheme="green",
                    size="2",
                    width="100%",
                    on_click=lambda name=camera: CameraState.open_camera_config(name),
                    _hover={"transform": "translateY(-1px)", "box_shadow": "0 4px 8px rgba(0, 0, 0, 0.15)"},
                    transition="all 0.2s ease",
                ),
                rx.box(height="40px"),  # Placeholder to maintain consistent card height
            ),
            
            # Capture button (only if available and in scope)
            rx.cond(
                CameraState.cameras.contains(camera) & (CameraState.camera_statuses.get(camera, "not_initialized") == "available"),
                rx.cond(
                    CameraState.capture_loading,
                    rx.button(
                        rx.hstack(
                            rx.spinner(size="1"),
                            rx.text("Capturing...", font_size="0.875rem"),
                            spacing="2",
                            align="center",
                        ),
                        variant="solid",
                        color_scheme="purple",
                        size="2",
                        width="100%",
                        disabled=True,
                    ),
                    rx.button(
                        "📸 Capture",
                        variant="solid",
                        color_scheme="purple",
                        size="2",
                        width="100%",
                        on_click=lambda name=camera: CameraState.capture_image_from_card(name),
                        _hover={"transform": "translateY(-1px)", "box_shadow": "0 4px 8px rgba(0, 0, 0, 0.15)"},
                        transition="all 0.2s ease",
                    ),
                ),
                rx.box(height="40px"),  # Placeholder to maintain consistent card height
            ),
            
            # Admin actions (only for admins and super admins)
            rx.cond(
                CameraState.is_admin | CameraState.is_super_admin,
                rx.cond(
                    # Show "Assign to Organization" for super admins when camera not assigned
                    CameraState.is_super_admin & (CameraState.camera_statuses.get(camera, "not_assigned") == "not_assigned"),
                    rx.button(
                        "Assign to Organization",
                        variant="outline",
                        color_scheme="green",
                        size="1",
                        width="100%",
                        font_size="0.75rem",
                        on_click=lambda: CameraState.assign_camera_to_organization(camera),
                        _hover={"transform": "translateY(-1px)", "box_shadow": "0 2px 4px rgba(0, 0, 0, 0.1)"},
                        transition="all 0.2s ease",
                    ),
                    # Show "Manage Assignment" for all admins and super admins
                    rx.button(
                        "Manage Assignment",
                        variant="outline",
                        color_scheme="orange",
                        size="1",
                        width="100%",
                        font_size="0.75rem",
                        on_click=lambda: CameraState.open_camera_assignment_dialog(camera),
                        _hover={"transform": "translateY(-1px)", "box_shadow": "0 2px 4px rgba(0, 0, 0, 0.1)"},
                        transition="all 0.2s ease",
                    ),
                ),
                rx.box(height="32px"),  # Placeholder for non-admin users
            ),
            
            spacing="2",
            width="100%",
            align="stretch",
        )
    
    def camera_footer() -> rx.Component:
        """Camera footer with additional info and quick actions."""
        return rx.hstack(
            rx.cond(
                CameraState.cameras.contains(camera),
                rx.hstack(
                    rx.text(
                        "✓",
                        color="#059669",
                        font_weight="bold",
                        font_size="0.875rem",
                    ),
                    rx.text(
                        "Accessible",
                        color="#059669",
                        font_size="0.75rem",
                        font_weight="500",
                    ),
                    spacing="1",
                    align="center",
                ),
                rx.hstack(
                    rx.text(
                        "⚠",
                        color="#DC2626",
                        font_weight="bold",
                        font_size="0.875rem",
                    ),
                    rx.text(
                        "No Access",
                        color="#DC2626",
                        font_size="0.75rem",
                        font_weight="500",
                    ),
                    spacing="1",
                    align="center",
                ),
            ),
            rx.spacer(),
            rx.cond(
                CameraState.camera_statuses.get(camera, "not_initialized") == "available",
                rx.text(
                    "🟢 Online",
                    font_size="0.75rem",
                    color="#059669",
                    font_weight="500",
                ),
                rx.text(
                    "🔴 Offline",
                    font_size="0.75rem",
                    color="#DC2626",
                    font_weight="500",
                ),
            ),
            width="100%",
            align="center",
        )
    
    return card_mindtrace(
        children=[
            camera_header(), 
            action_buttons(),
            camera_footer(),
        ],
        width="100%",
        min_height="240px",
    ) 