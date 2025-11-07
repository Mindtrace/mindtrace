from inspectra.backend.db.repos.user import InvalidCredentialsError, UserNotFoundError
from inspectra.backend.services.auth_service import AuthService
from inspectra.state.base_state import BaseState


class AuthState(BaseState):
    """Authentication state."""

    logged_in: bool = False
    username: str = ""
    role: str = ""
    token: str = ""
    error: str = ""

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
        self.role = user.role
        self.token = token
        self.error = ""
        return self.redirect("/")

    async def logout(self):
        self.logged_in = False
        self.username = ""
        self.role = ""
        self.token = ""
        return self.redirect("/login")

    def _set_error(self, message: str):
        self.logged_in = False
        self.username = ""
        self.role = ""
        self.token = ""
        self.error = message
