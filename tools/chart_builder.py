# tools/chart_builder.py
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.graph_objs import Figure


def _coerce_numeric(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        try:
            df[col] = pd.to_numeric(df[col])
        except (ValueError, TypeError):
            pass
    return df


def _combine_year_month(df: pd.DataFrame) -> pd.DataFrame:
    """
    When the agent queries EXTRACT(YEAR...) EXTRACT(MONTH...),
    the result has separate 'year' and 'month' numeric columns.
    Combine them into a single 'order_month' string so the
    time-series detector fires correctly.
    """
    cols_lower = [c.lower() for c in df.columns]
    has_year  = "year"  in cols_lower
    has_month = "month" in cols_lower

    if has_year and has_month:
        year_col  = df.columns[cols_lower.index("year")]
        month_col = df.columns[cols_lower.index("month")]
        df = df.copy()
        df["order_month"] = (
            df[year_col].astype(int).astype(str) + "-" +
            df[month_col].astype(int).astype(str).str.zfill(2)
        )
        df = df.drop(columns=[year_col, month_col])
        # Move order_month to front so it becomes the x-axis
        other_cols = [c for c in df.columns if c != "order_month"]
        df = df[["order_month"] + other_cols]
    return df


def detect_chart_type(df: pd.DataFrame) -> str:
    if df.empty or len(df.columns) < 2:
        return "table"

    if len(df) == 1:
        return "table"

    df       = _coerce_numeric(df.copy())
    cols     = list(df.columns)
    num_cols = df.select_dtypes(include="number").columns.tolist()
    str_cols = df.select_dtypes(include="object").columns.tolist()
    n_rows   = len(df)

    # Time series — check all column names for time keywords
    time_kw = [
        "date", "month", "year", "week", "quarter",
        "period", "time", "order_month", "order_date"
    ]
    for col in cols:
        if any(kw in col.lower() for kw in time_kw):
            if num_cols:
                return "line"

    # Bar — categorical + numeric, more than 2 rows
    if len(str_cols) >= 1 and len(num_cols) >= 1 and n_rows > 2:
        return "bar"

    # Pie — 2 or fewer rows
    if len(str_cols) == 1 and len(num_cols) == 1 and n_rows <= 2:
        return "pie"

    return "table"


def build_chart(df: pd.DataFrame,
                title: str = "Query Results",
                chart_type: str = None) -> Figure:

    if df is None or df.empty:
        fig = go.Figure()
        fig.update_layout(title="No data to display")
        return fig

    
    df = _combine_year_month(df.copy())          # combines year+month before anything else
    df = _coerce_numeric(df)

    cols     = list(df.columns)
    num_cols = df.select_dtypes(include="number").columns.tolist()
    str_cols = df.select_dtypes(include="object").columns.tolist()

    if chart_type is None:
        chart_type = detect_chart_type(df)

    try:
        if chart_type == "bar":
            x_col = str_cols[0] if str_cols else cols[0]
            y_col = num_cols[0] if num_cols else cols[1]
            fig   = px.bar(
                df, x=x_col, y=y_col, title=title,
                color=x_col,
                color_discrete_sequence=px.colors.qualitative.Set2
            )

        elif chart_type == "line":
            x_col = str_cols[0] if str_cols else cols[0]
            y_col = num_cols[0] if num_cols else cols[1]
            fig   = px.line(
                df, x=x_col, y=y_col,
                title=title,
                markers=True
            )
            fig.update_xaxes(tickangle=45)

        elif chart_type == "pie":
            name_col  = str_cols[0] if str_cols else cols[0]
            value_col = num_cols[0] if num_cols else cols[1]
            fig       = px.pie(df, names=name_col, values=value_col, title=title)

        else:
            fig = go.Figure(data=[go.Table(
                header=dict(
                    values=cols,
                    fill_color="#1f6feb",
                    font=dict(color="white"),
                    align="left"
                ),
                cells=dict(
                    values=[df[c].tolist() for c in cols],
                    fill_color="#161b22",
                    font=dict(color="#e6edf3"),
                    align="left"
                )
            )])
            fig.update_layout(title=title)

        fig.update_layout(
            paper_bgcolor="#161b22",
            plot_bgcolor="#0d1117",
            font_color="#e6edf3",
            title_font_color="#e6edf3",
            margin=dict(l=20, r=20, t=40, b=60),
            height=400
        )
        return fig

    except Exception as e:
        fig = go.Figure()
        fig.update_layout(title=f"Chart error: {str(e)}")
        return fig


def build_chart_from_string(data_json: str, title: str = "Results") -> str:
    """LangChain tool wrapper — returns status string to agent."""
    try:
        data  = json.loads(data_json)
        df    = pd.DataFrame(data)
        df    = _combine_year_month(df.copy())
        df    = _coerce_numeric(df)
        ctype = detect_chart_type(df)
        return f"Chart ready: type={ctype}, rows={len(df)}, cols={list(df.columns)}"
    except Exception as e:
        return f"Chart error: {str(e)}"