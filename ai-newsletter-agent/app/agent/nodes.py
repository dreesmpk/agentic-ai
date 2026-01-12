import asyncio
import datetime
import random
import re
import time

from app.agent.prompts import get_analysis_prompt, get_editor_prompt
from app.config import BLACKLIST_DOMAINS, CONFIG, TARGET_COMPANIES
from app.services.llm import article_summarizer, newsletter_generator
from app.services.scraper import scrape_url
from app.services.search import tavily_news
from app.state import AgentState
from dateutil import parser as date_parser
from langchain_core.messages import HumanMessage, SystemMessage


def monitor_news(state: AgentState):
    """
    Node 1: News Analyst.
    Searches for latest news on the target companies.
    Selects strictly the top 2 articles per company at most.
    """
    print(f"\n [Step 1] Monitoring {len(TARGET_COMPANIES)} Companies")

    # 1. Setup & Date Constraints
    existing_urls = set(state.get("seen_urls", []))
    cutoff_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        days=CONFIG["days_back"]
    )
    cutoff_date_str = cutoff_date.strftime("%Y-%m-%d")
    cutoff_date = cutoff_date - datetime.timedelta(days=1)

    # 2. Collect ALL candidates first (Bucketed by Company)
    company_buckets = {t["name"]: [] for t in TARGET_COMPANIES}
    new_urls = []

    for target in TARGET_COMPANIES:
        company = target["name"]
        keywords = target["keywords"]
        print(f"   -> Checking: {company}...")
        query = f'Latest important news, updates, and AI developments involving "{company}".'
        try:
            response = tavily_news.invoke({"query": query, "start_date": cutoff_date_str})
            hits = response.get("results", []) if isinstance(response, dict) else response

            if isinstance(hits, list):
                for item in hits:
                    url = item.get("url", "")
                    pub_date_str = item.get("published_date", None)
                    tavily_score = item.get("score", 0.0)

                    # Quality Gate
                    if tavily_score < CONFIG["min_search_score"]:
                        print(f"      x Low Score ({tavily_score:.2f}) Skipping: {url}")
                        continue

                    # Deduplication and blacklist check
                    if url in existing_urls or any(bad in url for bad in BLACKLIST_DOMAINS):
                        continue

                    # Date Check
                    pub_date = None
                    if pub_date_str:
                        try:
                            pub_date = date_parser.parse(pub_date_str)
                            if pub_date.tzinfo is None:
                                pub_date = pub_date.replace(tzinfo=datetime.timezone.utc)
                            if pub_date < cutoff_date:
                                continue
                        except Exception:
                            pass

                    # keyword check
                    content = item.get("content", "")
                    title = item.get("title", "")
                    full_text = (title + " " + content).lower()
                    if not any(k.lower() in full_text for k in keywords):
                        continue

                    # Add to Bucket
                    date_display = pub_date.strftime("%Y-%m-%d") if pub_date else "Unknown Date"

                    hit_data = {
                        "score": tavily_score,
                        "date": pub_date
                        or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc),
                        "company": company,
                        "url": url,
                        "string": f"[{company}] DATE: {date_display} | URL: {url} | TITLE: {title}",
                    }

                    if not any(h["url"] == url for h in company_buckets[company]):
                        company_buckets[company].append(hit_data)
                        existing_urls.add(url)
                        new_urls.append(url)
            else:
                print(f"      x Unexpected response format for {company}: {response}")
        except Exception as e:
            print(f"      x Error checking {company}: {e}")

        # Sort by Score then Date
        company_buckets[company].sort(key=lambda x: (x["score"], x["date"]), reverse=True)
        time.sleep(CONFIG["rate_limit_delay"])

    # 3. Select Top 2 articles per company
    final_results = []
    # Iterate through every target company (ensures we check every bucket)
    for company_name in company_buckets:
        bucket = company_buckets[company_name]

        # Take the top 2 (or less).
        top_picks = bucket[:2]
        for hit in top_picks:
            final_results.append(hit["string"])

    if not final_results:
        final_results = ["No significant news found for any target company."]

    print(f"\n   -> Selected {len(final_results)} articles (Top 2 per company).")
    return {"search_results": final_results, "seen_urls": new_urls, "steps": 1}


