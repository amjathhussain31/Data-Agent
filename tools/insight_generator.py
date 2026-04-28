# tools/insight_generator.py
"""
Sends query results to Gemini and gets a plain-English summary.
Produces the human-readable insight shown below every chart.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import json
import pandas as pd
import google.generativeai as genai
from config import GEMINI_API_KEY, GEMINI_MODEL

genai.configure(api_key=GEMINI_API_KEY)


INSIGHT_PROMPT = """You are a data analyst. A user asked a business question and 
you ran a SQL query. Summarize the results in 2-3 clear sentences.

User question: {query}

Query results:
{results_text}

Instructions:
- Start with the most important finding
- Include specific numbers from the results
- Keep it under 3 sentences
- Do not mention SQL or technical details
- Write for a non-technical business user
"""


def generate_insight(query: str, df: pd.DataFrame) -> str:
    """
    Generates a plain-English insight from query results.
    Returns a 2-3 sentence summary string.
    """
    if df is None or df.empty:
        return "The query returned no results."

    try:
        # Format DataFrame as readable text — limit to 20 rows
        results_text = df.head(20).to_string(index=False)

        prompt = INSIGHT_PROMPT.format(
            query=query,
            results_text=results_text
        )

        model    = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(prompt)
        return response.text.strip()

    except Exception as e:
        # Fallback — basic stats if Gemini fails
        return _fallback_insight(df)


def _fallback_insight(df: pd.DataFrame) -> str:
    """Rule-based fallback if Gemini API fails."""
    num_cols = df.select_dtypes(include="number").columns.tolist()
    lines    = [f"Query returned {len(df)} rows and {len(df.columns)} columns."]

    if num_cols:
        col = num_cols[0]
        lines.append(
            f"{col}: min={df[col].min():.2f}, "
            f"max={df[col].max():.2f}, "
            f"avg={df[col].mean():.2f}"
        )
    return " ".join(lines)


def generate_insight_from_string(data_json: str, query: str = "") -> str:
    """
    LangChain tool wrapper — accepts JSON string of records.
    Returns insight string.
    """
    try:
        data = json.loads(data_json)
        df   = pd.DataFrame(data)
        return generate_insight(query, df)
    except Exception as e:
        return f"Insight error: {str(e)}"