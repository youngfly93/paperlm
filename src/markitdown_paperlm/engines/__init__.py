"""Engine adapters: pluggable backends that produce IR from PDF bytes."""

from markitdown_paperlm.engines.base import EngineAdapter
from markitdown_paperlm.engines.fallback_adapter import FallbackAdapter

__all__ = ["EngineAdapter", "FallbackAdapter"]
