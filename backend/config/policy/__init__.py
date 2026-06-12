"""Policy-layer config.

Business rules live in sibling modules — import policies from here or directly:
- ``config.safe_rule`` — redaction / safety field lists
- ``config.cost_rule`` — cost caps and metering policy
"""

from __future__ import annotations
