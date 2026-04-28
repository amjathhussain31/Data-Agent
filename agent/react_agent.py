# agent/react_agent.py
"""
LangChain ReAct agent — the brain of the entire system.
Wires together: tools + memory + RAG + guardrails + Gemini.
"""
import os
import sys
import uuid
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from langchain.agents import AgentExecutor, create_react_agent
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.tools import Tool
from langchain.prompts import PromptTemplate
from langchain_community.vectorstores import FAISS
from langchain.memory import ConversationBufferWindowMemory

from config import GEMINI_API_KEY, GEMINI_MODEL, SQLITE_DB_URL
from tools.sql_executor     import execute_sql_as_string
from tools.schema_fetcher   import get_schema, format_schema_for_prompt
from tools.chart_builder    import build_chart_from_string
from tools.insight_generator import generate_insight_from_string
from memory.long_term       import get_recent_history


# ─────────────────────────────────────────
# REACT PROMPT
# ─────────────────────────────────────────

REACT_PROMPT_TEMPLATE = """You are a data analyst agent with access to a SQL database.
You ONLY answer questions about data, databases, SQL queries, and analytics.

TOOLS:
------
{tools}

DATABASE SCHEMA:
----------------
{schema}

LONG TERM MEMORY (past queries):
---------------------------------
{long_term_memory}

CONVERSATION HISTORY:
---------------------
{chat_history}

INSTRUCTIONS:
-------------
- Always use schema_fetcher first if you are unsure about table/column names
- Always use rag_retriever to understand business terms before writing SQL
- Use sql_executor to run the query — never guess results
- Use insight_generator after every sql_executor call
- Use chart_builder when results have numeric data
- If a query is blocked by guardrails, explain why to the user politely
- For follow-up questions, use conversation history to resolve references

Use this EXACT format for every step:

Question: the input question you must answer
Thought: your reasoning about what to do next
Action: the tool to use — must be one of [{tool_names}]
Action Input: the input to the tool
Observation: the result of the tool
... (repeat Thought/Action/Action Input/Observation as needed)
Thought: I now know the final answer
Final Answer: your complete answer including the insight

Begin!

Question: {input}
Thought: {agent_scratchpad}"""


# ─────────────────────────────────────────
# TOOL DEFINITIONS
# ─────────────────────────────────────────

def build_tools(vectorstore: FAISS = None,
                db_url: str = SQLITE_DB_URL) -> list:
    """Builds and returns all 5 agent tools."""

    def schema_fetcher_fn(_: str) -> str:
        schema, source = get_schema(prefer_mcp=True)
        return format_schema_for_prompt(schema)

    def rag_retriever_fn(query: str) -> str:
        if vectorstore is None:
            return "RAG not available."
        from rag.retriever import retrieve_context
        return retrieve_context(vectorstore, query, k=3)

    def sql_executor_fn(sql: str) -> str:
        return execute_sql_as_string(sql, db_url=db_url, auto_approve=False)

    def chart_builder_fn(data_json: str) -> str:
        return build_chart_from_string(data_json)

    def insight_generator_fn(input_str: str) -> str:
        # input_str format: "query|||data_json"
        parts = input_str.split("|||")
        query = parts[0].strip() if len(parts) > 0 else ""
        data  = parts[1].strip() if len(parts) > 1 else "{}"
        return generate_insight_from_string(data, query)

    return [
        Tool(
            name="schema_fetcher",
            func=schema_fetcher_fn,
            description=(
                "Fetches the full database schema including all table names, "
                "column names, types, and foreign keys. "
                "Use this first when unsure about table or column names. "
                "Input: any string (ignored)."
            )
        ),
        Tool(
            name="rag_retriever",
            func=rag_retriever_fn,
            description=(
                "Retrieves relevant documentation about column meanings, "
                "business terms, and how to calculate metrics like return rate, "
                "revenue, AOV, etc. "
                "Input: your question or the business term you want to understand."
            )
        ),
        Tool(
            name="sql_executor",
            func=sql_executor_fn,
            description=(
                "Executes a SQL SELECT query on the database and returns results. "
                "Input: a complete, valid SQL SELECT statement. "
                "Do not include markdown fences or backticks. "
                "Only SELECT queries are allowed — others will be blocked."
            )
        ),
        Tool(
            name="insight_generator",
            func=insight_generator_fn,
            description=(
                "Generates a plain-English summary of query results. "
                "Input format: 'user question|||JSON array of result rows' "
                "Example: 'sales by region|||[{\"region\":\"North\",\"total\":65000}]'"
            )
        ),
        Tool(
            name="chart_builder",
            func=chart_builder_fn,
            description=(
                "Builds a chart from query results. "
                "Input: JSON array string of result rows. "
                "Example: '[{\"region\":\"North\",\"sales\":65000}]' "
                "Returns chart type and confirmation."
            )
        ),
    ]


