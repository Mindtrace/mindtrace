# scope_state.py
import time
import reflex as rx


class ScopeState(rx.State):
    plants: list[tuple[str, str]] = []
    lines_by_plant: dict[str, list[tuple[str, str]]] = {}
    loading: bool = False
    error: str = ""
    _last_loaded: float = 0.0
    TTL_SECS: int = 1000

    # Optional persistence
    last_plant: str = rx.LocalStorage(name="last_plant", sync=True)
    last_line: str = rx.LocalStorage(name="last_line", sync=True)

    # ---------- fetch directory ----------
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
            plant_name = org_id

            plants = [(plant_id, plant_name)]
            lines = [(getattr(p, "id"), getattr(p, "name", str(getattr(p, "id")))) for p in projects]
            lines_map = {plant_id: lines}

            async with self:
                self.plants = plants
                self.lines_by_plant = lines_map
                self._last_loaded = time.time()
                self.loading = False
        except Exception as e:
            async with self:
                self.error = str(e)
                self.loading = False

    # ---------- current scope from URL ----------
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

    def _with_qs(self, dest: str) -> str:
        raw = self.router.page.raw_path or ""
        return dest + ("?" + raw.split("?", 1)[1] if "?" in raw else "")

    # ---------- changes (also persist) ----------
    def change_plant(self, plant_id: str):
        if plant_id != "all":
            self.last_plant = plant_id
            self.last_line = ""
        return (
            rx.redirect("/overview")
            if plant_id == "all"
            else rx.redirect(self._with_qs(f"/plants/{plant_id}/overview"))
        )

    def change_line(self, line_id: str):
        plant = self.selected_plant
        if plant == "all":
            return None
        if line_id == "all":
            return rx.redirect(self._with_qs(f"/plants/{plant}/overview"))
        self.last_line = line_id
        parts = (self.router.page.raw_path or "").split("?", 1)[0].strip("/").split("/")
        sub = "/".join(parts[4:]) or "predictions" if len(parts) >= 4 else "predictions"
        return rx.redirect(self._with_qs(f"/plants/{plant}/lines/{line_id}/{sub}"))

    # ---------- autoscope on mount ----------
    @rx.event
    def boot_autoscope(
        self,
        org_id: str | None,
        enable_autoscope: bool = False,
        prefer_last: bool = True,
        auto_pick_first: bool = True,
        default_subpage: str = "line-insights",
    ):
        print("boot_autoscope", org_id, enable_autoscope, prefer_last, auto_pick_first, default_subpage)
        if not enable_autoscope or not org_id:
            return

        # IMPORTANT: yield the CLASS event, not self.ensure_directory(...)
        yield ScopeState.ensure_directory(org_id)

        if self.plant_id and self.line_id:
            return

        plants = self.plants
        lines_by = self.lines_by_plant

        # last used
        lp = (self.last_plant or "").strip()
        ll = (self.last_line or "").strip()
        if prefer_last and lp and any(pid == lp for pid, _ in plants):
            if ll and any(lid == ll for lid, _ in lines_by.get(lp, [])):
                return rx.redirect(self._with_qs(f"/plants/{lp}/lines/{ll}/{default_subpage}"))
            return rx.redirect(self._with_qs(f"/plants/{lp}/overview"))

        # unique choice
        if len(plants) == 1:
            p = plants[0][0]
            ls = lines_by.get(p, [])
            if len(ls) == 1:
                l = ls[0][0]
                return rx.redirect(self._with_qs(f"/plants/{p}/lines/{l}/{default_subpage}"))
            return rx.redirect(self._with_qs(f"/plants/{p}/overview"))

        # optional first
        if auto_pick_first and plants:
            p0 = plants[0][0]
            ls = lines_by.get(p0, [])
            if ls:
                l0 = ls[0][0]
                return rx.redirect(self._with_qs(f"/plants/{p0}/lines/{l0}/{default_subpage}"))
            return rx.redirect(self._with_qs(f"/plants/{p0}/overview"))

        return
