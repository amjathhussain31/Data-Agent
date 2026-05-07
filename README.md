# DataMind Agent

**AI-Powered Enterprise Data Analytics Platform**

Transform natural language questions into actionable business insights — powered by AWS Bedrock, LangGraph, and the Model Context Protocol (MCP).

---

## Overview

DataMind Agent is an intelligent data analytics platform that enables business users to query databases, generate insights, and visualize data using plain English. No SQL knowledge required.

Upload any CSV dataset, ask questions like *"Show monthly revenue trend by region"*, and receive:
- Auto-generated SQL queries
- Business intelligence summaries
- Interactive Plotly visualizations
- Conversation memory for contextual follow-ups

---

## Key Features

| Feature | Description |
|---------|-------------|
| **Natural Language to SQL** | Converts business questions to optimized SQL using AWS Bedrock (Claude 3 Haiku) |
| **Intelligent Query Routing** | Automatically routes queries to SQL, RAG (documents), or hybrid paths |
| **Multi-Chart Visualization** | 8 chart types (bar, line, pie, scatter, area, histogram, stacked bar, heatmap) with smart auto-detection |
| **S3-Backed Data Lake** | Upload CSVs → stored in S3 → queryable instantly. S3 is the single source of truth |
| **LangGraph Supervisor Agent** | 12-node state machine with conditional routing, error handling, and HITL approval |
| **Input/Output Guardrails** | PII detection, topic filtering, SQL injection prevention, write operation blocking |
| **Human-in-the-Loop (HITL)** | UPDATE/INSERT operations require explicit user approval before execution |
| **Conversation Memory** | Short-term (session RAM) + long-term (DynamoDB) for contextual multi-turn queries |
| **RAG Document Search** | FAISS vector search over enterprise documents (policies, reports, guidelines) |
| **MCP Protocol** | Model Context Protocol server exposing 8 tools via FastMCP SDK |
| **Observability** | CloudWatch metrics: query latency, guardrail blocks, tool errors, confidence scores |
| **Dynamic Schema Awareness** | Agent reads actual column names (including spaces) and generates correct quoted SQL |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Streamlit UI (port 8501)                  │
│              Chat • Upload • Charts • HITL Approval           │
└─────────────────────────┬───────────────────────────────────┘
                          │ REST API
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                  FastAPI Gateway (port 8001)                  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │            LangGraph Supervisor Agent                    │ │
│  │                                                          │ │
│  │  Guardrails → Router → Memory → Schema → NL-to-SQL     │ │
│  │       │                              │                   │ │
│  │       ▼                              ▼                   │ │
│  │  [BLOCK/PASS]              SQL Guardrails → Execute      │ │
│  │                                      │                   │ │
│  │                              Summarise → Visualise       │ │
│  │                                      │                   │ │
│  │                              Save → Confidence → END     │ │
│  └────────────────────────────────────────────────────────┘ │
└──────┬──────────────┬──────────────┬──────────────┬─────────┘
       │              │              │              │
       ▼              ▼              ▼              ▼
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│  Bedrock │   │    S3    │   │ DynamoDB │   │CloudWatch│
│  Claude  │   │ Datalake │   │  Memory  │   │ Metrics  │
│  Haiku   │   │          │   │          │   │          │
└──────────┘   └────┬─────┘   └──────────┘   └──────────┘
                    │
                    ▼
             ┌──────────┐
             │  DuckDB  │
             │ (in-mem) │
             │  Engine  │
             └──────────┘
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **LLM** | AWS Bedrock — Claude 3 Haiku |
| **Agent Framework** | LangGraph (state machine, 12 nodes, conditional edges) |
| **Tool Protocol** | MCP (Model Context Protocol) via FastMCP SDK |
| **API Gateway** | FastAPI + Uvicorn |
| **Query Engine** | DuckDB (in-memory, mirrors S3 data) |
| **Data Lake** | AWS S3 |
| **Memory** | AWS DynamoDB (long-term) + Python dict (short-term) |
| **RAG** | FAISS + Sentence-Transformers (all-MiniLM-L6-v2) |
| **Visualization** | Plotly (8 chart types, dark theme) |
| **Frontend** | Streamlit |
| **Observability** | AWS CloudWatch |
| **Security** | Input guardrails, SQL firewall, PII detection, HITL |

---

## Quick Start

### Prerequisites
- Python 3.11+
- AWS account with Bedrock access enabled
- S3 bucket created

### Local Development

```bash
# Clone
git clone https://github.com/amjathhussain31/Data-Agent.git
cd Data-Agent

# Install
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your AWS credentials

# Run
python backend/gateway/main.py &
streamlit run frontend/app.py
```

Access at `http://localhost:8501`

### AWS Deployment (EC2)

```bash
# On EC2 instance
git clone https://github.com/amjathhussain31/Data-Agent.git ~/data_agent
cd ~/data_agent
pip install -r requirements.txt

# Start with nohup (survives terminal close)
nohup python3 backend/gateway/main.py > gateway.log 2>&1 &
nohup python3 -m streamlit run frontend/app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true > streamlit.log 2>&1 &
```

