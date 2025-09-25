# mindtrace/ui/mindtrace/ui/playground/storybook.py
import reflex as rx

from mindtrace.ui.playground.stories_registry import (
    STORY_ACCORDION,
    STORY_ALERT,
    STORY_BREADCRUMBS,
    STORY_EMPTY,
    STORY_MULTISELECT,
    STORY_PAGER,
    STORY_PILLTABS,
    STORY_SEARCH,
    STORY_STATGRID,
    STORY_TAG,
    STORY_UPLOAD,
)

_SIDEBAR = [
    {"id": STORY_BREADCRUMBS["id"], "name": STORY_BREADCRUMBS["name"]},
    {"id": STORY_STATGRID["id"], "name": STORY_STATGRID["name"]},
    {"id": STORY_ALERT["id"], "name": STORY_ALERT["name"]},
    {"id": STORY_PILLTABS["id"], "name": STORY_PILLTABS["name"]},
    {"id": STORY_ACCORDION["id"], "name": STORY_ACCORDION["name"]},
    {"id": STORY_TAG["id"], "name": STORY_TAG["name"]},
    {"id": STORY_MULTISELECT["id"], "name": STORY_MULTISELECT["name"]},
    {"id": STORY_SEARCH["id"], "name": STORY_SEARCH["name"]},
    {"id": STORY_UPLOAD["id"], "name": STORY_UPLOAD["name"]},
    {"id": STORY_EMPTY["id"], "name": STORY_EMPTY["name"]},
    {"id": STORY_PAGER["id"], "name": STORY_PAGER["name"]},
]

ID_BC = STORY_BREADCRUMBS["id"]
ID_SG = STORY_STATGRID["id"]
ID_AL = STORY_ALERT["id"]
ID_PT = STORY_PILLTABS["id"]
ID_AC = STORY_ACCORDION["id"]
ID_TI = STORY_TAG["id"]
ID_MS = STORY_MULTISELECT["id"]
ID_SB = STORY_SEARCH["id"]
ID_UP = STORY_UPLOAD["id"]
ID_ET = STORY_EMPTY["id"]
ID_PG = STORY_PAGER["id"]


class StoryState(rx.State):
    story_id: str = _SIDEBAR[0]["id"]

    def select(self, sid: str):
        self.story_id = sid


def _sidebar_item(item):
    is_active = item["id"] == StoryState.story_id
    return rx.box(
        rx.hstack(
            rx.text(
                item["name"],
                weight="medium",
                color=rx.cond(is_active, "#0f172a", "#334155"),
            ),
            align="center",
            padding="8px 10px",
        ),
        background=rx.cond(is_active, "#eef2ff", "transparent"),
        border_radius="8px",
        cursor="pointer",
        on_click=lambda _id=item["id"]: StoryState.select(_id),
    )


def _sidebar():
    return rx.box(
        rx.vstack(
            rx.hstack(rx.text("Components", weight="bold"), align="center", padding="6px 8px"),
            rx.vstack(
                *[_sidebar_item(it) for it in _SIDEBAR],
                spacing="1",
            ),
            spacing="2",
            width="100%",
        ),
        position="sticky",
        top="0",
        padding="0.75rem",
        border_right="1px solid #e2e8f0",
        min_width="240px",
        height="100%",
    )


