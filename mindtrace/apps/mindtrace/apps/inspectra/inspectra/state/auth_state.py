from typing import List

import reflex as rx

from inspectra.backend.db.repos.user import InvalidCredentialsError, UserNotFoundError
from inspectra.backend.services.auth_service import AuthService
from inspectra.backend.services.user_service import UserService
from inspectra.state.base_state import BaseState


class AuthState(BaseState):
    """Authentication state."""

    logged_in: bool = False
    username: str = ""
    role: str = ""
    token: str = ""
    error: str = ""
    user_id: str = ""
    line_scope: dict = {}
    line_scope_loaded_for: str = ""
    selected_plant: str = "all"
    selected_line: str = "all"

    @rx.var
    def plants(self) -> List[dict]:
        if not isinstance(self.line_scope, dict):
            return []
        return self.line_scope.get("plants", []) or []

    @rx.var
    def lines(self) -> List[dict]:
        lines = self._all_lines()
        if self.selected_plant in ("", "all"):
            return lines
        return [line for line in lines if line.get("plant_id") == self.selected_plant]

    @rx.var
    def has_scope(self) -> bool:
        return bool(self.line_scope)

    async def login(self, form_data: dict):
        email = form_data.get("email", "").strip()
        password = form_data.get("password", "").strip()

        if not email or not password:
            self._set_error("Email and password required")
            return None

        try:
            user, token = await AuthService.login(email, password)
        except UserNotFoundError:
            self._set_error("User not found or inactive")
            return None
        except InvalidCredentialsError:
            self._set_error("Invalid credentials")
            return None
        except Exception:
            self._set_error("Login failed")
            return None

        self.logged_in = True
        self.username = user.name
        self.user_id = str(user.id)
        self.role = user.role
        self.token = token
        self.error = ""
        return self.redirect("/")

    @rx.event
    async def fetch_line_scope(self):
        if not self.logged_in or not self.user_id:
            return
        if self.line_scope and self.line_scope_loaded_for == self.user_id:
            return
        try:
            scope = await UserService.get_plant_and_line_scope(self.user_id)
        except Exception:
            self.line_scope = {}
            self.line_scope_loaded_for = ""
            self.error = "Unable to load scope"
            return
        self.line_scope = {
            "plants": [{"id": str(item["id"]), "name": item["name"]} for item in scope.get("plants", []) or []],
            "lines": [
                {
                    "id": str(item["id"]),
                    "name": item["name"],
                    "plant_id": str(item["plant_id"]),
                }
                for item in scope.get("lines", []) or []
            ],
        }
        self.line_scope_loaded_for = self.user_id
        if self.selected_line in ("", "all"):
            first_line = self._first_line_id(self.selected_plant)
            if first_line:
                self.selected_line = first_line
        self.error = ""
        return

    @rx.event
    async def change_plant(self, value: str):
        self.selected_plant = value or "all"
        first_line = self._first_line_id(self.selected_plant)
        self.selected_line = first_line or "all"

    @rx.event
    async def change_line(self, value: str):
        candidate = value or "all"
        if candidate == "all":
            self.selected_line = "all"
            return
        allowed = {line["id"] for line in self._lines_for_plant(self.selected_plant)}
        self.selected_line = candidate if candidate in allowed else self._first_line_id(self.selected_plant) or "all"

    def _all_lines(self) -> List[dict]:
        if not isinstance(self.line_scope, dict):
            return []
        return self.line_scope.get("lines", []) or []

    def _lines_for_plant(self, plant_id: str) -> List[dict]:
        lines = self._all_lines()
        if plant_id in ("", "all"):
            return lines
        return [line for line in lines if line.get("plant_id") == plant_id]

    def _first_line_id(self, plant_id: str) -> str:
        lines = self._lines_for_plant(plant_id)
        if not lines:
            return ""
        return lines[0]["id"]

    async def logout(self):
        self.logged_in = False
        self.username = ""
        self.role = ""
        self.token = ""
        self.user_id = ""
        self.line_scope = {}
        self.line_scope_loaded_for = ""
        self.selected_plant = "all"
        self.selected_line = "all"
        return self.redirect("/login")

    def _set_error(self, message: str):
        self.logged_in = False
        self.username = ""
        self.role = ""
        self.token = ""
        self.user_id = ""
        self.error = message
        self.line_scope = {}
        self.line_scope_loaded_for = ""
        self.selected_plant = "all"
        self.selected_line = "all"
