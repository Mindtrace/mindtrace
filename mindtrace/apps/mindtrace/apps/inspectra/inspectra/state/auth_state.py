import reflex as rx
from inspectra.state.base_state import BaseState
from inspectra.models.user_model import get_user_by_username
from inspectra.utils.security import verify_password


class AuthState(BaseState):
    """Authentication state."""

    logged_in: bool = False
    username: str = ""
    error: str = ""

    async def login(self, form_data: dict):
        username = form_data.get("username", "").strip()
        password = form_data.get("password", "").strip()

        user = get_user_by_username(username)
        if not user:
            self.error = "User not found."
            return

        if not verify_password(password, user.password):
            self.error = "Invalid credentials."
            return

        self.logged_in = True
        self.username = username
        self.error = ""
        await self.redirect("/")

    async def logout(self):
        self.logged_in = False
        self.username = ""
        await self.redirect("/login")
