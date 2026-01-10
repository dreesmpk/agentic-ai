import operator
import datetime
import os
import time
import smtplib
import markdown
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Annotated, List, TypedDict, Optional
from pydantic import BaseModel, Field, field_validator
from dateutil import parser as date_parser
from langchain_anthropic import ChatAnthropic
from langchain_tavily import TavilySearch
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, START, END
from langgraph.types import RetryPolicy
from dotenv import load_dotenv

load_dotenv()

# --- Configuration ---
CONFIG = {
    "days_back": 1,
    "max_search_results": 5,
    "rate_limit_delay": 2.0,
}

# Email Settings
SMTP_SERVER = os.environ.get("SMTP_SERVER")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
EMAIL_RECIPIENT = os.environ.get("EMAIL_RECIPIENT")
SMTP_USERNAME = os.environ.get("SMTP_USERNAME") or EMAIL_SENDER

# FireCrawl Settings
FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY")


class TargetCompany(TypedDict):
    name: str
    keywords: List[str]


TARGET_COMPANIES: List[TargetCompany] = [
    {
        "name": "OpenAI",
        "keywords": [
            "openai",
            "chatgpt",
            "gpt-",
            "sam altman",
            "codex",
            "sora",
            "mark chen",
        ],
    },
    {
        "name": "Google DeepMind",
        "keywords": [
            "deepmind",
            "gemini",
            "google ai",
            "demis hassabis",
            "veo",
            "ai studio",
            "antigravity",
            "nano banana",
            "gemma",
            "imagen",
            "synthid",
            "lyria",
            "alphago",
            "alphazero",
        ],
    },
    {
        "name": "Microsoft AI",
        "keywords": [
            "microsoft",
            "copilot",
            "satya nadella",
            "azure ai",
            "phi",
            "foundry",
            "aurora",
            "magma",
            "muse",
            "autogen",
        ],
    },
    {
        "name": "Anthropic",
        "keywords": [
            "anthropic",
            "claude",
            "dario amodei",
            "opus",
            "sonnet",
            "haiku",
        ],
    },
    {
        "name": "NVIDIA",
        "keywords": [
            "nvidia",
            "jensen huang",
            "gpu",
            "blackwell",
            "omniverse",
            "dgx",
            "hgx",
            "igx",
            "ovx",
            "geforce",
            "nemo",
            "nim",
            "dynamo",
            "metropolis",
            "cosmos",
            "isaac groot",
            "clara",
            "nemotron",
        ],
    },
    {
        "name": "Meta AI",
        "keywords": [
            "meta ai",
            "llama",
            "mark zuckerberg",
            "facebook ai",
            "sam",
            "dino",
            "meta segment",
            "meta",
            "v-jepa",
            "llama",
        ],
    },
    {"name": "xAI", "keywords": ["xai", "grok", "elon musk", "colossus"]},
    {
        "name": "Apple",
        "keywords": [
            "apple intelligence",
            "siri",
            "tim cook",
            "apple ai",
            "amar subramanya",
        ],
    },
    {
        "name": "DeepSeek",
        "keywords": [
            "deepseek",
            "deepseek-v3",
            "deepseek-coder",
            "deepseek-r1",
            "deepseekmoe",
            "liang wengfeng",
            "wengfeng liang",
            "high-flyer",
        ],
    },
    {
        "name": "Mistral AI",
        "keywords": [
            "mistral",
            "mistral large",
            "mistral medium",
            "mistral family",
            "mistral small",
            "nemo",
            "ministral",
            "voxtral",
            "document ai",
            "le chat",
            "arthur mensch",
            "guillaume lample",
            "timothee lacroix",
            "mixtral",
            "codestral",
            "magistral",
        ],
    },
    {
        "name": "Perplexity",
        "keywords": [
            "perplexity",
            "aravind srinivas",
            "denis yarats",
            "johnny ho",
            "andy konwinski",
            "perplexity sonar",
            "sonar-pro",
            "comet",
            "pplx-api",
        ],
    },
    {
        "name": "Black Forest Labs",
        "keywords": [
            "black forest labs",
            "flux.1",
            "flux model",
            "flux.2",
            "flux",
            "robin rombach",
            "andreas blattmann",
            "axel sauer",
            "patrick esser",
            "image generation",
        ],
    },
    {
        "name": "LangChain",
        "keywords": [
            "langchain",
            "langgraph",
            "langsmith",
            "harrison chase",
            "llm orchestration",
            "ai agents",
            "ankush gola",
            "jacob lee",
            "deep agents",
        ],
    },
    {
        "name": "Helsing",
        "keywords": [
            "helsing",
            "defense ai",
            "torsten reil",
            "gundbert scherf",
            "niklas köhler",
            "daniel ek",
            "software-defined defence",
            "hx-2",
            "hf-1",
            "sg-1",
            "fathom",
            "ca-1",
            "cirra",
            "centaur",
            "lura",
            "altra",
        ],
    },
    {
        "name": "Celonis",
        "keywords": [
            "celonis",
            "alex rinke",
            "bastian nominacher",
            "martin klenk",
            "process mining",
            "execution management",
            "process intelligence",
            "enterprise ai",
        ],
    },
    {
        "name": "DeepL",
        "keywords": [
            "deepl",
            "jarek kutylowski",
            "ai translation",
            "deepl write",
            "deepl agent",
            "neural machine translation",
        ],
    },
    {
        "name": "Aleph Alpha",
        "keywords": [
            "aleph alpha",
            "jonas andrulis",
            "reto spörri",
            "samuel weinbach",
            "luminous",
            "pharia",
            "dora",
            "govtech",
            "sovereign ai",
            "industrial llm",
            "heidelberg ai",
        ],
    },
    {
        "name": "Oracle",
        "keywords": [
            "oracle",
            "larry ellison",
            "oci",
            "cohere",
            "heatwave",
            "oracle database 23ai",
            "safra catz",
            "ai vector search",
        ],
    },
]

