import os
from langchain_anthropic import ChatAnthropic
from app.config import MODEL_FAST, MODEL_SMART
from app.schemas import Newsletter, ResearchDecision, ArticleSummary

# Check keys strictly before initializing
if not os.environ.get("ANTHROPIC_API_KEY"):
    print("⚠️  Warning: ANTHROPIC_API_KEY not found in environment.")

# Initialize Models
# max_retries=3 handles internal API errors (500s) automatically
llm_fast = ChatAnthropic(model=MODEL_FAST, temperature=0, max_retries=3)
llm_smart = ChatAnthropic(model=MODEL_SMART, temperature=0, max_retries=3)

# Bind Structured Outputs
# This creates callable objects that return Pydantic models directly
research_decider = llm_fast.with_structured_output(ResearchDecision)
newsletter_generator = llm_smart.with_structured_output(Newsletter)
article_summarizer = llm_fast.with_structured_output(ArticleSummary)
