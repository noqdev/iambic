from __future__ import annotations

import copy
from unittest.mock import AsyncMock, patch

import pytest

from iambic.core.iambic_enum import IambicManaged
from iambic.core.template_generation import merge_model
from iambic.plugins.v0_1_0.aws.iam.role.models import AwsIamRoleTemplate
from iambic.plugins.v0_1_0.aws.iam.role.template_generation import create_templated_role
from iambic.plugins.v0_1_0.aws.models import AWSAccount, Description


def get_aws_account_map(aws_accounts: list[AWSAccount]) -> dict[str, AWSAccount]:
    account_map = {}
    for account in aws_accounts:
        account_map[account.account_name] = account
        account_map[account.account_id] = account
    return account_map


@pytest.fixture
def test_role():
    test_role_name = "test_role"
    test_role = AwsIamRoleTemplate(
        identifier=test_role_name,
        included_accounts=["dev"],
        file_path="/tmp/test_role.yaml",
        properties={"role_name": test_role_name},
    )
    return test_role


@pytest.fixture
def test_account():
    return AWSAccount(account_id="123456789011", account_name="dev", assume_role_arn="")


@pytest.fixture
def test_account_2():
    return AWSAccount(
        account_id="123456789012", account_name="dev_2", assume_role_arn=""
    )


@pytest.fixture
def mock_account_id_to_role_map(test_role):
    with patch(
        "iambic.plugins.v0_1_0.aws.iam.role.template_generation._account_id_to_role_map"
    ) as _mock_account_id_to_role_map:
        async_mock = AsyncMock(return_value={"dev": test_role.properties.dict()})
        _mock_account_id_to_role_map.side_effect = async_mock
        yield _mock_account_id_to_role_map


@pytest.fixture
def mock_account_id_to_role_map_import(test_role):
    with patch(
        "iambic.plugins.v0_1_0.aws.iam.role.template_generation._account_id_to_role_map"
    ) as _mock_account_id_to_role_map:
        role_dict = test_role.properties.dict()
        role_dict["tags"] = [{"key": "terraform", "value": "true"}]

        async_mock = AsyncMock(return_value={"dev": role_dict})
        _mock_account_id_to_role_map.side_effect = async_mock
        yield _mock_account_id_to_role_map


@pytest.fixture
def mock_write():
    with patch("iambic.core.models.BaseTemplate.write") as _mock_write:
        yield _mock_write


@pytest.mark.asyncio
async def test_create_template_role(
    test_config, test_role, mock_account_id_to_role_map, mock_write
):
    test_role_name = "test_role"
    test_account_id = "123456789012"
    test_account = AWSAccount(
        account_id=test_account_id, account_name="dev", assume_role_arn=""
    )
    test_aws_account_map = get_aws_account_map([test_account])
    test_role_ref = test_role.properties.dict()
    test_role_ref["account_id"] = "123456789012"
    test_role_refs = [test_role_ref]
    test_existing_template_map = {}

    output_role = await create_templated_role(
        test_aws_account_map,
        test_role_name,
        test_role_refs,
        "",
        test_existing_template_map,
        test_config.aws,
    )
    assert output_role.iambic_managed is IambicManaged.UNDEFINED

    test_role.iambic_managed = IambicManaged.READ_AND_WRITE
    test_existing_template_map = {test_role_name: test_role}
    output_role = await create_templated_role(
        test_aws_account_map,
        "test_role",
        test_role_refs,
        "",
        test_existing_template_map,
        test_config.aws,
    )
    assert output_role.iambic_managed is IambicManaged.READ_AND_WRITE