# ─────────────────────────────────────────
# AGENT BUILDER
# ─────────────────────────────────────────

def build_agent(memory: ConversationBufferWindowMemory,
                vectorstore: FAISS = None,
                db_url: str = SQLITE_DB_URL) -> AgentExecutor:

    # LLM selection — Groq or Gemini
    from config import USE_GROQ, GROQ_API_KEY, GROQ_MODEL
    if USE_GROQ:
        from langchain_groq import ChatGroq
        llm = ChatGroq(
            model=GROQ_MODEL,
            api_key=GROQ_API_KEY,
            temperature=0
        )
        print(f"[agent] Using Groq — {GROQ_MODEL}")
    else:
        from langchain_google_genai import ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(
            model=GEMINI_MODEL,
            google_api_key=GEMINI_API_KEY,
            temperature=0,
            convert_system_message_to_human=True
        )
        print(f"[agent] Using Gemini — {GEMINI_MODEL}")

    # rest of build_agent() stays exactly the same
    tools       = build_tools(vectorstore, db_url)
    schema, _   = get_schema(prefer_mcp=True)
    schema_text = format_schema_for_prompt(schema)

    prompt = PromptTemplate(
        input_variables=[
            "input", "tools", "tool_names",
            "agent_scratchpad", "chat_history",
            "schema", "long_term_memory"
        ],
        template=REACT_PROMPT_TEMPLATE
    )

    agent = create_react_agent(llm, tools, prompt)

    return AgentExecutor(
        agent=agent,
        tools=tools,
        memory=memory,
        verbose=True,
        max_iterations=8,
        handle_parsing_errors=True,
        return_intermediate_steps=True
    )

def run_agent(agent_executor: AgentExecutor,
              query: str,
              session_id: str = None,
              user_id: str = "default") -> dict:
    """
    Runs a query through the agent with full Langfuse tracing.
    Every tool call, LLM call, and step is automatically traced
    via the LangChain callback handler.
    """
    from observability.langfuse_client import get_langchain_handler, flush

    if session_id is None:
        session_id = str(uuid.uuid4())

    long_term   = get_recent_history(n=3)
    schema, _   = get_schema(prefer_mcp=True)
    schema_text = format_schema_for_prompt(schema)

    # Langfuse callback — traces entire agent run automatically
    handler = get_langchain_handler(
        session_id=session_id,
        user_id=user_id,
        trace_name=f"agent: {query[:50]}"
    )

    for attempt in range(3):
        try:
            result = agent_executor.invoke(
                {
                    "input":            query,
                    "schema":           schema_text,
                    "long_term_memory": long_term,
                },
                config={"callbacks": [handler]}   # <-- Langfuse wired here
            )
            flush()
            return {
                "output":     result.get("output", ""),
                "steps":      result.get("intermediate_steps", []),
                "error":      None,
                "session_id": session_id
            }
        except Exception as e:
            if "429" in str(e) and attempt < 2:
                wait = 20 * (attempt + 1)
                print(f"[rate limit] Waiting {wait}s... retry {attempt+2}/3")
                time.sleep(wait)
            else:
                flush()
                return {
                    "output":     "",
                    "steps":      [],
                    "error":      str(e),
                    "session_id": session_id
                }