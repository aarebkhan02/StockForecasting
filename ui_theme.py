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
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
}

h1, h2, h3, h4, .rms-hero-title, .rms-section-title, [data-testid="stMetricValue"] {
    font-family: 'Plus Jakarta Sans', 'Inter', sans-serif !important;
}

[data-testid="stAppViewContainer"] {
    background-color: #f8fafc !important;
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
    background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%) !important;
    border-right: 1px solid #e2e8f0 !important;
}

[data-testid="stSidebar"] hr {
    margin: 1.25rem 0 !important;
    border-color: #e2e8f0 !important;
}

/* Sidebar Navigation Items */
[data-testid="stSidebar"] .stPageLink a {
    border-radius: 9px !important;
    padding: 0.6rem 0.9rem !important;
    font-weight: 600 !important;
    font-size: 0.875rem !important;
    color: #334155 !important;
    transition: all 0.15s ease-in-out !important;
    border: 1px solid transparent !important;
}

[data-testid="stSidebar"] .stPageLink a:hover {
    background-color: #ffffff !important;
    color: #2563eb !important;
    border-color: #cbd5e1 !important;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.04) !important;
    transform: translateY(-1px);
}

/* -------------------------------------------------------------
   3. Header & Hero Banners (Rich Professional Web Design)
   ------------------------------------------------------------- */
.rms-hero-card {
    position: relative;
    overflow: hidden;
    background: #ffffff;
    border-radius: 16px;
    padding: 1.35rem 1.75rem;
    color: #0f172a;
    margin-bottom: 1.5rem;
    box-shadow: 0 4px 20px -2px rgba(99, 102, 241, 0.08), 0 2px 6px -1px rgba(15, 23, 42, 0.03);
    border: 1px solid #e2e8f0;
}

.rms-hero-dashboard {
    background: 
        radial-gradient(circle at 92% 12%, rgba(99, 102, 241, 0.09) 0%, transparent 45%),
        radial-gradient(circle at 8% 88%, rgba(14, 165, 233, 0.07) 0%, transparent 40%),
        #ffffff;
    border-top: 3.5px solid #2563eb;
    border-left: 1px solid #e2e8f0;
}

.rms-hero-dashboard::before {
    content: "";
    position: absolute;
    top: -3.5px;
    left: 0;
    right: 0;
    height: 3.5px;
    background: linear-gradient(90deg, #2563eb 0%, #6366f1 35%, #8b5cf6 65%, #06b6d4 100%);
    pointer-events: none;
}

.rms-hero-order {
    background: 
        radial-gradient(circle at 92% 12%, rgba(245, 158, 11, 0.09) 0%, transparent 45%),
        radial-gradient(circle at 8% 88%, rgba(239, 68, 68, 0.06) 0%, transparent 40%),
        #ffffff;
    border-top: 3.5px solid #f59e0b;
    border-left: 1px solid #e2e8f0;
}

.rms-hero-order::before {
    content: "";
    position: absolute;
    top: -3.5px;
    left: 0;
    right: 0;
    height: 3.5px;
    background: linear-gradient(90deg, #f59e0b 0%, #ea580c 45%, #e11d48 100%);
    pointer-events: none;
}

.rms-hero-icon-box {
    width: 44px;
    height: 44px;
    border-radius: 12px;
    background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
    border: 1px solid #bfdbfe;
    box-shadow: 0 4px 10px rgba(37, 99, 235, 0.12);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.45rem;
    flex-shrink: 0;
}

.rms-hero-title {
    font-size: 1.45rem;
    font-weight: 800;
    letter-spacing: -0.025em;
    color: #0f172a;
    margin: 0;
    line-height: 1.25;
}

.rms-hero-subtitle {
    font-size: 0.9rem;
    color: #475569;
    line-height: 1.5;
    margin: 0.4rem 0 0.85rem 0;
}

.rms-hero-subtitle b, .rms-hero-subtitle strong {
    color: #0f172a;
    font-weight: 600;
}

@keyframes rmsPulseRing {
    0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
    70% { transform: scale(1.05); box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }
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
    gap: 0.55rem;
    margin-top: 0.65rem;
}

.rms-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.28rem 0.72rem;
    border-radius: 8px;
    font-size: 0.775rem;
    font-weight: 600;
    letter-spacing: 0.01em;
    transition: all 0.18s cubic-bezier(0.16, 1, 0.3, 1);
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

.rms-pill:hover {
    transform: translateY(-1.5px);
    box-shadow: 0 4px 10px rgba(0, 0, 0, 0.08);
}

.rms-pill-live {
    background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%) !important;
    color: #047857 !important;
    border: none !important;
    box-shadow: 0 2px 6px rgba(16, 185, 129, 0.15) !important;
}

.rms-pill-live:hover {
    background: #a7f3d0 !important;
}

.rms-pill-info {
    background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%) !important;
    color: #1d4ed8 !important;
    border: none !important;
    box-shadow: 0 2px 6px rgba(37, 99, 235, 0.15) !important;
}

