def _total_cost(crop: dict, land_area: float, rent_cost: float) -> float:
    return (crop["cost_per_unit_area"] * land_area) + rent_cost


def budget_filter(
    crops: list[dict],
    budget: float,
    land_area: float,
    rent_cost: float = 0,
) -> list[dict]:
    """Pure Python, no LLM. Removes crops whose total cost exceeds the budget.
    total_cost = (cost_per_unit_area * land_area) + rent_cost
    Returns the filtered list, same dict structure, unmodified fields.

    This is plain arithmetic over numbers the research agent already
    returned, with one correct answer for any given input. An LLM call
    would be slower, cost money/quota, and risk an inconsistent or wrong
    result for something a single multiply-and-compare always gets right.
    """
    return [
        crop
        for crop in crops
        if _total_cost(crop, land_area, rent_cost) <= budget
    ]


def profit_ranker(
    crops: list[dict],
    land_area: float,
    rent_cost: float = 0,
) -> list[dict]:
    """Pure Python, no LLM. Ranks crops by profit margin, descending.
    revenue = expected_yield_per_unit_area * land_area * market_price_per_unit
    total_cost = (cost_per_unit_area * land_area) + rent_cost
    profit = revenue - total_cost
    profit_margin = profit / total_cost
    Adds 'revenue', 'total_cost', 'profit', 'profit_margin' keys to each crop dict.
    Returns the list sorted by profit_margin descending.

    Same reasoning as budget_filter: this is deterministic arithmetic and
    sorting, not a judgment call an LLM needs to make.
    """
    ranked = []
    for crop in crops:
        total_cost = _total_cost(crop, land_area, rent_cost)
        revenue = crop["expected_yield_per_unit_area"] * land_area * crop["market_price_per_unit"]
        profit = revenue - total_cost
        ranked.append(
            {
                **crop,
                "revenue": revenue,
                "total_cost": total_cost,
                "profit": profit,
                "profit_margin": profit / total_cost,
            }
        )

    return sorted(ranked, key=lambda crop: crop["profit_margin"], reverse=True)


if __name__ == "__main__":
    test_crops = [
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

    survivors = budget_filter(test_crops, budget=5000, land_area=10)

    print("Crops that survive budget=5000, land_area=10:")
    for crop in survivors:
        print(f"  - {crop['crop']}")

    ranked = profit_ranker(survivors, land_area=10)

    print("\nRanked by profit_margin descending:")
    for crop in ranked:
        print(f"  - {crop['crop']}: profit_margin={crop['profit_margin']:.4f}")
