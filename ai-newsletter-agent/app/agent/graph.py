from langgraph.graph import StateGraph, END
from app.agent.nodes import monitor_news, scraper_node, summarize_node, editor_writer
from app.state import AgentState

# 1. Define the workflow
workflow = StateGraph(AgentState)

# 2. Add Nodes
workflow.add_node("monitor", monitor_news)
workflow.add_node("scraper", scraper_node)
workflow.add_node("summarizer", summarize_node)
workflow.add_node("editor", editor_writer)

# 3. Set Entry Point
workflow.set_entry_point("monitor")

# 4. Add Simple Linear Edges
workflow.add_edge("monitor", "scraper")
workflow.add_edge("scraper", "summarizer")
workflow.add_edge("summarizer", "editor")
workflow.add_edge("editor", END)

# 5. Compile
workflow_app = workflow.compile()
