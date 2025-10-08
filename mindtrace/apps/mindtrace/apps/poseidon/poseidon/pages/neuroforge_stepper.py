# poseidon/pages/index.py

import reflex as rx
from poseidon.state.auth import AuthState
from poseidon.styles.variants import COMPONENT_VARIANTS

STEPS = [
    ("images",        "Create Line",        "Start a new inspection line"),
    ("brain-circuit", "Select Brain",       "Choose classification / detection / analytics"),
    ("camera",        "Configure Cameras",  "Adjust exposure, gain & stream settings"),
    ("map",           "Map & Capture",      "Connect stations and acquire images"),
    ("tags",          "Prepare Data",       "Select & send images for labeling"),
    ("play",          "Train Model",        "Train and watch live training logs"),
    ("rocket",        "Deploy",             "Roll out to cloud, edge, or containers"),
]

CARD_HEIGHT = 152  # uniform card height (px)

def _css() -> rx.Component:
    return rx.html(
        f"""
        <style>
            @keyframes fadeInUp {{
                from {{ opacity: 0; transform: translateY(18px); }}
                to   {{ opacity: 1; transform: translateY(0); }}
            }}
            @keyframes pop {{
                0%   {{ transform: scale(.96); opacity:.8; }}
                100% {{ transform: scale(1);   opacity:1;  }}
            }}
            .nf-shell {{
                display:flex; flex-direction:column; align-items:center;
                width:100%; min-height:100vh; padding: 48px 20px 36px;
                background:#f8fafc;
            }}
            .nf-hero h1 {{ letter-spacing:.2px; }}
            .nf-hero-sub {{ color:#475569; }}

            .nf-grid-wrap {{
                width: min(1100px, 96vw);
                margin: 10px auto 0;
                display:flex; flex-direction:column; align-items:center;
            }}

            /* Responsive, no forced 7-column rule to avoid overflow */
            .nf-grid {{
                display:grid;
                grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                gap: 18px;
                width: 100%;
                justify-items: stretch;
                align-items: stretch;
                box-sizing: border-box;
            }}

            .nf-card {{
                height: {CARD_HEIGHT}px;
                width: 100%;                 /* fill its grid column */
                background: #ffffff;
                border: 1px solid rgba(15, 23, 42, .06);
                border-radius: 16px;         /* tidy radius (no pill) */
                box-shadow: 0 6px 18px rgba(2, 6, 23, .06);
                transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
                display:flex; align-items:center; gap:14px;
                padding: 18px 18px;
                animation: fadeInUp .46s ease both;
                overflow: hidden;            /* prevent content spill */
                box-sizing: border-box;
            }}
            .nf-card:hover {{
                transform: translateY(-6px);
                box-shadow: 0 14px 30px rgba(2, 6, 23, .12);
                border-color: rgba(37, 99, 235, .22);
            }}

            .nf-icon {{
                width: 52px; height: 52px;
                border-radius: 14px;
                display: grid; place-items: center;
                background: linear-gradient(135deg, #e0e7ff 0%, #dbeafe 100%);
                color: #1e40af;
                box-shadow: inset 0 0 0 1px rgba(30,64,175,.06);
                flex: 0 0 auto;
            }}

            .nf-card-body {{
                display:flex; flex-direction:column; justify-content:center;
                min-width:0;
            }}
            .nf-title {{ font-weight: 700; color:#0f172a; line-height:1.15; }}
            .nf-sub   {{ color:#475569; font-size: .9rem; line-height:1.25; }}

            .nf-cta {{
                margin: 28px auto 0;
                animation: pop .28s ease both .08s;
                display:flex; justify-content:center; width: 100%;
            }}
        </style>
        """
    )

def _hero() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.text("Let's get started!", font_size="30px", weight="medium", color="#0f172a"),
                align="center",
            ),
            rx.text(
                "Visual Inspection — from setup to deploy",
                class_name="nf-hero-sub",
                size="4",
                margin_top=".5rem",
            ),
            spacing="1",
            align="center",
            class_name="nf-hero",
        ),
        text_align="center",
        margin_bottom="10px",
    )

def _tile(icon_name: str, title: str, subtitle: str, idx: int) -> rx.Component:
    delay = f"{0.04 * idx:.2f}s"
    return rx.link(
        rx.hstack(
            rx.box(rx.icon(icon_name, size=24), class_name="nf-icon"),
            rx.vstack(
                rx.text(title, class_name="nf-title"),
                rx.text(subtitle, class_name="nf-sub", truncate=True),
                spacing="1",
                align="start",
                class_name="nf-card-body",
            ),
            class_name="nf-card",
            style={"animationDelay": delay},
        ),
        href="/stepper",
        text_decoration="none",
        width="100%",
        display="block",
    )

def _steps_centered() -> rx.Component:
    return rx.box(
        # rx.text("Your 7-step journey", size="3", color="#64748b", weight="medium", margin_bottom="12px"),
        rx.box(
            *[_tile(icon, title, sub, i) for i, (icon, title, sub) in enumerate(STEPS)],
            class_name="nf-grid",
        ),
        class_name="nf-grid-wrap",
    )

def _cta_button() -> rx.Component:
    return rx.box(
        rx.link(
            rx.button(
                rx.hstack(rx.icon("arrow-right"), rx.text("Get started"), spacing="2", align="center"),
                size="3",
                color_scheme="indigo",
            ),
            href="/stepper",
            text_decoration="none",
        ),
        class_name="nf-cta",
    )

def index() -> rx.Component:
    return rx.box(
        _css(),
        rx.box(
            _hero(),
            _steps_centered(),
            _cta_button(),
            class_name="nf-shell",
        ),
        width="100%",
        min_height="100vh",
        on_mount=AuthState.check_auth,
    )