---

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `AWS_REGION` | AWS region | `us-east-1` |
| `BEDROCK_SQL_MODEL` | Model for SQL generation | `anthropic.claude-3-haiku-20240307-v1:0` |
| `BEDROCK_SUMMARY_MODEL` | Model for summarization | `anthropic.claude-3-haiku-20240307-v1:0` |
| `S3_DATALAKE_BUCKET` | S3 bucket for data storage | `datamind-datalake-zyphron` |
| `DYNAMODB_MEMORY_TABLE` | DynamoDB table for memory | `datamind_memory` |
| `MCP_USE_DIRECT` | Direct tool calls (local) | `true` |
| `GATEWAY_PORT` | Gateway API port | `8001` |

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/query` | Execute a natural language query |
| `POST` | `/upload` | Upload CSV file to S3 + create table |
| `POST` | `/refresh` | Sync DuckDB tables from S3 bucket |
| `GET` | `/tables` | List all available tables |
| `GET` | `/health` | Service health check |

### Query Request
```json
{
  "question": "Show total revenue by product category",
  "session_id": "user-session-123"
}
```

### Query Response
```json
{
  "sql": "SELECT category, SUM(revenue) FROM sales GROUP BY category",
  "summary": "Electronics leads with $2.1M in revenue, 35% of total...",
  "chart_json": "{plotly figure JSON}",
  "confidence": 0.9,
  "route": "sql",
  "blocked": false,
  "hitl": false,
  "error": ""
}
```

---

## Agent Pipeline

```
User Question
     │
     ▼
[1] Input Guardrails ──── Block PII, off-topic, injection
     │
     ▼
[2] Query Router ──────── sql / rag / hybrid
     │
     ▼
[3] Memory Recall ─────── Last 3 turns for context
     │
     ▼
[4] RAG Search ────────── Document retrieval (if rag/hybrid)
     │
     ▼
[5] Fetch Schema ──────── Real column names from DuckDB
     │
     ▼
[6] NL → SQL ──────────── Bedrock generates query with schema awareness
     │
     ▼
[7] SQL Guardrails ────── ALLOW / HITL / BLOCK
     │
     ▼
[8] Execute SQL ────────── DuckDB in-memory (data from S3)
     │
     ▼
[9] Summarise ─────────── Bedrock generates business insight
     │
     ▼
[10] Visualise ─────────── Auto-detect chart type, build Plotly figure
     │
     ▼
[11] Save & Return ────── Memory + CloudWatch + Response
```

---

## Security

| Layer | Protection |
|-------|-----------|
| **Input** | Topic filtering (blocks poems, jokes, weather), PII detection (SSN, credit cards, emails, phone numbers) |
| **SQL** | Firewall blocks DROP, DELETE, TRUNCATE, EXEC. Requires HITL approval for UPDATE, INSERT, ALTER |
| **Output** | No raw credentials exposed, error messages sanitized |
| **Data** | S3 bucket with public access blocked, IAM role-based access |

---

## Testing

```bash
# Run all 31 tests
python -m pytest tests/ -v

# Test suites:
# - test_agent.py      (9 tests)  — LangGraph agent flow
# - test_gateway.py    (9 tests)  — API endpoints
# - test_mcp_server.py (13 tests) — Individual tools
```

---

## Project Structure

```
Data-Agent/
├── backend/
│   ├── gateway/
│   │   ├── main.py              # FastAPI app + endpoints
│   │   ├── agent.py             # LangGraph supervisor (12 nodes)
│   │   ├── mcp_client.py        # Tool caller (direct/remote)
│   │   ├── db_upload.py         # S3 upload + DuckDB sync
│   │   ├── memory_manager.py    # Short + long term memory
│   │   ├── guardrails.py        # Input/output safety
│   │   └── query_router.py      # sql/rag/hybrid routing
│   ├── mcp_server/
│   │   ├── server.py            # FastMCP server (8 tools)
│   │   └── tools/
│   │       ├── nl_to_sql.py     # Bedrock NL→SQL
│   │       ├── execute_sql.py   # DuckDB executor + firewall
│   │       ├── rag_search.py    # FAISS vector search
│   │       ├── summarise.py     # Bedrock summarization
│   │       ├── visualise.py     # Plotly chart builder
│   │       ├── memory_store.py  # DynamoDB write
│   │       └── memory_recall.py # DynamoDB read
│   ├── guardrails/
│   │   ├── input_rails.py       # Topic + PII filters
│   │   └── output_rails.py      # SQL classification
│   ├── rag/
│   │   ├── embedder.py          # FAISS index management
│   │   └── retriever.py         # Vector similarity search
│   └── utils/
│       └── aws_clients.py       # Bedrock, DynamoDB, CloudWatch
├── frontend/
│   └── app.py                   # Streamlit UI
├── tests/                       # 31 unit + integration tests
├── scripts/                     # Deployment + setup scripts
├── config.py                    # Centralized configuration
├── requirements.txt             # Python dependencies
└── README.md
```

---

## Deployment Options

| Environment | Data Engine | Cost |
|-------------|------------|------|
| **Local** | DuckDB in-memory | Free |
| **EC2 (current)** | DuckDB + S3 | ~$1/day |
| **Production** | EMR Hive/Spark + S3 | ~$12/hour |

---

## License

MIT

---

## Authors

Built for Cognizant Hackathon 2024 by Team Zyphron.
