"""Chapter 6 — structural enrichment axis: trace-slice infrastructure."""
from .trace_extractor import (
    DecisionRecord,
    extract_incumbent_trace,
)

__all__ = [
    "DecisionRecord",
    "extract_incumbent_trace",
]
