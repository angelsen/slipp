"""Framework detection scanner.

Public API for framework detection. Clean interface matching flyctl's architecture.
"""

from slipp.scanner.scanner import scan

# Public API
__all__ = [
    "scan",  # Main entry point: scan directory for service
]