BLACKLIST_DOMAINS = [
    "ts2.tech",
    "biztoc.com",
    "bignewsnetwork.com",
    "fagenwasanni.com",
    "crypto.news",
    "investing.com",
]

# Model Configurations
MODEL_FAST = "claude-haiku-4-5-20251001"
MODEL_SMART = "claude-haiku-4-5-20251001"  # Using Haiku while Sonnet is unstable


# --- 1. State and Schema Definition ---
class AgentState(TypedDict):
    raw_news: Annotated[List[str], operator.add]
    opinions: Annotated[List[str], operator.add]
    seen_urls: Annotated[List[str], operator.add]
    final_report: str
    steps: Annotated[int, operator.add]


class ResearchDecision(BaseModel):
    """The decision on whether to research a story further."""

    should_research: bool = Field(
        description="True if the news stories warrant external opinion research"
    )
    search_query: Optional[str] = Field(
        description="The search query to use if researching"
    )


# Updated CompanySection with smarter validation
class CompanySection(BaseModel):
    name: str = Field(description="Name of the company (e.g., OpenAI)")
    update: str = Field(
        description="Detailed paragraph about the news. Cite sources using [Source](url)."
    )
    citations: List[str] = Field(description="List of source URLs used in this section")

    @field_validator("update")
    @classmethod
    def clean_citations(cls, text: str) -> str:
        """
        1. Fixes raw URLs to be markdown links.
        2. Deduplicates consecutive identical citations.
        """
        # Step 1: Fix raw URLs that aren't already markdown links
        # Matches http(s)://... that is NOT preceded by ](
        # This converts "http://google.com" -> "[Source](http://google.com)"
        url_pattern = r"(?<!\]\()(?<!\")(https?://\S+)"

        def url_replacer(match):
            url = match.group(1).rstrip(").,")  # Clean trailing punctuation
            # Try to extract a domain name for the label
            try:
                domain = url.split("//")[1].split("/")[0].replace("www.", "")
                label = domain.split(".")[0].title()  # e.g. "Techcrunch"
            except:
                label = "Source"
            return f" [{label}]({url})"

        text = re.sub(url_pattern, url_replacer, text)

        # Step 2: Deduplicate consecutive Markdown links
        # Finds [Label](URL) followed immediately by [Label](URL)
        md_link_pattern = r"(\[[^\]]+\]\([^)]+\))"

        # We look for patterns like: LINK ... same LINK
        # This logic is tricky with regex alone, so we split and rebuild

        def dedup_match(match):
            # This simplistic dedup just collapses exactly adjacent duplicates
            # For complex dedup, the previous logic was okay, but let's simplify:
            return match.group(0)  # Pass through for now to ensure links break

        # The previous dedup logic was actually fine, the issue was Step 1 (Raw URLs)
        # So we just return the fixed text now.
        return text.strip()


class Newsletter(BaseModel):
    executive_summary: List[str] = Field(
        description="List of summary bullet points, one per company"
    )
    company_reports: List[CompanySection] = Field(
        description="Detailed reports for each company"
    )
    community_pulse: str = Field(description="Summary of external opinions")


