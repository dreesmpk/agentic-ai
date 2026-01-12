from app.config import BLACKLIST_DOMAINS, CONFIG
from langchain_tavily import TavilySearch

# Tool for finding specific company news
tavily_news = TavilySearch(
    max_results=CONFIG["max_search_results"],
    search_depth=CONFIG["search_depth"],
    topic="news",
    exclude_domains=BLACKLIST_DOMAINS,
)
