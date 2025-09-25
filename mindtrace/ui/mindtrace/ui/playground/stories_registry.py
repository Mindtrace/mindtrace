import json

import reflex as rx

from mindtrace.ui.components.core.button import button
from mindtrace.ui.components.data.checklist import checklist
from mindtrace.ui.components.data.stat_cards import stat_grid
from mindtrace.ui.components.empty.empty_table import empty_table
from mindtrace.ui.components.feedback.inline_alert import inline_alert
from mindtrace.ui.components.inputs.file_upload import file_uploader
from mindtrace.ui.components.inputs.multi_select import multi_select
from mindtrace.ui.components.inputs.search_box import search_box
from mindtrace.ui.components.inputs.tag_input import tag_input

# === Import your modular components ===
from mindtrace.ui.components.layout.accordion import accordion
from mindtrace.ui.components.navigation.breadcrumbs import breadcrumbs
from mindtrace.ui.components.navigation.pagination import pagination
from mindtrace.ui.components.navigation.tabs_pills import pill_tabs

# ========== SHARED UI HELPERS (pure components) ==========


def _prop_input_text(label: str, value, on_change):
    return rx.vstack(
        rx.text(label, size="2", color="#64748b"),
        rx.input(value=value, on_change=on_change),
        spacing="1",
        width="100%",
    )


def _prop_textarea(label: str, value, on_change, rows: int = 6):
    return rx.vstack(
        rx.text(label, size="2", color="#64748b"),
        rx.text_area(value=value, rows=str(rows), on_change=on_change),
        spacing="1",
        width="100%",
    )


def _prop_select(label: str, value, options: list[str], on_change):
    return rx.vstack(
        rx.text(label, size="2", color="#64748b"),
        rx.select(options, value=value, on_change=on_change),
        spacing="1",
        width="100%",
    )


def _prop_switch(label: str, checked: bool, on_change):
    return rx.hstack(
        rx.switch(checked=checked, on_change=on_change),
        rx.text(label, size="2", color="#64748b"),
        spacing="2",
        align="center",
        width="100%",
    )


