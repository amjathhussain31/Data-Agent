# memory/short_term.py
"""
Short-term conversation memory using LangChain's
ConversationBufferWindowMemory — keeps last k turns only.
Prevents context window bloat on long conversations.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from langchain.memory import ConversationBufferWindowMemory
from langchain.schema import HumanMessage, AIMessage
from config import MEMORY_WINDOW_K


def get_short_term_memory(k: int = MEMORY_WINDOW_K) -> ConversationBufferWindowMemory:
    """
    Returns a fresh ConversationBufferWindowMemory instance.
    k = number of conversation turns to keep.
    Each turn = 1 human message + 1 AI response.
    """
    return ConversationBufferWindowMemory(
        k=k,
        memory_key="chat_history",
        input_key="input",
        output_key="output",
        return_messages=True
    )


def add_turn(memory: ConversationBufferWindowMemory,
             user_input: str,
             ai_output: str) -> None:
    """
    Manually add a turn to memory.
    Used when not going through LangChain AgentExecutor directly.
    """
    memory.save_context(
        {"input": user_input},
        {"output": ai_output}
    )


def get_history_string(memory: ConversationBufferWindowMemory) -> str:
    """
    Returns memory as a plain string for prompt injection.
    Format: 'Human: ...\nAI: ...\nHuman: ...\nAI: ...'
    """
    messages = memory.load_memory_variables({}).get("chat_history", [])
    if not messages:
        return ""

    lines = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            lines.append(f"Human: {msg.content}")
        elif isinstance(msg, AIMessage):
            lines.append(f"AI: {msg.content}")
    return "\n".join(lines)


def get_turn_count(memory: ConversationBufferWindowMemory) -> int:
    """Returns how many turns are currently stored."""
    messages = memory.load_memory_variables({}).get("chat_history", [])
    return len(messages) // 2