"""Suite-wide setup for the framework-seam contract tests.

The framework prints a startup banner on first `Agent` construction, which is
noise in a gate's output and is documented as suppressible by this variable.
"""

from __future__ import annotations

import os

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
