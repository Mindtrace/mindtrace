# scope_state.py
import time
import reflex as rx

class ScopeState(rx.State):
    plants: list[tuple[str, str]] = []                      # [("p1","Plant 1"), ...]
    lines_by_plant: dict[str, list[tuple[str, str]]] = {}   # {"p1":[("l1","Line 1"), ...]}
    loading: bool = False
    error: str = ""
    _last_loaded: float = 0.0
    TTL_SECS: int = 1000

    @rx.event(background=True)
    async def ensure_directory(self, org_id: str, force: bool = False):
        now = time.time()
        if not force and self.plants and (now - self._last_loaded) < self.TTL_SECS:
            return
        async with self:
            self.loading = True
            self.error = ""

        from poseidon.backend.database.repositories.project_repository import ProjectRepository

        try:
            projects = await ProjectRepository.get_by_organization(org_id)

            # TODO: Create Plants, hardcoded as org for now. 
            plants: list[tuple[str, str]] = [("p1", "plant1")]
            lines_map: dict[str, list[tuple[str, str]]] = {}
            lines = []
            for p in projects:
                project_id = getattr(p, "id")
                project_name = getattr(p, "name", str(project_id))
                lines.append((project_id, project_name))
            lines_map = {"p1": lines}
                

            async with self:
                self.plants = plants
                self.lines_by_plant = lines_map
                self._last_loaded = time.time()
                self.loading = False

        except Exception as e:
            async with self:
                self.error = str(e)
                self.loading = False
    @rx.var
    def selected_plant(self) -> str:
        parts = (self.router.page.raw_path or "").split("?")[0].strip("/").split("/")
        return parts[1] if len(parts) >= 2 and parts[0] == "plants" else "all"

    @rx.var
    def selected_line(self) -> str:
        parts = (self.router.page.raw_path or "").split("?")[0].strip("/").split("/")
        return parts[3] if len(parts) >= 4 and parts[0] == "plants" and parts[2] == "lines" else "all"

    @rx.var
    def lines_for_selected(self) -> list[tuple[str, str]]:
        return self.lines_by_plant.get(self.selected_plant, [])

    def _with_qs(self, dest: str) -> str:
        raw = self.router.page.raw_path or ""
        return dest + ("?" + raw.split("?", 1)[1] if "?" in raw else "")

    def change_plant(self, plant_id: str):
        if plant_id == "all":
            return rx.redirect("/overview")
        return rx.redirect(self._with_qs(f"/plants/{plant_id}/overview"))

    def change_line(self, line_id: str):
        plant = self.selected_plant
        if plant == "all":
            return None
        if line_id == "all":
            return rx.redirect(self._with_qs(f"/plants/{plant}/overview"))
        parts = (self.router.page.raw_path or "").split("?")[0].strip("/").split("/")
        sub = "/".join(parts[4:]) or "predictions" if len(parts) >= 4 else "predictions"
        return rx.redirect(self._with_qs(f"/plants/{plant}/lines/{line_id}/{sub}"))