@pytest.mark.asyncio
async def test_merge_template_role_with_explicit_exclude(
    test_config,
    test_role,
    test_account,
    test_account_2,
    mock_account_id_to_role_map,
    mock_write,
):
    test_aws_account_map = get_aws_account_map([test_account, test_account_2])
    test_role_ref = test_role.properties.dict()
    test_role_ref["account_id"] = test_account.account_id
    test_role_refs = [test_role_ref]
    test_existing_template_map = {}

    initial_role = await create_templated_role(
        test_aws_account_map,
        "test_role",
        test_role_refs,
        "",
        test_existing_template_map,
        test_config.aws,
    )
    initial_role.iambic_managed = IambicManaged.READ_AND_WRITE
    initial_role.included_accounts = [
        test_account.account_name,
        test_account_2.account_name,
    ]
    updated_role = await create_templated_role(
        test_aws_account_map,
        "test_role",
        test_role_refs,
        "",
        test_existing_template_map,
        test_config.aws,
    )
    updated_role.iambic_managed = IambicManaged.READ_AND_WRITE
    updated_role.included_accounts = [test_account.account_name]

    merged_model = merge_model(
        updated_role, initial_role, [test_account, test_account_2]
    )
    assert test_account_2.account_name not in merged_model.included_accounts
    assert test_account_2.account_name not in merged_model.excluded_accounts


@pytest.mark.asyncio
async def test_merge_template_role_with_wildcard_exclude(
    test_config,
    test_role,
    test_account,
    test_account_2,
    mock_account_id_to_role_map,
    mock_write,
):
    """
    Check that the wildcard for included account is preserved when merging
    Also confirm the now excluded account is explicitly added to excluded accounts
    """
    test_aws_account_map = get_aws_account_map([test_account, test_account_2])
    test_role_ref = test_role.properties.dict()
    test_role_ref["account_id"] = test_account.account_id
    test_role_refs = [test_role_ref]
    test_existing_template_map = {}

    initial_role = await create_templated_role(
        test_aws_account_map,
        "test_role",
        test_role_refs,
        "",
        test_existing_template_map,
        test_config.aws,
    )
    initial_role.iambic_managed = IambicManaged.READ_AND_WRITE
    initial_role.included_accounts = ["dev*"]
    updated_role = await create_templated_role(
        test_aws_account_map,
        "test_role",
        test_role_refs,
        "",
        test_existing_template_map,
        test_config.aws,
    )
    updated_role.iambic_managed = IambicManaged.READ_AND_WRITE
    updated_role.included_accounts = [test_account.account_name]

    merged_model = merge_model(
        updated_role, initial_role, [test_account, test_account_2]
    )
    assert merged_model.included_accounts == initial_role.included_accounts
    assert test_account_2.account_name in merged_model.excluded_accounts


@pytest.mark.asyncio
async def test_merge_template_role_with_wildcard_catch_include(
    test_config,
    test_role,
    test_account,
    test_account_2,
    mock_account_id_to_role_map,
    mock_write,
):
    """
    Check that an account that hits on a wildcard for included account is not explicitly added to included accounts
    """
    test_aws_account_map = get_aws_account_map([test_account, test_account_2])
    test_role_ref = test_role.properties.dict()
    test_role_ref["account_id"] = test_account.account_id
    test_role_refs = [test_role_ref]
    test_existing_template_map = {}

    initial_role = await create_templated_role(
        test_aws_account_map,
        "test_role",
        test_role_refs,
        "",
        test_existing_template_map,
        test_config.aws,
    )
    initial_role.iambic_managed = IambicManaged.READ_AND_WRITE
    initial_role.included_accounts = ["dev*"]
    updated_role = await create_templated_role(
        test_aws_account_map,
        "test_role",
        test_role_refs,
        "",
        test_existing_template_map,
        test_config.aws,
    )
    updated_role.iambic_managed = IambicManaged.READ_AND_WRITE
    updated_role.included_accounts = [
        test_account.account_name,
        test_account_2.account_name,
    ]

    merged_model = merge_model(
        updated_role, initial_role, [test_account, test_account_2]
    )
    assert merged_model.included_accounts == initial_role.included_accounts


