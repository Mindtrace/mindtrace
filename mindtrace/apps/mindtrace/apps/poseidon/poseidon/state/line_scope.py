import time
import reflex as rx


class ScopeState(rx.State):
    # Directory
    plants: list[tuple[str, str]] = []  # [(plant_id, plant_name)]
    lines_by_plant: dict[str, list[tuple[str, str]]] = {}  # {plant_id: [(line_id, line_name)]}
    loading: bool = False
    error: str = ""
    _last_loaded: float = 0.0
    TTL_SECS: int = 1000

    # Optional persistence (used only when user manually picks; not required for links)
    last_plant: str = rx.LocalStorage(name="last_plant", sync=True)
    last_line: str = rx.LocalStorage(name="last_line", sync=True)

    # -------- fetch directory ----------
    @rx.event(background=True)
    async def ensure_directory(self, org_id: str, force: bool = False):
        if not org_id:
            return
        now = time.time()
        if not force and self.plants and (now - self._last_loaded) < self.TTL_SECS:
            return
        async with self:
            self.loading = True
            self.error = ""
        from poseidon.backend.database.repositories.project_repository import ProjectRepository

        try:
            projects = await ProjectRepository.get_by_organization(org_id)

            plant_id = org_id
            plants = [(plant_id, org_id)]
            lines = [(str(getattr(p, "id")), getattr(p, "name", None)) for p in projects]

            async with self:
                self.plants = plants
                self.lines_by_plant = {plant_id: lines}
                self._last_loaded = time.time()
                self.loading = False
        except Exception as e:
            async with self:
                self.error = str(e)
                self.loading = False

    # -------- current scope from URL ----------
    @rx.var
    def selected_plant(self) -> str:
        return self.plant_id if self.plant_id else "all"

    @rx.var
    def selected_line(self) -> str:
        return self.line_id if self.line_id else "all"

    @rx.var
    def lines_for_selected(self) -> list[tuple[str, str]]:
        return self.lines_by_plant.get(self.selected_plant, [])

    # -------- helpers to resolve sensible scope (used by sidebar hrefs) ----------
    @rx.var
    def first_plant(self) -> str:
        return self.plants[0][0] if self.plants else ""

    def _first_line(self, plant_id: str) -> str:
        arr = self.lines_by_plant.get(plant_id, [])
        return str(arr[0][0]) if arr else ""

    @rx.var
    def resolved_plant(self) -> str:
        if self.plant_id:
            return self.plant_id

        if self.last_plant and any(self.last_plant == p[0] for p in self.plants):
            return self.last_plant

        return self.first_plant

    @rx.var
    def resolved_line(self) -> str:
        # use URL if present; otherwise last line or first line of resolved plant
        if self.line_id:
            return self.line_id
        plant = self.resolved_plant
        valid_ids = {lid for lid, _ in self.lines_by_plant.get(plant, [])}

        if self.last_line and self.last_line in valid_ids:
            return self.last_line
        return self._first_line(plant)

    @rx.var
    def links_ready(self) -> bool:
        # Sidebar enables links once at least a plant is known
        return bool(self.resolved_plant and self.resolved_line)

    # -------- navigation helpers (user-triggered) ----------
    def _current_subroute(self) -> str:
        raw = (self.router.page.raw_path or "").split("?", 1)[0].strip("/")
        parts = raw.split("/")
        if len(parts) >= 5 and parts[0] == "plants" and parts[2] == "lines":
            return "/".join(parts[4:])
        return ""

    def _goto(self, plant_id: str, line_id: str):
        sub = self._current_subroute() or "line-insights"
        return rx.redirect(f"/plants/{plant_id}/lines/{line_id}/{sub}")

    def change_plant(self, plant_id: str):
        if not plant_id:
            return None
        lines = self.lines_by_plant.get(plant_id, [])
        if not lines:
            return rx.redirect(f"/plants/{plant_id}/overview")
        self.last_plant = plant_id
        target_line = self.last_line if any(lid == self.last_line for lid, _ in lines) else lines[0][0]
        return self._goto(plant_id, target_line)

    def change_line(self, line_id: str):
        if not line_id:
            return None
        plant = self.resolved_plant
        if not plant:
            return None
        self.last_line = line_id
        return self._goto(plant, line_id)
