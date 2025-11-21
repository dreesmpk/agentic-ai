# Iterative Deep Research Agent

## Overview

This project implements an advanced AI research agent capable of performing autonomous, multi-step research on complex topics. Built using **LangGraph** and **LangChain** , the agent moves beyond simple query-response interactions by utilizing a cyclic workflow. It autonomously plans search queries, analyzes results, determines if further information is required, and synthesizes a comprehensive final report with citations.

A key feature of this architecture is the **Human-in-the-Loop (HITL)** mechanism, which allows users to review gathered data and guide the agent's direction before the final report is generated, ensuring accuracy and alignment with user intent.

## Key Features

-   **Cyclic Research Workflow:** Unlike linear chains, this agent operates on a graph topology (StateGraph), allowing it to loop through the research process multiple times until sufficient information is gathered or a logical iteration limit is reached.
-   **Human-in-the-Loop (HITL):** Implements LangGraph checkpoints and interrupts. The agent pauses execution prior to the synthesis phase, presenting the user with current findings and allowing for feedback or approval.
-   **State Management:** Utilizes persistent state to track research notes, source URLs, and conversation history across multiple iterations and interruptions.
-   **Robust Error Handling:** Includes specific logic to handle API rate limits (e.g., Anthropic 429 errors) via content truncation and automatic retry policies.
-   **Dynamic Routing:** The agent intelligently decides whether to utilize search tools, request human review, or generate the final report based on the context of the gathered data.

## System Architecture

The agent is modeled as a state machine with the following nodes:

1. **Chatbot (Decision Node):** The reasoning engine (Claude 3.5 Sonnet) that evaluates the current state and decides whether to search for more information or proceed to reporting.
2. **Tools:** Executes web searches using the Tavily Search API.
3. **Summarize:** Processes raw HTML/text content from search results, truncates data to manage context windows, and generates concise notes.
4. **Human Review:** A checkpoint node where the workflow pauses for user interaction.
5. **Synthesize:** Aggregates all gathered notes and sources to produce a final Markdown report with a bibliography.

### Workflow Logic

1. **Initialization:** User provides a research topic.
2. **Iterative Loop:**
    - The agent generates a search query.
    - Search results are summarized and stored in the state.
    - The agent evaluates the new information.
    - If gaps exist (and iteration limit < 3), the loop continues.
3. **Review:** Once data is sufficient, the agent requests approval.
4. **Feedback/Completion:** The user can approve the report generation or provide feedback, which triggers a new research loop.

## Technical Stack

-   **Language:** Python 3.10+
-   **Orchestration:** LangGraph, LangChain
-   **LLM:** Anthropic Claude 4.5 Sonnet
-   **Search Tool:** Tavily Search API
-   **State Persistence:** LangGraph MemorySaver

## Installation

1. **Clone the repository:**
   **Bash**

    ```
    git clone <repository-url>
    cd deep-research-agent
    ```

2. **Create and activate a virtual environment:**
   **Bash**

    ```
    python -m venv .venv
    # Windows
    .venv\Scripts\activate
    # macOS/Linux
    source .venv/bin/activate
    ```

3. **Install dependencies:**
   **Bash**

    ```
    pip install -r requirements.txt
    ```

## Configuration

Environment variables are required for the LLM and Search API. Create a `.env` file in the root directory or export them directly in your shell:

**Bash**

```
export ANTHROPIC_API_KEY="sk-..."
export TAVILY_API_KEY="tvly-..."
```

## Usage

To start an interactive research session:

**Bash**

```
python deep_research_agent.py
```

### Interaction Guide

-   The agent will display its thought process and the specific queries it is searching for.
-   When the research phase is complete, the system will pause and display a summary of the collected notes.
-   **Approve:** Type `ok` or `yes` to generate the final report.
-   **Refine:** Type specific feedback (e.g., "Please check the performance differences in multithreaded contexts") to send the agent back to the research phase.
-   The final report will be saved as `final_report.md`.

## Future Improvements

-   Implementation of parallel tool execution to perform multiple search queries simultaneously.
-   Integration of a local vector store (ChromaDB) to persist research over long-term sessions.
-   Support for multiple output formats (PDF, JSON) beyond Markdown.
