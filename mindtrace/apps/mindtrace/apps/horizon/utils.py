"""Utility functions for Horizon service.

Note: Configuration is now handled via the config_overrides pattern in HorizonService.
Access config through service.config.HORIZON after instantiation.
"""

# This module previously exported get_horizon_config and reset_horizon_config.
# Those functions have been removed in favor of the config_overrides pattern.
#
# For configuration access:
#   - Within the service: use self.config.HORIZON
#   - For testing: pass config_overrides to HorizonService()
#   - For standalone config: use Config({"HORIZON": HorizonSettings().model_dump()})

__all__: list[str] = []
