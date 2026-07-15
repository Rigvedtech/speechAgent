"""ATS package — org-scoped import from external hiring systems."""

from ats.factory import SUPPORTED_PROVIDERS, get_provider

__all__ = ["SUPPORTED_PROVIDERS", "get_provider"]
