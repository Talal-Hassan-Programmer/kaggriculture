# Single responsibility: own the actual pipeline (research -> filter -> rank
# -> synthesize) and expose it through two public entry points that differ
# only in how they handle untrusted input:
#   - run_pipeline(): structured args, guarded by input_guard_agent.
#   - run_pipeline_from_query(): free-text, guarded by intake_agent instead.
# Both entry points delegate the actual work to the shared, unguarded
# _run_core_pipeline(), so the retry/filter/rank/synthesize logic exists in
# exactly one place. This module is called by app.py (the FastAPI service)
# and mcp_server.py (the MCP tools) — it has no callers of its own besides
# main.py's manual test/demo entry points.

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
from agents.intake_agent import parse_query
from agents.research_agent import research_agent
from filters import budget_filter, profit_ranker

load_dotenv()


def _strip_fence(text: str) -> str:
    """Strips a leading/trailing ```json or ``` fence if present, so
    json.loads doesn't choke on grounded responses that ignore the
    'no markdown fences' instruction."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1]
        t = t.rsplit("```", 1)[0]
    return t.strip()

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
    correct types. Returns False on anything malformed, never raises.

    Used as the gate in _run_core_pipeline()'s retry loop: research_agent's
    output is an LLM response, so it can come back as non-JSON or with the
    wrong shape. This function is what decides "good enough to use" vs.
    "ask the model to try again," so it has to be strict and exception-free
    — a raised error here would crash the pipeline instead of triggering
    a retry.
    """
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


async def _run_core_pipeline(
    location: str,
    budget: float,
    land_area: float,
    target_profit: float,
    rent_cost: float = 0,
    max_retries: int = 2,
) -> dict:
    """Runs research_agent (with retries) -> budget_filter -> profit_ranker
    -> orchestrator_agent, and returns the final feasibility result.

    NO security/guard agent runs here — by design. This function assumes
    `location` has already been vetted by whichever guard the caller used
    (input_guard_agent via run_pipeline(), or intake_agent via
    run_pipeline_from_query()). It exists purely so that retry/filter/rank/
    synthesize logic lives in one place regardless of which guard ran
    upstream; it is never called directly from outside this module.
    """
    # Fail fast on invalid input before spending any API calls — land_area
    # feeds directly into budget_filter/profit_ranker's arithmetic, so a
    # non-positive value is never recoverable downstream. Lives here (rather
    # than in run_pipeline) so it protects both call paths: the structured
    # run_pipeline() and the free-text run_pipeline_from_query().
    if land_area <= 0:
        return {"feasible": False, "error": "land_area must be greater than 0"}

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
            parsed = json.loads(_strip_fence(raw_text))
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
        return {
            "feasible": False,
            "error": "no crops fit this budget",
            "raw_crops": crops,
        }

    ranked = profit_ranker(filtered, land_area, rent_cost)

    summary_message = json.dumps({"ranked_crops": ranked, "target_profit": target_profit})
    summary = await _call_agent_for_text(
        orchestrator_agent, summary_message, session_id="orchestrator"
    )

    return {
        "feasible": True,
        "raw_crops": crops,
        "ranked_crops": ranked,
        "summary": summary,
        "retries_used": retries_used,
    }


async def run_pipeline(
    location: str,
    budget: float,
    land_area: float,
    target_profit: float,
    rent_cost: float = 0,
    max_retries: int = 2,
) -> dict:
    """Entry point for STRUCTURED input (caller already knows location,
    budget, land_area, target_profit, rent_cost as separate values — e.g.
    app.py's /recommend endpoint or mcp_server.py's get_farm_recommendation).

    Guard: input_guard_agent (via check_input()), since `location` here is
    untrusted free text even though the other fields are structured numbers.
    This is the only guard used on this path — see run_pipeline_from_query()
    for why the free-text path uses a different guard instead of this one.
    """
    # Run the input guard before anything else costs an API call. research_agent
    # and orchestrator_agent are both paid LLM calls; if `location` is rejected
    # here, we return immediately and never spend quota on either of them.
    guard_result = await check_input(location)
    if not guard_result["allowed"]:
        return {"feasible": False, "rejected": True, "reason": guard_result["reason"]}

    return await _run_core_pipeline(
        location, budget, land_area, target_profit, rent_cost, max_retries
    )


async def run_pipeline_from_query(query: str, max_retries: int = 2) -> dict:
    """Entry point for FREE-TEXT input (caller only has a single
    unstructured string — e.g. app.py's /recommend/text endpoint or
    mcp_server.py's get_farm_recommendation_from_text).

    Guard: intake_agent (via parse_query()), NOT input_guard_agent.
    intake_agent does the same security classification input_guard_agent
    would do, plus field extraction, in one call — so this function calls
    _run_core_pipeline() directly instead of going through run_pipeline(),
    deliberately skipping input_guard_agent to avoid a second, redundant
    security check of the same already-vetted text.

    Single-shot: calls parse_query() exactly once. Any back-and-forth needed
    to fill in missing fields (an INCOMPLETE verdict) belongs in the caller
    (e.g. main.py's run_interactive() loop), not here.
    """
    intake_result = await parse_query(query)

    if intake_result["status"] != "allowed":
        return {
            "feasible": False,
            "rejected": intake_result["status"] == "rejected",
            "incomplete": intake_result["status"] == "incomplete",
            "reason": intake_result["reason"],
        }

    fields = intake_result["fields"]
    required = ("location", "budget", "land_area", "target_profit")
    if not fields or not all(k in fields and fields[k] is not None for k in required):
        return {
            "feasible": False,
            "rejected": False,
            "incomplete": True,
            "reason": "intake agent returned ALLOW but fields were missing or incomplete",
        }

    return await _run_core_pipeline(
        location=fields["location"],
        budget=fields["budget"],
        land_area=fields["land_area"],
        target_profit=fields["target_profit"],
        rent_cost=fields.get("rent_cost", 0),
        max_retries=max_retries,
    )


async def _main() -> None:
    """Manual smoke test for orchestrator_agent in isolation: feeds it
    pre-computed (mocked, not LLM-generated) ranked crops and prints the
    resulting summary text, to verify the synthesis step works without
    spending a research_agent call or running the security guards.

    Mocked research_agent output — same 4 crops used in filters.py's
    __main__ test — so this exercises budget_filter -> profit_ranker ->
    orchestrator_agent with exactly one real API call (the orchestrator
    synthesis), instead of burning quota on a real research_agent run.
    """
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
