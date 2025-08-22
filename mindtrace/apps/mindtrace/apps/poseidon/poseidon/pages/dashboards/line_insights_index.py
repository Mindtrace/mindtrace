"""
Line Insights Index Page

Landing page for Line Insights that allows users to select a plant and line
to view the insights dashboard.
"""

import reflex as rx
from poseidon.components_v2.containers.page_container import page_container
from poseidon.components_v2.core.button import button
from poseidon.styles.global_styles import THEME as T
from poseidon.backend.database.repositories.organization_repository import OrganizationRepository
from poseidon.backend.database.repositories.project_repository import ProjectRepository
from poseidon.state.auth import AuthState


class LineInsightsIndexState(rx.State):
    """State for Line Insights index page."""
    
    organizations: list[dict] = []
    projects: list[dict] = []
    selected_org_id: str = ""
    selected_project_id: str = ""
    loading: bool = False
    
    async def on_mount(self):
        """Load organizations and projects on mount."""
        self.loading = True
        try:
            # Get auth state to check permissions
            auth_state = await self.get_state(AuthState)
            
            if auth_state.is_super_admin:
                # Super admin can see all organizations
                orgs = await OrganizationRepository.get_all()
                # Convert to dict format for the frontend
                self.organizations = [
                    {"id": str(org.id), "name": org.name}
                    for org in orgs
                ]
            elif auth_state.is_admin:
                # Regular admin can only see their organization
                org = await OrganizationRepository.get_by_id(auth_state.user_organization_id)
                if org:
                    self.organizations = [{"id": str(org.id), "name": org.name}]
                else:
                    self.organizations = []
            
            # Load all projects for all organizations
            all_projects = []
            for org in self.organizations:
                org_projects = await self.load_projects_for_org_id(org["id"])
                all_projects.extend(org_projects)
            
            self.projects = all_projects
            
            if self.organizations:
                self.selected_org_id = self.organizations[0]["id"]
        except Exception as e:
            print(f"Error loading data: {e}")
            # Use sample data for development
            self.organizations = [
                {"id": "org1", "name": "Plant Alpha"},
                {"id": "org2", "name": "Plant Beta"},
            ]
            self.projects = [
                {"id": "proj1", "name": "Line 1"},
                {"id": "proj2", "name": "Line 2"},
            ]
        finally:
            self.loading = False
    
    async def load_projects_for_org_id(self, org_id: str) -> list[dict]:
        """Load projects for a specific organization ID and return as list of dicts."""
        try:
            projects = await ProjectRepository.get_by_organization(org_id)
            # Convert to dict format for the frontend, including organization_id
            return [
                {
                    "id": str(proj.id), 
                    "name": proj.name,
                    "organization_id": str(proj.organization.id) if proj.organization else org_id
                }
                for proj in projects
            ]
        except Exception as e:
            print(f"Error loading projects for org {org_id}: {e}")
            # Use sample data
            return [
                {"id": f"proj1_{org_id}", "name": "Production Line A", "organization_id": org_id},
                {"id": f"proj2_{org_id}", "name": "Production Line B", "organization_id": org_id},
            ]
    
    async def load_projects_for_org(self, org_id: str):
        """Load projects for selected organization (legacy method)."""
        projects = await self.load_projects_for_org_id(org_id)
        self.projects = projects
        if self.projects:
            self.selected_project_id = self.projects[0]["id"]
    
    def set_selected_org(self, org_id: str):
        """Set selected organization and load its projects."""
        self.selected_org_id = org_id
        return self.load_projects_for_org(org_id)
    
    def set_selected_project(self, project_id: str):
        """Set selected project."""
        self.selected_project_id = project_id
    
    @rx.var
    def view_insights_url(self) -> str:
        """Generate URL for viewing insights."""
        if self.selected_org_id and self.selected_project_id:
            return f"/line-insights/{self.selected_org_id}/{self.selected_project_id}"
        return "#"


