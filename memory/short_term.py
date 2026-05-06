# memory/short_term.py
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from langchain.memory import ConversationBufferWindowMemory
from langchain.schema import HumanMessage, AIMessage
from config import MEMORY_WINDOW_K


def get_short_term_memory(k: int = MEMORY_WINDOW_K) -> ConversationBufferWindowMemory:
    return ConversationBufferWindowMemory(
        k=k,
        memory_key="chat_history",
        input_key="input",
        output_key="output",
        return_messages=True
    )


def add_turn(memory, user_input: str, ai_output: str) -> None:
    memory.save_context({"input": user_input}, {"output": ai_output})


def get_history_string(memory) -> str:
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


def get_turn_count(memory) -> int:
    messages = memory.load_memory_variables({}).get("chat_history", [])
    return len(messages) // 2