@pytest.mark.asyncio
async def test_noop_merge_template_role_with_non_standard_account_name(
    test_config,
    test_role,
    test_account,
    test_account_2,
    mock_account_id_to_role_map,
    mock_write,
):
    """
    Check that an account that hits on a wildcard for included account is not explicitly added to included accounts
    """
    non_standard_account = AWSAccount(
        account_id="123456789013",
        account_name="@!#!@#)(%*#R)QWITFGO)FG+=0984",
        assume_role_arn="",
    )
    test_aws_account_map = get_aws_account_map(
        [test_account, test_account_2, non_standard_account]
    )
    test_role_ref = test_role.properties.dict()
    test_role_ref["account_id"] = test_account.account_id
    test_role_refs = [test_role_ref]
    test_existing_template_map = {}
    description = Description(
        description="test the weird account name",
        included_accounts=[non_standard_account.account_name],
    )
    initial_role = await create_templated_role(
        test_aws_account_map,
        "test_role",
        test_role_refs,
        "",
        test_existing_template_map,
        test_config.aws,
    )
    initial_role.iambic_managed = IambicManaged.READ_AND_WRITE
    initial_role.included_accounts = ["*"]
    initial_role.properties.description = [
        description,
        Description(
            description="with a couple normal ones", included_accounts=["dev*"]
        ),
    ]
    imported_role = await create_templated_role(
        test_aws_account_map,
        "test_role",
        test_role_refs,
        "",
        test_existing_template_map,
        test_config.aws,
    )
    imported_role.iambic_managed = IambicManaged.READ_AND_WRITE
    imported_role.included_accounts = ["*"]

    # Using the explicit account names in the list of included accounts to emulate the value generated on import
    imported_role.properties.description = [
        description,
        Description(
            description="with a couple normal ones",
            included_accounts=[test_account.account_name, test_account_2.account_name],
        ),
    ]

    merged_model = merge_model(
        imported_role,
        initial_role,
        [test_account, test_account_2, non_standard_account],
    )
    assert isinstance(merged_model.properties.description, list)
    assert len(merged_model.properties.description) == 2
    assert (
        merged_model.properties.description[0].description
        == "test the weird account name"
    )
    assert merged_model.properties.description[0].included_accounts == [
        non_standard_account.account_name
    ]


@pytest.mark.asyncio
async def test_merge_template_role_with_excluded_accounts_rule_preservation(
    test_config,
    test_role,
    test_account,
    test_account_2,
    mock_account_id_to_role_map,
    mock_write,
):
    """
    Check that an excluded account rule with a wildcard is preserved
    """
    test_account_3 = AWSAccount(
        account_id="123456789013",
        account_name="prod",
        assume_role_arn="",
    )
    account_list = [test_account, test_account_2, test_account_3]
    test_aws_account_map = get_aws_account_map(account_list)
    test_role_ref = test_role.properties.dict()
    test_role_ref["account_id"] = test_account.account_id
    test_role_refs = [test_role_ref]
    test_existing_template_map = {}
    initial_role = await create_templated_role(
        test_aws_account_map,
        "test_role",
        test_role_refs,
        "",
        test_existing_template_map,
        test_config.aws,
    )
    initial_role.iambic_managed = IambicManaged.READ_AND_WRITE
    initial_role.included_accounts = ["prod*"]
    initial_role.excluded_accounts = ["dev*"]
    imported_role = await create_templated_role(
        test_aws_account_map,
        "test_role",
        test_role_refs,
        "",
        test_existing_template_map,
        test_config.aws,
    )
    imported_role.iambic_managed = IambicManaged.READ_AND_WRITE
    imported_role.included_accounts = [
        test_account.account_name,
        test_account_3.account_name,
    ]

    merged_model = merge_model(imported_role, initial_role, account_list)
    assert "prod*" in merged_model.included_accounts
    assert "dev*" in merged_model.excluded_accounts
    assert test_account.account_name in merged_model.included_accounts


