import reflex as rx


class _TagState(rx.State):
    """
    Internal state for tag input components.

    Attributes:
        tags (dict[str, list[str]]): Mapping of component IDs (`cid`) to lists of committed tags.
        draft (dict[str, str]): Mapping of component IDs (`cid`) to the current draft input text.
    """
    tags: dict[str, list[str]] = {}
    draft: dict[str, str] = {}

    def set_draft(self, cid: str, txt: str) -> None:
        """
        Update the current draft text for a component.

        Args:
            cid (str): Tag input identifier.
            txt (str): Current input text.
        """
        self.draft[cid] = txt

    def on_keydown(self, cid: str, key: str) -> None:
        """
        Handle keydown events in the tag input.

        If Enter is pressed, commits the current draft as a tag.

        Args:
            cid (str): Tag input identifier.
            key (str): Pressed key.
        """
        if key == "Enter":
            self.add(cid)

    def add(self, cid: str) -> None:
        """
        Commit the current draft as a tag.

        Args:
            cid (str): Tag input identifier.
        """
        t = (self.draft.get(cid, "") or "").strip()
        if not t:
            return
        lst = list(self.tags.get(cid, []))
        if t not in lst:
            lst.append(t)
        self.tags[cid] = lst
        self.draft[cid] = ""

    def remove(self, cid: str, tag: str) -> None:
        """
        Remove a tag from the committed list.

        Args:
            cid (str): Tag input identifier.
            tag (str): Tag text to remove.
        """
        self.tags[cid] = [x for x in self.tags.get(cid, []) if x != tag]


def tag_input(cid: str = "default", placeholder: str = "Add tag and press Enter") -> rx.Component:
    """
    Render a tag input component.

    Features:
        - Draft input bound to `_TagState.draft`.
        - Pressing Enter commits the draft as a tag.
        - Tags are displayed as removable pills.
        - Displays a count of committed tags.

    Args:
        cid (str, optional): Tag input identifier. Defaults to "default".
        placeholder (str, optional): Placeholder text for the input. Defaults to "Add tag and press Enter".

    Returns:
        rx.Component: A styled Reflex tag input component.
    """
    return rx.vstack(
        rx.hstack(
            rx.foreach(
                _TagState.tags.get(cid, []),
                lambda tag: rx.box(
                    rx.hstack(
                        rx.text(tag),
                        rx.text(
                            "×",
                            cursor="pointer",
                            on_click=lambda t=tag: _TagState.remove(cid, t),
                        ),
                        spacing="1",
                        align="center",
                    ),
                    padding="2px 8px",
                    border_radius="999px",
                    background="#eff6ff",
                    color="#1d4ed8",
                ),
            ),
            rx.input(
                placeholder=placeholder,
                value=_TagState.draft.get(cid, ""),
                on_change=lambda v: _TagState.set_draft(cid, v),
                on_key_down=lambda key: _TagState.on_keydown(cid, key),
                border="none",
                _focus={"outline": "none"},
                flex="1",
            ),
            spacing="2",
            wrap="wrap",
            align="center",
            border="1px solid #e2e8f0",
            border_radius="10px",
            padding="6px 8px",
            background="#fff",
            width="100%",
        ),
        rx.hstack(
            rx.text(_TagState.tags.get(cid, []).length()),
            rx.text(" tags", size="1", color="#94a3b8"),
            spacing="1",
            align="center",
        ),
        spacing="2",
        width="100%",
    )
