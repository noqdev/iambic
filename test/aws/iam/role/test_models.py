from __future__ import annotations

from iambic.aws.iam.role.models import RoleTemplate
from iambic.core.models import merge_model


def test_merge_role_template_without_sid():
    existing_properties = {
        "role_name": "bar",
        "inline_policies": [
            {
                "policy_name": "spoke-acct-policy",
                "statement": [
                    {
                        "effect": "Allow",
                        "expires_at": "2023-01-24",
                    }
                ],
            }
        ],
    }
    existing_document = RoleTemplate(
        identifier="{{account_name}}_iambic_test_role",
        file_path="foo",
        properties=existing_properties,
    )
    new_properties = {
        "role_name": "bar",
        "inline_policies": [
            {
                "policy_name": "spoke-acct-policy",
                "statement": [
                    {
                        "effect": "Allow",
                    }
                ],
            }
        ],
    }
    new_document = RoleTemplate(
        identifier="{{account_name}}_iambic_test_role",
        file_path="foo",
        properties=new_properties,
    )
    merged_document: RoleTemplate = merge_model(existing_document, new_document)
    assert (
        existing_properties["inline_policies"][0]["statement"][0]
        != new_properties["inline_policies"][0]["statement"][0]
    )
    assert (
        merged_document.properties.inline_policies[0].statement[0].expires_at
        == existing_document.properties.inline_policies[0].statement[0].expires_at
    )


def test_merge_role_template_access_rules():
    existing_properties = {
        "role_name": "bar",
        "inline_policies": [
            {
                "policy_name": "spoke-acct-policy",
                "statement": [
                    {
                        "effect": "Allow",
                        "expires_at": "2023-01-24",
                    }
                ],
            }
        ],
    }
    existing_access_rules = [
        {
            "users": [
                "user@example.com",
            ],
            "expires_at": "in 3 days",
        }
    ]
    existing_document = RoleTemplate(
        identifier="{{account_name}}_iambic_test_role",
        file_path="foo",
        properties=existing_properties,
        access_rules=existing_access_rules,
    )
    new_properties = {
        "role_name": "bar",
        "inline_policies": [
            {
                "policy_name": "spoke-acct-policy",
                "statement": [
                    {
                        "effect": "Allow",
                    }
                ],
            }
        ],
    }
    new_access_rules = [
        {
            "users": [
                "user@example.com",
            ],
        }
    ]
    new_document = RoleTemplate(
        identifier="{{account_name}}_iambic_test_role",
        file_path="foo",
        properties=new_properties,
        access_rules=new_access_rules,
    )
    merged_document: RoleTemplate = merge_model(existing_document, new_document)
    assert (
        existing_properties["inline_policies"][0]["statement"][0]
        != new_properties["inline_policies"][0]["statement"][0]
    )
    assert existing_access_rules != new_access_rules
    assert (
        merged_document.properties.inline_policies[0].statement[0].expires_at
        == existing_document.properties.inline_policies[0].statement[0].expires_at
    )
    assert merged_document.access_rules == existing_document.access_rules
