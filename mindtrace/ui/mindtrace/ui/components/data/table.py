import reflex as rx


class _TableState(rx.State):
    """
    Internal state manager for table components.

    Attributes:
        sorts (dict[str, dict]): Sorting state by table ID (`cid`).
            Format: {cid: {"column": str, "direction": "asc"|"desc"}}
        pages (dict[str, int]): Current page index per table ID.
        rows_per_page (dict[str, int]): Rows per page per table ID.
    """

    sorts: dict[str, dict] = {}
    pages: dict[str, int] = {}
    rows_per_page: dict[str, int] = {}

    def set_sort(self, cid: str, column: str):
        """
        Toggle or set the sort order for a given column.

        Args:
            cid (str): Table identifier.
            column (str): Column ID to sort by.
        """
        cur = self.sorts.get(cid, {"column": "", "direction": "asc"})
        if cur["column"] == column:
            cur["direction"] = "desc" if cur["direction"] == "asc" else "asc"
        else:
            cur = {"column": column, "direction": "asc"}
        self.sorts[cid] = cur

    def set_page(self, cid: str, page: int):
        """
        Update the current page for a given table.

        Args:
            cid (str): Table identifier.
            page (int): Page number (minimum 1).
        """
        self.pages[cid] = max(1, page)

    def set_rpp(self, cid: str, rpp: int):
        """
        Update the rows-per-page setting for a given table.

        Args:
            cid (str): Table identifier.
            rpp (int): Number of rows per page (minimum 1).
        """
        self.rows_per_page[cid] = max(1, rpp)


def _sorted_rows(cid: str, rows: list[dict], columns: list[dict]) -> list[dict]:
    """
    Return rows sorted according to the current table state.

    Args:
        cid (str): Table identifier.
        rows (list[dict]): List of row dictionaries.
        columns (list[dict]): List of column definitions.

    Returns:
        list[dict]: Sorted list of rows.
    """
    conf = _TableState.sorts.get(cid)
    if not conf or not conf.get("column"):
        return rows
    col = conf["column"]
    reverse = conf["direction"] == "desc"
    try:
        return sorted(rows, key=lambda r: r.get(col, ""), reverse=reverse)
    except Exception:
        return rows


def table(
    columns: list[dict],
    rows: list[dict],
    cid: str = "default",
    paginate: bool = True,
    default_rpp: int = 10,
) -> rx.Component:
    """
    Render a sortable, paginated data table.

    Args:
        columns (list[dict]): Column definitions.
            Example: [{"id": "name", "label": "Name", "width": "auto"}]
        rows (list[dict]): Row data, keyed by column IDs.
            Example: [{"name": "Alice", ...}, ...]
        cid (str, optional): Unique table identifier. Defaults to "default".
        paginate (bool, optional): Enable pagination controls. Defaults to True.
        default_rpp (int, optional): Default rows per page. Defaults to 10.

    Returns:
        rx.Component: A styled Reflex table component.
    """
    _TableState.rows_per_page.setdefault(cid, default_rpp)
    _TableState.pages.setdefault(cid, 1)

    hdr = rx.hstack(
        *[
            rx.hstack(
                rx.text(col.get("label", col["id"]), weight="bold"),
                rx.icon_button(
                    rx.icon(tag="chevrons-up-down"),
                    variant="ghost",
                    on_click=lambda c=col["id"]: _TableState.set_sort(cid, c),
                ),
                spacing="1",
                style={"width": col.get("width", "auto")},
            )
            for col in columns
        ],
        spacing="4",
        width="100%",
        padding="0.5rem 0.75rem",
        border_bottom="1px solid #e2e8f0",
    )

    srows = _sorted_rows(cid, rows, columns)

    rpp = _TableState.rows_per_page.get(cid, default_rpp)
    page = _TableState.pages.get(cid, 1)
    start = (page - 1) * rpp
    end = start + rpp
    page_rows = srows[start:end]
    total_pages = max(1, ((len(srows) - 1) // rpp) + 1)
    page = min(page, total_pages)

    body = rx.vstack(
        *[
            rx.hstack(
                *[rx.text(str(r.get(col["id"], ""))) for col in columns],
                spacing="4",
                width="100%",
                padding="0.5rem 0.75rem",
                border_bottom="1px solid #f1f5f9",
            )
            for r in page_rows
        ],
        spacing="0",
        width="100%",
    )

    controls = (
        rx.hstack(
            rx.text(f"Rows: {len(srows)}", size="2", color="#64748b"),
            rx.spacer(),
            rx.button(
                "Prev",
                variant="ghost",
                disabled=page <= 1,
                on_click=lambda: _TableState.set_page(cid, page - 1),
            ),
            rx.text(f"{page}/{total_pages}", size="2"),
            rx.button(
                "Next",
                variant="ghost",
                disabled=page >= total_pages,
                on_click=lambda: _TableState.set_page(cid, page + 1),
            ),
            spacing="3",
            width="100%",
            padding="0.5rem 0.75rem",
        )
        if paginate
        else rx.fragment()
    )

    return rx.box(
        rx.box(
            hdr,
            background="#fbfdff",
            border="1px solid #e2e8f0",
            border_bottom="none",
            border_radius="10px 10px 0 0",
        ),
        rx.box(body, border="1px solid #e2e8f0", border_top="none"),
        rx.box(
            controls,
            border="1px solid #e2e8f0",
            border_top="none",
            border_radius="0 0 10px 10px",
        )
        if paginate
        else rx.fragment(),
        border_radius="10px",
        overflow="hidden",
        width="100%",
        background="#fff",
    )
