import reflex as rx
from typing import Iterable, Mapping, Union, Any


def accordion(
    items: Union[Iterable[Mapping[str, Any]], Any],
    cid: str | None = None,
    single: bool = False,
) -> rx.Component:
    """
    Render an accordion that supports both plain Python lists and Reflex Vars.

    Each item must include:
        - "key" (str): Unique identifier for the panel.
        - "title" (str): Header text.
        - "content" (optional): Either a Reflex Component or a string.

    Notes:
        - `items` can be a normal iterable of dict-like objects or a Reflex Var.
        - `cid` is reserved for future per-instance state (not used at the moment).
        - When `content` is a string, it will be wrapped in `rx.text(...)`.

    Args:
        items (Iterable[Mapping[str, Any]] | Var): Collection of item dicts (or a Var).
        cid (str | None, optional): Reserved component identifier. Defaults to None.
        single (bool, optional): If True, only one item can be open at a time
            (accordion type "single"); otherwise multiple items may be open ("multiple").
            Defaults to False.

    Returns:
        rx.Component: A Reflex accordion component.
    """

    def _row(it: Mapping[str, Any]) -> rx.Component:
        title = it["title"]
        content = (
            rx.cond(
                it["content"].__dict__.get("_is_var", False) if hasattr(it["content"], "_is_var") else False,
                it["content"],
                rx.text(it["content"]) if hasattr(it, "__getitem__") else rx.fragment(),
            )
            if hasattr(it, "__getitem__") and "content" in it
            else rx.fragment()
        )

        return rx.accordion.item(
            rx.accordion.header(
                rx.accordion.trigger(
                    rx.hstack(
                        rx.text(title),
                        rx.icon(tag="chevron-down"),
                        justify="between",
                        align="center",
                        width="100%",
                    ),
                    style={"padding": "8px 0"},
                ),
            ),
            rx.accordion.content(rx.box(content, style={"padding": "8px 0"})),
            value=it["key"],
        )

    acc_type = rx.cond(single, "single", "multiple")

    return rx.accordion.root(
        rx.foreach(items, _row) if hasattr(items, "_is_var") else rx.fragment(*[_row(it) for it in items]),
        type=acc_type,
        collapsible=True,
        style={"width": "100%"},
    )
