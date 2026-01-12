import datetime
from app.agent.graph import workflow_app
from app.services.email import send_email

if __name__ == "__main__":
    print(
        f"Starting AI Newsletter Agent ({datetime.datetime.now().strftime('%Y-%m-%d')})"
    )

    # Run the graph
    final_state = workflow_app.invoke(
        {
            "search_results": [],
            "scraped_articles": [],
            "summaries": [],
            "seen_urls": [],
            "final_report": "",
            "steps": 0,
        }
    )

    report = final_state["final_report"]

    # Save locally
    filename = f"AI_Newsletter_{datetime.datetime.now().strftime('%Y-%m-%d')}.md"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\n Report saved to: {filename}")

    # Send Email
    send_email(report)
