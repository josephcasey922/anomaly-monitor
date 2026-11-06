"""Anomaly Monitor: calendar-aware CSV analytics and change monitoring."""
__version__ = "0.2.1"
from .pipeline import run_pipeline

__all__ = ["run_pipeline", "__version__"]