.rms-pill-info:hover {
    background: #bfdbfe !important;
}

.rms-pill-model {
    background: linear-gradient(135deg, #dcfce7 0%, #86efac 100%) !important;
    color: #14532d !important;
    border: none !important;
    box-shadow: 0 2px 8px rgba(34, 197, 94, 0.25) !important;
}

.rms-pill-model:hover {
    background: #86efac !important;
}

.rms-pill-date {
    background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%) !important;
    color: #78350f !important;
    border: none !important;
    box-shadow: 0 2px 8px rgba(245, 158, 11, 0.25) !important;
}

.rms-pill-date:hover {
    background: #fde68a !important;
}

/* -------------------------------------------------------------
   4. Section Headers (Rich Modern Badges)
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
    width: 28px;
    height: 28px;
    border-radius: 8px;
    background: linear-gradient(135deg, #2563eb 0%, #4f46e5 100%);
    color: #ffffff;
    font-size: 0.825rem;
    font-weight: 800;
    font-family: 'Plus Jakarta Sans', sans-serif;
    box-shadow: 0 3px 8px rgba(37, 99, 235, 0.35);
}

.rms-section-title {
    font-size: 1.25rem;
    font-weight: 800;
    color: #0f172a;
    margin: 0;
    letter-spacing: -0.015em;
}

.rms-section-desc {
    font-size: 0.885rem;
    color: #64748b;
    margin-bottom: 1.15rem;
    line-height: 1.45;
}

/* -------------------------------------------------------------
   5. KPI Metric Cards (Rich Palette & Hover Halo)
   ------------------------------------------------------------- */
[data-testid="stMetric"] {
    background-color: #ffffff !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 14px !important;
    padding: 1.15rem 1.25rem !important;
    box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04) !important;
    transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1) !important;
}

[data-testid="stMetric"]:hover {
    box-shadow: 0 8px 18px -2px rgba(15, 23, 42, 0.08) !important;
    border-color: #cbd5e1 !important;
}

[data-testid="stMetricLabel"] {
    font-size: 0.775rem !important;
    font-weight: 700 !important;
    color: #64748b !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
}

[data-testid="stMetricValue"] {
    font-size: 1.95rem !important;
    font-weight: 800 !important;
    color: #0f172a !important;
    letter-spacing: -0.025em !important;
    line-height: 1.2 !important;
}

