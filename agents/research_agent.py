# Single responsibility: research real-world crop economics for a region.
# This is the ONLY agent in the project that does live research (via the
# google_search tool) — every other agent reasons purely over text or
# numbers it's handed. Called exclusively from agents/orchestrator.py's
# _run_core_pipeline(), which both run_pipeline() and run_pipeline_from_query()
# go through; never called directly from app.py or mcp_server.py.

import asyncio

from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.adk.tools import google_search

load_dotenv()

# LlmAgent is ADK's standard agent wrapper around a single LLM call (plus
# optional tools/sub-agents). Each constructor argument below maps to one
# piece of that wrapper's behavior:
research_agent = LlmAgent(
    # Unique identifier for this agent within an ADK app/session. Required
    # by the framework for routing events and logging.
    name="research_agent",

    # The underlying Gemini model that powers this agent's reasoning.
    model="gemini-3.5-flash",

    # Short summary of the agent's purpose, used by ADK tooling/UI and by
    # parent agents (e.g. an orchestrator) deciding whether to delegate to it.
    description="Finds viable crops and their cost/yield/price economics for a given region.",

    # The system prompt: tells the model what task to perform, what tool to
    # use to ground its answer in real data, and exactly what output shape
    # to return. Kept strict (JSON-only) so downstream code can parse it
    # without extra cleanup.
    instruction=(
        "You are an agricultural research agent. Given a region or location "
        "string, use the google_search tool to research real-world data and "
        "identify 5 to 8 crops that are viable to grow in that region.\n\n"
        "For each crop, return ONLY the following JSON structure, with no "
        "prose, headers, or markdown fences outside the JSON array:\n\n"
        "[\n"
        "  {\n"
        '    "crop": string,\n'
        '    "cost_per_unit_area": number,\n'
        '    "expected_yield_per_unit_area": number,\n'
        '    "market_price_per_unit": number,\n'
        '    "currency": string,\n'
        '    "unit_area": string\n'
        "  }\n"
        "]\n\n"
        "CONSISTENCY RULES (critical — downstream code depends on these):\n"
        "- Use exactly ONE currency for every crop in this response. Pick "
        "whichever currency is standard for real market transactions in "
        "this region (e.g. QAR for Qatar, USD for the US). Never mix "
        "currencies across crops.\n"
        "- Always set unit_area to exactly \"hectare\" for every crop, "
        "regardless of what unit your source data uses. If a source "
        "quotes dunams or acres, convert before reporting "
        "(1 hectare = 10 dunams = 2.471 acres).\n\n"
        "Respond with the JSON array and nothing else."
    ),

    # Tools the model may call while answering. google_search is ADK's
    # built-in Gemini grounding tool, letting the agent fetch live web
    # results instead of relying on stale training data.
    tools=[google_search],
)


async def _main() -> None:
    """Manual smoke test: runs research_agent standalone against a real
    location and prints the raw response, so this agent's prompt/tool
    wiring can be checked in isolation without going through the full
    pipeline (and without spending a research_agent + orchestrator_agent
    call pair just to verify the search grounding works)."""
    runner = InMemoryRunner(agent=research_agent)
    await runner.run_debug("Al Rayyan, Qatar")


if __name__ == "__main__":
    asyncio.run(_main())
