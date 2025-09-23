import reflex as rx


class _ChecklistState(rx.State):
    """
    State manager for checklist components.

    Attributes:
        checked (dict[str, set[str]]): Mapping of checklist IDs (`cid`) to a set of checked item keys.
    """

    checked: dict[str, set[str]] = {}

    def toggle(self, cid: str, key: str):
        """
        Toggle the checked state of a given key in a checklist.

        Args:
            cid (str): The checklist identifier.
            key (str): The key/item to toggle.
        """
        s = set(self.checked.get(cid, set()))
        if key in s:
            s.remove(key)
        else:
            s.add(key)
        self.checked[cid] = s


def checklist(items: list[str], cid: str = "default"):
    """
    Create a checklist component with checkable items.

    Each checklist is tracked internally by its `cid`, allowing
    multiple independent checklists to exist on the same page.

    Args:
        items (list[str]): List of item labels for the checklist.
        cid (str, optional): Unique checklist identifier. Defaults to "default".

    Returns:
        rx.Component: A Reflex box containing a vertical stack of checkable items.
    """

    def row(key: str):
        return rx.hstack(
            rx.checkbox(
                checked=key in _ChecklistState.checked.get(cid, set()),
                on_change=lambda _: _ChecklistState.toggle(cid, key),
            ),
            rx.text(key),
            align="center",
            spacing="2",
        )

    return rx.box(
        rx.vstack(*[row(k) for k in items], spacing="2", align="start", width="100%"),
        padding="1rem",
        border="1px solid #e2e8f0",
        border_radius="10px",
        background="#fff",
        width="100%",
    )
