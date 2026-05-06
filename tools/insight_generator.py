# tools/insight_generator.py

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import json
import pandas as pd
from langchain_groq import ChatGroq
from config import GROQ_API_KEY, GROQ_MODEL


INSIGHT_PROMPT = """You are a data analyst.

A user asked a business question:
{query}

Here are the query results:
{results_text}

Write a clear business insight:

- 2–3 sentences max
- Start with the key finding
- Include important numbers
- No SQL or technical explanation
"""


# Initialize Groq model ONCE
llm = ChatGroq(
    model=GROQ_MODEL,
    api_key=GROQ_API_KEY,
    temperature=0
)


def generate_insight(query: str, df: pd.DataFrame) -> str:

    if df is None or df.empty:
        return "The query returned no results."

    try:
        results_text = df.head(20).to_string(index=False)

        prompt = INSIGHT_PROMPT.format(
            query=query,
            results_text=results_text
        )

        response = llm.invoke(prompt)

        return response.content.strip()

    except Exception as e:
        return _fallback_insight(df)


def _fallback_insight(df: pd.DataFrame) -> str:
    num_cols = df.select_dtypes(include="number").columns.tolist()

    lines = [f"Query returned {len(df)} rows."]

    if num_cols:
        col = num_cols[0]
        lines.append(
            f"{col}: min={df[col].min():.2f}, "
            f"max={df[col].max():.2f}, "
            f"avg={df[col].mean():.2f}"
        )

    return " ".join(lines)


def generate_insight_from_string(input_str: str) -> str:
    """
    Expected format:
    "user question|||JSON rows"
    """
    try:
        query, data_json = input_str.split("|||")
        data = json.loads(data_json)
        df = pd.DataFrame(data)

        return generate_insight(query, df)

    except Exception as e:
        return f"Insight error: {str(e)}"