async def scraper_node(state: AgentState):
    """
    Node 2: The Stealth Hybrid Reader (Async + Concurrent).
    Fetches the content for the selected articles from Step 1 concurrently.
    """
    print(f"\n--- [Step 2] Scraping Full Articles (Concurrent) ---")

    # 1. Parse the search_results List
    search_results = state.get("search_results", [])
    urls_to_scrape = []
    url_to_date = {}

    for res in search_results:
        try:
            if " | URL: " in res:
                meta_part, rest = res.split(" | URL: ", 1)
                date_str = meta_part.split("DATE: ")[1].strip()

                if " | TITLE: " in rest:
                    url = rest.split(" | TITLE: ")[0].strip()
                else:
                    url = rest.strip()

                urls_to_scrape.append(url)
                url_to_date[url] = date_str
        except Exception as e:
            print(f"   x Parsing Error on result: {str(e)}")
            continue

    # 2. Safety Limit
    if len(urls_to_scrape) > 36:
        print(f"   (Limiting scrape to first 36 of {len(urls_to_scrape)} balanced URLs)")
        urls_to_scrape = urls_to_scrape[:36]

    # 3. Concurrency Control (The Semaphore)
    semaphore = asyncio.Semaphore(CONFIG.get("max_concurrency", 3))

    async def scrape_one(url):
        async with semaphore:
            # Add a small random delay to stagger browser launches (Stealth)
            await asyncio.sleep(random.uniform(0.5, 2.0))

            try:
                # Call the async scrape_url function directly
                content = await scrape_url(url)

                if content:
                    # Re-attach the date
                    date_str = url_to_date.get(url, "Unknown Date")

                    full_text = f"METADATA_DATE: {date_str}\n" f"METADATA_URL: {url}\n" f"{content}"
                    # Use string slicing to keep logs clean
                    print(f"      > Scraped: {url[:40]}... ({len(content)} chars)")
                    return full_text
                else:
                    print(f"      x Failed to scrape: {url[:40]}...")
                    return None

            except Exception as e:
                print(f"      x Error processing {url[:40]}... : {e}")
                return None

    # 4. Launch Tasks concurrently
    tasks = [scrape_one(url) for url in urls_to_scrape]
    results = await asyncio.gather(*tasks)

    # 5. Filter out failures (None)
    valid_articles = [r for r in results if r is not None]

    print(f"   -> Successfully scraped {len(valid_articles)} articles.")
    return {"scraped_articles": valid_articles, "steps": 1}


async def summarize_node(state: AgentState):
    """
    Node 3: The Summarizer (Throttled).
    Uses 'article_summarizer' (Pydantic) to extract structured data,
    then converts it to a string for the Editor.
    """
    scraped_content = state.get("scraped_articles", [])
    print(f"\n--- [Step 3] Summarizing {len(scraped_content)} Articles ---")

    # 1. Define the Semaphore (The Bouncer)
    # This limits concurrent API calls to prevent 429 errors.
    semaphore = asyncio.Semaphore(CONFIG.get("max_concurrency", 3))
    target_names = [t["name"] for t in TARGET_COMPANIES]

    async def summarize_one(text, index):
        """
        Summarizes a single article.

        :param text: Article text to summarize
        :param index: Index for logging
        :return: Formatted summary string or None on failure
        """
        async with semaphore:
            try:
                date_match = re.search(r"METADATA_DATE: (.*?)\n", text)
                url_match = re.search(r"METADATA_URL: (.*?)\n", text)

                meta_date = date_match.group(1).strip() if date_match else "Unknown Date"
                meta_url = url_match.group(1).strip() if url_match else "Unknown URL"
                # Stagger requests slightly to avoid a "thundering herd"
                await asyncio.sleep(0.5 + (index * 0.1))
                system_instruction = get_analysis_prompt(target_names)
                # 2. Invoke the LLM (Returns ArticleSummary Object)
                result = await article_summarizer.ainvoke(
                    [
                        SystemMessage(content=system_instruction),
                        HumanMessage(content=f"Article Content:\n{text}"),
                    ]
                )

                # 3. Handle the Pydantic Object
                # Join bullet points into a string
                points_str = "\n- ".join(result.key_points)

                formatted_summary = (
                    f"Title: {result.title}\n"
                    f"Entity: {result.primary_company}\n"
                    f"Relevance: {result.relevance_score}\n"
                    f"Key Points:\n- {points_str}\n"
                    f"Date: {meta_date}\n"
                    f"Source: {meta_url}"
                )

                return formatted_summary

            except Exception as e:
                # Log specific error but don't crash the whole batch
                print(f"      x Error summarizing article {index}: {e}")
                return None

    # 4. Create and Run Tasks
    tasks = [summarize_one(text, i) for i, text in enumerate(scraped_content)]
    summaries = await asyncio.gather(*tasks)

    # 5. Filter out failures (None)
    valid_summaries = [s for s in summaries if s]

    print(f"   -> Generated {len(valid_summaries)} valid summaries.")
    return {"summaries": valid_summaries, "steps": 1}


def editor_writer(state: AgentState):
    """
    Node 4: Editor-in-Chief.
    Synthesizes the final newsletter report."""
    print("\n [Step 4] Synthesizing Final Report")
    today = datetime.datetime.now().strftime("%B %d, %Y")

    # Get List of Target Names for strict matching
    target_names = [t["name"] for t in TARGET_COMPANIES]

    # Group Summaries
    grouped_content = {name: [] for name in target_names}
    unknown_bucket = []

    print("\n   [DEBUG] Grouping Articles:")

    for summary_str in state.get("summaries", []):
        # Extract Primary Company Tag
        primary_match = re.search(r"Entity: (.*?)\n", summary_str)
        primary_entity = primary_match.group(1).strip() if primary_match else "Unknown"

        print(f"   - Entity: '{primary_entity}' | Title: {summary_str.split('\n')[0][7:]}...")

        # Assign to Bucket
        found_bucket = False
        for name in target_names:
            # Match if the Primary Entity string *contains* the target name
            # e.g. "Microsoft AI" contains "Microsoft"
            if name.lower() in primary_entity.lower():
                grouped_content[name].append(summary_str)
                found_bucket = True
                break

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
        if len(report.update) > 50 and "no significant news" not in report.update.lower():
            final_md += f"### {report.name}\n\n{report.update}\n\n"

    final_md += "\n\n---\n**Report compiled by The Daily AI Editorial Team**"

    return {"final_report": final_md, "steps": 1}
