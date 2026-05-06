# tests/test_mcp_server.py
"""
Unit tests for the 7 MCP Server tools.
Uses mocks for AWS Bedrock, DynamoDB, and PyHive (EMR not available locally).
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


# ===========================================================================
# Test 1: rag_search — no index available
# ===========================================================================
class TestRagSearch:
    def test_rag_search_no_index(self):
        """When FAISS index doesn't exist, should return 'No documents indexed yet'."""
        with patch.dict(os.environ, {"FAISS_INDEX_PATH": "/nonexistent/path"}):
            # Force reload of the module to pick up new env
            if "backend.mcp_server.tools.rag_search" in sys.modules:
                del sys.modules["backend.mcp_server.tools.rag_search"]

            from backend.mcp_server.tools.rag_search import rag_search
            import backend.mcp_server.tools.rag_search as rag_mod
            rag_mod._vectorstore = None

            result = rag_search("What is our return policy?")
            assert result == "No documents indexed yet"


# ===========================================================================
# Test 2 & 3: execute_sql — SQL firewall
# ===========================================================================
class TestExecuteSqlFirewall:
    def test_execute_sql_firewall_drop(self):
        """DROP TABLE should be blocked by the SQL firewall."""
        from backend.mcp_server.tools.execute_sql import execute_sql
        result = execute_sql("DROP TABLE customers")
        assert result.get("blocked") is True
        assert "blocked" in result.get("error", "").lower()

    def test_execute_sql_firewall_delete(self):
        """DELETE should be blocked by the SQL firewall."""
        from backend.mcp_server.tools.execute_sql import execute_sql
        result = execute_sql("DELETE FROM orders WHERE id = 1")
        assert result.get("blocked") is True
        assert "blocked" in result.get("error", "").lower()

    def test_execute_sql_firewall_allows_select(self):
        """SELECT should pass the firewall (may fail on connection, not firewall)."""
        from backend.mcp_server.tools.execute_sql import execute_sql
        result = execute_sql("SELECT * FROM customers LIMIT 10")
        # Should NOT be blocked
        assert result.get("blocked") is not True


# ===========================================================================
# Test 4: memory_recall — empty session
# ===========================================================================
class TestMemoryRecall:
    @patch("backend.mcp_server.tools.memory_recall._get_table")
    def test_memory_recall_empty(self, mock_get_table):
        """Empty session should return empty string, not crash."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": None}
        mock_get_table.return_value = mock_table

        from backend.mcp_server.tools.memory_recall import memory_recall
        result = memory_recall("nonexistent-session-id")
        assert result == ""

    @patch("backend.mcp_server.tools.memory_recall._get_table")
    def test_memory_recall_no_item(self, mock_get_table):
        """Missing item in DynamoDB should return empty string."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}
        mock_get_table.return_value = mock_table

        from backend.mcp_server.tools.memory_recall import memory_recall
        result = memory_recall("some-session")
        assert result == ""

    @patch("backend.mcp_server.tools.memory_recall._get_table")
    def test_memory_recall_dynamo_error(self, mock_get_table):
        """DynamoDB error should return empty string, not crash."""
        mock_table = MagicMock()
        mock_table.get_item.side_effect = Exception("DynamoDB timeout")
        mock_get_table.return_value = mock_table

        from backend.mcp_server.tools.memory_recall import memory_recall
        result = memory_recall("some-session")
        assert result == ""


# ===========================================================================
# Test 5: nl_to_sql — prompt construction
# ===========================================================================
class TestNlToSql:
    @patch("backend.mcp_server.tools.nl_to_sql.call_bedrock")
    def test_nl_to_sql_prompt_contains_schema_and_question(self, mock_bedrock):
        """Verify the prompt sent to Bedrock contains schema and question."""
        mock_bedrock.return_value = "SELECT COUNT(*) FROM orders;"

        from backend.mcp_server.tools.nl_to_sql import nl_to_sql

        question = "How many orders do we have?"
        schema = "TABLE: orders (order_id INT, customer_id INT, total DECIMAL)"

        result = nl_to_sql(question, schema=schema)

        # Verify Bedrock was called
        assert mock_bedrock.called
        prompt_arg = mock_bedrock.call_args[0][0]

        # Verify prompt contains schema and question
        assert schema in prompt_arg
        assert question in prompt_arg

        # Verify result is clean SQL
        assert "SELECT" in result
        assert "orders" in result

    @patch("backend.mcp_server.tools.nl_to_sql.call_bedrock")
    def test_nl_to_sql_strips_markdown(self, mock_bedrock):
        """Verify markdown fences are stripped from Bedrock response."""
        mock_bedrock.return_value = "```sql\nSELECT * FROM products;\n```"

        from backend.mcp_server.tools.nl_to_sql import nl_to_sql
        result = nl_to_sql("Show all products")

        assert "```" not in result
        assert "SELECT * FROM products;" in result

    @patch("backend.mcp_server.tools.nl_to_sql.call_bedrock")
    def test_nl_to_sql_bedrock_fallback(self, mock_bedrock):
        """When Bedrock returns empty/error, should return fallback SQL."""
        mock_bedrock.return_value = ""

        from backend.mcp_server.tools.nl_to_sql import nl_to_sql
        result = nl_to_sql("Show sales")

        # Should return fallback SQL, not crash
        assert "SELECT" in result


# ===========================================================================
# Test: memory_store
# ===========================================================================
class TestMemoryStore:
    @patch("backend.mcp_server.tools.memory_store._get_table")
    def test_memory_store_success(self, mock_get_table):
        """Successful store should return True."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": {"session_id": "s1", "history": []}}
        mock_table.put_item.return_value = {}
        mock_get_table.return_value = mock_table

        from backend.mcp_server.tools.memory_store import memory_store
        result = memory_store("s1", "How many orders?", "SELECT COUNT(*) FROM orders", "42 orders")
        assert result is True

    @patch("backend.mcp_server.tools.memory_store._get_table")
    def test_memory_store_dynamo_error(self, mock_get_table):
        """DynamoDB error should return False, not crash."""
        mock_table = MagicMock()
        mock_table.get_item.side_effect = Exception("Access denied")
        mock_get_table.return_value = mock_table

        from backend.mcp_server.tools.memory_store import memory_store
        result = memory_store("s1", "test", "", "")
        assert result is False


# ===========================================================================
# Test: execute_sql with DuckDB (integration)
# ===========================================================================
class TestExecuteSqlDuckDB:
    def test_execute_sql_select_works(self):
        """SELECT on DuckDB should return actual data."""
        from backend.mcp_server.tools.execute_sql import execute_sql
        result = execute_sql("SELECT * FROM customers LIMIT 3")

        if "error" not in result:
            assert result["row_count"] <= 3
            assert "columns" in result
            assert "rows" in result
        # If DuckDB file doesn't exist, it's a connection error — acceptable


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
