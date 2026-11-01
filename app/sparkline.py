"""
Inline SVG sparklines, hand-rolled instead of embedding dozens of tiny
Plotly figures. Rendering 25+ Plotly charts in a table (one per row) is
slow and heavy; a plain SVG polyline is a few bytes of markup and instant
to render, which matters once this is used in a KPI card AND in every row
of the market table.
"""
from __future__ import annotations


def svg_sparkline(
    values: list[float],
    width: int = 100,
    height: int = 32,
    color: str = "#3987e5",
    stroke_width: float = 1.75,
) -> str:
    if not values or len(values) < 2:
        return f'<svg width="{width}" height="{height}"></svg>'

    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    n = len(values)
    pad = stroke_width

    def point(i: int, v: float) -> tuple[float, float]:
        x = pad + (i / (n - 1)) * (width - 2 * pad)
        y = pad + (1 - (v - lo) / span) * (height - 2 * pad)
        return x, y

    points = [point(i, v) for i, v in enumerate(values)]
    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)

    # Light fill under the line for a bit of depth, matching the line color
    # at low opacity rather than a separate fill color.
    fill_path = (
        f"{pad:.1f},{height - pad:.1f} " + path + f" {width - pad:.1f},{height - pad:.1f}"
    )

    return f"""
    <svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" style="display:block">
        <polygon points="{fill_path}" fill="{color}" fill-opacity="0.12" stroke="none" />
        <polyline points="{path}" fill="none" stroke="{color}" stroke-width="{stroke_width}"
                  stroke-linejoin="round" stroke-linecap="round" />
    </svg>
    """
