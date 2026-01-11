from langgraph.graph import StateGraph, START, END
from langgraph.constants import Send
from langgraph.types import RetryPolicy
from app.state import AgentState
from app.agent.nodes import (
    monitor_news,
    scraper_node,
    summarize_node,
    editor_writer,
)

# Define Retry Policy for robust execution
retry_policy = RetryPolicy(
    max_attempts=3,
    initial_interval=2,
    backoff_factor=2,
    retry_on=(Exception,),
)


def map_articles_to_summaries(state: AgentState):
    """
    This function generates the parallel tasks.
    It takes the global state, finds the 'raw_news',
    and returns a list of Send() objects.
    """
    return [
        Send("summarizer", {"content": article})
        for article in state["scraped_articles"]
    ]


# Build the Graph
workflow = StateGraph(AgentState)

# Add Nodes
workflow.add_node("monitor", monitor_news, retry=retry_policy)
workflow.add_node(
    "scraper", scraper_node
)  # Scraper has internal try/except, no graph retry needed
workflow.add_node("summarizer", summarize_node, retry=retry_policy)
workflow.add_node("editor", editor_writer, retry=retry_policy)

# Add Edges
workflow.add_edge(START, "monitor")
workflow.add_edge("monitor", "scraper")
workflow.add_conditional_edges("scraper", map_articles_to_summaries, ["summarizer"])
workflow.add_edge("summarizer", "editor")
workflow.add_edge("editor", END)

# Compile
workflow_app = workflow.compile()
