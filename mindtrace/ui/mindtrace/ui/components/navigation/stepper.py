import reflex as rx
from typing import List


class _StepperState(rx.State):
    """
    Internal state for stepper components.

    Attributes:
        steps (dict[str, int]): Mapping of stepper IDs (`cid`) to the current step index (0-based).
    """
    steps: dict[str, int] = {}

    def set(self, cid: str, i: int) -> None:
        """
        Set the current step index for a given stepper.

        Args:
            cid (str): Stepper identifier.
            i (int): Step index (0-based).
        """
        self.steps[cid] = max(0, i)

    def next(self, cid: str, total: int) -> None:
        """
        Advance to the next step, bounded by `total`.

        Args:
            cid (str): Stepper identifier.
            total (int): Total number of steps.
        """
        self.steps[cid] = min(total - 1, self.steps.get(cid, 0) + 1)

    def prev(self, cid: str) -> None:
        """
        Go back to the previous step.

        Args:
            cid (str): Stepper identifier.
        """
        self.steps[cid] = max(0, self.steps.get(cid, 0) - 1)


def stepper(steps: List[str], cid: str = "default") -> rx.Component:
    """
    Render a stepper with progress dots, step label, and navigation buttons.

    Args:
        steps (list[str]): List of step labels in order.
        cid (str, optional): Stepper identifier used to track current step. Defaults to "default".

    Returns:
        rx.Component: A Reflex stepper component.
    """
    cur = _StepperState.steps.get(cid, 0)
    total = max(1, len(steps))

    def dot(i: int) -> rx.Component:
        """Render a single progress dot (active if <= current step)."""
        active = i <= cur
        return rx.box(
            width="10px",
            height="10px",
            border_radius="999px",
            background="#0057FF" if active else "#e2e8f0",
        )

    return rx.vstack(
        rx.hstack(
            *[dot(i) for i in range(total)],
            spacing="2",
            align="center",
        ),
        rx.text(f"Step {cur+1} of {total} — {steps[cur]}", size="3", color="#0f172a"),
        rx.hstack(
            rx.button(
                "Back",
                variant="ghost",
                disabled=cur == 0,
                on_click=lambda: _StepperState.prev(cid),
            ),
            rx.button(
                "Next",
                on_click=lambda: _StepperState.next(cid, total),
                disabled=cur >= total - 1,
            ),
            spacing="2",
        ),
        spacing="3",
        width="100%",
    )
