import asyncio
import importlib.machinery
import inspect
import math
import sys
import threading
from collections.abc import Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import FrameType

import pytest

from cpp_matrix import _core, multiply_async


@dataclass
class NativeCall:
    started: threading.Event = field(default_factory=threading.Event)
    finished: threading.Event = field(default_factory=threading.Event)
    thread_ids: set[int] = field(default_factory=set)


@contextmanager
def observe_native_call() -> Iterator[NativeCall]:
    state = NativeCall()
    native = _core.multiply

    def profile(_frame: FrameType, event: str, arg: object) -> None:
        if arg is native:
            if event == "c_call":
                state.thread_ids.add(threading.get_ident())
                state.started.set()
            elif event in ("c_return", "c_exception"):
                state.finished.set()

    def observed(
        a: Sequence[Sequence[float]], b: Sequence[Sequence[float]]
    ) -> list[list[float]]:
        previous = sys.getprofile()
        sys.setprofile(profile)
        try:
            return native(a, b)
        finally:
            sys.setprofile(previous)

    previous_interval = sys.getswitchinterval()
    sys.setswitchinterval(1.0)
    try:
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(_core, "multiply", observed)
            yield state
    finally:
        sys.setswitchinterval(previous_interval)


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ([[1, 2, 3], [4, 5, 6]], [[7, 8], [9, 10], [11, 12]], [[58, 64], [139, 154]]),
        ([[3]], [[4]], [[12]]),
        ([[1, 2, 3, 4]], [[2], [3], [4], [5]], [[40]]),
        ([[2], [3], [4]], [[5, 6]], [[10, 12], [15, 18], [20, 24]]),
        ([[-1, 2], [3, -4]], [[5, -6], [-7, 8]], [[-19, 22], [43, -50]]),
        ([[0, 0], [0, 0]], [[1], [2]], [[0], [0]]),
        ([[1, 2]], [[0, 0], [0, 0]], [[0, 0]]),
    ],
)
def test_products(
    a: Sequence[Sequence[float]],
    b: Sequence[Sequence[float]],
    expected: list[list[float]],
) -> None:
    result = asyncio.run(multiply_async(a, b))
    assert result == expected
    assert all(isinstance(value, float) for row in result for value in row)


def test_identity_on_either_side() -> None:
    matrix = [[1, 2, 3], [4, 5, 6]]
    assert asyncio.run(multiply_async([[1, 0], [0, 1]], matrix)) == matrix
    assert (
        asyncio.run(multiply_async(matrix, [[1, 0, 0], [0, 1, 0], [0, 0, 1]])) == matrix
    )


def test_decimal() -> None:
    result = asyncio.run(multiply_async([[0.1, 0.2]], [[0.3], [0.4]]))
    assert result[0][0] == pytest.approx(0.11)


def test_tuple_and_keyword_inputs() -> None:
    assert asyncio.run(multiply_async(b=((3,), (4,)), a=((1, 2),))) == [[11.0]]


def test_bool_and_double_precision() -> None:
    assert asyncio.run(multiply_async([[True, False]], [[3], [4]])) == [[3.0]]
    assert asyncio.run(multiply_async([[2**53, 1]], [[1], [1]])) == [[float(2**53)]]


def test_input_unchanged_and_output_rows_independent() -> None:
    a = [[1], [2]]
    b = [[3, 4]]
    result = asyncio.run(multiply_async(a, b))
    assert a == [[1], [2]]
    assert b == [[3, 4]]
    assert result[0] is not result[1]
    result[0][0] = 999
    assert result[1] == [6, 8]


def test_creating_a_coroutine_does_not_take_a_snapshot() -> None:
    a = [[2]]
    pending = multiply_async(a, [[3]])
    assert inspect.iscoroutine(pending)
    a[0][0] = 4
    assert asyncio.run(pending) == [[12.0]]


def test_started_coroutine_snapshots_before_waiting_for_a_worker() -> None:
    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        loop.set_default_executor(ThreadPoolExecutor(max_workers=1))
        release = threading.Event()
        blocker = loop.run_in_executor(None, release.wait, 10.0)
        a = [[1, 2], [3, 4]]
        b = [[5], [6]]
        pending = asyncio.create_task(multiply_async(a, b))
        try:
            await asyncio.sleep(0)
            assert not pending.done()
            a[0][0] = 999
            a.append([999, 999])
            b[0][0] = -999
            b[1] = [999]
        finally:
            release.set()
            await blocker
        assert await pending == [[17.0], [39.0]]

    asyncio.run(scenario())


def test_concurrent_jobs_preserve_order() -> None:
    async def scenario() -> None:
        results = await asyncio.gather(
            multiply_async([[1, 2]], [[3], [4]]),
            multiply_async([[5]], [[6, 7]]),
            multiply_async([[1], [2]], [[3, 4]]),
        )
        assert list(results) == [[[11.0]], [[30.0, 35.0]], [[3.0, 4.0], [6.0, 8.0]]]

    asyncio.run(scenario())


@pytest.mark.parametrize("bad", [None, 1, True, "1", b"1", {}, object()])
def test_invalid_outer_types(bad: object) -> None:
    with pytest.raises(TypeError, match="a must be a sequence of rows"):
        asyncio.run(multiply_async(bad, [[1]]))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="b must be a sequence of rows"):
        asyncio.run(multiply_async([[1]], bad))  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [None, 1, "1", b"1", {}])
