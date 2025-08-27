import reflex as rx

class SidebarState(rx.State):
    collapsed: bool = False

    # Last chosen scope (written by your ScopeState.change_*)
    last_plant: str = rx.LocalStorage(name="last_plant", sync=True)
    last_line:  str = rx.LocalStorage(name="last_line",  sync=True)

    @rx.var
    def plant_prefix(self) -> str:
        """Prefix for plant-scoped pages or fallback to overview."""
        p = self.plant_id or (self.last_plant or "")
        return f"/plants/{p}" if p else "/overview"

    @rx.var
    def line_prefix(self) -> str:
        """Prefix for line-scoped pages or fallback to plant overview/overview."""
        p = self.plant_id or (self.last_plant or "")
        l = self.line_id  or (self.last_line  or "")
        if p and l:
            return f"/plants/{p}/lines/{l}"
        return f"/plants/{p}/overview" if p else "/overview"

    def toggle(self):
        self.collapsed = not self.collapsed