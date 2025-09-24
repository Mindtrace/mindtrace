from typing import Any, Dict, List

import reflex as rx


class _PagerState(rx.State):
    """
    Internal pagination state keyed by `cid`.

    Attributes:
        page (dict[str, int]): Current page per component ID.
        total (dict[str, int]): Total pages per component ID.
        display (dict[str, list[dict]]): Precomputed, condensed display model
            for the pager. Each item is either:
              - {"kind": "page", "n": int}
              - {"kind": "ellipsis"}
    """

    page: Dict[str, int] = {}
    total: Dict[str, int] = {}
    display: Dict[str, List[Dict[str, Any]]] = {}

    # ----- internal -----
    def _recalc(self, cid: str) -> None:
        """
        Recompute the condensed page list for the given `cid`.

        Keeps neighbors, first/last, and expands edges near the start/end.
        """
        cur = int(self.page.get(cid, 1) or 1)
        tot = int(self.total.get(cid, 1) or 1)

        nums: List[int] = []
        for p in range(1, tot + 1):
            if p in {1, tot, cur - 1, cur, cur + 1} or (cur <= 3 and p <= 5) or (cur >= tot - 2 and p >= tot - 4):
                nums.append(p)

        disp: List[Dict[str, Any]] = []
        last = 0
        for p in nums:
            if p - last > 1:
                disp.append({"kind": "ellipsis"})
            disp.append({"kind": "page", "n": p})
            last = p

        self.display[cid] = disp

    # ----- public events -----
    def set_total(self, cid: str, total_pages: int) -> None:
        """
        Initialize/update total pages and compute display model.

        Args:
            cid (str): Pager identifier.
            total_pages (int): Total number of pages (min 1).
        """
        self.total[cid] = max(1, int(total_pages))
        self.page.setdefault(cid, 1)
        self._recalc(cid)

    def go(self, cid: str, p: int) -> None:
        """
        Navigate to a specific page (clamped to [1, total]).

        Args:
            cid (str): Pager identifier.
            p (int): Target page number.
        """
        tot = int(self.total.get(cid, 1) or 1)
        self.page[cid] = min(max(1, int(p)), tot)
        self._recalc(cid)

    def prev(self, cid: str) -> None:
        """
        Navigate to the previous page.

        Args:
            cid (str): Pager identifier.
        """
        self.go(cid, int(self.page.get(cid, 1) or 1) - 1)

    def next(self, cid: str) -> None:
        """
        Navigate to the next page.

        Args:
            cid (str): Pager identifier.
        """
        self.go(cid, int(self.page.get(cid, 1) or 1) + 1)


def pagination(total_pages: int, cid: str = "default") -> rx.Component:
    """
    Render a Var-safe pagination control.

    All calculations happen inside `_PagerState` events. Rendering uses
    `rx.foreach` and `rx.cond` only, so it works with Vars.

    Args:
        total_pages (int): Total number of pages.
        cid (str, optional): Pager identifier. Defaults to "default".

    Returns:
        rx.Component: A horizontal pager with Prev/Next and condensed page buttons.
    """
    # Ensure state for this cid is initialized & display list computed
    _ = _PagerState.set_total(cid, total_pages)

    cur = _PagerState.page.get(cid, 1)
    tot = _PagerState.total.get(cid, total_pages)

    def page_btn(v) -> rx.Component:
        """
        Render a page button for a Var/number `v`.

        Note:
            `v` may be a Var from `rx.foreach`; avoid coercing to str directly.
        """
        return rx.button(
            rx.text(v),
            variant=rx.cond(v == cur, "solid", "ghost"),
            size="1",
            on_click=lambda _v=v: _PagerState.go(cid, _v),
        )

    return rx.hstack(
        rx.button(
            "Prev",
            variant="ghost",
            disabled=cur <= 1,
            on_click=lambda: _PagerState.prev(cid),
        ),
        rx.foreach(
            _PagerState.display.get(cid, []),
            lambda item: rx.cond(
                item["kind"] == "ellipsis",
                rx.text("…"),
                page_btn(item["n"]),
            ),
        ),
        rx.button(
            "Next",
            variant="ghost",
            disabled=cur >= tot,
            on_click=lambda: _PagerState.next(cid),
        ),
        align="center",
        spacing="2",
    )
