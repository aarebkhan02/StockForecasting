"""
UI/UX Theme and Styling Module for Restaurant RMS Application.
Provides modern, professional styling for Streamlit dashboard and order pages.
Maintains 100% strict compatibility with Streamlit native components without altering business logic.
"""

import streamlit as st

CUSTOM_CSS = """
<style>
/* -------------------------------------------------------------
   1. Typography & Global App Styling
   ------------------------------------------------------------- */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
}

/* App page container padding and max-width */
.block-container {
    padding-top: 1.5rem !important;
    padding-bottom: 3.5rem !important;
    padding-left: 2.25rem !important;
    padding-right: 2.25rem !important;
    max-width: 1440px !important;
}

/* -------------------------------------------------------------
   2. Sidebar Refinement
   ------------------------------------------------------------- */
/* Hide the auto-generated duplicate Streamlit pages list */
[data-testid="stSidebarNav"] {
    display: none !important;
}

/* Sidebar background & border */
[data-testid="stSidebar"] {
    background-color: #f8fafc !important;
    border-right: 1px solid #e2e8f0 !important;
}

[data-testid="stSidebar"] hr {
    margin: 1.25rem 0 !important;
    border-color: #e2e8f0 !important;
}

/* Sidebar Navigation Items */
[data-testid="stSidebar"] .stPageLink a {
    border-radius: 8px !important;
    padding: 0.55rem 0.85rem !important;
    font-weight: 600 !important;
    font-size: 0.875rem !important;
    color: #334155 !important;
    transition: all 0.15s ease-in-out !important;
    border: 1px solid transparent !important;
}

[data-testid="stSidebar"] .stPageLink a:hover {
    background-color: #e2e8f0 !important;
    color: #0f172a !important;
    border-color: #cbd5e1 !important;
}

/* -------------------------------------------------------------
   3. Header & Hero Banners
   ------------------------------------------------------------- */
/* -------------------------------------------------------------
   3. Header & Hero Banners (Light Palette)
   ------------------------------------------------------------- */
.rms-hero-card {
    position: relative;
    overflow: hidden;
    background: #ffffff;
    border-radius: 14px;
    padding: 1.25rem 1.6rem;
    color: #0f172a;
    margin-bottom: 1.4rem;
    box-shadow: 0 2px 10px -2px rgba(15, 23, 42, 0.05), 0 1px 3px rgba(15, 23, 42, 0.03);
    border: 1px solid #e2e8f0;
}

.rms-hero-dashboard {
    background: 
        radial-gradient(circle at 96% 15%, rgba(37, 99, 235, 0.06) 0%, transparent 45%),
        linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
    border-left: 4px solid #2563eb;
}

.rms-hero-order {
    background: 
        radial-gradient(circle at 96% 15%, rgba(245, 158, 11, 0.07) 0%, transparent 45%),
        linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
    border-left: 4px solid #f59e0b;
}

.rms-hero-icon-box {
    width: 44px;
    height: 44px;
    border-radius: 12px;
    background: #ffffff;
    border: 1px solid #e2e8f0;
    box-shadow: 0 2px 6px rgba(15, 23, 42, 0.04);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.45rem;
    flex-shrink: 0;
}

.rms-hero-title {
    font-size: 1.4rem;
    font-weight: 800;
    letter-spacing: -0.02em;
    color: #0f172a;
    margin: 0;
    line-height: 1.25;
}

.rms-hero-subtitle {
    font-size: 0.885rem;
    color: #475569;
    line-height: 1.45;
    margin: 0.4rem 0 0.75rem 0;
}

.rms-hero-subtitle b, .rms-hero-subtitle strong {
    color: #0f172a;
    font-weight: 600;
}

@keyframes rmsPulseRing {
    0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
    70% { transform: scale(1.05); box-shadow: 0 0 0 5px rgba(16, 185, 129, 0); }
    100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
}

.rms-pulse-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background-color: #10b981;
    display: inline-block;
    animation: rmsPulseRing 2s infinite ease-in-out;
}

.rms-badge-group {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.5rem;
    margin-top: 0.5rem;
}

.rms-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.25rem 0.65rem;
    border-radius: 8px;
    font-size: 0.76rem;
    font-weight: 600;
    letter-spacing: 0.01em;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    color: #475569;
    transition: all 0.15s ease;
}

.rms-pill:hover {
    transform: translateY(-1px);
    box-shadow: 0 2px 5px rgba(0, 0, 0, 0.04);
}

.rms-pill-live {
    background-color: #ecfdf5;
    color: #065f46;
    border: 1px solid #a7f3d0;
}

.rms-pill-live:hover {
    background-color: #d1fae5;
    border-color: #6ee7b7;
}

.rms-pill-info {
    background-color: #eff6ff;
    color: #1d4ed8;
    border: 1px solid #bfdbfe;
}

.rms-pill-info:hover {
    background-color: #dbeafe;
    border-color: #93c5fd;
}

.rms-pill-model {
    background-color: #fffbeb;
    color: #92400e;
    border: 1px solid #fde68a;
}

.rms-pill-model:hover {
    background-color: #fef3c7;
    border-color: #fcd34d;
}

.rms-pill-date {
    background-color: #f1f5f9;
    color: #334155;
    border: 1px solid #cbd5e1;
}

.rms-pill-date:hover {
    background-color: #e2e8f0;
    border-color: #94a3b8;
}

/* -------------------------------------------------------------
   4. Section Headers
   ------------------------------------------------------------- */
.rms-section-header {
    display: flex;
    align-items: center;
    gap: 0.65rem;
    margin-top: 1.75rem;
    margin-bottom: 0.3rem;
}

.rms-section-number {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 26px;
    height: 26px;
    border-radius: 6px;
    background-color: #2563eb;
    color: #ffffff;
    font-size: 0.825rem;
    font-weight: 700;
}

.rms-section-title {
    font-size: 1.25rem;
    font-weight: 700;
    color: #0f172a;
    margin: 0;
    letter-spacing: -0.015em;
}

.rms-section-desc {
    font-size: 0.875rem;
    color: #64748b;
    margin-bottom: 1.15rem;
    line-height: 1.45;
}

/* -------------------------------------------------------------
   5. KPI Metric Cards (Clean CSS-Only Accents)
   ------------------------------------------------------------- */
[data-testid="stMetric"] {
    background-color: #ffffff !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 12px !important;
    padding: 1.1rem 1.25rem !important;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04), 0 1px 2px rgba(0, 0, 0, 0.02) !important;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
}

[data-testid="stMetric"]:hover {
    box-shadow: 0 4px 8px -2px rgba(0, 0, 0, 0.08) !important;
    border-color: #cbd5e1 !important;
}

[data-testid="stMetricLabel"] {
    font-size: 0.775rem !important;
    font-weight: 600 !important;
    color: #64748b !important;
    text-transform: uppercase !important;
    letter-spacing: 0.04em !important;
}

[data-testid="stMetricValue"] {
    font-size: 1.95rem !important;
    font-weight: 800 !important;
    color: #0f172a !important;
    letter-spacing: -0.02em !important;
    line-height: 1.2 !important;
}

/* Target 5-column overview KPIs by column index */
div[data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) > div[data-testid="column"]:nth-child(1) [data-testid="stMetric"] {
    border-left: 4px solid #6366f1 !important;
    background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%) !important;
}

div[data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) > div[data-testid="column"]:nth-child(2) [data-testid="stMetric"] {
    border-left: 4px solid #ef4444 !important;
    background: linear-gradient(180deg, #ffffff 0%, #fff5f5 100%) !important;
}
div[data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) > div[data-testid="column"]:nth-child(2) [data-testid="stMetricValue"] {
    color: #dc2626 !important;
}

div[data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) > div[data-testid="column"]:nth-child(3) [data-testid="stMetric"] {
    border-left: 4px solid #f59e0b !important;
    background: linear-gradient(180deg, #ffffff 0%, #fffdf5 100%) !important;
}
div[data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) > div[data-testid="column"]:nth-child(3) [data-testid="stMetricValue"] {
    color: #d97706 !important;
}

div[data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) > div[data-testid="column"]:nth-child(4) [data-testid="stMetric"] {
    border-left: 4px solid #10b981 !important;
    background: linear-gradient(180deg, #ffffff 0%, #f0fdf4 100%) !important;
}
div[data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) > div[data-testid="column"]:nth-child(4) [data-testid="stMetricValue"] {
    color: #059669 !important;
}

div[data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) > div[data-testid="column"]:nth-child(5) [data-testid="stMetric"] {
    border-left: 4px solid #2563eb !important;
    background: linear-gradient(180deg, #ffffff 0%, #eff6ff 100%) !important;
}
div[data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) > div[data-testid="column"]:nth-child(5) [data-testid="stMetricValue"] {
    color: #2563eb !important;
}

/* -------------------------------------------------------------
   5b. Clickable KPI Container Cards
   ------------------------------------------------------------- */
div[data-testid="column"]:has(.kpi-col-marker) [data-testid="stMetric"] {
    border: none !important;
    background: transparent !important;
    padding: 0 !important;
    box-shadow: none !important;
}

div[data-testid="column"]:has(.kpi-col-marker) [data-testid="stVerticalBlockBorderWrapper"] {
    background-color: #ffffff !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 12px !important;
    padding: 1.1rem 1.15rem 0.95rem 1.15rem !important;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04), 0 1px 2px rgba(0, 0, 0, 0.02) !important;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
}

div[data-testid="column"]:has(.kpi-col-marker) [data-testid="stVerticalBlockBorderWrapper"]:hover {
    box-shadow: 0 6px 14px -2px rgba(0, 0, 0, 0.1), 0 2px 4px rgba(0, 0, 0, 0.04) !important;
    border-color: #cbd5e1 !important;
    transform: translateY(-2px);
}

/* Color accents on container cards */
div[data-testid="column"]:has(.kpi-col-1) [data-testid="stVerticalBlockBorderWrapper"] {
    border-left: 4px solid #6366f1 !important;
    background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%) !important;
}

div[data-testid="column"]:has(.kpi-col-2) [data-testid="stVerticalBlockBorderWrapper"] {
    border-left: 4px solid #ef4444 !important;
    background: linear-gradient(180deg, #ffffff 0%, #fff5f5 100%) !important;
}
div[data-testid="column"]:has(.kpi-col-2) [data-testid="stMetricValue"] {
    color: #dc2626 !important;
}

div[data-testid="column"]:has(.kpi-col-3) [data-testid="stVerticalBlockBorderWrapper"] {
    border-left: 4px solid #f59e0b !important;
    background: linear-gradient(180deg, #ffffff 0%, #fffdf5 100%) !important;
}
div[data-testid="column"]:has(.kpi-col-3) [data-testid="stMetricValue"] {
    color: #d97706 !important;
}

div[data-testid="column"]:has(.kpi-col-4) [data-testid="stVerticalBlockBorderWrapper"] {
    border-left: 4px solid #10b981 !important;
    background: linear-gradient(180deg, #ffffff 0%, #f0fdf4 100%) !important;
}
div[data-testid="column"]:has(.kpi-col-4) [data-testid="stMetricValue"] {
    color: #059669 !important;
}

div[data-testid="column"]:has(.kpi-col-5) [data-testid="stVerticalBlockBorderWrapper"] {
    border-left: 4px solid #2563eb !important;
    background: linear-gradient(180deg, #ffffff 0%, #eff6ff 100%) !important;
}
div[data-testid="column"]:has(.kpi-col-5) [data-testid="stMetricValue"] {
    color: #2563eb !important;
}

/* Active selected KPI card highlight */
div[data-testid="column"]:has(.kpi-active-marker) [data-testid="stVerticalBlockBorderWrapper"] {
    outline: 2px solid #2563eb !important;
    box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.18), 0 6px 14px -2px rgba(0, 0, 0, 0.1) !important;
}

/* Compact button inside KPI card */
div[data-testid="column"]:has(.kpi-col-marker) button {
    font-size: 0.775rem !important;
    font-weight: 600 !important;
    padding: 0.35rem 0.5rem !important;
    border-radius: 6px !important;
    margin-top: 0.35rem !important;
}

/* -------------------------------------------------------------
   6. Form Controls, Inputs & Selects
   ------------------------------------------------------------- */
div[data-baseweb="input"] {
    border-radius: 8px !important;
    border-color: #cbd5e1 !important;
}

div[data-baseweb="select"] {
    border-radius: 8px !important;
}

div[data-baseweb="input"]:focus-within,
div[data-baseweb="select"]:focus-within {
    border-color: #2563eb !important;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.15) !important;
}

/* -------------------------------------------------------------
   7. Buttons Styling
   ------------------------------------------------------------- */
button[kind="primary"] {
    background: #2563eb !important;
    color: #ffffff !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    border: none !important;
    padding: 0.55rem 1.25rem !important;
    box-shadow: 0 1px 2px rgba(37, 99, 235, 0.2) !important;
    transition: all 0.15s ease-in-out !important;
}

button[kind="primary"]:hover {
    background: #1d4ed8 !important;
    box-shadow: 0 4px 6px -1px rgba(37, 99, 235, 0.3) !important;
    transform: translateY(-1px);
}

button[kind="secondary"] {
    background-color: #ffffff !important;
    color: #334155 !important;
    border: 1px solid #cbd5e1 !important;
    border-radius: 8px !important;
    font-weight: 500 !important;
    transition: all 0.15s ease-in-out !important;
}

button[kind="secondary"]:hover {
    background-color: #f8fafc !important;
    border-color: #94a3b8 !important;
    color: #0f172a !important;
}

/* Download button */
.stDownloadButton button {
    border-radius: 8px !important;
    font-weight: 600 !important;
    border: 1px solid #cbd5e1 !important;
    background: #ffffff !important;
    color: #1e293b !important;
    padding: 0.5rem 1rem !important;
    transition: all 0.15s ease-in-out !important;
}

.stDownloadButton button:hover {
    background: #f1f5f9 !important;
    border-color: #94a3b8 !important;
}

/* -------------------------------------------------------------
   8. Tables and DataFrames
   ------------------------------------------------------------- */
[data-testid="stDataFrame"] {
    border: 1px solid #e2e8f0 !important;
    border-radius: 10px !important;
    overflow: hidden !important;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03) !important;
}

/* -------------------------------------------------------------
   9. Alerts & Info Banners
   ------------------------------------------------------------- */
[data-testid="stAlert"] {
    border-radius: 10px !important;
    border-width: 1px !important;
    font-size: 0.9rem !important;
    padding: 0.85rem 1.15rem !important;
}

/* -------------------------------------------------------------
   10. Chart Titles
   ------------------------------------------------------------- */
.rms-chart-title {
    font-size: 1.05rem;
    font-weight: 700;
    color: #1e293b;
    margin: 0 0 0.2rem 0;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.rms-chart-subtitle {
    font-size: 0.8rem;
    color: #64748b;
    margin-bottom: 0.5rem;
}

/* -------------------------------------------------------------
   11. Metadata Info Box
   ------------------------------------------------------------- */
.rms-meta-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 1rem 1.15rem;
    font-size: 0.825rem;
    color: #475569;
    line-height: 1.5;
}

.rms-meta-card b {
    color: #0f172a;
}
</style>
"""


