# agent/error_handler.py
"""
Centralized error handling and retry logic for the agent.
"""
import os
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def retry_on_rate_limit(fn, max_retries: int = 3, base_wait: int = 20):
    """
    Decorator-style retry for any function that might hit 429.
    Usage:
        result = retry_on_rate_limit(lambda: model.generate_content(prompt))
    """
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            err = str(e)
            if "429" in err and attempt < max_retries - 1:
                wait = base_wait * (attempt + 1)
                print(f"[error_handler] Rate limit — waiting {wait}s "
                      f"(attempt {attempt + 1}/{max_retries})")
                time.sleep(wait)
            else:
                raise


def classify_error(error: str) -> dict:
    """
    Classifies an error string into a user-friendly message.
    Used by Streamlit UI to show helpful messages.
    """
    error_lower = error.lower()

    if "429" in error or "quota" in error_lower or "rate limit" in error_lower:
        return {
            "type":    "rate_limit",
            "message": "API rate limit reached. Please wait 30 seconds and try again.",
            "retry":   True
        }
    if "timeout" in error_lower or "timed out" in error_lower:
        return {
            "type":    "timeout",
            "message": "Request timed out. Try a simpler query.",
            "retry":   True
        }
    if "authentication" in error_lower or "api key" in error_lower:
        return {
            "type":    "auth",
            "message": "API key invalid. Check your .env file.",
            "retry":   False
        }
    if "no such table" in error_lower or "operational error" in error_lower:
        return {
            "type":    "sql",
            "message": "Database error — the generated SQL referenced a non-existent table.",
            "retry":   False
        }
    if "blocked" in error_lower or "guardrail" in error_lower:
        return {
            "type":    "guardrail",
            "message": "Query was blocked by safety guardrails.",
            "retry":   False
        }
    return {
        "type":    "unknown",
        "message": f"Unexpected error: {error[:100]}",
        "retry":   False
    }