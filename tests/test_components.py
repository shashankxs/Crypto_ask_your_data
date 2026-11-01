"""
Regression tests for a real bug: any blank (or whitespace-only) line inside
an HTML string passed to st.markdown(unsafe_allow_html=True) prematurely
ends CommonMark's HTML-block parsing, so everything after it gets escaped
and rendered as literal text instead of markup. It hit the "Tracked Market
Cap" KPI card specifically (the only card combining no delta with a
sparkline, which produced an empty placeholder line followed by the
sparkline's own leading blank line).

These tests assert the invariant directly — no blank lines — rather than
just re-checking the one scenario that happened to surface it, so the next
new card/component shape can't reintroduce the same class of bug.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from components import stat_card_html  # noqa: E402
from sparkline import svg_sparkline  # noqa: E402


def assert_no_blank_lines(html: str) -> None:
    for line in html.splitlines():
        assert line.strip() != "", f"blank line found in HTML fragment:\n{html}"


def test_sparkline_output_has_no_blank_lines():
    assert_no_blank_lines(svg_sparkline([1, 2, 3, 4, 5]))


def test_sparkline_empty_case_has_no_blank_lines():
    assert_no_blank_lines(svg_sparkline([]))


def test_stat_card_without_delta_or_spark_has_no_blank_lines():
    assert_no_blank_lines(stat_card_html("Label", "$1.00"))


def test_stat_card_with_spark_but_no_delta_has_no_blank_lines():
    # This exact combination (delta=None + spark_values set) is what broke
    # the Tracked Market Cap card.
    html = stat_card_html("Tracked Market Cap", "$2.5T", spark_values=[1.0, 2.0, 3.0, 2.5])
    assert_no_blank_lines(html)
    assert "<svg" in html
    assert "&lt;svg" not in html  # would indicate the SVG got HTML-escaped


def test_stat_card_with_delta_and_spark_has_no_blank_lines():
    html = stat_card_html("Avg 24h", "+1.2%", delta="up", delta_color="#39e6bb", spark_values=[1, 2, 3, 2])
    assert_no_blank_lines(html)
    assert "&lt;svg" not in html
