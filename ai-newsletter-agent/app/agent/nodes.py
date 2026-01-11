import time
import re
import datetime
from dateutil import parser as date_parser
from langchain_core.messages import SystemMessage, HumanMessage

from app.state import AgentState
from app.config import CONFIG, TARGET_COMPANIES, BLACKLIST_DOMAINS
from app.services.search import tavily_news
from app.services.scraper import scrape_url
from app.services.llm import newsletter_generator, article_summarizer
from app.agent.prompts import ANALYSIS_SYSTEM_PROMPT, get_editor_prompt


def monitor_news(state: AgentState):
    """
    Node 1: News Analyst.
    Searches for latest news about the specific companies.
    """
    print(f"\n [Step 1] Monitoring {len(TARGET_COMPANIES)} Companies")
    results = []
    new_urls = []
    existing_urls = set(state.get("seen_urls", []))  # do not search existing urls again
    cutoff_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        days=CONFIG["days_back"]
    )
    cutoff_date_str = cutoff_date.strftime("%Y-%m-%d")  # cutoff for tavily
    cutoff_date = cutoff_date - datetime.timedelta(
        days=1
    )  # manual cutoff with one day puffer to account for timezone differences

    for target in TARGET_COMPANIES:
        company = target["name"]
        keywords = target["keywords"]
        query = (
            f'"{company}" AI model release funding partnership announcement benchmark'
        )
        print(f"   -> Checking: {company}...")

        try:
            response = tavily_news.invoke(
                {"query": query, "start_date": cutoff_date_str}
            )
            hits = (
                response.get("results", []) if isinstance(response, dict) else response
            )

            if isinstance(hits, list):
                for item in hits:
                    url = item.get("url", "")
                    pub_date_str = item.get("published_date", None)

                    # Deduplication & Blacklist Check
                    if url in existing_urls:
                        print(f"{url} already visited!")
                    elif any(bad in url for bad in BLACKLIST_DOMAINS):
                        print(f"{url} in blacklist!")
                        continue

                    # Manual Date Filtering
                    if pub_date_str:
                        try:
                            pub_date = date_parser.parse(pub_date_str)
                            if pub_date.tzinfo is None:
                                pub_date = pub_date.replace(
                                    tzinfo=datetime.timezone.utc
                                )
                            if pub_date < cutoff_date:
                                print(f"{url} is too old!")
                                continue
                        except Exception as e:
                            print(f"Error: {e}")
                            pass

                    # Keyword Validation, so we filter out any articles that only mention the company in a sub clause
                    content = item.get("content", "")
                    title = item.get("title", "")
                    full_text = (title + " " + content).lower()

                    if any(k.lower() in full_text for k in keywords):
                        date_str = (
                            pub_date.strftime("%Y-%m-%d")
                            if pub_date_str
                            else "Unknown Date"
                        )
                        results.append(
                            f"[{company}] DATE: {date_str} | URL: {url} | TITLE: {title}"
                        )
                        new_urls.append(url)
                        existing_urls.add(url)

            else:
                print(f"Whopsie hits: {hits}")

            time.sleep(CONFIG["rate_limit_delay"])

        except Exception as e:
            print(f"      x Error checking {company}: {e}")

    if not results:
        results = ["No significant news found for any target company."]

    return {"search_results": results, "seen_urls": new_urls, "steps": 1}


def scraper_node(state: AgentState):
    """
    Node 2: The Stealth Hybrid Reader.
    """
    print(f"\n--- [Step 2] Scraping Full Articles ---")
    url_to_date = {}
    for res in state.get("search_results", []):
        # Extract URL and Date from string format
        # Expected format: "[Company] DATE: 2026-01-11 | URL: https://... | TITLE: ..."
        try:
            parts = res.split("|")
            print(f"   Debug Scraper Parsing: {parts}")
            date_part = parts[0].split("DATE:")[1].strip()
            url_part = parts[1].split("URL:")[1].strip()
            url_to_date[url_part] = date_part
        except:
            continue
    urls_to_scrape = state.get("seen_urls", [])

    # Safety limit
    if len(urls_to_scrape) > 20:
        print(f"   (Limiting scrape to first 20 of {len(urls_to_scrape)} URLs)")
        urls_to_scrape = urls_to_scrape[:20]

    scraped_content = []
    for url in urls_to_scrape:
        content = scrape_url(url)
        if content:
            # Re-attach the date to the scraped content
            date_str = url_to_date.get(url, "Unknown Date")

            # Prepend a clear header for the Summarizer
            full_text = (
                f"METADATA_DATE: {date_str}\n"  # <--- The LLM needs this anchor!
                f"METADATA_URL: {url}\n"
                f"FULL ARTICLE CONTENT:\n{content}"
            )
            scraped_content.append(full_text)
            print(f"      Scraped {date_str}: {len(content)} chars")
        else:
            print(f"      Failed: {url}")

    return {"scraped_articles": scraped_content}


