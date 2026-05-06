# tests/test_agent.py
"""
Integration tests for the LangGraph supervisor agent.
Tests the full pipeline with mocked external services.
"""

import os
import sys
import json
from unittest.mock import patch, MagicMock

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ===========================================================================
# Test: Agent graph structure
# ===========================================================================
class TestAgentGraph:
    def test_agent_graph_compiles(self):
        """The LangGraph agent should compile without errors."""
        from backend.gateway.agent import build_agent_graph
        graph = build_agent_graph()
        compiled = graph.compile()
        assert compiled is not None

    def test_agent_graph_has_all_nodes(self):
        """The graph should contain all expected nodes."""
        from backend.gateway.agent import build_agent_graph
        graph = build_agent_graph()

        expected_nodes = [
            "guardrails", "router", "memory", "rag_search",
            "fetch_schema", "nl_to_sql", "sql_guardrails",
            "execute_sql", "summarise", "visualise", "save", "confidence",
        ]
        for node in expected_nodes:
            assert node in graph.nodes, f"Missing node: {node}"


# ===========================================================================
# Test: Agent execution — blocked query
# ===========================================================================
class TestAgentBlocked:
    def test_agent_blocks_offtopic(self):
        """Off-topic queries should be blocked at guardrails."""
        from backend.gateway.agent import run_agent
        result = run_agent("Write me a poem", "test-session")

        assert result["blocked"] is True
        assert result["sql"] == ""
        assert result["summary"] == ""

    def test_agent_blocks_pii(self):
        """PII in query should be blocked."""
        from backend.gateway.agent import run_agent
        result = run_agent("Find customer 123-45-6789", "test-session")

        assert result["blocked"] is True


# ===========================================================================
# Test: Agent execution — SQL route
# ===========================================================================
class TestAgentSQLRoute:
    @patch("backend.gateway.agent.save_interaction")
    @patch("backend.gateway.agent.call_visualise")
    @patch("backend.gateway.agent.call_summarise")
    @patch("backend.gateway.agent.call_execute_sql")
    @patch("backend.gateway.agent.call_nl_to_sql")
    @patch("backend.gateway.agent.call_fetch_schema")
    @patch("backend.gateway.agent.get_memory_context")
    def test_sql_route_full_flow(
        self, mock_memory, mock_schema, mock_nl, mock_exec,
        mock_summarise, mock_visualise, mock_save
    ):
        """SQL route should go through schema → nl_to_sql → execute → summarise → visualise."""
        mock_memory.return_value = ""
        mock_schema.return_value = "TABLE: orders (id, total, order_date)"
        mock_nl.return_value = "SELECT SUM(total) FROM orders;"
        mock_exec.return_value = {
            "columns": ["sum_total"],
            "rows": [{"sum_total": 10000}],
            "row_count": 1,
        }
        mock_summarise.return_value = "Total orders amount to $10,000."
        mock_visualise.return_value = json.dumps({"data": [], "layout": {}})
        mock_save.return_value = None

        from backend.gateway.agent import run_agent
        result = run_agent("Show total order value", "test-session")

        assert result["route"] == "sql"
        assert result["blocked"] is False
        assert result["hitl"] is False
        assert "SELECT" in result["sql"]
        assert "$10,000" in result["summary"]
        assert result["chart_json"] != ""

        mock_schema.assert_called_once()
        mock_nl.assert_called_once()
        mock_exec.assert_called_once()
        mock_summarise.assert_called_once()
        mock_visualise.assert_called_once()
        mock_save.assert_called_once()


