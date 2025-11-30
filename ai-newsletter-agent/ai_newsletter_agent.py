import operator
import datetime
import os
import time
from typing import Annotated, List, TypedDict
from langchain_anthropic import ChatAnthropic
from langchain_tavily import TavilySearch
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, START, END
from langgraph.types import RetryPolicy

# --- Configuration ---
TARGET_COMPANIES = [
    "OpenAI",
    "Google DeepMind",
    "Microsoft AI",
    "Anthropic",
    "NVIDIA",
    "Meta AI",
    "xAI (Grok)",
    "Apple AI",
    "Hugging Face",
]

# Model Configurations
MODEL_FAST = "claude-haiku-4-5-20251001"
MODEL_SMART = "claude-haiku-4-5-20251001"  # Using Haiku while Sonnet is unstable


# --- 1. State Definition ---
class AgentState(TypedDict):
    raw_news: Annotated[List[str], operator.add]
    opinions: Annotated[List[str], operator.add]
    final_report: str
    steps: Annotated[int, operator.add]


# --- 2. Model & Tool Initialization ---
retry_policy = RetryPolicy(
    max_attempts=5,
    initial_interval=2,
    backoff_factor=2,
    max_interval=30,
    retry_on=(Exception,),
)

llm_fast = ChatAnthropic(model=MODEL_FAST, temperature=0, max_retries=3)
llm_smart = ChatAnthropic(model=MODEL_SMART, temperature=0, max_retries=3)

tavily_tool = TavilySearch(
    max_results=5,
    topic="news",
    days=3,
    include_answer="advanced",
)


# --- 3. Node Definitions ---
def monitor_news(state: AgentState):
    """
    Node 1: Entity Monitor.
    Searches for latest news about the specific company names.
    """
    print(f"\n--- [Step 1] Monitoring {len(TARGET_COMPANIES)} Companies ---")
    results = []

    for company in TARGET_COMPANIES:
        # Search Query: Force exact match on name, look for news keywords
        query = f'"{company}" AI latest news announcement launch'
        print(f"   -> Checking: {company}...")

        try:
            response = tavily_tool.invoke({"query": query})

            valid_hits = []

            # 1. Check Summary
            if isinstance(response, dict) and response.get("answer"):
                summary = response.get("answer")
                if company.split(" ")[0].lower() in summary.lower():
                    valid_hits.append(f"[{company}] SUMMARY: {summary}")

            # 2. Check Results
            hits = (
                response.get("results", []) if isinstance(response, dict) else response
            )
            if isinstance(hits, list):
                for item in hits:
                    content = item.get("content", "")
                    title = item.get("title", "")
                    url = item.get("url", "")
                    full_text = (title + " " + content).lower()

                    # Verify relevance (Company name must appear in text)
                    # We check the first word (e.g. "OpenAI", "Meta", "Apple") to be safe
                    check_name = company.split(" ")[0].lower()

                    if check_name in full_text:
                        valid_hits.append(
                            f"[{company}] DETAIL: {content[:300]}... (Source: {url})"
                        )

            if valid_hits:
                results.extend(valid_hits)
            else:
                print(f"      (No validated hits for {company})")

            time.sleep(1.5)  # Slightly longer delay to be safe

        except Exception as e:
            print(f"      x Error checking {company}: {e}")

    if not results:
        results = ["No significant news found for any target company."]

    return {"raw_news": results, "steps": 1}