def _code_panel(title: str, code_text):
    """Render the code block. `code_text` is a str State field so it updates live."""
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.text(title, weight="bold"),
                rx.spacer(),
                rx.icon_button(rx.icon(tag="copy"), variant="ghost", title="Copy"),
                align="center",
            ),
            rx.box(
                rx.code_block(code_text, language="python", show_line_numbers=False),
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


# ========= PER-STORY STATE (each stores a live code_text) =========


class BreadcrumbsState(rx.State):
    items_json: str = '[{"label":"Home","href":"/"}, {"label":"Admin","href":"/admin"}, {"label":"Users"}]'
    code_text: str = """import reflex as rx
from mindtrace.ui.components.navigation.breadcrumbs import breadcrumbs

def demo():
    items = [
        {"label": "Home", "href": "/"},
        {"label": "Admin", "href": "/admin"},
        {"label": "Users", "is_last": True},
    ]
    return breadcrumbs(items)
"""

    def _sync_code(self):
        # Best effort: try to build code from items_json; fallback to a minimal version.
        try:
            items = json.loads(self.items_json)
            # flag the last item
            out = []
            for i, it in enumerate(items):
                o = {"label": it.get("label", "")}
                if it.get("href"):
                    o["href"] = it["href"]
                if i == len(items) - 1:
                    o["is_last"] = True
                out.append(o)
            body = ",\n        ".join("{" + ", ".join(f"{k!r}: {v!r}" for k, v in o.items()) + "}" for o in out)
        except Exception:
            body = """{"label": "Home", "href": "/"},
        {"label": "Admin", "href": "/admin"},
        {"label": "Users", "is_last": True}"""
        self.code_text = f"""import reflex as rx
from mindtrace.ui.components.navigation.breadcrumbs import breadcrumbs

def demo():
    items = [
        {body}
    ]
    return breadcrumbs(items)
"""

    def set_items_json(self, v: str):
        self.items_json = v
        self._sync_code()

    @rx.var
    def items(self) -> list[dict]:
        try:
            data = json.loads(self.items_json)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    @rx.var
    def items_flagged(self) -> list[dict]:
        out = []
        n = len(self.items)
        for i, it in enumerate(self.items):
            out.append(
                {
                    "label": it.get("label", ""),
                    "href": it.get("href", "") or "",
                    "is_last": (i == n - 1),
                }
            )
        return out


class StatGridState(rx.State):
    cards_json: str = (
        '[{"title":"Users","value":"1,234","subtitle":"+4% WoW","icon":"👥"},'
        ' {"title":"Revenue","value":"$12,450","subtitle":"+8%","icon":"💸"},'
        ' {"title":"Errors","value":"3","subtitle":"today","icon":"⚠️"}]'
    )
    code_text: str = """import reflex as rx
from mindtrace.ui.components.data.stat_cards import stat_grid

def demo():
    cards = [
        {"title": "Users", "value": "1,234", "subtitle": "+4% WoW", "icon": "👥"},
        {"title": "Revenue", "value": "$12,450", "subtitle": "+8%", "icon": "💸"},
        {"title": "Errors", "value": "3", "subtitle": "today", "icon": "⚠️"},
    ]
    return stat_grid(cards)
"""

    def _sync_code(self):
        try:
            cards = json.loads(self.cards_json)
            body = ",\n        ".join("{" + ", ".join(f"{k!r}: {v!r}" for k, v in c.items()) + "}" for c in cards)
        except Exception:
            body = """{"title": "Users", "value": "1,234", "subtitle": "+4% WoW", "icon": "👥"}"""
        self.code_text = f"""import reflex as rx
from mindtrace.ui.components.data.stat_cards import stat_grid

def demo():
    cards = [
        {body}
    ]
    return stat_grid(cards)
"""

    def set_cards_json(self, v: str):
        self.cards_json = v
        self._sync_code()

    @rx.var
    def cards(self) -> list[dict]:
        try:
            data = json.loads(self.cards_json)
            return data if isinstance(data, list) else []
        except Exception:
            return []


class InlineAlertState(rx.State):
    message: str = "Heads up: something changed."
    variant: str = "warning"  # info | success | warning | error
    dismissible: bool = True
    code_text: str = """import reflex as rx
from mindtrace.ui.components.feedback.inline_alert import inline_alert

def demo():
    return inline_alert(
        message="Heads up: something changed.",
        variant="warning",
        dismissible=True,
        cid="demo",
    )
"""

    def _sync_code(self):
        self.code_text = f"""import reflex as rx
from mindtrace.ui.components.feedback.inline_alert import inline_alert

def demo():
    return inline_alert(
        message={self.message!r},
        variant={self.variant!r},
        dismissible={self.dismissible},
        cid="demo",
    )
"""

    def set_message(self, v: str):
        self.message = v
        self._sync_code()

    def set_variant(self, v: str):
        self.variant = v
        self._sync_code()

    def toggle_dismissible(self):
        self.dismissible = not self.dismissible
        self._sync_code()


class AccordionState(rx.State):
    single: bool = False
    code_text: str = """import reflex as rx
from mindtrace.ui.components.layout.accordion import accordion

def demo():
    items = [
        {"key":"a","title":"Section A","content":rx.text("Hello A")},
        {"key":"b","title":"Section B","content":rx.text("Hello B")},
        {"key":"c","title":"Section C","content":rx.text("Hello C")},
    ]
    return accordion(items, cid="acc1", single=False)
"""

    def _sync_code(self):
        self.code_text = f"""import reflex as rx
from mindtrace.ui.components.layout.accordion import accordion

def demo():
    items = [
        {{"key":"a","title":"Section A","content":rx.text("Hello A")}},
        {{"key":"b","title":"Section B","content":rx.text("Hello B")}},
        {{"key":"c","title":"Section C","content":rx.text("Hello C")}},
    ]
    return accordion(items, cid="acc1", single={self.single})
"""

    def toggle_single(self):
        self.single = not self.single
        self._sync_code()


class PaginationState(rx.State):
    total_pages: int = 17
    code_text: str = """import reflex as rx
from mindtrace.ui.components.navigation.pagination import pagination

def demo():
    return pagination(17, cid="pg1")
"""

    def _sync_code(self):
        self.code_text = f"""import reflex as rx
from mindtrace.ui.components.navigation.pagination import pagination

def demo():
    return pagination({int(self.total_pages)}, cid="pg1")
"""

    def set_total_pages(self, v: str):
        try:
            n = int(v)
        except Exception:
            n = 1
        self.total_pages = max(1, n)
        self._sync_code()


# NEW: Button story state
class ButtonState(rx.State):
    label: str = "Click Me"
    variant: str = "primary"  # primary | secondary | ghost | danger | outline
    size: str = "md"  # xs | sm | md | lg
    disabled: bool = False
    loading: bool = False
    full_width: bool = False
    code_text: str = """import reflex as rx
from mindtrace.ui.components.core.button import button

def demo():
    return button("Click Me", variant="primary", size="md")
"""

    def _sync_code(self):
        self.code_text = f"""import reflex as rx
from mindtrace.ui.components.core.button import button

def demo():
    return button(
        {self.label!r},
        variant={self.variant!r},
        size={self.size!r},
        disabled={self.disabled},
        loading={self.loading},
        full_width={self.full_width},
    )
"""

    def set_label(self, v: str):
        self.label = v
        self._sync_code()

    def set_variant(self, v: str):
        self.variant = v
        self._sync_code()

    def set_size(self, v: str):
        self.size = v
        self._sync_code()

    def toggle_disabled(self):
        self.disabled = not self.disabled
        self._sync_code()

    def toggle_loading(self):
        self.loading = not self.loading
        self._sync_code()

    def toggle_full_width(self):
        self.full_width = not self.full_width
        self._sync_code()


# NEW: Checklist story state
class ChecklistState(rx.State):
    items_json: str = (
        '[{"id":"1","label":"Email backend wired"}, {"id":"2","label":"CI passing"}, {"id":"3","label":"Docs updated"}]'
    )
    checked_ids: set[str] = set()
    code_text: str = """import reflex as rx
from mindtrace.ui.components.data.checklist import checklist

def demo():
    items = [
        {"id": "1", "label": "Email backend wired"},
        {"id": "2", "label": "CI passing"},
        {"id": "3", "label": "Docs updated"},
    ]
    return checklist(items, checked={"2"})
"""

    def _parsed_items(self) -> list[dict]:
        try:
            data = json.loads(self.items_json)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _sync_code(self):
        items = self._parsed_items()
        items_body = (
            ",\n        ".join("{" + ", ".join(f"{k!r}: {v!r}" for k, v in it.items()) + "}" for it in items)
            or """{"id":"1","label":"Example"}"""
        )
        checked_body = "{" + ", ".join(repr(x) for x in sorted(self.checked_ids)) + "}"
        self.code_text = f"""import reflex as rx
from mindtrace.ui.components.data.checklist import checklist

def demo():
    items = [
        {items_body}
    ]
    return checklist(items, checked={checked_body})
"""

    def set_items_json(self, v: str):
        self.items_json = v
        self._sync_code()

    def toggle(self, item_id: str):
        s = set(self.checked_ids)
        if item_id in s:
            s.remove(item_id)
        else:
            s.add(item_id)
        self.checked_ids = s
        self._sync_code()

    @rx.var
    def items(self) -> list[dict]:
        return self._parsed_items()


# NEW: Simple Table story (using built-in rx.table primitives)
class TableState(rx.State):
    rows_json: str = '[{"name":"Alice","role":"Admin","active":true}, {"name":"Bob","role":"Editor","active":false}]'
    code_text: str = """import reflex as rx

def demo():
    rows = [
        {"name":"Alice","role":"Admin","active":True},
        {"name":"Bob","role":"Editor","active":False},
    ]
    return rx.table.root(
        rx.table.header(
            rx.table.row(
                rx.table.column_header_cell("Name"),
                rx.table.column_header_cell("Role"),
                rx.table.column_header_cell("Active"),
            )
        ),
        rx.table.body(
            *[
                rx.table.row(
                    rx.table.cell(r["name"]),
                    rx.table.cell(r["role"]),
                    rx.table.cell("Yes" if r["active"] else "No"),
                ) for r in rows
            ]
        ),
        width="100%",
    )
"""

    def _parsed_rows(self):
        try:
            data = json.loads(self.rows_json)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _sync_code(self):
        rows = self._parsed_rows()
        body = (
            ",\n        ".join("{" + ", ".join(f"{k!r}: {v!r}" for k, v in r.items()) + "}" for r in rows)
            or """{"name":"Alice","role":"Admin","active":True}"""
        )
        self.code_text = f"""import reflex as rx

def demo():
    rows = [
        {body}
    ]
    return rx.table.root(
        rx.table.header(
            rx.table.row(
                rx.table.column_header_cell("Name"),
                rx.table.column_header_cell("Role"),
                rx.table.column_header_cell("Active"),
            )
        ),
        rx.table.body(
            *[
                rx.table.row(
                    rx.table.cell(r["name"]),
                    rx.table.cell(r["role"]),
                    rx.table.cell("Yes" if r["active"] else "No"),
                ) for r in rows
            ]
        ),
        width="100%",
    )
"""

    def set_rows_json(self, v: str):
        self.rows_json = v
        self._sync_code()

    @rx.var
    def rows(self) -> list[dict]:
        return self._parsed_rows()


# ========== STORIES (stateful previews + controls + code panel) ==========


# Breadcrumbs
def story_breadcrumbs_preview() -> rx.Component:
    return rx.center(
        breadcrumbs(BreadcrumbsState.items_flagged),
        padding="2rem",
        width="100%",
    )


def story_breadcrumbs_controls() -> rx.Component:
    return rx.vstack(
        _prop_textarea("items_json", BreadcrumbsState.items_json, BreadcrumbsState.set_items_json, rows=8),
        rx.text(
            "Tip: each item may have 'label' and optional 'href'. The last item is inferred in state.",
            size="1",
            color="#94a3b8",
        ),
        spacing="2",
        width="100%",
    )


STORY_BREADCRUMBS = {
    "id": "breadcrumbs",
    "name": "Breadcrumbs",
    "preview": story_breadcrumbs_preview,
    "controls": story_breadcrumbs_controls,
    "code": lambda: _code_panel("Breadcrumbs", BreadcrumbsState.code_text),
}


# Stat Grid
def story_statgrid_preview() -> rx.Component:
    return rx.box(stat_grid(StatGridState.cards), width="100%")


def story_statgrid_controls() -> rx.Component:
    return rx.vstack(
        _prop_textarea("cards_json", StatGridState.cards_json, StatGridState.set_cards_json, rows=8),
        rx.text('Example: [{"title":"Users","value":"1,234","subtitle":"+4%","icon":"👥"}]', size="1", color="#94a3b8"),
        spacing="2",
        width="100%",
    )


STORY_STATGRID = {
    "id": "stat_grid",
    "name": "Stat Grid",
    "preview": story_statgrid_preview,
    "controls": story_statgrid_controls,
    "code": lambda: _code_panel("Stat Grid", StatGridState.code_text),
}


# Inline Alert
def story_alert_preview() -> rx.Component:
    return rx.box(
        inline_alert(InlineAlertState.message, InlineAlertState.variant, InlineAlertState.dismissible, "al-demo"),
        width="100%",
    )


def story_alert_controls() -> rx.Component:
    return rx.vstack(
        _prop_input_text("message", InlineAlertState.message, InlineAlertState.set_message),
        _prop_select(
            "variant", InlineAlertState.variant, ["info", "success", "warning", "error"], InlineAlertState.set_variant
        ),
        _prop_switch("dismissible", InlineAlertState.dismissible, InlineAlertState.toggle_dismissible),
        spacing="2",
        width="100%",
    )


STORY_ALERT = {
    "id": "inline_alert",
    "name": "Inline Alert",
    "preview": story_alert_preview,
    "controls": story_alert_controls,
    "code": lambda: _code_panel("Inline Alert", InlineAlertState.code_text),
}


# Pill Tabs (static demo)
def story_pilltabs_preview() -> rx.Component:
    tabs = [
        {"label": "Active", "value": "active", "badge": 5, "content": rx.text("Active content")},
        {"label": "Completed", "value": "completed", "badge": 12, "content": rx.text("Completed content")},
        {"label": "Archived", "value": "archived", "content": rx.text("Archived content")},
    ]
    return rx.box(pill_tabs(tabs, "pt1"), width="100%")


def story_pilltabs_controls() -> rx.Component:
    return rx.text("No controls for this story (add state if needed).")


STORY_PILLTABS = {
    "id": "pill_tabs",
    "name": "Pill Tabs",
    "preview": story_pilltabs_preview,
    "controls": story_pilltabs_controls,
    "code": lambda: _code_panel(
        "Pill Tabs",
        """import reflex as rx
from mindtrace.ui.components.navigation.tabs_pills import pill_tabs

def demo():
    tabs = [
        {"label":"Active","value":"active","badge":5,"content": rx.text("Active content")},
        {"label":"Completed","value":"completed","badge":12,"content": rx.text("Completed content")},
        {"label":"Archived","value":"archived","content": rx.text("Archived content")},
    ]
    return pill_tabs(tabs, cid="pt1")
""",
    ),
}


# Accordion
def story_accordion_preview() -> rx.Component:
    items = [
        {"key": "a", "title": "Section A", "content": rx.text("Hello A")},
        {"key": "b", "title": "Section B", "content": rx.text("Hello B")},
        {"key": "c", "title": "Section C", "content": rx.text("Hello C")},
    ]
    return rx.box(accordion(items, "acc1", AccordionState.single), width="100%")


def story_accordion_controls() -> rx.Component:
    return rx.vstack(_prop_switch("single", AccordionState.single, AccordionState.toggle_single), width="100%")


STORY_ACCORDION = {
    "id": "accordion",
    "name": "Accordion",
    "preview": story_accordion_preview,
    "controls": story_accordion_controls,
    "code": lambda: _code_panel("Accordion", AccordionState.code_text),
}


# Tag Input (no controls)
def story_tag_preview() -> rx.Component:
    return rx.box(tag_input("tags1"), width="100%")


def story_tag_controls() -> rx.Component:
    return rx.text("Type and press Enter to add tags.")


STORY_TAG = {
    "id": "tag_input",
    "name": "Tag Input",
    "preview": story_tag_preview,
    "controls": story_tag_controls,
    "code": lambda: _code_panel(
        "Tag Input",
        """import reflex as rx
from mindtrace.ui.components.inputs.tag_input import tag_input

def demo():
    return tag_input(cid="tags1")
""",
    ),
}


# Multi Select (no controls)
def story_ms_preview() -> rx.Component:
    options = ["Alpha", "Beta", "Gamma", "Delta"]
    return rx.box(multi_select(options, "ms1"), width="100%")


def story_ms_controls() -> rx.Component:
    return rx.text("Click items to select / unselect.")


STORY_MULTISELECT = {
    "id": "multi_select",
    "name": "Multi Select",
    "preview": story_ms_preview,
    "controls": story_ms_controls,
    "code": lambda: _code_panel(
        "Multi Select",
        """import reflex as rx
from mindtrace.ui.components.inputs.multi_select import multi_select

def demo():
    return multi_select(["Alpha","Beta","Gamma","Delta"], cid="ms1")
""",
    ),
}

# Story EmptyTableState


class EmptyTableState(rx.State):
    title: str = "No data"
    description: str = "There are no rows to display."
    action_label: str = "Create item"

    # live code snippet for the code panel
    code_text: str = """import reflex as rx
from mindtrace.ui.components.empty.empty_table import empty_table

def demo():
    return empty_table(
        title="No data",
        description="There are no rows to display.",
        action_label="Create item",
    )
"""

    def _sync_code(self):
        self.code_text = f"""import reflex as rx
from mindtrace.ui.components.empty.empty_table import empty_table

def demo():
    return empty_table(
        title={self.title!r},
        description={self.description!r},
        action_label={self.action_label!r},
    )
"""

    def set_title(self, v: str):
        self.title = v
        self._sync_code()

    def set_description(self, v: str):
        self.description = v
        self._sync_code()

    def set_action_label(self, v: str):
        self.action_label = v
        self._sync_code()


# Empty Table
def story_empty_preview() -> rx.Component:
    return rx.box(
        empty_table(EmptyTableState.title, EmptyTableState.description, EmptyTableState.action_label),
        width="100%",
    )


def story_empty_controls() -> rx.Component:
    return rx.vstack(
        _prop_input_text("title", EmptyTableState.title, EmptyTableState.set_title),
        _prop_input_text("description", EmptyTableState.description, EmptyTableState.set_description),
        _prop_input_text("action_label", EmptyTableState.action_label, EmptyTableState.set_action_label),
        spacing="2",
        width="100%",
    )


STORY_EMPTY = {
    "id": "empty_table",
    "name": "Empty Table",
    "preview": story_empty_preview,
    "controls": story_empty_controls,
    "code": lambda: _code_panel(
        "Empty Table",
        f"""import reflex as rx
from mindtrace.ui.components.empty.empty_table import empty_table

def demo():
    return empty_table(
        title={EmptyTableState.title!r},
        description={EmptyTableState.description!r},
        action_label={EmptyTableState.action_label!r},
    )
""",
    ),
}


# Search Box (no controls)
def story_search_preview() -> rx.Component:
    return rx.box(search_box("s1"), width="100%")


def story_search_controls() -> rx.Component:
    return rx.text("Press Enter to submit; click × to clear.")


STORY_SEARCH = {
    "id": "search_box",
    "name": "Search Box",
    "preview": story_search_preview,
    "controls": story_search_controls,
    "code": lambda: _code_panel(
        "Search Box",
        """import reflex as rx
from mindtrace.ui.components.inputs.search_box import search_box

def demo():
    return search_box(cid="s1")
""",
    ),
}


# File Uploader (no live controls in story)
def story_upload_preview() -> rx.Component:
    return rx.box(file_uploader("up1", ".png,.jpg,.pdf", True), width="100%")


def story_upload_controls() -> rx.Component:
    return rx.text("Drop or click; accepts .png/.jpg/.pdf in this demo.")


STORY_UPLOAD = {
    "id": "file_uploader",
    "name": "File Uploader",
    "preview": story_upload_preview,
    "controls": story_upload_controls,
    "code": lambda: _code_panel(
        "File Uploader",
        """import reflex as rx
from mindtrace.ui.components.inputs.file_upload import file_uploader

def demo():
    return file_uploader(cid="up1", accept=".png,.jpg,.pdf", multiple=True)
""",
    ),
}


# Pagination
def story_pager_preview() -> rx.Component:
    return rx.center(pagination(PaginationState.total_pages, "pg1"), padding="1rem", width="100%")


def story_pager_controls() -> rx.Component:
    return rx.vstack(
        _prop_input_text("total_pages", str(PaginationState.total_pages), PaginationState.set_total_pages),
        spacing="2",
        width="100%",
    )


STORY_PAGER = {
    "id": "pagination",
    "name": "Pagination",
    "preview": story_pager_preview,
    "controls": story_pager_controls,
    "code": lambda: _code_panel("Pagination", PaginationState.code_text),
}


# NEW: Button
def story_button_preview() -> rx.Component:
    return rx.center(
        button(
            ButtonState.label,
            variant=ButtonState.variant,
            size=ButtonState.size,
            disabled=ButtonState.disabled,
            loading=ButtonState.loading,
            full_width=ButtonState.full_width,
        ),
        padding="1rem",
        width="100%",
    )


def story_button_controls() -> rx.Component:
    return rx.vstack(
        _prop_input_text("label", ButtonState.label, ButtonState.set_label),
        _prop_select(
            "variant",
            ButtonState.variant,
            ["primary", "secondary", "ghost", "danger", "outline"],
            ButtonState.set_variant,
        ),
        _prop_select("size", ButtonState.size, ["xs", "sm", "md", "lg"], ButtonState.set_size),
        _prop_switch("disabled", ButtonState.disabled, ButtonState.toggle_disabled),
        _prop_switch("loading", ButtonState.loading, ButtonState.toggle_loading),
        _prop_switch("full_width", ButtonState.full_width, ButtonState.toggle_full_width),
        spacing="2",
        width="100%",
    )


STORY_BUTTON = {
    "id": "button",
    "name": "Button",
    "preview": story_button_preview,
    "controls": story_button_controls,
    "code": lambda: _code_panel("Button", ButtonState.code_text),
}


# NEW: Checklist
def story_checklist_preview() -> rx.Component:
    # checklist component should accept `on_toggle` callback if you have that;
    # If your checklist returns clickable rows, wire it up accordingly.
    # Here we render a custom list with toggles using your checklist component API.
    items = ChecklistState.items  # Var list[dict]
    return rx.box(
        checklist(items, checked=ChecklistState.checked_ids, on_toggle=lambda i: ChecklistState.toggle(i)),
        width="100%",
    )


def story_checklist_controls() -> rx.Component:
    return rx.vstack(
        _prop_textarea("items_json", ChecklistState.items_json, ChecklistState.set_items_json, rows=8),
        rx.text('Item format: [{"id":"1","label":"…"}, …]. Click to toggle.', size="1", color="#94a3b8"),
        spacing="2",
        width="100%",
    )


STORY_CHECKLIST = {
    "id": "checklist",
    "name": "Checklist",
    "preview": story_checklist_preview,
    "controls": story_checklist_controls,
    "code": lambda: _code_panel("Checklist", ChecklistState.code_text),
}


# NEW: Simple Table (built-in primitives)
def story_table_preview() -> rx.Component:
    rows = TableState.rows
    return rx.table.root(
        rx.table.header(
            rx.table.row(
                rx.table.column_header_cell("Name"),
                rx.table.column_header_cell("Role"),
                rx.table.column_header_cell("Active"),
            )
        ),
        rx.table.body(
            rx.foreach(
                rows,
                lambda r: rx.table.row(
                    rx.table.cell(r["name"]),
                    rx.table.cell(r["role"]),
                    rx.table.cell(rx.cond(r["active"], "Yes", "No")),
                ),
            )
        ),
        width="100%",
    )


def story_table_controls() -> rx.Component:
    return rx.vstack(
        _prop_textarea("rows_json", TableState.rows_json, TableState.set_rows_json, rows=8),
        rx.text('Row format: [{"name":"Alice","role":"Admin","active":true}, …]', size="1", color="#94a3b8"),
        spacing="2",
        width="100%",
    )


STORY_TABLE = {
    "id": "table",
    "name": "Table",
    "preview": story_table_preview,
    "controls": story_table_controls,
    "code": lambda: _code_panel("Table", TableState.code_text),
}


# Registry list (used only for sidebar labels / ids in storybook.py)
STORIES = [
    {
        "id": STORY_BUTTON["id"],
        "name": STORY_BUTTON["name"],
        "preview": STORY_BUTTON["preview"],
        "controls": STORY_BUTTON["controls"],
        "code": STORY_BUTTON["code"],
    },
    {
        "id": STORY_BREADCRUMBS["id"],
        "name": STORY_BREADCRUMBS["name"],
        "preview": STORY_BREADCRUMBS["preview"],
        "controls": STORY_BREADCRUMBS["controls"],
        "code": STORY_BREADCRUMBS["code"],
    },
    {
        "id": STORY_STATGRID["id"],
        "name": STORY_STATGRID["name"],
        "preview": STORY_STATGRID["preview"],
        "controls": STORY_STATGRID["controls"],
        "code": STORY_STATGRID["code"],
    },
    {
        "id": STORY_ALERT["id"],
        "name": STORY_ALERT["name"],
        "preview": STORY_ALERT["preview"],
        "controls": STORY_ALERT["controls"],
        "code": STORY_ALERT["code"],
    },
    {
        "id": STORY_PILLTABS["id"],
        "name": STORY_PILLTABS["name"],
        "preview": STORY_PILLTABS["preview"],
        "controls": STORY_PILLTABS["controls"],
        "code": STORY_PILLTABS["code"],
    },
    {
        "id": STORY_ACCORDION["id"],
        "name": STORY_ACCORDION["name"],
        "preview": STORY_ACCORDION["preview"],
        "controls": STORY_ACCORDION["controls"],
        "code": STORY_ACCORDION["code"],
    },
    {
        "id": STORY_TAG["id"],
        "name": STORY_TAG["name"],
        "preview": STORY_TAG["preview"],
        "controls": STORY_TAG["controls"],
        "code": STORY_TAG["code"],
    },
    {
        "id": STORY_MULTISELECT["id"],
        "name": STORY_MULTISELECT["name"],
        "preview": STORY_MULTISELECT["preview"],
        "controls": STORY_MULTISELECT["controls"],
        "code": STORY_MULTISELECT["code"],
    },
    {
        "id": STORY_SEARCH["id"],
        "name": STORY_SEARCH["name"],
        "preview": STORY_SEARCH["preview"],
        "controls": STORY_SEARCH["controls"],
        "code": STORY_SEARCH["code"],
    },
    {
        "id": STORY_UPLOAD["id"],
        "name": STORY_UPLOAD["name"],
        "preview": STORY_UPLOAD["preview"],
        "controls": STORY_UPLOAD["controls"],
        "code": STORY_UPLOAD["code"],
    },
    {
        "id": STORY_EMPTY["id"],
        "name": STORY_EMPTY["name"],
        "preview": STORY_EMPTY["preview"],
        "controls": STORY_EMPTY["controls"],
        "code": STORY_EMPTY["code"],
    },
    {
        "id": STORY_PAGER["id"],
        "name": STORY_PAGER["name"],
        "preview": STORY_PAGER["preview"],
        "controls": STORY_PAGER["controls"],
        "code": STORY_PAGER["code"],
    },
    {
        "id": STORY_TABLE["id"],
        "name": STORY_TABLE["name"],
        "preview": STORY_TABLE["preview"],
        "controls": STORY_TABLE["controls"],
        "code": STORY_TABLE["code"],
    },
]
