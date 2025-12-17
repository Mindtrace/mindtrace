"""CLI adapter for AgentRegistry.

Handles CLI-specific operations like importing CLI classes and registering Click commands.
"""

from typing import ClassVar

import click

from mindtrace.agents.catalogue.agents import AgentRegistry


class AgentCLIAdapter:
    """Adapter for CLI operations on AgentRegistry.

    Separates CLI concerns from core registry functionality.
    """

    # Cache for imported CLI classes to avoid repeated importlib calls
    _cli_class_cache: ClassVar[dict[str, type]] = {}

    @classmethod
    def get_cli_class(cls, name: str):
        """Dynamically import and return the CLI class for an agent.

        Caches imported classes to avoid repeated importlib calls.

        Args:
            name: Name of the agent.

        Returns:
            The CLI class if found, None otherwise.
        """
        # Check cache first
        if name in cls._cli_class_cache:
            return cls._cli_class_cache[name]

        # Load metadata from Registry
        info = AgentRegistry.get(name)
        if not info:
            return None

        # Import module and get class (only once)
        import importlib

        module = importlib.import_module(info["cli_module"])
        cli_class = getattr(module, info["cli_class"])

        # Cache for future use
        cls._cli_class_cache[name] = cli_class

        return cli_class

    @classmethod
    def register_all_commands(cls, parent_group: click.Group):
        """Register all agent CLI commands with the parent Click group.

        Args:
            parent_group: The Click group to register commands with.
        """
        for name in AgentRegistry.names():
            cli_class = cls.get_cli_class(name)
            if cli_class:
                parent_group.add_command(cli_class.cli_group(), name=name)
