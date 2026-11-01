import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from sparkline import svg_sparkline  # noqa: E402


def test_returns_valid_svg_for_normal_series():
    svg = svg_sparkline([1, 3, 2, 5, 4], width=80, height=24)
    assert svg.strip().startswith("<svg")
    assert svg.strip().endswith("</svg>")
    assert 'width="80"' in svg
    assert 'height="24"' in svg


def test_empty_series_returns_empty_svg_without_crashing():
    svg = svg_sparkline([])
    assert svg.strip().startswith("<svg")
    assert "polyline" not in svg


def test_single_value_returns_empty_svg_without_crashing():
    svg = svg_sparkline([42.0])
    assert svg.strip().startswith("<svg")
    assert "polyline" not in svg


def test_flat_series_does_not_divide_by_zero():
    # min == max -> span would be 0 without the `or 1.0` guard
    svg = svg_sparkline([5.0, 5.0, 5.0, 5.0])
    assert "polyline" in svg
    assert "nan" not in svg.lower()
    assert "inf" not in svg.lower()


def test_custom_color_is_applied():
    svg = svg_sparkline([1, 2, 3], color="#ff0000")
    assert "#ff0000" in svg