# ===========================================================================
# Test: Agent execution — RAG route
# ===========================================================================
class TestAgentRAGRoute:
    @patch("backend.gateway.agent.save_interaction")
    @patch("backend.gateway.agent.call_visualise")
    @patch("backend.gateway.agent.call_summarise")
    @patch("backend.gateway.agent.call_execute_sql")
    @patch("backend.gateway.agent.call_nl_to_sql")
    @patch("backend.gateway.agent.call_fetch_schema")
    @patch("backend.gateway.agent.call_rag_search")
    @patch("backend.gateway.agent.get_memory_context")
    def test_rag_route_skips_sql(
        self, mock_memory, mock_rag, mock_schema, mock_nl,
        mock_exec, mock_summarise, mock_visualise, mock_save
    ):
        """RAG route should search docs and skip SQL entirely."""
        mock_memory.return_value = ""
        mock_rag.return_value = "Our return policy allows 30-day returns for all items."
        mock_save.return_value = None

        from backend.gateway.agent import run_agent
        result = run_agent("What is our return policy?", "test-session")

        assert result["route"] == "rag"
        assert result["sql"] == ""
        assert "return" in result["summary"].lower()

        mock_rag.assert_called_once()
        mock_nl.assert_not_called()
        mock_exec.assert_not_called()


# ===========================================================================
# Test: Agent execution — HITL
# ===========================================================================
class TestAgentHITL:
    @patch("backend.gateway.agent.save_interaction")
    @patch("backend.gateway.agent.call_visualise")
    @patch("backend.gateway.agent.call_summarise")
    @patch("backend.gateway.agent.call_execute_sql")
    @patch("backend.gateway.agent.call_nl_to_sql")
    @patch("backend.gateway.agent.call_fetch_schema")
    @patch("backend.gateway.agent.get_memory_context")
    def test_hitl_for_update(
        self, mock_memory, mock_schema, mock_nl, mock_exec,
        mock_summarise, mock_visualise, mock_save
    ):
        """UPDATE queries should trigger HITL without executing."""
        mock_memory.return_value = ""
        mock_schema.return_value = "TABLE: products (id, name, stock)"
        mock_nl.return_value = "UPDATE products SET stock = 100 WHERE id = 1"

        from backend.gateway.agent import run_agent
        result = run_agent("Update product 1 stock to 100", "test-session")

        assert result["hitl"] is True
        assert "approval" in result["error"].lower()
        # execute_sql should NOT have been called
        mock_exec.assert_not_called()

    @patch("backend.gateway.agent.save_interaction")
    @patch("backend.gateway.agent.call_visualise")
    @patch("backend.gateway.agent.call_summarise")
    @patch("backend.gateway.agent.call_execute_sql")
    @patch("backend.gateway.agent.call_nl_to_sql")
    @patch("backend.gateway.agent.call_fetch_schema")
    @patch("backend.gateway.agent.get_memory_context")
    def test_block_for_drop(
        self, mock_memory, mock_schema, mock_nl, mock_exec,
        mock_summarise, mock_visualise, mock_save
    ):
        """DROP queries should be blocked entirely."""
        mock_memory.return_value = ""
        mock_schema.return_value = "TABLE: orders"
        mock_nl.return_value = "DROP TABLE orders"

        from backend.gateway.agent import run_agent
        result = run_agent("Delete the orders table", "test-session")

        assert result["blocked"] is True
        assert "blocked" in result["error"].lower()
        mock_exec.assert_not_called()


# ===========================================================================
# Test: Agent execution — error handling
# ===========================================================================
class TestAgentErrors:
    @patch("backend.gateway.agent.save_interaction")
    @patch("backend.gateway.agent.call_visualise")
    @patch("backend.gateway.agent.call_summarise")
    @patch("backend.gateway.agent.call_execute_sql")
    @patch("backend.gateway.agent.call_nl_to_sql")
    @patch("backend.gateway.agent.call_fetch_schema")
    @patch("backend.gateway.agent.get_memory_context")
    def test_sql_execution_error(
        self, mock_memory, mock_schema, mock_nl, mock_exec,
        mock_summarise, mock_visualise, mock_save
    ):
        """SQL execution errors should be returned gracefully."""
        mock_memory.return_value = ""
        mock_schema.return_value = "TABLE: orders"
        mock_nl.return_value = "SELECT * FROM nonexistent_table"
        mock_exec.return_value = {"error": "Table not found: nonexistent_table"}

        from backend.gateway.agent import run_agent
        result = run_agent("Show data from nonexistent table", "test-session")

        assert "error" in result["error"].lower() or "Table not found" in result["error"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
