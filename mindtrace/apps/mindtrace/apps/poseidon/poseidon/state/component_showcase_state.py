"""State management for the Component Showcase page."""

import reflex as rx
from typing import List, Dict


class ComponentShowcaseState(rx.State):
    """State for the component showcase page."""
    
    # Select options
    select_options: List[Dict[str, str]] = [
        {"id": "1", "name": "Option 1"},
        {"id": "2", "name": "Option 2"},
        {"id": "3", "name": "Option 3"},
        {"id": "4", "name": "Option 4"},
        {"id": "5", "name": "Option 5"},
    ]