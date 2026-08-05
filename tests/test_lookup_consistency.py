"""
The price lookup and the collectors have to agree on endpoint_type.

A row naming an endpoint no collector emits is dead weight that silently
never matches; the reverse (a search estimating cost for an endpoint with no
rows) produces nulls that look like zero spend.
"""

import csv
from pathlib import Path

LOOKUP = Path(__file__).resolve().parent.parent / "package" / "lookups" / "openai_model_costs.csv"

# Endpoints whose cost is read from /organization/costs rather than estimated:
# their pricing depends on a dimension the usage record does not carry
# (context level, session duration, storage duration).
BILLED_ONLY = {"code_interpreter", "web_search", "file_search", "vector_stores", "moderations", "costs"}


def _rows():
    with LOOKUP.open() as fh:
        return list(csv.DictReader(fh))


def test_lookup_only_references_live_endpoints(helper):
    known = {c.endpoint_type for c in helper.COLLECTOR_REGISTRY}
    referenced = {r["endpoint_type"] for r in _rows()}
    assert referenced - known == set()


def test_every_estimated_endpoint_has_price_rows(helper):
    referenced = {r["endpoint_type"] for r in _rows()}
    estimated = {c.endpoint_type for c in helper.COLLECTOR_REGISTRY} - BILLED_ONLY
    assert estimated - referenced == set()


def test_prices_are_numeric():
    for row in _rows():
        float(row["cost_per_input_unit_usd"])
        if row["cost_per_output_unit_usd"]:
            float(row["cost_per_output_unit_usd"])
