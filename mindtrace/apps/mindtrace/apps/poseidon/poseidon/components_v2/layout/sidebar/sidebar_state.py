import reflex as rx

class SidebarState(rx.State):
    collapsed: bool = False
    def toggle(self): self.collapsed = not self.collapsed

