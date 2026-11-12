"""Run the result, concurrency and error demos with python -m cpp_matrix."""

import asyncio
import sys

from . import multiply_async


async def main() -> None:
    result = await multiply_async([[1, 2, 3], [4, 5, 6]], [[7, 8], [9, 10], [11, 12]])
    print(f"2x3 @ 3x2 = {result}")
    results = await asyncio.gather(
        multiply_async([[1, 2]], [[3], [4]]),
        multiply_async([[5]], [[6, 7]]),
    )
    print(f"gather = {results}")
    outcomes = await asyncio.gather(
        multiply_async([[sys.float_info.max]], [[2]]),
        multiply_async([[3]], [[7]]),
        return_exceptions=True,
    )
    for outcome in outcomes:
        if isinstance(outcome, BaseException):
            print(f"{type(outcome).__name__}: {outcome}")
        else:
            print(f"success: {outcome}")


if __name__ == "__main__":
    asyncio.run(main())
