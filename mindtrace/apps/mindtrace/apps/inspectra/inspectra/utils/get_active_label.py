import reflex as rx


def get_active_label(path: rx.Var[str]) -> rx.Var[str]:
    """Map current path to sidebar label."""
    return rx.cond(
        path.endswith("/line-insights"), "Line insights",
        rx.cond(
            path.endswith("/line-view"), "Line view",
            rx.cond(
                path.endswith("/plant-view"), "Plant view",
                rx.cond(
                    path.endswith("/alerts"), "Alerts",
                    rx.cond(
                        path.endswith("/reports"), "Reports",
                        rx.cond(
                            path.endswith("/settings"), "Settings",
                            "Home",
                        ),
                    ),
                ),
            ),
        ),
    )