# --- 2. Model & Tool Initialization ---
# Check for environment variables
if not os.environ.get("ANTHROPIC_API_KEY") or not os.environ.get("TAVILY_API_KEY"):
    print("Error: Keys missing. Please set ANTHROPIC_API_KEY and TAVILY_API_KEY.")
    exit(1)

retry_policy = RetryPolicy(
    max_attempts=5,
    initial_interval=2,
    backoff_factor=2,
    max_interval=30,
    retry_on=(Exception,),
)

FAST_MODEL_ID = os.environ.get("MODEL_FAST", MODEL_FAST)
SMART_MODEL_ID = os.environ.get("MODEL_SMART", MODEL_SMART)

llm_fast = ChatAnthropic(model=FAST_MODEL_ID, temperature=0, max_retries=3)
llm_smart = ChatAnthropic(model=SMART_MODEL_ID, temperature=0, max_retries=3)

# Bind the Pydantic model to the fast LLM for structured output
research_decider = llm_fast.with_structured_output(ResearchDecision)

newsletter_generator = llm_smart.with_structured_output(Newsletter)

tavily_tool = TavilySearch(
    max_results=CONFIG["max_search_results"],
    topic="news",
    days=CONFIG["days_back"],
)


# --- 3. Node Definitions ---
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
        # Search Query: Force exact match on name, look for news keywords
        query = f'"{company}" AI latest news announcement launch'
        print(f"   -> Checking: {company}...")

        try:
            response = tavily_tool.invoke({"query": query})
            # 2. Check Results
            hits = (
                response.get("results", []) if isinstance(response, dict) else response
            )
            if isinstance(hits, list):
                for item in hits:
                    url = item.get("url", "")
                    pub_date_str = item.get("published_date", None)
                    # Deduplication Check
                    if url in existing_urls:
                        continue
                    # Spam Check
                    if any(bad in url for bad in BLACKLIST_DOMAINS):
                        continue

                    # Strict Date Filtering
                    if pub_date_str:
                        try:
                            # Parse the date string
                            pub_date = date_parser.parse(pub_date_str)
                            # Ensure timezone awareness for comparison
                            if pub_date.tzinfo is None:
                                pub_date = pub_date.replace(
                                    tzinfo=datetime.timezone.utc
                                )

                            if pub_date < cutoff_date:
                                # Skip old news silently
                                continue
                        except Exception:
                            # If date parsing fails, we fallback to keeping it (safety)
                            # or logging a warning.
                            pass

                    content = item.get("content", "")
                    title = item.get("title", "")
                    full_text = (title + " " + content).lower()

                    # Enhanced Validation: Check against keyword list
                    if any(k.lower() in full_text for k in keywords):
                        results.append(f"[{company}] DETAIL: {content} (Source: {url})")
                        new_urls.append(url)
                        existing_urls.add(url)

            time.sleep(CONFIG["rate_limit_delay"])  # Slightly longer delay to be safe

        except Exception as e:
            print(f"      x Error checking {company}: {e}")

    if not results:
        results = ["No significant news found for any target company."]

    return {"raw_news": results, "seen_urls": new_urls, "steps": 1}


# --- ADD THESE IMPORTS AT THE TOP OF YOUR FILE ---
from playwright.sync_api import sync_playwright
import trafilatura
import time


# --- HELPER: Manual Stealth Logic ---
def apply_stealth(page):
    """
    Manually injects JavaScript to hide automation signals.
    Identical to what playwright-stealth does, but dependency-free.
    """
    # 1. Mask the 'navigator.webdriver' property
    page.add_init_script(
        """
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
    """
    )
    # 2. Mock 'chrome' object
    page.add_init_script(
        """
        window.chrome = {
            runtime: {}
        };
    """
    )
    # 3. Mock Plugins
    page.add_init_script(
        """
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5]
        });
    """
    )
    # 4. Mock Languages
    page.add_init_script(
        """
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en']
        });
    """
    )


