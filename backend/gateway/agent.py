# backend/gateway/agent.py
"""
DataMind Supervisor Agent — LangGraph-based orchestrator.
Decides the flow: guardrails → route → tools → response.
Uses a state graph with conditional edges for intelligent routing.
"""

import os
import sys
import json
import time
import logging
from typing import TypedDict, Annotated, Literal
from operator import add

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from backend.gateway.guardrails import run_guardrails, check_sql
from backend.gateway.memory_manager import get_memory_context, save_interaction
from backend.gateway.query_router import route_query
from backend.gateway.mcp_client import (
    call_rag_search,
    call_nl_to_sql,
    call_execute_sql,
    call_fetch_schema,
    call_summarise,
    call_visualise,
)

logger = logging.getLogger("datamind-agent")


# ---------------------------------------------------------------------------
# Agent State
# ---------------------------------------------------------------------------
class AgentState(TypedDict):
    """State that flows through the LangGraph pipeline."""
    # Input
    question: str
    session_id: str

    # Pipeline state
    route: str
    schema: str
    rag_context: str
    memory_context: str
    sql: str
    exec_result: dict
    data_json: str
    summary: str
    chart_json: str
    confidence: float

    # Control flow
    blocked: bool
    block_reason: str
    hitl: bool
    hitl_reason: str
    error: str
    start_time: float


# ---------------------------------------------------------------------------
# Node functions
# ---------------------------------------------------------------------------
def guardrails_node(state: AgentState) -> dict:
    """Step 1: Run input guardrails."""
    passed, reason = run_guardrails(state["question"])
    if not passed:
        return {"blocked": True, "block_reason": reason}
    return {"blocked": False, "block_reason": ""}


def router_node(state: AgentState) -> dict:
    """Step 2: Route the query to sql/rag/hybrid."""
    route = route_query(state["question"])
    logger.info("Router: %s | %s", route, state["question"][:60])
    return {"route": route}


def memory_node(state: AgentState) -> dict:
    """Step 3: Fetch memory context."""
    memory_context = get_memory_context(state["session_id"])
    return {"memory_context": memory_context}


def rag_node(state: AgentState) -> dict:
    """Step 4: RAG search for document context."""
    rag_context = call_rag_search(state["question"])
    return {"rag_context": rag_context}


def schema_node(state: AgentState) -> dict:
    """Step 5: Fetch database schema."""
    schema = call_fetch_schema()
    return {"schema": schema}


def nl_to_sql_node(state: AgentState) -> dict:
    """Step 6: Convert natural language to SQL."""
    sql = call_nl_to_sql(
        state["question"],
        state.get("schema", ""),
        state.get("rag_context", ""),
        state.get("memory_context", ""),
    )
    if sql.startswith("ERROR:"):
        return {"sql": "", "error": sql}
    return {"sql": sql, "error": ""}


def sql_guardrails_node(state: AgentState) -> dict:
    """Step 7a: Check SQL through output guardrails."""
    sql = state.get("sql", "")
    if not sql:
        return {"hitl": False, "blocked": False}

    verdict, reason = check_sql(sql)
    if verdict == "BLOCK":
        return {"blocked": True, "block_reason": f"SQL blocked: {reason}"}
    if verdict == "HITL":
        return {"hitl": True, "hitl_reason": f"Requires approval: {reason}"}
    return {"hitl": False, "blocked": False}


def execute_sql_node(state: AgentState) -> dict:
    """Step 7b: Execute the SQL query."""
    sql = state.get("sql", "")
    if not sql:
        return {"exec_result": {}, "data_json": "[]"}

    exec_result = call_execute_sql(sql)
    if isinstance(exec_result, dict) and "error" in exec_result:
        return {
            "exec_result": exec_result,
            "data_json": "[]",
            "error": f"SQL execution error: {exec_result['error']}",
        }

    rows = exec_result.get("rows", [])
    data_json = json.dumps(rows, default=str)
    return {"exec_result": exec_result, "data_json": data_json, "error": ""}


def summarise_node(state: AgentState) -> dict:
    """Step 8: Generate business summary."""
    route = state.get("route", "")
    rag_context = state.get("rag_context", "")
    data_json = state.get("data_json", "[]")

    if route == "rag" and rag_context:
        return {"summary": rag_context}
    elif data_json != "[]":
        summary = call_summarise(state["question"], data_json)
        return {"summary": summary}
    return {"summary": "No data available for this query."}


def visualise_node(state: AgentState) -> dict:
    """Step 9: Generate chart visualization."""
    data_json = state.get("data_json", "[]")
    if data_json == "[]":
        return {"chart_json": ""}

    chart_json = call_visualise(data_json, state["question"])
    return {"chart_json": chart_json}


def save_node(state: AgentState) -> dict:
    """Step 10: Save interaction to memory."""
    save_interaction(
        state["session_id"],
        state["question"],
        state.get("sql", ""),
        state.get("summary", ""),
    )
    return {}


def confidence_node(state: AgentState) -> dict:
    """Step 11: Calculate confidence score."""
    confidence = 0.8
    if state.get("rag_context"):
        confidence += 0.1
    if state.get("memory_context"):
        confidence += 0.05
    if state.get("data_json", "[]") != "[]":
        confidence += 0.05
    return {"confidence": min(confidence, 1.0)}


# ---------------------------------------------------------------------------
# Conditional edges
# ---------------------------------------------------------------------------
def should_continue_after_guardrails(state: AgentState) -> str:
    """After guardrails: blocked → end, else → router."""
    if state.get("blocked"):
        return "end"
    return "router"


