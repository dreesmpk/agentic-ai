import operator
from typing import Annotated, List, TypedDict
from langgraph.graph import StateGraph, START, END
from langchain.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_tavily import TavilySearch
from langchain_anthropic import ChatAnthropic
from langgraph.types import Send
from langgraph.prebuilt import ToolNode
import json


class AgentState(TypedDict):
    topic: str
    messages: Annotated[list, operator.add]
    notes: Annotated[List[str], operator.add]


class SummarizerInput(TypedDict):
    topic: str
    content: str


# Initialize tools and model
tool = TavilySearch(max_results=3, topic="general")
tools = [tool]

llm = ChatAnthropic(model="claude-sonnet-4-5-20250929")
llm_with_tools = llm.bind_tools(tools)


def chatbot(state: AgentState):
    """Research agent node that decides if more research is needed."""
    try:
        messages = [
            SystemMessage(
                f"You are a researcher researching: {state['topic']}. "
                "Search for relevant information to build a comprehensive understanding."
            )
        ] + state["messages"]
        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}
    except Exception as e:
        print(f"Error in chatbot: {e}")
        return {"messages": [AIMessage(content=f"Error occurred: {str(e)}")]}


tool_node = ToolNode(tools)


def summarize_docs(state: AgentState):
    """Summarize search results relevant to the topic."""
    try:
        tool_message = state["messages"][-1]

        if isinstance(tool_message, ToolMessage):
            content = tool_message.content
            # Try to parse if it's JSON, otherwise use as-is
            try:
                if isinstance(content, str):
                    content = json.loads(content)
            except json.JSONDecodeError:
                pass
        else:
            return {"notes": ["No search results found."]}

        # Format content for summarization
        content_str = str(content) if not isinstance(content, str) else content

        response = llm.invoke(
            [
                HumanMessage(
                    f"Summarize the following search results relevant to '{state['topic']}':\n\n{content_str}\n\n"
                    "Provide a concise summary highlighting key findings."
                )
            ]
        )
        return {"notes": [response.content]}
    except Exception as e:
        print(f"Error summarizing: {e}")
        return {"notes": [f"Summarization failed: {str(e)}"]}


def synthesize_answer(state: AgentState):
    """Synthesize all gathered notes into a comprehensive report."""
    try:
        notes = (
            "\n\n".join(state["notes"])
            if state["notes"]
            else "No research notes found."
        )

        response = llm.invoke(
            [
                HumanMessage(
                    f"Based on the following research notes about '{state['topic']}', "
                    f"write a comprehensive, well-structured report:\n\n{notes}"
                )
            ]
        )
        return {"messages": [response]}
    except Exception as e:
        print(f"Error synthesizing: {e}")
        return {"messages": [AIMessage(content=f"Synthesis failed: {str(e)}")]}


def should_continue(state: AgentState):
    """Determine if more research is needed or if we should synthesize."""
    try:
        last_message = state["messages"][-1]

        # If it's an AI message, check for tool calls
        if isinstance(last_message, AIMessage):
            if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                return "tools"

        # Otherwise, move to synthesis
        return "synthesize"
    except Exception as e:
        print(f"Error in continuation logic: {e}")
        return "synthesize"


def map_from_tools(state: AgentState):
    """Route tool outputs to summarization."""
    try:
        # After tools execute, summarize the results
        return Send(node="summarize", arg=state)
    except Exception as e:
        print(f"Error mapping from tools: {e}")
        return "synthesize"


# Build the graph
graph = StateGraph(state_schema=AgentState)

# Add nodes
graph.add_node("chatbot", chatbot)
graph.add_node("tools", tool_node)
graph.add_node("summarize", summarize_docs)
graph.add_node("synthesize", synthesize_answer)

# Set entry point
graph.add_edge(START, "chatbot")

# Add conditional edge from chatbot
graph.add_conditional_edges("chatbot", should_continue)

# Tool results go to summarization
graph.add_edge("tools", "summarize")

# Summarization goes to synthesis
graph.add_edge("summarize", "synthesize")

# End the graph
graph.add_edge("synthesize", END)

compiled = graph.compile()

# Run the agent
if __name__ == "__main__":
    initial_state = AgentState(
        topic="State of the art of agentic AI",
        messages=[
            HumanMessage(
                "Please research the topic provided and write a comprehensive summary."
            )
        ],
        notes=[],
    )

    try:
        final_state = compiled.invoke(initial_state)
        final_answer = final_state["messages"][-1].content

        filename = "agent_research_report.md"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(final_answer)

        print(f"✅ Success! Report saved to {filename}")
    except Exception as e:
        print(f"❌ Agent execution failed: {e}")