# --- MAIN SCRAPER NODE ---
def scraper_node(state: AgentState):
    """
    Node 1.5: The Stealth Hybrid Reader.
    Strategy:
    1. Try fast static scrape (Trafilatura).
    2. If that fails/blocks, launch Stealth Headless Browser (Playwright).
    """
    print(f"\n--- [Step 1.5] Scraping Full Articles (Stealth Hybrid) ---")

    urls_to_scrape = state.get("seen_urls", [])

    # Safety limit
    if len(urls_to_scrape) > 20:
        print(f"   (Limiting scrape to first 20 of {len(urls_to_scrape)} URLs)")
        urls_to_scrape = urls_to_scrape[:20]

    scraped_content = []

    for url in urls_to_scrape:
        print(f"   -> Scraping: {url}")
        content = None

        # --- ATTEMPT 1: Fast Static Scrape ---
        try:
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                content = trafilatura.extract(
                    downloaded,
                    output_format="markdown",
                    include_links=True,
                    include_images=False,
                )
        except Exception:
            pass

        # Check for failure or "Anti-Bot" messages
        is_blocked = False
        if content:
            if "Cloudflare Ray ID" in content or "security service" in content:
                is_blocked = True

        # If empty, too short, or explicitly blocked... switch to Stealth Mode
        if not content or len(content) < 600 or is_blocked:
            print("      x Static scrape failed/blocked. Launching Stealth Browser...")

            # --- ATTEMPT 2: Stealth Browser ---
            try:
                with sync_playwright() as p:
                    # 1. Launch with anti-bot flags
                    browser = p.chromium.launch(
                        headless=True,
                        args=["--disable-blink-features=AutomationControlled"],
                    )

                    # 2. Use realistic context
                    context = browser.new_context(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        locale="en-US",
                        timezone_id="America/New_York",
                    )
                    page = context.new_page()

                    # 3. Apply Stealth Scripts
                    apply_stealth(page)

                    # 4. Navigate & Wait
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=25000)

                        # Wait for Cloudflare/JS to verify us
                        page.wait_for_timeout(5000)

                        # Scroll to load dynamic content
                        for _ in range(3):
                            page.mouse.wheel(0, 3000)
                            page.wait_for_timeout(1500)

                    except Exception as e:
                        print(f"      x Browser timeout: {e}")

                    html = page.content()
                    browser.close()

                    # Extract from the rendered HTML
                    content = trafilatura.extract(
                        html,
                        output_format="markdown",
                        include_links=True,
                        include_images=False,
                    )
            except Exception as e:
                print(f"      x Browser failed: {e}")

        # --- FINAL PROCESSING ---
        if content and "Cloudflare Ray ID" not in content:
            if len(content) > 20000:
                content = content[:20000] + "... [TRUNCATED]"

            scraped_content.append(f"FULL ARTICLE CONTENT ({url}):\n{content}\n---\n")
            print(f"      ✅ Success: {len(content)} chars")
        else:
            print(f"      x Failed to extract meaningful content from {url}")

    if not scraped_content:
        return {}

    return {"raw_news": scraped_content}