def route_decision(state: AgentState) -> str:
    """After routing: decide which tools to invoke."""
    route = state.get("route", "sql")
    if route == "rag":
        return "rag_only"
    elif route == "hybrid":
        return "hybrid"
    else:
        return "sql_only"


def should_execute_sql(state: AgentState) -> str:
    """After SQL guardrails: blocked/hitl → end, else → execute."""
    if state.get("blocked"):
        return "end"
    if state.get("hitl"):
        return "end"
    if state.get("error"):
        return "end"
    return "execute"


# ---------------------------------------------------------------------------
# Build the LangGraph
# ---------------------------------------------------------------------------
def build_agent_graph() -> StateGraph:
    """
    Construct the DataMind supervisor agent as a LangGraph StateGraph.

    Flow:
        guardrails → router → [rag_only | sql_only | hybrid]
            → sql_guardrails → execute → summarise → visualise → save → end
    """
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("guardrails", guardrails_node)
    graph.add_node("router", router_node)
    graph.add_node("memory", memory_node)
    graph.add_node("rag_search", rag_node)
    graph.add_node("fetch_schema", schema_node)
    graph.add_node("nl_to_sql", nl_to_sql_node)
    graph.add_node("sql_guardrails", sql_guardrails_node)
    graph.add_node("execute_sql", execute_sql_node)
    graph.add_node("summarise", summarise_node)
    graph.add_node("visualise", visualise_node)
    graph.add_node("save", save_node)
    graph.add_node("confidence", confidence_node)

    # Entry point
    graph.set_entry_point("guardrails")

    # Conditional: guardrails → router or end
    graph.add_conditional_edges(
        "guardrails",
        should_continue_after_guardrails,
        {"end": END, "router": "router"},
    )

    # Router → memory (always needed)
    graph.add_edge("router", "memory")

    # Memory → conditional routing
    graph.add_conditional_edges(
        "memory",
        route_decision,
        {
            "rag_only": "rag_search",
            "sql_only": "fetch_schema",
            "hybrid": "rag_search",
        },
    )

    # RAG-only path: rag → summarise → save → confidence → end
    # Hybrid path: rag → fetch_schema → nl_to_sql → ...
    graph.add_conditional_edges(
        "rag_search",
        lambda state: "schema" if state.get("route") == "hybrid" else "summarise",
        {"schema": "fetch_schema", "summarise": "summarise"},
    )

    # SQL path: schema → nl_to_sql
    graph.add_edge("fetch_schema", "nl_to_sql")

    # NL-to-SQL → SQL guardrails
    graph.add_edge("nl_to_sql", "sql_guardrails")

    # SQL guardrails → execute or end
    graph.add_conditional_edges(
        "sql_guardrails",
        should_execute_sql,
        {"end": END, "execute": "execute_sql"},
    )

    # Execute → summarise → visualise → save → confidence → end
    graph.add_edge("execute_sql", "summarise")
    graph.add_edge("summarise", "visualise")
    graph.add_edge("visualise", "save")
    graph.add_edge("save", "confidence")
    graph.add_edge("confidence", END)

    return graph


# ---------------------------------------------------------------------------
# Compiled agent (singleton)
# ---------------------------------------------------------------------------
_compiled_agent = None


def get_agent():
    """Get the compiled LangGraph agent (lazy singleton)."""
    global _compiled_agent
    if _compiled_agent is None:
        graph = build_agent_graph()
        _compiled_agent = graph.compile()
        logger.info("LangGraph supervisor agent compiled")
    return _compiled_agent


# ---------------------------------------------------------------------------
# Run the agent
# ---------------------------------------------------------------------------
def run_agent(question: str, session_id: str) -> dict:
    """
    Execute the full DataMind pipeline via the LangGraph supervisor agent.

    Args:
        question: User's natural language question.
        session_id: Unique session identifier.

    Returns:
        Dict with: sql, summary, chart_json, confidence, rag_sources,
                   route, blocked, hitl, error
    """
    agent = get_agent()

    initial_state: AgentState = {
        "question": question,
        "session_id": session_id,
        "route": "",
        "schema": "",
        "rag_context": "",
        "memory_context": "",
        "sql": "",
        "exec_result": {},
        "data_json": "[]",
        "summary": "",
        "chart_json": "",
        "confidence": 0.0,
        "blocked": False,
        "block_reason": "",
        "hitl": False,
        "hitl_reason": "",
        "error": "",
        "start_time": time.time(),
    }

    try:
        final_state = agent.invoke(initial_state)

        return {
            "sql": final_state.get("sql", ""),
            "summary": final_state.get("summary", ""),
            "chart_json": final_state.get("chart_json", ""),
            "confidence": round(final_state.get("confidence", 0.0), 2),
            "rag_sources": final_state.get("rag_context", ""),
            "route": final_state.get("route", ""),
            "blocked": final_state.get("blocked", False),
            "hitl": final_state.get("hitl", False),
            "error": final_state.get("block_reason", "")
                     or final_state.get("hitl_reason", "")
                     or final_state.get("error", ""),
        }

    except Exception as e:
        logger.error("Agent execution failed: %s", e)
        return {
            "sql": "",
            "summary": "",
            "chart_json": "",
            "confidence": 0.0,
            "rag_sources": "",
            "route": "",
            "blocked": False,
            "hitl": False,
            "error": f"Agent error: {str(e)}",
        }
