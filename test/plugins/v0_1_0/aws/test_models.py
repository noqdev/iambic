from __future__ import annotations

import pytest
from pydantic import ValidationError

from iambic.plugins.v0_1_0.aws.models import Tag


def test_valid_tag():
    tag = Tag(key="a", value="")
    assert tag


def test_invalid_tag_key():
    with pytest.raises(ValidationError):
        Tag(key="*", value="")


def test_invalid_tag_with_empty_string():
    with pytest.raises(ValidationError):
        Tag(key="", value="")


def test_invalid_tag_with_key_too_long():
    with pytest.raises(ValidationError):
        Tag(key="a" * 129, value="")


def test_valid_tag_with_max_key_length():
    assert Tag(key="a" * 128, value="")


def test_invalid_tag_value():
    with pytest.raises(ValidationError):
        Tag(key="a", value="*")


def test_valid_tag_value_with_empty_string():
    assert Tag(key="a", value="")


def test_invalid_tag_with_value_too_long():
    with pytest.raises(ValidationError):
        Tag(key="a", value="a" * 257)


def test_valid_tag_with_max_value_length():
    assert Tag(key="a", value="a" * 256)


def test_variable_on_tag_key():
    assert Tag(key="{{var.account_name}}", value="")