@pytest.mark.asyncio
async def test_merge_template_role_with_wildcard_include_and_excluded_accounts_rule_preservation(
    test_config,
    test_role,
    test_account,
    test_account_2,
    mock_account_id_to_role_map,
    mock_write,
):
    """
    Check that an excluded account rule with a wildcard is preserved
    """
    test_account_3 = AWSAccount(
        account_id="123456789013",
        account_name="prod",
        assume_role_arn="",
    )
    account_list = [test_account, test_account_2, test_account_3]
    test_aws_account_map = get_aws_account_map(account_list)
    test_role_ref = test_role.properties.dict()
    test_role_ref["account_id"] = test_account.account_id
    test_role_refs = [test_role_ref]
    test_existing_template_map = {}
    initial_role = await create_templated_role(
        test_aws_account_map,
        "test_role",
        test_role_refs,
        "",
        test_existing_template_map,
        test_config.aws,
    )
    initial_role.iambic_managed = IambicManaged.READ_AND_WRITE
    initial_role.included_accounts = ["*"]
    initial_role.excluded_accounts = ["dev*"]
    imported_role = await create_templated_role(
        test_aws_account_map,
        "test_role",
        test_role_refs,
        "",
        test_existing_template_map,
        test_config.aws,
    )
    imported_role.iambic_managed = IambicManaged.READ_AND_WRITE
    imported_role.included_accounts = [
        test_account.account_name,
        test_account_3.account_name,
    ]

    merged_model = merge_model(imported_role, initial_role, account_list)
    assert "*" in merged_model.included_accounts
    assert "dev*" in merged_model.excluded_accounts
    assert test_account.account_name in merged_model.included_accounts


@pytest.mark.asyncio
async def test_merge_template_role_with_new_include_account(
    test_config, test_role, mock_account_id_to_role_map, mock_write
):
    """
    Check that an account that hits on a wildcard for included account is not explicitly added to included accounts
    """

    test_account = AWSAccount(
        account_id="123456789011", account_name="dev", assume_role_arn=""
    )
    test_account_2 = AWSAccount(
        account_id="123456789012", account_name="dev_2", assume_role_arn=""
    )
    test_aws_account_map = {
        test_account.account_name: test_account,
        test_account.account_id: test_account,
        test_account_2.account_name: test_account_2,
        test_account_2.account_id: test_account_2,
    }
    test_role_ref = test_role.properties.dict()
    test_role_ref["account_id"] = test_account.account_id
    test_role_refs = [test_role_ref]
    test_existing_template_map = {}

    initial_role = await create_templated_role(
        test_aws_account_map,
        "test_role",
        test_role_refs,
        "",
        test_existing_template_map,
        test_config.aws,
    )
    initial_role.iambic_managed = IambicManaged.READ_AND_WRITE
    initial_role.included_accounts = ["dev_*"]
    updated_role = await create_templated_role(
        test_aws_account_map,
        "test_role",
        test_role_refs,
        "",
        test_existing_template_map,
        test_config.aws,
    )
    updated_role.iambic_managed = IambicManaged.READ_AND_WRITE
    updated_role.included_accounts = [
        test_account.account_name,
        test_account_2.account_name,
    ]

    merged_model = merge_model(
        updated_role, initial_role, [test_account, test_account_2]
    )
    assert test_account.account_name in merged_model.included_accounts
    assert initial_role.included_accounts[0] in merged_model.included_accounts


