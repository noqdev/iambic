from __future__ import annotations

import sys
import traceback

import pytest
from pydantic import ValidationError

from iambic.plugins.v0_1_0.aws.identity_center.permission_set.models import (
    AWSIdentityCenterPermissionSetProperties,
)
from iambic.plugins.v0_1_0.aws.models import Description


def test_description_validation_with_default_being_none():
    properties = AWSIdentityCenterPermissionSetProperties(name="foo")
    assert properties.description is None


def test_description_validation_with_empty_string():
    with pytest.raises(ValidationError) as exc_info:
        AWSIdentityCenterPermissionSetProperties(name="foo", description="")
    if sys.version_info < (3, 10):
        exc = exc_info.value
        captured_traceback_lines = traceback.format_exception(
            type(exc), exc, exc.__traceback__
        )
    else:
        captured_traceback_lines = traceback.format_exception(
            exc_info.value
        )  # this is a pytest specific format
    captured_traceback = "\n".join(captured_traceback_lines)

    assert "description must be between 1 and 700 characters" in captured_traceback


def test_description_validation_with_valid_string():
    properties = AWSIdentityCenterPermissionSetProperties(name="foo", description="A")
    assert properties.description == "A"


def test_description_validation_with_valid_list():
    properties = AWSIdentityCenterPermissionSetProperties(
        name="foo", description=[Description(description="A")]
    )
    assert properties.description[0].description == "A"


def test_description_validation_with_list_with_empty_string():
    with pytest.raises(ValidationError) as exc_info:
        AWSIdentityCenterPermissionSetProperties(
            name="foo", description=[Description(description="")]
        )
    if sys.version_info < (3, 10):
        exc = exc_info.value
        captured_traceback_lines = traceback.format_exception(
            type(exc), exc, exc.__traceback__
        )
    else:
        captured_traceback_lines = traceback.format_exception(
            exc_info.value
        )  # this is a pytest specific format
    captured_traceback = "\n".join(captured_traceback_lines)
    assert "description must be between 1 and 700 characters" in captured_traceback
