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
        parts = (self.router.page.raw_path or "").split("?", 1)[0].strip("/").split("/")
        return parts[1] if len(parts) >= 2 and parts[0] == "plants" else "all"

    @rx.var
    def selected_line(self) -> str:
        parts = (self.router.page.raw_path or "").split("?", 1)[0].strip("/").split("/")
        return parts[3] if len(parts) >= 4 and parts[0] == "plants" and parts[2] == "lines" else "all"

    @rx.var
    def lines_for_selected(self) -> list[tuple[str, str]]:
        return self.lines_by_plant.get(self.selected_plant, [])

    # -------- helpers to resolve sensible scope (used by sidebar hrefs) ----------
    @rx.var
    def first_plant(self) -> str:
        return self.plants[0][0] if self.plants else ""

    def _first_line(self, plant_id: str) -> str:
        if self.last_line:
            return self.last_line
        arr = self.lines_by_plant.get(plant_id, [])
        return str(arr[0][0]) if arr else ""

    @rx.var
    def resolved_plant(self) -> str:
        # use URL if present; otherwise first plant
        return self.selected_plant if self.selected_plant != "all" else self.first_plant

    @rx.var
    def resolved_line(self) -> str:
        # use URL if present; otherwise first line of resolved plant
        if self.selected_line != "all":
            return self.selected_line
        p = self.resolved_plant
        return self._first_line(p) if p else ""

    @rx.var
    def links_ready(self) -> bool:
        # Sidebar enables links once at least a plant is known
        return bool(self.resolved_plant)

    # -------- navigation helpers (user-triggered) ----------
    def _with_qs(self, dest: str) -> str:
        raw = self.router.page.raw_path or ""
        return dest + ("?" + raw.split("?", 1)[1] if "?" in raw else "")

    def change_plant(self, plant_id: str):
        # when user picks a plant, immediately pick its first line
        if plant_id == "all":
            return rx.redirect("/overview") # todo: change to index page
        self.last_plant, self.last_line = plant_id, ""
        l0 = self._first_line(plant_id)
        dest = f"/plants/{plant_id}/lines/{l0}/line-insights" if l0 else f"/plants/{plant_id}/overview"
        return rx.redirect(self._with_qs(dest))

    def change_line(self, line_id: str):
        plant = self.selected_plant if self.selected_plant != "all" else self.resolved_plant
        if not plant:
            return None
        if line_id == "all":
            l0 = self._first_line(plant)
            dest = f"/plants/{plant}/lines/{l0}/line-insights" if l0 else f"/plants/{plant}/overview"
            return rx.redirect(self._with_qs(dest))

        self.last_line = line_id
        parts = (self.router.page.raw_path or "").split("?", 1)[0].strip("/").split("/")
        sub = "/".join(parts[4:]) or "line-insights" if len(parts) >= 4 else "line-insights"
        return rx.redirect(self._with_qs(f"/plants/{plant}/lines/{line_id}/{sub}"))
