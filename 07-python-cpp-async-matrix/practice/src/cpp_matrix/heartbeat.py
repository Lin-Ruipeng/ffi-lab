"""Observe asyncio while a real C++ multiplication is running."""

import asyncio
from contextlib import suppress
from time import perf_counter

from . import multiply_async


async def main() -> None:
    rows, shared, cols = 600, 800, 500
    a = [[1.0] * shared for _ in range(rows)]
    b = [[1.0] * cols for _ in range(shared)]
    beats = 0

    async def heartbeat() -> None:
        nonlocal beats
        while True:
            await asyncio.sleep(0.05)
            beats += 1
            print(f"heartbeat {beats}")

    timer = asyncio.create_task(heartbeat())
    started = perf_counter()
    try:
        print(f"awaiting {rows}x{shared} @ {shared}x{cols}")
        result = await multiply_async(a, b)
        print(f"result: {len(result)}x{len(result[0])}; first = {result[0][0]}")
        print(f"heartbeats: {beats}; elapsed: {perf_counter() - started:.3f} s")
    finally:
        timer.cancel()
        with suppress(asyncio.CancelledError):
            await timer


if __name__ == "__main__":
    asyncio.run(main())
