"""Hardware CLI test setup.

``mindtrace.hardware.cli.commands.scanner`` imports ``...cli.utils.network``, which
is not part of the package; other device CLIs use ``mindtrace.core.utils.network``.
Alias the core module so importing ``mindtrace.hardware.cli.__main__`` works in tests.
"""

from __future__ import annotations

import sys

import mindtrace.core.utils.network as _core_network

sys.modules.setdefault("mindtrace.hardware.cli.utils.network", _core_network)
