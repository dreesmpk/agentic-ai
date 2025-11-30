import operator
import json
from typing import Annotated, List, TypedDict, Literal
from langchain_tavily import TavilySearch
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import RetryPolicy


# --- 1. Define Agent State ---
class AgentState(TypedDict):
    topic: str
    messages: Annotated[list, add_messages]
    notes: Annotated[List[str], operator.add]
    sources: Annotated[List[str], operator.add]
    loop_step: Annotated[int, operator.add]


# --- 2. Setup Tools & Model ---
tool = TavilySearch(max_results=2, topic="general")
tools = [tool]

llm = ChatAnthropic(model="claude-sonnet-4-5-20250929", temperature=0)
llm_with_tools = llm.bind_tools(tools)


# --- 3. Define Nodes ---
def chatbot(state: AgentState):
    current_notes = "\n".join(state.get("notes", []))
    current_loop = state.get("loop_step", 0)

    # Make the prompt stricter about the limit
    loop_instruction = ""
    if current_loop >= 3:
        loop_instruction = "This is your FINAL chance to research. Do not ask for more searches after this."

    system_prompt = (
        f"You are a senior researcher working on: '{state['topic']}'.\n"
        f"Current Iteration: {current_loop}/3. {loop_instruction}\n\n"
        f"Here are the notes you have gathered so far:\n"
        f"{'No notes yet.' if not current_notes else current_notes}\n\n"
        "Instructions:\n"
        "1. If you need more information, call the search tool.\n"
        "2. If you have sufficient information, simply reply with 'READY_TO_REPORT'.\n"
    )

    messages = [SystemMessage(content=system_prompt)] + state["messages"]
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


def summarize_search(state: AgentState):
    tool_message = state["messages"][-1]

    try:
        content = tool_message.content
        data = json.loads(content) if isinstance(content, str) else content
    except:
        data = tool_message.content

    results = data.get("results", []) if isinstance(data, dict) else data

    new_sources = []
    content_text = ""

    if isinstance(results, list):
        for res in results:
            if isinstance(res, dict):
                url = res.get("url", "Unknown")
                raw_content = res.get("content", "")

                # Truncate to avoid Rate Limits
                if len(raw_content) > 5000:
                    raw_content = raw_content[:5000] + "... [truncated]"

                new_sources.append(url)
                content_text += f"Source ({url}):\n{raw_content}\n\n"

    if not content_text:
        return {"notes": ["Search returned no usable text."], "loop_step": 1}

    summary_prompt = f"Extract key facts from these results regarding '{state['topic']}':\n\n{content_text}"
    response = llm.invoke([HumanMessage(content=summary_prompt)])

    # Increment loop_step by 1
    return {"notes": [response.content], "sources": new_sources, "loop_step": 1}


def human_review_node(state: AgentState):
    pass


def synthesize_report(state: AgentState):
    notes = "\n\n".join(state["notes"])
    sources = "\n".join([f"- {s}" for s in set(state["sources"])])

    prompt = (
        f"Topic: {state['topic']}\n\n"
        f"Research Notes:\n{notes}\n\n"
        f"Sources:\n{sources}\n\n"
        "Write a comprehensive report. Include a References section."
    )
    response = llm.invoke([HumanMessage(content=prompt)])
    return {"messages": [response]}


# --- 4. Routing Logic (FIXED) ---
def route_after_chat(state: AgentState) -> Literal["tools", "human_review", END]:
    last_message = state["messages"][-1]

    # --- FIX IS HERE ---
    # Check the Limit FIRST.
    # If we have done 3 or more loops, we force a review/stop,
    # even if the LLM wants to search again.
    if state.get("loop_step", 0) >= 3:
        return "human_review"

    # Then check for tool calls
    if last_message.tool_calls:
        return "tools"

    if "READY_TO_REPORT" in last_message.content:
        return "human_review"

    if state["notes"]:
        return "human_review"

    return END


def route_after_review(state: AgentState) -> Literal["synthesize", "chatbot"]:
    last_message = state["messages"][-1]
    if isinstance(last_message, HumanMessage):
        return "chatbot"
    return "synthesize"


# --- 5. Build Graph ---
workflow = StateGraph(AgentState)

workflow.add_node("chatbot", chatbot)
workflow.add_node("tools", ToolNode(tools))
workflow.add_node("summarize", summarize_search, retry=RetryPolicy(max_attempts=3))
workflow.add_node("human_review", human_review_node)
workflow.add_node("synthesize", synthesize_report)

workflow.add_edge(START, "chatbot")

workflow.add_conditional_edges(
    "chatbot",
    route_after_chat,
    {"tools": "tools", "human_review": "human_review", END: END},
)

workflow.add_edge("tools", "summarize")
workflow.add_edge("summarize", "chatbot")

workflow.add_conditional_edges(
    "human_review",
    route_after_review,
    {"synthesize": "synthesize", "chatbot": "chatbot"},
)

workflow.add_edge("synthesize", END)

memory = MemorySaver()
app = workflow.compile(checkpointer=memory, interrupt_before=["human_review"])


# --- 6. Run Interactive Session (UPDATED PRINTING) ---
def run_interactive_session():
    thread_id = "research-session-fixed"
    config = {"configurable": {"thread_id": thread_id}}

    initial_state = {
        "topic": "Comparison of Rust vs C++ for Embedded Systems in 2025",
        "messages": [HumanMessage(content="Please research this topic.")],
        "notes": [],
        "sources": [],
        "loop_step": 0,
    }

    print(f"🚀 Starting research on: {initial_state['topic']}")

    for event in app.stream(initial_state, config=config):
        for key, value in event.items():
            print(f"-> Executed: {key}")

            # Print what the chatbot decided to do
            if key == "chatbot" and "messages" in value:
                msg = value["messages"][0]
                if msg.tool_calls:
                    # --- FIX: PRINT QUERIES ---
                    for tc in msg.tool_calls:
                        query = tc["args"].get("query", "No query found")
                        print(f"   🔎 SEARCH QUERY: {query}")
                else:
                    print(f"   ✅ Chatbot is ready: {msg.content}")

    snapshot = app.get_state(config)

    if snapshot.next and snapshot.next[0] == "human_review":
        print("\n" + "=" * 40)
        print("⏸️  PAUSED FOR HUMAN REVIEW")
        print("=" * 40)
        print(f"Collected {len(snapshot.values['notes'])} research notes.")

        user_input = input("\nType 'ok' to approve report, or type feedback: ")

        if user_input.lower() in ["ok", "yes", "y", "go"]:
            print("\n📝 Approved! Generating report...")
            final_stream = app.stream(None, config=config)
        else:
            print(f"\n🔄 Feedback: '{user_input}'")
            print("Returning to Chatbot...")
            app.update_state(config, {"messages": [HumanMessage(content=user_input)]})
            final_stream = app.stream(None, config=config)

        for event in final_stream:
            for key, value in event.items():
                print(f"-> Executed: {key}")

        final_state = app.get_state(config)
        if "messages" in final_state.values:
            last_msg = final_state.values["messages"][-1]
            print("\n✅ FINAL REPORT:\n")
            print(last_msg.content)

            with open("final_report.md", "w", encoding="utf-8") as f:
                f.write(last_msg.content)
                print("\n(Saved to final_report.md)")


if __name__ == "__main__":
    run_interactive_session()
