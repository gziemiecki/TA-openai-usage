"""
format_record() must read the field names the API actually returns.

Every ``record`` below is shaped from the matching ``Usage*Result`` schema in
openai/openai-openapi.  The previous implementation invented names
(``num_images``, ``input_seconds``, ``num_characters``, ``num_queries``,
``context_tokens``) that appear nowhere in the spec, so every one of these
metrics silently indexed as 0.
"""

import pytest


def collector(helper, endpoint_type):
    for c in helper.COLLECTOR_REGISTRY:
        if c.endpoint_type == endpoint_type:
            return c
    raise AssertionError(f"no collector for {endpoint_type}")


def test_images_reads_the_images_count(helper):
    record = {
        "object": "organization.usage.images.result",
        "images": 2,
        "num_model_requests": 2,
        "source": "image.generation",
        "size": "1024x1024",
        "model": "gpt-image-1",
        "start_time": 1730419200,
    }
    event = collector(helper, "images").format_record(record)
    assert event["num_images"] == 2
    assert event["size"] == "1024x1024"
    assert event["source"] == "image.generation"


def test_audio_transcription_reads_seconds(helper):
    record = {
        "object": "organization.usage.audio_transcriptions.result",
        "seconds": 90,
        "num_model_requests": 3,
        "model": "whisper-1",
        "start_time": 1730419200,
    }
    event = collector(helper, "audio_transcription").format_record(record)
    assert event["input_seconds"] == 90


def test_audio_transcription_keeps_non_whisper_models(helper):
    """gpt-4o-transcribe bills as transcription but is not named 'whisper'."""
    record = {
        "object": "organization.usage.audio_transcriptions.result",
        "seconds": 42,
        "num_model_requests": 1,
        "model": "gpt-4o-transcribe",
        "start_time": 1730419200,
    }
    event = collector(helper, "audio_transcription").format_record(record)
    assert event is not None
    assert event["input_seconds"] == 42


def test_audio_speech_reads_characters(helper):
    record = {
        "object": "organization.usage.audio_speeches.result",
        "characters": 1450,
        "num_model_requests": 2,
        "model": "gpt-4o-mini-tts",
        "start_time": 1730419200,
    }
    event = collector(helper, "audio_speech").format_record(record)
    assert event is not None
    assert event["num_characters"] == 1450


def test_web_search_reads_request_counts_and_context_level(helper):
    record = {
        "object": "organization.usage.web_search_calls.result",
        "num_requests": 12,
        "num_model_requests": 12,
        "context_level": "medium",
        "model": "gpt-4o",
        "start_time": 1730419200,
    }
    event = collector(helper, "web_search").format_record(record)
    assert event["num_requests"] == 12
    assert event["num_model_requests"] == 12
    assert event["context_level"] == "medium"


def test_vector_stores_reads_usage_bytes(helper):
    record = {
        "object": "organization.usage.vector_stores.result",
        "usage_bytes": 1073741824,
        "project_id": "proj_abc",
        "start_time": 1730419200,
    }
    event = collector(helper, "vector_stores").format_record(record)
    assert event["bytes_stored"] == 1073741824


@pytest.mark.parametrize("endpoint_type", ["completions", "embeddings", "images"])
def test_attribution_ids_are_carried_through(helper, endpoint_type):
    record = {
        "input_tokens": 10,
        "images": 1,
        "num_model_requests": 1,
        "project_id": "proj_abc",
        "user_id": "user-123",
        "api_key_id": "key_abc",
        "model": "gpt-4o",
        "start_time": 1730419200,
    }
    event = collector(helper, endpoint_type).format_record(record)
    assert event["project_id"] == "proj_abc"
    assert event["user_id"] == "user-123"
    assert event["api_key_id"] == "key_abc"
