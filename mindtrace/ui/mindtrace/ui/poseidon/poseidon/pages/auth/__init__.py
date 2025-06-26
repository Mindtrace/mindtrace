"""Authentication pages for login and registration."""

from .login import login_page
from .register import register_page, register_admin_page, register_super_admin_page

__all__ = [
    "login_page",
    "register_page", 
    "register_admin_page",
    "register_super_admin_page",
] 