def plant_line_card(org: dict) -> rx.Component:
    """Card for a plant with its lines."""
    # Access dictionary items properly in Reflex foreach
    org_name = rx.cond(
        org["name"],
        org["name"],
        "Unknown Plant"
    )
    org_id = org["id"]
    
    # Get projects for this organization
    org_projects = rx.foreach(
        # Filter projects that belong to this organization
        LineInsightsIndexState.projects.to(list[dict]),
        lambda project: rx.cond(
            project.get("organization_id", org_id) == org_id,  # Show all for now
            rx.link(
                rx.hstack(
                    rx.icon("activity", size=16, color=T.colors.fg_muted),
                    rx.text(
                        project["name"],
                        color=T.colors.fg,
                    ),
                    rx.spacer(),
                    rx.icon("chevron-right", size=16, color=T.colors.fg_muted),
                    padding=T.spacing.space_3,
                    background=T.colors.bg,
                    border_radius=T.radius.r_md,
                    width="100%",
                    align="center",
                    _hover={
                        "background": T.colors.surface_2,
                        "cursor": "pointer",
                    },
                ),
                href=f"/line-insights/{org_id}/{project['id']}",
                text_decoration="none",
                width="100%",
            ),
            rx.fragment(),  # Don't show if not matching
        )
    )
    
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.icon("factory", size=24, color=T.colors.accent),
                rx.text(
                    org_name,
                    font_size=T.typography.fs_xl,
                    font_weight=T.typography.fw_600,
                    color=T.colors.fg,
                ),
                align="center",
                spacing="2",
            ),
            
            rx.divider(color=T.colors.border),
            
            rx.vstack(
                rx.text(
                    "Production Lines (Projects)",
                    font_size=T.typography.fs_sm,
                    color=T.colors.fg_muted,
                    font_weight=T.typography.fw_500,
                ),
                rx.vstack(
                    org_projects,
                    spacing="2",
                    width="100%",
                ),
                spacing="3",
                width="100%",
            ),
            
            spacing="4",
            width="100%",
        ),
        padding=T.spacing.space_5,
        background=T.colors.surface,
        border=f"1px solid {T.colors.border}",
        border_radius=T.radius.r_lg,
        box_shadow=T.shadows.shadow_1,
        _hover={
            "box_shadow": T.shadows.shadow_2,
        },
    )


def line_insights_index_page() -> rx.Component:
    """Line Insights index/selection page."""
    return page_container(
        rx.vstack(
            # Header
            rx.vstack(
                rx.heading(
                    "Line Insights",
                    size="8",
                    font_weight=T.typography.fw_700,
                    color=T.colors.fg,
                ),
                rx.text(
                    "Select a plant and production line to view detailed analytics",
                    font_size=T.typography.fs_lg,
                    color=T.colors.fg_muted,
                ),
                spacing="2",
                align="start",
                width="100%",
            ),
            
            rx.divider(color=T.colors.border),
            
            # Content
            rx.cond(
                LineInsightsIndexState.loading,
                rx.center(
                    rx.spinner(size="3"),
                    height="400px",
                    width="100%",
                ),
                rx.cond(
                    LineInsightsIndexState.organizations.length() > 0,
                    rx.grid(
                        rx.foreach(
                            LineInsightsIndexState.organizations,
                            plant_line_card,
                        ),
                        columns=rx.breakpoints(
                            initial="1",
                            sm="1",
                            md="2",
                            lg="3",
                        ),
                        spacing="4",
                        width="100%",
                    ),
                    rx.center(
                        rx.vstack(
                            rx.icon("triangle-alert", size=48, color=T.colors.fg_muted),
                            rx.text(
                                "No plants available",
                                font_size=T.typography.fs_xl,
                                color=T.colors.fg_muted,
                            ),
                            rx.text(
                                "Please ensure you have the necessary permissions to view plant data.",
                                font_size=T.typography.fs_sm,
                                color=T.colors.fg_subtle,
                                text_align="center",
                            ),
                            spacing="3",
                            align="center",
                        ),
                        height="400px",
                        width="100%",
                    ),
                ),
            ),
            
            # Quick access with sample data (for development)
            rx.box(
                rx.vstack(
                    rx.text(
                        "Quick Access (Development)",
                        font_size=T.typography.fs_sm,
                        color=T.colors.fg_muted,
                        font_weight=T.typography.fw_500,
                    ),
                    rx.hstack(
                        rx.link(
                            button(
                                "View Sample Dashboard",
                                variant="outline",
                                size="sm",
                            ),
                            href="/line-insights/sample-org/sample-project",
                            text_decoration="none",
                        ),
                        spacing="2",
                    ),
                    spacing="2",
                    padding=T.spacing.space_4,
                    background=T.colors.surface,
                    border=f"1px dashed {T.colors.border}",
                    border_radius=T.radius.r_md,
                    width="100%",
                ),
                margin_top=T.spacing.space_6,
            ),
            
            spacing="6",
            width="100%",
            padding_y=T.spacing.space_6,
        ),
        on_mount=LineInsightsIndexState.on_mount,
    )