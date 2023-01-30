from __future__ import annotations

from iambic.aws.identity_center.permission_set.models import (
    AWSIdentityCenterPermissionSetTemplate,
)
from iambic.core.models import merge_model


def test_merge_template_access_rules():
    existing_properties = {
        "name": "bar",
    }
    existing_access_rules = [
        {
            "users": [
                "user@example.com",
            ],
            "expires_at": "in 3 days",
        }
    ]
    existing_document = AWSIdentityCenterPermissionSetTemplate(
        identifier="bar",
        file_path="foo",
        properties=existing_properties,
        access_rules=existing_access_rules,
    )
    new_properties = {
        "name": "bar",
    }
    new_access_rules = [
        {
            "users": [
                "user@example.com",
            ],
        }
    ]
    new_document = AWSIdentityCenterPermissionSetTemplate(
        identifier="bar",
        file_path="foo",
        properties=new_properties,
        access_rules=new_access_rules,
    )
    merged_document: AWSIdentityCenterPermissionSetTemplate = merge_model(
        existing_document, new_document
    )
    assert existing_access_rules != new_access_rules
    assert merged_document.access_rules == existing_document.access_rules
