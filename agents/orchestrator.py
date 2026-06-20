import asyncio
import json
import sys
from pathlib import Path

# Allow this module to be run either as `python agents/orchestrator.py` or
# `python -m agents.orchestrator` by making the project root importable
# regardless of invocation style.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner

from agents.input_guard_agent import check_input
from agents.research_agent import research_agent
from filters import budget_filter, profit_ranker

load_dotenv()

# orchestrator_agent has NO tools and is handed already-computed numbers.
# Its only job is to turn a ranked list of crop dicts into a short written
# recommendation. The instruction explicitly forbids recalculating or
# altering any numbers because budget_filter() and profit_ranker() are the
# deterministic, auditable source of truth for cost/revenue/profit math
# (see filters.py). If the LLM were allowed to redo that arithmetic, two
# runs could disagree on the same input, and any mismatch between the
# LLM's numbers and the numbers actually used to filter/rank crops would
# undermine the whole pipeline's correctness guarantee. The model's value
# here is purely in language synthesis, not computation.
orchestrator_agent = LlmAgent(
    name="orchestrator_agent",
    model="gemini-3.5-flash",
    description="Synthesizes the final farm feasibility recommendation from pre-computed data.",
    instruction=(
        "You will be given a JSON list of feasible crops, already filtered by budget and "
        "ranked by profit margin (highest first), plus the user's target_profit. "
        "Write a short, clear recommendation: name the top crop, state its profit and margin, "
        "and note whether it meets target_profit. Briefly mention the next 1-2 alternatives. "
        "Do NOT recalculate or alter any numbers — use only the values given to you verbatim."
    ),
)

REQUIRED_CROP_FIELDS = {
    "crop": str,
    "cost_per_unit_area": (int, float),
    "expected_yield_per_unit_area": (int, float),
    "market_price_per_unit": (int, float),
    "currency": str,
    "unit_area": str,
}


def validate_crops(data) -> bool:
    """Checks data is a list of dicts, each with all 6 required keys and
    correct types. Returns False on anything malformed, never raises."""
    if not isinstance(data, list) or not data:
        return False

    for item in data:
        if not isinstance(item, dict):
            return False
        for key, expected_type in REQUIRED_CROP_FIELDS.items():
            if key not in item or not isinstance(item[key], expected_type):
                return False
            if isinstance(item[key], bool):
                # bool is a subclass of int; reject it explicitly for
                # numeric fields and for the `crop`/string fields above.
                return False

    return True


async def _call_agent_for_text(agent: LlmAgent, message: str, session_id: str) -> str:
    """Runs `agent` once with `message` in a fresh session and returns the
    final response text (empty string if no final response was produced)."""
    runner = InMemoryRunner(agent=agent)
    events = await runner.run_debug(message, session_id=session_id, quiet=True)

    for event in reversed(events):
        if event.is_final_response() and event.content and event.content.parts:
            return event.content.parts[0].text or ""

    return ""


async def run_pipeline(
    location: str,
    budget: float,
    land_area: float,
    target_profit: float,
    rent_cost: float = 0,
    max_retries: int = 2,
) -> dict:
    # Run the input guard before anything else costs an API call. research_agent
    # and orchestrator_agent are both paid LLM calls; if `location` is rejected
    # here, we return immediately and never spend quota on either of them.
    guard_result = await check_input(location)
    if not guard_result["allowed"]:
        return {"feasible": False, "rejected": True, "reason": guard_result["reason"]}

    crops = None
    error_feedback = None
    retries_used = 0

    for attempt in range(max_retries + 1):
        retries_used = attempt

        message = (
            location
            if error_feedback is None
            else (
                f"{location}\n\n"
                f"Your previous response was invalid: {error_feedback}\n"
                "Respond again with ONLY a valid JSON array matching the required schema."
            )
        )

        raw_text = await _call_agent_for_text(
            research_agent, message, session_id=f"research-{attempt}"
        )

        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            error_feedback = f"Response was not valid JSON: {exc}"
            continue

        if not validate_crops(parsed):
            error_feedback = (
                "JSON parsed but did not match the required schema. Each item "
                "needs crop (string), cost_per_unit_area (number), "
                "expected_yield_per_unit_area (number), market_price_per_unit "
                "(number), currency (string), unit_area (string)."
            )
            continue

        crops = parsed
        break

    if crops is None:
        return {
            "feasible": False,
            "error": f"research agent failed validation after {max_retries} retries",
        }

    filtered = budget_filter(crops, budget, land_area, rent_cost)
    if not filtered:
        return {"feasible": False, "error": "no crops fit this budget"}

    ranked = profit_ranker(filtered, land_area, rent_cost)

    summary_message = json.dumps({"ranked_crops": ranked, "target_profit": target_profit})
    summary = await _call_agent_for_text(
        orchestrator_agent, summary_message, session_id="orchestrator"
    )

    return {
        "feasible": True,
        "ranked_crops": ranked,
        "summary": summary,
        "retries_used": retries_used,
    }


async def _main() -> None:
    # Mocked research_agent output — same 4 crops used in filters.py's
    # __main__ test — so this exercises budget_filter -> profit_ranker ->
    # orchestrator_agent with exactly one real API call (the orchestrator
    # synthesis), instead of burning quota on a real research_agent run.
    mocked_crops = [
        {
            "crop": "Tomato",
            "cost_per_unit_area": 200,
            "expected_yield_per_unit_area": 800,
            "market_price_per_unit": 2.5,
            "currency": "QAR",
            "unit_area": "dunam",
        },
        {
            "crop": "Cucumber",
            "cost_per_unit_area": 350,
            "expected_yield_per_unit_area": 600,
            "market_price_per_unit": 1.8,
            "currency": "QAR",
            "unit_area": "dunam",
        },
        {
            "crop": "Dates",
            "cost_per_unit_area": 900,
            "expected_yield_per_unit_area": 300,
            "market_price_per_unit": 5.0,
            "currency": "QAR",
            "unit_area": "dunam",
        },
        {
            "crop": "Alfalfa",
            "cost_per_unit_area": 1200,
            "expected_yield_per_unit_area": 1500,
            "market_price_per_unit": 0.6,
            "currency": "QAR",
            "unit_area": "dunam",
        },
    ]

    filtered = budget_filter(mocked_crops, budget=5000, land_area=10)
    ranked = profit_ranker(filtered, land_area=10)

    summary_message = json.dumps({"ranked_crops": ranked, "target_profit": 3000})
    summary = await _call_agent_for_text(
        orchestrator_agent, summary_message, session_id="orchestrator-test"
    )

    print(summary)


if __name__ == "__main__":
    asyncio.run(_main())
