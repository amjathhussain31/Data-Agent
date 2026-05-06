# tests/test_gateway.py
"""
Unit tests for the FastAPI gateway + LangGraph agent pipeline.
Mocks the MCP client (call_tool) to return fake responses.
"""

import os
import sys
import json
from unittest.mock import patch, MagicMock

import pytest

# Ensure project root is importable
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def mock_cloudwatch():
    with patch("backend.gateway.main.cloudwatch") as mock_cw:
        if mock_cw:
            mock_cw.put_metric_data.return_value = {}
        yield mock_cw


@pytest.fixture
def client():
    from backend.gateway.main import app
    return TestClient(app)


# ===========================================================================
# Test 1: Guardrail blocks PII (SSN)
# ===========================================================================
class TestGuardrailBlocksPII:
    def test_guardrail_blocks_pii(self, client):
        """A question containing an SSN should be blocked by input guardrails."""
        response = client.post("/query", json={
            "question": "Look up customer 123-45-6789",
            "session_id": "test-session-1",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["blocked"] is True
        assert "SSN" in data["error"] or "personal" in data["error"].lower()

    def test_guardrail_blocks_offtopic(self, client):
        """Off-topic questions (poems) should be blocked."""
        response = client.post("/query", json={
            "question": "Write me a poem about databases",
            "session_id": "test-session-2",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["blocked"] is True


# ===========================================================================
# Test 2: Query routes correctly
# ===========================================================================
class TestQueryRouting:
    def test_query_routes_sql(self):
        """'show sales' should route to sql."""
        from backend.gateway.query_router import route_query
        route = route_query("show total sales by region")
        assert route == "sql"

    def test_query_routes_rag(self):
        """'what is our return policy' should route to rag."""
        from backend.gateway.query_router import route_query
        route = route_query("what is our return policy")
        assert route == "rag"

    def test_query_routes_hybrid(self):
        """A question with both SQL and doc keywords should route hybrid."""
        from backend.gateway.query_router import route_query
        route = route_query("show sales mentioned in the annual report")
        assert route == "hybrid"


# ===========================================================================
# Test 3: HITL returned for UPDATE
# ===========================================================================
class TestHITL:
    @patch("backend.gateway.agent.call_rag_search")
    @patch("backend.gateway.agent.call_nl_to_sql")
    @patch("backend.gateway.agent.call_execute_sql")
    @patch("backend.gateway.agent.call_fetch_schema")
    @patch("backend.gateway.agent.get_memory_context")
    def test_hitl_returned_for_update(
        self, mock_memory, mock_schema, mock_exec, mock_nl, mock_rag, client
    ):
        """UPDATE SQL should trigger HITL flag in response."""
        mock_memory.return_value = ""
        mock_schema.return_value = "TABLE: products (id, name, stock)"
        mock_rag.return_value = ""
        mock_nl.return_value = "UPDATE products SET stock = 100 WHERE name = 'Laptop'"
        mock_exec.return_value = {"columns": [], "rows": [], "row_count": 0}

        response = client.post("/query", json={
            "question": "Update laptop stock to 100",
            "session_id": "test-session-3",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["hitl"] is True
        assert "approval" in data["error"].lower()


# ===========================================================================
# Test 4: Full pipeline mock — end to end
# ===========================================================================
class TestFullPipeline:
    @patch("backend.gateway.agent.save_interaction")
    @patch("backend.gateway.agent.call_visualise")
    @patch("backend.gateway.agent.call_summarise")
    @patch("backend.gateway.agent.call_execute_sql")
    @patch("backend.gateway.agent.call_nl_to_sql")
    @patch("backend.gateway.agent.call_fetch_schema")
    @patch("backend.gateway.agent.call_rag_search")
    @patch("backend.gateway.agent.get_memory_context")
    def test_full_pipeline_mock(
        self,
        mock_memory,
        mock_rag,
        mock_schema,
        mock_nl,
        mock_exec,
        mock_summarise,
        mock_visualise,
        mock_save,
        client,
    ):
        """End-to-end pipeline with all tools mocked should return complete response."""
        mock_memory.return_value = ""
        mock_rag.return_value = ""
        mock_schema.return_value = "TABLE: orders (id, customer_id, total, order_date)"
        mock_nl.return_value = "SELECT region, SUM(total) as revenue FROM orders GROUP BY region"
        mock_exec.return_value = {
            "columns": ["region", "revenue"],
            "rows": [
                {"region": "East", "revenue": 50000},
                {"region": "West", "revenue": 75000},
            ],
            "row_count": 2,
        }
        mock_summarise.return_value = "West region leads with $75K in revenue."
        mock_visualise.return_value = json.dumps({"data": [], "layout": {"title": "Sales"}})
        mock_save.return_value = None

        response = client.post("/query", json={
            "question": "Show total sales by region",
            "session_id": "test-session-4",
        })
        assert response.status_code == 200
        data = response.json()

        assert data["blocked"] is False
        assert data["hitl"] is False
        assert data["error"] == ""
        assert data["route"] == "sql"
        assert "SELECT" in data["sql"]
        assert "West" in data["summary"] or "75K" in data["summary"]
        assert data["chart_json"] != ""
        assert data["confidence"] > 0

    @patch("backend.gateway.agent.save_interaction")
    @patch("backend.gateway.agent.call_visualise")
    @patch("backend.gateway.agent.call_summarise")
    @patch("backend.gateway.agent.call_execute_sql")
    @patch("backend.gateway.agent.call_nl_to_sql")
    @patch("backend.gateway.agent.call_fetch_schema")
    @patch("backend.gateway.agent.call_rag_search")
    @patch("backend.gateway.agent.get_memory_context")
    def test_rag_route_skips_sql(
        self,
        mock_memory,
        mock_rag,
        mock_schema,
        mock_nl,
        mock_exec,
        mock_summarise,
        mock_visualise,
        mock_save,
        client,
    ):
        """RAG-only route should skip SQL generation and return RAG content."""
        mock_memory.return_value = ""
        mock_rag.return_value = "Our return policy allows 30-day returns."
        mock_schema.return_value = ""
        mock_save.return_value = None

        response = client.post("/query", json={
            "question": "What is our return policy?",
            "session_id": "test-session-5",
        })
        assert response.status_code == 200
        data = response.json()

        assert data["route"] == "rag"
        assert data["blocked"] is False
        assert "return policy" in data["summary"].lower() or "30-day" in data["summary"]
        assert data["sql"] == ""
        mock_nl.assert_not_called()


# ===========================================================================
# Test: Health endpoint
# ===========================================================================
class TestHealth:
    def test_health_endpoint(self, client):
        """Health endpoint should return 200 with status healthy."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
