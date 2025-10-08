# poseidon/pages/index.py

import reflex as rx
from poseidon.state.auth import AuthState
from poseidon.styles.variants import COMPONENT_VARIANTS

CARD_HEIGHT = 180  # uniform card height (px)

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
                margin: 14px auto 0;
                display:flex; flex-direction:column; align-items:center;
            }}

            .nf-grid {{
                display:grid;
                grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                gap: 22px;
                width: 100%;
                justify-items: stretch;
                align-items: stretch;
                box-sizing: border-box;
            }}

            .nf-card {{
                height: {CARD_HEIGHT}px;
                width: 100%;
                background: #ffffff;
                border: 1px solid rgba(15, 23, 42, .06);
                border-radius: 16px;
                box-shadow: 0 6px 18px rgba(2, 6, 23, .06);
                transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
                display:flex; align-items:center; gap:16px;
                padding: 22px 22px;
                animation: fadeInUp .46s ease both;
                overflow: hidden;
                box-sizing: border-box;
            }}
            .nf-card:hover {{
                transform: translateY(-6px);
                box-shadow: 0 14px 30px rgba(2, 6, 23, .12);
                border-color: rgba(37, 99, 235, .22);
            }}

            .nf-icon {{
                width: 60px; height: 60px;
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
            .nf-title {{ font-weight: 700; color:#0f172a; line-height:1.15; font-size: 1.15rem; }}
            .nf-sub   {{ color:#475569; font-size: .95rem; line-height:1.25; }}

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
                rx.text("Welcome to", font_size="30px", weight="medium", color="#0f172a"),
                rx.text(
                    "NeuroForge",
                    style=COMPONENT_VARIANTS["logo"]["title"],
                    font_size="30px",
                    line_height="1.05",
                ),
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

def _tile(icon_name: str, title: str, subtitle: str, href: str, delay_idx: int) -> rx.Component:
    delay = f"{0.05 * delay_idx:.2f}s"
    return rx.link(
        rx.hstack(
            rx.box(rx.icon(icon_name, size=28), class_name="nf-icon"),
            rx.vstack(
                rx.text(title, class_name="nf-title"),
                rx.text(subtitle, class_name="nf-sub", truncate=True),
                spacing="2",
                align="start",
                class_name="nf-card-body",
            ),
            class_name="nf-card",
            style={"animationDelay": delay},
        ),
        href=href,
        text_decoration="none",
        width="100%",
        display="block",
    )

def _main_actions() -> rx.Component:
    cards = [
        ("plus",          "Create a New Line",      "Start a new inspection line",       "/create-line"),
        ("wrench",        "Modify Deployed Lines",  "Edit or manage existing lines",     "/lines"),
        ("loader-circle", "Lines in Progress",      "Track training & pending setups",   "/lines-in-progress"),
    ]
    return rx.box(
        rx.box(
            *[_tile(icon, title, sub, href, i) for i, (icon, title, sub, href) in enumerate(cards)],
            class_name="nf-grid",
        ),
        class_name="nf-grid-wrap",
    )

def index() -> rx.Component:
    return rx.box(
        _css(),
        rx.box(
            _hero(),
            _main_actions(),
            class_name="nf-shell",
        ),
        width="100%",
        min_height="100vh",
        on_mount=AuthState.check_auth,
    )
