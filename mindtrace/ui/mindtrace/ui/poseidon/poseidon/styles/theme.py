"""Modern dashboard theme configuration for the Reflex app."""

import reflex as rx

# Enhanced modern color palette - inspired by premium dashboards
COLORS = {
    # Primary brand colors - Ocean Blue palette
    "primary": "#2563eb",           # Rich blue (professional primary)
    "primary_hover": "#1d4ed8",     # Deeper blue for hover states
    "primary_light": "#3b82f6",     # Lighter blue for accents
    "secondary": "#000000",         # Black (secondary actions)
    
    # Background colors - Subtle gradients
    "background": "#fafbfc",        # Slightly off-white background
    "surface": "#f8fafc",          # Light gray surface
    "surface_hover": "#f1f5f9",    # Slightly darker for hover
    "sidebar": "#f9fafb",          # Sidebar background with warmth
    
    # Text colors - Enhanced contrast
    "text": "#111827",             # Rich dark gray text
    "text_muted": "#6b7280",       # Balanced gray text
    "text_light": "#9ca3af",      # Light gray text
    
    # Border and divider colors - Subtle but defined
    "border": "#e5e7eb",          # Clean border
    "border_light": "#f3f4f6",    # Very light border
    "border_accent": "#d1d5db",   # Slightly darker border
    
    # Status colors - Vibrant but professional
    "success": "#059669",          # Emerald green
    "warning": "#d97706",          # Amber orange
    "error": "#dc2626",            # Crisp red
    "info": "#0ea5e9",             # Sky blue
    
    # Accent colors for variety
    "accent_purple": "#8b5cf6",    # Purple accent
    "accent_teal": "#0d9488",      # Teal accent
    "accent_orange": "#ea580c",    # Orange accent
    
    # Utility colors
    "transparent": "transparent",
    "white": "#ffffff",
    "black": "#000000",
}

# Enhanced typography system - modern and readable
TYPOGRAPHY = {
    # Modern font stack with better fallbacks
    "font_family": "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell', sans-serif",
    "font_family_display": "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif",
    "font_family_mono": "'JetBrains Mono', 'Fira Code', 'Monaco', 'Consolas', monospace",
    
    "font_sizes": {
        "xs": "0.75rem",    # 12px - Small labels
        "sm": "0.875rem",   # 14px - Body text
        "base": "1rem",     # 16px - Default
        "lg": "1.125rem",   # 18px - Large text
        "xl": "1.25rem",    # 20px - Headings
        "2xl": "1.5rem",    # 24px - Page titles
        "3xl": "1.875rem",  # 30px - Large headings
        "4xl": "2.25rem",   # 36px - Hero text
        "5xl": "3rem",      # 48px - Display text
        "6xl": "3.75rem",   # 60px - Extra large display
    },
    
    "font_weights": {
        "light": "300",
        "normal": "400",
        "medium": "500",
        "semibold": "600",
        "bold": "700",
        "extrabold": "800",
        "black": "900",
    },
    
    "line_heights": {
        "none": "1",
        "tight": "1.25",
        "snug": "1.375",
        "normal": "1.5",
        "relaxed": "1.625",
        "loose": "2",
    },
    
    "letter_spacing": {
        "tighter": "-0.05em",
        "tight": "-0.025em",
        "normal": "0em",
        "wide": "0.025em",
        "wider": "0.05em",
        "widest": "0.1em",
    },
}

# Reflex spacing system - standardized on Reflex scale (0-9)
SPACING = {
    "xs": "1",      # 0.25rem (4px)
    "sm": "2",      # 0.5rem  (8px)
    "md": "4",      # 1rem    (16px)
    "lg": "6",      # 1.5rem  (24px)
    "xl": "8",      # 2rem    (32px)
    "2xl": "9",     # 2.25rem (36px)
}

# Sizing constants for modern dashboard
SIZING = {
    # Border radius
    "border_radius_sm": "4px",
    "border_radius": "8px",
    "border_radius_lg": "12px",
    "border_radius_xl": "16px",
    
    # Border widths
    "border_width": "1px",
    "border_width_thick": "2px",
    
    # Layout dimensions
    "sidebar_width": "240px",
    "header_height": "64px",
    "card_min_height": "120px",
    
    # Content widths
    "max_width_form": "400px",
    "max_width_content": "1200px",
    "max_width_prose": "65ch",
    
    # Heights
    "full_height": "100vh",
    "content_height": "calc(100vh - 64px)",
}

# Enhanced shadows for premium depth and visual hierarchy
SHADOWS = {
    "none": "0 0 #0000",
    "sm": "0 1px 2px 0 rgb(0 0 0 / 0.05)",
    "md": "0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)",
    "lg": "0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)",
    "xl": "0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1)",
    "2xl": "0 25px 50px -12px rgb(0 0 0 / 0.25)",
    
    # Card-specific shadows for better UX
    "card": "0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)",
    "card_hover": "0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)",
    "card_focus": "0 0 0 3px rgb(59 130 246 / 0.1)",
    
    # Special shadows for interactive elements
    "button": "0 1px 2px 0 rgb(0 0 0 / 0.05)",
    "button_hover": "0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)",
    "dropdown": "0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1)",
    
    # Colored shadows for accents
    "primary": "0 4px 14px 0 rgb(37 99 235 / 0.2)",
    "success": "0 4px 14px 0 rgb(5 150 105 / 0.2)",
    "warning": "0 4px 14px 0 rgb(217 119 6 / 0.2)",
    "error": "0 4px 14px 0 rgb(220 38 38 / 0.2)",
}

# Enhanced theme configuration - premium light theme
theme_config = rx.theme(
    appearance="light",
    accent_color="blue",
    gray_color="slate",
    radius="medium",
    scaling="100%",
    # Add Google Fonts import
    fonts={
        "Inter": "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap",
        "JetBrains Mono": "https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&display=swap"
    }
) 