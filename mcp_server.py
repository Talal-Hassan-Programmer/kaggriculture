from mcp.server.fastmcp import FastMCP

from agents.orchestrator import run_pipeline

mcp = FastMCP("kaggriculture")


@mcp.tool()
async def get_farm_recommendation(
    location: str,
    budget: float,
    land_area: float,
    target_profit: float,
    rent_cost: float = 0,
) -> dict:
    """Get a ranked crop feasibility recommendation for a farm location, budget, and land area.

    Runs the full Kaggriculture pipeline:
    1. Validates `location` is a genuine place name and not a prompt injection or
       off-topic request. Unsafe input is rejected before any research is done.
    2. Researches real-world crops viable for `location`, including their cost,
       expected yield, and market price.
    3. Filters out crops whose total cost (cost_per_unit_area * land_area + rent_cost)
       exceeds `budget`.
    4. Ranks the remaining crops by profit margin, highest first.
    5. Synthesizes a short written recommendation comparing the top crop's profit
       against `target_profit`, with 1-2 alternatives.

    Args:
        location: A real-world place name to research crops for, e.g.
            "Al Rayyan, Qatar" or just "Qatar".
        budget: Total amount the farmer is willing to spend, in the local
            currency the research turns up for that crop/region (e.g. QAR).
        land_area: Amount of land available, in whatever unit_area the
            research data uses (e.g. hectares, acres, dunams).
        target_profit: The profit the farmer hopes to clear, in the same
            currency as budget, used only to phrase the recommendation
            (it does not affect filtering or ranking).
        rent_cost: Optional flat additional cost (e.g. land rent) added on
            top of each crop's per-area cost before comparing to budget.
            Defaults to 0.

    Returns:
        On success: {"feasible": True, "raw_crops": [...], "ranked_crops": [...],
        "summary": str, "retries_used": int}.
        On no crop fitting the budget: {"feasible": False, "error": str,
        "raw_crops": [...]}.
        On rejected/unsafe input: {"feasible": False, "rejected": True,
        "reason": str}.
    """
    return await run_pipeline(location, budget, land_area, target_profit, rent_cost)


if __name__ == "__main__":
    mcp.run()
