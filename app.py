# Single responsibility: the deployed HTTP service (Cloud Run) over
# agents/orchestrator.py's two entry points. Holds no pipeline logic itself
# — every route is a thin wrapper that validates the request shape (via
# pydantic) and delegates straight to run_pipeline() or
# run_pipeline_from_query().

from fastapi import FastAPI
from pydantic import BaseModel

from agents.orchestrator import run_pipeline, run_pipeline_from_query

app = FastAPI(title="Kaggriculture")


class StructuredRequest(BaseModel):
    """Request body for /recommend — caller already knows each field
    individually rather than describing their situation in prose."""

    location: str
    budget: float
    land_area: float
    target_profit: float
    rent_cost: float = 0


class TextRequest(BaseModel):
    """Request body for /recommend/text — a single free-text description
    of the farmer's situation, parsed and validated by intake_agent."""

    query: str


@app.get("/")
async def health():
    """Liveness check for Cloud Run / uptime monitoring — confirms the
    container is up and serving, independent of whether the Gemini API
    or any agent is reachable."""
    return {"status": "ok", "service": "kaggriculture"}


@app.post("/recommend")
async def recommend(req: StructuredRequest) -> dict:
    """Structured entry point: passes pre-parsed fields straight to
    run_pipeline(), which guards `location` via input_guard_agent before
    running research_agent/orchestrator_agent."""
    return await run_pipeline(req.location, req.budget, req.land_area, req.target_profit, req.rent_cost)


@app.post("/recommend/text")
async def recommend_text(req: TextRequest) -> dict:
    """Free-text entry point: hands the raw query to
    run_pipeline_from_query(), which guards/extracts via intake_agent
    instead of input_guard_agent (see orchestrator.py for why)."""
    return await run_pipeline_from_query(req.query)
