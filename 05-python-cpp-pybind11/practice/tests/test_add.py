import importlib.machinery
import math
import sys
from pathlib import Path

import pytest

from cpp_add import _core, add


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [(2, 3, 5.0), (-2, -3, -5.0), (-2, 3, 1.0), (0, 0, 0.0)],
)
def test_numbers(a: float, b: float, expected: float) -> None:
    result = add(a, b)
    assert result == expected
    assert isinstance(result, float)


def test_decimal() -> None:
    assert add(0.1, 0.2) == pytest.approx(0.3)


def test_keywords() -> None:
    assert add(b=3, a=2) == 5.0


def test_bool_uses_default_numeric_conversion() -> None:
    assert add(True, False) == 1.0


def test_integer_precision_is_double_precision() -> None:
    assert add(2**53, 1) == float(2**53)


def test_nan() -> None:
    assert math.isnan(add(math.nan, 1))


def test_infinity() -> None:
    assert add(math.inf, 1) == math.inf
    assert add(-math.inf, 1) == -math.inf
    assert math.isnan(add(math.inf, -math.inf))


def test_floating_point_overflow() -> None:
    assert add(sys.float_info.max, sys.float_info.max) == math.inf


@pytest.mark.parametrize("bad", ["3", None, [], {}, object()])
def test_invalid_types(bad: object) -> None:
    with pytest.raises(TypeError, match="incompatible function arguments"):
        add(bad, 1)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="incompatible function arguments"):
        add(1, bad)  # type: ignore[arg-type]


def test_missing_argument() -> None:
    with pytest.raises(TypeError, match="incompatible function arguments"):
        add(1)  # type: ignore[call-arg]


def test_extra_argument() -> None:
    with pytest.raises(TypeError, match="incompatible function arguments"):
        add(1, 2, 3)  # type: ignore[call-arg]


def test_unknown_keyword() -> None:
    with pytest.raises(TypeError, match="incompatible function arguments"):
        add(a=1, c=2)  # type: ignore[call-arg]


def test_real_native_extension() -> None:
    assert add is _core.add
    assert add.__module__ == "cpp_add._core"
    native_path = _core.__file__
    assert native_path is not None
    assert Path(native_path).is_file()
    assert any(
        native_path.endswith(suffix)
        for suffix in importlib.machinery.EXTENSION_SUFFIXES
    )
