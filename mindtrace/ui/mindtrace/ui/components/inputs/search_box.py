import reflex as rx


class _SearchState(rx.State):
    """
    Per-component search state keyed by component ID (`cid`).

    Attributes:
        q (dict[str, str]): Current query text per component.
        last (dict[str, str]): Last submitted query per component.
    """
    q: dict[str, str] = {}
    last: dict[str, str] = {}

    def set_q(self, cid: str, v: str) -> None:
        """
        Update the current query for a component.

        Args:
            cid (str): Search box identifier.
            v (str): New query value.
        """
        self.q[cid] = v

    def submit(self, cid: str) -> None:
        """
        Submit the current query and save it as the last query.

        This is the method where real search side-effects should be hooked in.

        Args:
            cid (str): Search box identifier.
        """
        query = (self.q.get(cid, "") or "").strip()
        self.last[cid] = query

    def clear(self, cid: str) -> None:
        """
        Clear the current and last query for a component.

        Args:
            cid (str): Search box identifier.
        """
        self.q[cid] = ""
        self.last[cid] = ""


def search_box(cid: str = "s1", placeholder: str = "Search…") -> rx.Component:
    """
    Render a Var-safe search box.

    Features:
        - Input value bound to `_SearchState.q`.
        - Pressing Enter submits via `rx.form` `on_submit`.
        - "Search" button triggers submit.
        - "Clear" button resets state.

    Args:
        cid (str, optional): Search box identifier. Defaults to "s1".
        placeholder (str, optional): Placeholder text in the input field. Defaults to "Search…".

    Returns:
        rx.Component: A styled Reflex search box with input, buttons, and status text.
    """
    return rx.vstack(
        rx.form(
            rx.hstack(
                rx.input(
                    placeholder=placeholder,
                    value=_SearchState.q.get(cid, ""),
                    on_change=lambda v: _SearchState.set_q(cid, v),
                    flex="1",
                ),
                rx.button("Search", type="submit", variant="solid"),
                rx.button(
                    "Clear",
                    type="button",
                    variant="ghost",
                    on_click=lambda: _SearchState.clear(cid),
                ),
                spacing="2",
                align="center",
                width="100%",
            ),
            on_submit=lambda: _SearchState.submit(cid),
            width="100%",
        ),
        rx.text(
            rx.cond(
                (_SearchState.last.get(cid, "") != ""),
                f'Last search: "{_SearchState.last.get(cid, "")}"',
                "No search yet.",
            ),
            size="1",
            color="#64748b",
        ),
        spacing="2",
        width="100%",
    )
