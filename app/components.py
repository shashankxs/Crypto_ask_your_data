"""
HTML/CSS components rendered via st.markdown(unsafe_allow_html=True):
ticker tape, KPI stat cards (with an embedded SVG sparkline), the
trading-grid results table (zebra striping + inline sparkline cells), and
a tiny JS snippet binding Cmd+K / Ctrl+K to focus the question input.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

import theme
from sparkline import svg_sparkline


def fmt_usd(value: float) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"${value:,.2f}" if value < 1000 else f"${value:,.0f}"


def fmt_compact(value: float) -> str:
    if value is None or pd.isna(value):
        return "—"
    for threshold, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(value) >= threshold:
            return f"${value / threshold:,.2f}{suffix}"
    return f"${value:,.0f}"


def fmt_pct(value: float) -> str:
    if value is None or pd.isna(value):
        return "—"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:,.2f}%"


def render_ticker_tape(overview_df: pd.DataFrame, n: int = 15) -> None:
    rows = overview_df.head(n)
    items = []
    for _, r in rows.iterrows():
        color = theme.pct_color(r["price_change_pct_24h"])
        items.append(
            f'<span class="ticker-item"><b>{r["symbol"]}</b> {fmt_usd(r["price_usd"])} '
            f'<span style="color:{color}">{fmt_pct(r["price_change_pct_24h"])}</span></span>'
        )
    track_html = "".join(items)
    # Duplicate the track once so the CSS translateX(-50%) loop is seamless.
    st.markdown(
        f'<div class="ticker-wrap"><div class="ticker-track">{track_html}{track_html}</div></div>',
        unsafe_allow_html=True,
    )


def stat_card_html(label: str, value: str, delta: str | None = None, delta_color: str = theme.TEXT_MUTED,
                    spark_values: list[float] | None = None, spark_color: str = theme.ACCENT) -> str:
    delta_html = f'<div class="stat-delta" style="color:{delta_color}">{delta}</div>' if delta else ""
    spark_html = ""
    if spark_values and len(spark_values) >= 2:
        spark_html = f'<div class="stat-spark">{svg_sparkline(spark_values, width=160, height=36, color=spark_color)}</div>'
    return f"""
    <div class="glass-card">
        <div class="stat-label">{label}</div>
        <div class="stat-value">{value}</div>
        {delta_html}
        {spark_html}
    </div>
    """


def skeleton_block(height_px: int = 90) -> str:
    return f'<div class="skeleton" style="height:{height_px}px;"></div>'


def render_trading_grid(df: pd.DataFrame, sparklines: dict[str, list[float]] | None = None) -> None:
    """A hand-built HTML table instead of st.dataframe: gives full control
    over zebra striping, per-row hover, and an inline sparkline cell per
    coin — none of which st.dataframe's column_config supports together."""
    sparklines = sparklines or {}
    headers = ["", "Coin", "Price", "24h %", "7d %", "Market Cap", "Trend"]
    rows_html = []
    for _, r in df.iterrows():
        color_24h = theme.pct_color(r.get("price_change_pct_24h"))
        color_7d = theme.pct_color(r.get("price_change_pct_7d"))
        spark = sparklines.get(r["coin_id"], [])
        spark_svg = svg_sparkline(spark, width=90, height=28, color=color_24h) if spark else ""
        rows_html.append(
            f"<tr>"
            f'<td><img class="coin-icon" src="{r.get("image_url", "")}" /></td>'
            f'<td><b>{r.get("name", "")}</b> <span style="color:{theme.TEXT_MUTED}">{r.get("symbol", "")}</span></td>'
            f'<td class="mono">{fmt_usd(r.get("price_usd"))}</td>'
            f'<td class="mono" style="color:{color_24h}">{fmt_pct(r.get("price_change_pct_24h"))}</td>'
            f'<td class="mono" style="color:{color_7d}">{fmt_pct(r.get("price_change_pct_7d"))}</td>'
            f'<td class="mono">{fmt_compact(r.get("market_cap_usd"))}</td>'
            f"<td>{spark_svg}</td>"
            f"</tr>"
        )
    table_html = (
        '<table class="trading-grid"><thead><tr>'
        + "".join(f"<th>{h}</th>" for h in headers)
        + "</tr></thead><tbody>"
        + "".join(rows_html)
        + "</tbody></table>"
    )
    st.markdown(table_html, unsafe_allow_html=True)


def inject_command_palette_shortcut(input_label: str) -> None:
    """Binds Cmd+K (Mac) / Ctrl+K (Windows/Linux) to focus the question
    input, command-palette style. Implemented as a small inline script
    rather than a pip package (e.g. streamlit-shortcuts): the component
    iframe can reach `window.parent.document` because Streamlit serves
    everything same-origin, so a ~15-line snippet covers it without adding
    a dependency for something this small.
    """
    import streamlit.components.v1 as components

    components.html(
        f"""
        <script>
        (function() {{
            const doc = window.parent.document;
            function focusInput() {{
                const inputs = doc.querySelectorAll('input[aria-label="{input_label}"]');
                if (inputs.length) {{
                    inputs[0].focus();
                    inputs[0].select();
                }}
            }}
            doc.addEventListener('keydown', function(e) {{
                const isK = e.key === 'k' || e.key === 'K';
                if ((e.metaKey || e.ctrlKey) && isK) {{
                    e.preventDefault();
                    focusInput();
                }}
            }});
        }})();
        </script>
        """,
        height=0,
    )
