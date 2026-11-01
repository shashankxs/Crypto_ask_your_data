"""
Palette, typography, and CSS for the dashboard. Centralized here so chart
colors (Plotly) and DOM colors (CSS) never drift apart.
"""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------------------
# Palette — dark-mode steps, validated for colorblind-safe adjacent contrast
# (see dataviz skill references/palette.md). Gains/losses use the fixed
# status pair (never reused for categorical series); the categorical ramp
# is for multi-series overlays (comparison mode, multiple indicators).
# ---------------------------------------------------------------------------
PAGE_PLANE = "#0a0a0f"
SURFACE = "#13131a"
SURFACE_RAISED = "#1a1a24"
GLASS_BORDER = "rgba(255,255,255,0.08)"
GLASS_BORDER_HOVER = "rgba(57,230,187,0.35)"
TEXT_PRIMARY = "#f2f2f5"
TEXT_SECONDARY = "#a3a3b0"
TEXT_MUTED = "#6e6e7d"
GRIDLINE = "#23232e"
BASELINE = "#33333f"

# Electric green / muted red for gains & losses — the one status pair, never
# reused as a categorical series color.
GOOD = "#39e6bb"
CRITICAL = "#e8637a"

ACCENT = "#5b8cff"
ACCENT_2 = "#9b6bff"

CATEGORICAL = ["#5b8cff", "#f5a623", "#39e6bb", "#e8637a", "#9b6bff", "#2dd4bf", "#f472b6", "#facc15"]


def pct_color(value: float | None) -> str:
    if value is None:
        return TEXT_MUTED
    try:
        import pandas as pd

        if pd.isna(value):
            return TEXT_MUTED
    except Exception:
        pass
    return GOOD if value >= 0 else CRITICAL


