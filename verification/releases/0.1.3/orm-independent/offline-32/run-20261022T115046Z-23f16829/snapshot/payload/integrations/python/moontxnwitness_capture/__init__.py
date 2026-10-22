"""Opt-in psycopg capture for explicitly mapped, uniquely versioned point SQL.

This adapter records facts. MoonBit validates and normalizes the exported trace.
It never treats business values, transaction IDs, or timestamps as version order.
"""

from .capture import (
    AsyncCapturedConnection, CaptureSession, CaptureSetupError, CapturedConnection,
    PointRead, PointWrite, Table, load_jsonl,
)

__all__ = [
    "AsyncCapturedConnection", "CaptureSession", "CaptureSetupError",
    "CapturedConnection", "PointRead", "PointWrite", "Table", "load_jsonl",
]
