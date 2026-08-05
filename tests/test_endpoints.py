"""
Each collector must target a path that actually exists on the OpenAI
Organization Usage API.

The expected paths below are copied from openai/openai-openapi
(``paths:`` entries beginning ``/organization/usage``).  There is no
fine-tuning usage endpoint, so no collector may claim one.
"""

REAL_USAGE_PATHS = {
    "https://api.openai.com/v1/organization/usage/audio_speeches",
    "https://api.openai.com/v1/organization/usage/audio_transcriptions",
    "https://api.openai.com/v1/organization/usage/code_interpreter_sessions",
    "https://api.openai.com/v1/organization/usage/completions",
    "https://api.openai.com/v1/organization/usage/embeddings",
    "https://api.openai.com/v1/organization/usage/file_search_calls",
    "https://api.openai.com/v1/organization/usage/images",
    "https://api.openai.com/v1/organization/usage/moderations",
    "https://api.openai.com/v1/organization/usage/vector_stores",
    "https://api.openai.com/v1/organization/usage/web_search_calls",
}


COSTS_PATH = "https://api.openai.com/v1/organization/costs"


def test_every_collector_targets_a_real_endpoint(helper):
    known = REAL_USAGE_PATHS | {COSTS_PATH}
    bad = {
        c.endpoint_type: c.url
        for c in helper.COLLECTOR_REGISTRY
        if c.url not in known
    }
    assert bad == {}


def test_all_billable_usage_endpoints_are_collected(helper):
    covered = {c.url for c in helper.COLLECTOR_REGISTRY}
    assert REAL_USAGE_PATHS - covered == set()


def test_audio_speech_and_transcription_use_separate_endpoints(helper):
    by_type = {c.endpoint_type: c.url for c in helper.COLLECTOR_REGISTRY}
    assert by_type["audio_speech"].endswith("/audio_speeches")
    assert by_type["audio_transcription"].endswith("/audio_transcriptions")
    assert by_type["audio_speech"] != by_type["audio_transcription"]
