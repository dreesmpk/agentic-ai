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
    primary_company: str = Field(
        description="The SINGLE company this article is primarily about. "
        "If about multiple, pick the most dominant one. "
        "Use 'Industry' if generic."
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
        # Debug: Check if the validator is running and finding raw links
        if "http" in text and "](" not in text:
            print(f"   [Validator] Fixing raw links in text snippet: {text[:30]}...")

        url_pattern = r"(?<!\]\()(?<!\")(https?://\S+)"

        def url_replacer(match):
            url = match.group(1).rstrip(").,")
            try:
                domain = url.split("//")[1].split("/")[0].replace("www.", "")
                label = domain.split(".")[0].title()
            except:
                label = "Source"

            print(f"   [Validator] Converted {url} -> [{label}]({url})")
            return f" [{label}]({url})"

        text = re.sub(url_pattern, url_replacer, text)
        return text.strip()


class Newsletter(BaseModel):
    executive_summary: List[str] = Field(
        description="List of summary bullet points, one per company"
    )
    company_reports: List[CompanySection] = Field(
        description="Detailed reports for each company"
    )