def inject_custom_css():
    """Inject polished UI styles into current Streamlit page."""
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def style_risk_cell(val):
    """Refined styling for risk status pills in tables."""
    if val == "Critical":
        return (
            "background-color: #fee2e2; color: #991b1b; "
            "font-weight: 700; border-radius: 4px; padding: 2px 6px;"
        )
    elif val == "At Risk":
        return (
            "background-color: #fef3c7; color: #92400e; "
            "font-weight: 700; border-radius: 4px; padding: 2px 6px;"
        )
    elif val == "Sufficient":
        return (
            "background-color: #d1fae5; color: #065f46; "
            "font-weight: 700; border-radius: 4px; padding: 2px 6px;"
        )
    return "background-color: #f1f5f9; color: #475569; font-weight: 500;"


def style_buffer_cell(val):
    """Refined styling for buffer deficit vs adequate."""
    if "Deficit" in str(val):
        return "color: #dc2626; font-weight: 700;"
    return "color: #059669; font-weight: 700;"


def style_availability_cell(val):
    """Refined styling for order page inventory availability."""
    if val == "Available":
        return "color: #059669; font-weight: 700; background-color: #f0fdf4;"
    elif val == "Insufficient":
        return "color: #dc2626; font-weight: 700; background-color: #fef2f2;"
    return ""


def apply_plotly_theme(fig, height=390):
    """
    Apply a consistent modern theme to Plotly figures.
    Provides adequate top margin clearance to prevent legend collisions with titles.
    """
    fig.update_layout(
        template="plotly_white",
        height=height,
        font=dict(
            family="Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
            size=11,
            color="#475569"
        ),
        margin=dict(l=52, r=24, t=32, b=45),
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        hoverlabel=dict(
            bgcolor="#0f172a",
            font_size=12,
            font_color="#ffffff",
            font_family="Inter, sans-serif",
            bordercolor="#1e293b"
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1.0,
            font=dict(size=11, color="#334155"),
            bgcolor="rgba(255, 255, 255, 0.95)",
            bordercolor="#e2e8f0",
            borderwidth=1
        ),
        xaxis=dict(
            showgrid=True,
            gridcolor="#f1f5f9",
            linecolor="#cbd5e1",
            tickfont=dict(size=10, color="#64748b")
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor="#f1f5f9",
            linecolor="#cbd5e1",
            tickfont=dict(size=10, color="#64748b")
        )
    )
    return fig
