DOC_PHRASES = [
    "return policy",
    "refund policy",
    "sales policy",
    "discount policy",
    "company policy",
    "what is our policy",
    "what are our",
    "what is our",
    "tell me about",
    "annual report",
    "q3 report",
    "q4 report",
    "company overview",
    "our company",
    "compliance",
    "guidelines",
    "portfolio",
    "founded",
    "headquarters",
    "according to",
    "based on the report",
    "warranty",
    "guarantee",
]

SQL_KEYWORDS = [
    "show", "list", "count", "total", "sum", "average", "avg",
    "how many", "how much", "top", "bottom", "highest", "lowest",
    "sales", "revenue", "orders", "order", "customers", "customer",
    "products", "product", "stock", "inventory",
    "region", "category", "segment", "spend", "spending",
    "last", "this", "year", "month", "quarter", "week", "today",
    "trend", "monthly", "yearly", "compare", "rank", "filter",
    "perform", "performance", "return rate", "returns by",
    "which product", "which region", "which customer",
]

DOC_KEYWORDS = [
    "policy", "annual", "report", "overview",
    "target", "goal", "strategy", "plan",
    "history", "refund", "document", "stated",
    "q3", "q4",
]


def route_query(query: str) -> str:
    """
    Returns: 'sql', 'rag', or 'hybrid'
    Priority: DOC_PHRASES > keyword matching
    """
    query_lower = query.lower()

    # Check doc phrases first — these override keyword matching
    matched_doc_phrase = any(phrase in query_lower for phrase in DOC_PHRASES)

    if matched_doc_phrase:
        # Check for strong SQL signal alongside doc phrase → hybrid
        has_sql = any(kw in query_lower for kw in SQL_KEYWORDS)
        if has_sql:
            return "hybrid"
        return "rag"

    # Keyword matching
    has_sql = any(kw in query_lower for kw in SQL_KEYWORDS)
    has_doc = any(kw in query_lower for kw in DOC_KEYWORDS)

    if has_sql and has_doc:
        return "hybrid"
    elif has_doc and not has_sql:
        return "rag"
    else:
        return "sql"