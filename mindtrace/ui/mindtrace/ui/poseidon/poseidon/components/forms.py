"""Poseidon Form Components - Buridan UI Styling.

Renamed Buridan UI pantry forms for Poseidon use cases
while keeping the exact styling patterns.
"""

import reflex as rx
from poseidon.state.auth import AuthState


def form_input_with_label(label: str, placeholder: str, input_type: str = "text", name: str = "", required: bool = False):
    """Form input with label - keeps Buridan UI styling."""
    return rx.vstack(
        rx.text(label, font_size="11px", weight="medium", color_scheme="gray"),
        rx.input(
            placeholder=placeholder, 
            width="100%",
            type=input_type,
            name=name,
            required=required
        ),
        width="100%",
        spacing="2",
    )


def login_form(title: str = "Sign in to your account", subtitle: str = "Enter your credentials"):
    """Login form - keeps Buridan UI styling."""
    return rx.vstack(
        rx.vstack(
            rx.heading(title, size="5", weight="bold"),
            rx.text(
                subtitle,
                font_size="12px",
                weight="medium",
                color_scheme="gray",
                text_align="center",
            ),
            width="100%",
            spacing="1",
            align="center",
            padding="12px 0px",
        ),
        rx.form(
            rx.vstack(
                form_input_with_label("Email", "example@company.com", "email", "email", True),
                form_input_with_label("Password", "Enter your password", "password", "password", True),
                rx.button(
                    "Sign In",
                    width="100%",
                    cursor="pointer",
                    variant="surface",
                    color_scheme="gray",
                    type="submit",
                ),
                # Error display
                rx.cond(
                    AuthState.error,
                    rx.text(
                        AuthState.error,
                        color="red",
                        font_size="12px",
                        text_align="center",
                    )
                ),
                width="100%",
                spacing="3",
            ),
            on_submit=AuthState.login,
            width="100%",
        ),
        width="100%",
        max_width="21em",
        height="100%",
        justify="center",
        align="center",
    )


def registration_form(title: str = "Create your account", subtitle: str = "Fill out the form to get started", extra_fields=None, submit_label="Create Account", on_submit=AuthState.register):
    """Registration form - keeps Buridan UI styling."""
    if extra_fields is None:
        extra_fields = []
    return rx.vstack(
        rx.vstack(
            rx.heading(title, size="5", weight="bold"),
            rx.text(
                subtitle,
                font_size="12px",
                weight="medium",
                color_scheme="gray",
                text_align="center",
            ),
            width="100%",
            spacing="1",
            align="center",
            padding="12px 0px",
        ),
        rx.form(
            rx.vstack(
                rx.hstack(
                    form_input_with_label("Username", "Enter username", "text", "username", True),
                    form_input_with_label("Email", "you@company.com", "email", "email", True),
                    width="100%",
                    display="flex",
                ),
                form_input_with_label("Password", "Create password", "password", "password", True),
                # Organization selection
                rx.vstack(
                    rx.text("Organization", font_size="11px", color_scheme="gray", weight="medium"),
                    rx.cond(
                        AuthState.organizations_loaded,
                        rx.select.root(
                            rx.select.trigger(
                                placeholder="Select your organization",
                                width="100%",
                            ),
                            rx.select.content(
                                rx.foreach(
                                    AuthState.available_organizations,
                                    lambda org: rx.select.item(
                                        org["name"],
                                        value=org["id"],
                                    )
                                ),
                            ),
                            name="organization_id",
                            width="100%",
                        ),
                        rx.input(
                            placeholder="Loading organizations...",
                            disabled=True,
                            width="100%",
                        ),
                    ),
                    width="100%",
                    spacing="2",
                ),
                # Inject extra fields here (e.g., admin key input)
                *extra_fields,
                rx.button(
                    submit_label,
                    width="100%",
                    cursor="pointer",
                    variant="surface",
                    color_scheme="gray",
                    type="submit",
                ),
                # Error display
                rx.cond(
                    AuthState.error,
                    rx.text(
                        AuthState.error,
                        color="red",
                        font_size="12px",
                        text_align="center",
                    )
                ),
                width="100%",
                spacing="3",
            ),
            on_submit=on_submit,
            width="100%",
        ),
        width="100%",
        max_width="21em",
        height="100%",
        justify="center",
        align="center",
    )


def contact_form(title: str = "Contact us", subtitle: str = "We'd love to hear from you"):
    """Contact form - keeps Buridan UI styling."""
    return rx.vstack(
        rx.vstack(
            rx.heading(title, size="5", weight="bold"),
            rx.text(
                subtitle,
                font_size="12px",
                weight="medium",
                color_scheme="gray",
                text_align="center",
            ),
            width="100%",
            spacing="1",
            align="center",
            padding="12px 0px",
        ),
        rx.hstack(
            form_input_with_label("First Name", "First name"),
            form_input_with_label("Last Name", "Last name"),
            width="100%",
            display="flex",
        ),
        form_input_with_label("Email", "example@company.com", "email"),
        rx.vstack(
            rx.text("Message", font_size="11px", color_scheme="gray", weight="medium"),
            rx.text_area(
                width="100%",
                placeholder="Tell us how we can help...",
                rows="5",
            ),
            width="100%",
            spacing="2",
        ),
        rx.button(
            "Send Message",
            width="100%",
            cursor="pointer",
            variant="surface",
            color_scheme="gray",
        ),
        width="100%",
        max_width="21em",
        height="100%",
        justify="center",
        align="center",
    )


# Keep original demo form for reference
def forms_v1():
    """Original Buridan UI demo form - for reference."""
    services = [
        ["Website Design", "Content Creation"],
        ["UX Design", "Consulting"],
        ["Research", "Other"],
    ]
    
    def item_and_title(title: str, placeholder: str):
        return rx.vstack(
            rx.text(title, font_size="11px", weight="medium", color_scheme="gray"),
            rx.input(placeholder=placeholder, width="100%"),
            width="100%",
            spacing="2",
        )

    def check_box_item(name: str):
        return rx.box(rx.checkbox(name), width="100%")

    return rx.vstack(
        rx.vstack(
            rx.heading("Contact our team", size="5", weight="bold"),
            rx.text(
                "Got any questions about the product? We're here to help. Fill out the form below to get started.",
                font_size="12px",
                weight="medium",
                color_scheme="gray",
                text_align="center",
            ),
            width="100%",
            spacing="1",
            align="center",
            padding="12px 0px",
        ),
        rx.hstack(
            item_and_title("First Name", "First name"),
            item_and_title("Last Name", "Last name"),
            width="100%",
            display="flex",
        ),
        item_and_title("Email", "example@someplace.com"),
        rx.vstack(
            rx.text("Message", font_size="11px", color_scheme="gray", weight="medium"),
            rx.text_area(
                width="100%",
                placeholder="Leave us message...",
                rows="5",
            ),
            width="100%",
            spacing="2",
        ),
        rx.vstack(
            rx.text("Services", font_size="11px", color_scheme="gray", weight="medium"),
            *[
                rx.hstack(
                    check_box_item(x),
                    check_box_item(y),
                    width="100%",
                )
                for x, y in services
            ],
            width="100%",
            spacing="2",
        ),
        rx.spacer(),
        rx.button(
            "Continue",
            width="100%",
            cursor="pointer",
            variant="surface",
            color_scheme="gray",
        ),
        width="100%",
        max_width="21em",
        height="100%",
        justify="center",
        align="center",
    )
