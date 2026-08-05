"""
The attribution dimensions are an input setting, so the string that arrives
from the Splunk config has to be parsed and validated before it reaches the
API as a ``group_by`` param.
"""

import pytest


def test_parses_a_comma_separated_list(helper):
    assert helper.parse_group_by("project_id, api_key_id") == ["project_id", "api_key_id"]


def test_empty_config_means_no_extra_grouping(helper):
    assert helper.parse_group_by("") == []
    assert helper.parse_group_by(None) == []


def test_unknown_dimensions_are_rejected(helper):
    """A typo must not turn every request into a 400."""
    assert helper.parse_group_by("project_id,department") == ["project_id"]


def test_duplicates_collapse(helper):
    assert helper.parse_group_by("user_id,user_id") == ["user_id"]


def test_model_is_not_an_attribution_dimension(helper):
    """Collectors already group by model where the endpoint supports it."""
    assert helper.parse_group_by("model,project_id") == ["project_id"]
