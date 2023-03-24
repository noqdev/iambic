from __future__ import annotations

from iambic.core.template_generation import merge_model
from iambic.plugins.v0_1_0.aws.iam.role.models import AwsIamRoleTemplate, RoleProperties
from iambic.plugins.v0_1_0.aws.models import AWSAccount, Description


def test_merge_role_template_without_sid(aws_accounts: list[AWSAccount]):
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
    existing_document = AwsIamRoleTemplate(
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
    new_document = AwsIamRoleTemplate(
        identifier="{{account_name}}_iambic_test_role",
        file_path="foo",
        properties=new_properties,
    )
    merged_document: AwsIamRoleTemplate = merge_model(
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


def test_merge_role_template_access_rules(aws_accounts: list[AWSAccount]):
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
    existing_document = AwsIamRoleTemplate(
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
    new_document = AwsIamRoleTemplate(
        identifier="{{account_name}}_iambic_test_role",
        file_path="foo",
        properties=new_properties,
        access_rules=new_access_rules,
    )
    merged_document: AwsIamRoleTemplate = merge_model(
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


def test_merge_role_with_forked_policy(aws_accounts: list[AWSAccount]):
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
    existing_document = AwsIamRoleTemplate(
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
    new_document = AwsIamRoleTemplate(
        identifier="{{account_name}}_iambic_test_role",
        file_path="foo",
        properties=new_properties,
    )
    merged_document: AwsIamRoleTemplate = merge_model(
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


def test_merge_role_with_access_preservation(aws_accounts: list[AWSAccount]):
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
    existing_document = AwsIamRoleTemplate(
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

    new_document = AwsIamRoleTemplate(
        identifier="{{account_name}}_iambic_test_role",
        file_path="foo",
        properties=new_properties,
    )
    merged_document: AwsIamRoleTemplate = merge_model(
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


def test_merge_role_with_assignment_resolution(aws_accounts: list[AWSAccount]):
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
    existing_document = AwsIamRoleTemplate(
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
    new_document = AwsIamRoleTemplate(
        identifier="{{account_name}}_iambic_test_role",
        file_path="foo",
        properties=new_properties,
    )
    merged_document: AwsIamRoleTemplate = merge_model(
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


def test_merge_role_with_new_excluded_account(aws_accounts: list[AWSAccount]):
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
    existing_document = AwsIamRoleTemplate(
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
    new_document = AwsIamRoleTemplate(
        identifier="{{account_name}}_iambic_test_role",
        file_path="foo",
        properties=new_properties,
    )
    merged_document: AwsIamRoleTemplate = merge_model(
        new_document, existing_document, aws_accounts
    )

    assert len(merged_document.properties.inline_policies) == 1
    inline_policy = merged_document.properties.inline_policies[0]
    assert inline_policy.included_accounts == ["prod*"]
    assert inline_policy.excluded_accounts == [removed_account]


def test_merge_role_with_multiple_access_removals(aws_accounts: list[AWSAccount]):
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
    existing_document = AwsIamRoleTemplate(
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
    new_document = AwsIamRoleTemplate(
        identifier="{{account_name}}_iambic_test_role",
        file_path="foo",
        properties=new_properties,
    )
    merged_document: AwsIamRoleTemplate = merge_model(
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


def test_role_properties_tags():

    tags_1 = [
        {"key": "apple", "value": "red", "included_accounts": ["ses"]},
        {"key": "apple", "value": "yellow", "included_accounts": ["development"]},
    ]
    tags_2 = list(reversed(tags_1))
    assert tags_1 != tags_2
    properties_1 = RoleProperties(role_name="foo", tags=tags_1)
    properties_2 = RoleProperties(role_name="foo", tags=tags_2)
    assert properties_1.tags == properties_2.tags


def test_role_properties_validation():

    tags_1 = [
        {"key": "apple", "value": "red", "included_accounts": ["ses"]},
        {"key": "apple", "value": "yellow", "included_accounts": ["development"]},
    ]
    properties_1 = RoleProperties(role_name="foo", tags=tags_1)
    tag_models_1 = properties_1.tags
    tag_models_2 = list(reversed(properties_1.tags))
    assert tag_models_1 != tag_models_2  # because we reverse the list
    properties_1.tags = tag_models_2
    assert (
        properties_1.tags == tag_models_2
    )  # double check the list is reversed because validation doesn't happen after creation
    properties_1.validate_model_afterward()
    assert properties_1.tags == tag_models_1


def test_role_max_session_duration_validation():

    max_session_duration = [
        {"included_accounts": ["account_1", "account_2"], "max_session_duration": 3600},
        {"included_accounts": ["account_3"], "max_session_duration": 600},
    ]
    properties_1 = RoleProperties(
        role_name="foo", max_session_duration=max_session_duration
    )
    max_session_duration_models_1 = properties_1.max_session_duration
    max_session_duration_models_2 = list(reversed(properties_1.max_session_duration))
    assert (
        max_session_duration_models_1 != max_session_duration_models_2
    )  # because we reverse the list
    properties_1.max_session_duration = max_session_duration_models_2
    assert (
        properties_1.max_session_duration == max_session_duration_models_2
    )  # double check the list is reversed because validation doesn't happen after creation
    properties_1.validate_model_afterward()
    assert properties_1.max_session_duration == max_session_duration_models_1


def test_role_permissions_boundary_validation():

    permissions_boundary = [
        {
            "included_accounts": ["account_1", "account_2"],
            "policy_arn": "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy",
        },
        {
            "included_accounts": ["account_3"],
            "policy_arn": "arn:aws:iam::aws:policy/AmazonEKSServicePolicy",
        },
    ]
    properties_1 = RoleProperties(
        role_name="foo", permissions_boundary=permissions_boundary
    )
    permissions_boundary_models_1 = properties_1.permissions_boundary
    permissions_boundary_models_2 = list(reversed(properties_1.permissions_boundary))
    assert (
        permissions_boundary_models_1 != permissions_boundary_models_2
    )  # because we reverse the list
    properties_1.permissions_boundary = permissions_boundary_models_2
    assert (
        properties_1.permissions_boundary == permissions_boundary_models_2
    )  # double check the list is reversed because validation doesn't happen after creation
    properties_1.validate_model_afterward()
    assert properties_1.permissions_boundary == permissions_boundary_models_1


def test_role_path_validation():

    path = [
        {"included_accounts": ["account_1", "account_2"], "file_path": "/engineering"},
        {"included_accounts": ["account_3"], "file_path": "/finance"},
    ]
    properties_1 = RoleProperties(role_name="foo", path=path)
    path_1 = properties_1.path
    path_2 = list(reversed(properties_1.path))
    assert path_1 != path_2  # because we reverse the list
    properties_1.path = path_2
    assert (
        properties_1.path == path_2
    )  # double check the list is reversed because validation doesn't happen after creation
    properties_1.validate_model_afterward()
    assert properties_1.path == path_1


def test_description_path_validation():

    description = [
        {"included_accounts": ["account_1", "account_2"], "description": "foo"},
        {"included_accounts": ["account_3"], "description": "bar"},
    ]
    properties_1 = RoleProperties(role_name="foo", description=description)
    description_1 = properties_1.description
    description_2 = list(reversed(properties_1.description))
    assert description_1 != description_2  # because we reverse the list
    properties_1.description = description_2
    assert (
        properties_1.description == description_2
    )  # double check the list is reversed because validation doesn't happen after creation
    properties_1.validate_model_afterward()
    assert properties_1.description == description_1


def test_access_rule_validation():

    access_rules = [
        {"included_accounts": ["account_1", "account_2"], "users": ["foo"]},
        {"included_accounts": ["account_3"], "users": ["bar"]},
    ]
    properties_1 = RoleProperties(role_name="foo")
    template_1 = AwsIamRoleTemplate(
        file_path="foo",
        identifier="foo",
        properties=properties_1,
        access_rules=access_rules,
    )
    access_rules_1 = template_1.access_rules
    access_rules_2 = list(reversed(template_1.access_rules))
    assert access_rules_1 != access_rules_2  # because we reverse the list
    template_1.access_rules = access_rules_2
    assert (
        template_1.access_rules == access_rules_2
    )  # double check the list is reversed because validation doesn't happen after creation
    template_1.validate_model_afterward()
    assert template_1.access_rules == access_rules_1


def test_mixed_type_description_merges():
    existing_description = [Description(description="foo")]
    existing_properties = RoleProperties(
        role_name="foo", description=existing_description
    )
    new_description = "foo"  # intend to be mixed types because the RoleProperties::Description allow mixed types
    new_properties = RoleProperties(role_name="foo", description=new_description)
    merged_model = merge_model(new_properties, existing_properties, [])
    assert merged_model.description[0].description == "foo"
