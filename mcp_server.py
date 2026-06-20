# Single responsibility: expose agents/orchestrator.py's two entry points
# as MCP tools, so any MCP-compatible client/LLM can call the pipeline
# directly. Like app.py, holds no pipeline logic of its own — each tool is
# a thin wrapper that delegates to run_pipeline() or run_pipeline_from_query().

from mcp.server.fastmcp import FastMCP

from agents.orchestrator import run_pipeline, run_pipeline_from_query

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


@mcp.tool()
async def get_farm_recommendation_from_text(query: str) -> dict:
    """Get a farm feasibility recommendation from a free-text description.

    Runs the same pipeline as get_farm_recommendation, but starts from a
    single unstructured string instead of separate fields. The query is
    parsed by intake_agent, which checks it for safety and extracts
    location/budget/land_area/target_profit/rent_cost in one step (this
    tool does not call input_guard_agent — intake_agent's check covers it).

    Example: "I have $5000 and 2 acres in Qatar, want something profitable, target $1000 profit."

    Args:
        query: A free-text description of the farmer's situation. Should
            mention a location, budget, land area, and target profit;
            rent cost is optional and defaults to 0 if not mentioned.

    Returns:
        Same shape as get_farm_recommendation on success or budget failure.
        If required information is missing from `query`, returns
        {"feasible": False, "incomplete": True, "reason": str} where
        `reason` is a follow-up question — ask the user and call this tool
        again with the combined original query and their answer.
    """
    return await run_pipeline_from_query(query)


if __name__ == "__main__":
    mcp.run()
