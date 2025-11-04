import reflex as rx

# ─────────────────────────────────────────────────────────────
# 🎨 TOKENS — Global constants used throughout Inspectra
# ─────────────────────────────────────────────────────────────
class Tokens:
    """App-wide design tokens for Inspectra."""
    # Colors
    primary = "#184937"       # Inspectra green
    primary_light = "#60CCA5"
    surface = "#ffffff"
    background = "#f9fafb"
    border = "rgba(0,0,0,0.1)"

    # Typography
    font_family = "Inter, system-ui, sans-serif"

    # Layout
    header_h = "72px"
    sidebar_w = "120px"
    border_radius = "12px"

    # Spacing
    space_1 = "4px"
    space_2 = "8px"
    space_3 = "12px"
    space_4 = "16px"
    space_5 = "20px"
    space_6 = "24px"
    space_8 = "32px"
    space_10 = "40px"

    # Z-index
    z_header = 100
    z_overlay = 1000


T = Tokens  # shorthand alias used by other components

# ─────────────────────────────────────────────────────────────
# ⚙️ Shared style primitives (spacers, layout helpers)
# ─────────────────────────────────────────────────────────────
class SP:
    """Common spacing primitives."""
    space_1 = T.space_1
    space_2 = T.space_2
    space_3 = T.space_3
    space_4 = T.space_4
    space_6 = T.space_6
    space_8 = T.space_8
    space_10 = T.space_10


# ─────────────────────────────────────────────────────────────
# 🧱 COMPONENT VARIANTS — for branding, logo, cards, etc.
# ─────────────────────────────────────────────────────────────
COMPONENT_VARIANTS = {
    "logo": {
        "title": {
            "font_weight": "700",
            "font_size": "22px",
            "letter_spacing": "-0.02em",
            "color": T.primary_light,
        },
        "subtitle": {
            "font_weight": "500",
            "font_size": "14px",
            "color": "#64748b",
        },
    },
    "card": {
        "base": {
            "background": T.surface,
            "border_radius": T.border_radius,
            "box_shadow": "0 2px 8px rgba(0,0,0,0.05)",
            "border": f"1px solid {T.border}",
            "padding": T.space_6,
        }
    },
}

# ─────────────────────────────────────────────────────────────
# 💅 Base <style> injection for app (applied once globally)
# ─────────────────────────────────────────────────────────────
def global_css() -> rx.Component:
    """Injects global CSS variables for Inspectra theme."""
    return rx.html(f"""
    <style>
        :root {{
            --color-primary: {T.primary};
            --color-primary-light: {T.primary_light};
            --color-surface: {T.surface};
            --color-background: {T.background};
            --border-color: {T.border};
            --radius: {T.border_radius};
            --font-family: {T.font_family};
            --header-h: {T.header_h};
        }}

        html, body {{
            font-family: var(--font-family);
            background: var(--color-background);
            color: #0f172a;
            margin: 0;
            padding: 0;
        }}

        /* Scrollbar Styling */
        ::-webkit-scrollbar {{
            width: 10px;
        }}
        ::-webkit-scrollbar-thumb {{
            background: rgba(0,0,0,0.15);
            border-radius: 5px;
        }}
        ::-webkit-scrollbar-thumb:hover {{
            background: rgba(0,0,0,0.3);
        }}

        /* Buttons, cards, and icons share a soft hover */
        .clickable:hover {{
            opacity: .85;
            cursor: pointer;
        }}
    </style>
    """)
