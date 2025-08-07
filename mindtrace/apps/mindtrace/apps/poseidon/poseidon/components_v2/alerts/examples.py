"""
Alert Component Examples

This module demonstrates how to use the Alert component with all its
variants, severity levels, and features.
"""

import reflex as rx
from .alert import Alert, AlertGroup, success_alert, error_alert, warning_alert, info_alert


def basic_alerts_example():
    """Example of basic alerts with different severities."""
    return rx.vstack(
        rx.heading("Basic Alerts", size="lg", margin_bottom="1rem"),
        
        success_alert(
            message="Your changes have been saved successfully!",
            title="Success",
        ),
        
        error_alert(
            message="There was an error processing your request.",
            title="Error",
        ),
        
        warning_alert(
            message="Please review your input before submitting.",
            title="Warning",
        ),
        
        info_alert(
            message="This is an informational message.",
            title="Info",
        ),
        
        spacing="1rem",
        width="100%",
        max_width="600px",
    )


def alert_variants_example():
    """Example of alerts with different variants."""
    return rx.vstack(
        rx.heading("Alert Variants", size="lg", margin_bottom="1rem"),
        
        # Filled variant (default)
        success_alert(
            message="Filled variant - default styling",
            variant="filled",
        ),
        
        # Outlined variant
        error_alert(
            message="Outlined variant - transparent background",
            variant="outlined",
        ),
        
        # Soft variant
        warning_alert(
            message="Soft variant - subtle shadow",
            variant="soft",
        ),
        
        spacing="1rem",
        width="100%",
        max_width="600px",
    )


def dismissible_alerts_example():
    """Example of dismissible alerts."""
    return rx.vstack(
        rx.heading("Dismissible Alerts", size="lg", margin_bottom="1rem"),
        
        success_alert(
            message="This alert can be dismissed by clicking the X button.",
            title="Dismissible Success",
            dismissible=True,
            on_dismiss=lambda: print("Alert dismissed!"),
        ),
        
        error_alert(
            message="Another dismissible alert with custom action.",
            title="Dismissible Error",
            dismissible=True,
            action=rx.button(
                "Retry",
                size="sm",
                background="rgba(239, 68, 68, 0.2)",
                color="#991b1b",
                border="1px solid rgba(239, 68, 68, 0.3)",
                _hover={"background": "rgba(239, 68, 68, 0.3)"},
            ),
        ),
        
        spacing="1rem",
        width="100%",
        max_width="600px",
    )


def custom_icons_example():
    """Example of alerts with custom icons."""
    return rx.vstack(
        rx.heading("Custom Icons", size="lg", margin_bottom="1rem"),
        
        Alert(
            severity="success",
            message="Alert with custom icon",
            icon="star",
        ),
        
        Alert(
            severity="info",
            message="Alert with custom component icon",
            icon=rx.icon("lightbulb", color="yellow"),
        ),
        
        Alert(
            severity="warning",
            message="Alert without icon",
            icon=None,
        ),
        
        spacing="1rem",
        width="100%",
        max_width="600px",
    )


def alert_with_actions_example():
    """Example of alerts with custom actions."""
    return rx.vstack(
        rx.heading("Alerts with Actions", size="lg", margin_bottom="1rem"),
        
        Alert(
            severity="info",
            message="This alert has a custom action button.",
            action=rx.button(
                "Learn More",
                size="sm",
                background="rgba(59, 130, 246, 0.2)",
                color="#1e40af",
                border="1px solid rgba(59, 130, 246, 0.3)",
                _hover={"background": "rgba(59, 130, 246, 0.3)"},
            ),
        ),
        
        Alert(
            severity="warning",
            message="Multiple actions in one alert.",
            action=rx.hstack(
                rx.button(
                    "Accept",
                    size="sm",
                    background="rgba(245, 158, 11, 0.2)",
                    color="#92400e",
                    border="1px solid rgba(245, 158, 11, 0.3)",
                    _hover={"background": "rgba(245, 158, 11, 0.3)"},
                ),
                rx.button(
                    "Decline",
                    size="sm",
                    background="transparent",
                    color="#92400e",
                    border="1px solid rgba(245, 158, 11, 0.3)",
                    _hover={"background": "rgba(245, 158, 11, 0.1)"},
                ),
                spacing="0.5rem",
            ),
        ),
        
        spacing="1rem",
        width="100%",
        max_width="600px",
    )


def alert_group_example():
    """Example of grouped alerts."""
    alerts = [
        success_alert("First success message"),
        error_alert("Second error message"),
        warning_alert("Third warning message"),
        info_alert("Fourth info message"),
    ]
    
    return rx.vstack(
        rx.heading("Alert Group", size="lg", margin_bottom="1rem"),
        
        AlertGroup(
            alerts=alerts,
            spacing="0.75rem",
            max_alerts=3,  # Only show first 3 alerts
        ),
        
        spacing="1rem",
        width="100%",
        max_width="600px",
    )


def all_alerts_demo():
    """Complete demo of all alert features."""
    return rx.vstack(
        rx.heading("Poseidon Alert Component Demo", size="2xl", margin_bottom="2rem"),
        
        basic_alerts_example(),
        rx.divider(margin="2rem 0"),
        
        alert_variants_example(),
        rx.divider(margin="2rem 0"),
        
        dismissible_alerts_example(),
        rx.divider(margin="2rem 0"),
        
        custom_icons_example(),
        rx.divider(margin="2rem 0"),
        
        alert_with_actions_example(),
        rx.divider(margin="2rem 0"),
        
        alert_group_example(),
        
        spacing="2rem",
        width="100%",
        max_width="800px",
        padding="2rem",
    ) 