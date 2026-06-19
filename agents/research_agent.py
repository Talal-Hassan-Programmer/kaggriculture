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
        '    "unit_area": string  // e.g. "dunam", "acre", "hectare"\n'
        "  }\n"
        "]\n\n"
        "Respond with the JSON array and nothing else."
    ),

    # Tools the model may call while answering. google_search is ADK's
    # built-in Gemini grounding tool, letting the agent fetch live web
    # results instead of relying on stale training data.
    tools=[google_search],
)


async def _main() -> None:
    runner = InMemoryRunner(agent=research_agent)
    await runner.run_debug("Al Rayyan, Qatar")


if __name__ == "__main__":
    asyncio.run(_main())