/* -------------------------------------------------------------
   5b. Clickable KPI Container Cards (Rich Jewel Accents)
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
    border-radius: 14px !important;
    padding: 1.15rem 1.2rem 1rem 1.2rem !important;
    box-shadow: 0 3px 10px rgba(15, 23, 42, 0.04), 0 1px 2px rgba(15, 23, 42, 0.02) !important;
    transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1) !important;
}

div[data-testid="column"]:has(.kpi-col-marker) [data-testid="stVerticalBlockBorderWrapper"]:hover {
    box-shadow: 0 10px 22px -3px rgba(15, 23, 42, 0.1), 0 4px 6px -2px rgba(15, 23, 42, 0.04) !important;
    border-color: #cbd5e1 !important;
    transform: translateY(-3px);
}

/* Color accents on container cards */
div[data-testid="column"]:has(.kpi-col-1) [data-testid="stVerticalBlockBorderWrapper"] {
    border-top: 3.5px solid #6366f1 !important;
    background: linear-gradient(180deg, rgba(99, 102, 241, 0.04) 0%, #ffffff 100%) !important;
}

div[data-testid="column"]:has(.kpi-col-2) [data-testid="stVerticalBlockBorderWrapper"] {
    border-top: 3.5px solid #f43f5e !important;
    background: linear-gradient(180deg, rgba(244, 63, 94, 0.05) 0%, #ffffff 100%) !important;
}
div[data-testid="column"]:has(.kpi-col-2) [data-testid="stMetricValue"] {
    color: #e11d48 !important;
}

div[data-testid="column"]:has(.kpi-col-3) [data-testid="stVerticalBlockBorderWrapper"] {
    border-top: 3.5px solid #f59e0b !important;
    background: linear-gradient(180deg, rgba(245, 158, 11, 0.05) 0%, #ffffff 100%) !important;
}
div[data-testid="column"]:has(.kpi-col-3) [data-testid="stMetricValue"] {
    color: #d97706 !important;
}

div[data-testid="column"]:has(.kpi-col-4) [data-testid="stVerticalBlockBorderWrapper"] {
    border-top: 3.5px solid #10b981 !important;
    background: linear-gradient(180deg, rgba(16, 185, 129, 0.05) 0%, #ffffff 100%) !important;
}
div[data-testid="column"]:has(.kpi-col-4) [data-testid="stMetricValue"] {
    color: #059669 !important;
}

div[data-testid="column"]:has(.kpi-col-5) [data-testid="stVerticalBlockBorderWrapper"] {
    border-top: 3.5px solid #8b5cf6 !important;
    background: linear-gradient(180deg, rgba(139, 92, 246, 0.05) 0%, #ffffff 100%) !important;
}
div[data-testid="column"]:has(.kpi-col-5) [data-testid="stMetricValue"] {
    color: #7c3aed !important;
}

/* Active selected KPI card highlight */
div[data-testid="column"]:has(.kpi-active-marker) [data-testid="stVerticalBlockBorderWrapper"] {
    outline: 2px solid #2563eb !important;
    box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.2), 0 10px 22px -3px rgba(15, 23, 42, 0.1) !important;
}

/* Compact button inside KPI card */
div[data-testid="column"]:has(.kpi-col-marker) button {
    font-size: 0.775rem !important;
    font-weight: 600 !important;
    padding: 0.38rem 0.55rem !important;
    border-radius: 8px !important;
    margin-top: 0.4rem !important;
    transition: all 0.15s ease !important;
}

/* -------------------------------------------------------------
   6. Form Controls, Inputs & Selects
   ------------------------------------------------------------- */
div[data-baseweb="input"], div[data-baseweb="select"] {
    border-radius: 9px !important;
    border-color: #cbd5e1 !important;
    background-color: #ffffff !important;
}

div[data-baseweb="input"]:focus-within,
div[data-baseweb="select"]:focus-within {
    border-color: #2563eb !important;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.18) !important;
}

/* -------------------------------------------------------------
   7. Buttons Styling (Rich Vibrant Gradients)
   ------------------------------------------------------------- */
button[kind="primary"] {
    background: linear-gradient(135deg, #2563eb 0%, #4f46e5 100%) !important;
    color: #ffffff !important;
    border-radius: 9px !important;
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    font-weight: 700 !important;
    border: none !important;
    padding: 0.55rem 1.35rem !important;
    box-shadow: 0 3px 12px rgba(37, 99, 235, 0.3) !important;
    transition: all 0.18s cubic-bezier(0.16, 1, 0.3, 1) !important;
}

button[kind="primary"]:hover {
    background: linear-gradient(135deg, #1d4ed8 0%, #4338ca 100%) !important;
    box-shadow: 0 6px 18px rgba(37, 99, 235, 0.45) !important;
    transform: translateY(-1.5px) !important;
}

button[kind="secondary"] {
    background-color: #ffffff !important;
    color: #334155 !important;
    border: 1.5px solid #cbd5e1 !important;
    border-radius: 9px !important;
    font-family: 'Plus Jakarta Sans', sans-serif !important;
    font-weight: 600 !important;
    transition: all 0.15s ease-in-out !important;
}

button[kind="secondary"]:hover {
    background-color: #f8fafc !important;
    border-color: #2563eb !important;
    color: #2563eb !important;
    box-shadow: 0 2px 8px rgba(37, 99, 235, 0.1) !important;
    transform: translateY(-1px) !important;
}

/* -------------------------------------------------------------
   8. Tables and DataFrames
   ------------------------------------------------------------- */
[data-testid="stDataFrame"] {
    border: 1px solid #e2e8f0 !important;
    border-radius: 12px !important;
    overflow: hidden !important;
    box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04) !important;
    background-color: #ffffff !important;
}

/* -------------------------------------------------------------
   9. Alerts & Info Banners
   ------------------------------------------------------------- */
[data-testid="stAlert"] {
    border-radius: 12px !important;
    border-width: 1px !important;
    font-size: 0.9rem !important;
    padding: 0.9rem 1.25rem !important;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.03) !important;
}

/* -------------------------------------------------------------
   10. Chart Titles
   ------------------------------------------------------------- */
.rms-chart-title {
    font-size: 1.05rem;
    font-weight: 800;
    font-family: 'Plus Jakarta Sans', sans-serif;
    color: #0f172a;
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
    border-radius: 12px;
    padding: 1rem 1.25rem;
    font-size: 0.825rem;
    color: #475569;
    line-height: 1.5;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.03);
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
