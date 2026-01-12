import re
from typing import List
from pydantic import BaseModel, Field, field_validator


class ArticleSummary(BaseModel):
    title: str = Field(description="The clear headline of the article")
    key_points: List[str] = Field(description="List of 3-5 specific facts (prices, names, dates)")
    relevance_score: int = Field(description="1-10 score of how important this is to AI tech")
    primary_company: str = Field(
        description="The SINGLE company this article is primarily about. "
        "If about multiple, pick the most dominant one. "
        "Use 'Industry' if generic."
    )


class CompanySection(BaseModel):
    name: str = Field(description="Name of the company (e.g., OpenAI)")
    update: str = Field(
        description="Detailed paragraph about the news. You MUST include inline citations using [Publisher Name](url) format."
        "The citations must be placed exactly where the information is used in the text."
    )

    @field_validator("update")
    @classmethod
    def validate_links(cls, v):
        # Optional: Fail if no links are found to force a retry
        if "](" not in v:
            # You could log a warning or raise a ValueError to force the LLM to retry
            print(" [Warning] No markdown links found in update.")
        return v


class Newsletter(BaseModel):
    executive_summary: List[str] = Field(
        description="List of summary bullet points, one per company"
    )
    company_reports: List[CompanySection] = Field(description="Detailed reports for each company")
