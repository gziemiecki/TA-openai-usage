"""
Model filtering belongs on the API, not in the add-on.

The usage endpoints take a ``models`` query parameter.  Filtering client-side
fetches every record and then throws some away, which costs the same API
calls and hides the filter from anyone reading the request.  It also means a
model the add-on has never heard of is silently dropped rather than counted.
"""

import types

import pytest


def collector(helper, endpoint_type):
    for c in helper.COLLECTOR_REGISTRY:
        if c.endpoint_type == endpoint_type:
            return c
    raise AssertionError(f"no collector for {endpoint_type}")


@pytest.fixture
def run(helper, monkeypatch, recording_session):
    def _run(endpoint_type, pages=None, **kwargs):
        session = recording_session(pages or [{"data": [], "has_more": False}])
        monkeypatch.setattr(helper, "requests", session)
        records = collector(helper, endpoint_type).collect(
            logger=types.SimpleNamespace(
                info=lambda *a, **k: None,
                warning=lambda *a, **k: None,
                error=lambda *a, **k: None,
            ),
            headers={},
            start_time=1730419200,
            end_time=1730505600,
            proxies=None,
            **kwargs,
        )
        return session.calls[0]["params"], records

    return _run


def test_models_are_sent_as_a_query_param(run):
    params, _ = run("completions", model_filter=["gpt-4o", "o3"])
    assert params["models"] == ["gpt-4o", "o3"]


def test_no_models_param_when_unfiltered(run):
    params, _ = run("completions", model_filter=None)
    assert "models" not in params


def test_endpoints_without_a_models_param_never_send_one(run):
    for endpoint_type in ("code_interpreter", "vector_stores", "file_search", "costs"):
        params, _ = run(endpoint_type, model_filter=["gpt-4o"])
        assert "models" not in params, endpoint_type


def test_records_are_not_discarded_client_side(run):
    """The API already applied the filter; dropping rows here loses real usage."""
    page = {
        "data": [
            {
                "start_time": 1730419200,
                "results": [
                    {
                        "object": "organization.usage.completions.result",
                        "input_tokens": 100,
                        "output_tokens": 50,
                        "num_model_requests": 1,
                        "model": "a-model-this-addon-has-never-heard-of",
                    }
                ],
            }
        ],
        "has_more": False,
    }
    _, records = run("completions", pages=[page], model_filter=["gpt-4o"])
    assert len(records) == 1
    assert records[0]["model"] == "a-model-this-addon-has-never-heard-of"
