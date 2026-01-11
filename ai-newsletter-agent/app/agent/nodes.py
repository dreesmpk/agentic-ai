import time
import datetime
from dateutil import parser as date_parser
from langchain_core.messages import SystemMessage, HumanMessage

from app.state import AgentState
from app.config import CONFIG, TARGET_COMPANIES, BLACKLIST_DOMAINS
from app.services.search import tavily_news, tavily_general
from app.services.scraper import scrape_url
from app.services.llm import research_decider, newsletter_generator, article_summarizer
from app.schemas import Newsletter, ResearchDecision


def monitor_news(state: AgentState):
    """
    Node 1: Entity Monitor.
    Searches for latest news about the specific companies.
    """
    print(f"\n--- [Step 1] Monitoring {len(TARGET_COMPANIES)} Companies ---")
    results = []
    new_urls = []
    existing_urls = set(state.get("seen_urls", []))
    cutoff_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        days=CONFIG["days_back"]
    )

    for target in TARGET_COMPANIES:
        company = target["name"]
        keywords = target["keywords"]
        query = f'"{company}" AI latest news announcement launch'
        print(f"   -> Checking: {company}...")

        try:
            response = tavily_news.invoke({"query": query})
            hits = (
                response.get("results", []) if isinstance(response, dict) else response
            )

            if isinstance(hits, list):
                for item in hits:
                    url = item.get("url", "")
                    pub_date_str = item.get("published_date", None)

                    # Deduplication & Spam Check
                    if url in existing_urls or any(
                        bad in url for bad in BLACKLIST_DOMAINS
                    ):
                        continue

                    # Strict Date Filtering
                    if pub_date_str:
                        try:
                            pub_date = date_parser.parse(pub_date_str)
                            if pub_date.tzinfo is None:
                                pub_date = pub_date.replace(
                                    tzinfo=datetime.timezone.utc
                                )
                            if pub_date < cutoff_date:
                                continue
                        except Exception:
                            pass

                    # Keyword Validation
                    content = item.get("content", "")
                    title = item.get("title", "")
                    full_text = (title + " " + content).lower()

                    if any(k.lower() in full_text for k in keywords):
                        results.append(f"[{company}] DETAIL: {content} (Source: {url})")
                        new_urls.append(url)
                        existing_urls.add(url)

            time.sleep(CONFIG["rate_limit_delay"])

        except Exception as e:
            print(f"      x Error checking {company}: {e}")

    if not results:
        results = ["No significant news found for any target company."]

    return {"raw_news": results, "seen_urls": new_urls, "steps": 1}


def scraper_node(state: AgentState):
    """
    Node 1.5: The Stealth Hybrid Reader.
    """
    print(f"\n--- [Step 1.5] Scraping Full Articles ---")
    urls_to_scrape = state.get("seen_urls", [])

    # Safety limit
    if len(urls_to_scrape) > 20:
        print(f"   (Limiting scrape to first 20 of {len(urls_to_scrape)} URLs)")
        urls_to_scrape = urls_to_scrape[:20]

    scraped_content = []
    for url in urls_to_scrape:
        content = scrape_url(url)
        if content:
            scraped_content.append(content)
            print(f"      ✅ Success: {len(content)} chars")
        else:
            print(f"      x Failed/Blocked: {url}")

    if not scraped_content:
        return {}

    return {"raw_news": scraped_content}


def summarize_node(state: dict):
    """
    Takes a SINGLE article content (from the Send API),
    summarizes it, and returns it to the global state.
    """
    content = state.get("content", "")

    # 1. Summarize
    try:
        summary_obj = article_summarizer.invoke(
            f"Analyze this text and extract key facts. If it's not relevant to AI, give a low score.\n\nTEXT: {content}"
        )

        # 2. Filter Low Quality
        if summary_obj.relevance_score < 4:
            return {"summaries": []}  # Skip irrelevant articles

        # 3. Format for the Editor
        formatted = (
            f"SOURCE: {summary_obj.title}\n"
            f"FACTS:\n" + "\n".join([f"- {pt}" for pt in summary_obj.key_points]) + "\n"
        )
        return {"summaries": [formatted]}

    except Exception as e:
        print(f"Summary failed: {e}")
        return {"summaries": []}