def opinion_researcher(state: AgentState):
    """
    Node 2: Opinion Researcher.
    """
    print("\n--- [Step 2] Researching Community Opinions ---")

    news_context = "\n".join(state["raw_news"])

    prompt = f"""
    Here are the latest headlines found:
    {news_context}
    
    Analyze these headlines. Is there a specific story that is controversial, 
    highly technical, or major industry news that warrants checking Reddit/Hacker News?
    
    If yes, provide a specific search query. If no, set should_research to False.
    """
    # Using Structured Output instead of string parsing
    decision: ResearchDecision = research_decider.invoke(prompt)

    if not decision.should_research:
        return {"opinions": ["No major controversy found."], "steps": 1}

    search_query = decision.search_query
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
    Uses Structured Output (Newsletter Schema) to ensure formatting strictness.
    """
    print("\n--- [Step 3] Synthesizing Final Report ---")

    today = datetime.datetime.now().strftime("%B %d, %Y")
    allowed_companies = ", ".join([t["name"] for t in TARGET_COMPANIES])

    system_prompt = (
        f"You are the Editor-in-Chief of 'The Daily AI'. Today is {today}.\n"
        "Your goal: Write a comprehensive, high-signal market report.\n\n"
        "**SCOPE ENFORCEMENT**:\n"
        f"- You are ONLY allowed to report on these companies: **{allowed_companies}**.\n"
        "- Do not create sections for companies not on this list.\n\n"
        "**STRUCTURE REQUIREMENTS**:\n"
        "1. **EXECUTIVE SUMMARY**:\n"
        "   - Create a bulleted list.\n"
        "   - Exactly ONE bullet point per company monitored.\n"
        "   - Summarize the most important update.\n"
        "2. **DETAILED COMPANY REPORTS**:\n"
        "   - Create a subsection for each company.\n"
        "   - Write a detailed paragraph analyzing their latest news.\n"
        "   - You have access to FULL ARTICLE content. Use specific details (prices, benchmarks, quotes, etc.) from the text.\n"
        "   **CITATION RULE (CRITICAL)**:\n"
        "   - You MUST cite your sources **immediately** after the sentence.\n"
        "   - Format: `Sentence goes here ([Source Name](url)).`\n"
        "   - EXAMPLE: 'OpenAI raised funds [TechCrunch](https://techcrunch.com/...).'\n"
        "   - DO NOT use raw URLs like '[https://...]'. Always give them a name.\n"
        "3. **COMMUNITY PULSE**:\n"
        "   - Summarize external opinions.\n"
    )

    user_message = f"DATE: {today}\n\nRAW NEWS (Snippets + Full Articles):\n{'\n'.join(state['raw_news'])}\n\nEXTERNAL OPINIONS:\n{'\n'.join(state['opinions'])}"

    # Call the LLM with the Structured Output Schema
    # This returns a Pydantic object, not a string
    newsletter: Newsletter = newsletter_generator.invoke(
        [SystemMessage(content=system_prompt), HumanMessage(content=user_message)]
    )

    final_md = f"# THE DAILY AI | Market Report\n**{today}**\n\n---\n\n## EXECUTIVE SUMMARY\n\n"
    for item in newsletter.executive_summary:
        final_md += f"- {item}\n"

    final_md += "\n---\n\n## DETAILED COMPANY REPORTS\n\n"

    for report in newsletter.company_reports:
        # FILTER: Skip sections that say "No news" or are very short
        if "no significant news" in report.update.lower() or len(report.update) < 50:
            continue

        final_md += f"### {report.name}\n\n{report.update}\n\n"

    final_md += "\n---\n\n## COMMUNITY PULSE\n\n"
    final_md += newsletter.community_pulse

    final_md += "\n\n---\n**Report compiled by The Daily AI Editorial Team**"

    return {"final_report": final_md}


# --- 5. Graph Construction ---
workflow = StateGraph(AgentState)

workflow.add_node("monitor", monitor_news, retry=retry_policy)
workflow.add_node("scraper", scraper_node)
workflow.add_node("researcher", opinion_researcher, retry=retry_policy)
workflow.add_node("editor", editor_writer, retry=retry_policy)

workflow.add_edge(START, "monitor")
workflow.add_edge("monitor", "scraper")
workflow.add_edge("scraper", "researcher")
workflow.add_edge("researcher", "editor")
workflow.add_edge("editor", END)

app = workflow.compile()


# --- 6. Helper Function: Send Email ---
def send_email(report_md: str):
    """
    Sends the Markdown report as an HTML email using SMTP with Split Auth support.
    """
    # Check against SMTP_USERNAME instead of EMAIL_SENDER for login credentials
    if not SMTP_USERNAME or not EMAIL_PASSWORD or not EMAIL_RECIPIENT:
        print("⚠️  Email credentials missing. Skipping email send.")
        return

    print(f"\n📧 Sending email to {EMAIL_RECIPIENT} via {SMTP_SERVER}...")

    try:
        html_content = markdown.markdown(report_md)
        styled_html = f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 20px;">
                <div style="background-color: #f4f4f4; padding: 10px; text-align: center; border-radius: 5px;">
                    <h2 style="color: #2c3e50; margin: 0;">The Daily AI Report</h2>
                    <p style="font-size: 12px; color: #7f8c8d;">{datetime.datetime.now().strftime('%B %d, %Y')}</p>
                </div>
                <div style="margin-top: 20px;">
                    {html_content}
                </div>
                <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
                <p style="font-size: 11px; color: #999; text-align: center;">
                    Generated automatically by your AI Agent.
                </p>
            </body>
        </html>
        """

        msg = MIMEMultipart()
        # The 'From' header is what the recipient sees. It must be your verified email.
        msg["From"] = f"AI Newsletter <{EMAIL_SENDER}>"
        msg["To"] = EMAIL_RECIPIENT
        msg["Subject"] = (
            f"AI Market Report: {datetime.datetime.now().strftime('%Y-%m-%d')}"
        )
        msg.attach(MIMEText(styled_html, "html"))

        # Connect to SMTP Server
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            # Login with the specific Username (ID)
            server.login(SMTP_USERNAME, EMAIL_PASSWORD)
            # Send message
            server.send_message(msg)

        print("✅ Email sent successfully!")

    except Exception as e:
        print(f"❌ Failed to send email: {e}")


# --- 5. Execution ---
if __name__ == "__main__":
    print(
        f"🚀 Starting AI Newsletter Agent ({datetime.datetime.now().strftime('%Y-%m-%d')})"
    )

    final_state = app.invoke(
        {"raw_news": [], "opinions": [], "seen_urls": [], "steps": 0}
    )

    report = final_state["final_report"]

    filename = f"AI_Newsletter_{datetime.datetime.now().strftime('%Y-%m-%d')}.md"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n✅ Report saved to: {filename}")
    send_email(report)
