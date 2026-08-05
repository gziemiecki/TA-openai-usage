"""
Request parameters must be ones the API will accept.

Two rules from openai/openai-openapi:

* ``limit`` is capped per bucket width: 31 for ``1d``, 168 for ``1h``,
  1440 for ``1m``.  Every collector here uses daily buckets, so anything
  above 31 is a 400 on every request.
* ``group_by`` is a per-endpoint enum.  ``vector_stores`` and
  ``code_interpreter_sessions`` accept only ``project_id``; asking them to
  group by ``model`` is also a 400.
"""

import types

import pytest


def collector(helper, endpoint_type):
    for c in helper.COLLECTOR_REGISTRY:
        if c.endpoint_type == endpoint_type:
            return c
    raise AssertionError(f"no collector for {endpoint_type}")


@pytest.fixture
def capture(helper, monkeypatch, recording_session):
    """Run a collector against a fake transport and return the request params."""

    def run(endpoint_type, **kwargs):
        session = recording_session([{"data": [], "has_more": False}])
        monkeypatch.setattr(helper, "requests", session)
        collector(helper, endpoint_type).collect(
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
            **kwargs,
        )
        return session.calls[0]["params"]

    return run


def test_daily_buckets_never_request_more_than_31(capture):
    params = capture("completions")
    assert params["bucket_width"] == "1d"
    assert params["limit"] <= 31


def test_every_collector_stays_within_the_limit_cap(helper, capture):
    for c in helper.COLLECTOR_REGISTRY:
        params = capture(c.endpoint_type)
        assert params["limit"] <= 31, c.endpoint_type


def test_requested_attribution_dimensions_are_sent(capture):
    params = capture("completions", extra_group_by=["project_id", "api_key_id"])
    assert set(params["group_by"]) == {"model", "project_id", "api_key_id"}


def test_unsupported_dimensions_are_dropped(capture):
    """vector_stores accepts project_id only; model would be rejected."""
    params = capture("vector_stores", extra_group_by=["project_id", "user_id"])
    assert params["group_by"] == ["project_id"]


def test_code_interpreter_rejects_model_grouping(capture):
    params = capture("code_interpreter", extra_group_by=["model", "project_id"])
    assert params["group_by"] == ["project_id"]
