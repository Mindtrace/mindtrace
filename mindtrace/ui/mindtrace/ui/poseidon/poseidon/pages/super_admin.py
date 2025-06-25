"""Super Admin Dashboard - System-wide management interface.

This page provides super administrators with:
- Organization management (create, view, manage organizations)
- System-wide user statistics
- Organization admin key management
- System health and analytics
"""

import reflex as rx
from typing import Dict, List
from poseidon.state.auth import AuthState
from poseidon.components.navbar import navbar, sidebar, header
from poseidon.styles import (
    COLORS, TYPOGRAPHY, SIZING, SPACING, SHADOWS,
    card_variants, content_variants, button_variants, input_variants
)

class SuperAdminState(rx.State):
    """State management for super admin operations."""
    
    # Organization management
    organizations: List[Dict[str, str]] = []
    loading: bool = False
    error: str = ""
    success: str = ""
    
    # New organization form
    new_org_name: str = ""
    new_org_description: str = ""
    
    async def load_organizations(self):
        """Load all organizations."""
        try:
            self.loading = True
            self.error = ""
            
            from poseidon.backend.database.repositories.organization_repository import OrganizationRepository
            orgs = await OrganizationRepository.get_all_active()
            
            self.organizations = [
                {
                    "id": str(org.id),
                    "name": org.name,
                    "description": org.description,
                    "subscription_plan": org.subscription_plan,
                    "max_users": org.max_users,
                    "max_projects": org.max_projects,
                    "admin_key": org.admin_registration_key,
                    "created_at": org.created_at,
                    "is_active": org.is_active
                }
                for org in orgs
            ]
            
        except Exception as e:
            self.error = f"Failed to load organizations: {str(e)}"
        finally:
            self.loading = False
    
    async def create_organization(self):
        """Create a new organization."""
        try:
            if not self.new_org_name.strip():
                self.error = "Organization name is required."
                return
            
            self.loading = True
            self.error = ""
            
            from poseidon.backend.database.repositories.organization_repository import OrganizationRepository
            
            org_data = {
                "name": self.new_org_name.strip(),
                "description": self.new_org_description.strip(),
                "subscription_plan": "basic",
                "max_users": 50,
                "max_projects": 10,
                "is_active": True
            }
            
            new_org = await OrganizationRepository.create_organization(org_data)
            self.success = f"Organization '{self.new_org_name}' created successfully!"
            
            # Clear form
            self.new_org_name = ""
            self.new_org_description = ""
            
            # Reload organizations
            await self.load_organizations()
            
        except Exception as e:
            self.error = f"Failed to create organization: {str(e)}"
        finally:
            self.loading = False

def organization_card(org: dict) -> rx.Component:
    """Create an organization card component."""
    return rx.box(
        rx.vstack(
            rx.heading(org["name"], font_size=TYPOGRAPHY["font_sizes"]["lg"]),
            rx.text(
                rx.cond(org["description"], org["description"], "No description"), 
                color=COLORS["text_muted"]
            ),
            rx.text(f"Plan: {org['subscription_plan']}", font_weight="bold"),
            rx.text(f"Limits: {org['max_users']} users, {org['max_projects']} projects"),
            rx.box(
                rx.text("Admin Key:", font_weight="bold"),
                rx.text(org["admin_key"], font_family="monospace", font_size="sm"),
                padding=SPACING["sm"],
                background=COLORS["surface"],
                border_radius=SIZING["border_radius"],
            ),
            spacing="2",
            align="start",
            width="100%",
        ),
        **card_variants["default"],
        margin_bottom=SPACING["md"],
    )

def super_admin_content():
    """Super admin dashboard content."""
    return rx.fragment(
        sidebar(),
        header(),
        rx.box(
            rx.heading("Super Admin Dashboard", **content_variants["page_title"]),
            rx.text("System-wide organization management", **content_variants["page_subtitle"]),
            
            # Create organization form
            rx.box(
                rx.heading("Create New Organization", font_size=TYPOGRAPHY["font_sizes"]["xl"]),
                rx.vstack(
                    rx.input(
                        placeholder="Organization Name",
                        value=SuperAdminState.new_org_name,
                        on_change=SuperAdminState.set_new_org_name,
                        **input_variants["default"],
                    ),
                    rx.input(
                        placeholder="Description",
                        value=SuperAdminState.new_org_description,
                        on_change=SuperAdminState.set_new_org_description,
                        **input_variants["default"],
                    ),
                    rx.button(
                        "Create Organization",
                        on_click=SuperAdminState.create_organization,
                        **button_variants["primary"],
                    ),
                    spacing="3",
                ),
                **card_variants["default"],
                margin_bottom=SPACING["xl"],
            ),
            
            # Organizations list
            rx.box(
                rx.heading("Organizations", font_size=TYPOGRAPHY["font_sizes"]["xl"]),
                rx.cond(
                    SuperAdminState.organizations,
                    rx.foreach(SuperAdminState.organizations, organization_card),
                    rx.text("No organizations found"),
                ),
                **card_variants["default"],
            ),
            
            # Error/success messages
            rx.cond(SuperAdminState.error, rx.text(SuperAdminState.error, color=COLORS["error"])),
            rx.cond(SuperAdminState.success, rx.text(SuperAdminState.success, color=COLORS["success"])),
            
            **content_variants["container"]
        ),
        on_mount=SuperAdminState.load_organizations,
    )

def super_admin_page():
    """Super admin page with dynamic rendering."""
    return rx.box(
        rx.cond(
            AuthState.is_super_admin,
            super_admin_content(),
            rx.box("Redirecting...", on_mount=AuthState.redirect_if_not_super_admin),
        )
    ) 