def summarize_node(state: dict):
    """
    Summarizes a single article.
    """
    content = state.get("content", "")

    # Parse Metadata (URL & Date)
    # We look for the headers we prepared in the scraper_node
    url_match = re.search(r"METADATA_URL: (.*?)\n", content)
    date_match = re.search(r"METADATA_DATE: (.*?)\n", content)

    original_url = url_match.group(1).strip() if url_match else "Source Unknown"
    article_date = date_match.group(1).strip() if date_match else "Unknown Date"

    print(f"   [Summarizer] Processing: {original_url} (Date: {article_date})")

    # Prepare System Prompt
    system_msg = SystemMessage(content=ANALYSIS_SYSTEM_PROMPT)

    try:
        # Invoke LLM
        # Pass the full content (headers included) so the LLM sees the Date Anchor.
        summary_obj = article_summarizer.invoke(
            [system_msg, HumanMessage(content=f"Analyze this text:\n{content}")]
        )

        # Relevance Filter
        if summary_obj.relevance_score < 4:
            print(f"      x Low Score ({summary_obj.relevance_score}): {original_url}")
            return {"summaries": []}

        # Format Output
        # Attach the URL here so the Editor sees it clearly
        formatted = (
            f"SOURCE: {summary_obj.title}\n"
            f"PRIMARY: {summary_obj.primary_company}\n"
            f"URL: {original_url}\n"
            f"FACTS:\n" + "\n".join([f"- {pt}" for pt in summary_obj.key_points]) + "\n"
        )
        return {"summaries": [formatted]}

    except Exception as e:
        print(f"Summary failed for {original_url}: {e}")
        return {"summaries": []}


def editor_writer(state: AgentState):
    """
    Node 3: Editor-in-Chief.
    Synthesizes the final newsletter report."""
    print("\n [Step 3] Synthesizing Final Report")
    today = datetime.datetime.now().strftime("%B %d, %Y")

    # Get List of Target Names for strict matching
    target_names = [t["name"] for t in TARGET_COMPANIES]

    # Group Summaries
    grouped_content = {name: [] for name in target_names}
    unknown_bucket = []

    print("\n   [DEBUG] Grouping Articles:")

    for summary_str in state.get("summaries", []):
        # Extract Primary Company Tag
        primary_match = re.search(r"PRIMARY: (.*?)\n", summary_str)
        primary_entity = primary_match.group(1).strip() if primary_match else "Unknown"

        print(
            f"   - Entity: '{primary_entity}' | Title: {summary_str.split('\n')[0][8:40]}..."
        )

        # Assign to Bucket
        found_bucket = False
        for name in target_names:
            # Match if the Primary Entity string *contains* the target name
            # e.g. "Microsoft AI" contains "Microsoft"
            if name.lower() in primary_entity.lower():
                grouped_content[name].append(summary_str)
                found_bucket = True
                break
            else:
                print(f'     x "{primary_entity}" does not match "{name}"')

        if not found_bucket:
            unknown_bucket.append(summary_str)

    # Construct String Input
    structured_news_input = ""
    for company, items in grouped_content.items():
        if items:
            structured_news_input += f"\n### NEWS FOR {company.upper()} ###\n"
            structured_news_input += "\n".join(items) + "\n"

    if unknown_bucket:
        structured_news_input += "\n### OTHER INDUSTRY NEWS ###\n"
        structured_news_input += "\n".join(unknown_bucket)

    # Generate Prompt using the helper from prompts.py
    system_prompt_str = get_editor_prompt(today, target_names)

    user_message = f"GROUPED NEWS:\n{structured_news_input}\n"

    # Invoke Editor
    newsletter = newsletter_generator.invoke(
        [SystemMessage(content=system_prompt_str), HumanMessage(content=user_message)]
    )

    # Formatting to Markdown
    final_md = f"# THE DAILY AI | Market Report\n**{today}**\n\n---\n\n## EXECUTIVE SUMMARY\n\n"
    for item in newsletter.executive_summary:
        final_md += f"- {item}\n"

    final_md += "\n---\n\n## DETAILED COMPANY REPORTS\n\n"
    for report in newsletter.company_reports:
        # Filter out empty or "no news" sections
        if (
            len(report.update) > 50
            and "no significant news" not in report.update.lower()
        ):
            final_md += f"### {report.name}\n\n{report.update}\n\n"

    final_md += "\n\n---\n**Report compiled by The Daily AI Editorial Team**"

    return {"final_report": final_md}
