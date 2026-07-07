"""Container image transfer service."""

from slipp.services.image.transfer import detect_local_runtime, push_image

__all__ = ["detect_local_runtime", "push_image"]
