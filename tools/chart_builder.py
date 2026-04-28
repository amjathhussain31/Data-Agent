# tools/chart_builder.py
"""
Auto-selects and builds a Plotly chart from a DataFrame.
Chart type is chosen based on data shape — no manual selection needed.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.graph_objs import Figure


def detect_chart_type(df: pd.DataFrame) -> str:
    """
    Automatically picks the best chart type based on DataFrame shape.

    Rules:
      time column present          → line
      2 cols: categorical+numeric  → bar
      1 numeric col, many rows     → histogram
      3+ numeric cols              → scatter
      2 cols, ≤6 rows              → pie
      fallback                     → table
    """
    if df.empty or len(df.columns) < 2:
        return "table"

    cols        = list(df.columns)
    num_cols    = df.select_dtypes(include="number").columns.tolist()
    str_cols    = df.select_dtypes(include="object").columns.tolist()
    n_rows      = len(df)

    # Time series detection
    time_keywords = ["date", "month", "year", "week", "quarter", "period", "time"]
    for col in cols:
        if any(kw in col.lower() for kw in time_keywords):
            if num_cols:
                return "line"

    # Bar — categorical + numeric, more than 2 rows
    if len(str_cols) >= 1 and len(num_cols) >= 1 and n_rows > 2:
        return "bar"

    # Pie — only for very few categories (2 or fewer)
    if len(str_cols) == 1 and len(num_cols) == 1 and n_rows <= 2:
        return "pie"

    # Multiple numeric — scatter
    if len(num_cols) >= 3:
        return "scatter"

    # Single numeric — histogram
    if len(num_cols) == 1:
        return "histogram"

    return "table"


def build_chart(df: pd.DataFrame,
                title: str = "Query Results",
                chart_type: str = None) -> Figure:
    """
    Builds and returns a Plotly Figure.
    If chart_type is None, auto-detects from DataFrame.
    """
    if df is None or df.empty:
        fig = go.Figure()
        fig.update_layout(title="No data to display")
        return fig

    cols     = list(df.columns)
    num_cols = df.select_dtypes(include="number").columns.tolist()
    str_cols = df.select_dtypes(include="object").columns.tolist()

    if chart_type is None:
        chart_type = detect_chart_type(df)

    try:
        if chart_type == "bar":
            x_col = str_cols[0] if str_cols else cols[0]
            y_col = num_cols[0] if num_cols else cols[1]
            fig = px.bar(df, x=x_col, y=y_col, title=title,
                         color=x_col, color_discrete_sequence=px.colors.qualitative.Set2)

        elif chart_type == "line":
            x_col = cols[0]
            y_col = num_cols[0] if num_cols else cols[1]
            fig = px.line(df, x=x_col, y=y_col, title=title, markers=True)

        elif chart_type == "pie":
            name_col  = str_cols[0] if str_cols else cols[0]
            value_col = num_cols[0] if num_cols else cols[1]
            fig = px.pie(df, names=name_col, values=value_col, title=title)

        elif chart_type == "scatter":
            fig = px.scatter(df, x=num_cols[0], y=num_cols[1],
                             title=title, color=str_cols[0] if str_cols else None)

        elif chart_type == "histogram":
            fig = px.histogram(df, x=num_cols[0], title=title)

        else:
            # Table fallback
            fig = go.Figure(data=[go.Table(
                header=dict(values=cols, fill_color="#4A90D9",
                            font=dict(color="white"), align="left"),
                cells=dict(values=[df[c] for c in cols],
                           fill_color="lavender", align="left")
            )])
            fig.update_layout(title=title)

        fig.update_layout(
            margin=dict(l=20, r=20, t=40, b=20),
            height=400
        )
        return fig

    except Exception as e:
        fig = go.Figure()
        fig.update_layout(title=f"Chart error: {str(e)}")
        return fig


def build_chart_from_string(data_json: str, title: str = "Results") -> str:
    """
    LangChain tool wrapper — accepts JSON string, returns status string.
    The actual Figure is stored in session state in the Streamlit app.
    """
    try:
        data  = json.loads(data_json)
        df    = pd.DataFrame(data)
        ctype = detect_chart_type(df)
        return f"Chart ready: type={ctype}, rows={len(df)}, cols={list(df.columns)}"
    except Exception as e:
        return f"Chart error: {str(e)}"