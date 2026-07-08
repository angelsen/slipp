"""Framework detection scanner.

Public API for framework detection. Clean interface matching flyctl's architecture.
"""

from slipp.scanner.models import SourceInfo
from slipp.scanner.scanner import scan

# Public API
__all__ = [
    "scan",  # Main entry point: scan directory for service
    "SourceInfo",  # Internal result model (for advanced usage)
]
