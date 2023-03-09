from __future__ import annotations

from datetime import date, datetime, timezone

import pytz

from iambic.core.iambic_enum import IambicManaged
from iambic.core.models import BaseTemplate, ExpiryModel
from iambic.core.template_generation import merge_model


def test_merge_model():
    existing_template = BaseTemplate(
        template_type="foo", file_path="bar", iambic_managed=IambicManaged.IMPORT_ONLY
    )
    new_template = BaseTemplate(
        template_type="foo_new",
        file_path="bar_new",
        iambic_managed=IambicManaged.UNDEFINED,
    )
    merged_template = merge_model(new_template, existing_template, [])
    assert merged_template.template_type == new_template.template_type
    assert merged_template.iambic_managed == IambicManaged.IMPORT_ONLY
    assert merged_template.file_path == existing_template.file_path


def test_merge_model_with_none():
    existing_template = BaseTemplate(
        template_type="foo", file_path="bar", iambic_managed=IambicManaged.IMPORT_ONLY
    )
    new_template = None
    merged_template = merge_model(new_template, existing_template, [])
    assert merged_template is None


def test_expiry_model_to_json_with_datetime():
    expiry_date = datetime(2023, 3, 7, 12, 30, 0, tzinfo=timezone.utc)
    model = ExpiryModel(expires_at=expiry_date, deleted=True)
    expected_json = '{"expires_at": "2023-03-07T12:30 UTC", "deleted": true}'
    assert (
        model.json(exclude_unset=True, exclude_defaults=True, exclude_none=True)
        == expected_json
    )


def test_expiry_model_to_json_with_date():
    expiry_date = date(2023, 3, 7)
    model = ExpiryModel(expires_at=expiry_date, deleted=False)
    expected_json = '{"expires_at": "2023-03-07T00:00 UTC"}'
    assert (
        model.json(exclude_unset=True, exclude_defaults=True, exclude_none=True)
        == expected_json
    )


def test_expiry_model_to_json_with_str():
    expiry_date = "2023-03-07T12:30:00Z"
    model = ExpiryModel(expires_at=expiry_date, deleted=False)
    expected_json = '{"expires_at": "2023-03-07T12:30 UTC"}'
    assert (
        model.json(exclude_unset=True, exclude_defaults=True, exclude_none=True)
        == expected_json
    )


def test_expiry_model_to_json_with_null():
    model = ExpiryModel(expires_at=None, deleted=False)
    expected_json = "{}"
    assert (
        model.json(exclude_unset=True, exclude_defaults=True, exclude_none=True)
        == expected_json
    )


def test_expiry_model_from_json_with_datetime():
    json_str = '{"expires_at": "2023-03-07T12:30 UTC", "deleted": true}'
    expected_expiry_date = datetime(2023, 3, 7, 12, 30, 0, tzinfo=pytz.utc)
    expected_model = ExpiryModel(expires_at=expected_expiry_date, deleted=True)
    actual_model = ExpiryModel.parse_raw(json_str)
    assert actual_model == expected_model


def test_expiry_model_from_json_with_date():
    json_str = '{"expires_at": "2023-03-07T00:00 UTC"}'
    expected_expiry_date = date(2023, 3, 7)
    expected_model = ExpiryModel(expires_at=expected_expiry_date, deleted=False)
    actual_model = ExpiryModel.parse_raw(json_str)
    assert actual_model == expected_model


def test_expiry_model_from_json_with_str():
    json_str = '{"expires_at": "2023-03-07T12:30 UTC"}'
    expected_expiry_date = "2023-03-07T12:30:00Z"
    expected_model = ExpiryModel(expires_at=expected_expiry_date, deleted=False)
    actual_model = ExpiryModel.parse_raw(json_str)
    assert actual_model == expected_model


def test_expiry_model_from_json_with_null():
    json_str = '{"expires_at": null, "deleted": false}'
    expected_model = ExpiryModel(expires_at=None, deleted=False)
    actual_model = ExpiryModel.parse_raw(json_str)
    assert actual_model == expected_model
