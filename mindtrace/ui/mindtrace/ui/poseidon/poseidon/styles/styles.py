"""Simplified global styles for the Reflex app.

Since we're using Buridan UI components which handle their own styling,
this module only contains essential global styles.
"""

import reflex as rx

# Essential global styles only
styles = {
    # Basic global styles
    "body": {
        "margin": "0",
        "padding": "0",
        "font_family": "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif",
        "line_height": "1.5",
        "-webkit_font_smoothing": "antialiased",
        "-moz_osx_font_smoothing": "grayscale",
    },
    
    # Remove default margins from headings and paragraphs
    rx.heading: {
        "margin": "0",
    },
    
    rx.text: {
        "margin": "0",
    },
}