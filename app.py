from fastapi import FastAPI
from pydantic import BaseModel

from agents.orchestrator import run_pipeline, run_pipeline_from_query

app = FastAPI(title="Kaggriculture")


class StructuredRequest(BaseModel):
    location: str
    budget: float
    land_area: float
    target_profit: float
    rent_cost: float = 0


class TextRequest(BaseModel):
    query: str


@app.get("/")
async def health():
    return {"status": "ok", "service": "kaggriculture"}


@app.post("/recommend")
async def recommend(req: StructuredRequest) -> dict:
    return await run_pipeline(req.location, req.budget, req.land_area, req.target_profit, req.rent_cost)


@app.post("/recommend/text")
async def recommend_text(req: TextRequest) -> dict:
    return await run_pipeline_from_query(req.query)
