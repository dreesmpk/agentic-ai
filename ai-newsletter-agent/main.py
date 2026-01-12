import asyncio
import datetime

from app.agent.graph import workflow_app
from app.services.email import send_email


async def main():
    print(
        f"Starting AI Newsletter Agent ({datetime.datetime.now().strftime('%Y-%m-%d')})"
    )

    # Initial State
    initial_state = {
        "search_results": [],
        "scraped_articles": [],
        "summaries": [],
        "seen_urls": [],
        "final_report": "",
        "steps": 0,
    }

    # Use 'ainvoke' instead of 'invoke' because summarize_node is async
    final_state = await workflow_app.ainvoke(initial_state)
    report = final_state.get("final_report", "No report generated.")

    # Save locally
    filename = f"output/AI_Newsletter_{datetime.datetime.now().strftime('%Y-%m-%d')}.md"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\n Report saved to: {filename}")
    # Send via Email
    try:
        send_email(report)
    except Exception as e:
        print(f"Failed to send email: {e}")


if __name__ == "__main__":
    asyncio.run(main())
