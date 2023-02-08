from __future__ import annotations

from iambic.aws.iam.role.models import RoleTemplate
from iambic.core.template_generation import merge_model


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
                "expires_at": "2023-01-24",
                "statement": [
                    {
                        "effect": "Allow",
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
                "expires_at": "2023-01-24",
                "statement": [
                    {
                        "effect": "Allow",
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

    for inline_policy in existing_document.properties.inline_policies:
        if inline_policy.included_accounts == ["prod*"]:
            prod_expires_at = inline_policy.expires_at
        else:
            non_prod_expires_at = inline_policy.expires_at

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
            assert inline_policy.expires_at == prod_expires_at
        else:
            assert inline_policy.included_accounts == ["*"]
            assert inline_policy.excluded_accounts == ["prod*"]
            assert inline_policy.expires_at == non_prod_expires_at


def test_merge_role_with_assignment_resolution(aws_accounts):
    account_names = [account.account_name for account in aws_accounts]
    non_prod_accounts = [
        account_name for account_name in account_names if "prod" not in account_name
    ]
    existing_properties = {
        "role_name": "bar",
        "inline_policies": [
            {
                "policy_name": "test_merge_role_with_assignment_resolution",
                "included_accounts": ["prod*"],
                "statement": [
                    {
                        "effect": "Allow",
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
                "policy_name": "test_merge_role_with_assignment_resolution",
                "included_accounts": account_names,
                "statement": [
                    {
                        "effect": "Allow",
                        "action": ["s3:*"],
                        "resource": "*",
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

    assert len(merged_document.properties.inline_policies) == 1
    inline_policy = merged_document.properties.inline_policies[0]
    included_accounts = [
        account_name
        for account_name in inline_policy.included_accounts
        if "*" not in account_name
    ]
    assert sorted(included_accounts) == sorted(non_prod_accounts)
    assert "prod*" in inline_policy.included_accounts


def test_merge_role_with_new_excluded_account(aws_accounts):
    prod_accounts = [
        account.account_name
        for account in aws_accounts
        if "prod" in account.account_name
    ]
    removed_account = prod_accounts.pop()
    existing_properties = {
        "role_name": "bar",
        "inline_policies": [
            {
                "policy_name": "test_merge_role_with_new_excluded_account",
                "included_accounts": ["prod*"],
                "statement": [
                    {
                        "effect": "Allow",
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
                "policy_name": "test_merge_role_with_new_excluded_account",
                "included_accounts": prod_accounts,
                "statement": [
                    {
                        "effect": "Allow",
                        "action": ["s3:*"],
                        "resource": "*",
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

    assert len(merged_document.properties.inline_policies) == 1
    inline_policy = merged_document.properties.inline_policies[0]
    assert inline_policy.included_accounts == ["prod*"]
    assert inline_policy.excluded_accounts == [removed_account]


def test_merge_role_with_multiple_access_removals(aws_accounts):
    all_accounts = [account.account_name for account in aws_accounts]
    dev_accounts = [account for account in all_accounts if "dev" in account]
    non_dev_accounts = [account for account in all_accounts if "dev" not in account]
    removed_account = dev_accounts.pop()
    dev_statement = [
        {
            "effect": "Allow",
            "action": ["s3:*"],
            "resource": "*",
        }
    ]
    non_dev_statement = [
        {
            "effect": "Allow",
            "action": [
                "s3:list*",
                "s3:get*",
            ],
            "resource": "*",
        }
    ]

    existing_properties = {
        "role_name": "bar",
        "inline_policies": [
            {
                "policy_name": "test_merge_role_with_multiple_access_removals",
                "included_accounts": ["*"],
                "statement": non_dev_statement,
            },
            {
                "policy_name": "test_merge_role_with_multiple_access_removals",
                "included_accounts": ["dev*"],
                "statement": dev_statement,
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
                "policy_name": "test_merge_role_with_multiple_access_removals",
                "included_accounts": non_dev_accounts,
                "statement": non_dev_statement,
            },
            {
                "policy_name": "test_merge_role_with_multiple_access_removals",
                "included_accounts": dev_accounts,
                "statement": dev_statement,
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
        if inline_policy.included_accounts == ["*"]:
            assert sorted(inline_policy.excluded_accounts) == sorted(
                dev_accounts + [removed_account]
            )
            assert bool(
                sorted(inline_policy.statement[0].action)
                == sorted(non_dev_statement[0]["action"])
            )
        else:
            assert inline_policy.included_accounts == ["dev*"]
            assert inline_policy.excluded_accounts == [removed_account]
            assert bool(
                sorted(inline_policy.statement[0].action)
                == sorted(dev_statement[0]["action"])
            )
