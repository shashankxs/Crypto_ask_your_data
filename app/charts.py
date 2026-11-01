"""
Plotly figure builders for the technical chart, Fear & Greed gauge, and
comparison-mode overlay. All styled against theme.py's palette/template.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import indicators as ind
import theme

MA_COLORS = {7: theme.ACCENT, 25: theme.ACCENT_2, 50: "#facc15"}


def build_technical_chart(
    price_df: pd.DataFrame,
    ohlc_df: pd.DataFrame | None,
    chart_type: str,
    show_mas: list[int],
    show_bollinger: bool,
    show_rsi: bool,
    show_macd: bool,
    title: str = "",
) -> go.Figure:
    """
    price_df: columns [price_date, price_usd, volume_usd] — daily resolution.
    ohlc_df: columns [candle_time, open, high, low, close] or None/empty —
             ~4-day resolution (see ingest_coingecko_ohlc.py). Only used when
             chart_type == "candlestick" and data is available.
    """
    use_candles = chart_type == "candlestick" and ohlc_df is not None and not ohlc_df.empty
    x_price = ohlc_df["candle_time"] if use_candles else price_df["price_date"]
    close_series = ohlc_df["close"] if use_candles else price_df["price_usd"]

    n_rows = 2 + int(show_rsi) + int(show_macd)  # price + volume always; +RSI +MACD
    row_heights = [0.55, 0.15] + [0.15] * (n_rows - 2)
    specs = [[{"secondary_y": False}] for _ in range(n_rows)]

    fig = make_subplots(
        rows=n_rows,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=row_heights,
        specs=specs,
    )

    # --- Row 1: price (candlestick or line/area) ---
    if use_candles:
        fig.add_trace(
            go.Candlestick(
                x=ohlc_df["candle_time"], open=ohlc_df["open"], high=ohlc_df["high"],
                low=ohlc_df["low"], close=ohlc_df["close"], name="Price",
                increasing_line_color=theme.GOOD, decreasing_line_color=theme.CRITICAL,
                increasing_fillcolor=theme.GOOD, decreasing_fillcolor=theme.CRITICAL,
            ),
            row=1, col=1,
        )
    elif chart_type == "area":
        fig.add_trace(
            go.Scatter(
                x=price_df["price_date"], y=price_df["price_usd"], mode="lines", name="Price",
                line=dict(color=theme.ACCENT, width=2),
                fill="tozeroy", fillcolor="rgba(91,140,255,0.12)",
            ),
            row=1, col=1,
        )
    else:
        fig.add_trace(
            go.Scatter(
                x=price_df["price_date"], y=price_df["price_usd"], mode="lines", name="Price",
                line=dict(color=theme.ACCENT, width=2),
            ),
            row=1, col=1,
        )

    # --- Overlays: moving averages + Bollinger Bands (always computed on the
    # daily-close series, since MAs/BB are conventionally close-price-based
    # even for a candlestick chart) ---
    for window in show_mas:
        ma = ind.moving_average(price_df["price_usd"], window)
        fig.add_trace(
            go.Scatter(
                x=price_df["price_date"], y=ma, mode="lines", name=f"MA{window}",
                line=dict(color=MA_COLORS.get(window, theme.TEXT_MUTED), width=1.4),
            ),
            row=1, col=1,
        )

    if show_bollinger:
        upper, mid, lower = ind.bollinger_bands(price_df["price_usd"])
        fig.add_trace(
            go.Scatter(x=price_df["price_date"], y=upper, mode="lines", name="BB Upper",
                       line=dict(color=theme.TEXT_MUTED, width=1, dash="dot"), showlegend=False),
            row=1, col=1,
        )
        fig.add_trace(
            go.Scatter(x=price_df["price_date"], y=lower, mode="lines", name="Bollinger Bands",
                       line=dict(color=theme.TEXT_MUTED, width=1, dash="dot"),
                       fill="tonexty", fillcolor="rgba(163,163,176,0.07)"),
            row=1, col=1,
        )

    # --- Row 2: volume ---
    if "daily_return_pct" in price_df.columns:
        vol_colors = [theme.GOOD if r is not None and r >= 0 else theme.CRITICAL
                      for r in price_df["daily_return_pct"].fillna(0)]
    else:
        vol_colors = theme.ACCENT
    fig.add_trace(
        go.Bar(x=price_df["price_date"], y=price_df["volume_usd"], name="Volume",
               marker=dict(color=vol_colors, opacity=0.65), showlegend=False),
        row=2, col=1,
    )

    next_row = 3
    if show_rsi:
        rsi_series = ind.rsi(price_df["price_usd"])
        fig.add_trace(
            go.Scatter(x=price_df["price_date"], y=rsi_series, mode="lines", name="RSI(14)",
                       line=dict(color=theme.ACCENT_2, width=1.6)),
            row=next_row, col=1,
        )
        fig.add_hline(y=70, line=dict(color=theme.CRITICAL, width=1, dash="dash"), row=next_row, col=1)
        fig.add_hline(y=30, line=dict(color=theme.GOOD, width=1, dash="dash"), row=next_row, col=1)
        fig.update_yaxes(range=[0, 100], row=next_row, col=1, title_text="RSI")
        next_row += 1

    if show_macd:
        macd_line, signal_line, hist = ind.macd(price_df["price_usd"])
        hist_colors = [theme.GOOD if v >= 0 else theme.CRITICAL for v in hist.fillna(0)]
        fig.add_trace(
            go.Bar(x=price_df["price_date"], y=hist, name="MACD Hist",
                   marker=dict(color=hist_colors, opacity=0.6), showlegend=False),
            row=next_row, col=1,
        )
        fig.add_trace(
            go.Scatter(x=price_df["price_date"], y=macd_line, mode="lines", name="MACD",
                       line=dict(color=theme.ACCENT, width=1.5)),
            row=next_row, col=1,
        )
        fig.add_trace(
            go.Scatter(x=price_df["price_date"], y=signal_line, mode="lines", name="Signal",
                       line=dict(color=theme.CRITICAL, width=1.5)),
            row=next_row, col=1,
        )
        fig.update_yaxes(title_text="MACD", row=next_row, col=1)

    fig.update_layout(
        template=theme.plotly_dark_template(),
        height=420 + 110 * (n_rows - 2),
        title=title,
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=10, r=10, t=50 if title else 30, b=10),
    )
    for r in range(1, n_rows + 1):
        fig.update_xaxes(showspikes=True, spikemode="across", spikesnap="cursor", row=r, col=1)
    fig.update_yaxes(title_text="Price (USD)", row=1, col=1)
    fig.update_yaxes(title_text="Volume", row=2, col=1)
    return fig


def build_comparison_chart(series_by_symbol: dict[str, pd.DataFrame]) -> go.Figure:
    """Each df has columns [price_date, price_usd]; normalized to % change from first value."""
    fig = go.Figure()
    for i, (symbol, df) in enumerate(series_by_symbol.items()):
        if df.empty:
            continue
        base = df["price_usd"].iloc[0]
        normalized = (df["price_usd"] / base - 1) * 100
        fig.add_trace(
            go.Scatter(
                x=df["price_date"], y=normalized, mode="lines", name=symbol,
                line=dict(color=theme.CATEGORICAL[i % len(theme.CATEGORICAL)], width=2),
            )
        )
    fig.add_hline(y=0, line=dict(color=theme.BASELINE, width=1))
    fig.update_layout(
        template=theme.plotly_dark_template(),
        height=420,
        yaxis_title="% change from range start",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    return fig


def build_fear_greed_gauge(value: float, label: str) -> go.Figure:
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=value,
            number=dict(suffix="", font=dict(size=36, color=theme.TEXT_PRIMARY)),
            title=dict(text=label, font=dict(size=14, color=theme.TEXT_SECONDARY)),
            gauge=dict(
                axis=dict(range=[0, 100], tickcolor=theme.TEXT_MUTED, tickfont=dict(color=theme.TEXT_MUTED)),
                bar=dict(color=theme.ACCENT, thickness=0.25),
                bgcolor=theme.SURFACE_RAISED,
                borderwidth=0,
                steps=[
                    dict(range=[0, 25], color="rgba(232,99,122,0.35)"),
                    dict(range=[25, 45], color="rgba(245,166,35,0.3)"),
                    dict(range=[45, 55], color="rgba(163,163,176,0.25)"),
                    dict(range=[55, 75], color="rgba(57,230,187,0.25)"),
                    dict(range=[75, 100], color="rgba(57,230,187,0.45)"),
                ],
            ),
        )
    )
    fig.update_layout(
        template=theme.plotly_dark_template(),
        height=220,
        margin=dict(l=20, r=20, t=40, b=10),
    )
    return fig