@pytest.mark.asyncio
async def test_merge_template_role_with_wildcard_move_from_exclude(
    test_config,
    test_role,
    test_account,
    test_account_2,
    mock_account_id_to_role_map,
    mock_write,
):
    """
    Check that the wildcard for included account is preserved when merging
    Also confirm the previously excluded account has been removed from excluded accounts
    """
    test_aws_account_map = get_aws_account_map([test_account, test_account_2])
    test_role_ref = test_role.properties.dict()
    test_role_ref["account_id"] = test_account.account_id
    test_role_refs = [test_role_ref]
    test_existing_template_map = {}

    initial_role = await create_templated_role(
        test_aws_account_map,
        "test_role",
        test_role_refs,
        "",
        test_existing_template_map,
        test_config.aws,
    )
    initial_role.iambic_managed = IambicManaged.READ_AND_WRITE
    initial_role.included_accounts = ["dev*"]
    initial_role.excluded_accounts = [test_account_2.account_name]
    updated_role = await create_templated_role(
        test_aws_account_map,
        "test_role",
        test_role_refs,
        "",
        test_existing_template_map,
        test_config.aws,
    )
    updated_role.iambic_managed = IambicManaged.READ_AND_WRITE
    updated_role.included_accounts = [
        test_account.account_name,
        test_account_2.account_name,
    ]

    merged_model = merge_model(
        updated_role, initial_role, [test_account, test_account_2]
    )
    assert merged_model.included_accounts == initial_role.included_accounts
    assert test_account_2.account_name not in merged_model.excluded_accounts


@pytest.mark.asyncio
async def test_merge_template_role_with_explicit_exclude_on_policy(
    test_config,
    test_role,
    test_account,
    test_account_2,
    mock_account_id_to_role_map,
    mock_write,
):
    test_aws_account_map = get_aws_account_map([test_account, test_account_2])
    test_role_ref = test_role.properties.dict()
    inline_policies = [
        {
            "policy_name": "spoke-acct-policy",
            "included_accounts": [
                test_account.account_name,
                test_account_2.account_name,
            ],
            "statement": [
                {
                    "action": [
                        "config:BatchGet*",
                    ],
                    "effect": "Allow",
                    "resource": "*",
                }
            ],
            "version": "2012-10-17",
        }
    ]

    test_role_ref["account_id"] = test_account.account_id
    test_role_refs = [test_role_ref]
    test_existing_template_map = {}

    initial_role = await create_templated_role(
        test_aws_account_map,
        "test_role",
        test_role_refs,
        "",
        test_existing_template_map,
        test_config.aws,
    )
    initial_role.iambic_managed = IambicManaged.READ_AND_WRITE
    initial_role.included_accounts = [
        test_account.account_name,
        test_account_2.account_name,
    ]
    initial_role.properties.inline_policies = inline_policies
    updated_role = await create_templated_role(
        test_aws_account_map,
        "test_role",
        test_role_refs,
        "",
        test_existing_template_map,
        test_config.aws,
    )
    updated_role.iambic_managed = IambicManaged.READ_AND_WRITE
    updated_role.included_accounts = [
        test_account.account_name,
        test_account_2.account_name,
    ]
    updated_role.properties.inline_policies = inline_policies
    updated_role.properties.inline_policies[0]["included_accounts"] = [
        test_account.account_name
    ]

    merged_model = merge_model(
        updated_role, initial_role, [test_account, test_account_2]
    )
    mm_inline_policy = merged_model.properties.inline_policies[0]
    assert test_account_2.account_name not in mm_inline_policy["included_accounts"]
    assert test_account_2.account_name not in mm_inline_policy.get(
        "excluded_accounts", []
    )


