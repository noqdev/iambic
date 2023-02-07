from __future__ import annotations

from iambic.aws.iam.role.models import RoleTemplate
from iambic.core.models import merge_model


def test_merge_role_template_without_sid(aws_accounts):
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
    merged_document: RoleTemplate = merge_model(
        new_document, existing_document, aws_accounts
    )
    assert (
        existing_properties["inline_policies"][0]["statement"][0]
        != new_properties["inline_policies"][0]["statement"][0]
    )
    assert (
        merged_document.properties.inline_policies[0].statement[0].expires_at
        == existing_document.properties.inline_policies[0].statement[0].expires_at
    )


def test_merge_role_template_access_rules(aws_accounts):
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
    merged_document: RoleTemplate = merge_model(
        new_document, existing_document, aws_accounts
    )
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


def test_merge_role_with_forked_policy(aws_accounts):
    prod_accounts = [
        account.account_name
        for account in aws_accounts
        if "prod" in account.account_name
    ]
    non_prod_accounts = [
        account.account_name
        for account in aws_accounts
        if "prod" not in account.account_name
    ]
    existing_properties = {
        "role_name": "bar",
        "inline_policies": [
            {
                "policy_name": "s3-policy",
                "included_accounts": ["prod*"],
                "statement": [
                    {
                        "effect": "Allow",
                        "expires_at": "2023-01-24",
                        "action": ["s3:*"],
                        "resource": "*",
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
                "policy_name": "s3-policy",
                "included_accounts": prod_accounts,
                "statement": [
                    {
                        "effect": "Allow",
                        "expires_at": "2023-01-24",
                        "action": ["s3:*"],
                        "resource": "*",
                    }
                ],
            },
            {
                "policy_name": "s3-policy",
                "included_accounts": non_prod_accounts,
                "statement": [
                    {
                        "effect": "Allow",
                        "action": ["s3:*"],
                        "resource": "*",
                    }
                ],
            },
        ],
    }
    new_document = RoleTemplate(
        identifier="{{account_name}}_iambic_test_role",
        file_path="foo",
        properties=new_properties,
    )
    merged_document: RoleTemplate = merge_model(
        new_document, existing_document, aws_accounts
    )
    assert len(merged_document.properties.inline_policies) == 2

    for inline_policy in merged_document.properties.inline_policies:
        if inline_policy.included_accounts == ["prod*"]:
            assert (
                inline_policy.statement[0].expires_at
                == existing_document.properties.inline_policies[0]
                .statement[0]
                .expires_at
            )
        else:
            assert sorted(inline_policy.included_accounts) == sorted(non_prod_accounts)


def test_merge_role_with_access_preservation(aws_accounts):
    prod_accounts = [
        account.account_name
        for account in aws_accounts
        if "prod" in account.account_name
    ]
    non_prod_accounts = [
        account.account_name
        for account in aws_accounts
        if "prod" not in account.account_name
    ]
    existing_properties = {
        "role_name": "bar",
        "inline_policies": [
            {
                "policy_name": "s3-policy",
                "included_accounts": ["prod*"],
                "statement": [
                    {
                        "effect": "Allow",
                        "expires_at": "2023-01-24",
                        "action": ["s3:*"],
                        "resource": "*",
                    }
                ],
            },
            {
                "policy_name": "s3-policy",
                "excluded_accounts": ["prod*"],
                "statement": [
                    {
                        "effect": "Allow",
                        "expires_at": "2023-01-24",
                        "action": ["s3:*"],
                        "resource": "*",
                    }
                ],
            },
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
                "policy_name": "s3-policy",
                "included_accounts": prod_accounts,
                "statement": [
                    {
                        "effect": "Allow",
                        "expires_at": "2023-01-24",
                        "action": ["s3:*"],
                        "resource": "*",
                    }
                ],
            },
            {
                "policy_name": "s3-policy",
                "included_accounts": non_prod_accounts,
                "statement": [
                    {
                        "effect": "Allow",
                        "action": ["s3:*"],
                        "resource": "*",
                    }
                ],
            },
        ],
    }
    new_document = RoleTemplate(
        identifier="{{account_name}}_iambic_test_role",
        file_path="foo",
        properties=new_properties,
    )
    merged_document: RoleTemplate = merge_model(
        new_document, existing_document, aws_accounts
    )

    assert len(merged_document.properties.inline_policies) == 2

    for inline_policy in merged_document.properties.inline_policies:
        if inline_policy.included_accounts == ["prod*"]:
            assert (
                inline_policy.statement[0].expires_at
                == existing_document.properties.inline_policies[0]
                .statement[0]
                .expires_at
            )
        else:
            assert inline_policy.included_accounts == ["*"]
            assert inline_policy.excluded_accounts == ["prod*"]
            assert (
                inline_policy.statement[0].expires_at
                == existing_document.properties.inline_policies[1]
                .statement[0]
                .expires_at
            )


"""
Test to add one off included account

Test to remove one off included account

Test to capture this scenario:
    An account named dev_account_new (matching both * and dev_*) is updated.
    Now the resource no longer contains the inline policy s3-policy
    On the first element in inline_policies add the account to excluded_accounts
    On the second element in inline_policies add the account to excluded_accounts

Test to add a 3rd variant of the same policy name

Add some documentation
"""