def opinion_researcher(state: AgentState):
    """
    Node 2: Opinion Researcher.

    Analyzes the distilled news summaries to identify stories that are controversial,
    highly technical, or significant enough to warrant checking community discussions
    (Reddit, Hacker News). If a topic is found, it performs a targeted search.
    """
    print("\n--- [Step 2] Researching Community Opinions ---")

    # Prioritize using the clean summaries; fallback to raw news if the map step produced no output
    context = "\n".join(state.get("summaries", [])) or "\n".join(state["raw_news"])

    prompt = f"""
    Analyze these news summaries:
    {context}
    
    Is there a specific story that is controversial, highly technical, 
    or major industry news that warrants checking Reddit/Hacker News?
    """

    decision = research_decider.invoke(prompt)

    if not decision.should_research:
        return {"opinions": ["No major controversy found."], "steps": 1}

    print(f"   -> Deep diving into: '{decision.search_query}'")

    try:
        response = tavily_general.invoke(
            {"query": decision.search_query + " reddit hacker news discussion"}
        )
        opinion_notes = []
        hits = response.get("results", []) if isinstance(response, dict) else response
        for hit in hits:
            opinion_notes.append(
                f"OPINION: {hit.get('content','')[:200]} ({hit.get('url')})"
            )
        return {"opinions": opinion_notes, "steps": 1}
    except Exception:
        return {"opinions": [], "steps": 1}


def editor_writer(state: AgentState):
    """
    Node 3: Editor-in-Chief.

    Synthesizes the final newsletter report.
    CRITICAL: This node restores the rich formatting instructions to ensure
    the output is not just a list of facts, but a readable narrative.
    """
    print("\n--- [Step 3] Synthesizing Final Report ---")
    today = datetime.datetime.now().strftime("%B %d, %Y")
    allowed_companies = ", ".join([t["name"] for t in TARGET_COMPANIES])

    system_prompt = (
        f"You are the Editor-in-Chief of 'The Daily AI'. Today is {today}.\n"
        "Your goal: Write a comprehensive, high-signal market report.\n\n"
        "**SCOPE ENFORCEMENT**:\n"
        f"- You are ONLY allowed to report on these companies: **{allowed_companies}**.\n"
        "- If the provided summaries mention other companies, IGNORE them.\n\n"
        "**TONE & STYLE**:\n"
        "- Professional, concise, and dense with information.\n"
        "- No fluff. No 'In the world of AI...'. Start directly with the news.\n\n"
        "**STRUCTURE REQUIREMENTS**:\n"
        "1. **EXECUTIVE SUMMARY**:\n"
        "   - Create a bulleted list.\n"
        "   - Exactly ONE bullet point per company that has significant news.\n"
        "2. **DETAILED COMPANY REPORTS**:\n"
        "   - Create a subsection for each company.\n"
        "   - Write a detailed paragraph analyzing their latest news.\n"
        "   - Use specific stats, prices, and names from the summaries.\n"
        "   **CITATION RULE (CRITICAL)**:\n"
        "   - You MUST cite your sources immediately after the claim.\n"
        "   - Format: `Sentence goes here ([Source Name](url)).`\n"
        "3. **COMMUNITY PULSE**:\n"
        "   - Summarize the external opinions section.\n"
    )

    # We combine the "Map" outputs (Summaries) and "Researcher" outputs (Opinions)
    user_message = (
        f"SUMMARIZED NEWS:\n{'\n'.join(state['summaries'])}\n\n"
        f"COMMUNITY OPINIONS:\n{'\n'.join(state['opinions'])}"
    )

    newsletter: Newsletter = newsletter_generator.invoke(
        [SystemMessage(content=system_prompt), HumanMessage(content=user_message)]
    )

    # Format output as Markdown
    final_md = f"# THE DAILY AI | Market Report\n**{today}**\n\n---\n\n## EXECUTIVE SUMMARY\n\n"
    for item in newsletter.executive_summary:
        final_md += f"- {item}\n"

    final_md += "\n---\n\n## DETAILED COMPANY REPORTS\n\n"
    for report in newsletter.company_reports:
        if "no significant news" in report.update.lower() or len(report.update) < 50:
            continue
        final_md += f"### {report.name}\n\n{report.update}\n\n"

    final_md += "\n---\n\n## COMMUNITY PULSE\n\n"
    final_md += newsletter.community_pulse
    final_md += "\n\n---\n**Report compiled by The Daily AI Editorial Team**"

    return {"final_report": final_md}