@pytest.mark.asyncio
async def test_merge_template_role_with_removed_policy(
    test_config,
    test_role,
    test_account,
    test_account_2,
    mock_account_id_to_role_map,
    mock_write,
):
    test_aws_account_map = get_aws_account_map([test_account, test_account_2])
    test_role_ref = test_role.properties.dict()
    inline_policies = [
        {
            "policy_name": "spoke-acct-policy",
            "included_accounts": [
                test_account.account_name,
                test_account_2.account_name,
            ],
            "statement": [
                {
                    "action": [
                        "config:BatchGet*",
                    ],
                    "effect": "Allow",
                    "resource": "*",
                }
            ],
            "version": "2012-10-17",
        }
    ]

    test_role_ref["account_id"] = test_account.account_id
    test_role_refs = [test_role_ref]
    test_existing_template_map = {}

    initial_role = await create_templated_role(
        test_aws_account_map,
        "test_role",
        test_role_refs,
        "",
        test_existing_template_map,
        test_config.aws,
    )
    initial_role.iambic_managed = IambicManaged.READ_AND_WRITE
    initial_role.included_accounts = [
        test_account.account_name,
        test_account_2.account_name,
    ]
    initial_role.properties.inline_policies = inline_policies
    updated_role = await create_templated_role(
        test_aws_account_map,
        "test_role",
        test_role_refs,
        "",
        test_existing_template_map,
        test_config.aws,
    )
    updated_role.iambic_managed = IambicManaged.READ_AND_WRITE
    updated_role.included_accounts = [
        test_account.account_name,
        test_account_2.account_name,
    ]
    merged_model = merge_model(
        updated_role, initial_role, [test_account, test_account_2]
    )
    assert not merged_model.properties.inline_policies


@pytest.mark.asyncio
async def test_merge_template_role_with_import_rule(
    test_config,
    test_role,
    test_account,
    test_account_2,
    mock_account_id_to_role_map_import,
    mock_write,
):
    """
    The test_rules in this test validate that the `iambic_managed` setting
    is set correctly based on the rules. In the event that the rules tell us
    to ignore a resource (for example, because the resource is managed by other IaC),
    the result of calling `create_templated_role` is None.
    """
    from iambic.plugins.v0_1_0.aws.iambic_plugin import (
        ImportAction,
        ImportRule,
        ImportRuleTag,
    )

    test_rules = [
        {
            "rules": [
                ImportRule(
                    match_tags=[ImportRuleTag(key="terraform")],
                    action=ImportAction.set_import_only,
                ),
            ],
            "result": "import_only",
        },
        {
            "rules": [
                ImportRule(
                    match_tags=[ImportRuleTag(key="tagkey", value="tagvalue")],
                    action=ImportAction.set_import_only,
                )
            ],
            "result": "undefined",
        },
        {
            "rules": [ImportRule(match_names=["test*"], action=ImportAction.ignore)],
            "result": None,
        },
        {
            "rules": [
                ImportRule(match_names=["AWSServiceRole*"], action=ImportAction.ignore)
            ],
            "result": "undefined",
        },
        {
            "rules": [
                ImportRule(
                    match_paths=["/service-role/*", "/aws-service-role/*"],
                    action=ImportAction.ignore,
                )
            ],
            "result": "undefined",
        },
        {
            "rules": [
                ImportRule(
                    match_paths=["/"],
                    action=ImportAction.ignore,
                )
            ],
            "result": None,
        },
        {
            "rules": [
                ImportRule(
                    match_tags=[{"key": "ManagedBy", "value": "CDK"}],
                    action=ImportAction.ignore,
                )
            ],
            "result": "undefined",
        },
        {
            "rules": [
                ImportRule(
                    match_template_types=["NOQ::AWS::IAM::Role"],
                    match_tags=[ImportRuleTag(key="terraform", value="tagvalue")],
                    action=ImportAction.set_import_only,
                )
            ],
            "result": "undefined",
        },
    ]

    for test_rule in test_rules:
        test_config = copy.deepcopy(test_config)
        test_config.aws.import_rules = test_rule["rules"]
        test_aws_account_map = get_aws_account_map([test_account, test_account_2])
        test_role_ref = copy.deepcopy(test_role.properties.dict())
        test_role_ref["account_id"] = test_account.account_id
        test_role_refs = [test_role_ref]
        test_existing_template_map = {}

        role_template = await create_templated_role(
            test_aws_account_map,
            "test_role",
            test_role_refs,
            "",
            test_existing_template_map,
            test_config.aws,
        )

        if not test_rule["result"]:
            assert role_template is None
        else:
            assert role_template.iambic_managed.value == test_rule["result"]
