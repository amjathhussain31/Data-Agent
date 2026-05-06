# backend/mcp_server/tools/visualise.py
"""
Builds Plotly charts from query results.
Auto-detects the best chart type: bar, line, pie, scatter, area,
histogram, stacked_bar, heatmap, table.
"""

import json
import logging

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.graph_objs import Figure

logger = logging.getLogger("datamind-mcp.visualise")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _coerce_numeric(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        try:
            df[col] = pd.to_numeric(df[col])
        except (ValueError, TypeError):
            pass
    return df


def _combine_year_month(df: pd.DataFrame) -> pd.DataFrame:
    """Combine separate year/month columns into a single date string."""
    cols_lower = [c.lower() for c in df.columns]
    has_year = "year" in cols_lower
    has_month = "month" in cols_lower

    if has_year and has_month:
        year_col = df.columns[cols_lower.index("year")]
        month_col = df.columns[cols_lower.index("month")]
        df = df.copy()
        df["order_month"] = (
            df[year_col].astype(int).astype(str)
            + "-"
            + df[month_col].astype(int).astype(str).str.zfill(2)
        )
        df = df.drop(columns=[year_col, month_col])
        other_cols = [c for c in df.columns if c != "order_month"]
        df = df[["order_month"] + other_cols]
    return df


def detect_chart_type(df: pd.DataFrame, question: str = "") -> str:
    """
    Detect the best chart type. Priority:
    1. Explicit question keywords (pie only if user says "pie/proportion/share")
    2. Time-series columns -> line
    3. Default: bar for categorical+numeric data
    """
    if df.empty or len(df.columns) < 2:
        return "table"
    if len(df) == 1:
        return "table"

    df_check = _coerce_numeric(df.copy())
    cols = list(df_check.columns)
    num_cols = df_check.select_dtypes(include="number").columns.tolist()
    str_cols = df_check.select_dtypes(include="object").columns.tolist()
    n_rows = len(df_check)
    n_num = len(num_cols)
    n_str = len(str_cols)
    q = question.lower() if question else ""

    # --- Explicit question keywords (user must ask for pie) ---
    if any(kw in q for kw in ["pie", "proportion", "share", "percentage"]):
        return "pie"
    if any(kw in q for kw in ["trend", "over time", "monthly", "daily", "weekly", "growth"]):
        return "line"
    if any(kw in q for kw in ["distribution", "spread", "histogram"]):
        return "histogram"
    if any(kw in q for kw in ["scatter", "correlation", "relationship"]):
        return "scatter"
    if any(kw in q for kw in ["stacked"]):
        return "stacked_bar"
    if any(kw in q for kw in ["area", "cumulative"]):
        return "area"

    # --- Data-shape detection ---
    # Time series columns -> line chart
    time_kw = ["date", "month", "year", "week", "quarter", "period", "time"]
    for col in cols:
        if any(kw in col.lower() for kw in time_kw):
            if num_cols:
                return "line"

    # Two+ numeric, no string -> scatter
    if n_num >= 2 and n_str == 0 and n_rows > 5:
        return "scatter"

    # Single numeric, no string -> histogram
    if n_num == 1 and n_str == 0 and n_rows > 5:
        return "histogram"

    # Multiple numeric + categorical -> stacked bar
    if n_num >= 2 and n_str >= 1:
        return "stacked_bar"

    # Categorical + numeric -> BAR (this is the default for most queries)
    if n_str >= 1 and n_num >= 1:
        return "bar"

    return "table"


def _build_chart(df: pd.DataFrame, title: str, chart_type: str) -> Figure:
    """Build a Plotly Figure based on detected chart type."""
    cols = list(df.columns)
    num_cols = df.select_dtypes(include="number").columns.tolist()
    str_cols = df.select_dtypes(include="object").columns.tolist()

    try:
        if chart_type == "bar":
            x_col = str_cols[0] if str_cols else cols[0]
            y_col = num_cols[0] if num_cols else cols[1]
            fig = px.bar(
                df, x=x_col, y=y_col, title=title,
                color=x_col,
                color_discrete_sequence=px.colors.qualitative.Set2,
            )

        elif chart_type == "stacked_bar":
            x_col = str_cols[0] if str_cols else cols[0]
            y_cols = num_cols[:3]
            fig = go.Figure()
            colors = px.colors.qualitative.Set2
            for i, y_col in enumerate(y_cols):
                fig.add_trace(go.Bar(
                    name=y_col, x=df[x_col], y=df[y_col],
                    marker_color=colors[i % len(colors)],
                ))
            fig.update_layout(barmode="stack", title=title)

        elif chart_type == "line":
            x_col = str_cols[0] if str_cols else cols[0]
            y_col = num_cols[0] if num_cols else cols[1]
            fig = px.line(df, x=x_col, y=y_col, title=title, markers=True)
            fig.update_xaxes(tickangle=45)

        elif chart_type == "area":
            x_col = str_cols[0] if str_cols else cols[0]
            y_col = num_cols[0] if num_cols else cols[1]
            fig = px.area(df, x=x_col, y=y_col, title=title)

        elif chart_type == "pie":
            name_col = str_cols[0] if str_cols else cols[0]
            value_col = num_cols[0] if num_cols else cols[1]
            fig = px.pie(df, names=name_col, values=value_col, title=title,
                         color_discrete_sequence=px.colors.qualitative.Set2)

        elif chart_type == "scatter":
            x_col = num_cols[0] if num_cols else cols[0]
            y_col = num_cols[1] if len(num_cols) > 1 else cols[1]
            color_col = str_cols[0] if str_cols else None
            fig = px.scatter(df, x=x_col, y=y_col, color=color_col,
                             title=title, size_max=15)

        elif chart_type == "histogram":
            x_col = num_cols[0] if num_cols else cols[0]
            fig = px.histogram(df, x=x_col, title=title, nbins=20,
                               color_discrete_sequence=["#58a6ff"])

        elif chart_type == "heatmap":
            x_col = str_cols[0] if str_cols else cols[0]
            y_col = str_cols[1] if len(str_cols) > 1 else cols[1]
            z_col = num_cols[0] if num_cols else cols[2]
            pivot = df.pivot_table(index=y_col, columns=x_col, values=z_col, aggfunc="sum")
            fig = px.imshow(pivot, title=title, color_continuous_scale="Blues", aspect="auto")

        else:  # table
            fig = go.Figure(data=[go.Table(
                header=dict(values=cols, fill_color="#1f6feb",
                            font=dict(color="white"), align="left"),
                cells=dict(values=[df[c].tolist() for c in cols],
                           fill_color="#161b22", font=dict(color="#e6edf3"), align="left"),
            )])
            fig.update_layout(title=title)

        # Dark theme
        fig.update_layout(
            paper_bgcolor="#161b22",
            plot_bgcolor="#0d1117",
            font_color="#e6edf3",
            title_font_color="#e6edf3",
            margin=dict(l=20, r=20, t=40, b=60),
            height=420,
        )

        # Auto-scale Y-axis to start near the minimum value (shows differences better)
        if chart_type in ("bar", "line", "area", "stacked_bar"):
            try:
                y_values = []
                for trace in fig.data:
                    if hasattr(trace, 'y') and trace.y is not None:
                        y_values.extend([v for v in trace.y if v is not None])
                if y_values:
                    y_min = min(y_values)
                    y_max = max(y_values)
                    # Only adjust if values are clustered (min > 30% of max)
                    if y_min > 0 and y_min > y_max * 0.3:
                        padding = (y_max - y_min) * 0.15
                        fig.update_yaxes(range=[y_min - padding, y_max + padding])
            except Exception:
                pass

        return fig

    except Exception as e:
        fig = go.Figure()
        fig.update_layout(title=f"Chart error: {str(e)}")
        return fig


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def visualise(data_json: str, question: str) -> str:
    """
    Build a Plotly chart from query results and return it as JSON.
    """
    try:
        data = json.loads(data_json)
        df = pd.DataFrame(data)

        if df.empty:
            fig = go.Figure()
            fig.update_layout(title="No data to display")
            return fig.to_json()

        df = _combine_year_month(df.copy())
        df = _coerce_numeric(df)

        chart_type = detect_chart_type(df, question)
        title = question[:60] if question else "Query Results"
        fig = _build_chart(df, title=title, chart_type=chart_type)

        logger.info("visualise: type=%s, rows=%d", chart_type, len(df))
        return fig.to_json()

    except Exception as e:
        logger.error("visualise failed: %s", e)
        return json.dumps({"error": str(e)})