def test_invalid_row_types(bad: object) -> None:
    with pytest.raises(TypeError, match="a rows must be sequences"):
        asyncio.run(multiply_async([bad], [[1]]))  # type: ignore[list-item]
    with pytest.raises(TypeError, match="b rows must be sequences"):
        asyncio.run(multiply_async([[1]], [bad]))  # type: ignore[list-item]


@pytest.mark.parametrize("bad", ["1", None, [], {}, object()])
def test_invalid_element_types(bad: object) -> None:
    with pytest.raises(TypeError, match="incompatible function arguments"):
        asyncio.run(multiply_async([[bad]], [[1]]))  # type: ignore[list-item]
    with pytest.raises(TypeError, match="incompatible function arguments"):
        asyncio.run(multiply_async([[1]], [[bad]]))  # type: ignore[list-item]


@pytest.mark.parametrize(
    ("bad", "message"),
    [
        ([], "must not be empty"),
        ([[]], "rows must not be empty"),
        ([[], []], "rows must not be empty"),
        ([[1, 2], [3]], "rows must have equal lengths"),
        ([[1], []], "rows must have equal lengths"),
    ],
)
def test_invalid_shapes(bad: list[list[float]], message: str) -> None:
    with pytest.raises(ValueError, match=f"a {message}"):
        asyncio.run(multiply_async(bad, [[1]]))
    with pytest.raises(ValueError, match=f"b {message}"):
        asyncio.run(multiply_async([[1]], bad))


def test_incompatible_dimensions() -> None:
    with pytest.raises(ValueError, match="a columns must equal b rows"):
        asyncio.run(multiply_async([[1, 2]], [[3, 4]]))


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_inputs(value: float) -> None:
    with pytest.raises(ValueError, match="a elements must be finite"):
        asyncio.run(multiply_async([[value]], [[1]]))
    with pytest.raises(ValueError, match="b elements must be finite"):
        asyncio.run(multiply_async([[1]], [[value]]))


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ([[sys.float_info.max]], [[2]]),
        ([[sys.float_info.max, sys.float_info.max]], [[1], [1]]),
    ],
)
def test_overflow(a: list[list[float]], b: list[list[float]]) -> None:
    with pytest.raises(OverflowError, match="produced a non-finite value"):
        asyncio.run(multiply_async(a, b))


def test_argument_errors_are_immediate() -> None:
    with pytest.raises(TypeError):
        _ = multiply_async([[1]])  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        _ = multiply_async([[1]], [[1]], [[1]])  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        _ = multiply_async(a=[[1]], c=[[1]])  # type: ignore[call-arg]


def test_content_errors_are_reported_when_awaited() -> None:
    pending = multiply_async([], [[1]])
    assert inspect.iscoroutine(pending)
    with pytest.raises(ValueError, match="a must not be empty"):
        asyncio.run(pending)


def test_failure_does_not_corrupt_another_job() -> None:
    async def scenario() -> None:
        results = await asyncio.gather(
            multiply_async([[sys.float_info.max]], [[2]]),
            multiply_async([[3]], [[7]]),
            return_exceptions=True,
        )
        assert isinstance(results[0], OverflowError)
        assert results[1] == [[21.0]]

    asyncio.run(scenario())


def test_native_work_runs_off_thread_and_releases_the_gil() -> None:
    async def scenario(state: NativeCall) -> int:
        a = [[1.0] * 800 for _ in range(600)]
        b = [[1.0] * 500 for _ in range(800)]
        pending = asyncio.create_task(multiply_async(a, b))
        beats = 0
        while not pending.done():
            await asyncio.sleep(0.001)
            if state.started.is_set() and not state.finished.is_set():
                beats += 1
        result = await pending
        assert (len(result), len(result[0]), result[0][0]) == (600, 500, 800.0)
        return beats

    with observe_native_call() as state:
        beats = asyncio.run(scenario(state))
    assert state.started.is_set() and state.finished.is_set()
    assert state.thread_ids and threading.get_ident() not in state.thread_ids
    assert beats > 0, "no heartbeat while the native call was active"


def test_cancellation_does_not_stop_running_native_work() -> None:
    async def scenario(state: NativeCall) -> None:
        a = [[1.0] * 800 for _ in range(600)]
        b = [[1.0] * 500 for _ in range(800)]
        pending = asyncio.create_task(multiply_async(a, b))
        assert await asyncio.to_thread(state.started.wait, 10.0)
        assert not state.finished.is_set(), (
            "native workload completed before cancellation"
        )
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        assert await asyncio.to_thread(state.finished.wait, 10.0)
        assert await multiply_async([[3]], [[7]]) == [[21.0]]

    with observe_native_call() as state:
        asyncio.run(scenario(state))


def test_real_native_extension() -> None:
    assert _core.multiply.__module__ == "cpp_matrix._core"
    native_path = _core.__file__
    assert native_path is not None
    assert Path(native_path).is_file()
    assert any(
        native_path.endswith(suffix)
        for suffix in importlib.machinery.EXTENSION_SUFFIXES
    )