def inject_css() -> None:
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

        html, body, [class*="css"] {{
            font-family: 'Inter', system-ui, -apple-system, "Segoe UI", sans-serif !important;
        }}
        .mono, .tabular {{
            font-family: 'JetBrains Mono', ui-monospace, monospace !important;
            font-variant-numeric: tabular-nums;
        }}

        .stApp {{
            background:
                radial-gradient(circle at 20% -10%, rgba(91,140,255,0.12) 0%, transparent 45%),
                radial-gradient(circle at 85% 0%, rgba(155,107,255,0.10) 0%, transparent 40%),
                {PAGE_PLANE};
        }}
        #MainMenu, footer, header {{ visibility: hidden; }}
        .block-container {{ padding-top: 1rem; max-width: 1400px; }}

        /* ---------------- Ticker tape ---------------- */
        .ticker-wrap {{
            position: sticky;
            top: 0;
            z-index: 999;
            overflow: hidden;
            background: rgba(19,19,26,0.75);
            backdrop-filter: blur(14px) saturate(140%);
            -webkit-backdrop-filter: blur(14px) saturate(140%);
            border-bottom: 1px solid {GLASS_BORDER};
            padding: 0.55rem 0;
            margin: -1rem -1rem 1.2rem -1rem;
            width: calc(100% + 2rem);
        }}
        .ticker-track {{
            display: flex;
            width: max-content;
            animation: ticker-scroll 42s linear infinite;
        }}
        .ticker-wrap:hover .ticker-track {{ animation-play-state: paused; }}
        @keyframes ticker-scroll {{
            0%   {{ transform: translateX(0); }}
            100% {{ transform: translateX(-50%); }}
        }}
        .ticker-item {{
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            padding: 0 1.4rem;
            white-space: nowrap;
            font-size: 0.86rem;
            color: {TEXT_SECONDARY};
            border-right: 1px solid {GLASS_BORDER};
        }}
        .ticker-item b {{ color: {TEXT_PRIMARY}; font-weight: 600; }}

        /* ---------------- Hero ---------------- */
        .hero-title {{
            font-size: 2.4rem;
            font-weight: 800;
            background: linear-gradient(90deg, {ACCENT} 0%, {ACCENT_2} 55%, {GOOD} 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.15rem;
            letter-spacing: -0.02em;
        }}
        .hero-sub {{
            color: {TEXT_SECONDARY};
            font-size: 1rem;
            margin-bottom: 1.4rem;
        }}

        /* ---------------- Glass cards ---------------- */
        .glass-card {{
            background: linear-gradient(180deg, rgba(255,255,255,0.035), rgba(255,255,255,0.015)), {SURFACE};
            border: 1px solid {GLASS_BORDER};
            border-radius: 18px;
            padding: 1.1rem 1.3rem;
            box-shadow: 0 8px 32px rgba(0,0,0,0.35);
            backdrop-filter: blur(6px);
            transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
        }}
        .glass-card:hover {{
            transform: translateY(-3px);
            border-color: {GLASS_BORDER_HOVER};
            box-shadow: 0 14px 40px rgba(57,230,187,0.08);
        }}
        .stat-label {{
            color: {TEXT_MUTED};
            font-size: 0.74rem;
            text-transform: uppercase;
            letter-spacing: 0.07em;
            font-weight: 600;
            margin-bottom: 0.35rem;
        }}
        .stat-value {{
            color: {TEXT_PRIMARY};
            font-size: 1.55rem;
            font-weight: 700;
            line-height: 1.1;
            font-variant-numeric: tabular-nums;
        }}
        .stat-delta {{
            font-size: 0.88rem;
            font-weight: 600;
            margin-top: 0.3rem;
            font-variant-numeric: tabular-nums;
        }}
        .stat-spark {{ margin-top: 0.5rem; opacity: 0.9; }}

        /* ---------------- Skeleton loading ---------------- */
        .skeleton {{
            border-radius: 18px;
            background: linear-gradient(100deg, {SURFACE} 30%, {SURFACE_RAISED} 50%, {SURFACE} 70%);
            background-size: 200% 100%;
            animation: skeleton-shimmer 1.4s ease-in-out infinite;
            border: 1px solid {GLASS_BORDER};
        }}
        @keyframes skeleton-shimmer {{
            0%   {{ background-position: 200% 0; }}
            100% {{ background-position: -200% 0; }}
        }}

        .section-title {{
            color: {TEXT_PRIMARY};
            font-size: 1.25rem;
            font-weight: 700;
            margin-top: 2rem;
            margin-bottom: 0.85rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}
        .pill {{
            display: inline-block;
            background: {SURFACE_RAISED};
            border: 1px solid {GLASS_BORDER};
            color: {TEXT_SECONDARY};
            border-radius: 999px;
            padding: 0.2rem 0.75rem;
            font-size: 0.76rem;
            margin-right: 0.4rem;
        }}

        /* ---------------- Command-palette input ---------------- */
        div[data-testid="stTextInput"] input {{
            background: {SURFACE_RAISED} !important;
            border: 1px solid {GLASS_BORDER} !important;
            border-radius: 14px !important;
            color: {TEXT_PRIMARY} !important;
            font-size: 1.05rem !important;
            padding: 0.95rem 1.1rem !important;
            box-shadow: 0 8px 28px rgba(0,0,0,0.3);
        }}
        div[data-testid="stTextInput"] input:focus {{
            border-color: {ACCENT} !important;
            box-shadow: 0 0 0 3px rgba(91,140,255,0.25) !important;
        }}
        .kbd-hint {{
            display: inline-flex;
            align-items: center;
            gap: 0.2rem;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.72rem;
            color: {TEXT_MUTED};
            background: {SURFACE_RAISED};
            border: 1px solid {GLASS_BORDER};
            border-radius: 6px;
            padding: 0.1rem 0.4rem;
        }}

        /* ---------------- Buttons / chips ---------------- */
        div[data-testid="stButton"] button {{
            background: {SURFACE_RAISED};
            border: 1px solid {GLASS_BORDER};
            color: {TEXT_SECONDARY};
            border-radius: 999px;
            font-size: 0.84rem;
            padding: 0.4rem 0.95rem;
            transition: all 0.16s cubic-bezier(.2,.8,.2,1);
        }}
        div[data-testid="stButton"] button:hover {{
            border-color: {ACCENT};
            color: {TEXT_PRIMARY};
            background: rgba(91,140,255,0.14);
            transform: translateY(-1px);
        }}
        div[data-testid="stButton"] button[kind="primary"] {{
            background: linear-gradient(90deg, {ACCENT}, {ACCENT_2});
            border: none;
            color: white;
            font-weight: 600;
            padding: 0.65rem 1.7rem;
            box-shadow: 0 6px 20px rgba(91,140,255,0.35);
        }}
        div[data-testid="stButton"] button[kind="primary"]:hover {{
            box-shadow: 0 8px 26px rgba(91,140,255,0.5);
            transform: translateY(-1px);
        }}

        /* ---------------- Trading-grid table ---------------- */
        .trading-grid {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; }}
        .trading-grid th {{
            text-align: left;
            color: {TEXT_MUTED};
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            font-weight: 600;
            padding: 0.55rem 0.8rem;
            border-bottom: 1px solid {GLASS_BORDER};
        }}
        .trading-grid td {{
            padding: 0.5rem 0.8rem;
            color: {TEXT_PRIMARY};
            border-bottom: 1px solid rgba(255,255,255,0.03);
            font-variant-numeric: tabular-nums;
            vertical-align: middle;
        }}
        .trading-grid tr:nth-child(even) td {{ background: rgba(255,255,255,0.015); }}
        .trading-grid tr:hover td {{ background: rgba(91,140,255,0.06); }}
        .trading-grid img.coin-icon {{ width: 20px; height: 20px; border-radius: 50%; vertical-align: middle; margin-right: 0.5rem; }}

        .footer-note {{
            color: {TEXT_MUTED};
            font-size: 0.8rem;
            margin-top: 3rem;
            text-align: center;
        }}

        /* Narrower viewports: tighter padding, smaller hero */
        @media (max-width: 640px) {{
            .hero-title {{ font-size: 1.8rem; }}
            .block-container {{ padding-left: 0.6rem; padding-right: 0.6rem; }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def plotly_dark_template() -> go.layout.Template:
    axis_common = dict(
        gridcolor=GRIDLINE,
        zerolinecolor=BASELINE,
        linecolor=BASELINE,
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikecolor=TEXT_MUTED,
        spikethickness=1,
    )
    return go.layout.Template(
        layout=go.Layout(
            paper_bgcolor=SURFACE,
            plot_bgcolor=SURFACE,
            font=dict(color=TEXT_PRIMARY, family="Inter, sans-serif"),
            colorway=CATEGORICAL,
            xaxis=axis_common,
            yaxis=dict(gridcolor=GRIDLINE, zerolinecolor=BASELINE, linecolor=BASELINE),
            legend=dict(bgcolor="rgba(0,0,0,0)"),
            margin=dict(l=10, r=10, t=30, b=10),
            hoverlabel=dict(bgcolor=SURFACE_RAISED, font_color=TEXT_PRIMARY, bordercolor=GLASS_BORDER,
                             font_family="JetBrains Mono, monospace"),
            hovermode="x unified",
        )
    )
