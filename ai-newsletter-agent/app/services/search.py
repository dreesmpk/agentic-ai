from langchain_tavily import TavilySearch
from app.config import CONFIG, BLACKLIST_DOMAINS

# Tool for finding specific company news
tavily_news = TavilySearch(
    max_results=CONFIG["max_search_results"],
    search_depth=CONFIG["search_depth"],
    topic="news",
    exclude_domains=BLACKLIST_DOMAINS,
)
