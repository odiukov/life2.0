"""Legacy alias preserving module globals for existing callers and tests."""

import sys

from shared.observability import telemetry as _implementation

sys.modules[__name__] = _implementation