def opinion_researcher(state: AgentState):
    """
    Node 2: Opinion Researcher.
    """
    print("\n--- [Step 2] Researching Community Opinions ---")

    news_context = "\n".join(state["raw_news"])

    prompt = f"""
    Here are the latest headlines found:
    {news_context}
    
    Identify the single most controversial or impactful story. 
    Generate a search query to find external opinions (reviews, reddit, hacker news) on it.
    
    CRITICAL OUTPUT RULES:
    - Return ONLY the search query string.
    - Do NOT output reasoning.
    - If nothing is interesting, return exactly "SKIP".
    """

    decision = llm_fast.invoke(prompt)
    content = decision.content.strip()

    if "SKIP" in content:
        return {"opinions": ["No major controversy found."], "steps": 1}

    search_query = content.replace('"', "").replace("'", "")
    print(f"   -> Deep diving into: '{search_query}'")

    general_search = TavilySearch(
        max_results=5, topic="general", include_answer="advanced"
    )

    try:
        response = general_search.invoke(
            {"query": search_query + " reddit hacker news discussion"}
        )
        opinion_notes = []

        if isinstance(response, dict) and response.get("answer"):
            opinion_notes.append(f"OPINION SUMMARY: {response.get('answer')}")

        hits = response.get("results", []) if isinstance(response, dict) else response
        for hit in hits:
            opinion_notes.append(
                f"OPINION SOURCE: {hit.get('content', '')[:200]}... ({hit.get('url')})"
            )

        return {"opinions": opinion_notes, "steps": 1}

    except Exception as e:
        print(f"   x Error in opinion search: {e}")
        return {"opinions": [], "steps": 1}


def editor_writer(state: AgentState):
    """
    Node 3: Editor-in-Chief.
    """
    print("\n--- [Step 3] Synthesizing Final Report ---")

    today = datetime.datetime.now().strftime("%B %d, %Y")

    system_prompt = (
        "You are the Editor-in-Chief of 'The Daily AI'.\n"
        "Your goal: Write a comprehensive, high-signal market report.\n\n"
        "**STRUCTURE REQUIREMENTS**:\n\n"
        "1. **EXECUTIVE SUMMARY**:\n"
        "   - Create a bulleted list.\n"
        "   - Exactly ONE bullet point per company monitored.\n"
        "   - Summarize the most important update. If NO news, write 'No major updates.'\n\n"
        "2. **DETAILED COMPANY REPORTS**:\n"
        "   - Create a subsection for each company (e.g., '### OpenAI').\n"
        "   - Write a detailed paragraph analyzing their latest news.\n\n"
        "   **CITATION RULE (CRITICAL)**:\n"
        "   - You MUST cite your sources **immediately** after the sentence that uses the information.\n"
        "   - Format: `Sentence goes here [Source Name](url). Next sentence.`\n"
        "   - Do NOT group citations at the end of the paragraph.\n"
        "   - Every specific claim (dates, numbers, quotes) needs a citation.\n\n"
        "3. **COMMUNITY PULSE**:\n"
        "   - Summarize external opinions.\n\n"
        "**QUALITY CONTROL RULES**:\n"
        "- **STRICT RELEVANCE**: Only report news specifically about the target companies.\n"
        "- Do not hallucinate news if the input says 'No validated hits'.\n"
    )

    user_message = f"DATE: {today}\n\nRAW NEWS SCANS:\n{'\n'.join(state['raw_news'])}\n\nEXTERNAL OPINIONS:\n{'\n'.join(state['opinions'])}"

    response = llm_smart.invoke(
        [SystemMessage(content=system_prompt), HumanMessage(content=user_message)]
    )

    return {"final_report": response.content}


# --- 4. Graph Construction ---
workflow = StateGraph(AgentState)

workflow.add_node("monitor", monitor_news, retry=retry_policy)
workflow.add_node("researcher", opinion_researcher, retry=retry_policy)
workflow.add_node("editor", editor_writer, retry=retry_policy)

workflow.add_edge(START, "monitor")
workflow.add_edge("monitor", "researcher")
workflow.add_edge("researcher", "editor")
workflow.add_edge("editor", END)

app = workflow.compile()

# --- 5. Execution ---
if __name__ == "__main__":
    if not os.environ.get("ANTHROPIC_API_KEY") or not os.environ.get("TAVILY_API_KEY"):
        print("Error: Keys missing.")
        exit(1)

    print(
        f"🚀 Starting AI Newsletter Agent ({datetime.datetime.now().strftime('%Y-%m-%d')})"
    )

    final_state = app.invoke({"raw_news": [], "opinions": [], "steps": 0})

    print(
        "\n" + "=" * 40 + "\n           FINAL NEWSLETTER           \n" + "=" * 40 + "\n"
    )
    print(final_state["final_report"])

    filename = f"AI_Newsletter_{datetime.datetime.now().strftime('%Y-%m-%d')}.md"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(final_state["final_report"])
    print(f"\n✅ Report saved to: {filename}")
