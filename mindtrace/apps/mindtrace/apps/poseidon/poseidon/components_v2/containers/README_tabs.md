# Tabs Container Component

A modern, flexible tabs container component built with Reflex and integrated with the Poseidon design system.

## Features

- **Multiple Variants**: Default, Pills, Underline, and Card styles
- **Orientation Support**: Horizontal and vertical layouts
- **Icon Support**: Optional icons for tab labels
- **Accessibility**: Full keyboard navigation and ARIA support
- **Responsive**: Adapts to different screen sizes
- **Theme Integration**: Uses global design tokens for consistent styling
- **Smooth Animations**: Built-in transitions and hover effects

## Usage

### Basic Usage

```python
from poseidon.components_v2.containers import tabs_container

# Define your tabs
tabs = [
    {
        "label": "Overview",
        "value": "overview",
        "icon": "📊",  # Optional
        "content": rx.text("Overview content here"),
    },
    {
        "label": "Settings",
        "value": "settings",
        "content": rx.text("Settings content here"),
    },
]

# Create tabs container
tabs_component = tabs_container(tabs)
```

### Convenience Functions

```python
from poseidon.components_v2.containers import (
    horizontal_tabs,
    vertical_tabs,
    pill_tabs,
    underline_tabs,
    card_tabs,
)

# Different variants
horizontal_tabs(tabs)      # Default horizontal tabs
vertical_tabs(tabs)        # Vertical layout
pill_tabs(tabs)           # Pill-style tabs
underline_tabs(tabs)      # Underline-style tabs
card_tabs(tabs)           # Card-style tabs
```

## API Reference

### `tabs_container()`

Main function to create a tabs container.

**Parameters:**
- `tabs` (List[Dict]): List of tab configurations
- `default_value` (str, optional): Default active tab value
- `orientation` (str): "horizontal" or "vertical" (default: "horizontal")
- `variant` (str): "default", "pills", "underline", or "cards" (default: "default")
- `**kwargs`: Additional props for rx.tabs.root

**Tab Configuration:**
```python
{
    "label": str,           # Tab label text
    "value": str,           # Unique tab identifier
    "icon": str,           # Optional emoji or icon
    "content": Component,   # Tab content (Reflex component)
    "disabled": bool,       # Optional: disable tab
}
```

### Convenience Functions

All convenience functions accept the same parameters as `tabs_container()` except for the variant/orientation which is pre-configured:

- `horizontal_tabs(tabs, **kwargs)` - Default horizontal tabs
- `vertical_tabs(tabs, **kwargs)` - Vertical layout tabs
- `pill_tabs(tabs, **kwargs)` - Pill-style tabs
- `underline_tabs(tabs, **kwargs)` - Underline-style tabs
- `card_tabs(tabs, **kwargs)` - Card-style tabs

## Variants

### Default
Standard tabs with subtle hover effects and accent color for active state.

### Pills
Rounded pill-style tabs with background color changes for active state.

### Underline
Minimal tabs with underline indicator for active state.

### Cards
Card-style tabs with elevated appearance and content in card containers.

## Examples

### Complex Content Example

```python
from poseidon.components_v2.containers import card_tabs
from poseidon.components_v2.core import button

tabs = [
    {
        "label": "Dashboard",
        "value": "dashboard",
        "icon": "🏠",
        "content": rx.vstack(
            rx.heading("Dashboard", size="4"),
            rx.text("Welcome to your dashboard"),
            rx.hstack(
                button("Action 1", variant="primary"),
                button("Action 2", variant="secondary"),
            ),
            spacing="4",
        ),
    },
    {
        "label": "Analytics",
        "value": "analytics",
        "icon": "📈",
        "content": rx.vstack(
            rx.heading("Analytics", size="4"),
            rx.text("View your analytics data"),
            # Add charts or data visualization here
            spacing="4",
        ),
    },
]

dashboard_tabs = card_tabs(tabs)
```

### Vertical Layout Example

```python
from poseidon.components_v2.containers import vertical_tabs

settings_tabs = vertical_tabs([
    {
        "label": "General",
        "value": "general",
        "icon": "⚙️",
        "content": rx.text("General settings"),
    },
    {
        "label": "Security",
        "value": "security",
        "icon": "🔒",
        "content": rx.text("Security settings"),
    },
    {
        "label": "Privacy",
        "value": "privacy",
        "icon": "👤",
        "content": rx.text("Privacy settings"),
    },
])
```

### Controlled Tabs Example

```python
import reflex as rx

class TabsState(rx.State):
    active_tab = "overview"
    
    def change_tab(self, value: str):
        self.active_tab = value

def controlled_tabs():
    tabs = [
        {
            "label": "Overview",
            "value": "overview",
            "content": rx.text("Overview content"),
        },
        {
            "label": "Details",
            "value": "details",
            "content": rx.text("Details content"),
        },
    ]
    
    return tabs_container(
        tabs,
        value=TabsState.active_tab,
        on_change=TabsState.change_tab,
    )
```

## Styling

The tabs container uses the global design tokens from `poseidon.styles.global_styles`:

- **Colors**: Uses theme colors for consistent appearance
- **Typography**: Inherits font family and sizing from theme
- **Spacing**: Uses consistent spacing tokens
- **Animations**: Smooth transitions with theme-defined timing
- **Shadows**: Subtle shadows for depth and elevation

## Accessibility

- Full keyboard navigation support
- ARIA attributes for screen readers
- Focus management
- High contrast support
- Semantic HTML structure

## Browser Support

- Modern browsers with CSS Grid and Flexbox support
- Graceful degradation for older browsers
- Mobile-responsive design

## Integration

The tabs container is fully integrated with the Poseidon design system and can be used alongside other components like:

- Cards
- Buttons
- Forms
- Charts
- Navigation components

## Performance

- Optimized rendering with minimal re-renders
- Efficient state management
- Lazy content loading support
- Smooth animations with hardware acceleration 