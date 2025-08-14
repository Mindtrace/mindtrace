from typing import Callable, Optional, Sequence, Union

import reflex as rx

from poseidon.styles.global_styles import THEME


def page_container(
    *children,
    title: str | None = None,
    sub_text: str | None = None,
    tools: rx.Component | None = None,
    on_mount: Callable | None = None,
    **props,
) -> rx.Component:
    """Standard page container for content pages with optional title header."""
    inner_children = []
    if title is not None:
        inner_children.append(title_container(title=title, sub_text=sub_text, tools=tools))
    inner_children.extend(children)

    return rx.box(
        rx.box(
            *inner_children,
            display="flex",
            flex_direction="column",
            gap=THEME.layout.content_gap,
            z_index="1",
            **props,
        ),
        min_height="100vh",
        position="relative",
        bg=THEME.colors.bg,
        on_mount=on_mount,
    )


def title_container(
    title: str,
    sub_text: Optional[str] = None,
    tools: Optional[Union[rx.Component, Sequence[rx.Component]]] = None,
    **props,
) -> rx.Component:
    """A page title header with optional subtitle and right-aligned tools.

    Args:
        title: Main heading text.
        sub_text: Optional subtitle text displayed under the heading.
        tools: Optional component or list of components on the right (e.g., time picker, filters).
        **props: Additional props forwarded to the outer container.
    """
    left_stack = rx.box(
        rx.heading(title, size="5", font_weight=THEME.typography.fw_600),
        rx.cond(
            sub_text is not None,
            rx.text(sub_text, color=THEME.colors.fg_muted, font_size=THEME.typography.fs_sm),
            rx.fragment(),
        ),
        display="flex",
        flex_direction="column",
        gap="4px",
    )

    if tools is None:
        right_tools = rx.box()
    elif isinstance(tools, (list, tuple)):
        right_tools = rx.box(*tools, display="flex", align_items="center", gap="8px")
    else:
        right_tools = rx.box(tools)

    return rx.box(
        left_stack,
        right_tools,
        display="flex",
        align_items="center",
        justify_content="space-between",
        width="100%",
        **props,
    )
