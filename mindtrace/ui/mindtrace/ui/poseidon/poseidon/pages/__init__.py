"""Pages for the Reflex app."""

from .index import index

# Import from subfolders
from .auth import login_page, register_page, register_admin_page, register_super_admin_page
from .dashboards import admin_page, super_admin_dashboard_page
from .management import user_management_page, organization_management_page
from .user import profile_page
from .camera_configurator import camera_configurator_page

__all__ = [
    "index", 
    # Auth pages
    "login_page", 
    "register_page", 
    "register_admin_page",
    "register_super_admin_page",
    # Dashboard pages
    "admin_page",
    "super_admin_dashboard_page",
    # Management pages
    "user_management_page",
    "organization_management_page",
    # User pages
    "profile_page",
    "camera_configurator_page",
] 