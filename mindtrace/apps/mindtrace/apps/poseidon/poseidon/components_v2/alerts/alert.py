"""
Poseidon Alert Component

A comprehensive alert component inspired by MUI alerts with multiple variants,
severity levels, and styling options.
"""

import reflex as rx
from typing import Literal, Optional, Union, Callable
from poseidon.styles.variants import COMPONENT_VARIANTS
from poseidon.styles.global_styles import TYPOGRAPHY, SPACING, EFFECTS


class Alert(rx.Component):
    """
    A comprehensive alert component inspired by MUI alerts.
    
    Features:
    - Multiple severity levels: success, error, warning, info
    - Multiple variants: filled, outlined, soft
    - Optional actions
    - Dismissible functionality
    - Customizable styling
    """
    
    # Component props
    severity: Literal["success", "error", "warning", "info"] = "info"
    variant: Literal["filled", "outlined", "soft"] = "filled"
    title: Optional[str] = None
    message: str = ""
    action: Optional[rx.Component] = None
    dismissible: bool = False
    on_dismiss: Optional[Callable] = None
    show: bool = True
    
    # Styling props
    margin: Optional[str] = None
    margin_bottom: Optional[str] = None
    width: Optional[str] = None
    max_width: Optional[str] = None
    
    def _get_styles(self) -> dict:
        """Get the combined styles for the alert."""
        base_styles = COMPONENT_VARIANTS["alert"]["base"].copy()
        severity_styles = COMPONENT_VARIANTS["alert"][self.severity].copy()
        variant_styles = COMPONENT_VARIANTS["alert"][self.variant].copy()
        
        # Merge all styles
        styles = {**base_styles, **severity_styles, **variant_styles}
        
        # Add custom props
        if self.margin:
            styles["margin"] = self.margin
        if self.margin_bottom:
            styles["margin_bottom"] = self.margin_bottom
        if self.width:
            styles["width"] = self.width
        if self.max_width:
            styles["max_width"] = self.max_width
            
        return styles
    
    def _render_content(self) -> rx.Component:
        """Render the alert content."""
        content = []
        
        # Add text content
        text_content = []
        text_content.append(
            rx.cond(
                self.title,
                rx.text(
                    self.title,
                    font_weight=TYPOGRAPHY["font_weights"]["semibold"],
                    margin_bottom="0.25rem",
                ),
                rx.fragment()
            )
        )
        
        text_content.append(
            rx.cond(
                self.message,
                rx.text(
                    self.message,
                    font_weight=TYPOGRAPHY["font_weights"]["normal"],
                ),
                rx.fragment()
            )
        )
        
        content.append(
            rx.box(
                *text_content,
                flex="1",
            )
        )
        
        # Add action
        content.append(
            rx.cond(
                self.action,
                rx.box(
                    self.action,
                    margin_left=SPACING["sm"],
                    flex_shrink="0",
                ),
                rx.fragment()
            )
        )
        
        # Add dismiss button
        content.append(
            rx.cond(
                self.dismissible,
                rx.button(
                    "×",
                    on_click=self.on_dismiss,
                    background="transparent",
                    border="none",
                    cursor="pointer",
                    padding="0.25rem",
                    border_radius="50%",
                    transition=EFFECTS["transitions"]["fast"],
                    _hover={
                        "background": "rgba(0, 0, 0, 0.1)",
                    },
                    margin_left=SPACING["sm"],
                    flex_shrink="0",
                    font_size="1.2rem",
                    font_weight="bold",
                ),
                rx.fragment()
            )
        )
        
        return rx.hstack(
            *content,
            align="start",
            width="100%",
        )
    
    def render(self) -> rx.Component:
        """Render the alert component."""
        return rx.cond(
            self.show,
            rx.box(
                self._render_content(),
                **self._get_styles(),
            ),
            rx.fragment()
        )


# Convenience functions for quick alert creation
def success_alert(
    message: str,
    title: Optional[str] = None,
    variant: Literal["filled", "outlined", "soft"] = "filled",
    dismissible: bool = False,
    on_dismiss: Optional[Callable] = None,
    **kwargs
) -> Alert:
    """Create a success alert."""
    return Alert(
        severity="success",
        variant=variant,
        title=title,
        message=message,
        dismissible=dismissible,
        on_dismiss=on_dismiss,
        **kwargs
    )


def error_alert(
    message: str,
    title: Optional[str] = None,
    variant: Literal["filled", "outlined", "soft"] = "filled",
    dismissible: bool = False,
    on_dismiss: Optional[Callable] = None,
    **kwargs
) -> Alert:
    """Create an error alert."""
    return Alert(
        severity="error",
        variant=variant,
        title=title,
        message=message,
        dismissible=dismissible,
        on_dismiss=on_dismiss,
        **kwargs
    )


def warning_alert(
    message: str,
    title: Optional[str] = None,
    variant: Literal["filled", "outlined", "soft"] = "filled",
    dismissible: bool = False,
    on_dismiss: Optional[Callable] = None,
    **kwargs
) -> Alert:
    """Create a warning alert."""
    return Alert(
        severity="warning",
        variant=variant,
        title=title,
        message=message,
        dismissible=dismissible,
        on_dismiss=on_dismiss,
        **kwargs
    )


def info_alert(
    message: str,
    title: Optional[str] = None,
    variant: Literal["filled", "outlined", "soft"] = "filled",
    dismissible: bool = False,
    on_dismiss: Optional[Callable] = None,
    **kwargs
) -> Alert:
    """Create an info alert."""
    return Alert(
        severity="info",
        variant=variant,
        title=title,
        message=message,
        dismissible=dismissible,
        on_dismiss=on_dismiss,
        **kwargs
    )


# Alert group component for multiple alerts
class AlertGroup(rx.Component):
    """
    A component to group multiple alerts together.
    """
    
    alerts: list[Alert] = []
    spacing: str = SPACING["sm"]
    max_alerts: Optional[int] = None
    
    def render(self) -> rx.Component:
        """Render the alert group."""
        alerts_to_show = self.alerts
        if self.max_alerts:
            alerts_to_show = self.alerts[:self.max_alerts]
        
        return rx.vstack(
            *alerts_to_show,
            spacing=self.spacing,
            width="100%",
        ) 