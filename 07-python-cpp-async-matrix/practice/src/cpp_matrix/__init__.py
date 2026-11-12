"""Run C++ matrix multiplication through asyncio's thread pool."""

import asyncio
from collections.abc import Sequence

from . import _core

__all__ = ["multiply_async"]


def _snapshot(
    matrix: Sequence[Sequence[float]], name: str
) -> tuple[tuple[float, ...], ...]:
    if isinstance(matrix, (str, bytes, bytearray)) or not isinstance(matrix, Sequence):
        raise TypeError(f"{name} must be a sequence of rows")
    rows: list[tuple[float, ...]] = []
    for row in matrix:
        if isinstance(row, (str, bytes, bytearray)) or not isinstance(row, Sequence):
            raise TypeError(f"{name} rows must be sequences")
        rows.append(tuple(row))
    return tuple(rows)


async def multiply_async(
    a: Sequence[Sequence[float]], b: Sequence[Sequence[float]]
) -> list[list[float]]:
    """Snapshot the inputs when this coroutine starts, then await native work."""
    a_snapshot = _snapshot(a, "a")
    b_snapshot = _snapshot(b, "b")
    return await asyncio.to_thread(_core.multiply, a_snapshot, b_snapshot)
