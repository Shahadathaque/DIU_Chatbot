"""Deterministic cleaning for the DIU admission research dataset."""

from cleaning.models import CleanedRecord, CleanTable, PageText


CLEANING_PIPELINE_VERSION = "phase5-1.0"

__all__ = [
    "CLEANING_PIPELINE_VERSION",
    "CleanedRecord",
    "CleanTable",
    "PageText",
]
