import reflex as rx
from poseidon.styles.global_styles import C, Ty,T
from poseidon.styles.variants import COMPONENT_VARIANTS
from poseidon.state.line_scope import ScopeState

def ScopeSelector():
    truncate = {
        "white_space": "nowrap",
        "overflow": "hidden",
        "text_overflow": "ellipsis",
    }
    trigger_base = {
        **COMPONENT_VARIANTS["select"]["base"],
        **COMPONENT_VARIANTS["select"]["compact"],
        "_focus": COMPONENT_VARIANTS["select"]["focus"],
        "_hover": COMPONENT_VARIANTS["select"]["hover"],
        **truncate,
    }
    plant_trigger_style = {**trigger_base, "width": "120px", "min_width": "120px"}
    line_trigger_style = {**trigger_base, "width": "150px", "min_width": "150px"}

    return rx.hstack(
        rx.select.root(
            rx.select.trigger(placeholder="Plant", style=plant_trigger_style),
            rx.select.content(
                rx.select.item("Plant: All", value="all",_hover={"background": T.ring, "color": T.accent}),
                rx.foreach(
                    ScopeState.plants, 
                    lambda item: rx.select.item(f"Plant: {item[1]}", value=item[0],_hover={"background": T.ring, "color": T.accent}),
                ),
            ),
            value=ScopeState.selected_plant,
            on_change=ScopeState.change_plant,
        ),
        rx.select.root(
            rx.select.trigger(placeholder="Line", style=line_trigger_style),
            rx.select.content(
                rx.select.item("Line: All", value="all",_hover={"background": T.ring, "color": T.accent}),
                rx.foreach(
                    ScopeState.lines_for_selected,
                    lambda item: rx.select.item(f"Line: {item[1]}", value=item[0],_hover={"background": T.ring, "color": T.accent}),
                ),
            ),
            value=ScopeState.selected_line,
            on_change=ScopeState.change_line,
        ),
        align="center",
        spacing="2",
    )
