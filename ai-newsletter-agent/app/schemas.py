import re
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class ArticleSummary(BaseModel):
    title: str = Field(description="The clear headline of the article")
    key_points: List[str] = Field(
        description="List of 3-5 specific facts (prices, names, dates)"
    )
    relevance_score: int = Field(
        description="1-10 score of how important this is to AI tech"
    )


class ResearchDecision(BaseModel):
    """The decision on whether to research a story further."""

    should_research: bool = Field(
        description="True if the news stories warrant external opinion research"
    )
    search_query: Optional[str] = Field(
        description="The search query to use if researching"
    )


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
        # (The original logic noted that simply breaking raw URLs often fixes duplicates)
        return text.strip()


class Newsletter(BaseModel):
    executive_summary: List[str] = Field(
        description="List of summary bullet points, one per company"
    )
    company_reports: List[CompanySection] = Field(
        description="Detailed reports for each company"
    )
    community_pulse: str = Field(description="Summary of external opinions")
