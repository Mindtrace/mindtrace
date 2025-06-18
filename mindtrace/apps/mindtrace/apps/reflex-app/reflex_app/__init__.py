"""MindTrace - A modern web application built with Reflex.

This package provides a complete web application with:
- Authentication system with role-based access control
- Clean black and orange design system
- Responsive UI components
- Secure backend services
- Consistent styling patterns

The application follows clean architecture principles with
separated concerns for better maintainability.
"""

from . import state
from .pages import index, login, register

__all__ = ["state", "index", "login", "register"] 