"""
The usage and costs endpoints return time buckets, not records.

  {"data": [{"object": "bucket", "start_time": ..., "end_time": ...,
             "results": [ <the actual metrics> ]}], "has_more": false}

Every metric lives on the nested ``results`` entries.  Formatting the bucket
itself yields an event with a correct timestamp and zero for everything else,
which is indistinguishable from "this model was not used".
"""

import types

import pytest


def collector(helper, endpoint_type):
    for c in helper.COLLECTOR_REGISTRY:
        if c.endpoint_type == endpoint_type:
            return c
    raise AssertionError(f"no collector for {endpoint_type}")


@pytest.fixture
def fetch(helper, monkeypatch, recording_session):
    def _fetch(endpoint_type, pages):
        session = recording_session(pages)
        monkeypatch.setattr(helper, "requests", session)
        return collector(helper, endpoint_type).collect(
            logger=types.SimpleNamespace(
                info=lambda *a, **k: None,
                warning=lambda *a, **k: None,
                error=lambda *a, **k: None,
            ),
            headers={},
            start_time=1730419200,
            end_time=1730505600,
            model_filter=None,
            proxies=None,
        )

    return _fetch


BUCKET = {
    "data": [
        {
            "object": "bucket",
            "start_time": 1730419200,
            "end_time": 1730505600,
            "results": [
                {
                    "object": "organization.usage.completions.result",
                    "input_tokens": 1200,
                    "output_tokens": 340,
                    "input_cached_tokens": 200,
                    "num_model_requests": 4,
                    "model": "gpt-4o",
                },
                {
                    "object": "organization.usage.completions.result",
                    "input_tokens": 90,
                    "output_tokens": 12,
                    "num_model_requests": 1,
                    "model": "o3",
                },
            ],
        }
    ],
    "has_more": False,
}


def test_one_event_per_result_not_per_bucket(fetch):
    records = fetch("completions", [BUCKET])
    assert len(records) == 2


def test_metrics_come_from_the_nested_result(fetch):
    records = fetch("completions", [BUCKET])
    by_model = {r["model"]: r for r in records}
    assert by_model["gpt-4o"]["input_tokens"] == 1200
    assert by_model["gpt-4o"]["output_tokens"] == 340
    assert by_model["gpt-4o"]["cached_tokens"] == 200
    assert by_model["o3"]["input_tokens"] == 90


def test_bucket_window_is_carried_onto_each_event(fetch):
    records = fetch("completions", [BUCKET])
    for record in records:
        assert record["_time"] == 1730419200
        assert record["bucket_start_time"] == 1730419200
        assert record["bucket_end_time"] == 1730505600


def test_empty_buckets_produce_no_events(fetch):
    page = {
        "data": [
            {"object": "bucket", "start_time": 1730419200, "end_time": 1730505600, "results": []}
        ],
        "has_more": False,
    }
    assert fetch("completions", [page]) == []


def test_costs_buckets_are_unwrapped_too(fetch):
    page = {
        "data": [
            {
                "object": "bucket",
                "start_time": 1730419200,
                "end_time": 1730505600,
                "results": [
                    {
                        "object": "organization.costs.result",
                        "amount": {"value": 12.5, "currency": "usd"},
                        "line_item": "Image models",
                    }
                ],
            }
        ],
        "has_more": False,
    }
    records = fetch("costs", [page])
    assert len(records) == 1
    assert records[0]["cost_usd"] == 12.5
