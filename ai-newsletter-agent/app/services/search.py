from langchain_tavily import TavilySearch
from app.config import CONFIG

# Tool for finding specific company news (strict date filtering)
tavily_news = TavilySearch(
    max_results=CONFIG["max_search_results"],
    topic="news",
    days=CONFIG["days_back"],
)

# Tool for general research (Reddit/HN opinions)
tavily_general = TavilySearch(max_results=5, topic="general", include_answer="advanced")
