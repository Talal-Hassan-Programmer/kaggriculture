import asyncio
import json

from agents.orchestrator import run_pipeline


async def _main() -> None:
    print("=" * 60)
    print("CASE A: valid location")
    print("=" * 60)
    valid_result = await run_pipeline(
        location="Al Rayyan, Qatar",
        budget=500000,
        land_area=10,
        target_profit=10000,
        rent_cost=0,
    )

    print("Raw crops returned by research_agent (before budget_filter):")
    print(json.dumps(valid_result.get("raw_crops"), indent=2))

    print()
    print("Full result:")
    print(json.dumps(valid_result, indent=2))


if __name__ == "__main__":
    asyncio.run(_main())
