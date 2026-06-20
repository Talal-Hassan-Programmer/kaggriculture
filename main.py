# Single responsibility: CLI entry point for manual end-to-end testing of
# the real pipeline (no mocks). Two modes, both calling agents/orchestrator.py
# directly rather than going through app.py or mcp_server.py:
#   - default (`python main.py`): runs a hardcoded structured demo case.
#   - `--interactive`: runs the free-text intake flow with live user input.

import asyncio
import json
import sys

from agents.intake_agent import parse_query
from agents.orchestrator import run_pipeline


async def _main() -> None:
    """Real (non-mocked) demo run: calls run_pipeline() with a hardcoded
    location/budget/land_area/target_profit and prints both the raw
    research_agent output and the full pipeline result, so a real end-to-end
    run can be eyeballed without writing a test harness. Budget is set high
    enough (2,000,000 QAR) that at least one crop survives budget_filter,
    so the demo shows a real ranked recommendation rather than an
    infeasible-budget result."""
    print("=" * 60)
    print("CASE A: valid location")
    print("=" * 60)
    valid_result = await run_pipeline(
        location="Al Rayyan, Qatar",
        budget=2000000,
        land_area=10,
        target_profit=10000,
        rent_cost=0,
    )

    print("Raw crops returned by research_agent (before budget_filter):")
    print(json.dumps(valid_result.get("raw_crops"), indent=2))

    print()
    print("Full result:")
    print(json.dumps(valid_result, indent=2))


async def run_interactive() -> None:
    """Interactive CLI mode: collects a free-text query, lets the user fill
    in anything intake_agent reports as missing (up to 3 rounds total),
    then runs the existing run_pipeline() with the extracted fields.

    The back-and-forth loop lives here and only here — intake_agent.py and
    orchestrator.py each call their respective agent exactly once per call.
    """
    query = input("Describe your farm situation: ")

    max_rounds = 3
    parsed = None
    for round_num in range(1, max_rounds + 1):
        parsed = await parse_query(query)

        if parsed["status"] == "rejected":
            print(f"Rejected: {parsed['reason']}")
            return

        if parsed["status"] == "allowed":
            break

        # incomplete
        if round_num == max_rounds:
            print(f"Still missing information after {max_rounds} rounds: {parsed['reason']}")
            return

        print(parsed["reason"])
        reply = input("> ")
        query = f"{query}\n{reply}"

    fields = parsed["fields"]
    result = await run_pipeline(
        location=fields["location"],
        budget=fields["budget"],
        land_area=fields["land_area"],
        target_profit=fields["target_profit"],
        rent_cost=fields.get("rent_cost", 0),
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    if "--interactive" in sys.argv:
        asyncio.run(run_interactive())
    else:
        asyncio.run(_main())
