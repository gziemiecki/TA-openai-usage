"""
Endpoints the add-on did not collect at all.

``moderations`` and ``file_search_calls`` are billable usage endpoints that
were simply missing.  ``/organization/costs`` is the more important gap: it
returns what OpenAI actually billed, in currency, which is the number the
add-on previously tried to reconstruct from a hand-maintained price list.
"""

import types

import pytest


def collector(helper, endpoint_type):
    for c in helper.COLLECTOR_REGISTRY:
        if c.endpoint_type == endpoint_type:
            return c
    raise AssertionError(f"no collector for {endpoint_type}")


def test_moderations_is_collected(helper):
    record = {
        "object": "organization.usage.moderations.result",
        "input_tokens": 250,
        "num_model_requests": 5,
        "model": "text-moderation-latest",
        "start_time": 1730419200,
    }
    event = collector(helper, "moderations").format_record(record)
    assert event["input_tokens"] == 250
    assert event["num_model_requests"] == 5


def test_file_search_is_collected(helper):
    record = {
        "object": "organization.usage.file_search_calls.result",
        "num_requests": 7,
        "project_id": "proj_abc",
        "vector_store_id": "vs_123",
        "start_time": 1730419200,
    }
    event = collector(helper, "file_search").format_record(record)
    assert event["num_requests"] == 7
    assert event["vector_store_id"] == "vs_123"


def test_costs_records_the_billed_amount_and_currency(helper):
    record = {
        "object": "organization.costs.result",
        "amount": {"value": 0.06, "currency": "usd"},
        "line_item": "Image models",
        "project_id": "proj_abc",
        "quantity": 10000,
        "start_time": 1730419200,
    }
    event = collector(helper, "costs").format_record(record)
    assert event["cost_usd"] == 0.06
    assert event["currency"] == "usd"
    assert event["line_item"] == "Image models"
    assert event["project_id"] == "proj_abc"


def test_costs_endpoint_is_not_under_the_usage_path(helper):
    url = collector(helper, "costs").url
    assert url == "https://api.openai.com/v1/organization/costs"


def test_costs_groups_by_line_item_and_project(helper):
    resolved = collector(helper, "costs").resolve_group_by(["project_id", "model"])
    assert "line_item" in resolved
    assert "project_id" in resolved
    assert "model" not in resolved, "the costs endpoint has no model dimension"


def test_costs_survives_a_missing_amount(helper):
    """`amount` is the only interesting field and the spec marks it optional."""
    event = collector(helper, "costs").format_record(
        {"object": "organization.costs.result", "start_time": 1730419200}
    )
    assert event["cost_usd"] == 0
