# poseidon/pages/inspections_results.py
import reflex as rx
from typing import List, Dict, Union, Optional


class ResultsState(rx.State):
    """State for the Inspections Results page."""
    # Toolbar
    search: str = ""
    result_filter: str = "Defective"  # "All" | "Defective" | "Healthy"
    sort_desc: bool = True            # Created At sort

    # Table / paging
    page: int = 1
    page_size: int = 10
    expanded_serial: str = ""         # expanded row id (serial); "" = none

    # Dummy dataset (repeatable; realistic looking)
    rows: List[Dict[str, Union[str, int]]] = [
        {
            "serial": s,
            "part": f"Part {i % 5 + 1}",
            "created_at": t,
            "result": "Defective" if i % 3 in (0, 1) else "Healthy",  # ← use "Healthy"
        }
        for i, (s, t) in enumerate(
            [
                ("3c2d5b50fb054e2b_6f3dc0470f984bd8", "2025-09-09 23:32:05"),
                ("a9de83b461d64d19_e2576687ddef469a", "2025-09-09 23:13:17"),
                ("212476ac5898416e_2c3b8fff2b824a4b", "2025-09-09 23:06:27"),
                ("764e965ada464277_dcc7fe0a514e4416", "2025-09-09 22:48:23"),
                ("5df7ed0df384477d_7c170acd007646f8", "2025-09-09 21:53:59"),
                ("bb59ad280321473c_7bbe29de6a9c495b", "2025-09-09 18:53:09"),
                ("558aef3bd0ad450d_6217c9881e0b4041", "2025-09-09 18:04:24"),
                ("7a0878e84ce14c55_9bbc6aa39ae0d4c1f", "2025-09-09 16:34:37"),
                ("91fac9c6093f40ff_3acdc4afccb045f8", "2025-09-09 16:24:49"),
                ("3e0c6f7917794cc2_8be88fdbf40804e5", "2025-09-09 16:24:14"),
                # add a few more for paging demo
                ("2f0a8a7073b14dc1_71f0d6d9b1dce501", "2025-09-09 15:54:31"),
                ("e17a1c04e67d4b8b_4020d31f9d0a482a", "2025-09-09 15:33:05"),
                ("c9f7bdea101e41f6_a32b4a5e055f1a22", "2025-09-09 15:11:47"),
                ("3b1db5ee8b2a40f8_1ff92d8a0b6d332b", "2025-09-09 14:59:26"),
                ("b7b59f0dd6904d1a_724b6145c2d6a789", "2025-09-09 14:13:06"),
                ("84b9a14d33b1413f_96e221a0c3e4e010", "2025-09-09 13:42:17"),
                ("5a0c94f7f53a4a0b_f9d3c85c4b1a0e5d", "2025-09-09 13:11:50"),
                ("a4f536ba3e8e4a29_1a2233b4c5d6e7f8", "2025-09-09 12:45:03"),
                ("dcb7e2a90c224b5e_a9f8e7d6c5b4a321", "2025-09-09 12:11:11"),
                ("0a1b2c3d4e5f6789_abcdef0123456789", "2025-09-09 11:59:59"),
            ]
        )
    ]

    # ── Derived data ─────────────────────────────────────────
    @rx.var
    def filtered_rows(self) -> List[Dict[str, Union[str, int]]]:
        rows = self.rows
        if self.result_filter and self.result_filter != "All":
            rows = [r for r in rows if r["result"] == self.result_filter]
        q = self.search.strip().lower()
        if q:
            rows = [r for r in rows if q in str(r["serial"]).lower()]
        # sort by created_at (string timestamp works for ISO-like)
        rows = sorted(rows, key=lambda r: str(r["created_at"]), reverse=self.sort_desc)
        return rows

    @rx.var
    def total_results(self) -> int:
        return len(self.filtered_rows)

    @rx.var
    def total_pages(self) -> int:
        n = self.total_results
        return max(1, (n + self.page_size - 1) // self.page_size)

    @rx.var
    def page_rows(self) -> List[Dict[str, Union[str, int]]]:
        start = (self.page - 1) * self.page_size
        end = start + self.page_size
        return self.filtered_rows[start:end]

    # ── Events ───────────────────────────────────────────────
    def set_search(self, v: str):
        self.search = v
        self.page = 1

    def clear_search(self):
        self.search = ""
        self.page = 1

    def set_filter(self, v: Optional[str]):  # ← accept None safely
        self.result_filter = v or "All"
        self.page = 1

    def toggle_sort(self):
        self.sort_desc = not self.sort_desc

    def next_page(self):
        if self.page < self.total_pages:
            self.page += 1

    def prev_page(self):
        if self.page > 1:
            self.page -= 1

    def toggle_expand(self, serial: str):
        self.expanded_serial = "" if self.expanded_serial == serial else serial


# ── CSS ─────────────────────────────────────────────────────
def _css() -> rx.Component:
    return rx.html(
        """
        <style>
            .sr-title { font-size:1.5rem; font-weight:700; color:#0f172a; }
            .sr-subtitle { font-size:1rem; color:#475569; margin-bottom:6px; }
          .sr-shell { display:flex; justify-content:center; width:100%; min-height:100vh; background:#f8fafc; padding:24px; }
          .sr-page  { width:min(1180px, 100%); display:flex; flex-direction:column; gap:16px; }

          .sr-card { background:#fff; border:1px solid rgba(15,23,42,.08); border-radius:12px; box-shadow:0 2px 6px rgba(2,6,23,.05); }

          /* Toolbar */
          .sr-toolbar { padding:16px; display:grid; grid-template-columns: 1fr auto; gap:16px; align-items:center; }
          .sr-field  { display:flex; flex-direction:column; gap:6px; width:180px; }
          .sr-label  { color:#334155; font-weight:600; font-size:.9rem; }
          .sr-search { display:flex; gap:8px; align-items:center; }
          .sr-input  { width:360px; max-width:48vw; }
          .sr-clear  { border:1px solid rgba(15,23,42,.10); }

          /* Table */
          .sr-table { width:100%; }
          .sr-th, .sr-tr { display:grid; grid-template-columns: 2.2fr 1.6fr 1.4fr 1.1fr 48px; align-items:center; gap:12px; }
          .sr-th { padding:12px 16px; color:#475569; font-weight:700; }
          .sr-row { padding:14px 16px; border-top:1px solid rgba(15,23,42,.06); }
          .sr-serial { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color:#0f172a; }
          .sr-result-pill { width: 100px; padding:5px 10px; font-weight:500; font-size:.75rem; display:inline-block; text-align:center; border-radius:5px; }
          .pill-def { background:#fee2e2; color:#991b1b; }  /* defective */
          .pill-ok  { background:#d1fae5; color:#065f46; }  /* Healthy */

          .sr-subrow { background:#f9fafb; margin:8px 16px 0 16px; border:1px dashed rgba(15,23,42,.12); border-radius:8px; padding:10px 12px; color:#334155; }

          /* Pager */
          .sr-footer { display:flex; justify-content:space-between; align-items:center; padding:12px 16px; }
          .sr-page-chip { color:#475569; }
          .sr-nav { display:flex; gap:8px; }
          .sr-nav-btn { width:32px; height:32px; border-radius:8px; display:grid; place-items:center; border:1px solid rgba(15,23,42,.10); }
          .sr-nav-btn:disabled { opacity:.4; cursor:not-allowed; }

          /* Header: unify typography and alignment */
          .sr-th.sr-tr { justify-items: start; }
          .sr-th-txt    { font-size:.9rem; color:#475569; font-weight:700; }

          /* Sort "button" that looks like plain text */
          .sr-sort {
            background: transparent;
            border: none;
            padding: 0;
            margin: 0;
            box-shadow: none;
            color: #475569;
            font-weight: 700;
            font-size: .9rem;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            cursor: pointer;
          }
          .sr-sort:hover,
          .sr-sort:active,
          .sr-sort:focus { background: transparent; box-shadow: none; outline: none; }
          
          /* unify table cell text */
            .sr-cell { color:#0f172a; font-size:.75rem; }

            /* neutral expand button + subtle hover */
            .sr-expand { 
            width:28px; height:28px; border-radius:8px; 
            display:grid; place-items:center;
            background:#fff; 
            color:#334155;                 /* neutral, not blue */
            cursor:pointer;
            }
            .sr-expand:hover { background:#f1f5f9; }
            .sr-expand:focus { outline:none; box-shadow:none; }

            /* chevron animation */
            .sr-caret { transition: transform .18s ease; }
            .sr-caret.rot-180 { transform: rotate(180deg); }
        </style>
        """
    )


# ── Small pieces ───────────────────────────────────────────
def _result_pill(result):  # Var[str]
    return rx.text(
        result,
        as_="span",
        class_name=rx.cond(
            result == "Defective",
            "sr-result-pill pill-def",
            "sr-result-pill pill-ok",
        ),
    )


def _table_header() -> rx.Component:
    # Created At header toggles sort; chevron reflects order
    sort_icon = rx.cond(
        ResultsState.sort_desc,
        rx.icon("chevron-down", size=16),
        rx.icon("chevron-up", size=16),
    )
    created_sort_btn = rx.button(
        rx.hstack(
            rx.text("Created At", as_="span", class_name="sr-th-txt"),
            sort_icon,
            align="center",
            spacing="1",
        ),
        on_click=ResultsState.toggle_sort,
        class_name="sr-sort",
        style={"justify_self": "start"},
    )

    return rx.box(
        rx.text("Serial Number", as_="span", class_name="sr-th-txt"),
        rx.text("Part",          as_="span", class_name="sr-th-txt"),
        created_sort_btn,
        rx.text("Result",        as_="span", class_name="sr-th-txt"),
        rx.box(),  # spacer for chevron column
        class_name="sr-th sr-tr",
        role="row",
    )


def _row(item):  # item is Var[dict]
    serial = item["serial"]

    # main grid row
    row = rx.box(
        rx.text(item["serial"], as_="span", class_name="sr-serial sr-cell"),
        rx.text(item["part"], as_="span", class_name="sr-cell"),
        rx.text(item["created_at"], as_="span", class_name="sr-cell"),
        _result_pill(item["result"]),
        rx.button(
            rx.icon(
                "chevron-down",
                size=16,
                class_name=rx.cond(
                    ResultsState.expanded_serial == serial,
                    "sr-caret rot-180",
                    "sr-caret",
                ),
            ),
            class_name="sr-expand",
            on_click=lambda: ResultsState.toggle_expand(serial),  # type: ignore
            variant="ghost",
            size="1",
        ),
        class_name="sr-row sr-tr",
        role="row",
    )

    # expanded details (dummy content)
    details = rx.box(
        rx.text("Details", class_name="sr-cell"),
        rx.text(
            rx.fragment(
                rx.text("Serial: ", as_="span", weight="bold"),
                rx.text(serial, as_="span"),
            ),
            class_name="sr-cell",
        ),
        rx.text(
            rx.fragment(
                rx.text("Part: ", as_="span", weight="bold"),
                rx.text(item["part"], as_="span"),
            ),
            class_name="sr-cell",
        ),
        rx.text(
            rx.fragment(
                rx.text("Created At: ", as_="span", weight="bold"),
                rx.text(item["created_at"], as_="span"),
            ),
            class_name="sr-cell",
        ),
        class_name="sr-subrow",
    )

    return rx.box(
        row,
        rx.cond(ResultsState.expanded_serial == serial, details, rx.fragment()),
    )



def _toolbar() -> rx.Component:
    left = rx.box(
        rx.text("Result", class_name="sr-label"),
        # Use the simple select API to avoid None/placeholder quirks
        rx.select(
            ["All", "Defective", "Healthy"],
            value=ResultsState.result_filter,
            on_change=ResultsState.set_filter,  # type: ignore
            size="2",
        ),
        class_name="sr-field",
    )
    right = rx.hstack(
        rx.input(
            placeholder="Search by serial number...",
            value=ResultsState.search,
            on_change=ResultsState.set_search,  # type: ignore
            size="2",
            class_name="sr-input",
        ),
        rx.button(
            "Clear",
            on_click=ResultsState.clear_search,
            disabled=ResultsState.search == "",
            class_name="sr-clear",
            size="2",
        ),
        class_name="sr-search",
    )
    return rx.box(left, right, class_name="sr-card sr-toolbar")


def _table() -> rx.Component:
    return rx.box(_table_header(), rx.foreach(ResultsState.page_rows, _row), class_name="sr-card sr-table")


def _footer() -> rx.Component:
    left = rx.text(
        rx.fragment(
            rx.text("Page ", as_="span"),
            rx.text(ResultsState.page, as_="span"),
            rx.text(" of ", as_="span"),
            rx.text(ResultsState.total_pages, as_="span"),
            rx.text(" — ", as_="span"),
            rx.text(ResultsState.total_results, as_="span"),
            rx.text(" results", as_="span"),
        ),
        class_name="sr-page-chip",
    )
    right = rx.box(
        rx.button(rx.icon("chevron-left", size=16), class_name="sr-nav-btn",
                  on_click=ResultsState.prev_page, disabled=ResultsState.page <= 1),
        rx.button(rx.icon("chevron-right", size=16), class_name="sr-nav-btn",
                  on_click=ResultsState.next_page, disabled=ResultsState.page >= ResultsState.total_pages),
        class_name="sr-nav",
    )
    return rx.box(left, right, class_name="sr-card sr-footer")


def inspectra_line_view() -> rx.Component:
    return rx.box(
        _css(),
        rx.box(
            rx.text("Line View", class_name="sr-title"),
            rx.text("Detailed view of inspection results for a specific production line.", class_name="sr-subtitle"),
            _toolbar(),
            _table(),
            _footer(),
            class_name="sr-page"
        ),
        class_name="sr-shell",
    )