def _pick_preview():
    return rx.cond(
        StoryState.story_id == ID_BC,
        STORY_BREADCRUMBS["preview"](),
        rx.cond(
            StoryState.story_id == ID_SG,
            STORY_STATGRID["preview"](),
            rx.cond(
                StoryState.story_id == ID_AL,
                STORY_ALERT["preview"](),
                rx.cond(
                    StoryState.story_id == ID_PT,
                    STORY_PILLTABS["preview"](),
                    rx.cond(
                        StoryState.story_id == ID_AC,
                        STORY_ACCORDION["preview"](),
                        rx.cond(
                            StoryState.story_id == ID_TI,
                            STORY_TAG["preview"](),
                            rx.cond(
                                StoryState.story_id == ID_MS,
                                STORY_MULTISELECT["preview"](),
                                rx.cond(
                                    StoryState.story_id == ID_SB,
                                    STORY_SEARCH["preview"](),
                                    rx.cond(
                                        StoryState.story_id == ID_UP,
                                        STORY_UPLOAD["preview"](),
                                        rx.cond(
                                            StoryState.story_id == ID_ET,
                                            STORY_EMPTY["preview"](),
                                            STORY_PAGER["preview"](),
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )


def _pick_controls():
    return rx.cond(
        StoryState.story_id == ID_BC,
        STORY_BREADCRUMBS["controls"](),
        rx.cond(
            StoryState.story_id == ID_SG,
            STORY_STATGRID["controls"](),
            rx.cond(
                StoryState.story_id == ID_AL,
                STORY_ALERT["controls"](),
                rx.cond(
                    StoryState.story_id == ID_PT,
                    STORY_PILLTABS["controls"](),
                    rx.cond(
                        StoryState.story_id == ID_AC,
                        STORY_ACCORDION["controls"](),
                        rx.cond(
                            StoryState.story_id == ID_TI,
                            STORY_TAG["controls"](),
                            rx.cond(
                                StoryState.story_id == ID_MS,
                                STORY_MULTISELECT["controls"](),
                                rx.cond(
                                    StoryState.story_id == ID_SB,
                                    STORY_SEARCH["controls"](),
                                    rx.cond(
                                        StoryState.story_id == ID_UP,
                                        STORY_UPLOAD["controls"](),
                                        rx.cond(
                                            StoryState.story_id == ID_ET,
                                            STORY_EMPTY["controls"](),
                                            STORY_PAGER["controls"](),
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )


def _code_body(code_or_component):
    """Return a component suitable for the code panel.
    - If a plain string is provided, render a code block.
    - If a Reflex component is provided, render it directly.
    """
    try:
        # Reflex components inherit from Component.
        if isinstance(code_or_component, rx.Component):
            return code_or_component
    except Exception:
        # If isinstance check fails for some reason, fall back to str.
        pass
    return rx.code_block(str(code_or_component), language="python", show_line_numbers=False)


def _code_box(title: str, code_or_component):
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.text(f"Code – {title}", weight="bold"),
                rx.spacer(),
                rx.icon_button(rx.icon(tag="copy"), variant="ghost", title="Copy"),
                align="center",
            ),
            rx.box(
                _code_body(code_or_component),
                padding="0.75rem",
                background="#0b1020",
                color="#e2e8f0",
                border_radius="10px",
                width="100%",
            ),
            spacing="2",
            width="100%",
        ),
        width="100%",
    )


def _pick_code():
    # Each branch calls the story's code() and hands the result (string OR component) to _code_box.
    return rx.cond(
        StoryState.story_id == ID_BC,
        _code_box("Breadcrumbs", STORY_BREADCRUMBS["code"]()),
        rx.cond(
            StoryState.story_id == ID_SG,
            _code_box("Stat Grid", STORY_STATGRID["code"]()),
            rx.cond(
                StoryState.story_id == ID_AL,
                _code_box("Inline Alert", STORY_ALERT["code"]()),
                rx.cond(
                    StoryState.story_id == ID_PT,
                    _code_box("Pill Tabs", STORY_PILLTABS["code"]()),
                    rx.cond(
                        StoryState.story_id == ID_AC,
                        _code_box("Accordion", STORY_ACCORDION["code"]()),
                        rx.cond(
                            StoryState.story_id == ID_TI,
                            _code_box("Tag Input", STORY_TAG["code"]()),
                            rx.cond(
                                StoryState.story_id == ID_MS,
                                _code_box("Multi Select", STORY_MULTISELECT["code"]()),
                                rx.cond(
                                    StoryState.story_id == ID_SB,
                                    _code_box("Search Box", STORY_SEARCH["code"]()),
                                    rx.cond(
                                        StoryState.story_id == ID_UP,
                                        _code_box("File Uploader", STORY_UPLOAD["code"]()),
                                        rx.cond(
                                            StoryState.story_id == ID_ET,
                                            _code_box("Empty Table", STORY_EMPTY["code"]()),
                                            _code_box("Pagination", STORY_PAGER["code"]()),
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )


def _preview_panel():
    return rx.box(
        rx.box(
            _pick_preview(),
            padding="1rem",
            background="#ffffff",
            border="1px solid #e2e8f0",
            border_radius="12px",
            width="100%",
        ),
        padding="1rem",
        width="100%",
        max_width="900px",
        margin="0 auto",
    )


def _controls_panel():
    return rx.card(
        rx.vstack(
            rx.text("Controls", weight="bold"),
            _pick_controls(),
            spacing="2",
            width="100%",
        ),
    )


def storybook_page() -> rx.Component:
    return rx.hstack(
        _sidebar(),
        rx.box(
            rx.vstack(
                _preview_panel(),
                _controls_panel(),
                _pick_code(),
                spacing="4",
                width="100%",
            ),
            padding="1rem",
            width="100%",
        ),
        align="start",
        width="100%",
        spacing="0",
    )
