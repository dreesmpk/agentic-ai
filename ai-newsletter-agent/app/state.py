import operator
from typing import Annotated, List, TypedDict


class AgentState(TypedDict):
    raw_news: Annotated[List[str], operator.add]
    summaries: Annotated[List[str], operator.add]
    opinions: Annotated[List[str], operator.add]
    seen_urls: Annotated[List[str], operator.add]
    final_report: str
    steps: Annotated[int, operator.add]
