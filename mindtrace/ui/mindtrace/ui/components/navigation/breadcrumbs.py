from typing import Any, Iterable, Mapping

import reflex as rx


def _crumb(it: Mapping[str, Any]) -> rx.Component:
    """
    Render a single breadcrumb item.

    Each breadcrumb dict must include:
        - "label" (str): Display text.
        - "href" (str): Link URL. Use empty string "" for plain text.
        - "is_last" (bool): Whether this is the last breadcrumb in the sequence.

    Args:
        it (Mapping[str, Any]): Breadcrumb item dictionary.

    Returns:
        rx.Component: A horizontal stack containing the breadcrumb item.
    """
    return rx.hstack(
        rx.cond(
            (~it["is_last"]) & (it["href"] != ""),
            rx.link(it["label"], href=it["href"], color="#334155"),
            rx.text(it["label"], color="#0f172a", weight="medium"),
        ),
        rx.cond(~it["is_last"], rx.text(" / ", color="#94a3b8"), rx.fragment()),
        align="center",
        spacing="1",
    )


def breadcrumbs(items: Iterable[Mapping[str, Any]] | Any) -> rx.Component:
    """
    Render a breadcrumbs navigation bar.

    Each item must be a dict with:
        - "label" (str): Display text.
        - "href" (str): Link URL. Use "" for plain text.
        - "is_last" (bool): Whether this is the final breadcrumb.

    Supports both static lists and reactive Vars.

    Args:
        items (Iterable[Mapping[str, Any]] | Var): Collection of breadcrumb dicts
            or a reactive Var resolving to such a list.

    Returns:
        rx.Component: A horizontal stack of breadcrumb items.
    """
    return rx.hstack(
        rx.foreach(items, _crumb),
        align="center",
        spacing="1",
        wrap="wrap",
    )
